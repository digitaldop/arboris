from calendar import monthrange
from collections import defaultdict
from datetime import date, time, timedelta
from decimal import Decimal
from urllib.parse import urlencode

from django.utils import timezone

from economia.models import PrestazioneScambioRetta
from scuola.models import AnnoScolastico
from scuola.utils import resolve_default_anno_scolastico


MONTH_LABELS = {
    1: "Gennaio",
    2: "Febbraio",
    3: "Marzo",
    4: "Aprile",
    5: "Maggio",
    6: "Giugno",
    7: "Luglio",
    8: "Agosto",
    9: "Settembre",
    10: "Ottobre",
    11: "Novembre",
    12: "Dicembre",
}

WEEKDAY_SHORT_LABELS = ["Lun", "Mar", "Mer", "Gio", "Ven", "Sab", "Dom"]
WEEKDAY_FULL_LABELS = [
    "Lunedi",
    "Martedi",
    "Mercoledi",
    "Giovedi",
    "Venerdi",
    "Sabato",
    "Domenica",
]


def resolve_current_school_year():
    return resolve_default_anno_scolastico(AnnoScolastico.objects.filter(attivo=True))


def normalize_scambio_view(value):
    if value in {"week", "month"}:
        return value
    return "list"


def parse_iso_date(value):
    if not value:
        return None

    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        return None


def clamp_date_to_school_year(target_date, anno_scolastico):
    if target_date < anno_scolastico.data_inizio:
        return anno_scolastico.data_inizio
    if target_date > anno_scolastico.data_fine:
        return anno_scolastico.data_fine
    return target_date


def chunk_list(items, size):
    return [items[index:index + size] for index in range(0, len(items), size)]


def build_inline_query(anno_scolastico_id, view_name, week_start=None, month_start=None):
    params = {
        "scambio_year": anno_scolastico_id,
        "scambio_view": view_name,
    }

    if view_name == "week" and week_start:
        params["scambio_week"] = week_start.isoformat()
    if view_name == "month" and month_start:
        params["scambio_month"] = month_start.isoformat()

    return urlencode(params)


def resolve_reference_date(anno_scolastico, prestazioni):
    today = timezone.localdate()
    if anno_scolastico.data_inizio <= today <= anno_scolastico.data_fine:
        return today

    if prestazioni:
        return prestazioni[0].data

    return anno_scolastico.data_inizio


def build_week_context(anno_scolastico, prestazioni, requested_week=None):
    requested_week = requested_week or resolve_reference_date(anno_scolastico, prestazioni)
    requested_week = clamp_date_to_school_year(requested_week, anno_scolastico)

    min_week_start = anno_scolastico.data_inizio - timedelta(days=anno_scolastico.data_inizio.weekday())
    max_week_start = anno_scolastico.data_fine - timedelta(days=anno_scolastico.data_fine.weekday())
    week_start = requested_week - timedelta(days=requested_week.weekday())
    if week_start < min_week_start:
        week_start = min_week_start
    if week_start > max_week_start:
        week_start = max_week_start

    week_end = week_start + timedelta(days=6)
    entries_by_date = defaultdict(list)
    for prestazione in prestazioni:
        entries_by_date[prestazione.data].append(prestazione)

    days = []
    total_hours = Decimal("0.00")
    total_amount = Decimal("0.00")
    today = timezone.localdate()

    for offset in range(7):
        current_day = week_start + timedelta(days=offset)
        day_entries = sorted(
            entries_by_date.get(current_day, []),
            key=lambda item: (item.ora_ingresso or time.max, item.id),
        )

        for entry in day_entries:
            total_hours += entry.ore_lavorate or Decimal("0.00")
            total_amount += entry.importo_maturato or Decimal("0.00")

        days.append(
            {
                "date": current_day,
                "weekday_short": WEEKDAY_SHORT_LABELS[current_day.weekday()],
                "weekday_full": WEEKDAY_FULL_LABELS[current_day.weekday()],
                "entries": day_entries,
                "is_today": current_day == today,
                "is_inside_year": anno_scolastico.data_inizio <= current_day <= anno_scolastico.data_fine,
            }
        )

    prev_week_start = week_start - timedelta(days=7)
    next_week_start = week_start + timedelta(days=7)

    return {
        "title": f"{week_start.strftime('%d/%m/%Y')} - {week_end.strftime('%d/%m/%Y')}",
        "days": days,
        "week_start": week_start,
        "week_end": week_end,
        "has_prev": prev_week_start >= min_week_start,
        "has_next": next_week_start <= max_week_start,
        "prev_query": build_inline_query(anno_scolastico.id, "week", week_start=prev_week_start),
        "next_query": build_inline_query(anno_scolastico.id, "week", week_start=next_week_start),
        "total_hours": total_hours.quantize(Decimal("0.01")),
        "total_amount": total_amount.quantize(Decimal("0.01")),
    }


def build_month_context(anno_scolastico, prestazioni, requested_month=None):
    requested_month = requested_month or resolve_reference_date(anno_scolastico, prestazioni)
    requested_month = clamp_date_to_school_year(requested_month, anno_scolastico)

    min_month_start = anno_scolastico.data_inizio.replace(day=1)
    max_month_start = anno_scolastico.data_fine.replace(day=1)
    month_start = requested_month.replace(day=1)
    if month_start < min_month_start:
        month_start = min_month_start
    if month_start > max_month_start:
        month_start = max_month_start

    month_end = date(month_start.year, month_start.month, monthrange(month_start.year, month_start.month)[1])
    grid_start = month_start - timedelta(days=month_start.weekday())
    grid_end = month_end + timedelta(days=(6 - month_end.weekday()))

    entries_by_date = defaultdict(list)
    for prestazione in prestazioni:
        entries_by_date[prestazione.data].append(prestazione)

    today = timezone.localdate()
    cells = []
    total_hours = Decimal("0.00")
    total_amount = Decimal("0.00")
    current_day = grid_start

    while current_day <= grid_end:
        day_entries = sorted(
            entries_by_date.get(current_day, []),
            key=lambda item: (item.ora_ingresso or time.max, item.id),
        )

        if month_start <= current_day <= month_end:
            for entry in day_entries:
                total_hours += entry.ore_lavorate or Decimal("0.00")
                total_amount += entry.importo_maturato or Decimal("0.00")

        cells.append(
            {
                "date": current_day,
                "entries": day_entries,
                "is_today": current_day == today,
                "is_current_month": current_day.month == month_start.month and current_day.year == month_start.year,
                "is_inside_year": anno_scolastico.data_inizio <= current_day <= anno_scolastico.data_fine,
            }
        )
        current_day += timedelta(days=1)

    prev_month_start = (month_start.replace(day=1) - timedelta(days=1)).replace(day=1)
    next_month_start = (month_end + timedelta(days=1)).replace(day=1)

    return {
        "title": f"{MONTH_LABELS.get(month_start.month, month_start.month)} {month_start.year}",
        "weekday_labels": WEEKDAY_SHORT_LABELS,
        "rows": chunk_list(cells, 7),
        "month_start": month_start,
        "month_end": month_end,
        "has_prev": prev_month_start >= min_month_start,
        "has_next": next_month_start <= max_month_start,
        "prev_query": build_inline_query(anno_scolastico.id, "month", month_start=prev_month_start),
        "next_query": build_inline_query(anno_scolastico.id, "month", month_start=next_month_start),
        "total_hours": total_hours.quantize(Decimal("0.01")),
        "total_amount": total_amount.quantize(Decimal("0.01")),
    }


def build_familiare_scambio_retta_inline_context(familiare, params):
    if not familiare or not familiare.pk or not familiare.abilitato_scambio_retta:
        return {
            "enabled": False,
            "sections": [],
        }

    prestazioni = list(
        PrestazioneScambioRetta.objects.filter(familiare=familiare)
        .select_related("anno_scolastico", "studente", "tariffa_scambio_retta")
        .order_by("-data", "-ora_ingresso", "-id")
    )

    current_year = resolve_current_school_year()
    years_by_id = {}
    ordered_years = []

    if current_year:
        years_by_id[current_year.id] = current_year
        ordered_years.append(current_year)

    for prestazione in prestazioni:
        anno = prestazione.anno_scolastico
        if anno.id in years_by_id:
            continue
        years_by_id[anno.id] = anno
        ordered_years.append(anno)

    if current_year:
        other_years = sorted(
            [year for year in ordered_years if year.id != current_year.id],
            key=lambda item: (item.data_inizio, item.id),
            reverse=True,
        )
        ordered_years = [current_year, *other_years]
    else:
        ordered_years = sorted(ordered_years, key=lambda item: (item.data_inizio, item.id), reverse=True)

    active_year = None
    requested_year = params.get("scambio_year")
    if requested_year:
        try:
            active_year = years_by_id.get(int(requested_year))
        except (TypeError, ValueError):
            active_year = None

    if not active_year:
        active_year = current_year or (ordered_years[0] if ordered_years else None)

    active_view = normalize_scambio_view(params.get("scambio_view"))
    requested_week = parse_iso_date(params.get("scambio_week"))
    requested_month = parse_iso_date(params.get("scambio_month"))

    prestazioni_by_year = defaultdict(list)
    for prestazione in prestazioni:
        prestazioni_by_year[prestazione.anno_scolastico_id].append(prestazione)

    sections = []
    total_hours = Decimal("0.00")
    total_amount = Decimal("0.00")

    for anno_scolastico in ordered_years:
        year_entries = prestazioni_by_year.get(anno_scolastico.id, [])
        year_total_hours = sum(
            ((entry.ore_lavorate or Decimal("0.00")) for entry in year_entries),
            Decimal("0.00"),
        )
        year_total_amount = sum(
            ((entry.importo_maturato or Decimal("0.00")) for entry in year_entries),
            Decimal("0.00"),
        )
        total_hours += year_total_hours
        total_amount += year_total_amount

        default_reference = resolve_reference_date(anno_scolastico, year_entries)
        default_week_start = default_reference - timedelta(days=default_reference.weekday())
        default_month_start = default_reference.replace(day=1)

        section = {
            "anno_scolastico": anno_scolastico,
            "entries": year_entries,
            "entry_count": len(year_entries),
            "total_hours": year_total_hours.quantize(Decimal("0.01")),
            "total_amount": year_total_amount.quantize(Decimal("0.01")),
            "is_current": bool(current_year and anno_scolastico.id == current_year.id),
            "is_active": bool(active_year and anno_scolastico.id == active_year.id),
            "default_reference": default_reference,
            "default_open": bool((active_year and anno_scolastico.id == active_year.id) or (current_year and anno_scolastico.id == current_year.id)),
            "collapsible_storage_key": f"arboris-familiare-scambio-anno-{familiare.id}-{anno_scolastico.id}",
            "list_query": build_inline_query(anno_scolastico.id, "list"),
            "week_query": build_inline_query(anno_scolastico.id, "week", week_start=default_week_start),
            "month_query": build_inline_query(anno_scolastico.id, "month", month_start=default_month_start),
            "week": None,
            "month": None,
        }

        if section["is_active"] and active_view == "week":
            section["week"] = build_week_context(anno_scolastico, year_entries, requested_week=requested_week)
        elif section["is_active"] and active_view == "month":
            section["month"] = build_month_context(anno_scolastico, year_entries, requested_month=requested_month)

        sections.append(section)

    return {
        "enabled": True,
        "sections": sections,
        "active_view": active_view,
        "active_year": active_year,
        "has_any_entries": bool(prestazioni),
        "total_entries": len(prestazioni),
        "total_hours": total_hours.quantize(Decimal("0.01")),
        "total_amount": total_amount.quantize(Decimal("0.01")),
        "missing_school_year_configuration": not ordered_years,
    }
