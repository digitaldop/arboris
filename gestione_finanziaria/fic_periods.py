from calendar import monthrange

from django.core.exceptions import ValidationError
from django.utils import timezone


IMPORT_PERIOD_CHOICES = (
    ("1", "1 mese"),
    ("3", "3 mesi"),
    ("6", "6 mesi"),
    ("9", "9 mesi"),
    ("12", "Un anno"),
    ("tutte", "Tutte"),
    ("manuale", "Data manuale"),
)


def import_start_date(period, manual_date=None, *, today=None):
    today = today or timezone.localdate()
    if period == "tutte":
        return None
    if period == "manuale":
        if manual_date is None:
            raise ValidationError("Imposta la data da cui importare le fatture.")
        if manual_date > today:
            raise ValidationError("La data iniziale non può essere successiva a oggi.")
        return manual_date
    if period not in {"1", "3", "6", "9", "12"}:
        raise ValidationError("Seleziona un periodo di importazione valido.")
    year, month_index = divmod(today.year * 12 + today.month - 1 - int(period), 12)
    month = month_index + 1
    return today.replace(year=year, month=month, day=min(today.day, monthrange(year, month)[1]))
