from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

try:
    from django.core.files.storage import InvalidStorageError
except ImportError:  # pragma: no cover
    try:
        from django.core.files.storage.handler import InvalidStorageError
    except ImportError:  # pragma: no cover
        InvalidStorageError = None

try:
    from botocore.exceptions import BotoCoreError, ClientError
except ImportError:  # pragma: no cover
    BotoCoreError = None
    ClientError = None


DOCUMENT_STORAGE_ERROR_TYPES = [ImproperlyConfigured]
for storage_error_type in (InvalidStorageError, BotoCoreError, ClientError):
    if storage_error_type is not None:
        DOCUMENT_STORAGE_ERROR_TYPES.append(storage_error_type)

DOCUMENT_STORAGE_ERROR_TYPES = tuple(DOCUMENT_STORAGE_ERROR_TYPES)


def build_document_storage_error_message(exc):
    base_message = (
        "Non e stato possibile salvare o leggere il documento sullo storage configurato. "
        "Verifica bucket S3, regione, chiavi AWS e che django-storages/boto3 siano installati sul server."
    )
    if settings.DEBUG:
        return f"{base_message} Dettaglio tecnico: {exc}"
    return base_message
