import gzip
import os
import shutil
import subprocess
import tempfile
from datetime import timedelta
from glob import glob
from pathlib import Path
from uuid import uuid4

from django.conf import settings
from django.core.files import File
from django.db import OperationalError, ProgrammingError, connections, transaction
from django.template.defaultfilters import filesizeformat
from django.utils import timezone
from django.utils.text import get_valid_filename

from .models import (
    FrequenzaBackupAutomatico,
    SistemaBackupDatabaseConfigurazione,
    SistemaDatabaseBackup,
    TipoBackupDatabase,
)


MAX_DATABASE_BACKUPS = 10


class DatabaseBackupError(Exception):
    def __init__(self, message, *, safety_backup=None):
        super().__init__(message)
        self.safety_backup = safety_backup


def format_size_label(size_bytes):
    return filesizeformat(size_bytes or 0)


def ensure_postgresql_database():
    db_settings = connections["default"].settings_dict
    engine = db_settings.get("ENGINE", "")
    if "postgresql" not in engine:
        raise DatabaseBackupError("Il modulo backup supporta attualmente solo database PostgreSQL.")
    return db_settings


def get_backup_configuration():
    configurazione, _ = SistemaBackupDatabaseConfigurazione.objects.get_or_create(pk=1)
    return configurazione


def get_backup_root():
    backup_root = Path(settings.MEDIA_ROOT) / "database_backups"
    backup_root.mkdir(parents=True, exist_ok=True)
    return backup_root


def get_pending_restore_root():
    restore_root = get_backup_root() / "_pending_restore"
    restore_root.mkdir(parents=True, exist_ok=True)
    return restore_root


def get_postgres_server_major_version():
    try:
        ensure_postgresql_database()
        with connections["default"].cursor() as cursor:
            cursor.execute("SHOW server_version_num")
            row = cursor.fetchone()
    except Exception:
        return None

    if not row:
        return None

    try:
        return int(row[0]) // 10000
    except (TypeError, ValueError):
        return None


def extract_postgres_version_from_path(candidate):
    try:
        path = Path(candidate)
    except TypeError:
        return None

    parts = [part.lower() for part in path.parts]
    for index, part in enumerate(parts):
        if part == "postgresql" and index + 1 < len(parts):
            try:
                return int(path.parts[index + 1])
            except (TypeError, ValueError):
                return None
    return None


def locate_postgres_utility(executable_name):
    preferred_bin_dir = getattr(settings, "POSTGRESQL_BIN_DIR", "")
    explicit_candidates = []
    candidates = []

    if preferred_bin_dir:
        explicit_candidates.append(Path(preferred_bin_dir) / executable_name)
        explicit_candidates.append(Path(preferred_bin_dir) / f"{executable_name}.exe")

    discovered = shutil.which(executable_name) or shutil.which(f"{executable_name}.exe")
    if discovered:
        candidates.append(Path(discovered))

    for pattern in (
        f"C:/Program Files/PostgreSQL/*/bin/{executable_name}.exe",
        f"C:/Program Files/PostgreSQL/*/bin/{executable_name}",
        f"C:/Program Files (x86)/PostgreSQL/*/bin/{executable_name}.exe",
        f"C:/Program Files (x86)/PostgreSQL/*/bin/{executable_name}",
    ):
        candidates.extend(Path(path) for path in glob(pattern))

    for candidate in explicit_candidates:
        if candidate and Path(candidate).exists():
            return str(candidate)

    unique_candidates = []
    seen_candidates = set()
    for candidate in candidates:
        candidate_path = Path(candidate)
        candidate_key = str(candidate_path).lower()
        if candidate_key in seen_candidates or not candidate_path.exists():
            continue
        seen_candidates.add(candidate_key)
        unique_candidates.append(candidate_path)

    server_major = get_postgres_server_major_version()
    if server_major is not None:
        exact_match_candidates = [
            candidate
            for candidate in unique_candidates
            if extract_postgres_version_from_path(candidate) == server_major
        ]
        if exact_match_candidates:
            return str(exact_match_candidates[0])

    versioned_candidates = [
        candidate
        for candidate in unique_candidates
        if extract_postgres_version_from_path(candidate) is not None
    ]
    if versioned_candidates:
        versioned_candidates.sort(
            key=lambda candidate: extract_postgres_version_from_path(candidate) or -1,
            reverse=True,
        )
        return str(versioned_candidates[0])

    for candidate in unique_candidates:
        if candidate and candidate.exists():
            return str(candidate)

    raise DatabaseBackupError(
        f"Utility PostgreSQL non trovata: {executable_name}. Verifica che pg_dump e psql siano installati sul server."
    )


def build_postgres_env(db_settings):
    env = os.environ.copy()
    password = db_settings.get("PASSWORD")
    if password:
        env["PGPASSWORD"] = password
    return env


def build_postgres_base_command(executable_path, db_settings):
    command = [executable_path]
    if db_settings.get("HOST"):
        command.extend(["-h", db_settings["HOST"]])
    if db_settings.get("PORT"):
        command.extend(["-p", str(db_settings["PORT"])])
    if db_settings.get("USER"):
        command.extend(["-U", db_settings["USER"]])
    return command


def build_backup_filename(prefix):
    now = timezone.localtime()
    timestamp = now.strftime("%Y%m%d_%H%M%S")
    safe_prefix = get_valid_filename(prefix) or "backup_database"
    return f"{safe_prefix}_{timestamp}.sql.gz"


def run_pg_dump(output_path):
    db_settings = ensure_postgresql_database()
    pg_dump_path = locate_postgres_utility("pg_dump")
    command = build_postgres_base_command(pg_dump_path, db_settings)
    command.extend(
        [
            "--clean",
            "--if-exists",
            "--no-owner",
            "--no-privileges",
            "--encoding=UTF8",
            db_settings["NAME"],
        ]
    )

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    env = build_postgres_env(db_settings)

    with gzip.open(output_path, "wb") as output_handle:
        result = subprocess.run(
            command,
            stdout=output_handle,
            stderr=subprocess.PIPE,
            env=env,
            check=False,
        )

    if result.returncode != 0:
        message = result.stderr.decode("utf-8", errors="ignore").strip()
        raise DatabaseBackupError(message or "Creazione backup non riuscita.")


def delete_backup_record(backup_record):
    file_name = backup_record.file_backup.name
    storage = backup_record.file_backup.storage
    backup_record.delete()

    if file_name:
        try:
            storage.delete(file_name)
        except Exception:
            pass


def purge_old_database_backups(max_backups=MAX_DATABASE_BACKUPS):
    obsolete_backups = list(
        SistemaDatabaseBackup.objects.order_by("-data_creazione", "-id")[max_backups:]
    )
    for backup_record in obsolete_backups:
        delete_backup_record(backup_record)
    return obsolete_backups


def create_database_backup(triggered_by=None, backup_type=TipoBackupDatabase.MANUALE, note=""):
    db_settings = ensure_postgresql_database()
    backup_root = get_backup_root()
    temp_dir = backup_root / "_tmp"
    temp_dir.mkdir(parents=True, exist_ok=True)

    prefix = f"arboris_{db_settings['NAME']}_{backup_type}"
    final_name = build_backup_filename(prefix)
    temp_path = Path(tempfile.mkstemp(prefix="backup_", suffix=".sql.gz", dir=temp_dir)[1])

    try:
        run_pg_dump(temp_path)
        file_size = temp_path.stat().st_size

        backup = SistemaDatabaseBackup(
            tipo_backup=backup_type,
            nome_file=final_name,
            dimensione_file_bytes=file_size,
            creato_da=triggered_by if getattr(triggered_by, "is_authenticated", False) else None,
            note=note,
        )

        with temp_path.open("rb") as backup_handle:
            backup.file_backup.save(final_name, File(backup_handle), save=False)

        backup.save()
        purge_old_database_backups()
        return backup
    finally:
        try:
            temp_path.unlink(missing_ok=True)
        except Exception:
            pass


def is_backup_due(configurazione, now=None):
    now = timezone.localtime(now or timezone.now())
    frequenza = configurazione.frequenza_backup_automatico

    if not frequenza:
        return False

    ultimo_backup = configurazione.ultimo_backup_automatico_at
    if not ultimo_backup:
        return True

    ultimo_backup = timezone.localtime(ultimo_backup)

    if frequenza == FrequenzaBackupAutomatico.GIORNALIERO:
        return ultimo_backup.date() < now.date()
    if frequenza == FrequenzaBackupAutomatico.SETTIMANALE:
        return ultimo_backup.date() <= (now.date() - timedelta(days=7))
    if frequenza == FrequenzaBackupAutomatico.MENSILE:
        return (ultimo_backup.year, ultimo_backup.month) != (now.year, now.month)
    return False


def maybe_run_scheduled_backup(triggered_by=None):
    try:
        with transaction.atomic():
            SistemaBackupDatabaseConfigurazione.objects.get_or_create(pk=1)
            configurazione = SistemaBackupDatabaseConfigurazione.objects.select_for_update().get(pk=1)
            now = timezone.now()

            if not is_backup_due(configurazione, now=now):
                return None

            is_stuck = (
                configurazione.backup_automatico_in_corso
                and configurazione.backup_automatico_avviato_at
                and configurazione.backup_automatico_avviato_at < now - timedelta(hours=2)
            )
            if configurazione.backup_automatico_in_corso and not is_stuck:
                return None

            configurazione.backup_automatico_in_corso = True
            configurazione.backup_automatico_avviato_at = now
            configurazione.ultimo_errore_backup_automatico = ""
            configurazione.save(
                update_fields=[
                    "backup_automatico_in_corso",
                    "backup_automatico_avviato_at",
                    "ultimo_errore_backup_automatico",
                    "data_aggiornamento",
                ]
            )
    except (OperationalError, ProgrammingError):
        return None

    try:
        backup = create_database_backup(
            triggered_by=triggered_by,
            backup_type=TipoBackupDatabase.AUTOMATICO,
            note=f"Backup automatico {configurazione.frequenza_label.lower()}",
        )
    except Exception as exc:
        with transaction.atomic():
            configurazione = SistemaBackupDatabaseConfigurazione.objects.select_for_update().get(pk=1)
            configurazione.backup_automatico_in_corso = False
            configurazione.ultimo_errore_backup_automatico = str(exc)
            configurazione.save(
                update_fields=[
                    "backup_automatico_in_corso",
                    "ultimo_errore_backup_automatico",
                    "data_aggiornamento",
                ]
            )
        return None

    with transaction.atomic():
        configurazione = SistemaBackupDatabaseConfigurazione.objects.select_for_update().get(pk=1)
        configurazione.backup_automatico_in_corso = False
        configurazione.ultimo_backup_automatico_at = timezone.now()
        configurazione.ultimo_errore_backup_automatico = ""
        configurazione.save(
            update_fields=[
                "backup_automatico_in_corso",
                "ultimo_backup_automatico_at",
                "ultimo_errore_backup_automatico",
                "data_aggiornamento",
            ]
        )

    return backup


def store_pending_restore_upload(uploaded_file):
    restore_root = get_pending_restore_root()
    safe_name = get_valid_filename(uploaded_file.name or "backup.sql.gz") or "backup.sql.gz"
    target_name = f"{uuid4().hex}_{safe_name}"
    target_path = restore_root / target_name

    with target_path.open("wb") as destination:
        for chunk in uploaded_file.chunks():
            destination.write(chunk)

    file_size = target_path.stat().st_size
    return {
        "path": str(target_path),
        "original_name": uploaded_file.name,
        "size_bytes": file_size,
        "size_label": format_size_label(file_size),
    }


def delete_pending_restore_upload(metadata):
    if not metadata:
        return

    file_path = metadata.get("path")
    if not file_path:
        return

    try:
        Path(file_path).unlink(missing_ok=True)
    except Exception:
        pass


def restore_database_from_backup_file(file_path, original_name="", triggered_by=None):
    file_path = Path(file_path)
    if not file_path.exists():
        raise DatabaseBackupError("Il file di backup selezionato non esiste piu.")

    safety_backup = create_database_backup(
        triggered_by=triggered_by,
        backup_type=TipoBackupDatabase.SICUREZZA_RIPRISTINO,
        note=f"Backup di sicurezza creato prima del ripristino da {original_name or file_path.name}",
    )

    db_settings = ensure_postgresql_database()
    psql_path = locate_postgres_utility("psql")
    command = build_postgres_base_command(psql_path, db_settings)
    command.extend(["-d", db_settings["NAME"], "-v", "ON_ERROR_STOP=1"])
    env = build_postgres_env(db_settings)

    connections.close_all()

    open_handler = gzip.open if file_path.suffix.lower() == ".gz" else open

    try:
        with open_handler(file_path, "rb") as restore_handle:
            result = subprocess.run(
                command,
                stdin=restore_handle,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
                check=False,
            )
    finally:
        connections.close_all()

    if result.returncode != 0:
        error_message = result.stderr.decode("utf-8", errors="ignore").strip()
        raise DatabaseBackupError(
            error_message
            or "Ripristino del database non riuscito. Verifica il file di backup e riprova.",
            safety_backup=safety_backup,
        )

    return safety_backup
