import gzip
import os
import shutil
import subprocess
import tempfile
from datetime import timedelta
from glob import glob
from pathlib import Path
from urllib.parse import unquote, urlparse
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
RESTORE_PUBLIC_SCHEMA_RESET_SQL = """
DROP SCHEMA IF EXISTS public CASCADE;
CREATE SCHEMA public;
GRANT ALL ON SCHEMA public TO CURRENT_USER;
GRANT USAGE ON SCHEMA public TO PUBLIC;
"""
RESTORE_IGNORABLE_ERROR_MARKERS = (
    "does not exist",
    "doesn't exist",
    "non esiste",
)
RESTORE_IGNORABLE_EXACT_ERROR_MARKERS = (
    'schema "public" already exists',
    "schema public already exists",
    'lo schema "public" esiste gia',
)


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


def normalize_restore_storage_reference(file_reference):
    reference = str(file_reference or "").strip()
    if not reference:
        return ""

    parsed = urlparse(reference)
    if parsed.scheme in {"http", "https"} and parsed.netloc:
        reference = unquote(parsed.path or "").lstrip("/")

        media_url = (getattr(settings, "MEDIA_URL", "") or "").strip("/")
        if media_url and reference.startswith(f"{media_url}/"):
            reference = reference[len(media_url) + 1 :]

        bucket_name = (getattr(settings, "AWS_STORAGE_BUCKET_NAME", "") or "").strip("/")
        if bucket_name and reference.startswith(f"{bucket_name}/"):
            reference = reference[len(bucket_name) + 1 :]

    return reference.replace("\\", "/").lstrip("/")


def restore_file_reference_exists(file_reference):
    reference = normalize_restore_storage_reference(file_reference)
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


def file_looks_gzipped(file_path):
    try:
        with Path(file_path).open("rb") as handle:
            return handle.read(2) == b"\x1f\x8b"
    except OSError:
        return False


def unwrap_gzip_layers(file_path, *, max_layers=3):
    """
    Restituisce un file SQL non compresso, decomprimendo anche eventuali gzip annidati.

    Alcuni backup possono arrivare rinominati o compressi piu volte. Il restore deve
    basarsi sui byte reali del file, non sull'estensione, e deve garantire che a psql
    arrivi testo SQL puro.
    """
    current_path = Path(file_path)
    temporary_paths = []

    try:
        for _ in range(max_layers):
            if not file_looks_gzipped(current_path):
                break

            fd, temp_name = tempfile.mkstemp(prefix="arboris_restore_unwrapped_", suffix=".sql")
            os.close(fd)
            next_path = Path(temp_name)
            try:
                with gzip.open(current_path, "rb") as source_handle:
                    with next_path.open("wb") as destination_handle:
                        shutil.copyfileobj(source_handle, destination_handle)
            except Exception:
                next_path.unlink(missing_ok=True)
                raise

            temporary_paths.append(next_path)
            current_path = next_path

        if file_looks_gzipped(current_path):
            raise DatabaseBackupError("Il file di backup risulta ancora compresso dopo piu livelli gzip.")

        return current_path, lambda: [path.unlink(missing_ok=True) for path in temporary_paths]
    except Exception:
        for path in temporary_paths:
            path.unlink(missing_ok=True)
        raise


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


def is_restore_cleanup_sql_line(line):
    stripped = (line or "").strip()
    if not stripped or stripped.startswith("--"):
        return False

    normalized = stripped.upper()
    if normalized.startswith("DROP "):
        return True
    if normalized.startswith("ALTER TABLE") and " DROP CONSTRAINT " in normalized:
        return True
    if normalized in {"CREATE SCHEMA PUBLIC;", 'CREATE SCHEMA "PUBLIC";'}:
        return True
    return False


def build_sanitized_restore_sql(source_path, *, reference_name=""):
    """
    Crea una copia SQL senza i comandi di cleanup del vecchio dump.

    Arboris resetta gia lo schema public prima del restore. Tenere i DROP/ALTER DROP
    dentro al file importato puo far fallire il ripristino su database vuoto o gia
    ripulito, quindi li rimuoviamo e poi eseguiamo psql con ON_ERROR_STOP=1.
    """
    source_path = Path(source_path)
    suffix = ".sql"
    fd, temp_name = tempfile.mkstemp(prefix="arboris_restore_clean_", suffix=suffix)
    os.close(fd)
    temp_path = Path(temp_name)
    plain_source_path, cleanup_unwrapped_file = unwrap_gzip_layers(source_path)
    in_copy_block = False

    try:
        with plain_source_path.open("rt", encoding="utf-8", errors="ignore", newline="") as source_handle:
            with temp_path.open("w", encoding="utf-8", newline="") as destination_handle:
                for line in source_handle:
                    stripped = line.strip()
                    if in_copy_block:
                        destination_handle.write(line)
                        if stripped == r"\.":
                            in_copy_block = False
                        continue

                    normalized = stripped.upper()
                    if normalized.startswith("COPY ") and normalized.endswith(" FROM STDIN;"):
                        in_copy_block = True
                        destination_handle.write(line)
                        continue

                    if is_restore_cleanup_sql_line(line):
                        continue

                    destination_handle.write(line)
    except Exception as exc:
        try:
            temp_path.unlink(missing_ok=True)
        except Exception:
            pass
        raise DatabaseBackupError(f"Impossibile preparare il file SQL per il ripristino: {exc}") from exc
    finally:
        cleanup_unwrapped_file()

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


def reset_public_schema_for_restore(psql_path, db_settings, env):
    """
    Svuota lo schema applicativo prima del restore.

    Il dump generato con --clean elimina gli oggetti che conosce, ma se il database di
    destinazione contiene tabelle o vincoli piu recenti non presenti nel dump, PostgreSQL
    puo bloccare il drop delle primary key per dipendenze residue. Resettare public rende
    il ripristino coerente con la promessa "sostituisce integralmente il database".
    """
    command = build_postgres_base_command(psql_path, db_settings)
    command.extend(
        [
            "-d",
            db_settings["NAME"],
            "-v",
            "ON_ERROR_STOP=1",
            "-c",
            RESTORE_PUBLIC_SCHEMA_RESET_SQL,
        ]
    )
    result = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        check=False,
    )
    if result.returncode != 0:
        message = result.stderr.decode("utf-8", errors="ignore").strip()
        raise DatabaseBackupError(message or "Preparazione del database al ripristino non riuscita.")


def restore_stderr_has_blocking_errors(stderr_text):
    """
    Dopo il reset dello schema i vecchi dump generati con --clean possono contenere
    comandi DROP/ALTER DROP per oggetti gia rimossi. Questi errori sono innocui; gli
    altri errori SQL devono invece bloccare il ripristino e finire nel log utente.
    """
    for line in (stderr_text or "").splitlines():
        normalized = line.lower()
        if "fatal:" in normalized:
            return True
        if "error:" not in normalized:
            continue
        if any(marker in normalized for marker in RESTORE_IGNORABLE_ERROR_MARKERS):
            continue
        if any(marker in normalized for marker in RESTORE_IGNORABLE_EXACT_ERROR_MARKERS):
            continue
        return True
    return False


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


def store_pending_restore_local_file(file_path, original_name):
    path = Path(file_path)
    storage_name = get_restore_upload_storage_name(original_name or path.name)
    with path.open("rb") as file_handle:
        storage_name = default_storage.save(storage_name, File(file_handle))

    try:
        file_size = default_storage.size(storage_name)
    except Exception:
        file_size = path.stat().st_size if path.exists() else 0

    return {
        "storage_name": storage_name,
        "original_name": original_name or path.name,
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


def create_restore_job_from_local_file(file_path, original_name, triggered_by=None):
    """
    Variante usata dall'upload a blocchi: il file viene ricomposto prima in area temporanea,
    poi salvato nello storage configurato con lo stesso flusso del normale upload.
    """
    meta = store_pending_restore_local_file(file_path, original_name)
    return SistemaDatabaseRestoreJob.objects.create(
        stato=StatoRipristinoDatabase.IN_ATTESA_CONFERMA,
        percorso_file=meta["storage_name"],
        nome_file_originale=meta["original_name"] or "backup.sql",
        dimensione_file_bytes=meta["size_bytes"],
        creato_da=triggered_by if getattr(triggered_by, "is_authenticated", False) else None,
    )


def create_restore_job_from_storage_reference(file_reference, triggered_by=None):
    """
    Prepara un ripristino da un file gia presente nello storage configurato.
    Utile quando il browser non riesce a caricare dump grandi passando da Render/WAF.
    """
    reference = normalize_restore_storage_reference(file_reference)
    if not reference:
        raise DatabaseBackupError("Indica il percorso del file nello storage.")
    lower_reference = reference.lower()
    if not (lower_reference.endswith(".sql") or lower_reference.endswith(".sql.gz")):
        raise DatabaseBackupError("Il file nello storage deve essere in formato .sql o .sql.gz.")
    if not restore_file_reference_exists(reference):
        raise DatabaseBackupError("File non trovato nello storage configurato. Verifica percorso, bucket e permessi.")

    if is_absolute_file_reference(reference):
        file_size = Path(reference).stat().st_size
    else:
        try:
            file_size = default_storage.size(reference)
        except Exception:
            file_size = 0

    return SistemaDatabaseRestoreJob.objects.create(
        stato=StatoRipristinoDatabase.IN_ATTESA_CONFERMA,
        percorso_file=reference,
        nome_file_originale=Path(reference).name or "backup.sql",
        dimensione_file_bytes=file_size,
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

    cleanup_sanitized_file = lambda: None
    try:
        sanitized_file_path, cleanup_sanitized_file = build_sanitized_restore_sql(
            materialized_file_path,
            reference_name=original_name,
        )
        try:
            reset_public_schema_for_restore(psql_path, db_settings, env)
        except DatabaseBackupError as exc:
            raise DatabaseBackupError(str(exc), safety_backup=safety_backup) from exc

        with sanitized_file_path.open("rb") as restore_handle:
            result = subprocess.run(
                command,
                stdin=restore_handle,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
                check=False,
            )
    finally:
        cleanup_sanitized_file()
        cleanup_materialized_file()
        connections.close_all()

    error_message = result.stderr.decode("utf-8", errors="ignore").strip()
    if result.returncode != 0 or restore_stderr_has_blocking_errors(error_message):
        raise DatabaseBackupError(
            error_message
            or "Ripristino del database non riuscito. Verifica il file di backup e riprova.",
            safety_backup=safety_backup,
        )

    return safety_backup
