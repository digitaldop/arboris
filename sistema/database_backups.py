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
from django.core.cache import cache
from django.core.files import File
from django.core.files.storage import default_storage
from django.db import OperationalError, ProgrammingError, connections, transaction
from django.template.defaultfilters import filesizeformat
from django.utils import timezone
from django.utils.text import get_valid_filename

from .models import (
    FrequenzaBackupAutomatico,
    SistemaBackupDatabaseConfigurazione,
    SistemaDatabaseBackup,
    SistemaDatabaseRestoreJob,
    StatoRipristinoDatabase,
    TipoBackupDatabase,
)


MAX_DATABASE_BACKUPS = 10
BACKUP_SCHEDULE_CHECK_CACHE_KEY = "sistema:backup_schedule_recent_check"
BACKUP_SCHEDULE_CHECK_TTL_SECONDS = 60


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


def get_database_backups_prefix():
    return (getattr(settings, "DATABASE_BACKUPS_UPLOAD_PREFIX", "db_backups") or "db_backups").strip().strip("/")


def get_restore_uploads_prefix():
    return (getattr(settings, "DATABASE_RESTORE_UPLOAD_PREFIX", "db_restore_uploads") or "db_restore_uploads").strip().strip("/")


def is_absolute_file_reference(file_reference):
    reference = str(file_reference or "").strip()
    if not reference:
        return False
    return Path(reference).is_absolute() or (len(reference) > 1 and reference[1] == ":" and reference[0].isalpha())


def get_restore_upload_storage_name(original_name):
    safe_name = get_valid_filename(Path(original_name or "backup.sql.gz").name) or "backup.sql.gz"
    return f"{get_restore_uploads_prefix()}/{timezone.localtime():%Y/%m}/{uuid4().hex}_{safe_name}"


def restore_file_reference_exists(file_reference):
    reference = str(file_reference or "").strip()
    if not reference:
        return False

    if is_absolute_file_reference(reference):
        return Path(reference).exists()

    try:
        return default_storage.exists(reference)
    except Exception:
        return False


def is_restore_upload_reference(file_reference):
    reference = str(file_reference or "").strip().replace("\\", "/")
    if not reference:
        return False
    restore_prefix = get_restore_uploads_prefix()
    return reference.startswith(f"{restore_prefix}/") or "/_pending_restore/" in reference or reference.endswith("/_pending_restore")


def delete_restore_file_reference(file_reference):
    reference = str(file_reference or "").strip()
    if not reference:
        return

    if is_absolute_file_reference(reference):
        try:
            Path(reference).unlink(missing_ok=True)
        except Exception:
            pass
        return

    try:
        default_storage.delete(reference)
    except Exception:
        pass


def build_restore_temp_suffix(reference_name):
    lower_name = (reference_name or "").lower()
    if lower_name.endswith(".sql.gz"):
        return ".sql.gz"
    if lower_name.endswith(".gz"):
        return ".gz"
    return ".sql"


def materialize_restore_file_reference(file_reference, *, reference_name=""):
    reference = str(file_reference or "").strip()
    if not reference:
        raise DatabaseBackupError("Il file di backup selezionato non esiste piu.")

    if is_absolute_file_reference(reference):
        path = Path(reference)
        if not path.exists():
            raise DatabaseBackupError("Il file di backup selezionato non esiste piu.")
        return path, lambda: None

    suffix = build_restore_temp_suffix(reference_name or reference)
    fd, temp_name = tempfile.mkstemp(prefix="arboris_restore_", suffix=suffix)
    os.close(fd)
    temp_path = Path(temp_name)

    try:
        with default_storage.open(reference, "rb") as source_handle:
            with temp_path.open("wb") as destination_handle:
                shutil.copyfileobj(source_handle, destination_handle)
    except Exception as exc:
        try:
            temp_path.unlink(missing_ok=True)
        except Exception:
            pass
        raise DatabaseBackupError(f"Impossibile leggere il file di backup dallo storage: {exc}") from exc

    return temp_path, lambda: temp_path.unlink(missing_ok=True)


def get_backup_root():
    backup_root = Path(tempfile.gettempdir()) / "arboris_database_backups"
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
    if not cache.add(BACKUP_SCHEDULE_CHECK_CACHE_KEY, True, BACKUP_SCHEDULE_CHECK_TTL_SECONDS):
        return None

    now = timezone.now()

    try:
        configurazione = (
            SistemaBackupDatabaseConfigurazione.objects.only(
                "id",
                "frequenza_backup_automatico",
                "ultimo_backup_automatico_at",
                "backup_automatico_in_corso",
                "backup_automatico_avviato_at",
            )
            .filter(pk=1)
            .first()
        )
        if not configurazione or not is_backup_due(configurazione, now=now):
            return None

        with transaction.atomic():
            configurazione = SistemaBackupDatabaseConfigurazione.objects.select_for_update().get(pk=1)
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
    storage_name = default_storage.save(
        get_restore_upload_storage_name(uploaded_file.name),
        uploaded_file,
    )
    try:
        file_size = default_storage.size(storage_name)
    except Exception:
        file_size = getattr(uploaded_file, "size", 0) or 0

    return {
        "storage_name": storage_name,
        "original_name": uploaded_file.name,
        "size_bytes": file_size,
        "size_label": format_size_label(file_size),
    }


def create_restore_job_from_upload(uploaded_file, triggered_by=None):
    """
    Salva il file nello storage configurato senza elaborarlo e crea un record SistemaDatabaseRestoreJob
    in stato 'in attesa di conferma'.
    """
    meta = store_pending_restore_upload(uploaded_file)
    return SistemaDatabaseRestoreJob.objects.create(
        stato=StatoRipristinoDatabase.IN_ATTESA_CONFERMA,
        percorso_file=meta["storage_name"],
        nome_file_originale=meta["original_name"] or "backup.sql",
        dimensione_file_bytes=meta["size_bytes"],
        creato_da=triggered_by if getattr(triggered_by, "is_authenticated", False) else None,
    )


def create_restore_job_from_backup_record(backup_record, triggered_by=None):
    return SistemaDatabaseRestoreJob.objects.create(
        stato=StatoRipristinoDatabase.IN_ATTESA_CONFERMA,
        percorso_file=backup_record.file_backup.name,
        nome_file_originale=backup_record.nome_file or Path(backup_record.file_backup.name).name,
        dimensione_file_bytes=backup_record.dimensione_file_bytes,
        creato_da=triggered_by if getattr(triggered_by, "is_authenticated", False) else None,
    )


def delete_pending_restore_upload(metadata):
    if not metadata:
        return

    file_reference = metadata.get("storage_name") or metadata.get("path")
    if not file_reference:
        return

    delete_restore_file_reference(file_reference)


def cancel_or_delete_restore_job(job: SistemaDatabaseRestoreJob) -> None:
    """Rimuove file e record per job ancora in attesa di conferma o annullato manualmente."""
    if is_restore_upload_reference(job.percorso_file):
        delete_restore_file_reference(job.percorso_file)
    job.delete()


def restore_database_from_backup_file(file_path, original_name="", triggered_by=None):
    if not restore_file_reference_exists(file_path):
        raise DatabaseBackupError("Il file di backup selezionato non esiste piu.")

    safety_backup = create_database_backup(
        triggered_by=triggered_by,
        backup_type=TipoBackupDatabase.SICUREZZA_RIPRISTINO,
        note=f"Backup di sicurezza creato prima del ripristino da {original_name or Path(str(file_path)).name}",
    )

    materialized_file_path, cleanup_materialized_file = materialize_restore_file_reference(
        file_path,
        reference_name=original_name,
    )

    db_settings = ensure_postgresql_database()
    psql_path = locate_postgres_utility("psql")
    command = build_postgres_base_command(psql_path, db_settings)
    command.extend(["-d", db_settings["NAME"], "-v", "ON_ERROR_STOP=1"])
    env = build_postgres_env(db_settings)

    connections.close_all()

    open_handler = gzip.open if str(original_name or materialized_file_path.name).lower().endswith(".gz") else open

    try:
        with open_handler(materialized_file_path, "rb") as restore_handle:
            result = subprocess.run(
                command,
                stdin=restore_handle,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
                check=False,
            )
    finally:
        cleanup_materialized_file()
        connections.close_all()

    if result.returncode != 0:
        error_message = result.stderr.decode("utf-8", errors="ignore").strip()
        raise DatabaseBackupError(
            error_message
            or "Ripristino del database non riuscito. Verifica il file di backup e riprova.",
            safety_backup=safety_backup,
        )

    return safety_backup
