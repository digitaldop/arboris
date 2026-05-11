from datetime import date, datetime, timedelta

from django.urls import reverse
from django.utils import timezone

from anagrafica.family_logic import build_logical_family_snapshot, logical_family_detail_url
from anagrafica.models import Documento
from economia.models import RataIscrizione
from famiglie_interessate.models import AttivitaFamigliaInteressata, StatoAttivitaFamigliaInteressata
from gestione_finanziaria.models import ScadenzaPagamentoFornitore, StatoScadenzaFornitore
from sistema.models import LivelloPermesso
from sistema.permissions import module_is_enabled, user_has_module_permission

from .models import (
    CategoriaCalendario,
    EventoCalendario,
    SYSTEM_CATEGORY_DOCUMENTS,
    SYSTEM_CATEGORY_INTERESTED_FAMILIES,
    SYSTEM_CATEGORY_RATE_DUE,
    SYSTEM_CATEGORY_SUPPLIER_DUE,
    ensure_system_calendar_categories,
)

ITALIAN_WEEKDAY_NAMES = (
    "Lunedi",
    "Martedi",
    "Mercoledi",
    "Giovedi",
    "Venerdi",
    "Sabato",
    "Domenica",
)


def format_time_value(value):
    return value.strftime("%H:%M") if value else ""


def format_compact_date_label(value):
    return value.strftime("%d/%m/%Y")


def format_weekday_date_label(value):
    return f"{ITALIAN_WEEKDAY_NAMES[value.weekday()]} {format_compact_date_label(value)}"


def build_duration_label(start_date, end_date, all_day, start_time="", end_time=""):
    if all_day:
        if start_date == end_date:
            return "Intera giornata"
        total_days = (end_date - start_date).days + 1
        return "1 giorno" if total_days == 1 else f"{total_days} giorni"

    if not start_time or not end_time:
        return "-"

    start_dt = datetime.combine(start_date, datetime.strptime(start_time, "%H:%M").time())
    end_dt = datetime.combine(end_date, datetime.strptime(end_time, "%H:%M").time())
    duration_minutes = max(int((end_dt - start_dt).total_seconds() // 60), 0)

    if duration_minutes == 0:
        return "-"
    if duration_minutes % 60 == 0:
        hours = duration_minutes // 60
        return "1 h" if hours == 1 else f"{hours} h"
    return f"{duration_minutes} min"


def build_period_label(record):
    start_date = record["start_date"]
    end_date = record["end_date"]
    start_time = record["start_time"]
    end_time = record["end_time"]

    if record["all_day"]:
        if start_date == end_date:
            return "Intera giornata"
        return f"Dal {start_date.strftime('%d/%m')} al {end_date.strftime('%d/%m')}"

    if start_date == end_date:
        return f"{start_time} - {end_time}".strip(" -")

    return f"{start_date.strftime('%d/%m')} {start_time} - {end_date.strftime('%d/%m')} {end_time}".strip()


def build_calendar_entry_record(
    entry_id,
    source,
    title,
    category,
    start_date,
    end_date,
    *,
    detail_label="",
    start_time="",
    end_time="",
    all_day=True,
    location="",
    description="",
    url="",
    external=False,
    open_in_popup=False,
    popup_title="Dettaglio calendario",
    popup_features="",
    visible=True,
    active=True,
    action_label="Apri",
    delete_url="",
    recurrence_summary="",
    is_recurring=False,
    active_object=None,
):
    record = {
        "id": entry_id,
        "source": source,
        "title": title,
        "category_id": category.pk,
        "category_label": category.nome,
        "detail_label": detail_label,
        "start_date": start_date,
        "end_date": end_date,
        "start_time": start_time,
        "end_time": end_time,
        "all_day": all_day,
        "location": location,
        "description": description,
        "url": url,
        "external": external,
        "open_in_popup": open_in_popup,
        "popup_title": popup_title,
        "popup_features": popup_features,
        "color": category.colore,
        "badge_label": category.nome,
        "visibile": visible,
        "attivo": active,
        "action_label": action_label,
        "delete_url": delete_url,
        "recurrence_summary": recurrence_summary,
        "is_recurring": is_recurring,
        "active_object": active_object,
    }
    record["duration_label"] = build_duration_label(
        start_date,
        end_date,
        all_day,
        start_time=start_time,
        end_time=end_time,
    )
    record["period_label"] = build_period_label(record)
    return record


def serialize_calendar_entry(record):
    return {
        "id": record["id"],
        "source": record["source"],
        "title": record["title"],
        "category_id": record["category_id"],
        "category_label": record["category_label"],
        "detail_label": record["detail_label"],
        "start_date": record["start_date"].isoformat(),
        "end_date": record["end_date"].isoformat(),
        "start_time": record["start_time"],
        "end_time": record["end_time"],
        "all_day": record["all_day"],
        "location": record["location"],
        "description": record["description"],
        "url": record["url"],
        "external": record["external"],
        "open_in_popup": record["open_in_popup"],
        "popup_title": record["popup_title"],
        "popup_features": record.get("popup_features", ""),
        "color": record["color"],
        "badge_label": record["badge_label"],
    }


def get_calendar_record_sort_key(record):
    return (
        record["start_date"],
        0 if record["all_day"] else 1,
        record["start_time"] or "",
        record["title"].lower(),
        record["id"],
    )


def overlaps_calendar_day(record, target_day):
    return record["start_date"] <= target_day <= record["end_date"]


def overlaps_calendar_range(record, range_start, range_end):
    return record["start_date"] <= range_end and record["end_date"] >= range_start


def build_local_calendar_occurrence_record(evento, occurrence):
    detail_parts = []
    if evento.tipologia:
        detail_parts.append(evento.tipologia)
    if evento.is_recurring:
        detail_parts.append(evento.recurrence_summary)

    occurrence_id = f"locale-{evento.pk}"
    if occurrence["index"] > 0:
        occurrence_id = f"{occurrence_id}-{occurrence['index']}"

    return build_calendar_entry_record(
        occurrence_id,
        "locale",
        evento.titolo,
        evento.categoria_evento,
        occurrence["start_date"],
        occurrence["end_date"],
        detail_label=" - ".join(detail_parts),
        start_time=format_time_value(evento.ora_inizio),
        end_time=format_time_value(evento.ora_fine),
        all_day=evento.intera_giornata,
        location=evento.luogo,
        description=evento.descrizione,
        url=reverse("modifica_evento_calendario", kwargs={"pk": evento.pk}),
        external=False,
        open_in_popup=True,
        popup_title="Modifica evento calendario",
        popup_features="width=920,height=760,resizable=yes,scrollbars=yes",
        visible=evento.visibile,
        active=evento.attivo,
        action_label="Apri",
        delete_url=reverse("elimina_evento_calendario", kwargs={"pk": evento.pk}),
        recurrence_summary=evento.recurrence_summary,
        is_recurring=evento.is_recurring,
        active_object=evento,
    )


def build_local_calendar_list_record(evento):
    detail_parts = []
    if evento.tipologia:
        detail_parts.append(evento.tipologia)
    if evento.is_recurring:
        detail_parts.append(evento.recurrence_summary)

    return build_calendar_entry_record(
        f"locale-list-{evento.pk}",
        "locale",
        evento.titolo,
        evento.categoria_evento,
        evento.data_inizio,
        evento.data_fine,
        detail_label=" - ".join(detail_parts),
        start_time=format_time_value(evento.ora_inizio),
        end_time=format_time_value(evento.ora_fine),
        all_day=evento.intera_giornata,
        location=evento.luogo,
        description=evento.descrizione,
        url=reverse("modifica_evento_calendario", kwargs={"pk": evento.pk}),
        external=False,
        open_in_popup=True,
        popup_title="Modifica evento calendario",
        popup_features="width=920,height=760,resizable=yes,scrollbars=yes",
        visible=evento.visibile,
        active=evento.attivo,
        action_label="Apri",
        delete_url=reverse("elimina_evento_calendario", kwargs={"pk": evento.pk}),
        recurrence_summary=evento.recurrence_summary,
        is_recurring=evento.is_recurring,
        active_object=evento,
    )


def get_document_owner_metadata(documento):
    if documento.studente_id:
        return str(documento.studente), reverse("modifica_studente", kwargs={"pk": documento.studente_id})
    if documento.familiare_id:
        return str(documento.familiare), reverse("modifica_familiare", kwargs={"pk": documento.familiare_id})
    return "Documento", ""


def can_include_interested_family_records(user):
    if user is None:
        return True
    return user_has_module_permission(user, "famiglie_interessate", LivelloPermesso.VISUALIZZAZIONE)


def build_interested_family_activity_records(system_categories=None, user=None):
    if not can_include_interested_family_records(user):
        return []

    system_categories = system_categories or ensure_system_calendar_categories()
    categoria = system_categories.get(SYSTEM_CATEGORY_INTERESTED_FAMILIES)
    if not categoria:
        return []

    records = []
    attivita_qs = (
        AttivitaFamigliaInteressata.objects.filter(
            calendarizza=True,
            data_programmata__isnull=False,
        )
        .exclude(stato=StatoAttivitaFamigliaInteressata.ANNULLATA)
        .select_related("famiglia", "assegnata_a")
        .order_by("data_programmata", "id")
    )
    for attivita in attivita_qs:
        start_dt = attivita.calendar_start
        end_dt = attivita.calendar_end
        if not start_dt or not end_dt:
            continue

        detail_parts = [attivita.get_tipo_display(), attivita.get_stato_display()]
        if attivita.assegnata_a_id:
            assignee = attivita.assegnata_a.get_full_name().strip() or attivita.assegnata_a.email
            if assignee:
                detail_parts.append(assignee)

        records.append(
            build_calendar_entry_record(
                f"famiglia-interessata-attivita-{attivita.pk}",
                "famiglia_interessata",
                attivita.calendar_title,
                categoria,
                start_dt.date(),
                end_dt.date(),
                detail_label=" - ".join([part for part in detail_parts if part]),
                start_time=format_time_value(start_dt.time()),
                end_time=format_time_value(end_dt.time()),
                all_day=False,
                location=attivita.luogo,
                description=attivita.descrizione or attivita.esito or attivita.famiglia.nome_display,
                url=reverse("modifica_attivita_famiglia_interessata", kwargs={"pk": attivita.pk}),
                external=False,
                open_in_popup=True,
                popup_title="Attivita famiglia interessata",
                popup_features="width=1040,height=780,resizable=yes,scrollbars=yes",
                action_label="Apri attivita",
            )
        )

    return records


def build_calendar_deadline_records(system_categories=None):
    system_categories = system_categories or ensure_system_calendar_categories()
    records = []

    categoria_rate = system_categories.get(SYSTEM_CATEGORY_RATE_DUE)
    categoria_documenti = system_categories.get(SYSTEM_CATEGORY_DOCUMENTS)
    categoria_fornitori = system_categories.get(SYSTEM_CATEGORY_SUPPLIER_DUE)

    if categoria_rate and module_is_enabled("economia"):
        rate = (
            RataIscrizione.objects.filter(data_scadenza__isnull=False)
            .select_related(
                "iscrizione",
                "iscrizione__studente",
                "iscrizione__anno_scolastico",
            )
            .order_by("data_scadenza", "anno_riferimento", "mese_riferimento", "numero_rata", "pk")
        )
        for rata in rate:
            stato_pagamento = "Pagata" if rata.pagata else "Da incassare"
            detail_label = f"{rata.display_label} - {stato_pagamento}"
            description = f"{rata.iscrizione.studente} - {rata.iscrizione.anno_scolastico}"
            if rata.importo_finale:
                description = f"{description} - EUR {rata.importo_finale}"

            records.append(
                build_calendar_entry_record(
                    f"rata-{rata.pk}",
                    "rata",
                    f"Scadenza retta - {rata.iscrizione.studente}",
                    categoria_rate,
                    rata.data_scadenza,
                    rata.data_scadenza,
                    detail_label=detail_label,
                    description=description,
                    url=reverse("modifica_rata_iscrizione", kwargs={"pk": rata.pk}),
                    external=False,
                    open_in_popup=True,
                    popup_title="Scheda rata",
                    popup_features="width=1080,height=760,resizable=yes,scrollbars=yes",
                    action_label="Apri scheda",
                )
            )

    if categoria_documenti and module_is_enabled("anagrafica"):
        today = timezone.localdate()
        current_year_start = date(today.year, 1, 1)
        current_year_end = date(today.year, 12, 31)
        documenti = (
            Documento.objects.filter(scadenza__range=(current_year_start, current_year_end))
            .select_related("tipo_documento", "familiare", "studente")
            .order_by("scadenza", "pk")
        )
        for documento in documenti:
            owner_label, owner_url = get_document_owner_metadata(documento)
            description_parts = [owner_label]
            if documento.descrizione:
                description_parts.append(documento.descrizione)
            if documento.filename:
                description_parts.append(documento.filename)

            records.append(
                build_calendar_entry_record(
                    f"documento-{documento.pk}",
                    "documento",
                    f"{documento.tipo_documento} - {owner_label}",
                    categoria_documenti,
                    documento.scadenza,
                    documento.scadenza,
                    detail_label="Documento in scadenza",
                    description=" - ".join([part for part in description_parts if part]),
                    url=owner_url,
                    external=False,
                    action_label="Vai alla scheda",
                )
            )

    if categoria_fornitori and module_is_enabled("gestione_finanziaria"):
        scadenze = (
            ScadenzaPagamentoFornitore.objects.exclude(
                stato__in=[StatoScadenzaFornitore.PAGATA, StatoScadenzaFornitore.ANNULLATA]
            )
            .select_related("documento", "documento__fornitore", "documento__categoria_spesa")
            .order_by("data_scadenza", "pk")
        )
        for scadenza in scadenze:
            documento = scadenza.documento
            description_parts = [
                documento.fornitore.denominazione,
                documento.get_tipo_documento_display(),
                documento.numero_documento,
            ]
            if documento.categoria_spesa:
                description_parts.append(str(documento.categoria_spesa))
            records.append(
                build_calendar_entry_record(
                    f"fornitore-scadenza-{scadenza.pk}",
                    "fornitore_scadenza",
                    f"Scadenza fornitore - {documento.fornitore.denominazione}",
                    categoria_fornitori,
                    scadenza.data_scadenza,
                    scadenza.data_scadenza,
                    detail_label=f"{scadenza.get_stato_display()} - EUR {scadenza.importo_residuo}",
                    description=" - ".join([part for part in description_parts if part]),
                    url=reverse("modifica_documento_fornitore", kwargs={"pk": documento.pk}),
                    external=False,
                    open_in_popup=True,
                    popup_title="Scheda fattura fornitore",
                    popup_features="width=1180,height=820,autoFit=no,resizable=yes,scrollbars=yes",
                    action_label="Apri scheda",
                )
            )

    return records


def build_calendar_agenda_bundle(user=None):
    system_categories = ensure_system_calendar_categories()
    categorie = list(CategoriaCalendario.objects.order_by("ordine", "nome"))
    eventi_locali = list(
        EventoCalendario.objects.filter(attivo=True, visibile=True)
        .select_related("categoria_evento")
        .order_by("data_inizio", "ora_inizio", "titolo")
    )

    records = []
    for evento in eventi_locali:
        for occurrence in evento.iter_occurrence_ranges():
            records.append(build_local_calendar_occurrence_record(evento, occurrence))

    records.extend(build_calendar_deadline_records(system_categories))
    records.extend(build_interested_family_activity_records(system_categories, user=user))
    records.sort(key=get_calendar_record_sort_key)

    counts_by_category = {}
    for record in records:
        counts_by_category[record["category_id"]] = counts_by_category.get(record["category_id"], 0) + 1

    for categoria in categorie:
        categoria.count_eventi = counts_by_category.get(categoria.pk, 0)

    return {
        "categories": categorie,
        "records": records,
        "counts_by_category": counts_by_category,
    }


def record_matches_query(record, query):
    normalized_query = (query or "").strip().lower()
    if not normalized_query:
        return True

    haystack = " ".join(
        [
            record["title"],
            record.get("detail_label", ""),
            record.get("description", ""),
            record.get("location", ""),
            record.get("category_label", ""),
        ]
    ).lower()
    return normalized_query in haystack


def build_calendar_list_bundle(categoria_filter="", query="", user=None):
    system_categories = ensure_system_calendar_categories()
    categorie = list(CategoriaCalendario.objects.order_by("ordine", "nome"))
    eventi_locali = list(
        EventoCalendario.objects.select_related("categoria_evento").all().order_by("data_inizio", "ora_inizio", "titolo")
    )

    all_records = [build_local_calendar_list_record(evento) for evento in eventi_locali]
    all_records.extend(build_calendar_deadline_records(system_categories))
    all_records.extend(build_interested_family_activity_records(system_categories, user=user))
    all_records.sort(key=get_calendar_record_sort_key)

    filtered_records = all_records
    if categoria_filter.isdigit():
        categoria_id = int(categoria_filter)
        filtered_records = [record for record in filtered_records if record["category_id"] == categoria_id]

    if query:
        filtered_records = [record for record in filtered_records if record_matches_query(record, query)]

    return {
        "categories": categorie,
        "records": filtered_records,
        "count_eventi_totali": len(all_records),
        "count_intera_giornata": sum(1 for record in all_records if record["all_day"]),
        "count_con_orario": sum(1 for record in all_records if not record["all_day"]),
    }


def build_dashboard_calendar_data(today=None, user=None, week_page_size=3):
    today = today or timezone.localdate()
    agenda_bundle = build_calendar_agenda_bundle(user=user)
    visible_dashboard_category_ids = {
        categoria.pk
        for categoria in agenda_bundle["categories"]
        if getattr(categoria, "visibile_dashboard", True)
    }
    records = [
        record
        for record in agenda_bundle["records"]
        if record.get("category_id") in visible_dashboard_category_ids
    ]

    week_start = today - timedelta(days=today.weekday())
    week_end = week_start + timedelta(days=6)

    today_records = [record for record in records if overlaps_calendar_day(record, today)]
    week_records = [record for record in records if overlaps_calendar_range(record, week_start, week_end)]
    count_week_records = len(week_records)
    week_total_pages = max(1, (count_week_records + week_page_size - 1) // week_page_size)

    return {
        "today": today,
        "today_label": format_weekday_date_label(today),
        "week_start": week_start,
        "week_end": week_end,
        "week_label": f"Dal {format_weekday_date_label(week_start)} al {format_weekday_date_label(week_end)}",
        "today_records": today_records,
        "week_records": week_records,
        "week_page_size": week_page_size,
        "week_total_pages": week_total_pages,
        "count_today_records": len(today_records),
        "count_week_records": count_week_records,
    }
