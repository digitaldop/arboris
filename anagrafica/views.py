from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal, ROUND_DOWN, ROUND_HALF_UP
from django.utils import timezone

from .utils import citta_choice_label
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
    Indirizzo,
    Famiglia,
    StatoRelazioneFamiglia,
    RelazioneFamiliare,
    TipoDocumento,
    Studente,
    Documento,
    Familiare,
)
from economia.models import Iscrizione, PrestazioneScambioRetta, RataIscrizione
from economia.scambio_retta_helpers import build_familiare_scambio_retta_inline_context
from calendario.data import build_dashboard_calendar_data
from sistema.models import Scuola, SistemaImpostazioniGenerali
from scuola.models import AnnoScolastico, Classe
from django.forms import modelform_factory

from django.db import transaction
from django.db.models import Count, Q, Sum

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


def resolve_current_school_year():
    oggi = timezone.localdate()

    anno_corrente = AnnoScolastico.objects.filter(corrente=True).order_by("-data_inizio").first()
    if anno_corrente:
        return anno_corrente, anno_corrente.nome_anno_scolastico

    anno_corrente = (
        AnnoScolastico.objects.filter(data_inizio__lte=oggi, data_fine__gte=oggi)
        .order_by("-data_inizio")
        .first()
    )
    if anno_corrente:
        return anno_corrente, anno_corrente.nome_anno_scolastico

    anno_inizio = oggi.year if oggi.month >= 9 else oggi.year - 1
    anno_fine = anno_inizio + 1
    return None, f"{anno_inizio}/{anno_fine}"


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


def distribute_dashboard_amount(total_amount, parts):
    total_amount = total_amount or Decimal("0.00")

    if parts <= 0:
        return []

    if total_amount <= 0:
        return [Decimal("0.00") for _ in range(parts)]

    importo_base = (total_amount / parts).quantize(Decimal("0.01"), rounding=ROUND_DOWN)
    importo_residuo = total_amount - (importo_base * parts)
    importi = [importo_base for _ in range(parts)]
    importi[-1] += importo_residuo
    return importi


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
                "importo_finale": item["importo_finale"] or Decimal("0.00"),
                "importo_incassato": Decimal("0.00"),
            }
            for item in iscrizione.build_rate_plan()
        ]

    tariffa = iscrizione.get_tariffa_applicabile() if not iscrizione.non_pagante else None
    totale_lordo_annuo = tariffa.retta_annuale if tariffa else Decimal("0.00")
    importo_preiscrizione = iscrizione.get_importo_preiscrizione_dovuto()
    righe_mensili = [row for row in rate_rows if row["tipo_rata"] == RataIscrizione.TIPO_MENSILE]
    importi_lordi_mensili = distribute_dashboard_amount(totale_lordo_annuo, len(righe_mensili))

    dashboard_rows = []
    indice_mensile = 0
    for index, rate_row in enumerate(rate_rows):
        importo_finale = rate_row["importo_finale"] or Decimal("0.00")
        importo_incassato = rate_row["importo_incassato"] or Decimal("0.00")
        if rate_row["tipo_rata"] == RataIscrizione.TIPO_PREISCRIZIONE:
            importo_totale = importo_preiscrizione
        else:
            importo_totale = (
                importi_lordi_mensili[indice_mensile]
                if indice_mensile < len(importi_lordi_mensili)
                else Decimal("0.00")
            )
            indice_mensile += 1
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


def build_studente_rate_overview(studente):
    overview = []

    iscrizioni = (
        studente.iscrizioni.select_related(
            "anno_scolastico",
            "classe",
            "stato_iscrizione",
            "condizione_iscrizione",
            "agevolazione",
        )
        .prefetch_related("rate")
        .order_by("-anno_scolastico__data_inizio", "-id")
    )

    for iscrizione in iscrizioni:
        if (
            not getattr(iscrizione, "anno_scolastico_id", None)
            or not getattr(iscrizione, "stato_iscrizione_id", None)
            or not getattr(iscrizione, "condizione_iscrizione_id", None)
        ):
            continue

        tariffa = iscrizione.get_tariffa_applicabile()
        rate = list(iscrizione.rate.order_by("anno_riferimento", "mese_riferimento", "numero_rata", "id"))
        importo_preiscrizione = iscrizione.get_importo_preiscrizione_dovuto()

        if rate:
            months = [
                {
                    "label": rata.display_period_label,
                    "display_label": rata.display_label,
                    "is_preiscrizione": rata.is_preiscrizione,
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
            piano = iscrizione.build_rate_plan()
            months = [
                {
                    "label": (
                        item["descrizione"]
                        if item.get("tipo_rata") == RataIscrizione.TIPO_PREISCRIZIONE
                        else f"{MONTH_LABELS.get(item['mese_riferimento'], item['mese_riferimento'])} {item['anno_riferimento']}"
                    ),
                    "display_label": (
                        item["descrizione"]
                        if item.get("tipo_rata") == RataIscrizione.TIPO_PREISCRIZIONE
                        else f"Rata {item['numero_rata']}"
                    ),
                    "is_preiscrizione": item.get("tipo_rata") == RataIscrizione.TIPO_PREISCRIZIONE,
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

        monthly_months = [month for month in months if not month["is_preiscrizione"]]

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
                "numero_mensilita": max(iscrizione.condizione_iscrizione.numero_mensilita_default or 0, 1),
                "rata_standard": monthly_months[0]["importo_dovuto"] if monthly_months else None,
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
        Classe.objects.filter(anno_scolastico=anno_scolastico)
        .annotate(
            count_studenti=Count(
                "iscrizioni",
                filter=Q(iscrizioni__attiva=True),
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
        qs = qs.filter(nome__icontains=q)

    qs = qs.order_by("nome")[:20]

    results = []
    for c in qs:
        caps = list(
            c.cap_list.filter(attivo=True)
            .order_by("codice")
            .values("id", "codice")
        )

        prov = getattr(c, "provincia", None)
        results.append({
            "id": c.id,
            "nome": c.nome,
            "label": citta_choice_label(c),
            "codice_catastale": c.codice_catastale,
            "provincia_nome": getattr(prov, "nome", "") if prov is not None else "",
            "provincia_sigla": getattr(prov, "sigla", "") if prov is not None else "",
            "regione_nome": prov.regione.nome if prov and prov.regione else "",
            "caps": caps,
        })

    return JsonResponse({"results": results})

#FINE VIEWS DEGLI INDIRIZZI

#INIZIO VIEWS DELLE FAMIGLIE
def lista_famiglie(request):
    q = request.GET.get("q", "").strip()

    famiglie = (
        Famiglia.objects
        .select_related("stato_relazione_famiglia", "indirizzo_principale", "indirizzo_principale__citta")
        .order_by("cognome_famiglia")
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
            Q(studenti__codice_fiscale__icontains=q)
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
    if request.method == "POST":
        active_inline_tab = resolve_active_inline_tab(request, allowed_inline_targets, "familiari")
        prefer_initial_active_tab = should_prefer_initial_famiglia_tab(request, allowed_inline_targets)
        edit_scope, inline_target = resolve_inline_target(
            request,
            allowed_inline_targets,
        )
        form = FamigliaForm(request.POST)
        familiari_formset = (
            FamiliareFormSet(request.POST, prefix="familiari")
            if inline_target in (None, "familiari")
            else FamiliareFormSet(prefix="familiari")
        )
        studenti_formset = (
            StudenteFormSet(request.POST, prefix="studenti")
            if inline_target in (None, "studenti")
            else StudenteFormSet(prefix="studenti")
        )
        documenti_formset = (
            DocumentoFamigliaFormSet(request.POST, request.FILES, prefix="documenti")
            if inline_target in (None, "documenti")
            else DocumentoFamigliaFormSet(prefix="documenti")
        )

        form_is_valid = form.is_valid()
        familiari_is_valid = familiari_formset.is_valid() if inline_target in (None, "familiari") else True
        studenti_is_valid = studenti_formset.is_valid() if inline_target in (None, "studenti") else True
        documenti_is_valid = documenti_formset.is_valid() if inline_target in (None, "documenti") else True

        if form_is_valid and familiari_is_valid and studenti_is_valid and documenti_is_valid:
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

            if "_continue" in request.POST:
                messages.success(request, "Famiglia creata correttamente. Ora puoi continuare a modificarla.")
                return redirect(build_famiglia_redirect_url(famiglia.pk, active_inline_tab))

            if "_addanother" in request.POST:
                messages.success(request, "Famiglia creata correttamente. Puoi inserirne un'altra.")
                return redirect("crea_famiglia")

            messages.success(request, "Famiglia creata correttamente.")
            return redirect(f"{reverse('lista_famiglie')}?highlight={famiglia.pk}")
    else:
        active_inline_tab = resolve_active_inline_tab(request, allowed_inline_targets, "familiari")
        prefer_initial_active_tab = should_prefer_initial_famiglia_tab(request, allowed_inline_targets)
        form = FamigliaForm()
        familiari_formset = FamiliareFormSet(prefix="familiari")
        studenti_formset = StudenteFormSet(prefix="studenti")
        documenti_formset = DocumentoFamigliaFormSet(prefix="documenti")

    today = timezone.localdate()

    return render(
        request,
        "anagrafica/famiglie/famiglia_form.html",
        {
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
        },
    )


def modifica_famiglia(request, pk):
    allowed_inline_targets = {"familiari", "studenti", "documenti"}
    famiglia = get_object_or_404(Famiglia, pk=pk)
    edit_scope = "view"
    inline_target = "familiari"
    active_inline_tab = "familiari"
    prefer_initial_active_tab = False

    if request.method == "POST":
        active_inline_tab = resolve_active_inline_tab(request, allowed_inline_targets, "familiari")
        prefer_initial_active_tab = should_prefer_initial_famiglia_tab(request, allowed_inline_targets)
        edit_scope, inline_target = resolve_inline_target(
            request,
            allowed_inline_targets,
        )
        form = FamigliaForm(request.POST, instance=famiglia)
        familiari_formset = (
            FamiliareFormSet(request.POST, instance=famiglia, prefix="familiari")
            if inline_target in (None, "familiari")
            else FamiliareFormSet(instance=famiglia, prefix="familiari")
        )
        studenti_formset = (
            StudenteFormSet(request.POST, instance=famiglia, prefix="studenti")
            if inline_target in (None, "studenti")
            else StudenteFormSet(instance=famiglia, prefix="studenti")
        )
        documenti_formset = (
            DocumentoFamigliaFormSet(request.POST, request.FILES, instance=famiglia, prefix="documenti")
            if inline_target in (None, "documenti")
            else DocumentoFamigliaFormSet(instance=famiglia, prefix="documenti")
        )

        form_is_valid = form.is_valid()
        familiari_is_valid = familiari_formset.is_valid() if inline_target in (None, "familiari") else True
        studenti_is_valid = studenti_formset.is_valid() if inline_target in (None, "studenti") else True
        documenti_is_valid = documenti_formset.is_valid() if inline_target in (None, "documenti") else True

        if form_is_valid and familiari_is_valid and studenti_is_valid and documenti_is_valid:
            famiglia = form.save()
            if inline_target in (None, "familiari"):
                familiari_formset.save()
            if inline_target in (None, "studenti"):
                studenti_formset.save()
            if inline_target in (None, "documenti"):
                documenti_formset.save()

            if "_continue" in request.POST:
                messages.success(request, "Modifiche salvate correttamente.")
                return redirect(build_famiglia_redirect_url(famiglia.pk, active_inline_tab))

            if "_addanother" in request.POST:
                messages.success(request, "Modifiche salvate correttamente. Puoi inserire una nuova famiglia.")
                return redirect("crea_famiglia")

            messages.success(request, "Modifiche salvate correttamente.")
            return redirect(build_famiglia_redirect_url(famiglia.pk, active_inline_tab))
    else:
        active_inline_tab = resolve_active_inline_tab(request, allowed_inline_targets, "familiari")
        prefer_initial_active_tab = should_prefer_initial_famiglia_tab(request, allowed_inline_targets)
        form = FamigliaForm(instance=famiglia)
        familiari_formset = FamiliareFormSet(instance=famiglia, prefix="familiari")
        studenti_formset = StudenteFormSet(instance=famiglia, prefix="studenti")
        documenti_formset = DocumentoFamigliaFormSet(instance=famiglia, prefix="documenti")

    today = timezone.localdate()

    documenti_familiari = (
        Documento.objects
        .filter(familiare__famiglia=famiglia)
        .select_related("familiare", "tipo_documento")
        .order_by("familiare__cognome", "familiare__nome", "-data_caricamento", "-id")
    )

    documenti_studenti = (
        Documento.objects
        .filter(studente__famiglia=famiglia)
        .select_related("studente", "tipo_documento")
        .order_by("studente__cognome", "studente__nome", "-data_caricamento", "-id")
    )
    count_documenti_totali = (
        famiglia.documenti.count()
        + (documenti_familiari.count() if hasattr(documenti_familiari, "count") else 0)
        + (documenti_studenti.count() if hasattr(documenti_studenti, "count") else 0)
    )

    return render(
        request,
        "anagrafica/famiglie/famiglia_form.html",
        {
            "form": form,
            "famiglia": famiglia,
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
            "count_documenti_familiari": documenti_familiari.count() if hasattr(documenti_familiari, "count") else 0,
            "count_documenti_studenti": documenti_studenti.count() if hasattr(documenti_studenti, "count") else 0,
            "edit_scope": edit_scope,
            "inline_target": inline_target,
            "active_inline_tab": active_inline_tab,
            "prefer_initial_active_tab": prefer_initial_active_tab,
            "has_form_errors": bool(form.errors or familiari_formset.total_error_count() or studenti_formset.total_error_count() or documenti_formset.total_error_count()),
        },
    )


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
        .select_related("relazione_familiare", "indirizzo", "famiglia__indirizzo_principale")
        .order_by("cognome", "nome")
    )
    studenti = (
        famiglia.studenti
        .select_related("indirizzo", "famiglia__indirizzo_principale", "luogo_nascita")
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

#Views per la modifica rapida dello stato di relazione con la scuola, da usare nella lista famiglie
def popup_response(request, message="Operazione completata."):
    return render(request, "popup/popup_close.html", {"message": message})


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
            "famiglia__indirizzo_principale",
            "famiglia__indirizzo_principale__citta",
        )
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
            familiare = form.save()
            documenti_formset.instance = familiare
            documenti_formset.save()

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
            "figli": [],
            "count_figli": 0,
            "count_documenti": 0,
            "count_documenti_in_scadenza": 0,
            "count_documenti_scaduti": 0,
            "scambio_retta_inline_context": {"enabled": False, "sections": []},
            "scambio_retta_return_to": "",
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
            "famiglia__indirizzo_principale",
        ),
        pk=pk,
    )
    today = timezone.localdate()

    if request.method == "POST":
        form = FamiliareForm(request.POST, instance=familiare)
        documenti_formset = DocumentoFamiliareFormSet(
            request.POST,
            request.FILES,
            instance=familiare,
            prefix="documenti",
        )

        if form.is_valid() and documenti_formset.is_valid():
            familiare = form.save()
            documenti_formset.save()

            if "_continue" in request.POST:
                messages.success(request, "Modifiche salvate correttamente.")
                return redirect("modifica_familiare", pk=familiare.pk)

            if "_addanother" in request.POST:
                messages.success(request, "Modifiche salvate correttamente. Puoi inserire un nuovo familiare.")
                return redirect("crea_familiare")

            messages.success(request, "Modifiche salvate correttamente.")
            return redirect(f"{reverse('lista_familiari')}?highlight={familiare.pk}")
    else:
        form = FamiliareForm(instance=familiare)
        documenti_formset = DocumentoFamiliareFormSet(instance=familiare, prefix="documenti")

    figli = (
        familiare.famiglia.studenti
        .select_related("indirizzo", "famiglia__indirizzo_principale")
        .order_by("cognome", "nome")
    ) if familiare.famiglia_id else Studente.objects.none()
    scambio_retta_inline_context = build_familiare_scambio_retta_inline_context(familiare, request.GET)
    scambio_retta_return_to = f"{request.get_full_path()}#scambio-retta-inline"

    return render(
        request,
        "anagrafica/familiari/familiari_form.html",
        {
            "form": form,
            "familiare": familiare,
            "documenti_formset": documenti_formset,
            "figli": figli,
            "count_figli": figli.count() if hasattr(figli, "count") else 0,
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
        Studente.objects
        .select_related("famiglia", "indirizzo", "indirizzo__citta", "luogo_nascita", "luogo_nascita__provincia")
        .order_by("cognome", "nome")
    )

    if q:
        studenti = studenti.filter(
            Q(cognome__icontains=q) |
            Q(nome__icontains=q) |
            Q(codice_fiscale__icontains=q) |
            Q(luogo_nascita__nome__icontains=q) |
            Q(luogo_nascita__provincia__sigla__icontains=q) |
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
            IscrizioneStudenteFormSet(request.POST, prefix="iscrizioni")
            if inline_target in (None, "iscrizioni")
            else IscrizioneStudenteFormSet(prefix="iscrizioni")
        )
        documenti_formset = (
            DocumentoStudenteFormSet(request.POST, request.FILES, prefix="documenti")
            if inline_target in (None, "documenti")
            else DocumentoStudenteFormSet(prefix="documenti")
        )

        form_is_valid = form.is_valid()
        iscrizioni_is_valid = iscrizioni_formset.is_valid() if inline_target in (None, "iscrizioni") else True
        documenti_is_valid = documenti_formset.is_valid() if inline_target in (None, "documenti") else True

        if form_is_valid and iscrizioni_is_valid and documenti_is_valid:
            missing_rate_count = 0
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
        iscrizioni_formset = IscrizioneStudenteFormSet(prefix="iscrizioni")
        documenti_formset = DocumentoStudenteFormSet(prefix="documenti")

    return render(
        request,
        "anagrafica/studenti/studente_form.html",
        {
            "form": form,
            "iscrizioni_formset": iscrizioni_formset,
            "documenti_formset": documenti_formset,
            "classe_corrente_label": "",
            "edit_scope": edit_scope,
            "inline_target": inline_target,
            "count_iscrizioni": 0,
            "count_documenti": 0,
            "count_documenti_in_scadenza": 0,
            "count_documenti_scaduti": 0,
            "rate_overview": [],
        },
    )


def modifica_studente(request, pk):
    studente = get_object_or_404(
        Studente.objects.select_related("famiglia", "indirizzo", "luogo_nascita", "luogo_nascita__provincia"),
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

    if request.method == "POST":
        edit_scope, inline_target = resolve_inline_target(
            request,
            {"iscrizioni", "documenti"},
        )
        form = StudenteStandaloneForm(request.POST, instance=studente)
        iscrizioni_formset = (
            IscrizioneStudenteFormSet(request.POST, instance=studente, prefix="iscrizioni")
            if inline_target in (None, "iscrizioni")
            else IscrizioneStudenteFormSet(instance=studente, prefix="iscrizioni")
        )
        documenti_formset = (
            DocumentoStudenteFormSet(request.POST, request.FILES, instance=studente, prefix="documenti")
            if inline_target in (None, "documenti")
            else DocumentoStudenteFormSet(instance=studente, prefix="documenti")
        )

        form_is_valid = form.is_valid()
        iscrizioni_is_valid = iscrizioni_formset.is_valid() if inline_target in (None, "iscrizioni") else True
        documenti_is_valid = documenti_formset.is_valid() if inline_target in (None, "documenti") else True

        if form_is_valid and iscrizioni_is_valid and documenti_is_valid:
            missing_rate_count = 0
            with transaction.atomic():
                studente = form.save()
                if inline_target in (None, "iscrizioni"):
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

                if inline_target in (None, "documenti"):
                    documenti_formset.save()

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
        iscrizioni_formset = IscrizioneStudenteFormSet(instance=studente, prefix="iscrizioni")
        documenti_formset = DocumentoStudenteFormSet(instance=studente, prefix="documenti")

    iscrizione_corrente = (
        studente.iscrizioni.select_related("classe", "anno_scolastico")
        .filter(classe__isnull=False)
        .order_by("-attiva", "-anno_scolastico__data_inizio", "-pk")
        .first()
    )
    classe_corrente_label = str(iscrizione_corrente.classe) if iscrizione_corrente and iscrizione_corrente.classe else ""

    return render(
        request,
        "anagrafica/studenti/studente_form.html",
        {
            "form": form,
            "studente": studente,
            "iscrizioni_formset": iscrizioni_formset,
            "documenti_formset": documenti_formset,
            "classe_corrente_label": classe_corrente_label,
            "edit_scope": edit_scope,
            "inline_target": inline_target,
            "count_iscrizioni": studente.iscrizioni.count(),
            "count_documenti": studente.documenti.count(),
            "count_documenti_in_scadenza": studente.documenti.filter(
                scadenza__isnull=False,
                scadenza__gte=today,
                scadenza__lte=today + timedelta(days=30),
            ).count(),
            "count_documenti_scaduti": studente.documenti.filter(
                scadenza__isnull=False,
                scadenza__lt=today,
            ).count(),
            "rate_overview": build_studente_rate_overview(studente),
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
