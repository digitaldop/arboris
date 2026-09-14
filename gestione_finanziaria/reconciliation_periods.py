"""Calendar evidence shared by tuition matching and stored proposal display."""
import re
from datetime import date


MONTHS = (
    "Gennaio", "Febbraio", "Marzo", "Aprile", "Maggio", "Giugno",
    "Luglio", "Agosto", "Settembre", "Ottobre", "Novembre", "Dicembre",
)
_MONTH_PATTERN = re.compile(
    r"\b(" + "|".join(MONTHS) + r")\b(?:\s+(?:del\s+)?(20\d{2}|\d{2})(?!\d))?",
    re.IGNORECASE,
)


def rate_period_evidence(*, year, month, due_date, movement_date, description):
    """Return a score ceiling, chronological tie-break and explanation.

    Identity and amount alone must not saturate every monthly alternative.
    An explicit month takes precedence over the booking date (arrears/advances).
    """
    distance = abs((due_date - movement_date).days) if due_date and movement_date else 99999
    periods = set()
    for match in _MONTH_PATTERN.finditer(description or ""):
        mentioned_month = next(i for i, name in enumerate(MONTHS, 1) if name.casefold() == match[1].casefold())
        mentioned_year = int(match[2]) if match[2] else None
        if mentioned_year is not None and mentioned_year < 100:
            mentioned_year += 2000
        if mentioned_year is None and movement_date:
            mentioned_year = min(
                range(movement_date.year - 1, movement_date.year + 2),
                key=lambda value: abs((date(value, mentioned_month, 15) - movement_date).days),
            )
        periods.add((mentioned_year, mentioned_month))
    if periods and year and month:
        if (year, month) in periods or (None, month) in periods:
            return 100, (0, distance), "Mese della rata corrispondente al periodo indicato nella causale"
        return 74, (3, distance), "Periodo della rata diverso da quello indicato nella causale"
    if movement_date and (year, month) == (movement_date.year, movement_date.month):
        return 98, (1, distance), "Mese della rata corrispondente al mese del movimento"
    if distance <= 30:
        return 90, (2, distance), "Scadenza entro 30 giorni dal movimento"
    return 84, (3, distance), "Periodo della rata non confermato dalla data del movimento"


def rate_movement_evidence(rate, movement):
    monthly = getattr(rate, "tipo_rata", "mensile") == "mensile"
    due = rate.data_scadenza
    return rate_period_evidence(
        year=rate.anno_riferimento if monthly else (due.year if due else None),
        month=rate.mese_riferimento if monthly else (due.month if due else None),
        due_date=due, movement_date=movement.data_contabile,
        description=movement.descrizione if monthly else "",
    )
