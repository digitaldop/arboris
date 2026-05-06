from calendar import monthrange

from django.core.cache import cache
from django.db.utils import OperationalError, ProgrammingError
from django.utils import timezone

from .models import SistemaImpostazioniGenerali, SistemaOperazioneCronologia


AUDIT_RETENTION_LAST_CLEANUP_CACHE_KEY = "sistema:audit_retention:last_cleanup"
AUDIT_RETENTION_THROTTLE_SECONDS = 60 * 60 * 12
AUDIT_RETENTION_BATCH_SIZE = 1000
AUDIT_RETENTION_MAX_BATCHES_FORCE = 20


def subtract_months(value, months):
    month_index = value.month - 1 - months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    day = min(value.day, monthrange(year, month)[1])
    return value.replace(year=year, month=month, day=day)


def get_cronologia_cutoff(retention_months, now=None):
    retention_months = int(retention_months or 0)
    if retention_months <= 0:
        return None
    return subtract_months(now or timezone.now(), retention_months)


def cleanup_cronologia_operazioni(*, impostazioni=None, force=False):
    try:
        if impostazioni is None:
            impostazioni = SistemaImpostazioniGenerali.objects.first()

        retention_months = int(
            getattr(
                impostazioni,
                "cronologia_retention_mesi",
                SistemaImpostazioniGenerali._meta.get_field("cronologia_retention_mesi").default,
            )
            or 0
        )
        cutoff = get_cronologia_cutoff(retention_months)
        if cutoff is None:
            return {
                "enabled": False,
                "retention_months": retention_months,
                "cutoff": None,
                "deleted_count": 0,
                "truncated": False,
                "skipped": False,
            }

        if not force and cache.get(AUDIT_RETENTION_LAST_CLEANUP_CACHE_KEY):
            return {
                "enabled": True,
                "retention_months": retention_months,
                "cutoff": cutoff,
                "deleted_count": 0,
                "truncated": False,
                "skipped": True,
            }

        max_batches = AUDIT_RETENTION_MAX_BATCHES_FORCE if force else 1
        deleted_total = 0
        truncated = False
        base_qs = SistemaOperazioneCronologia.objects.filter(data_operazione__lt=cutoff).order_by("id")

        for batch_index in range(max_batches):
            ids = list(base_qs.values_list("id", flat=True)[:AUDIT_RETENTION_BATCH_SIZE])
            if not ids:
                break
            deleted_count, _details = SistemaOperazioneCronologia.objects.filter(id__in=ids).delete()
            deleted_total += deleted_count
            if len(ids) < AUDIT_RETENTION_BATCH_SIZE:
                break
            truncated = batch_index == max_batches - 1

        cache.set(
            AUDIT_RETENTION_LAST_CLEANUP_CACHE_KEY,
            timezone.now().isoformat(),
            timeout=AUDIT_RETENTION_THROTTLE_SECONDS,
        )
        return {
            "enabled": True,
            "retention_months": retention_months,
            "cutoff": cutoff,
            "deleted_count": deleted_total,
            "truncated": truncated,
            "skipped": False,
        }
    except (OperationalError, ProgrammingError, LookupError, ValueError):
        return {
            "enabled": False,
            "retention_months": 0,
            "cutoff": None,
            "deleted_count": 0,
            "truncated": False,
            "skipped": True,
        }
