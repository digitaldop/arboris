import mimetypes
import unicodedata

from django.contrib import messages
from django.conf import settings
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from django.utils import timezone

from .utils import citta_choice_label
from .storage_utils import DOCUMENT_STORAGE_ERROR_TYPES, build_document_storage_error_message
from .forms import (
    IndirizzoForm,
    FamigliaForm,
    FamiliareFormSet,
    StudenteFormSet,
    DocumentoFamigliaFormSet,
    DocumentoFamiliareFormSet,
    StudenteStandaloneForm,
    DocumentoStudenteFormSet,
    FamiliareForm,
    IscrizioneStudenteFormSet,
)
from .models import (
    Citta,
    Nazione,
    Indirizzo,
    Famiglia,
    StatoRelazioneFamiglia,
    RelazioneFamiliare,
    TipoDocumento,
    Studente,
    Documento,
    Familiare,
)
from economia.models import Iscrizione, PrestazioneScambioRetta, RataIscrizione, TariffaCondizioneIscrizione
from economia.scambio_retta_helpers import build_familiare_scambio_retta_inline_context
from calendario.data import build_dashboard_calendar_data
from sistema.inline_context import famiglia_inline_head, studente_inline_head
from sistema.models import (
    AzioneOperazioneCronologia,
    LivelloPermesso,
    Scuola,
    SistemaImpostazioniGenerali,
    SistemaOperazioneCronologia,
)
from sistema.permissions import user_has_module_permission
from sistema.terminology import get_student_terminology
from scuola.models import AnnoScolastico, Classe
from scuola.utils import resolve_default_anno_scolastico
from gestione_finanziaria.services import build_home_financial_dashboard_data
from django.forms import modelform_factory

from django.db import transaction
from django.db.models import Case, Count, Exists, IntegerField, OuterRef, Prefetch, Q, Sum, Value, When
from django.utils.http import url_has_allowed_host_and_scheme

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

ANAGRAFICA_DOCUMENT_QUERY_TARGETS = {
    "familiari": "Familiari",
    "studenti": "Studenti",
    "famiglie": "Famiglie",
}

ANAGRAFICA_DOCUMENT_QUERY_PRESETS = [
    {
        "key": "familiari_senza_documento_identita",
        "title": "Familiari senza documento di identita",
        "target": "familiari",
        "aliases": ["documento identita", "documento d identita", "carta identita", "identita"],
    },
    {
        "key": "studenti_senza_contratto",
        "title": "Studenti senza contratto",
        "target": "studenti",
        "aliases": ["contratto", "scheda contratto"],
    },
    {
        "key": "studenti_senza_carta_identita",
        "title": "Studenti senza carta di identita",
        "target": "studenti",
        "aliases": ["carta identita", "documento identita", "documento d identita", "identita"],
    },
]


def normalize_query_text(value):
    normalized = unicodedata.normalize("NFKD", value or "")
    without_accents = "".join(char for char in normalized if not unicodedata.combining(char))
    return " ".join(without_accents.lower().replace("'", " ").split())


def find_tipo_documento_by_aliases(tipi_documento, aliases):
    normalized_aliases = [normalize_query_text(alias) for alias in aliases]
    for tipo_documento in tipi_documento:
        normalized_name = normalize_query_text(tipo_documento.tipo_documento)
        if any(alias and alias in normalized_name for alias in normalized_aliases):
            return tipo_documento
    return None


def resolve_current_school_year():
    anno_corrente = resolve_default_anno_scolastico()
    if anno_corrente:
        return anno_corrente, anno_corrente.nome_anno_scolastico

    oggi = timezone.localdate()
    anno_inizio = oggi.year if oggi.month >= 9 else oggi.year - 1
    anno_fine = anno_inizio + 1
    return None, f"{anno_inizio}/{anno_fine}"


def apri_documento(request, pk):
    documento = get_object_or_404(
        Documento.objects.select_related("tipo_documento", "famiglia", "familiare", "studente"),
        pk=pk,
    )

    if not documento.file:
        raise Http404("Il documento non ha alcun file associato.")

    try:
        file_handle = documento.file.open("rb")
    except FileNotFoundError as exc:
        raise Http404("Il file del documento non e disponibile sul server.") from exc
    except DOCUMENT_STORAGE_ERROR_TYPES as exc:
        raise Http404(build_document_storage_error_message(exc)) from exc

    filename = documento.filename or f"documento-{documento.pk}"
    content_type, _encoding = mimetypes.guess_type(filename)
    response = FileResponse(file_handle, content_type=content_type or "application/octet-stream")
    response["Content-Disposition"] = f'inline; filename="{filename}"'
    return response


def elimina_documento(request, pk):
    documento = get_object_or_404(
        Documento.objects.select_related("tipo_documento", "famiglia", "familiare", "studente"),
        pk=pk,
    )
    popup = is_popup_request(request)
    return_url = resolve_document_return_url(request, documento)

    if request.method == "POST":
        documento.delete()

        if popup:
            return popup_response(request, "Documento eliminato correttamente.")

        messages.success(request, "Documento eliminato correttamente.")
        return redirect(return_url)

    return render(
        request,
        "anagrafica/documenti/documento_confirm_delete.html",
        {
            "documento": documento,
            "documento_label": build_document_display_label(documento),
            "documento_owner_label": build_document_owner_label(documento),
            "popup": popup,
            "return_url": return_url,
        },
    )


def build_document_owner_redirect_url(documento):
    if documento.famiglia_id:
        return build_famiglia_redirect_url(documento.famiglia_id, "documenti")
    if documento.familiare_id:
        return reverse("modifica_familiare", kwargs={"pk": documento.familiare_id})
    if documento.studente_id:
        return reverse("modifica_studente", kwargs={"pk": documento.studente_id})
    return reverse("lista_famiglie")


def resolve_document_return_url(request, documento):
    candidate = (request.GET.get("return_to") or request.POST.get("return_to") or "").strip()
    if candidate and url_has_allowed_host_and_scheme(candidate, allowed_hosts={request.get_host()}):
        return candidate
    return build_document_owner_redirect_url(documento)


def build_document_owner_label(documento):
    if documento.famiglia_id:
        return f"Famiglia {documento.famiglia}"
    if documento.familiare_id:
        return f"Familiare {documento.familiare}"
    if documento.studente_id:
        return f"Studente {documento.studente}"
    return ""


def build_document_display_label(documento):
    return documento.descrizione or documento.filename or str(documento.tipo_documento)


def resolve_next_school_year(anno_corrente):
    if not anno_corrente:
        return None

    return (
        AnnoScolastico.objects.filter(data_inizio__gt=anno_corrente.data_inizio)
        .order_by("data_inizio", "id")
        .first()
    )


def resolve_inline_target(request, allowed_targets):
    edit_scope = request.POST.get("_edit_scope") or "full"
    inline_target = (request.POST.get("_inline_target") or "").strip()

    if edit_scope != "inline" or inline_target not in allowed_targets:
        return edit_scope, None

    return edit_scope, inline_target


def resolve_active_inline_tab(request, allowed_targets, default_target):
    if request.method == "POST":
        candidate = (request.POST.get("_inline_target") or "").strip()
    else:
        candidate = (request.GET.get("tab") or "").strip()

    if candidate in allowed_targets:
        return candidate

    return default_target


def build_famiglia_redirect_url(pk, active_inline_tab=None):
    url = reverse("modifica_famiglia", kwargs={"pk": pk})
    if active_inline_tab and active_inline_tab != "familiari":
        return f"{url}?tab={active_inline_tab}"
    return url


def build_familiare_redirect_url(pk, active_inline_tab=None, default_tab="studenti"):
    url = reverse("modifica_familiare", kwargs={"pk": pk})
    if active_inline_tab and active_inline_tab != default_tab:
        return f"{url}?tab={active_inline_tab}"
    return url


def pick_audit_entry(entries, action, order_by):
    action_entries = entries.filter(azione=action)
    user_entry = action_entries.filter(utente__isnull=False).order_by(*order_by).first()
    if user_entry:
        return user_entry

    labeled_entry = (
        action_entries
        .exclude(utente_label="")
        .exclude(utente_label__iexact="Sistema")
        .order_by(*order_by)
        .first()
    )
    return labeled_entry or action_entries.order_by(*order_by).first()


def famiglia_audit_labels(famiglia):
    if not famiglia or not famiglia.pk:
        return "-", "-"

    entries = SistemaOperazioneCronologia.objects.select_related(
        "utente",
        "utente__profilo_permessi",
        "utente__profilo_permessi__ruolo_permessi",
    ).filter(
        app_label="anagrafica",
        model_name="famiglia",
        oggetto_id=str(famiglia.pk),
    )
    created_entry = pick_audit_entry(
        entries,
        AzioneOperazioneCronologia.CREAZIONE,
        ["data_operazione", "id"],
    )
    updated_entry = pick_audit_entry(
        entries,
        AzioneOperazioneCronologia.MODIFICA,
        ["-data_operazione", "-id"],
    ) or created_entry

    return audit_user_label_with_role(created_entry), audit_user_label_with_role(updated_entry)


def audit_user_label_with_role(entry):
    if not entry:
        return "-"

    label = entry.utente_display
    ruolo_label = ""
    user = entry.utente
    if user:
        profilo = getattr(user, "profilo_permessi", None)
        if profilo:
            ruolo_label = getattr(profilo, "ruolo_display", "") or ""
        if not ruolo_label and user.is_superuser:
            ruolo_label = "Superuser"

    return f"{label} ({ruolo_label})" if ruolo_label else label


def last_update_audit_label(instance):
    entry = last_update_audit_entry(instance)
    return audit_user_label_with_role(entry)


def last_update_audit_entry(instance):
    if not instance or not instance.pk:
        return None

    entries = SistemaOperazioneCronologia.objects.select_related(
        "utente",
        "utente__profilo_permessi",
        "utente__profilo_permessi__ruolo_permessi",
    ).filter(
        app_label=instance._meta.app_label,
        model_name=instance._meta.model_name,
        oggetto_id=str(instance.pk),
    )
    entry = (
        entries
        .filter(azione=AzioneOperazioneCronologia.MODIFICA)
        .order_by("-data_operazione", "-id")
        .first()
    ) or (
        entries
        .filter(azione=AzioneOperazioneCronologia.CREAZIONE)
        .order_by("-data_operazione", "-id")
        .first()
    )

    return entry


def last_update_audit_info(instance):
    entry = last_update_audit_entry(instance)
    return {
        "data": entry.data_operazione if entry else None,
        "utente_label": audit_user_label_with_role(entry),
    }


def famiglia_familiari_inline_queryset(famiglia=None):
    if not famiglia:
        return Familiare.objects.none()

    return (
        Familiare.objects.filter(famiglia=famiglia)
        .select_related(
            "relazione_familiare",
            "indirizzo__citta__provincia",
            "indirizzo__provincia",
            "luogo_nascita__provincia",
            "nazione_nascita",
            "nazionalita",
            "famiglia__indirizzo_principale__citta__provincia",
            "famiglia__indirizzo_principale__provincia",
        )
        .order_by("cognome", "nome")
    )


def famiglia_studenti_inline_queryset(famiglia=None):
    if not famiglia:
        return Studente.objects.none()

    return (
        annotate_studenti_current_iscrizione_status(Studente.objects.filter(famiglia=famiglia))
        .annotate(
            data_nascita_vuota=Case(
                When(data_nascita__isnull=True, then=Value(1)),
                default=Value(0),
                output_field=IntegerField(),
            )
        )
        .select_related(
            "indirizzo__citta__provincia",
            "indirizzo__provincia",
            "luogo_nascita__provincia",
            "nazione_nascita",
            "nazionalita",
            "famiglia__indirizzo_principale__citta__provincia",
            "famiglia__indirizzo_principale__provincia",
        )
        .order_by("data_nascita_vuota", "data_nascita", "cognome", "nome", "id")
    )


def annotate_studenti_current_iscrizione_status(queryset, today=None):
    today = today or timezone.localdate()
    iscrizione_corrente = Iscrizione.objects.filter(
        studente=OuterRef("pk"),
        attiva=True,
        anno_scolastico__data_inizio__lte=today,
        anno_scolastico__data_fine__gte=today,
    )
    return queryset.annotate(
        ha_iscrizione_attiva_corrente=Exists(iscrizione_corrente),
    )


def famiglia_documenti_inline_queryset(famiglia=None):
    if not famiglia:
        return Documento.objects.none()

    return (
        Documento.objects.filter(famiglia=famiglia)
        .select_related("tipo_documento")
        .order_by("-data_caricamento", "-id")
    )


def build_familiari_formset(*, data=None, instance=None, prefix="familiari"):
    kwargs = {
        "prefix": prefix,
        "queryset": famiglia_familiari_inline_queryset(instance),
    }
    if data is not None:
        kwargs["data"] = data
    if instance is not None:
        kwargs["instance"] = instance
    return FamiliareFormSet(**kwargs)


def build_studenti_formset(*, data=None, instance=None, prefix="studenti"):
    kwargs = {
        "prefix": prefix,
        "queryset": famiglia_studenti_inline_queryset(instance),
    }
    if data is not None:
        kwargs["data"] = data
    if instance is not None:
        kwargs["instance"] = instance
    return StudenteFormSet(**kwargs)


def build_documenti_famiglia_formset(*, data=None, files=None, instance=None, prefix="documenti"):
    kwargs = {
        "prefix": prefix,
        "queryset": famiglia_documenti_inline_queryset(instance),
    }
    if data is not None:
        kwargs["data"] = data
    if files is not None:
        kwargs["files"] = files
    if instance is not None:
        kwargs["instance"] = instance
    return DocumentoFamigliaFormSet(**kwargs)


def studente_iscrizioni_inline_queryset(studente=None):
    if not studente:
        return Iscrizione.objects.none()

    ordered_rate_queryset = RataIscrizione.objects.order_by(
        "anno_riferimento",
        "mese_riferimento",
        "numero_rata",
        "id",
    )
    tariffa_queryset = TariffaCondizioneIscrizione.objects.filter(attiva=True).order_by(
        "ordine_figlio_da",
        "ordine_figlio_a",
        "id",
    )

    return (
        Iscrizione.objects.filter(studente=studente)
        .select_related(
            "studente__famiglia",
            "anno_scolastico",
            "classe",
            "gruppo_classe",
            "stato_iscrizione",
            "condizione_iscrizione",
            "agevolazione",
        )
        .prefetch_related(
            Prefetch("rate", queryset=ordered_rate_queryset),
            Prefetch("condizione_iscrizione__tariffe", queryset=tariffa_queryset),
        )
        .order_by("-anno_scolastico__data_inizio", "-id")
    )


def studente_documenti_inline_queryset(studente=None):
    if not studente:
        return Documento.objects.none()

    return (
        Documento.objects.filter(studente=studente)
        .select_related("tipo_documento")
        .order_by("-data_caricamento", "-id")
    )


def build_iscrizioni_studente_formset(*, data=None, instance=None, prefix="iscrizioni", queryset=None):
    kwargs = {
        "prefix": prefix,
        "queryset": queryset if queryset is not None else studente_iscrizioni_inline_queryset(instance),
    }
    if data is not None:
        kwargs["data"] = data
    if instance is not None:
        kwargs["instance"] = instance
    return IscrizioneStudenteFormSet(**kwargs)


def build_documenti_studente_formset(*, data=None, files=None, instance=None, prefix="documenti", queryset=None):
    kwargs = {
        "prefix": prefix,
        "queryset": queryset if queryset is not None else studente_documenti_inline_queryset(instance),
    }
    if data is not None:
        kwargs["data"] = data
    if files is not None:
        kwargs["files"] = files
    if instance is not None:
        kwargs["instance"] = instance
    return DocumentoStudenteFormSet(**kwargs)


def build_studente_document_counts(studente, today):
    counts = studente.documenti.aggregate(
        totale=Count("id"),
        in_scadenza=Count(
            "id",
            filter=Q(
                scadenza__isnull=False,
                scadenza__gte=today,
                scadenza__lte=today + timedelta(days=30),
            ),
        ),
        scaduti=Count(
            "id",
            filter=Q(
                scadenza__isnull=False,
                scadenza__lt=today,
            ),
        ),
    )
    return {
        "count_documenti": counts["totale"] or 0,
        "count_documenti_in_scadenza": counts["in_scadenza"] or 0,
        "count_documenti_scaduti": counts["scaduti"] or 0,
    }


def should_prefer_initial_famiglia_tab(request, allowed_targets):
    if request.method == "POST":
        return True

    requested_tab = (request.GET.get("tab") or "").strip()
    return requested_tab in allowed_targets


def build_school_year_months(anno_scolastico):
    if not anno_scolastico or not anno_scolastico.data_inizio or not anno_scolastico.data_fine:
        return []

    current_month = anno_scolastico.data_inizio.replace(day=1)
    end_month = anno_scolastico.data_fine.replace(day=1)
    months = []

    while current_month <= end_month:
        months.append(
            {
                "year": current_month.year,
                "month": current_month.month,
                "label": f"{MONTH_LABELS.get(current_month.month, current_month.month)} {current_month.year}",
            }
        )

        if current_month.month == 12:
            current_month = date(current_month.year + 1, 1, 1)
        else:
            current_month = date(current_month.year, current_month.month + 1, 1)

    return months


def build_iscrizione_dashboard_rate_rows(iscrizione):
    rate_iscrizione = sorted(
        iscrizione.rate.all(),
        key=lambda rata: (
            rata.anno_riferimento,
            rata.mese_riferimento,
            rata.numero_rata,
            rata.id,
        ),
    )

    if rate_iscrizione:
        rate_rows = [
            {
                "year": rata.anno_riferimento,
                "month": rata.mese_riferimento,
                "tipo_rata": rata.tipo_rata or RataIscrizione.TIPO_MENSILE,
                "numero_rata": rata.numero_rata,
                "importo_finale": rata.importo_finale or Decimal("0.00"),
                "importo_incassato": rata.importo_pagato or Decimal("0.00"),
            }
            for rata in rate_iscrizione
        ]
    else:
        rate_rows = [
            {
                "year": item["anno_riferimento"],
                "month": item["mese_riferimento"],
                "tipo_rata": item.get("tipo_rata", RataIscrizione.TIPO_MENSILE),
                "numero_rata": item["numero_rata"],
                "importo_finale": item["importo_finale"] or Decimal("0.00"),
                "importo_incassato": Decimal("0.00"),
            }
            for item in iscrizione.build_rate_plan()
        ]

    tariffa = iscrizione.get_tariffa_applicabile() if not iscrizione.non_pagante else None
    totale_lordo_annuo = tariffa.retta_annuale if tariffa else Decimal("0.00")
    importo_preiscrizione = iscrizione.get_importo_preiscrizione_dovuto()
    piano_lordo_mensile = iscrizione.build_rate_mensili_entries_for_importo(totale_lordo_annuo)
    importi_lordi_per_numero_rata = {
        item["numero_rata"]: item["importo_dovuto"]
        for item in piano_lordo_mensile
    }
    totale_lordo_periodo = sum(importi_lordi_per_numero_rata.values(), Decimal("0.00"))

    dashboard_rows = []
    for index, rate_row in enumerate(rate_rows):
        importo_finale = rate_row["importo_finale"] or Decimal("0.00")
        importo_incassato = rate_row["importo_incassato"] or Decimal("0.00")
        if rate_row["tipo_rata"] == RataIscrizione.TIPO_PREISCRIZIONE:
            importo_totale = importo_preiscrizione
        elif rate_row["tipo_rata"] == RataIscrizione.TIPO_UNICA_SOLUZIONE:
            importo_totale = totale_lordo_periodo
        else:
            importo_totale = importi_lordi_per_numero_rata.get(rate_row["numero_rata"], Decimal("0.00"))
        dashboard_rows.append(
            {
                "year": rate_row["year"],
                "month": rate_row["month"],
                "tipo_rata": rate_row["tipo_rata"],
                "importo_totale": importo_totale,
                "importo_incassato": importo_incassato,
                "importo_rimanente": max(importo_finale - importo_incassato, Decimal("0.00")),
            }
        )

    return dashboard_rows


def build_studente_projected_rate_plan(iscrizione, tariffa, importo_preiscrizione):
    return iscrizione.build_rate_plan()


def build_economia_dashboard_data(anno_corrente):
    default_data = {
        "configured_year": bool(anno_corrente),
        "count_studenti_iscritti": 0,
        "count_studenti_paganti": 0,
        "count_studenti_non_paganti": 0,
        "count_studenti_riduzione_speciale": 0,
        "totale_rette_annuo": Decimal("0.00"),
        "totale_rette_incassato": Decimal("0.00"),
        "totale_rette_rimanenti": Decimal("0.00"),
        "totale_preiscrizioni": Decimal("0.00"),
        "totale_preiscrizioni_incassato": Decimal("0.00"),
        "totale_preiscrizioni_rimanenti": Decimal("0.00"),
        "media_mensile_rette": Decimal("0.00"),
        "totale_riduzioni_speciali": Decimal("0.00"),
        "totale_scambi_retta": Decimal("0.00"),
        "agevolazioni": [],
        "riepilogo_preiscrizioni": {
            "label": "Preiscrizioni",
            "importo_totale": Decimal("0.00"),
            "importo_incassato": Decimal("0.00"),
            "importo_rimanente": Decimal("0.00"),
        },
        "riepilogo_mensile": [],
    }

    if not anno_corrente:
        return default_data

    school_year_months = build_school_year_months(anno_corrente)
    school_year_keys = {(item["year"], item["month"]) for item in school_year_months}

    iscrizioni_anno_corrente = list(
        Iscrizione.objects.filter(
            anno_scolastico=anno_corrente,
            attiva=True,
        )
        .select_related(
            "studente",
            "agevolazione",
            "condizione_iscrizione",
        )
        .prefetch_related("rate")
        .order_by("studente__cognome", "studente__nome", "id")
    )

    monthly_total_map = defaultdict(lambda: Decimal("0.00"))
    monthly_paid_map = defaultdict(lambda: Decimal("0.00"))
    monthly_remaining_map = defaultdict(lambda: Decimal("0.00"))
    agevolazioni_map = {}

    count_studenti_paganti = 0
    count_studenti_non_paganti = 0
    count_studenti_riduzione_speciale = 0
    totale_rette_annuo = Decimal("0.00")
    totale_rette_incassato = Decimal("0.00")
    totale_rette_rimanenti = Decimal("0.00")
    totale_preiscrizioni = Decimal("0.00")
    totale_preiscrizioni_incassato = Decimal("0.00")
    totale_preiscrizioni_rimanenti = Decimal("0.00")
    totale_riduzioni_speciali = Decimal("0.00")
    totale_scambi_retta = (
        PrestazioneScambioRetta.objects.filter(
            anno_scolastico=anno_corrente,
            familiare__abilitato_scambio_retta=True,
        ).aggregate(total=Sum("importo_maturato"))["total"]
        or Decimal("0.00")
    )

    for iscrizione in iscrizioni_anno_corrente:
        if iscrizione.non_pagante:
            count_studenti_non_paganti += 1
        else:
            count_studenti_paganti += 1

        importo_riduzione = iscrizione.get_importo_riduzione_applicata()
        if importo_riduzione > 0:
            count_studenti_riduzione_speciale += 1
            totale_riduzioni_speciali += importo_riduzione

        if iscrizione.agevolazione_id:
            agevolazione_data = agevolazioni_map.setdefault(
                iscrizione.agevolazione_id,
                {
                    "nome_agevolazione": str(iscrizione.agevolazione),
                    "count_studenti": 0,
                    "studenti": [],
                    "totale_importo": Decimal("0.00"),
                },
            )
            agevolazione_data["count_studenti"] += 1
            agevolazione_data["studenti"].append(str(iscrizione.studente))
            agevolazione_data["totale_importo"] += iscrizione.get_importo_agevolazione_applicata()

        rate_rows = build_iscrizione_dashboard_rate_rows(iscrizione)
        for rate_row in rate_rows:
            if rate_row["tipo_rata"] == RataIscrizione.TIPO_PREISCRIZIONE:
                totale_preiscrizioni += rate_row["importo_totale"]
                totale_preiscrizioni_incassato += rate_row["importo_incassato"]
                totale_preiscrizioni_rimanenti += rate_row["importo_rimanente"]
                continue

            totale_rette_annuo += rate_row["importo_totale"]
            totale_rette_incassato += rate_row["importo_incassato"]
            totale_rette_rimanenti += rate_row["importo_rimanente"]

            month_key = (rate_row["year"], rate_row["month"])
            if month_key not in school_year_keys:
                continue

            monthly_total_map[month_key] += rate_row["importo_totale"]
            monthly_paid_map[month_key] += rate_row["importo_incassato"]
            monthly_remaining_map[month_key] += rate_row["importo_rimanente"]

    riepilogo_mensile = [
        {
            "label": item["label"],
            "importo_totale": monthly_total_map[(item["year"], item["month"])],
            "importo_incassato": monthly_paid_map[(item["year"], item["month"])],
            "importo_rimanente": monthly_remaining_map[(item["year"], item["month"])],
        }
        for item in school_year_months
    ]

    total_months = len(riepilogo_mensile)
    media_mensile_rette = (
        (totale_rette_annuo / total_months).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        if total_months
        else Decimal("0.00")
    )

    agevolazioni = sorted(
        [
            {
                "nome_agevolazione": item["nome_agevolazione"],
                "count_studenti": item["count_studenti"],
                "studenti_label": (
                    "1 Studente"
                    if item["count_studenti"] == 1
                    else f"{item['count_studenti']} Studenti"
                ),
                "studenti_names": ", ".join(item["studenti"]),
                "totale_importo": item["totale_importo"],
            }
            for item in agevolazioni_map.values()
            if item["count_studenti"] > 0
        ],
        key=lambda item: item["nome_agevolazione"].lower(),
    )

    return {
        "configured_year": True,
        "count_studenti_iscritti": len(iscrizioni_anno_corrente),
        "count_studenti_paganti": count_studenti_paganti,
        "count_studenti_non_paganti": count_studenti_non_paganti,
        "count_studenti_riduzione_speciale": count_studenti_riduzione_speciale,
        "totale_rette_annuo": totale_rette_annuo,
        "totale_rette_incassato": totale_rette_incassato,
        "totale_rette_rimanenti": totale_rette_rimanenti,
        "totale_preiscrizioni": totale_preiscrizioni,
        "totale_preiscrizioni_incassato": totale_preiscrizioni_incassato,
        "totale_preiscrizioni_rimanenti": totale_preiscrizioni_rimanenti,
        "media_mensile_rette": media_mensile_rette,
        "totale_riduzioni_speciali": totale_riduzioni_speciali,
        "totale_scambi_retta": totale_scambi_retta,
        "agevolazioni": agevolazioni,
        "riepilogo_preiscrizioni": {
            "label": "Preiscrizioni",
            "importo_totale": totale_preiscrizioni,
            "importo_incassato": totale_preiscrizioni_incassato,
            "importo_rimanente": totale_preiscrizioni_rimanenti,
        },
        "riepilogo_mensile": riepilogo_mensile,
    }


def build_studente_rate_overview(studente, iscrizioni=None):
    overview = []

    iscrizioni = list(iscrizioni) if iscrizioni is not None else list(studente_iscrizioni_inline_queryset(studente))
    ordine_figlio_mappa = {}

    if studente.famiglia_id:
        anni_scolastici_ids = {
            iscrizione.anno_scolastico_id
            for iscrizione in iscrizioni
            if iscrizione.anno_scolastico_id
        }
        if anni_scolastici_ids:
            iscrizioni_famiglia = (
                Iscrizione.objects.filter(
                    studente__famiglia_id=studente.famiglia_id,
                    anno_scolastico_id__in=anni_scolastici_ids,
                )
                .select_related("studente")
                .order_by(
                    "anno_scolastico_id",
                    "studente__data_nascita",
                    "studente__cognome",
                    "studente__nome",
                    "studente_id",
                    "id",
                )
            )

            progressivi_per_anno = defaultdict(int)
            for iscrizione_famiglia in iscrizioni_famiglia:
                progressivi_per_anno[iscrizione_famiglia.anno_scolastico_id] += 1
                ordine_figlio_mappa[iscrizione_famiglia.pk] = progressivi_per_anno[iscrizione_famiglia.anno_scolastico_id]

    for iscrizione in iscrizioni:
        if (
            not getattr(iscrizione, "anno_scolastico_id", None)
            or not getattr(iscrizione, "stato_iscrizione_id", None)
            or not getattr(iscrizione, "condizione_iscrizione_id", None)
        ):
            continue

        ordine_figlio = ordine_figlio_mappa.get(iscrizione.pk)
        tariffe_condizione = list(iscrizione.condizione_iscrizione.tariffe.all())
        tariffa = None
        if not iscrizione.non_pagante and ordine_figlio is not None:
            tariffa = next(
                (
                    item for item in tariffe_condizione
                    if item.ordine_figlio_da <= ordine_figlio
                    and (item.ordine_figlio_a is None or item.ordine_figlio_a >= ordine_figlio)
                ),
                None,
            )

        rate = list(iscrizione.rate.all())
        importo_preiscrizione = Decimal("0.00") if iscrizione.non_pagante or not tariffa else (tariffa.preiscrizione or Decimal("0.00"))

        if rate:
            months = [
                {
                    "label": rata.display_period_label,
                    "display_label": rata.display_label,
                    "is_preiscrizione": rata.is_preiscrizione,
                    "is_unica_soluzione": rata.is_unica_soluzione,
                    "numero_rata": rata.numero_rata,
                    "importo_dovuto": rata.importo_dovuto,
                    "importo_finale": rata.importo_finale,
                    "importo_pagato": rata.importo_pagato,
                    "pagata": rata.pagata,
                    "data_scadenza": rata.data_scadenza,
                    "data_pagamento": rata.data_pagamento,
                    "credito_applicato": rata.credito_applicato,
                    "altri_sgravi": rata.altri_sgravi,
                    "metodo_pagamento": rata.metodo_pagamento,
                    "rata_pk": rata.pk,
                    "is_projected": False,
                }
                for rata in rate
            ]
        else:
            piano = build_studente_projected_rate_plan(
                iscrizione,
                tariffa=tariffa,
                importo_preiscrizione=importo_preiscrizione,
            )
            months = [
                {
                    "label": (
                        item["descrizione"]
                        if item.get("tipo_rata") in {RataIscrizione.TIPO_PREISCRIZIONE, RataIscrizione.TIPO_UNICA_SOLUZIONE}
                        else f"{MONTH_LABELS.get(item['mese_riferimento'], item['mese_riferimento'])} {item['anno_riferimento']}"
                    ),
                    "display_label": (
                        item["descrizione"]
                        if item.get("tipo_rata") in {RataIscrizione.TIPO_PREISCRIZIONE, RataIscrizione.TIPO_UNICA_SOLUZIONE}
                        else f"Rata {item['numero_rata']}"
                    ),
                    "is_preiscrizione": item.get("tipo_rata") == RataIscrizione.TIPO_PREISCRIZIONE,
                    "is_unica_soluzione": item.get("tipo_rata") == RataIscrizione.TIPO_UNICA_SOLUZIONE,
                    "numero_rata": item["numero_rata"],
                    "importo_dovuto": item["importo_dovuto"],
                    "importo_finale": item["importo_finale"],
                    "importo_pagato": None,
                    "pagata": False,
                    "data_scadenza": item["data_scadenza"],
                    "data_pagamento": None,
                    "credito_applicato": item["credito_applicato"],
                    "altri_sgravi": item["altri_sgravi"],
                    "metodo_pagamento": None,
                    "rata_pk": None,
                    "is_projected": True,
                }
                for item in piano
            ]

        monthly_months = [
            month
            for month in months
            if not month["is_preiscrizione"] and not month.get("is_unica_soluzione")
        ]
        single_payment_month = next((month for month in months if month.get("is_unica_soluzione")), None)
        is_pagamento_unica_soluzione = iscrizione.is_pagamento_unica_soluzione

        overview.append(
            {
                "iscrizione": iscrizione,
                "anno_label": iscrizione.anno_scolastico.nome_anno_scolastico,
                "classe_label": str(iscrizione.classe) if iscrizione.classe else None,
                "stato_label": str(iscrizione.stato_iscrizione),
                "condizione_label": iscrizione.condizione_iscrizione.nome_condizione_iscrizione,
                "has_tariffa": bool(tariffa),
                "retta_annuale_base": tariffa.retta_annuale if tariffa else None,
                "preiscrizione": importo_preiscrizione,
                "numero_mensilita": 1
                if is_pagamento_unica_soluzione
                else max(iscrizione.condizione_iscrizione.numero_mensilita_default or 0, 1),
                "rata_standard": single_payment_month["importo_dovuto"]
                if single_payment_month
                else (monthly_months[0]["importo_dovuto"] if monthly_months else None),
                "pagamento_unica_soluzione": is_pagamento_unica_soluzione,
                "modalita_pagamento_label": iscrizione.get_modalita_pagamento_retta_display(),
                "sconto_unica_soluzione": iscrizione.get_importo_sconto_unica_soluzione_applicato(),
                "agevolazione_label": str(iscrizione.agevolazione) if iscrizione.agevolazione_id else "",
                "riduzione_retta_speciale": (
                    iscrizione.importo_riduzione_speciale
                    if iscrizione.riduzione_speciale and iscrizione.importo_riduzione_speciale
                    else None
                ),
                "months": months,
                "month_rows": build_balanced_rate_rows(months),
                "has_projected_plan": bool(months) and all(month["is_projected"] for month in months),
            }
        )

    return overview


def build_balanced_rate_rows(months, max_single_row=6):
    months = list(months or [])

    if not months:
        return []

    if len(months) <= max_single_row:
        return [months]

    split_index = (len(months) + 1) // 2
    return [months[:split_index], months[split_index:]]


def build_dashboard_school_year_statistics(anno_scolastico):
    data = {
        "anno_scolastico": anno_scolastico,
        "anno_label": anno_scolastico.nome_anno_scolastico if anno_scolastico else "",
        "count_studenti_iscritti": 0,
        "count_famiglie_iscritte": 0,
        "composizione_classi": [],
    }

    if not anno_scolastico:
        return data

    iscrizioni_anno = Iscrizione.objects.filter(
        anno_scolastico=anno_scolastico,
        attiva=True,
    )

    data["count_studenti_iscritti"] = iscrizioni_anno.values("studente_id").distinct().count()
    data["count_famiglie_iscritte"] = iscrizioni_anno.values("studente__famiglia_id").distinct().count()

    classi_anno = (
        Classe.objects.filter(attiva=True)
        .annotate(
            count_studenti=Count(
                "iscrizioni__studente",
                filter=Q(iscrizioni__anno_scolastico=anno_scolastico, iscrizioni__attiva=True),
                distinct=True,
            )
        )
        .order_by("ordine_classe", "nome_classe", "sezione_classe", "id")
    )

    data["composizione_classi"] = [
        {
            "nome_classe": str(classe),
            "count_studenti": classe.count_studenti,
            "studenti_label": (
                "Nessun Studente"
                if classe.count_studenti == 0
                else f"{classe.count_studenti} Studente" if classe.count_studenti == 1 else f"{classe.count_studenti} Studenti"
            ),
        }
        for classe in classi_anno
    ]

    return data


def home(request):
    anno_corrente, anno_scolastico_corrente = resolve_current_school_year()
    impostazioni_generali = SistemaImpostazioniGenerali.objects.first()
    can_view_gestione_finanziaria = user_has_module_permission(
        request.user,
        "gestione_finanziaria",
        LivelloPermesso.VISUALIZZAZIONE,
    )
    mostra_dashboard_prossimo_anno = bool(
        impostazioni_generali and impostazioni_generali.mostra_dashboard_prossimo_anno_scolastico
    )

    dashboard_corrente = build_dashboard_school_year_statistics(anno_corrente)
    prossimo_anno_scolastico = resolve_next_school_year(anno_corrente) if mostra_dashboard_prossimo_anno else None
    dashboard_prossimo_anno = (
        build_dashboard_school_year_statistics(prossimo_anno_scolastico)
        if prossimo_anno_scolastico
        else build_dashboard_school_year_statistics(None)
    )

    economia_dashboard = build_economia_dashboard_data(anno_corrente)
    economia_dashboard_prossimo_anno = (
        build_economia_dashboard_data(prossimo_anno_scolastico)
        if prossimo_anno_scolastico
        else build_economia_dashboard_data(None)
    )
    calendario_dashboard = build_dashboard_calendar_data()
    gestione_finanziaria_dashboard = (
        build_home_financial_dashboard_data()
        if can_view_gestione_finanziaria
        else None
    )

    context = {
        "anno_scolastico_corrente": anno_scolastico_corrente,
        "count_famiglie_iscritte": dashboard_corrente["count_famiglie_iscritte"],
        "count_studenti_iscritti": dashboard_corrente["count_studenti_iscritti"],
        "composizione_classi": dashboard_corrente["composizione_classi"],
        "economia_dashboard": economia_dashboard,
        "mostra_dashboard_prossimo_anno": mostra_dashboard_prossimo_anno and bool(prossimo_anno_scolastico),
        "dashboard_prossimo_anno": dashboard_prossimo_anno,
        "economia_dashboard_prossimo_anno": economia_dashboard_prossimo_anno,
        "calendario_dashboard": calendario_dashboard,
        "gestione_finanziaria_dashboard": gestione_finanziaria_dashboard,
    }

    return render(request, "home.html", context)

#Funzione per l'helper dei pop up di creazione/modifica rapida
def is_popup_request(request):
    return request.GET.get("popup") == "1" or request.POST.get("popup") == "1"


def popup_select_response(request, field_name, object_id, object_label):
    return render(
        request,
        "popup/popup_close_select.html",
        {
            "action": "select",
            "field_name": field_name,
            "object_id": object_id,
            "object_label": object_label,
            "target_input_name": request.GET.get("target_input_name") or request.POST.get("target_input_name", ""),
        },
    )


def popup_delete_response(request, field_name, object_id):
    return render(
        request,
        "popup/popup_close_select.html",
        {
            "action": "delete",
            "field_name": field_name,
            "object_id": object_id,
            "target_input_name": request.GET.get("target_input_name") or request.POST.get("target_input_name", ""),
        },
    )


def popup_response(request, message="Operazione completata."):
    return render(request, "popup/popup_close.html", {"message": message})
#Fine helper pop up


def get_indirizzo_usage(indirizzo):
    famiglie = list(
        indirizzo.famiglie_principali.order_by("cognome_famiglia").values_list("cognome_famiglia", flat=True)
    )
    studenti = [
        f"{cognome} {nome}".strip()
        for cognome, nome in indirizzo.studenti.order_by("cognome", "nome").values_list("cognome", "nome")
    ]
    familiari = [
        f"{cognome} {nome}".strip()
        for cognome, nome in indirizzo.familiari.order_by("cognome", "nome").values_list("cognome", "nome")
    ]
    scuole_legali = list(
        indirizzo.scuole_sede_legale.order_by("nome_scuola").values_list("nome_scuola", flat=True)
    )
    scuole_operative = list(
        indirizzo.scuole_sede_operativa.order_by("nome_scuola").values_list("nome_scuola", flat=True)
    )
    scuole = list(dict.fromkeys(scuole_legali + scuole_operative))

    return {
        "famiglie": famiglie,
        "studenti": studenti,
        "familiari": familiari,
        "scuole": scuole,
        "totale": len(famiglie) + len(studenti) + len(familiari) + len(scuole),
    }


def get_famiglia_delete_impact(famiglia):
    familiari_qs = famiglia.familiari.order_by("cognome", "nome")
    studenti_qs = famiglia.studenti.order_by("cognome", "nome")

    familiari = list(familiari_qs.values_list("cognome", "nome"))
    studenti = list(studenti_qs.values_list("cognome", "nome"))
    documenti_famiglia = list(famiglia.documenti.select_related("tipo_documento").order_by("-data_caricamento", "-id"))
    documenti_familiari = list(
        Documento.objects.filter(familiare__famiglia=famiglia)
        .select_related("familiare", "tipo_documento")
        .order_by("familiare__cognome", "familiare__nome", "-data_caricamento", "-id")
    )
    documenti_studenti = list(
        Documento.objects.filter(studente__famiglia=famiglia)
        .select_related("studente", "tipo_documento")
        .order_by("studente__cognome", "studente__nome", "-data_caricamento", "-id")
    )

    address_map = {}

    def add_address(address):
        if not address:
            return
        address_map[address.pk] = address

    add_address(famiglia.indirizzo_principale)

    for indirizzo_id in familiari_qs.exclude(indirizzo__isnull=True).values_list("indirizzo_id", flat=True).distinct():
        add_address(Indirizzo.objects.filter(pk=indirizzo_id).first())

    for indirizzo_id in studenti_qs.exclude(indirizzo__isnull=True).values_list("indirizzo_id", flat=True).distinct():
        add_address(Indirizzo.objects.filter(pk=indirizzo_id).first())

    indirizzi_da_eliminare = []
    indirizzi_condivisi = []

    for address in address_map.values():
        scuole_esterne = list(
            Scuola.objects.filter(
                Q(indirizzo_sede_legale=address) | Q(indirizzo_operativo=address)
            )
            .order_by("nome_scuola")
            .values_list("nome_scuola", flat=True)
            .distinct()
        )
        famiglie_esterne = list(
            address.famiglie_principali.exclude(pk=famiglia.pk).order_by("cognome_famiglia").values_list("cognome_famiglia", flat=True)
        )
        studenti_esterni = [
            f"{cognome} {nome}".strip()
            for cognome, nome in address.studenti.exclude(famiglia=famiglia).order_by("cognome", "nome").values_list("cognome", "nome")
        ]
        familiari_esterni = [
            f"{cognome} {nome}".strip()
            for cognome, nome in address.familiari.exclude(famiglia=famiglia).order_by("cognome", "nome").values_list("cognome", "nome")
        ]

        item = {
            "id": address.pk,
            "label": address.label_select(),
        }

        if famiglie_esterne or studenti_esterni or familiari_esterni or scuole_esterne:
            item["usi_esterni"] = {
                "scuole": scuole_esterne,
                "famiglie": famiglie_esterne,
                "studenti": studenti_esterni,
                "familiari": familiari_esterni,
            }
            indirizzi_condivisi.append(item)
        else:
            indirizzi_da_eliminare.append(item)

    return {
        "familiari": [f"{cognome} {nome}".strip() for cognome, nome in familiari],
        "studenti": [f"{cognome} {nome}".strip() for cognome, nome in studenti],
        "documenti_famiglia": documenti_famiglia,
        "documenti_familiari": documenti_familiari,
        "documenti_studenti": documenti_studenti,
        "totale_documenti": len(documenti_famiglia) + len(documenti_familiari) + len(documenti_studenti),
        "indirizzi_da_eliminare": indirizzi_da_eliminare,
        "indirizzi_condivisi": indirizzi_condivisi,
    }


def get_record_documents_impact(record):
    documenti = list(record.documenti.select_related("tipo_documento").order_by("-data_caricamento", "-id"))
    return {
        "documenti": documenti,
        "totale_documenti": len(documenti),
    }

#INIZIO VIEWS DEGLI INDIRIZZI
def lista_indirizzi(request):
    indirizzi = (
        Indirizzo.objects
        .select_related("citta", "provincia", "regione", "cap_scelto")
        .order_by("via", "numero_civico")
    )

    evidenzia_id = request.GET.get("highlight")

    return render(
        request,
        "anagrafica/indirizzi/indirizzo_list.html",
        {
            "indirizzi": indirizzi,
            "evidenzia_id": evidenzia_id,
        },
    )


def crea_indirizzo(request):
    popup = is_popup_request(request)

    if request.method == "POST":
        form = IndirizzoForm(request.POST)
        if form.is_valid():
            indirizzo = form.save()

            if popup:
                return popup_select_response(
                    request,
                    field_name="indirizzo_principale",
                    object_id=indirizzo.pk,
                    object_label=indirizzo.label_select(),
                )

            messages.success(request, "Indirizzo creato correttamente.")
            return redirect(f"{reverse('lista_indirizzi')}?highlight={indirizzo.pk}")
    else:
        form = IndirizzoForm()

    template_name = "anagrafica/indirizzi/indirizzo_popup_form.html" if popup else "anagrafica/indirizzi/indirizzo_form.html"

    return render(
        request,
        template_name,
        {
            "form": form,
            "popup": popup,
        },
    )


def modifica_indirizzo(request, pk):
    indirizzo = get_object_or_404(Indirizzo, pk=pk)
    popup = is_popup_request(request)

    if request.method == "POST":
        form = IndirizzoForm(request.POST, instance=indirizzo)
        if form.is_valid():
            indirizzo = form.save()

            if popup:
                return popup_select_response(
                    request,
                    field_name="indirizzo_principale",
                    object_id=indirizzo.pk,
                    object_label=indirizzo.label_select(),
                )

            messages.success(request, "Modifiche salvate correttamente.")
            return redirect(f"{reverse('lista_indirizzi')}?highlight={indirizzo.pk}")
    else:
        form = IndirizzoForm(instance=indirizzo)

    template_name = "anagrafica/indirizzi/indirizzo_popup_form.html" if popup else "anagrafica/indirizzi/indirizzo_form.html"

    return render(
        request,
        template_name,
        {
            "form": form,
            "indirizzo": indirizzo,
            "popup": popup,
        },
    )


def elimina_indirizzo(request, pk):
    indirizzo = get_object_or_404(Indirizzo, pk=pk)
    popup = is_popup_request(request)

    object_id = indirizzo.pk
    usage = get_indirizzo_usage(indirizzo)

    if request.method == "POST":
        indirizzo.delete()

        if popup:
            return popup_delete_response(
                request,
                field_name="indirizzo_principale",
                object_id=object_id,
            )

        messages.success(request, "Indirizzo eliminato correttamente.")
        return redirect("lista_indirizzi")

    template_name = "anagrafica/indirizzi/indirizzo_popup_delete.html" if popup else "anagrafica/indirizzi/indirizzo_conferma_elimina.html"

    return render(
        request,
        template_name,
        {
            "indirizzo": indirizzo,
            "popup": popup,
            "usage": usage,
        },
    )


def ajax_cerca_citta(request):
    citta_id = (request.GET.get("id") or "").strip()
    q = request.GET.get("q", "").strip()
    include_nazioni = (request.GET.get("include_nazioni") or "").strip() == "1"
    italia_nazionalita_id = None
    if include_nazioni:
        italia_nazionalita_id = (
            Nazione.objects
            .filter(attiva=True, nome__iexact="Italia")
            .exclude(nome_nazionalita="")
            .order_by("ordine", "id")
            .values_list("pk", flat=True)
            .first()
        )

    qs = (
        Citta.objects
        .filter(attiva=True)
        .select_related("provincia", "provincia__regione")
    )

    if citta_id:
        try:
            qs = qs.filter(pk=int(citta_id))
        except (TypeError, ValueError):
            return JsonResponse({"results": []})
    elif q:
        qs = (
            qs.filter(nome__icontains=q)
            .annotate(
                search_rank=Case(
                    When(nome__iexact=q, then=Value(0)),
                    When(nome__istartswith=q, then=Value(1)),
                    default=Value(2),
                    output_field=IntegerField(),
                )
            )
            .order_by("search_rank", "nome", "provincia__sigla")
        )
    else:
        qs = qs.order_by("nome", "provincia__sigla")

    qs = qs[:20]

    results = []
    for c in qs:
        caps = list(
            c.cap_list.filter(attivo=True)
            .order_by("codice")
            .values("id", "codice")
        )

        prov = getattr(c, "provincia", None)
        results.append({
            "type": "citta",
            "id": c.id,
            "nome": c.nome,
            "label": citta_choice_label(c),
            "codice_catastale": c.codice_catastale,
            "provincia_nome": getattr(prov, "nome", "") if prov is not None else "",
            "provincia_sigla": getattr(prov, "sigla", "") if prov is not None else "",
            "regione_nome": prov.regione.nome if prov and prov.regione else "",
            "nazionalita_id": italia_nazionalita_id or "",
            "nazionalita_label": "Italiana" if italia_nazionalita_id else "",
            "caps": caps,
        })

    if include_nazioni and not citta_id and q:
        nazioni_qs = (
            Nazione.objects
            .filter(attiva=True, nome__icontains=q)
            .annotate(
                search_rank=Case(
                    When(nome__iexact=q, then=Value(0)),
                    When(nome__istartswith=q, then=Value(1)),
                    default=Value(2),
                    output_field=IntegerField(),
                )
            )
            .order_by("search_rank", "nome")[:10]
        )
        for nazione in nazioni_qs:
            nazionalita = None
            if nazione.nome_nazionalita:
                nazionalita = (
                    Nazione.objects
                    .filter(attiva=True, nome_nazionalita__iexact=nazione.nome_nazionalita)
                    .exclude(nome_nazionalita="")
                    .order_by("nome_nazionalita", "ordine", "id")
                    .first()
                )
            has_same_name = Nazione.objects.filter(
                attiva=True,
                nome__iexact=nazione.nome,
            ).exclude(pk=nazione.pk).exists()
            label = str(nazione)
            if has_same_name and nazione.codice_belfiore:
                label = f"{nazione} ({nazione.codice_belfiore})"
            results.append({
                "type": "nazione",
                "id": nazione.id,
                "nome": str(nazione),
                "label": label,
                "codice_catastale": nazione.codice_belfiore,
                "nazionalita_id": nazionalita.pk if nazionalita else "",
                "nazionalita_label": nazionalita.label_nazionalita if nazionalita else "",
                "provincia_nome": "",
                "provincia_sigla": "",
                "regione_nome": "",
                "caps": [],
            })

    return JsonResponse({"results": results})

#FINE VIEWS DEGLI INDIRIZZI


def anagrafica_document_missing_queryset(target, tipo_documento):
    documento_filter = Documento.objects.filter(tipo_documento=tipo_documento)

    if target == "familiari":
        return (
            Familiare.objects.annotate(
                has_required_document=Exists(documento_filter.filter(familiare=OuterRef("pk")))
            )
            .filter(has_required_document=False)
            .select_related(
                "famiglia",
                "relazione_familiare",
                "indirizzo__citta__provincia",
                "famiglia__indirizzo_principale__citta__provincia",
            )
            .prefetch_related("famiglia__familiari", "famiglia__studenti")
            .order_by("cognome", "nome", "id")
        )

    if target == "studenti":
        return (
            Studente.objects.annotate(
                has_required_document=Exists(documento_filter.filter(studente=OuterRef("pk")))
            )
            .filter(has_required_document=False)
            .select_related(
                "famiglia",
                "indirizzo__citta__provincia",
                "famiglia__indirizzo_principale__citta__provincia",
            )
            .prefetch_related("famiglia__familiari", "famiglia__studenti")
            .order_by("cognome", "nome", "id")
        )

    if target == "famiglie":
        return (
            Famiglia.objects.annotate(
                has_required_document=Exists(documento_filter.filter(famiglia=OuterRef("pk")))
            )
            .filter(has_required_document=False)
            .select_related(
                "stato_relazione_famiglia",
                "indirizzo_principale__citta__provincia",
            )
            .prefetch_related("familiari", "studenti")
            .order_by("cognome_famiglia", "id")
        )

    return []


def build_anagrafica_query_rows(target, records):
    rows = []
    for record in records:
        if target == "familiari":
            details = []
            if record.relazione_familiare_id:
                details.append(str(record.relazione_familiare))
            if record.email:
                details.append(record.email)
            if record.formatted_telefono:
                details.append(record.formatted_telefono)
            rows.append(
                {
                    "label": str(record),
                    "context": f"Famiglia: {record.famiglia.cognome_famiglia}",
                    "details": " | ".join(details),
                    "url": reverse("modifica_familiare", kwargs={"pk": record.pk}),
                }
            )
        elif target == "studenti":
            details = []
            if record.codice_fiscale:
                details.append(f"CF: {record.codice_fiscale}")
            if record.data_nascita:
                details.append(f"Nato/a il {record.data_nascita:%d/%m/%Y}")
            rows.append(
                {
                    "label": str(record),
                    "context": f"Famiglia: {record.famiglia.cognome_famiglia}",
                    "details": " | ".join(details),
                    "url": reverse("modifica_studente", kwargs={"pk": record.pk}),
                }
            )
        elif target == "famiglie":
            details = []
            if record.stato_relazione_famiglia_id:
                details.append(str(record.stato_relazione_famiglia))
            rows.append(
                {
                    "label": record.cognome_famiglia,
                    "context": record.label_contesto_anagrafica(),
                    "details": " | ".join(details),
                    "url": reverse("modifica_famiglia", kwargs={"pk": record.pk}),
                }
            )
    return rows


def ricerche_anagrafica(request):
    query_key = (request.GET.get("query") or "").strip()
    target = (request.GET.get("target") or "").strip()
    tipo_documento_id = (request.GET.get("tipo_documento") or "").strip()
    tipi_documento = list(TipoDocumento.objects.filter(attivo=True).order_by("ordine", "tipo_documento"))
    base_url = reverse("ricerche_anagrafica")

    preset_cards = []
    for preset in ANAGRAFICA_DOCUMENT_QUERY_PRESETS:
        tipo_documento = find_tipo_documento_by_aliases(tipi_documento, preset["aliases"])
        url = ""
        if tipo_documento:
            url = (
                f"{base_url}?query=documenti_mancanti"
                f"&target={preset['target']}"
                f"&tipo_documento={tipo_documento.pk}"
            )
        preset_cards.append({**preset, "tipo_documento": tipo_documento, "url": url})

    selected_tipo_documento = None
    if tipo_documento_id.isdigit():
        selected_tipo_documento = next(
            (tipo for tipo in tipi_documento if tipo.pk == int(tipo_documento_id)),
            None,
        )

    rows = []
    result_title = ""
    result_message = ""
    if query_key == "documenti_mancanti":
        target_label = ANAGRAFICA_DOCUMENT_QUERY_TARGETS.get(target)
        if not target_label:
            result_message = "Seleziona un gruppo valido tra studenti, familiari e famiglie."
        elif not selected_tipo_documento:
            result_message = "Seleziona il tipo documento da verificare."
        else:
            records = anagrafica_document_missing_queryset(target, selected_tipo_documento)
            rows = build_anagrafica_query_rows(target, records)
            result_title = f"{target_label} senza {selected_tipo_documento.tipo_documento}"

    return render(
        request,
        "anagrafica/ricerche_anagrafica.html",
        {
            "query_key": query_key,
            "target": target,
            "tipo_documento_id": tipo_documento_id,
            "tipi_documento": tipi_documento,
            "target_choices": ANAGRAFICA_DOCUMENT_QUERY_TARGETS.items(),
            "preset_cards": preset_cards,
            "rows": rows,
            "result_title": result_title,
            "result_message": result_message,
        },
    )


#INIZIO VIEWS DELLE FAMIGLIE
def lista_famiglie(request):
    q = request.GET.get("q", "").strip()

    famiglie = (
        Famiglia.objects
        .select_related(
            "stato_relazione_famiglia",
            "indirizzo_principale",
            "indirizzo_principale__citta",
            "indirizzo_principale__provincia",
            "indirizzo_principale__regione",
            "indirizzo_principale__cap_scelto",
        )
        .prefetch_related("familiari", "studenti")
        .order_by("cognome_famiglia", "id")
    )

    if q:
        famiglie = famiglie.filter(
            Q(cognome_famiglia__icontains=q) |
            Q(familiari__nome__icontains=q) |
            Q(familiari__cognome__icontains=q) |
            Q(familiari__email__icontains=q) |
            Q(familiari__telefono__icontains=q) |
            Q(studenti__nome__icontains=q) |
            Q(studenti__cognome__icontains=q) |
            Q(studenti__codice_fiscale__icontains=q) |
            Q(indirizzo_principale__via__icontains=q) |
            Q(indirizzo_principale__citta__nome__icontains=q)
        ).distinct()

    evidenzia_id = request.GET.get("highlight")

    return render(
        request,
        "anagrafica/famiglie/famiglia_list.html",
        {
            "famiglie": famiglie,
            "evidenzia_id": evidenzia_id,
            "q": q,
        },
    )


def crea_famiglia(request):
    allowed_inline_targets = {"familiari", "studenti", "documenti"}
    edit_scope = "full"
    inline_target = "familiari"
    active_inline_tab = "familiari"
    prefer_initial_active_tab = False
    familiari_formset = None
    studenti_formset = None
    documenti_formset = None
    if request.method == "POST":
        active_inline_tab = resolve_active_inline_tab(request, allowed_inline_targets, "familiari")
        prefer_initial_active_tab = should_prefer_initial_famiglia_tab(request, allowed_inline_targets)
        edit_scope, inline_target = resolve_inline_target(
            request,
            allowed_inline_targets,
        )
        form = FamigliaForm(request.POST)
        familiari_formset = (
            build_familiari_formset(data=request.POST, prefix="familiari")
            if inline_target in (None, "familiari")
            else None
        )
        studenti_formset = (
            build_studenti_formset(data=request.POST, prefix="studenti")
            if inline_target in (None, "studenti")
            else None
        )
        documenti_formset = (
            build_documenti_famiglia_formset(data=request.POST, files=request.FILES, prefix="documenti")
            if inline_target in (None, "documenti")
            else None
        )

        form_is_valid = form.is_valid()
        familiari_is_valid = familiari_formset.is_valid() if inline_target in (None, "familiari") else True
        studenti_is_valid = studenti_formset.is_valid() if inline_target in (None, "studenti") else True
        documenti_is_valid = documenti_formset.is_valid() if inline_target in (None, "documenti") else True

        if form_is_valid and familiari_is_valid and studenti_is_valid and documenti_is_valid:
            try:
                with transaction.atomic():
                    famiglia = form.save()

                    if inline_target in (None, "familiari"):
                        familiari_formset.instance = famiglia
                        familiari_formset.save()

                    if inline_target in (None, "studenti"):
                        studenti_formset.instance = famiglia
                        studenti_formset.save()

                    if inline_target in (None, "documenti"):
                        documenti_formset.instance = famiglia
                        documenti_formset.save()
            except DOCUMENT_STORAGE_ERROR_TYPES as exc:
                messages.error(request, build_document_storage_error_message(exc))
            else:
                if "_continue" in request.POST:
                    messages.success(request, "Famiglia creata correttamente. Ora puoi continuare a modificarla.")
                    return redirect(build_famiglia_redirect_url(famiglia.pk, active_inline_tab))

                if "_addanother" in request.POST:
                    messages.success(request, "Famiglia creata correttamente. Puoi inserirne un'altra.")
                    return redirect("crea_famiglia")

                messages.success(request, "Famiglia creata correttamente. Ora puoi continuare a inserire i dati.")
                return redirect(build_famiglia_redirect_url(famiglia.pk, active_inline_tab))

        if familiari_formset is None:
            familiari_formset = build_familiari_formset(prefix="familiari")
        if studenti_formset is None:
            studenti_formset = build_studenti_formset(prefix="studenti")
        if documenti_formset is None:
            documenti_formset = build_documenti_famiglia_formset(prefix="documenti")
    else:
        active_inline_tab = resolve_active_inline_tab(request, allowed_inline_targets, "familiari")
        prefer_initial_active_tab = should_prefer_initial_famiglia_tab(request, allowed_inline_targets)
        form = FamigliaForm()
        familiari_formset = build_familiari_formset(prefix="familiari")
        studenti_formset = build_studenti_formset(prefix="studenti")
        documenti_formset = build_documenti_famiglia_formset(prefix="documenti")

    today = timezone.localdate()

    ctx = {
        "form": form,
        "familiari_formset": familiari_formset,
        "studenti_formset": studenti_formset,
        "documenti_formset": documenti_formset,
        "count_familiari": 0,
        "count_studenti": 0,
        "count_documenti": 0,
        "count_documenti_in_scadenza": 0,
        "count_documenti_scaduti": 0,
        "documenti_familiari": [],
        "documenti_studenti": [],
        "count_documenti_familiari": 0,
        "count_documenti_studenti": 0,
        "edit_scope": edit_scope,
        "inline_target": inline_target,
        "active_inline_tab": active_inline_tab,
        "prefer_initial_active_tab": prefer_initial_active_tab,
        "has_form_errors": bool(form.errors or familiari_formset.total_error_count() or studenti_formset.total_error_count() or documenti_formset.total_error_count()),
    }
    ctx.update(
        famiglia_inline_head(
            active_inline_tab=active_inline_tab,
            count_familiari=ctx["count_familiari"],
            count_studenti=ctx["count_studenti"],
            count_documenti=ctx["count_documenti"],
            related_famiglia_studenti_doc_count=0,
        )
    )
    return render(request, "anagrafica/famiglie/famiglia_form.html", ctx)


def modifica_famiglia(request, pk):
    allowed_inline_targets = {"familiari", "studenti", "documenti"}
    famiglia = get_object_or_404(
        Famiglia.objects.select_related(
            "stato_relazione_famiglia",
            "indirizzo_principale__citta__provincia",
            "indirizzo_principale__provincia",
        ),
        pk=pk,
    )
    edit_scope = "view"
    inline_target = "familiari"
    active_inline_tab = "familiari"
    prefer_initial_active_tab = False
    familiari_formset = None
    studenti_formset = None
    documenti_formset = None

    if request.method == "POST":
        active_inline_tab = resolve_active_inline_tab(request, allowed_inline_targets, "familiari")
        prefer_initial_active_tab = should_prefer_initial_famiglia_tab(request, allowed_inline_targets)
        edit_scope, inline_target = resolve_inline_target(
            request,
            allowed_inline_targets,
        )
        form = FamigliaForm(request.POST, instance=famiglia)
        familiari_formset = (
            build_familiari_formset(data=request.POST, instance=famiglia, prefix="familiari")
            if inline_target == "familiari"
            else None
        )
        studenti_formset = (
            build_studenti_formset(data=request.POST, instance=famiglia, prefix="studenti")
            if inline_target == "studenti"
            else None
        )
        documenti_formset = (
            build_documenti_famiglia_formset(
                data=request.POST,
                files=request.FILES,
                instance=famiglia,
                prefix="documenti",
            )
            if inline_target == "documenti"
            else None
        )

        form_is_valid = form.is_valid()
        familiari_is_valid = familiari_formset.is_valid() if inline_target == "familiari" else True
        studenti_is_valid = studenti_formset.is_valid() if inline_target == "studenti" else True
        documenti_is_valid = documenti_formset.is_valid() if inline_target == "documenti" else True

        if form_is_valid and familiari_is_valid and studenti_is_valid and documenti_is_valid:
            try:
                with transaction.atomic():
                    famiglia = form.save()
                    if inline_target == "familiari":
                        familiari_formset.save()
                    if inline_target == "studenti":
                        studenti_formset.save()
                    if inline_target == "documenti":
                        documenti_formset.save()
            except DOCUMENT_STORAGE_ERROR_TYPES as exc:
                messages.error(request, build_document_storage_error_message(exc))
            else:
                if "_continue" in request.POST:
                    messages.success(request, "Modifiche salvate correttamente.")
                    return redirect(build_famiglia_redirect_url(famiglia.pk, active_inline_tab))

                if "_addanother" in request.POST:
                    messages.success(request, "Modifiche salvate correttamente. Puoi inserire una nuova famiglia.")
                    return redirect("crea_famiglia")

                messages.success(request, "Modifiche salvate correttamente.")
                return redirect(build_famiglia_redirect_url(famiglia.pk, active_inline_tab))

        if familiari_formset is None:
            familiari_formset = build_familiari_formset(instance=famiglia, prefix="familiari")
        if studenti_formset is None:
            studenti_formset = build_studenti_formset(instance=famiglia, prefix="studenti")
        if documenti_formset is None:
            documenti_formset = build_documenti_famiglia_formset(instance=famiglia, prefix="documenti")
    else:
        active_inline_tab = resolve_active_inline_tab(request, allowed_inline_targets, "familiari")
        prefer_initial_active_tab = should_prefer_initial_famiglia_tab(request, allowed_inline_targets)
        form = FamigliaForm(instance=famiglia)
        familiari_formset = build_familiari_formset(instance=famiglia, prefix="familiari")
        studenti_formset = build_studenti_formset(instance=famiglia, prefix="studenti")
        documenti_formset = build_documenti_famiglia_formset(instance=famiglia, prefix="documenti")

    today = timezone.localdate()

    documenti_familiari = list(
        Documento.objects
        .filter(familiare__famiglia=famiglia)
        .select_related("familiare", "tipo_documento")
        .order_by("familiare__cognome", "familiare__nome", "-data_caricamento", "-id")
    )

    documenti_studenti = list(
        Documento.objects
        .filter(studente__famiglia=famiglia)
        .select_related("studente", "tipo_documento")
        .order_by("studente__cognome", "studente__nome", "-data_caricamento", "-id")
    )
    count_documenti_familiari = len(documenti_familiari)
    count_documenti_studenti = len(documenti_studenti)
    count_documenti_totali = (
        famiglia.documenti.count()
        + count_documenti_familiari
        + count_documenti_studenti
    )
    famiglia_creata_da_label, famiglia_aggiornata_da_label = famiglia_audit_labels(famiglia)

    ctx = {
        "form": form,
        "famiglia": famiglia,
        "famiglia_creata_da_label": famiglia_creata_da_label,
        "famiglia_aggiornata_da_label": famiglia_aggiornata_da_label,
        "familiari_formset": familiari_formset,
        "studenti_formset": studenti_formset,
        "documenti_formset": documenti_formset,
        "count_familiari": famiglia.familiari.count(),
        "count_studenti": famiglia.studenti.count(),
        "count_documenti": count_documenti_totali,
        "count_documenti_in_scadenza": famiglia.documenti.filter(
            scadenza__isnull=False,
            scadenza__gte=today,
            scadenza__lte=today + timedelta(days=30),
        ).count(),
        "count_documenti_scaduti": famiglia.documenti.filter(
            scadenza__isnull=False,
            scadenza__lt=today,
        ).count(),
        "documenti_familiari": documenti_familiari,
        "documenti_studenti": documenti_studenti,
        "count_documenti_familiari": count_documenti_familiari,
        "count_documenti_studenti": count_documenti_studenti,
        "edit_scope": edit_scope,
        "inline_target": inline_target,
        "active_inline_tab": active_inline_tab,
        "prefer_initial_active_tab": prefer_initial_active_tab,
        "has_form_errors": bool(form.errors or familiari_formset.total_error_count() or studenti_formset.total_error_count() or documenti_formset.total_error_count()),
    }
    ctx.update(
        famiglia_inline_head(
            active_inline_tab=active_inline_tab,
            count_familiari=ctx["count_familiari"],
            count_studenti=ctx["count_studenti"],
            count_documenti=ctx["count_documenti"],
            related_famiglia_studenti_doc_count=count_documenti_familiari + count_documenti_studenti,
        )
    )
    return render(request, "anagrafica/famiglie/famiglia_form.html", ctx)


def elimina_famiglia(request, pk):
    famiglia = get_object_or_404(Famiglia, pk=pk)
    impact = get_famiglia_delete_impact(famiglia)

    if request.method == "POST":
        if request.POST.get("confirm_delete_related") != "1":
            return render(
                request,
                "anagrafica/famiglie/famiglia_conferma_elimina.html",
                {
                    "famiglia": famiglia,
                    "impact": impact,
                    "double_confirm": True,
                },
            )

        indirizzi_da_eliminare_ids = [item["id"] for item in impact["indirizzi_da_eliminare"]]

        with transaction.atomic():
            famiglia.delete()
            if indirizzi_da_eliminare_ids:
                Indirizzo.objects.filter(pk__in=indirizzi_da_eliminare_ids).delete()

        messages.success(request, "Famiglia e dati correlati eliminati correttamente.")
        return redirect("lista_famiglie")

    return render(
        request,
        "anagrafica/famiglie/famiglia_conferma_elimina.html",
        {
            "famiglia": famiglia,
            "impact": impact,
            "double_confirm": False,
        },
    )


def stampa_famiglia(request, pk):
    famiglia = get_object_or_404(
        Famiglia.objects.select_related(
            "stato_relazione_famiglia",
            "indirizzo_principale",
            "indirizzo_principale__citta",
        ),
        pk=pk,
    )

    familiari = (
        famiglia.familiari
        .select_related("relazione_familiare", "indirizzo", "famiglia__indirizzo_principale", "luogo_nascita", "nazione_nascita", "nazionalita")
        .order_by("cognome", "nome")
    )
    studenti = (
        famiglia.studenti
        .select_related("indirizzo", "famiglia__indirizzo_principale", "luogo_nascita", "nazione_nascita", "nazionalita")
        .order_by("cognome", "nome")
    )

    return render(
        request,
        "anagrafica/famiglie/famiglia_print.html",
        {
            "famiglia": famiglia,
            "familiari": familiari,
            "studenti": studenti,
            "print_date": timezone.localdate(),
        },
    )
def crea_stato_relazione_famiglia(request):
    popup = is_popup_request(request)

    StatoRelazioneFamigliaForm = modelform_factory(
        StatoRelazioneFamiglia,
        fields=["stato", "ordine", "attivo", "note"],
    )

    if request.method == "POST":
        form = StatoRelazioneFamigliaForm(request.POST)
        if form.is_valid():
            obj = form.save()

            if popup:
                return popup_select_response(
                    request,
                    field_name="stato_relazione_famiglia",
                    object_id=obj.pk,
                    object_label=str(obj),
                )

            messages.success(request, "Stato relazione famiglia creato correttamente.")
            return redirect("lista_famiglie")
    else:
        form = StatoRelazioneFamigliaForm()

    return render(
        request,
        "anagrafica/configurazioni/stato_relazione_famiglia_popup_form.html" if popup else "anagrafica/configurazioni/stato_relazione_famiglia_form.html",
        {
            "form": form,
            "titolo": "Nuovo stato relazione famiglia",
            "popup": popup,
        },
    )


def modifica_stato_relazione_famiglia(request, pk):
    stato = get_object_or_404(StatoRelazioneFamiglia, pk=pk)
    popup = is_popup_request(request)

    StatoRelazioneFamigliaForm = modelform_factory(
        StatoRelazioneFamiglia,
        fields=["stato", "ordine", "attivo", "note"],
    )

    if request.method == "POST":
        form = StatoRelazioneFamigliaForm(request.POST, instance=stato)
        if form.is_valid():
            obj = form.save()

            if popup:
                return popup_select_response(
                    request,
                    field_name="stato_relazione_famiglia",
                    object_id=obj.pk,
                    object_label=str(obj),
                )

            messages.success(request, "Stato relazione famiglia modificato correttamente.")
            return redirect("lista_famiglie")
    else:
        form = StatoRelazioneFamigliaForm(instance=stato)

    return render(
        request,
        "anagrafica/configurazioni/stato_relazione_famiglia_popup_form.html" if popup else "anagrafica/configurazioni/stato_relazione_famiglia_form.html",
        {
            "form": form,
            "titolo": "Modifica stato relazione famiglia",
            "popup": popup,
        },
    )


def elimina_stato_relazione_famiglia(request, pk):
    stato = get_object_or_404(StatoRelazioneFamiglia, pk=pk)
    popup = is_popup_request(request)

    object_id = stato.pk

    if request.method == "POST":
        stato.delete()

        if popup:
            return popup_delete_response(
                request,
                field_name="stato_relazione_famiglia",
                object_id=object_id,
            )

        messages.success(request, "Stato relazione famiglia eliminato correttamente.")
        return redirect("lista_famiglie")

    return render(
        request,
        "anagrafica/configurazioni/stato_relazione_famiglia_popup_delete.html" if popup else "anagrafica/configurazioni/stato_relazione_famiglia_delete.html",
        {
            "oggetto": stato,
            "titolo": "Elimina stato relazione famiglia",
            "popup": popup,
        },
    )

#FINE VIEWS DELLE FAMIGLIE

#INIZIO VIEWS PER I FAMILIARI

#Views per le relazioni familiari
def crea_relazione_familiare(request):
    popup = is_popup_request(request)

    RelazioneFamiliareForm = modelform_factory(
        RelazioneFamiliare,
        fields=["relazione", "ordine", "note"],
    )

    if request.method == "POST":
        form = RelazioneFamiliareForm(request.POST)
        if form.is_valid():
            obj = form.save()

            if popup:
                return popup_select_response(
                    request,
                    field_name="relazione_familiare",
                    object_id=obj.pk,
                    object_label=str(obj),
                )

            messages.success(request, "Relazione familiare creata correttamente.")
            return redirect("lista_famiglie")
    else:
        form = RelazioneFamiliareForm()

    return render(
        request,
        "anagrafica/configurazioni/relazione_familiare_popup_form.html" if popup else "anagrafica/configurazioni/relazione_familiare_form.html",
        {
            "form": form,
            "titolo": "Nuova relazione familiare",
            "popup": popup,
        },
    )


def modifica_relazione_familiare(request, pk):
    relazione = get_object_or_404(RelazioneFamiliare, pk=pk)
    popup = is_popup_request(request)

    RelazioneFamiliareForm = modelform_factory(
        RelazioneFamiliare,
        fields=["relazione", "ordine", "note"],
    )

    if request.method == "POST":
        form = RelazioneFamiliareForm(request.POST, instance=relazione)
        if form.is_valid():
            obj = form.save()

            if popup:
                return popup_select_response(
                    request,
                    field_name="relazione_familiare",
                    object_id=obj.pk,
                    object_label=str(obj),
                )

            messages.success(request, "Relazione familiare modificata correttamente.")
            return redirect("lista_famiglie")
    else:
        form = RelazioneFamiliareForm(instance=relazione)

    return render(
        request,
        "anagrafica/configurazioni/relazione_familiare_popup_form.html" if popup else "anagrafica/configurazioni/relazione_familiare_form.html",
        {
            "form": form,
            "titolo": "Modifica relazione familiare",
            "popup": popup,
        },
    )


def elimina_relazione_familiare(request, pk):
    relazione = get_object_or_404(RelazioneFamiliare, pk=pk)
    popup = is_popup_request(request)

    object_id = relazione.pk

    if request.method == "POST":
        relazione.delete()

        if popup:
            return popup_delete_response(
                request,
                field_name="relazione_familiare",
                object_id=object_id,
            )

        messages.success(request, "Relazione familiare eliminata correttamente.")
        return redirect("lista_famiglie")

    return render(
        request,
        "anagrafica/configurazioni/relazione_familiare_popup_delete.html" if popup else "anagrafica/configurazioni/relazione_familiare_delete.html",
        {
            "oggetto": relazione,
            "titolo": "Elimina relazione familiare",
            "popup": popup,
        },
    )


#Views per i familiari veri e propri
def lista_familiari(request):
    q = request.GET.get("q", "").strip()

    familiari = (
        Familiare.objects
        .select_related(
            "famiglia",
            "relazione_familiare",
            "indirizzo",
            "indirizzo__citta",
            "luogo_nascita",
            "luogo_nascita__provincia",
            "nazione_nascita",
            "nazionalita",
            "famiglia__indirizzo_principale",
            "famiglia__indirizzo_principale__citta",
            "famiglia__indirizzo_principale__provincia",
            "famiglia__indirizzo_principale__regione",
            "famiglia__indirizzo_principale__cap_scelto",
        )
        .prefetch_related("famiglia__familiari", "famiglia__studenti")
        .order_by("cognome", "nome")
    )

    if q:
        familiari = familiari.filter(
            Q(nome__icontains=q) |
            Q(cognome__icontains=q) |
            Q(email__icontains=q) |
            Q(telefono__icontains=q) |
            Q(codice_fiscale__icontains=q) |
            Q(luogo_nascita__nome__icontains=q) |
            Q(luogo_nascita__provincia__sigla__icontains=q) |
            Q(nazione_nascita__nome__icontains=q) |
            Q(luogo_nascita_custom__icontains=q) |
            Q(famiglia__cognome_famiglia__icontains=q) |
            Q(relazione_familiare__relazione__icontains=q)
        )

    evidenzia_id = request.GET.get("highlight")

    return render(
        request,
        "anagrafica/familiari/familiari_lista.html",
        {
            "familiari": familiari,
            "q": q,
            "evidenzia_id": evidenzia_id,
        },
    )


def crea_familiare(request):
    if request.method == "POST":
        form = FamiliareForm(request.POST)
        documenti_formset = DocumentoFamiliareFormSet(
            request.POST,
            request.FILES,
            prefix="documenti",
        )

        if form.is_valid() and documenti_formset.is_valid():
            try:
                with transaction.atomic():
                    familiare = form.save()
                    documenti_formset.instance = familiare
                    documenti_formset.save()
            except DOCUMENT_STORAGE_ERROR_TYPES as exc:
                messages.error(request, build_document_storage_error_message(exc))
            else:
                if "_continue" in request.POST:
                    messages.success(request, "Familiare creato correttamente. Ora puoi continuare a modificarlo.")
                    return redirect("modifica_familiare", pk=familiare.pk)

                if "_addanother" in request.POST:
                    messages.success(request, "Familiare creato correttamente. Puoi inserirne un altro.")
                    return redirect("crea_familiare")

                messages.success(request, "Familiare creato correttamente.")
                return redirect(f"{reverse('lista_familiari')}?highlight={familiare.pk}")
    else:
        form = FamiliareForm()
        documenti_formset = DocumentoFamiliareFormSet(prefix="documenti")

    return render(
        request,
        "anagrafica/familiari/familiari_form.html",
        {
            "form": form,
            "documenti_formset": documenti_formset,
            "studenti_formset": None,
            "studenti_famiglia": None,
            "count_studenti": 0,
            "studente_inline_defaults": None,
            "count_documenti": 0,
            "count_documenti_in_scadenza": 0,
            "count_documenti_scaduti": 0,
            "scambio_retta_inline_context": {"enabled": False, "sections": []},
            "scambio_retta_return_to": "",
            "edit_scope": "full",
            "inline_target": "documenti",
            "familiare_inline_tabs": [
                {
                    "tab_id": "tab-documenti",
                    "label": "Documenti",
                    "base_label": "Documenti",
                    "count": 0,
                    "is_active": True,
                },
            ],
            "familiare_inline_edit_label": "Modifica Documenti",
        },
    )


def modifica_familiare(request, pk):
    familiare = get_object_or_404(
        Familiare.objects.select_related(
            "famiglia",
            "relazione_familiare",
            "indirizzo",
            "luogo_nascita",
            "luogo_nascita__provincia",
            "nazione_nascita",
            "nazionalita",
            "famiglia__indirizzo_principale",
            "famiglia__indirizzo_principale__citta",
            "famiglia__indirizzo_principale__provincia",
            "famiglia__indirizzo_principale__regione",
            "famiglia__indirizzo_principale__cap_scelto",
        )
        .prefetch_related("famiglia__familiari", "famiglia__studenti"),
        pk=pk,
    )
    today = timezone.localdate()
    edit_scope = "view"

    studenti_formset = None

    def famiglia_for_studenti_inline(current_edit_scope=None):
        if request.method != "POST" or current_edit_scope == "inline":
            return familiare.famiglia if familiare.famiglia_id else None
        raw = (request.POST.get("famiglia") or "").strip()
        if raw.isdigit():
            return (
                Famiglia.objects.filter(pk=int(raw))
                .select_related("indirizzo_principale", "indirizzo_principale__citta__provincia")
                .first()
            )
        return None

    if request.method == "POST":
        edit_scope = (request.POST.get("_edit_scope") or "full").strip()
        if edit_scope == "view":
            return redirect(request.get_full_path())

        inline_editing = edit_scope == "inline"
        famiglia_for_studenti = famiglia_for_studenti_inline(edit_scope)
        form = (
            FamiliareForm(instance=familiare)
            if inline_editing
            else FamiliareForm(request.POST, instance=familiare)
        )
        if inline_editing:
            documenti_formset = DocumentoFamiliareFormSet(
                request.POST,
                request.FILES,
                instance=familiare,
                prefix="documenti",
            )
        else:
            documenti_formset = DocumentoFamiliareFormSet(instance=familiare, prefix="documenti")
        if famiglia_for_studenti:
            studenti_formset = build_studenti_formset(
                data=request.POST if inline_editing else None,
                instance=famiglia_for_studenti,
                prefix="studenti",
            )

        studenti_ok = studenti_formset.is_valid() if inline_editing and studenti_formset is not None else True
        form_ok = True if inline_editing else form.is_valid()
        documenti_ok = documenti_formset.is_valid() if inline_editing else True

        if form_ok and documenti_ok and studenti_ok:
            try:
                with transaction.atomic():
                    if not inline_editing:
                        familiare = form.save()
                    if inline_editing:
                        documenti_formset.save()
                    if inline_editing and studenti_formset is not None:
                        studenti_formset.save()
            except DOCUMENT_STORAGE_ERROR_TYPES as exc:
                messages.error(request, build_document_storage_error_message(exc))
            else:
                if "_continue" in request.POST:
                    messages.success(request, "Modifiche salvate correttamente.")
                    target = (request.POST.get("_inline_target") or "").strip()
                    allowed_targets = ["documenti"]
                    if studenti_formset is not None:
                        allowed_targets.insert(0, "studenti")
                    default_target = "studenti" if "studenti" in allowed_targets else "documenti"
                    if target not in allowed_targets:
                        target = default_target
                    return redirect(build_familiare_redirect_url(familiare.pk, target, default_target))

                if "_addanother" in request.POST:
                    messages.success(request, "Modifiche salvate correttamente. Puoi inserire un nuovo familiare.")
                    return redirect("crea_familiare")

                messages.success(request, "Modifiche salvate correttamente.")
                target = (request.POST.get("_inline_target") or "").strip()
                allowed_targets = ["documenti"]
                if studenti_formset is not None:
                    allowed_targets.insert(0, "studenti")
                default_target = "studenti" if "studenti" in allowed_targets else "documenti"
                if target not in allowed_targets:
                    target = default_target
                return redirect(build_familiare_redirect_url(familiare.pk, target, default_target))
        if studenti_formset is None and famiglia_for_studenti:
            studenti_formset = build_studenti_formset(instance=famiglia_for_studenti, prefix="studenti")
    else:
        famiglia_for_studenti = famiglia_for_studenti_inline(edit_scope)
        form = FamiliareForm(instance=familiare)
        documenti_formset = DocumentoFamiliareFormSet(instance=familiare, prefix="documenti")
        if famiglia_for_studenti:
            studenti_formset = build_studenti_formset(instance=famiglia_for_studenti, prefix="studenti")

    count_studenti = famiglia_for_studenti.studenti.count() if famiglia_for_studenti else 0
    studente_inline_defaults = None
    if famiglia_for_studenti:
        studente_inline_defaults = {
            "indirizzo_principale_id": str(famiglia_for_studenti.indirizzo_principale_id or ""),
            "cognome_famiglia": famiglia_for_studenti.cognome_famiglia or "",
        }
    scambio_retta_inline_context = build_familiare_scambio_retta_inline_context(familiare, request.GET)
    scambio_retta_return_to = f"{request.get_full_path()}#scambio-retta-inline"
    allowed_inline_targets = ["documenti"]
    if studenti_formset is not None:
        allowed_inline_targets.insert(0, "studenti")
    default_inline_target = "studenti" if "studenti" in allowed_inline_targets else "documenti"
    inline_target = resolve_active_inline_tab(request, allowed_inline_targets, default_inline_target)
    familiare_inline_tabs = []
    familiare_inline_edit_label = "Modifica Documenti"
    if studenti_formset is not None:
        terminology = get_student_terminology()
        familiare_inline_tabs.append({
            "tab_id": "tab-studenti",
            "label": terminology["selected_plural"],
            "base_label": terminology["selected_plural"],
            "count": count_studenti,
            "is_active": inline_target == "studenti",
        })
        if inline_target == "studenti":
            familiare_inline_edit_label = f"Modifica {terminology['selected_plural']}"
    familiare_inline_tabs.append({
        "tab_id": "tab-documenti",
        "label": "Documenti",
        "base_label": "Documenti",
        "count": familiare.documenti.count(),
        "is_active": inline_target == "documenti",
    })
    familiare_audit_info = last_update_audit_info(familiare)

    return render(
        request,
        "anagrafica/familiari/familiari_form.html",
        {
            "form": form,
            "familiare": familiare,
            "documenti_formset": documenti_formset,
            "studenti_formset": studenti_formset,
            "studenti_famiglia": famiglia_for_studenti,
            "count_studenti": count_studenti,
            "studente_inline_defaults": studente_inline_defaults,
            "count_documenti": familiare.documenti.count(),
            "count_documenti_in_scadenza": familiare.documenti.filter(
                scadenza__isnull=False,
                scadenza__gte=today,
                scadenza__lte=today + timedelta(days=30),
            ).count(),
            "count_documenti_scaduti": familiare.documenti.filter(
                scadenza__isnull=False,
                scadenza__lt=today,
            ).count(),
            "scambio_retta_inline_context": scambio_retta_inline_context,
            "scambio_retta_return_to": scambio_retta_return_to,
            "edit_scope": edit_scope,
            "inline_target": inline_target,
            "familiare_inline_tabs": familiare_inline_tabs,
            "familiare_inline_edit_label": familiare_inline_edit_label,
            "familiare_ultima_modifica_data": familiare_audit_info["data"],
            "familiare_aggiornato_da_label": familiare_audit_info["utente_label"],
        },
    )


def elimina_familiare(request, pk):
    familiare = get_object_or_404(Familiare, pk=pk)
    impact = get_record_documents_impact(familiare)

    if request.method == "POST":
        familiare.delete()
        messages.success(request, "Familiare eliminato correttamente.")
        return redirect("lista_familiari")

    return render(
        request,
        "anagrafica/familiari/familiari_conferma_elimina.html",
        {
            "familiare": familiare,
            "impact": impact,
        },
    )

#FINE VIEWS PER I FAMILIARI

#VIEWS PER I DOCUMENTI ALLEGATI

def crea_tipo_documento(request):
    popup = is_popup_request(request)

    TipoDocumentoForm = modelform_factory(
        TipoDocumento,
        fields=["tipo_documento", "ordine", "attivo", "note"],
    )

    if request.method == "POST":
        form = TipoDocumentoForm(request.POST)
        if form.is_valid():
            obj = form.save()

            if popup:
                return popup_select_response(
                    request,
                    field_name="tipo_documento",
                    object_id=obj.pk,
                    object_label=str(obj),
                )

            messages.success(request, "Tipo documento creato correttamente.")
            return redirect("lista_famiglie")
    else:
        form = TipoDocumentoForm()

    return render(
        request,
        "anagrafica/configurazioni/tipo_documento_popup_form.html" if popup else "anagrafica/configurazioni/tipo_documento_form.html",
        {
            "form": form,
            "titolo": "Nuovo tipo documento",
            "popup": popup,
        },
    )


def modifica_tipo_documento(request, pk):
    tipo = get_object_or_404(TipoDocumento, pk=pk)
    popup = is_popup_request(request)

    TipoDocumentoForm = modelform_factory(
        TipoDocumento,
        fields=["tipo_documento", "ordine", "attivo", "note"],
    )

    if request.method == "POST":
        form = TipoDocumentoForm(request.POST, instance=tipo)
        if form.is_valid():
            obj = form.save()

            if popup:
                return popup_select_response(
                    request,
                    field_name="tipo_documento",
                    object_id=obj.pk,
                    object_label=str(obj),
                )

            messages.success(request, "Tipo documento modificato correttamente.")
            return redirect("lista_famiglie")
    else:
        form = TipoDocumentoForm(instance=tipo)

    return render(
        request,
        "anagrafica/configurazioni/tipo_documento_popup_form.html" if popup else "anagrafica/configurazioni/tipo_documento_form.html",
        {
            "form": form,
            "titolo": "Modifica tipo documento",
            "popup": popup,
        },
    )


def elimina_tipo_documento(request, pk):
    tipo = get_object_or_404(TipoDocumento, pk=pk)
    popup = is_popup_request(request)

    object_id = tipo.pk

    if request.method == "POST":
        tipo.delete()

        if popup:
            return popup_delete_response(
                request,
                field_name="tipo_documento",
                object_id=object_id,
            )

        messages.success(request, "Tipo documento eliminato correttamente.")
        return redirect("lista_famiglie")

    return render(
        request,
        "anagrafica/configurazioni/tipo_documento_popup_delete.html" if popup else "anagrafica/configurazioni/tipo_documento_delete.html",
        {
            "oggetto": tipo,
            "titolo": "Elimina tipo documento",
            "popup": popup,
        },
    )

#FINE VIEWS PER I DOCUMENTI ALLEGATI

#INIZIO VIEWS PER GLI STUDENTI

def lista_studenti(request):
    q = request.GET.get("q", "").strip()

    studenti = (
        annotate_studenti_current_iscrizione_status(Studente.objects.all())
        .select_related(
            "famiglia",
            "famiglia__indirizzo_principale",
            "famiglia__indirizzo_principale__citta",
            "famiglia__indirizzo_principale__provincia",
            "famiglia__indirizzo_principale__regione",
            "famiglia__indirizzo_principale__cap_scelto",
            "indirizzo",
            "indirizzo__citta",
            "indirizzo__provincia",
            "indirizzo__regione",
            "indirizzo__cap_scelto",
            "luogo_nascita",
            "luogo_nascita__provincia",
            "nazione_nascita",
            "nazionalita",
        )
        .prefetch_related("famiglia__familiari", "famiglia__studenti")
        .order_by("cognome", "nome")
    )

    if q:
        studenti = studenti.filter(
            Q(cognome__icontains=q) |
            Q(nome__icontains=q) |
            Q(codice_fiscale__icontains=q) |
            Q(luogo_nascita__nome__icontains=q) |
            Q(luogo_nascita__provincia__sigla__icontains=q) |
            Q(nazione_nascita__nome__icontains=q) |
            Q(luogo_nascita_custom__icontains=q) |
            Q(famiglia__cognome_famiglia__icontains=q)
        )

    evidenzia_id = request.GET.get("highlight")

    return render(
        request,
        "anagrafica/studenti/studente_list.html",
        {
            "studenti": studenti,
            "q": q,
            "evidenzia_id": evidenzia_id,
        },
    )


def crea_studente(request):
    popup = is_popup_request(request)

    if popup:
        famiglia_id = request.GET.get("famiglia")
        if request.method == "POST":
            form = StudenteStandaloneForm(request.POST)
            if form.is_valid():
                studente = form.save()
                return popup_select_response(request, "studente", studente.pk, str(studente))
        else:
            initial = {}
            if famiglia_id:
                try:
                    initial["famiglia"] = int(famiglia_id)
                except (TypeError, ValueError):
                    pass
            form = StudenteStandaloneForm(initial=initial)

        return render(
            request,
            "anagrafica/studenti/studente_popup_form.html",
            {
                "form": form,
                "studente": None,
                "popup": popup,
            },
        )

    edit_scope = "full"
    inline_target = "iscrizioni"

    if request.method == "POST":
        edit_scope, inline_target = resolve_inline_target(
            request,
            {"iscrizioni", "documenti"},
        )
        form = StudenteStandaloneForm(request.POST)
        iscrizioni_formset = (
            build_iscrizioni_studente_formset(data=request.POST, prefix="iscrizioni")
            if inline_target in (None, "iscrizioni")
            else build_iscrizioni_studente_formset(prefix="iscrizioni")
        )
        documenti_formset = (
            build_documenti_studente_formset(data=request.POST, files=request.FILES, prefix="documenti")
            if inline_target in (None, "documenti")
            else build_documenti_studente_formset(prefix="documenti")
        )

        form_is_valid = form.is_valid()
        iscrizioni_is_valid = iscrizioni_formset.is_valid() if inline_target in (None, "iscrizioni") else True
        documenti_is_valid = documenti_formset.is_valid() if inline_target in (None, "documenti") else True

        if form_is_valid and iscrizioni_is_valid and documenti_is_valid:
            missing_rate_count = 0
            try:
                with transaction.atomic():
                    studente = form.save()

                    if inline_target in (None, "iscrizioni"):
                        iscrizioni_formset.instance = studente
                        iscrizioni_formset.save()

                    if inline_target in (None, "iscrizioni"):
                        for iscrizione in studente.iscrizioni.select_related(
                            "anno_scolastico",
                            "condizione_iscrizione",
                            "stato_iscrizione",
                            "agevolazione",
                            "studente__famiglia",
                        ):
                            if (
                                not getattr(iscrizione, "anno_scolastico_id", None)
                                or not getattr(iscrizione, "condizione_iscrizione_id", None)
                                or not getattr(iscrizione, "stato_iscrizione_id", None)
                            ):
                                continue
                            esito_rate = iscrizione.sync_rate_schedule()
                            if esito_rate == "missing":
                                missing_rate_count += 1

                    if inline_target in (None, "documenti"):
                        documenti_formset.instance = studente
                        documenti_formset.save()
            except DOCUMENT_STORAGE_ERROR_TYPES as exc:
                messages.error(request, build_document_storage_error_message(exc))
            else:
                if missing_rate_count:
                    messages.warning(
                        request,
                        "Una o piu iscrizioni sono state salvate senza generare il piano rate: verifica la tariffa attiva della condizione selezionata.",
                    )

                if "_continue" in request.POST:
                    messages.success(request, "Studente creato correttamente. Ora puoi continuare a modificarlo.")
                    return redirect("modifica_studente", pk=studente.pk)

                if "_addanother" in request.POST:
                    messages.success(request, "Studente creato correttamente. Puoi inserirne un altro.")
                    return redirect("crea_studente")

                messages.success(request, "Studente creato correttamente.")
                return redirect(f"{reverse('lista_studenti')}?highlight={studente.pk}")
    else:
        form = StudenteStandaloneForm()
        iscrizioni_formset = build_iscrizioni_studente_formset(prefix="iscrizioni")
        documenti_formset = build_documenti_studente_formset(prefix="documenti")

    ctx = {
        "form": form,
        "iscrizioni_formset": iscrizioni_formset,
        "documenti_formset": documenti_formset,
        "classe_corrente_label": "",
        "edit_scope": edit_scope,
        "inline_target": inline_target,
        "show_inline_iscrizioni_editor": edit_scope == "inline" and inline_target == "iscrizioni",
        "count_iscrizioni": 0,
        "count_documenti": 0,
        "count_documenti_in_scadenza": 0,
        "count_documenti_scaduti": 0,
        "rate_overview": [],
    }
    ctx.update(
        studente_inline_head(
            inline_target=inline_target,
            count_iscrizioni=ctx["count_iscrizioni"],
            count_documenti=ctx["count_documenti"],
        )
    )
    return render(request, "anagrafica/studenti/studente_form.html", ctx)


def modifica_studente(request, pk):
    studente = get_object_or_404(
        Studente.objects.select_related(
            "famiglia",
            "famiglia__indirizzo_principale",
            "famiglia__indirizzo_principale__provincia",
            "famiglia__indirizzo_principale__regione",
            "famiglia__indirizzo_principale__citta__provincia",
            "indirizzo",
            "indirizzo__provincia",
            "indirizzo__regione",
            "indirizzo__citta__provincia",
            "luogo_nascita",
            "luogo_nascita__provincia",
        )
        .prefetch_related("famiglia__familiari", "famiglia__studenti"),
        pk=pk,
    )
    today = timezone.localdate()
    popup = is_popup_request(request)
    edit_scope = "view"
    inline_target = "iscrizioni"

    if popup:
        if request.method == "POST":
            form = StudenteStandaloneForm(request.POST, instance=studente)
            if form.is_valid():
                studente = form.save()
                return popup_select_response(request, "studente", studente.pk, str(studente))
        else:
            form = StudenteStandaloneForm(instance=studente)

        return render(
            request,
            "anagrafica/studenti/studente_popup_form.html",
            {
                "form": form,
                "studente": studente,
                "popup": popup,
            },
        )

    iscrizioni_queryset = studente_iscrizioni_inline_queryset(studente)
    documenti_queryset = studente_documenti_inline_queryset(studente)

    if request.method == "POST":
        edit_scope, inline_target = resolve_inline_target(
            request,
            {"iscrizioni", "documenti"},
        )
        form = StudenteStandaloneForm(request.POST, instance=studente)
        iscrizioni_formset = (
            build_iscrizioni_studente_formset(
                data=request.POST,
                instance=studente,
                prefix="iscrizioni",
                queryset=iscrizioni_queryset,
            )
            if inline_target == "iscrizioni"
            else build_iscrizioni_studente_formset(
                instance=studente,
                prefix="iscrizioni",
                queryset=iscrizioni_queryset,
            )
        )
        documenti_formset = (
            build_documenti_studente_formset(
                data=request.POST,
                files=request.FILES,
                instance=studente,
                prefix="documenti",
                queryset=documenti_queryset,
            )
            if inline_target == "documenti"
            else build_documenti_studente_formset(
                instance=studente,
                prefix="documenti",
                queryset=documenti_queryset,
            )
        )

        form_is_valid = form.is_valid()
        iscrizioni_is_valid = iscrizioni_formset.is_valid() if inline_target == "iscrizioni" else True
        documenti_is_valid = documenti_formset.is_valid() if inline_target == "documenti" else True

        if form_is_valid and iscrizioni_is_valid and documenti_is_valid:
            missing_rate_count = 0
            try:
                with transaction.atomic():
                    studente = form.save()
                    if inline_target == "iscrizioni":
                        iscrizioni_formset.save()

                        for iscrizione in studente.iscrizioni.select_related(
                            "anno_scolastico",
                            "condizione_iscrizione",
                            "stato_iscrizione",
                            "agevolazione",
                            "studente__famiglia",
                        ):
                            if (
                                not getattr(iscrizione, "anno_scolastico_id", None)
                                or not getattr(iscrizione, "condizione_iscrizione_id", None)
                                or not getattr(iscrizione, "stato_iscrizione_id", None)
                            ):
                                continue
                            esito_rate = iscrizione.sync_rate_schedule()
                            if esito_rate == "missing":
                                missing_rate_count += 1

                    if inline_target == "documenti":
                        documenti_formset.save()
            except DOCUMENT_STORAGE_ERROR_TYPES as exc:
                messages.error(request, build_document_storage_error_message(exc))
            else:
                if missing_rate_count:
                    messages.warning(
                        request,
                        "Una o piu iscrizioni sono state salvate senza generare il piano rate: verifica la tariffa attiva della condizione selezionata.",
                    )

                if "_continue" in request.POST:
                    messages.success(request, "Modifiche salvate correttamente.")
                    return redirect("modifica_studente", pk=studente.pk)

                if "_addanother" in request.POST:
                    messages.success(request, "Modifiche salvate correttamente. Puoi inserire un nuovo studente.")
                    return redirect("crea_studente")

                messages.success(request, "Modifiche salvate correttamente.")
                return redirect("modifica_studente", pk=studente.pk)
    else:
        form = StudenteStandaloneForm(instance=studente)
        iscrizioni_formset = build_iscrizioni_studente_formset(
            instance=studente,
            prefix="iscrizioni",
            queryset=iscrizioni_queryset,
        )
        documenti_formset = build_documenti_studente_formset(
            instance=studente,
            prefix="documenti",
            queryset=documenti_queryset,
        )

    iscrizioni_correnti_list = list(iscrizioni_queryset)
    iscrizione_corrente = (
        next(
            (
                item for item in sorted(
                    (iscrizione for iscrizione in iscrizioni_correnti_list if iscrizione.classe_id or iscrizione.gruppo_classe_id),
                    key=lambda iscrizione: (
                        0 if iscrizione.attiva else 1,
                        -(iscrizione.anno_scolastico.data_inizio.toordinal() if iscrizione.anno_scolastico and iscrizione.anno_scolastico.data_inizio else 0),
                        -iscrizione.pk,
                    ),
                )
            ),
            None,
        )
    )
    classe_corrente_label = ""
    if iscrizione_corrente:
        if iscrizione_corrente.classe:
            classe_corrente_label = str(iscrizione_corrente.classe)
        elif iscrizione_corrente.gruppo_classe_id:
            classe_corrente_label = iscrizione_corrente.gruppo_classe.nome_gruppo_classe
    document_counts = build_studente_document_counts(studente, today)
    studente_audit_info = last_update_audit_info(studente)

    ctx = {
        "form": form,
        "studente": studente,
        "iscrizioni_formset": iscrizioni_formset,
        "documenti_formset": documenti_formset,
        "classe_corrente_label": classe_corrente_label,
        "edit_scope": edit_scope,
        "inline_target": inline_target,
        "show_inline_iscrizioni_editor": edit_scope == "inline" and inline_target == "iscrizioni",
        "count_iscrizioni": len(iscrizioni_correnti_list),
        "count_documenti": document_counts["count_documenti"],
        "count_documenti_in_scadenza": document_counts["count_documenti_in_scadenza"],
        "count_documenti_scaduti": document_counts["count_documenti_scaduti"],
        "rate_overview": build_studente_rate_overview(studente, iscrizioni_correnti_list),
        "studente_ultima_modifica_data": studente_audit_info["data"],
        "studente_aggiornato_da_label": studente_audit_info["utente_label"],
    }
    ctx.update(
        studente_inline_head(
            inline_target=inline_target,
            count_iscrizioni=ctx["count_iscrizioni"],
            count_documenti=ctx["count_documenti"],
        )
    )
    return render(request, "anagrafica/studenti/studente_form.html", ctx)


def get_studente_print_osservazioni(request, studente):
    try:
        from osservazioni.views import get_osservazioni_policy, user_can_manage_osservazioni
        from sistema.permissions import user_is_operational_admin
    except ImportError:
        return [], False

    if not user_can_manage_osservazioni(request.user):
        return [], False

    osservazioni_policy = get_osservazioni_policy()
    osservazioni_qs = studente.osservazioni.select_related("creato_da", "aggiornato_da").order_by(
        "data_inserimento",
        "id",
    )
    if osservazioni_policy["solo_autori_visualizzazione"] and not user_is_operational_admin(request.user):
        osservazioni_qs = osservazioni_qs.filter(creato_da=request.user)

    return list(osservazioni_qs), True


def get_studente_print_payload(request, studente, *, include_rate=False, include_osservazioni=False):
    anno_corrente = resolve_default_anno_scolastico(AnnoScolastico.objects.filter(attivo=True))
    iscrizioni_correnti = []
    rate_overview = []

    if include_rate and anno_corrente:
        iscrizioni_correnti = list(
            studente_iscrizioni_inline_queryset(studente).filter(anno_scolastico=anno_corrente)
        )
        rate_overview = build_studente_rate_overview(studente, iscrizioni_correnti)

    osservazioni = []
    can_print_osservazioni = False
    if include_osservazioni:
        osservazioni, can_print_osservazioni = get_studente_print_osservazioni(request, studente)
    else:
        _, can_print_osservazioni = get_studente_print_osservazioni(request, studente)

    classe_corrente_label = ""
    iscrizione_corrente = next((item for item in iscrizioni_correnti if item.classe_id or item.gruppo_classe_id), None)
    if iscrizione_corrente and iscrizione_corrente.classe:
        classe_corrente_label = str(iscrizione_corrente.classe)
    elif iscrizione_corrente and iscrizione_corrente.gruppo_classe_id:
        classe_corrente_label = iscrizione_corrente.gruppo_classe.nome_gruppo_classe
    elif anno_corrente:
        iscrizione_corrente = (
            studente.iscrizioni.select_related("classe", "gruppo_classe", "anno_scolastico")
            .filter(anno_scolastico=anno_corrente)
            .filter(Q(classe__isnull=False) | Q(gruppo_classe__isnull=False))
            .order_by("-attiva", "-pk")
            .first()
        )
        if iscrizione_corrente and iscrizione_corrente.classe:
            classe_corrente_label = str(iscrizione_corrente.classe)
        elif iscrizione_corrente and iscrizione_corrente.gruppo_classe_id:
            classe_corrente_label = iscrizione_corrente.gruppo_classe.nome_gruppo_classe

    return {
        "anno_corrente": anno_corrente,
        "classe_corrente_label": classe_corrente_label,
        "rate_overview": rate_overview,
        "osservazioni": osservazioni,
        "can_print_osservazioni": can_print_osservazioni,
    }


def stampa_studente_opzioni(request, pk):
    studente = get_object_or_404(
        Studente.objects.select_related("famiglia"),
        pk=pk,
    )
    _, can_print_osservazioni = get_studente_print_osservazioni(request, studente)
    anno_corrente = resolve_default_anno_scolastico(AnnoScolastico.objects.filter(attivo=True))

    return render(
        request,
        "anagrafica/studenti/studente_print_options.html",
        {
            "studente": studente,
            "anno_corrente": anno_corrente,
            "can_print_osservazioni": can_print_osservazioni,
        },
    )


def stampa_studente(request, pk):
    studente = get_object_or_404(
        Studente.objects.select_related(
            "famiglia",
            "famiglia__indirizzo_principale",
            "famiglia__indirizzo_principale__citta",
            "indirizzo",
            "indirizzo__citta",
            "luogo_nascita",
            "luogo_nascita__provincia",
            "nazione_nascita",
            "nazionalita",
        ),
        pk=pk,
    )

    include_dati_generali = request.GET.get("dati_generali") == "1"
    include_rate = request.GET.get("piano_rate") == "1"
    include_osservazioni = request.GET.get("osservazioni") == "1"
    if not any([include_dati_generali, include_rate, include_osservazioni]):
        include_dati_generali = True

    payload = get_studente_print_payload(
        request,
        studente,
        include_rate=include_rate,
        include_osservazioni=include_osservazioni,
    )

    return render(
        request,
        "anagrafica/studenti/studente_print.html",
        {
            "studente": studente,
            "print_date": timezone.localdate(),
            "include_dati_generali": include_dati_generali,
            "include_rate": include_rate,
            "include_osservazioni": include_osservazioni and payload["can_print_osservazioni"],
            **payload,
        },
    )


def elimina_studente(request, pk):
    studente = get_object_or_404(Studente, pk=pk)
    impact = get_record_documents_impact(studente)
    popup = is_popup_request(request)

    if request.method == "POST":
        object_id = studente.pk
        studente.delete()

        if popup:
            return popup_delete_response(request, "studente", object_id)

        messages.success(request, "Studente eliminato correttamente.")
        return redirect("lista_studenti")

    template_name = "anagrafica/studenti/studente_popup_delete.html" if popup else "anagrafica/studenti/studente_conferma_elimina.html"

    return render(
        request,
        template_name,
        {
            "studente": studente,
            "impact": impact,
            "popup": popup,
        },
    )

#FINE VIEWS PER GLI STUDENTI
