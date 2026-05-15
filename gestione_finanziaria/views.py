import csv
import io
import json
import logging
import re
import secrets
import unicodedata
from calendar import monthrange
from datetime import date, datetime, time
from decimal import Decimal, InvalidOperation
from urllib.parse import urlencode

from django.contrib import messages
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Count, Min, Prefetch, Q, Sum
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from anagrafica.views import is_popup_request, popup_delete_response, popup_select_response
from scuola.models import AnnoScolastico
from sistema.models import LivelloPermesso
from sistema.permissions import user_has_module_permission, user_is_operational_admin

from .fatture_in_cloud import (
    FIC_SOURCE,
    FattureInCloudError,
    FattureInCloudClient,
    authorization_url,
    configured_oauth_redirect_uri,
    has_oauth_credentials,
    importa_documento_da_webhook,
    oauth_env_configured,
    sincronizza_fatture_in_cloud,
)
from .fatture_in_cloud_debug import payload_debug_report_json
from .forms import (
    CategoriaSpesaForm,
    CategoriaFinanziariaForm,
    ContoBancarioForm,
    DocumentoFornitoreForm,
    FattureInCloudConnessioneForm,
    FornitoreForm,
    ImportEstrattoContoForm,
    ImportSaldiContoCsvForm,
    MovimentoFinanziarioForm,
    NuovaConnessioneBancariaForm,
    PagamentoFornitoreForm,
    PianoRatealeSpesaForm,
    PianificazioneSincronizzazioneForm,
    PuliziaMovimentiFinanziariForm,
    ProviderBancarioForm,
    ProviderPsd2ConfigForm,
    RegolaCategorizzazioneForm,
    SaldoContoForm,
    ScadenzaPagamentoFornitoreCreateFormSet,
    ScadenzaPagamentoFornitoreFormSet,
    SpesaOperativaForm,
    VoceBudgetRicorrenteForm,
    movimenti_fornitore_recenti_ids,
)
from gestione_amministrativa.models import BustaPagaDipendente
from .importers import (
    Camt053Parser,
    CsvImporter,
    CsvImporterConfig,
    ExcelImporter,
    detect_csv_import_config,
    detect_excel_import_config,
    is_probable_excel_file,
)
from .importers.service import importa_movimenti_da_file
from .models import (
    CategoriaFinanziaria,
    CanaleMovimento,
    ConnessioneBancaria,
    ContoBancario,
    DocumentoFornitore,
    EsitoSincronizzazione,
    FattureInCloudConnessione,
    FattureInCloudSyncLog,
    FonteSaldo,
    Fornitore,
    MovimentoFinanziario,
    MetodoPagamentoFornitore,
    NotificaFinanziaria,
    NotificaFinanziariaLettura,
    PagamentoFornitore,
    PianoRatealeSpesa,
    OrigineMovimento,
    ProviderBancario,
    RegolaCategorizzazione,
    SaldoConto,
    ScadenzaPagamentoFornitore,
    SincronizzazioneLog,
    SpesaOperativa,
    StatoConnessioneBancaria,
    StatoConnessioneFattureInCloud,
    StatoDocumentoFornitore,
    StatoScadenzaFornitore,
    StatoRiconciliazione,
    TipoCategoriaFinanziaria,
    TipoPianoRatealeSpesa,
    TipoSpesaOperativa,
    TipoProviderBancario,
    VoceBudgetRicorrente,
)
from .providers import (
    adapter_for_provider,
    is_enablebanking_adapter,
    is_oauth_adapter,
    is_redirect_callback_adapter,
    is_saltedge_adapter,
)
from .providers.enablebanking import EnableBankingAdapter, EnableBankingError
from .providers.registry import (
    ADAPTER_SALTEDGE,
    ADAPTER_TRUELAYER,
    ProviderConfigurazioneMancante,
    _adapter_id,
    configurazione_completa,
)
from .providers.saltedge import SaltEdgeAdapter, SaltEdgeError
from .providers.truelayer import TrueLayerAdapter, TrueLayerError
from .security import cifra_testo, decifra_testo_safe
from .scheduler import (
    get_or_create_singleton,
    maybe_run_scheduled_sync,
    prossima_esecuzione_prevista,
)
from .services import (
    aggiorna_stato_riconciliazione_movimento,
    annulla_riconciliazione,
    annulla_pagamento_fornitore,
    anteprima_riconcilia_fornitori_automaticamente,
    applica_anteprima_riconciliazione_fornitori,
    applica_regole_a_movimento,
    aggiorna_stato_documento_da_scadenze as service_aggiorna_stato_documento_da_scadenze,
    build_budgeting_dashboard_data,
    calcola_saldo_conto_alla_data,
    calcola_hash_deduplica_movimento,
    importo_movimento_disponibile_fornitori,
    importo_scadenza_fornitore_residuo,
    ricalcola_saldo_corrente_conto,
    riconcilia_fornitori_automaticamente,
    riconcilia_movimento_con_scadenza_fornitore,
    riconcilia_movimento_con_rata,
    registra_pagamento_fornitore,
    sincronizza_conto_psd2,
    trova_movimenti_candidati_per_scadenza_fornitore,
    trova_scadenze_fornitori_candidate,
    trova_rate_candidate,
)

logger = logging.getLogger(__name__)
RICONCILIAZIONE_FORNITORI_PREVIEW_SESSION_KEY = "gestione_finanziaria_riconciliazione_fornitori_preview"


def _oauth_redirect_uri(request, provider):
    """
    Ritorna il ``redirect_uri`` da usare nelle chiamate OAuth2 al provider.

    Preferisce il valore configurato su ``ProviderBancario.configurazione
    ['redirect_uri']`` (quello registrato nella console dello sviluppatore).
    Altrimenti calcola l'URL della view ``callback_oauth_psd2`` dall'host
    della richiesta corrente.

    IMPORTANTE: deve essere lo stesso valore sia quando si genera l'auth URL
    sia quando si scambia il code per i token.
    """
    cfg = (provider.configurazione or {}) if provider else {}
    override = (cfg.get("redirect_uri") or "").strip()
    if override:
        return override
    return request.build_absolute_uri(reverse("callback_oauth_psd2"))


# =========================================================================
#  Dashboard del modulo
# =========================================================================


def dashboard_gestione_finanziaria(request):
    conti = list(ContoBancario.objects.filter(attivo=True).order_by("nome_conto"))
    saldo_totale = Decimal("0")
    saldo_per_tipo_map = {}
    for conto in conti:
        conto.saldo_calcolato = calcola_saldo_conto_alla_data(conto)
        saldo_totale += conto.saldo_calcolato
        tipo_label = conto.get_tipo_conto_display()
        saldo_per_tipo_map[tipo_label] = saldo_per_tipo_map.get(tipo_label, Decimal("0")) + conto.saldo_calcolato

    saldo_per_tipo = [
        {"tipo": tipo, "saldo": saldo}
        for tipo, saldo in sorted(saldo_per_tipo_map.items(), key=lambda item: item[0])
    ]

    ultimi_movimenti = (
        MovimentoFinanziario.objects.select_related("conto", "categoria")
        .order_by("-data_contabile", "-id")[:15]
    )
    movimenti_senza_categoria = MovimentoFinanziario.objects.filter(categoria__isnull=True).count()
    categorie_attive = CategoriaFinanziaria.objects.filter(attiva=True).count()
    regole_attive = RegolaCategorizzazione.objects.filter(attiva=True).count()
    fornitori_attivi = Fornitore.objects.filter(attivo=True).count()
    scadenze_fornitori_aperte = ScadenzaPagamentoFornitore.objects.exclude(
        stato__in=[StatoScadenzaFornitore.PAGATA, StatoScadenzaFornitore.ANNULLATA]
    ).count()
    scadenze_fornitori_scadute = ScadenzaPagamentoFornitore.objects.exclude(
        stato__in=[StatoScadenzaFornitore.PAGATA, StatoScadenzaFornitore.ANNULLATA]
    ).filter(data_scadenza__lt=timezone.localdate()).count()
    fatture_in_cloud_attive = FattureInCloudConnessione.objects.filter(attiva=True).count()

    return render(
        request,
        "gestione_finanziaria/dashboard.html",
        {
            "conti": conti,
            "saldo_totale": saldo_totale,
            "saldo_per_tipo": saldo_per_tipo,
            "ultimi_movimenti": ultimi_movimenti,
            "movimenti_senza_categoria": movimenti_senza_categoria,
            "categorie_attive": categorie_attive,
            "regole_attive": regole_attive,
            "fornitori_attivi": fornitori_attivi,
            "scadenze_fornitori_aperte": scadenze_fornitori_aperte,
            "scadenze_fornitori_scadute": scadenze_fornitori_scadute,
            "fatture_in_cloud_attive": fatture_in_cloud_attive,
        },
    )


# =========================================================================
#  Budgeting
# =========================================================================


def budgeting_dashboard(request):
    period_type = request.GET.get("periodo") or "anno_scolastico"
    budget_data = build_budgeting_dashboard_data(period_type=period_type)
    voci_budget = (
        VoceBudgetRicorrente.objects.select_related("categoria", "fornitore")
        .order_by("tipo", "categoria__nome", "nome")
    )
    return render(
        request,
        "gestione_finanziaria/budgeting_dashboard.html",
        {
            "budget_data": budget_data,
            "voci_budget": voci_budget,
            "periodo_corrente": budget_data["period"]["type"],
        },
    )


def crea_voce_budget(request):
    popup = is_popup_request(request)
    if request.method == "POST":
        form = VoceBudgetRicorrenteForm(request.POST)
        if form.is_valid():
            form.save()
            if popup:
                return render(
                    request,
                    "popup/popup_close.html",
                    {"message": "Voce di budget creata correttamente."},
                )
            messages.success(request, "Voce di budget creata correttamente.")
            return redirect("budgeting_dashboard")
    else:
        form = VoceBudgetRicorrenteForm(initial={"data_inizio": timezone.localdate(), "attiva": True})

    return render(
        request,
        "gestione_finanziaria/voce_budget_form.html",
        {"form": form, "voce": None, "popup": popup},
    )


def modifica_voce_budget(request, pk):
    voce = get_object_or_404(VoceBudgetRicorrente, pk=pk)
    popup = is_popup_request(request)
    if request.method == "POST":
        form = VoceBudgetRicorrenteForm(request.POST, instance=voce)
        if form.is_valid():
            form.save()
            if popup:
                return render(
                    request,
                    "popup/popup_close.html",
                    {"message": "Voce di budget aggiornata correttamente."},
                )
            messages.success(request, "Voce di budget aggiornata correttamente.")
            return redirect("budgeting_dashboard")
    else:
        form = VoceBudgetRicorrenteForm(instance=voce)

    return render(
        request,
        "gestione_finanziaria/voce_budget_form.html",
        {"form": form, "voce": voce, "popup": popup},
    )


def elimina_voce_budget(request, pk):
    voce = get_object_or_404(VoceBudgetRicorrente, pk=pk)
    if request.method == "POST":
        voce.delete()
        messages.success(request, "Voce di budget eliminata correttamente.")
        return redirect("budgeting_dashboard")

    return render(
        request,
        "gestione_finanziaria/voce_budget_confirm_delete.html",
        {"voce": voce},
    )


@require_POST
def toggle_voce_budget(request, pk):
    voce = get_object_or_404(VoceBudgetRicorrente, pk=pk)
    raw_value = (request.POST.get("attiva") or "").lower()
    voce.attiva = raw_value in {"1", "true", "on", "yes", "si"}
    voce.save(update_fields=["attiva", "data_aggiornamento"])

    if request.headers.get("x-requested-with") == "XMLHttpRequest" or request.POST.get("ajax") == "1":
        return JsonResponse({"ok": True, "attiva": voce.attiva})

    next_url = request.POST.get("next") or reverse("budgeting_dashboard")
    if url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
        return redirect(next_url)
    return redirect("budgeting_dashboard")


# =========================================================================
#  Fornitori, categorie spesa e documenti passivi
# =========================================================================


def _aggiorna_stato_documento_da_scadenze(documento):
    return service_aggiorna_stato_documento_da_scadenze(documento)


def _popup_target_input_name(request):
    return request.GET.get("target_input_name") or request.POST.get("target_input_name", "")


def _categoria_spesa_template(popup, action):
    if not popup:
        if action == "form":
            return "gestione_finanziaria/categoria_spesa_form.html"
        return "gestione_finanziaria/categoria_spesa_confirm_delete.html"
    if action == "form":
        return "gestione_finanziaria/categoria_spesa_popup_form.html"
    return "gestione_finanziaria/categoria_spesa_popup_delete.html"


def _categorie_spesa_queryset(*, attive_solo=False):
    queryset = CategoriaFinanziaria.objects.filter(tipo=TipoCategoriaFinanziaria.SPESA)
    if attive_solo:
        queryset = queryset.filter(attiva=True)
    return queryset.order_by("parent__nome", "ordine", "nome")


def _generic_popup_form_context(request, form, title):
    return {
        "form": form,
        "popup_title": title,
        "target_input_name": _popup_target_input_name(request),
    }


def _generic_popup_delete_context(request, title, object_label, ha_vincoli=False, vincoli_message=""):
    return {
        "popup_title": title,
        "object_label": object_label,
        "ha_vincoli": ha_vincoli,
        "vincoli_message": vincoli_message,
        "target_input_name": _popup_target_input_name(request),
    }


def lista_categorie_spesa(request):
    categorie = list(
        _categorie_spesa_queryset()
        .select_related("parent")
        .annotate(
            numero_fornitori=Count("fornitori", distinct=True),
            numero_documenti=Count("documenti_fornitori", distinct=True),
            numero_movimenti=Count("movimenti", distinct=True),
        )
        .order_by("ordine", "nome", "id")
    )
    figli_by_parent = {}
    for categoria in categorie:
        figli_by_parent.setdefault(categoria.parent_id, []).append(categoria)

    def build_node(categoria, livello=0):
        figli = [
            build_node(figlia, livello + 1)
            for figlia in figli_by_parent.get(categoria.pk, [])
        ]
        discendenti_count = sum(1 + figlia["discendenti_count"] for figlia in figli)
        return {
            "categoria": categoria,
            "figli": figli,
            "livello": livello,
            "row_id": f"categoria-spesa-{categoria.pk}",
            "discendenti_count": discendenti_count,
        }

    categorie_tree = [
        build_node(categoria)
        for categoria in figli_by_parent.get(None, [])
    ]
    return render(
        request,
        "gestione_finanziaria/categorie_spesa_list.html",
        {"categorie": categorie, "categorie_tree": categorie_tree},
    )


def crea_categoria_spesa(request):
    popup = is_popup_request(request)
    if request.method == "POST":
        form = CategoriaSpesaForm(request.POST)
        if form.is_valid():
            categoria = form.save()
            if popup:
                return popup_select_response(request, "categoria_spesa", categoria.pk, str(categoria))
            messages.success(request, "Categoria spesa creata correttamente.")
            return redirect("lista_categorie_spesa")
    else:
        form = CategoriaSpesaForm(initial={"attiva": True})

    return render(
        request,
        _categoria_spesa_template(popup, "form"),
        {
            "form": form,
            "categoria": None,
            "popup": popup,
            "target_input_name": _popup_target_input_name(request),
        },
    )


def modifica_categoria_spesa(request, pk):
    popup = is_popup_request(request)
    categoria = get_object_or_404(_categorie_spesa_queryset(), pk=pk)
    if request.method == "POST":
        form = CategoriaSpesaForm(request.POST, instance=categoria)
        if form.is_valid():
            categoria = form.save()
            if popup:
                return popup_select_response(request, "categoria_spesa", categoria.pk, str(categoria))
            messages.success(request, "Categoria spesa aggiornata correttamente.")
            return redirect("lista_categorie_spesa")
    else:
        form = CategoriaSpesaForm(instance=categoria)

    return render(
        request,
        _categoria_spesa_template(popup, "form"),
        {
            "form": form,
            "categoria": categoria,
            "popup": popup,
            "target_input_name": _popup_target_input_name(request),
        },
    )


def elimina_categoria_spesa(request, pk):
    popup = is_popup_request(request)
    categoria = get_object_or_404(_categorie_spesa_queryset(), pk=pk)
    count_fornitori = categoria.fornitori.count()
    count_documenti = categoria.documenti_fornitori.count()
    count_movimenti = categoria.movimenti.count()
    count_regole = categoria.regole.count()
    count_figlie = categoria.figli.count()
    ha_vincoli = bool(count_fornitori or count_documenti or count_movimenti or count_regole or count_figlie)

    if request.method == "POST":
        if ha_vincoli:
            if popup:
                return render(
                    request,
                    "gestione_finanziaria/categoria_spesa_popup_delete.html",
                    {
                        "categoria": categoria,
                        "count_fornitori": count_fornitori,
                        "count_documenti": count_documenti,
                        "count_movimenti": count_movimenti,
                        "count_regole": count_regole,
                        "count_figlie": count_figlie,
                        "ha_vincoli": ha_vincoli,
                        "target_input_name": _popup_target_input_name(request),
                    },
                )
            messages.error(
                request,
                "Impossibile eliminare la categoria: e' collegata a fornitori, documenti o movimenti. "
                "Puoi disattivarla invece di eliminarla.",
            )
            return redirect("lista_categorie_spesa")
        object_id = categoria.pk
        categoria.delete()
        if popup:
            return popup_delete_response(request, "categoria_spesa", object_id)
        messages.success(request, "Categoria spesa eliminata correttamente.")
        return redirect("lista_categorie_spesa")

    return render(
        request,
        _categoria_spesa_template(popup, "delete"),
        {
            "categoria": categoria,
            "count_fornitori": count_fornitori,
            "count_documenti": count_documenti,
            "count_movimenti": count_movimenti,
            "count_regole": count_regole,
            "count_figlie": count_figlie,
            "ha_vincoli": ha_vincoli,
            "popup": popup,
            "target_input_name": _popup_target_input_name(request),
        },
    )


def lista_fornitori(request):
    q = (request.GET.get("q") or "").strip()
    categoria_id = request.GET.get("categoria") or ""
    stato = request.GET.get("stato") or ""

    fornitori = (
        Fornitore.objects.select_related("categoria_spesa")
        .annotate(numero_documenti=Count("documenti", distinct=True))
        .order_by("denominazione")
    )
    if q:
        fornitori = fornitori.filter(
            Q(denominazione__icontains=q)
            | Q(codice_fiscale__icontains=q)
            | Q(partita_iva__icontains=q)
            | Q(email__icontains=q)
            | Q(pec__icontains=q)
            | Q(referente__icontains=q)
        )
    if categoria_id.isdigit():
        fornitori = fornitori.filter(categoria_spesa_id=int(categoria_id))
    if stato == "attivi":
        fornitori = fornitori.filter(attivo=True)
    elif stato == "non_attivi":
        fornitori = fornitori.filter(attivo=False)

    return render(
        request,
        "gestione_finanziaria/fornitori_list.html",
        {
            "fornitori": fornitori,
            "categorie": _categorie_spesa_queryset(attive_solo=True),
            "q": q,
            "categoria_selezionata": categoria_id,
            "stato": stato,
        },
    )


def crea_fornitore(request):
    popup = is_popup_request(request)
    if request.method == "POST":
        form = FornitoreForm(request.POST)
        if form.is_valid():
            fornitore = form.save()
            if popup:
                return popup_select_response(request, "fornitore", fornitore.pk, str(fornitore))
            messages.success(request, "Fornitore creato correttamente.")
            return redirect("modifica_fornitore", pk=fornitore.pk)
    else:
        form = FornitoreForm(initial={"attivo": True})

    if popup:
        return render(
            request,
            "gestione_finanziaria/entity_popup_form.html",
            _generic_popup_form_context(request, form, "Nuovo fornitore"),
        )

    return render(
        request,
        "gestione_finanziaria/fornitore_form.html",
        {"form": form, "fornitore": None, "edit_scope": "full"},
    )


def modifica_fornitore(request, pk):
    popup = is_popup_request(request)
    fornitore = get_object_or_404(Fornitore.objects.select_related("categoria_spesa"), pk=pk)
    edit_scope = "view"
    if request.method == "POST":
        form = FornitoreForm(request.POST, instance=fornitore)
        if form.is_valid():
            fornitore = form.save()
            if popup:
                return popup_select_response(request, "fornitore", fornitore.pk, str(fornitore))
            messages.success(request, "Fornitore aggiornato correttamente.")
            return redirect("modifica_fornitore", pk=fornitore.pk)
        edit_scope = "full"
    else:
        form = FornitoreForm(instance=fornitore)

    if popup:
        return render(
            request,
            "gestione_finanziaria/entity_popup_form.html",
            _generic_popup_form_context(request, form, f"Fornitore {fornitore.denominazione}"),
        )

    documenti = (
        fornitore.documenti.select_related("categoria_spesa")
        .prefetch_related("scadenze")
        .order_by("-data_documento", "-id")[:20]
    )
    scadenze_aperte = (
        ScadenzaPagamentoFornitore.objects.select_related("documento")
        .filter(documento__fornitore=fornitore)
        .exclude(stato__in=[StatoScadenzaFornitore.PAGATA, StatoScadenzaFornitore.ANNULLATA])
        .order_by("data_scadenza", "id")[:20]
    )

    return render(
        request,
        "gestione_finanziaria/fornitore_form.html",
        {
            "form": form,
            "fornitore": fornitore,
            "documenti": documenti,
            "scadenze_aperte": scadenze_aperte,
            "edit_scope": edit_scope,
        },
    )


def elimina_fornitore(request, pk):
    popup = is_popup_request(request)
    fornitore = get_object_or_404(Fornitore, pk=pk)
    count_documenti = fornitore.documenti.count()
    ha_vincoli = bool(count_documenti)

    if request.method == "POST":
        if ha_vincoli:
            if popup:
                return render(
                    request,
                    "gestione_finanziaria/entity_popup_delete.html",
                    _generic_popup_delete_context(
                        request,
                        "Elimina fornitore",
                        str(fornitore),
                        True,
                        "Questo fornitore ha documenti collegati: puoi disattivarlo invece di eliminarlo.",
                    ),
                )
            messages.error(
                request,
                "Impossibile eliminare il fornitore: ha documenti collegati. Puoi disattivarlo.",
            )
            return redirect("lista_fornitori")
        object_id = fornitore.pk
        fornitore.delete()
        if popup:
            return popup_delete_response(request, "fornitore", object_id)
        messages.success(request, "Fornitore eliminato correttamente.")
        return redirect("lista_fornitori")

    if popup:
        return render(
            request,
            "gestione_finanziaria/entity_popup_delete.html",
            _generic_popup_delete_context(
                request,
                "Elimina fornitore",
                str(fornitore),
                ha_vincoli,
                "Questo fornitore ha documenti collegati: puoi disattivarlo invece di eliminarlo.",
            ),
        )

    return render(
        request,
        "gestione_finanziaria/fornitore_confirm_delete.html",
        {"fornitore": fornitore, "count_documenti": count_documenti, "ha_vincoli": ha_vincoli},
    )


def lista_documenti_fornitori(request):
    q = (request.GET.get("q") or "").strip()
    fornitore_id = request.GET.get("fornitore") or ""
    categoria_id = request.GET.get("categoria") or ""
    stato = request.GET.get("stato") or ""

    documenti = (
        DocumentoFornitore.objects.select_related("fornitore", "fornitore__categoria_spesa", "categoria_spesa")
        .annotate(data_scadenza_prima=Min("scadenze__data_scadenza"))
        .prefetch_related("scadenze")
        .order_by("-data_documento", "-id")
    )
    if q:
        documenti = documenti.filter(
            Q(numero_documento__icontains=q)
            | Q(descrizione__icontains=q)
            | Q(fornitore__denominazione__icontains=q)
        )
    if fornitore_id.isdigit():
        documenti = documenti.filter(fornitore_id=int(fornitore_id))
    if categoria_id.isdigit():
        categoria_pk = int(categoria_id)
        documenti = documenti.filter(
            Q(categoria_spesa_id=categoria_pk)
            | Q(categoria_spesa__isnull=True, fornitore__categoria_spesa_id=categoria_pk)
        )
    if stato:
        documenti = documenti.filter(stato=stato)

    documenti = list(documenti)
    stati_non_saldati = {
        StatoDocumentoFornitore.DA_PAGARE,
        StatoDocumentoFornitore.PARZIALMENTE_PAGATO,
    }
    totale_documenti_non_saldati = Decimal("0.00")
    numero_documenti_non_saldati = 0
    for documento in documenti:
        if documento.stato not in stati_non_saldati:
            continue
        numero_documenti_non_saldati += 1
        importo_pagato = sum(
            (scadenza.importo_pagato or Decimal("0.00") for scadenza in documento.scadenze.all()),
            Decimal("0.00"),
        )
        residuo = (documento.totale or Decimal("0.00")) - importo_pagato
        totale_documenti_non_saldati += max(residuo, Decimal("0.00"))

    return render(
        request,
        "gestione_finanziaria/documenti_fornitori_list.html",
        {
            "documenti": documenti,
            "totale_documenti_non_saldati": totale_documenti_non_saldati,
            "numero_documenti_non_saldati": numero_documenti_non_saldati,
            "fornitori": Fornitore.objects.filter(attivo=True).order_by("denominazione"),
            "categorie": _categorie_spesa_queryset(attive_solo=True),
            "stati": StatoDocumentoFornitore.choices,
            "q": q,
            "fornitore_selezionato": fornitore_id,
            "categoria_selezionata": categoria_id,
            "stato": stato,
        },
    )


def _scadenza_documento_da_collegare(documento):
    if not documento:
        return None

    stati_chiusi = {StatoScadenzaFornitore.PAGATA, StatoScadenzaFornitore.ANNULLATA}
    for scadenza in documento.scadenze.all():
        if scadenza.stato not in stati_chiusi and scadenza.importo_residuo > Decimal("0.00"):
            return scadenza
    return None


def _documento_form_context(form, formset, documento, popup=False):
    return {
        "form": form,
        "formset": formset,
        "documento": documento,
        "popup": popup,
        "scadenza_collegamento_movimento": _scadenza_documento_da_collegare(documento),
    }


def _documento_fornitore_scadenze_queryset():
    return ScadenzaPagamentoFornitore.objects.select_related("conto_bancario", "movimento_finanziario").order_by(
        "data_scadenza",
        "id",
    )


def _documento_fornitore_pagamenti_queryset():
    return PagamentoFornitore.objects.select_related("movimento_finanziario", "conto_bancario").order_by(
        "data_pagamento",
        "id",
    )


def _documento_fornitore_detail_queryset():
    return DocumentoFornitore.objects.select_related(
        "fornitore",
        "fornitore__categoria_spesa",
        "categoria_spesa",
    ).prefetch_related(
        Prefetch(
            "scadenze",
            queryset=_documento_fornitore_scadenze_queryset().prefetch_related(
                Prefetch("pagamenti", queryset=_documento_fornitore_pagamenti_queryset())
            ),
        )
    )


def _documento_fornitore_formset_kwargs(documento=None, compact_movimenti=False):
    kwargs = {}
    if compact_movimenti:
        kwargs["form_kwargs"] = {"movimento_choices_ids": movimenti_fornitore_recenti_ids()}
    if documento and documento.pk:
        kwargs["queryset"] = _documento_fornitore_scadenze_queryset().filter(documento=documento)
    return kwargs


def _documento_fornitore_formset_class(documento=None):
    if documento and documento.pk:
        return ScadenzaPagamentoFornitoreFormSet
    return ScadenzaPagamentoFornitoreCreateFormSet


def crea_documento_fornitore(request):
    popup = is_popup_request(request)
    if request.method == "POST":
        form = DocumentoFornitoreForm(request.POST, request.FILES)
        formset = _documento_fornitore_formset_class()(
            request.POST,
            instance=DocumentoFornitore(),
            **_documento_fornitore_formset_kwargs(compact_movimenti=popup),
        )
        if form.is_valid() and formset.is_valid():
            documento = form.save()
            formset.instance = documento
            formset.save()
            _aggiorna_stato_documento_da_scadenze(documento)
            messages.success(request, "Fattura fornitore creata correttamente.")
            if popup:
                return render(
                    request,
                    "popup/popup_close.html",
                    {"message": "Fattura fornitore creata correttamente."},
                )
            return redirect("modifica_documento_fornitore", pk=documento.pk)
    else:
        initial = {
            "data_documento": timezone.localdate(),
            "data_ricezione": timezone.localdate(),
            "aliquota_iva": Decimal("22.00"),
        }
        fornitore_id = request.GET.get("fornitore")
        if fornitore_id and fornitore_id.isdigit():
            fornitore = Fornitore.objects.filter(pk=int(fornitore_id)).first()
            if fornitore:
                initial["fornitore"] = fornitore
                initial["categoria_spesa"] = fornitore.categoria_spesa
        form = DocumentoFornitoreForm(initial=initial)
        formset = _documento_fornitore_formset_class()(
            instance=DocumentoFornitore(),
            **_documento_fornitore_formset_kwargs(compact_movimenti=popup),
        )

    return render(
        request,
        "gestione_finanziaria/documento_fornitore_form.html",
        _documento_form_context(form, formset, None, popup=popup),
    )


def modifica_documento_fornitore(request, pk):
    popup = is_popup_request(request)
    documento = get_object_or_404(_documento_fornitore_detail_queryset(), pk=pk)
    if request.method == "POST":
        form = DocumentoFornitoreForm(request.POST, request.FILES, instance=documento)
        formset = _documento_fornitore_formset_class(documento)(
            request.POST,
            instance=documento,
            **_documento_fornitore_formset_kwargs(documento, compact_movimenti=popup),
        )
        if form.is_valid() and formset.is_valid():
            documento = form.save()
            formset.save()
            _aggiorna_stato_documento_da_scadenze(documento)
            messages.success(request, "Fattura fornitore aggiornata correttamente.")
            if popup:
                return render(
                    request,
                    "popup/popup_close.html",
                    {"message": "Fattura fornitore aggiornata correttamente."},
                )
            return redirect("modifica_documento_fornitore", pk=documento.pk)
    else:
        form = DocumentoFornitoreForm(instance=documento)
        formset = _documento_fornitore_formset_class(documento)(
            instance=documento,
            **_documento_fornitore_formset_kwargs(documento, compact_movimenti=popup),
        )

    return render(
        request,
        "gestione_finanziaria/documento_fornitore_form.html",
        _documento_form_context(form, formset, documento, popup=popup),
    )


def elimina_documento_fornitore(request, pk):
    documento = get_object_or_404(DocumentoFornitore.objects.select_related("fornitore"), pk=pk)
    if request.method == "POST":
        documento.delete()
        messages.success(request, "Fattura fornitore eliminata correttamente.")
        return redirect("lista_documenti_fornitori")

    return render(
        request,
        "gestione_finanziaria/documento_fornitore_confirm_delete.html",
        {"documento": documento},
    )


def _ids_selezionati_da_post(request):
    ids = []
    for raw_id in request.POST.getlist("selected_ids"):
        if str(raw_id).isdigit():
            ids.append(int(raw_id))
    return list(dict.fromkeys(ids))


def _safe_bulk_next_url(request, fallback_url_name):
    next_url = request.POST.get("next") or ""
    if next_url and url_has_allowed_host_and_scheme(
        next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return next_url
    return reverse(fallback_url_name)


def _safe_next_url(request, fallback_url_name):
    next_url = request.GET.get("next") or request.POST.get("next") or ""
    if next_url and url_has_allowed_host_and_scheme(
        next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return next_url
    return reverse(fallback_url_name)


def _safe_reload_url(request, fallback_url_name):
    reload_url = request.GET.get("reload_url") or request.POST.get("reload_url") or ""
    if reload_url and url_has_allowed_host_and_scheme(
        reload_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return reload_url
    return reverse(fallback_url_name)


def elimina_documenti_fornitori_multipla(request):
    if request.method != "POST":
        return redirect("lista_documenti_fornitori")

    next_url = _safe_bulk_next_url(request, "lista_documenti_fornitori")
    selected_ids = _ids_selezionati_da_post(request)
    if not selected_ids:
        messages.error(request, "Seleziona almeno una fattura fornitore da eliminare.")
        return redirect(next_url)

    queryset = (
        DocumentoFornitore.objects.select_related("fornitore", "categoria_spesa")
        .filter(pk__in=selected_ids)
        .order_by("-data_documento", "-id")
    )
    documenti = list(queryset)
    if not documenti:
        messages.error(request, "Le fatture selezionate non sono piu disponibili.")
        return redirect(next_url)

    if request.POST.get("conferma") == "1":
        count = len(documenti)
        with transaction.atomic():
            DocumentoFornitore.objects.filter(pk__in=[documento.pk for documento in documenti]).delete()
        messages.success(request, f"Eliminate {count} fatture fornitori selezionate.")
        return redirect(next_url)

    totale_documenti = sum(
        ((documento.totale or Decimal("0.00")) for documento in documenti),
        Decimal("0.00"),
    )
    scadenze_count = ScadenzaPagamentoFornitore.objects.filter(documento__in=documenti).count()
    pagamenti_count = PagamentoFornitore.objects.filter(scadenza__documento__in=documenti).count()

    return render(
        request,
        "gestione_finanziaria/documenti_fornitori_bulk_confirm_delete.html",
        {
            "documenti": documenti,
            "selected_ids": selected_ids,
            "next_url": next_url,
            "totale_documenti": totale_documenti,
            "scadenze_count": scadenze_count,
            "pagamenti_count": pagamenti_count,
        },
    )


def scadenziario_fornitori(request):
    stato = request.GET.get("stato") or "aperte"
    categoria_id = request.GET.get("categoria") or ""
    fornitore_id = request.GET.get("fornitore") or ""

    scadenze = (
        ScadenzaPagamentoFornitore.objects.select_related(
            "documento",
            "documento__fornitore",
            "documento__categoria_spesa",
            "conto_bancario",
            "movimento_finanziario",
        )
        .order_by("data_scadenza", "id")
    )
    if stato == "aperte":
        scadenze = scadenze.exclude(stato__in=[StatoScadenzaFornitore.PAGATA, StatoScadenzaFornitore.ANNULLATA])
    elif stato:
        scadenze = scadenze.filter(stato=stato)
    if categoria_id.isdigit():
        scadenze = scadenze.filter(documento__categoria_spesa_id=int(categoria_id))
    if fornitore_id.isdigit():
        scadenze = scadenze.filter(documento__fornitore_id=int(fornitore_id))

    totale_previsto = scadenze.aggregate(totale=Sum("importo_previsto"))["totale"] or Decimal("0.00")
    totale_pagato = scadenze.aggregate(totale=Sum("importo_pagato"))["totale"] or Decimal("0.00")

    return render(
        request,
        "gestione_finanziaria/scadenziario_fornitori.html",
        {
            "scadenze": scadenze,
            "totale_previsto": totale_previsto,
            "totale_pagato": totale_pagato,
            "totale_residuo": max(totale_previsto - totale_pagato, Decimal("0.00")),
            "stati": StatoScadenzaFornitore.choices,
            "stato": stato,
            "categorie": _categorie_spesa_queryset(attive_solo=True),
            "fornitori": Fornitore.objects.filter(attivo=True).order_by("denominazione"),
            "categoria_selezionata": categoria_id,
            "fornitore_selezionato": fornitore_id,
        },
    )


def fatture_scadenze_fornitori(request):
    q = (request.GET.get("q") or "").strip()
    stato = request.GET.get("stato") or ""
    vista = (request.GET.get("vista") or "tutte").strip()
    if vista not in {"tutte", "insolute"}:
        vista = "tutte"
    categoria_id = request.GET.get("categoria") or ""
    fornitore_id = request.GET.get("fornitore") or ""
    oggi = timezone.localdate()

    scadenze = (
        ScadenzaPagamentoFornitore.objects.select_related(
            "documento",
            "documento__fornitore",
            "documento__fornitore__categoria_spesa",
            "documento__categoria_spesa",
        )
        .exclude(stato=StatoScadenzaFornitore.ANNULLATA)
        .order_by("data_scadenza", "id")
    )
    if q:
        scadenze = scadenze.filter(
            Q(documento__numero_documento__icontains=q)
            | Q(documento__descrizione__icontains=q)
            | Q(documento__fornitore__denominazione__icontains=q)
        )
    if fornitore_id.isdigit():
        scadenze = scadenze.filter(documento__fornitore_id=int(fornitore_id))
    if categoria_id.isdigit():
        categoria_pk = int(categoria_id)
        scadenze = scadenze.filter(
            Q(documento__categoria_spesa_id=categoria_pk)
            | Q(documento__categoria_spesa__isnull=True, documento__fornitore__categoria_spesa_id=categoria_pk)
        )
    if stato == "pagata":
        scadenze = scadenze.filter(stato=StatoScadenzaFornitore.PAGATA)
    elif stato == "da_pagare":
        scadenze = scadenze.exclude(stato=StatoScadenzaFornitore.PAGATA)
    elif stato == "scaduta":
        scadenze = scadenze.exclude(stato=StatoScadenzaFornitore.PAGATA).filter(data_scadenza__lt=oggi)

    scadenze_tutte = list(scadenze)
    for scadenza in scadenze_tutte:
        scadenza.mostra_badge_scaduta = (
            scadenza.importo_residuo > Decimal("0.00")
            and scadenza.data_scadenza
            and scadenza.data_scadenza < oggi
        )

    totale_previsto = sum((scadenza.importo_previsto or Decimal("0.00") for scadenza in scadenze_tutte), Decimal("0.00"))
    totale_pagato = sum((scadenza.importo_pagato or Decimal("0.00") for scadenza in scadenze_tutte), Decimal("0.00"))
    totale_residuo = sum((scadenza.importo_residuo for scadenza in scadenze_tutte), Decimal("0.00"))
    scadenze_scadute_count = sum(1 for scadenza in scadenze_tutte if scadenza.mostra_badge_scaduta)

    scadenze = scadenze_tutte
    if vista == "insolute":
        scadenze = [scadenza for scadenza in scadenze if scadenza.importo_residuo > Decimal("0.00")]

    switch_params = {}
    if q:
        switch_params["q"] = q
    if fornitore_id:
        switch_params["fornitore"] = fornitore_id
    if categoria_id:
        switch_params["categoria"] = categoria_id

    def switch_url(vista_value):
        params = {**switch_params, "vista": vista_value}
        return f"{reverse('fatture_scadenze_fornitori')}?{urlencode(params)}"

    return render(
        request,
        "gestione_finanziaria/fatture_scadenze_fornitori.html",
        {
            "scadenze": scadenze,
            "totale_previsto": totale_previsto,
            "totale_pagato": totale_pagato,
            "totale_residuo": totale_residuo,
            "scadenze_scadute_count": scadenze_scadute_count,
            "q": q,
            "stato": stato,
            "vista": vista,
            "vista_tutte_url": switch_url("tutte"),
            "vista_insolute_url": switch_url("insolute"),
            "categorie": _categorie_spesa_queryset(attive_solo=True),
            "fornitori": Fornitore.objects.filter(attivo=True).order_by("denominazione"),
            "categoria_selezionata": categoria_id,
            "fornitore_selezionato": fornitore_id,
        },
    )


MESI_BREVI = ["Gen", "Feb", "Mar", "Apr", "Mag", "Giu", "Lug", "Ago", "Set", "Ott", "Nov", "Dic"]


def _first_day(value):
    return date(value.year, value.month, 1)


def _last_day(value):
    return date(value.year, value.month, monthrange(value.year, value.month)[1])


def _add_months(value, months, day=None):
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    target_day = day or value.day
    return date(year, month, min(target_day, monthrange(year, month)[1]))


def _month_key(value):
    return f"{value.year}-{value.month:02d}"


def _month_from_key(value, fallback):
    try:
        year, month = (int(part) for part in (value or "").split("-", 1))
        return date(year, month, 1)
    except (TypeError, ValueError):
        return fallback


def _periodo_spese_mensili(request):
    oggi = timezone.localdate()
    periodo = request.GET.get("periodo") or "solare"
    if periodo not in {"solare", "scolastico"}:
        periodo = "solare"

    anni_scolastici = list(AnnoScolastico.objects.filter(attivo=True).order_by("-data_inizio", "-id"))
    anno_scolastico = None
    anno_scolastico_id = request.GET.get("anno_scolastico") or ""
    if anno_scolastico_id.isdigit():
        anno_scolastico = next((anno for anno in anni_scolastici if anno.pk == int(anno_scolastico_id)), None)
    if anno_scolastico is None:
        anno_scolastico = next((anno for anno in anni_scolastici if anno.is_corrente), None)
    if anno_scolastico is None and anni_scolastici:
        anno_scolastico = anni_scolastici[0]

    anno_raw = request.GET.get("anno") or str(oggi.year)
    anno = int(anno_raw) if str(anno_raw).isdigit() else oggi.year
    anni_solari = list(range(oggi.year - 3, oggi.year + 4))
    if anno not in anni_solari:
        anni_solari.append(anno)
        anni_solari.sort()

    if periodo == "scolastico" and anno_scolastico:
        start = _first_day(anno_scolastico.data_inizio)
    else:
        periodo = "solare"
        start = date(anno, 1, 1)

    mesi = [_add_months(start, offset, day=1) for offset in range(12)]
    selected_month = _month_from_key(request.GET.get("mese"), _first_day(oggi))
    if _month_key(selected_month) not in {_month_key(mese) for mese in mesi}:
        selected_month = mesi[0]
    end = _last_day(mesi[-1])

    return {
        "periodo": periodo,
        "anno": anno,
        "anni_solari": anni_solari,
        "anni_scolastici": anni_scolastici,
        "anno_scolastico": anno_scolastico,
        "start": start,
        "end": end,
        "mesi": mesi,
        "selected_month": selected_month,
    }


def _base_period_params(periodo_data, selected_month=None, vista=None):
    params = {"periodo": periodo_data["periodo"]}
    if periodo_data["periodo"] == "scolastico" and periodo_data["anno_scolastico"]:
        params["anno_scolastico"] = periodo_data["anno_scolastico"].pk
    else:
        params["anno"] = periodo_data["anno"]
    if selected_month:
        params["mese"] = _month_key(selected_month)
    if vista:
        params["vista"] = vista
    return params


def _spesa_row(
    *,
    data_scadenza,
    tipo,
    descrizione,
    soggetto="",
    categoria=None,
    importo_previsto=Decimal("0.00"),
    importo_pagato=Decimal("0.00"),
    detail_url="",
    popup_url="",
    popup_title="",
    action_url="",
    action_label="",
):
    importo_previsto = importo_previsto or Decimal("0.00")
    importo_pagato = importo_pagato or Decimal("0.00")
    residuo = max(importo_previsto - importo_pagato, Decimal("0.00"))
    return {
        "data_scadenza": data_scadenza,
        "mese_key": _month_key(data_scadenza),
        "tipo": tipo,
        "descrizione": descrizione,
        "soggetto": soggetto or "-",
        "categoria": categoria or "-",
        "importo_previsto": importo_previsto,
        "importo_pagato": importo_pagato,
        "residuo": residuo,
        "pagata": residuo <= Decimal("0.00"),
        "parziale": importo_pagato > Decimal("0.00") and residuo > Decimal("0.00"),
        "scaduta": residuo > Decimal("0.00") and data_scadenza < timezone.localdate(),
        "detail_url": detail_url,
        "popup_url": popup_url,
        "popup_title": popup_title,
        "action_url": action_url,
        "action_label": action_label,
    }


def _descrizione_spesa_mensile_documento(documento):
    descrizione = (documento.descrizione or "").strip()
    fallback = f"Fattura {documento.numero_documento}".strip()
    if not descrizione:
        return fallback

    fornitore = (getattr(getattr(documento, "fornitore", None), "denominazione", "") or "").strip()
    if not fornitore:
        return descrizione

    supplier_pattern = re.escape(fornitore)
    cleaned = re.sub(
        rf"\s*(?:[-,;:]\s*)?\bda\s+{supplier_pattern}\s*$",
        "",
        descrizione,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(
        rf"^\s*\bda\s+{supplier_pattern}\b\s*(?:[-,;:]\s*)?",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip(" -,;:")
    return cleaned or fallback


def _spese_mensili_rows(request, start, end):
    rows = []

    scadenze = (
        ScadenzaPagamentoFornitore.objects.select_related(
            "documento",
            "documento__fornitore",
            "documento__categoria_spesa",
            "documento__fornitore__categoria_spesa",
        )
        .exclude(stato=StatoScadenzaFornitore.ANNULLATA)
        .filter(data_scadenza__gte=start, data_scadenza__lte=end)
        .order_by("data_scadenza", "id")
    )
    for scadenza in scadenze:
        documento = scadenza.documento
        residuo = scadenza.importo_residuo
        documento_url = reverse("modifica_documento_fornitore", kwargs={"pk": documento.pk})
        documento_popup_url = f"{documento_url}?popup=1"
        payment_url = ""
        if residuo > Decimal("0.00"):
            payment_url = (
                f"{reverse('registra_pagamento_scadenza_fornitore', kwargs={'pk': scadenza.pk})}?"
                f"{urlencode({'popup': '1', 'reload_url': request.get_full_path()})}"
            )
        rows.append(
            _spesa_row(
                data_scadenza=scadenza.data_scadenza,
                tipo="Fattura",
                descrizione=_descrizione_spesa_mensile_documento(documento),
                soggetto=documento.fornitore.denominazione,
                categoria=documento.categoria_spesa_effettiva,
                importo_previsto=scadenza.importo_previsto,
                importo_pagato=scadenza.importo_pagato,
                detail_url=documento_url,
                popup_url=documento_popup_url,
                popup_title=f"Fattura {documento.numero_documento}",
                action_url=payment_url,
                action_label="Registra pagamento",
            )
        )

    spese = (
        SpesaOperativa.objects.select_related("categoria", "fornitore", "dipendente", "piano_rateale")
        .filter(data_scadenza__gte=start, data_scadenza__lte=end)
        .order_by("data_scadenza", "id")
    )
    for spesa in spese:
        rows.append(
            _spesa_row(
                data_scadenza=spesa.data_scadenza,
                tipo=spesa.get_tipo_display(),
                descrizione=spesa.descrizione,
                soggetto=str(spesa.soggetto_label) if spesa.soggetto_label else "",
                categoria=spesa.categoria,
                importo_previsto=spesa.importo_previsto,
                importo_pagato=spesa.importo_pagato,
                detail_url=reverse("modifica_spesa_operativa", kwargs={"pk": spesa.pk}),
                action_url=reverse("modifica_spesa_operativa", kwargs={"pk": spesa.pk}) if spesa.importo_residuo else "",
                action_label="Aggiorna pagamento",
            )
        )

    buste = BustaPagaDipendente.objects.select_related("dipendente").filter(
        anno__gte=start.year,
        anno__lte=end.year,
    )
    for busta in buste:
        data_scadenza = date(busta.anno, busta.mese, monthrange(busta.anno, busta.mese)[1])
        if data_scadenza < start or data_scadenza > end:
            continue
        importo_previsto = (
            busta.costo_azienda_effettivo
            or busta.costo_azienda_previsto
            or busta.netto_effettivo
            or busta.netto_previsto
            or Decimal("0.00")
        )
        if importo_previsto <= Decimal("0.00"):
            continue
        importo_pagato = importo_previsto if busta.data_pagamento_effettiva or busta.movimento_pagamento_id else Decimal("0.00")
        rows.append(
            _spesa_row(
                data_scadenza=data_scadenza,
                tipo="Busta paga",
                descrizione=f"Busta paga {busta.periodo_label}",
                soggetto=str(busta.dipendente),
                categoria="-",
                importo_previsto=importo_previsto,
                importo_pagato=importo_pagato,
                detail_url=reverse("modifica_busta_paga_dipendente", kwargs={"pk": busta.pk}),
                action_url=reverse("modifica_busta_paga_dipendente", kwargs={"pk": busta.pk}) if importo_pagato < importo_previsto else "",
                action_label="Apri busta paga",
            )
        )

    return sorted(rows, key=lambda row: (row["data_scadenza"], row["descrizione"]))


def _introiti_mensili(start, end):
    return list(
        MovimentoFinanziario.objects.select_related("conto", "categoria")
        .filter(data_contabile__gte=start, data_contabile__lte=end, importo__gt=0)
        .filter(Q(origine__in=[OrigineMovimento.BANCA, OrigineMovimento.IMPORT_FILE]) | Q(incide_su_saldo_banca=True))
        .order_by("data_contabile", "id")
    )


def spese_mensili_dashboard(request):
    periodo_data = _periodo_spese_mensili(request)
    vista = request.GET.get("vista") or "tutte"
    if vista not in {"tutte", "insolute"}:
        vista = "tutte"

    rows = _spese_mensili_rows(request, periodo_data["start"], periodo_data["end"])
    introiti = _introiti_mensili(periodo_data["start"], periodo_data["end"])
    month_stats = {
        _month_key(mese): {
            "date": mese,
            "key": _month_key(mese),
            "label": f"{MESI_BREVI[mese.month - 1]} {mese.year}",
            "totale_spese": Decimal("0.00"),
            "residuo": Decimal("0.00"),
            "spese_count": 0,
            "insolute_count": 0,
            "introiti": Decimal("0.00"),
            "url": f"{reverse('spese_mensili_dashboard')}?{urlencode(_base_period_params(periodo_data, mese, vista))}",
            "is_selected": _month_key(mese) == _month_key(periodo_data["selected_month"]),
        }
        for mese in periodo_data["mesi"]
    }

    for row in rows:
        stats = month_stats.get(row["mese_key"])
        if not stats:
            continue
        stats["totale_spese"] += row["importo_previsto"]
        stats["residuo"] += row["residuo"]
        stats["spese_count"] += 1
        if row["residuo"] > Decimal("0.00"):
            stats["insolute_count"] += 1

    for movimento in introiti:
        stats = month_stats.get(_month_key(movimento.data_contabile))
        if stats:
            stats["introiti"] += movimento.importo or Decimal("0.00")

    selected_key = _month_key(periodo_data["selected_month"])
    selected_rows_all = [row for row in rows if row["mese_key"] == selected_key]
    selected_rows = (
        [row for row in selected_rows_all if row["residuo"] > Decimal("0.00")]
        if vista == "insolute"
        else selected_rows_all
    )
    selected_introiti = [movimento for movimento in introiti if _month_key(movimento.data_contabile) == selected_key]

    switch_params = _base_period_params(periodo_data, periodo_data["selected_month"])
    vista_tutte_url = f"{reverse('spese_mensili_dashboard')}?{urlencode({**switch_params, 'vista': 'tutte'})}"
    vista_insolute_url = f"{reverse('spese_mensili_dashboard')}?{urlencode({**switch_params, 'vista': 'insolute'})}"

    return render(
        request,
        "gestione_finanziaria/spese_mensili_dashboard.html",
        {
            **periodo_data,
            "month_stats": list(month_stats.values()),
            "selected_month_key": selected_key,
            "selected_month_label": f"{MESI_BREVI[periodo_data['selected_month'].month - 1]} {periodo_data['selected_month'].year}",
            "selected_rows": selected_rows,
            "selected_rows_all_count": len(selected_rows_all),
            "selected_introiti": selected_introiti,
            "selected_introiti_total": sum((movimento.importo or Decimal("0.00") for movimento in selected_introiti), Decimal("0.00")),
            "vista": vista,
            "vista_tutte_url": vista_tutte_url,
            "vista_insolute_url": vista_insolute_url,
        },
    )


def _redirect_spese_mensili_for_date(value):
    params = {"periodo": "solare", "anno": value.year, "mese": _month_key(value)}
    return f"{reverse('spese_mensili_dashboard')}?{urlencode(params)}"


def _spesa_operativa_success_response(request, message, date_value, popup):
    target_url = (
        _safe_next_url(request, "spese_mensili_dashboard")
        if request.POST.get("next")
        else _redirect_spese_mensili_for_date(date_value)
    )
    messages.success(request, message)
    if popup:
        return render(
            request,
            "popup/popup_close.html",
            {"message": message, "reload_url": target_url},
        )
    return redirect(target_url)


def _spese_mensili_next_url(request):
    if request.GET.get("next") or request.POST.get("next"):
        return _safe_next_url(request, "spese_mensili_dashboard")
    return ""


def crea_spesa_operativa(request):
    popup = is_popup_request(request)
    if request.method == "POST":
        form = SpesaOperativaForm(request.POST)
        if form.is_valid():
            spesa = form.save(commit=False)
            spesa.creato_da = request.user if request.user.is_authenticated else None
            spesa.save()
            return _spesa_operativa_success_response(request, "Spesa registrata correttamente.", spesa.data_scadenza, popup)
    else:
        form = SpesaOperativaForm(
            initial={
                "data_scadenza": timezone.localdate(),
                "tipo": TipoSpesaOperativa.MANUALE,
            }
        )

    return render(
        request,
        "gestione_finanziaria/spesa_operativa_form.html",
        {
            "form": form,
            "spesa": None,
            "next_url": _spese_mensili_next_url(request),
            "popup": popup,
        },
    )


def modifica_spesa_operativa(request, pk):
    popup = is_popup_request(request)
    spesa = get_object_or_404(SpesaOperativa, pk=pk)
    if request.method == "POST":
        form = SpesaOperativaForm(request.POST, instance=spesa)
        if form.is_valid():
            spesa = form.save()
            return _spesa_operativa_success_response(request, "Spesa aggiornata correttamente.", spesa.data_scadenza, popup)
    else:
        form = SpesaOperativaForm(instance=spesa)

    return render(
        request,
        "gestione_finanziaria/spesa_operativa_form.html",
        {
            "form": form,
            "spesa": spesa,
            "next_url": _spese_mensili_next_url(request),
            "popup": popup,
        },
    )


def _tipo_spesa_da_piano(piano):
    if piano.tipo == TipoPianoRatealeSpesa.F24:
        return TipoSpesaOperativa.F24
    if piano.tipo == TipoPianoRatealeSpesa.FINANZIAMENTO:
        return TipoSpesaOperativa.FINANZIAMENTO
    return TipoSpesaOperativa.RATA_PIANO


def _genera_rate_piano_spesa(piano):
    piano.rate.all().delete()
    importo_base = (piano.importo_totale / Decimal(piano.numero_rate)).quantize(Decimal("0.01"))
    totale_precedente = Decimal("0.00")
    giorno_scadenza = piano.giorno_scadenza or piano.data_prima_scadenza.day
    for index in range(piano.numero_rate):
        if index == piano.numero_rate - 1:
            importo_rata = piano.importo_totale - totale_precedente
        else:
            importo_rata = importo_base
            totale_precedente += importo_rata
        SpesaOperativa.objects.create(
            piano_rateale=piano,
            numero_rata=index + 1,
            totale_rate=piano.numero_rate,
            tipo=_tipo_spesa_da_piano(piano),
            descrizione=f"{piano.descrizione} - rata {index + 1}/{piano.numero_rate}",
            categoria=piano.categoria,
            fornitore=piano.fornitore,
            data_scadenza=_add_months(piano.data_prima_scadenza, index * piano.frequenza_mesi, day=giorno_scadenza),
            importo_previsto=importo_rata,
            importo_pagato=Decimal("0.00"),
            creato_da=piano.creato_da,
        )


def _piano_rateale_spesa_success_response(request, message, date_value, popup):
    target_url = (
        _safe_next_url(request, "spese_mensili_dashboard")
        if request.POST.get("next")
        else _redirect_spese_mensili_for_date(date_value)
    )
    messages.success(request, message)
    if popup:
        return render(
            request,
            "popup/popup_close.html",
            {"message": message, "reload_url": target_url},
        )
    return redirect(target_url)


def crea_piano_rateale_spesa(request):
    popup = is_popup_request(request)
    if request.method == "POST":
        form = PianoRatealeSpesaForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                piano = form.save(commit=False)
                piano.creato_da = request.user if request.user.is_authenticated else None
                piano.save()
                _genera_rate_piano_spesa(piano)
            return _piano_rateale_spesa_success_response(
                request,
                "Piano rateale creato e rate generate correttamente.",
                piano.data_prima_scadenza,
                popup,
            )
    else:
        form = PianoRatealeSpesaForm(
            initial={
                "data_prima_scadenza": timezone.localdate(),
                "numero_rate": 12,
                "frequenza_mesi": 1,
            }
        )

    return render(
        request,
        "gestione_finanziaria/piano_rateale_spesa_form.html",
        {"form": form, "popup": popup, "next_url": _spese_mensili_next_url(request)},
    )


# =========================================================================
#  Fatture in Cloud, pagamenti e notifiche fornitori
# =========================================================================


def lista_fatture_in_cloud(request):
    connessioni = FattureInCloudConnessione.objects.order_by("nome")
    logs = FattureInCloudSyncLog.objects.select_related("connessione").order_by("-data_operazione", "-id")[:20]
    return render(
        request,
        "gestione_finanziaria/fatture_in_cloud_list.html",
        {
            "connessioni": connessioni,
            "logs": logs,
        },
    )


def crea_fatture_in_cloud(request):
    if request.method == "POST":
        form = FattureInCloudConnessioneForm(request.POST)
        if form.is_valid():
            connessione = form.save()
            messages.success(request, "Connessione Fatture in Cloud creata correttamente.")
            if request.POST.get("azione") == "salva_collega":
                return redirect("avvia_oauth_fatture_in_cloud", pk=connessione.pk)
            return redirect("modifica_fatture_in_cloud", pk=connessione.pk)
    else:
        form = FattureInCloudConnessioneForm()

    default_redirect_uri = _fatture_in_cloud_redirect_uri(request, None)
    return render(
        request,
        "gestione_finanziaria/fatture_in_cloud_form.html",
        {
            "form": form,
            "connessione": None,
            "default_redirect_uri": default_redirect_uri,
            "oauth_render_configurato": oauth_env_configured(),
        },
    )


def modifica_fatture_in_cloud(request, pk):
    connessione = get_object_or_404(FattureInCloudConnessione, pk=pk)
    if request.method == "POST":
        form = FattureInCloudConnessioneForm(request.POST, instance=connessione)
        if form.is_valid():
            connessione = form.save()
            messages.success(request, "Connessione Fatture in Cloud aggiornata correttamente.")
            if request.POST.get("azione") == "salva_collega":
                return redirect("avvia_oauth_fatture_in_cloud", pk=connessione.pk)
            return redirect("modifica_fatture_in_cloud", pk=connessione.pk)
    else:
        form = FattureInCloudConnessioneForm(instance=connessione)

    default_redirect_uri = _fatture_in_cloud_redirect_uri(request, connessione)
    webhook_url = request.build_absolute_uri(
        reverse("webhook_fatture_in_cloud", kwargs={"webhook_key": connessione.webhook_key})
    )
    return render(
        request,
        "gestione_finanziaria/fatture_in_cloud_form.html",
        {
            "form": form,
            "connessione": connessione,
            "default_redirect_uri": default_redirect_uri,
            "oauth_render_configurato": oauth_env_configured(),
            "oauth_confermato": request.GET.get("oauth") == "ok",
            "webhook_url": webhook_url,
            "logs": connessione.log_sincronizzazioni.order_by("-data_operazione", "-id")[:10],
        },
    )


def elimina_fatture_in_cloud(request, pk):
    connessione = get_object_or_404(FattureInCloudConnessione, pk=pk)

    if request.method == "POST":
        nome = connessione.nome
        connessione.delete()
        messages.success(
            request,
            f"Connessione Fatture in Cloud \"{nome}\" rimossa. Puoi crearne una nuova e ripetere la sincronizzazione.",
        )
        return redirect("lista_fatture_in_cloud")

    return render(
        request,
        "gestione_finanziaria/fatture_in_cloud_confirm_delete.html",
        {"connessione": connessione},
    )


def _fatture_in_cloud_redirect_uri(request, connessione):
    if connessione and connessione.redirect_uri:
        return connessione.redirect_uri
    if configured_oauth_redirect_uri():
        return configured_oauth_redirect_uri()
    return request.build_absolute_uri(reverse("callback_fatture_in_cloud"))


def avvia_oauth_fatture_in_cloud(request, pk):
    connessione = get_object_or_404(FattureInCloudConnessione, pk=pk)
    if not has_oauth_credentials(connessione):
        messages.error(
            request,
            "Configura prima Client ID e Client Secret nella connessione oppure nelle variabili ambiente Render.",
        )
        return redirect("modifica_fatture_in_cloud", pk=connessione.pk)

    state = secrets.token_urlsafe(32)
    connessione.oauth_state = state
    connessione.save(update_fields=["oauth_state", "data_aggiornamento"])
    try:
        auth_url = authorization_url(connessione, _fatture_in_cloud_redirect_uri(request, connessione), state)
    except FattureInCloudError as exc:
        messages.error(request, str(exc))
        return redirect("modifica_fatture_in_cloud", pk=connessione.pk)
    return redirect(auth_url)


def callback_fatture_in_cloud(request):
    state = request.GET.get("state") or ""
    code = request.GET.get("code") or ""
    error = request.GET.get("error") or ""
    if error:
        messages.error(request, f"Autorizzazione Fatture in Cloud fallita: {error}")
        return redirect("lista_fatture_in_cloud")
    if not state or not code:
        messages.error(request, "Callback Fatture in Cloud incompleta.")
        return redirect("lista_fatture_in_cloud")

    connessione = FattureInCloudConnessione.objects.filter(oauth_state=state).first()
    if connessione is None:
        messages.error(request, "State OAuth non riconosciuto.")
        return redirect("lista_fatture_in_cloud")

    try:
        client = FattureInCloudClient(connessione)
        client.exchange_code(code, _fatture_in_cloud_redirect_uri(request, connessione))
        if not connessione.company_id:
            companies = client.list_user_companies()
            if len(companies) == 1 and companies[0].get("id"):
                connessione.company_id = companies[0]["id"]
        connessione.oauth_state = ""
        connessione.stato = StatoConnessioneFattureInCloud.ATTIVA
        connessione.save(update_fields=["company_id", "oauth_state", "stato", "data_aggiornamento"])
        messages.success(request, "Fatture in Cloud collegato correttamente.")
        return redirect(f"{reverse('modifica_fatture_in_cloud', kwargs={'pk': connessione.pk})}?oauth=ok")
    except FattureInCloudError as exc:
        messages.error(request, str(exc))
    except Exception as exc:
        logger.exception("Errore inatteso nella callback Fatture in Cloud per connessione %s", connessione.pk)
        messages.error(
            request,
            "Collegamento Fatture in Cloud non completato per un errore interno. "
            "Controlla i log applicativi e riprova.",
        )
    return redirect("modifica_fatture_in_cloud", pk=connessione.pk)


def sincronizza_fatture_in_cloud_view(request, pk):
    connessione = get_object_or_404(FattureInCloudConnessione, pk=pk)
    if request.method != "POST":
        return redirect("modifica_fatture_in_cloud", pk=connessione.pk)
    try:
        stats = sincronizza_fatture_in_cloud(connessione, utente=request.user)
        message = (
            f"Sincronizzazione completata: {stats['creati']} documenti nuovi, "
            f"{stats['aggiornati']} documenti aggiornati. "
            f"Fornitori: {stats.get('fornitori_creati', 0)} nuovi, "
            f"{stats.get('fornitori_aggiornati', 0)} aggiornati."
        )
        if stats.get("esito") == EsitoSincronizzazione.PARZIALE:
            detail = " ".join(stats.get("messaggi") or [])
            messages.warning(request, f"{message} Alcuni elementi non sono stati completati. {detail}"[:4000])
        else:
            messages.success(request, message)
    except FattureInCloudError as exc:
        messages.error(request, f"Sincronizzazione fallita: {exc}")
    return redirect("modifica_fatture_in_cloud", pk=connessione.pk)


def diagnostica_payload_fatture_in_cloud(request, pk):
    if not user_is_operational_admin(request.user):
        messages.error(request, "La diagnostica Fatture in Cloud e riservata ad amministratori e superuser.")
        return redirect("modifica_fatture_in_cloud", pk=pk)

    connessione = get_object_or_404(FattureInCloudConnessione, pk=pk)
    documenti_recenti = (
        DocumentoFornitore.objects.select_related("fornitore")
        .filter(external_source=FIC_SOURCE)
        .exclude(external_id="")
        .order_by("-data_documento", "-id")[:80]
    )
    selected_documento_pk = ""
    document_id = ""
    source_type = "registered"
    report_json = ""

    if request.method == "POST":
        selected_documento_pk = (request.POST.get("documento_fornitore") or "").strip()
        document_id = (request.POST.get("document_id") or "").strip()
        source_type = request.POST.get("source_type") if request.POST.get("source_type") in {"registered", "pending"} else "registered"

        if selected_documento_pk and not document_id:
            documento = DocumentoFornitore.objects.filter(
                pk=selected_documento_pk,
                external_source=FIC_SOURCE,
            ).exclude(external_id="").first()
            if documento:
                document_id = documento.external_id
            else:
                messages.error(request, "Fattura importata non trovata o senza ID Fatture in Cloud.")

        if not document_id:
            messages.error(request, "Inserisci un ID documento Fatture in Cloud o seleziona una fattura importata.")
        else:
            client = FattureInCloudClient(connessione)
            try:
                if source_type == "pending":
                    payload = client.get_pending_received_document(document_id)
                else:
                    payload = client.get_received_document(document_id)
                if not isinstance(payload, dict):
                    raise FattureInCloudError("Il payload recuperato non e' un oggetto JSON.")
                report_json = payload_debug_report_json(
                    payload,
                    source=source_type,
                    document_id=document_id,
                    max_depth=6,
                    max_list_items=2,
                    include_attachment=True,
                )
                messages.success(request, "Report diagnostico generato e mascherato correttamente.")
            except FattureInCloudError as exc:
                messages.error(request, f"Diagnostica non completata: {exc}")

    return render(
        request,
        "gestione_finanziaria/fatture_in_cloud_diagnostica.html",
        {
            "connessione": connessione,
            "documenti_recenti": documenti_recenti,
            "selected_documento_pk": selected_documento_pk,
            "document_id": document_id,
            "source_type": source_type,
            "report_json": report_json,
        },
    )


@csrf_exempt
def webhook_fatture_in_cloud(request, webhook_key):
    connessione = get_object_or_404(FattureInCloudConnessione, webhook_key=webhook_key, attiva=True)
    if request.method == "GET":
        return JsonResponse({"success": True})
    if request.method != "POST":
        return JsonResponse({"success": False, "error": "Metodo non consentito."}, status=405)

    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        payload = {}

    notification_type = request.headers.get("ce-type") or payload.get("type") or ""
    data = payload.get("data") or {}
    ids = data.get("ids") or data.get("id") or []
    if isinstance(ids, (str, int)):
        ids = [ids]
    imported = 0
    errors = []
    for document_id in ids:
        try:
            importa_documento_da_webhook(connessione, notification_type, document_id)
            imported += 1
        except Exception as exc:
            errors.append(str(exc))

    status = 200 if not errors else 202
    return JsonResponse({"success": True, "imported": imported, "errors": errors[:3]}, status=status)


def lista_notifiche_finanziarie(request):
    notifiche = NotificaFinanziaria.objects.select_related("documento", "scadenza", "movimento_finanziario")
    can_manage_gestione_finanziaria = user_has_module_permission(
        request.user,
        "gestione_finanziaria",
        LivelloPermesso.GESTIONE,
    )
    if not can_manage_gestione_finanziaria:
        notifiche = notifiche.filter(richiede_gestione=False)
    lette_ids = set(
        NotificaFinanziariaLettura.objects.filter(user=request.user).values_list("notifica_id", flat=True)
    )
    only_unread = request.GET.get("stato") == "non_lette"
    if only_unread:
        notifiche = notifiche.exclude(letture__user=request.user)

    return render(
        request,
        "gestione_finanziaria/notifiche_finanziarie_list.html",
        {
            "notifiche": notifiche.order_by("-data_creazione", "-id"),
            "lette_ids": lette_ids,
            "stato": request.GET.get("stato") or "",
        },
    )


def segna_notifica_finanziaria_letta(request, pk):
    notifica = get_object_or_404(NotificaFinanziaria, pk=pk)
    if request.method == "POST":
        NotificaFinanziariaLettura.objects.get_or_create(notifica=notifica, user=request.user)
        if next_url := request.POST.get("next"):
            if url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
                return redirect(next_url)
    return redirect("lista_notifiche_finanziarie")


def segna_tutte_notifiche_finanziarie_lette(request):
    if request.method == "POST":
        qs = NotificaFinanziaria.objects.all()
        if not user_has_module_permission(request.user, "gestione_finanziaria", LivelloPermesso.GESTIONE):
            qs = qs.filter(richiede_gestione=False)
        existing = set(
            NotificaFinanziariaLettura.objects.filter(user=request.user).values_list("notifica_id", flat=True)
        )
        NotificaFinanziariaLettura.objects.bulk_create(
            [
                NotificaFinanziariaLettura(notifica=notifica, user=request.user)
                for notifica in qs
                if notifica.pk not in existing
            ],
            ignore_conflicts=True,
        )
        messages.success(request, "Notifiche segnate come lette.")
    return redirect("lista_notifiche_finanziarie")


def registra_pagamento_scadenza_fornitore(request, pk):
    popup = is_popup_request(request)
    scadenza = get_object_or_404(
        ScadenzaPagamentoFornitore.objects.select_related("documento", "documento__fornitore", "conto_bancario"),
        pk=pk,
    )
    candidati_movimento = trova_movimenti_candidati_per_scadenza_fornitore(scadenza, limite=5)
    if request.method == "POST":
        post_data = request.POST.copy()
        quick_movimento_id = post_data.get("quick_movimento")
        if quick_movimento_id:
            movimento = (
                MovimentoFinanziario.objects.select_related("conto")
                .filter(pk=quick_movimento_id, importo__lt=0)
                .first()
            )
            if movimento is not None:
                importo = min(importo_movimento_disponibile_fornitori(movimento), importo_scadenza_fornitore_residuo(scadenza))
                post_data["movimento_finanziario"] = str(movimento.pk)
                post_data["metodo"] = MetodoPagamentoFornitore.BANCA
                post_data["data_pagamento"] = movimento.data_contabile.isoformat()
                post_data["importo"] = str(importo)
                if movimento.conto_id:
                    post_data["conto_bancario"] = str(movimento.conto_id)
            else:
                messages.error(request, "Movimento bancario non valido per la riconciliazione.")

        form = PagamentoFornitoreForm(post_data)
        if form.is_valid():
            movimento = form.cleaned_data.get("movimento_finanziario")
            try:
                registra_pagamento_fornitore(
                    scadenza,
                    importo=form.cleaned_data["importo"],
                    data_pagamento=form.cleaned_data["data_pagamento"],
                    movimento=movimento,
                    metodo=form.cleaned_data["metodo"],
                    conto=form.cleaned_data.get("conto_bancario"),
                    note=form.cleaned_data.get("note") or "",
                    utente=request.user,
                )
                messages.success(request, "Pagamento fornitore registrato correttamente.")
                if popup:
                    return render(
                        request,
                        "popup/popup_close.html",
                        {
                            "message": "Pagamento fornitore registrato correttamente.",
                            "reload_url": _safe_reload_url(request, "lista_documenti_fornitori"),
                        },
                    )
                return redirect("modifica_documento_fornitore", pk=scadenza.documento_id)
            except ValidationError as exc:
                for message in exc.messages:
                    messages.error(request, message)
    else:
        form = PagamentoFornitoreForm(
            initial={
                "scadenza": scadenza,
                "data_pagamento": timezone.localdate(),
                "importo": importo_scadenza_fornitore_residuo(scadenza),
            }
        )

    return render(
        request,
        "gestione_finanziaria/pagamento_fornitore_form.html",
        {
            "form": form,
            "scadenza": scadenza,
            "popup": popup,
            "candidati_movimento": candidati_movimento,
            "reload_url": request.GET.get("reload_url") or request.POST.get("reload_url") or "",
        },
    )


def elimina_pagamento_fornitore(request, pk):
    popup = is_popup_request(request)
    pagamento = get_object_or_404(
        PagamentoFornitore.objects.select_related("scadenza", "scadenza__documento", "scadenza__documento__fornitore"),
        pk=pk,
    )
    documento_id = pagamento.scadenza.documento_id
    if request.method == "POST":
        annulla_pagamento_fornitore(pagamento)
        messaggio = "Pagamento fornitore annullato."
        if popup:
            return render(
                request,
                "popup/popup_close.html",
                {
                    "message": messaggio,
                    "reload_url": _safe_reload_url(request, "lista_documenti_fornitori"),
                },
            )
        messages.success(request, messaggio)
        return redirect("modifica_documento_fornitore", pk=documento_id)
    return render(
        request,
        "gestione_finanziaria/pagamento_fornitore_confirm_delete.html",
        {"pagamento": pagamento, "popup": popup, "reload_url": request.GET.get("reload_url") or request.POST.get("reload_url") or ""},
    )


def lista_movimenti_da_riconciliare_fornitori(request):
    if request.method == "POST" and request.POST.get("azione") == "conferma_auto":
        preview = request.session.get(RICONCILIAZIONE_FORNITORI_PREVIEW_SESSION_KEY) or {}
        risultato = applica_anteprima_riconciliazione_fornitori(
            preview.get("dettagli", []),
            request.POST.getlist("selected_items"),
            utente=request.user,
        )
        request.session.pop(RICONCILIAZIONE_FORNITORI_PREVIEW_SESSION_KEY, None)
        stats = risultato["stats"]
        if risultato.get("errori"):
            messages.warning(
                request,
                f"Riconciliazione fornitori completata con errori: {stats.get('riconciliati', 0)} pagamento/i collegati.",
            )
        elif stats.get("riconciliati"):
            messages.success(request, f"Riconciliazione fornitori: {stats['riconciliati']} pagamento/i collegati.")
        else:
            messages.info(request, "Nessuna scadenza fornitore selezionata per la riconciliazione.")
        return redirect("lista_movimenti_da_riconciliare_fornitori")

    if request.method == "POST" and request.POST.get("azione") == "auto":
        preview = anteprima_riconcilia_fornitori_automaticamente()
        request.session[RICONCILIAZIONE_FORNITORI_PREVIEW_SESSION_KEY] = {
            "dettagli": preview["dettagli"],
        }
        return render(
            request,
            "gestione_finanziaria/riconciliazione_fornitori_preview.html",
            {
                "preview": preview,
            },
        )

    if request.method == "POST":
        return redirect("lista_movimenti_da_riconciliare_fornitori")

    movimenti = (
        MovimentoFinanziario.objects.select_related("conto", "categoria")
        .exclude(stato_riconciliazione=StatoRiconciliazione.IGNORATO)
        .filter(importo__lt=0)
        .order_by("-data_contabile", "-id")[:100]
    )
    movimenti_con_candidati = []
    for movimento in movimenti:
        residuo = importo_movimento_disponibile_fornitori(movimento)
        if residuo <= Decimal("0.00"):
            continue
        candidati = trova_scadenze_fornitori_candidate(movimento, limite=3)
        movimento.residuo_fornitori = residuo
        movimenti_con_candidati.append({"movimento": movimento, "candidati": candidati})

    return render(
        request,
        "gestione_finanziaria/riconciliazione_fornitori_list.html",
        {"movimenti_con_candidati": movimenti_con_candidati},
    )


def riconcilia_movimento_fornitore(request, pk):
    movimento = get_object_or_404(MovimentoFinanziario.objects.select_related("conto", "categoria"), pk=pk)
    candidati = trova_scadenze_fornitori_candidate(movimento, limite=12)
    if request.method == "POST":
        scadenza_id = request.POST.get("scadenza")
        importo = request.POST.get("importo")
        scadenza = ScadenzaPagamentoFornitore.objects.filter(pk=scadenza_id).select_related("documento").first()
        if scadenza is None:
            messages.error(request, "Seleziona una scadenza fornitore valida.")
        else:
            try:
                riconcilia_movimento_con_scadenza_fornitore(
                    movimento,
                    scadenza,
                    importo=Decimal(str(importo).replace(",", ".")) if importo else None,
                    utente=request.user,
                    note=request.POST.get("note") or "",
                )
                messages.success(request, "Movimento riconciliato con la scadenza fornitore.")
                return redirect("lista_movimenti_da_riconciliare_fornitori")
            except (ValidationError, InvalidOperation, ValueError) as exc:
                if isinstance(exc, ValidationError):
                    for message in exc.messages:
                        messages.error(request, message)
                else:
                    messages.error(request, "Importo non valido.")

    return render(
        request,
        "gestione_finanziaria/riconciliazione_fornitore.html",
        {
            "movimento": movimento,
            "candidati": candidati,
            "residuo_movimento": importo_movimento_disponibile_fornitori(movimento),
        },
    )


# =========================================================================
#  Provider bancari - CRUD
# =========================================================================


def lista_provider_bancari(request):
    provider = ProviderBancario.objects.annotate(
        numero_conti=Count("conti", distinct=True),
        numero_connessioni=Count("connessioni", distinct=True),
    ).order_by("nome")
    return render(
        request,
        "gestione_finanziaria/provider_list.html",
        {"provider": provider},
    )


def crea_provider_bancario(request):
    if request.method == "POST":
        form = ProviderBancarioForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Provider bancario creato correttamente.")
            return redirect("lista_provider_bancari")
    else:
        form = ProviderBancarioForm()

    return render(
        request,
        "gestione_finanziaria/provider_form.html",
        {"form": form, "provider": None},
    )


def modifica_provider_bancario(request, pk):
    provider = get_object_or_404(ProviderBancario, pk=pk)
    if request.method == "POST":
        form = ProviderBancarioForm(request.POST, instance=provider)
        if form.is_valid():
            form.save()
            messages.success(request, "Provider bancario aggiornato correttamente.")
            return redirect("lista_provider_bancari")
    else:
        form = ProviderBancarioForm(instance=provider)

    return render(
        request,
        "gestione_finanziaria/provider_form.html",
        {"form": form, "provider": provider},
    )


def elimina_provider_bancario(request, pk):
    provider = get_object_or_404(ProviderBancario, pk=pk)

    count_conti = provider.conti.count()
    count_connessioni = provider.connessioni.count()
    ha_vincoli = bool(count_conti or count_connessioni)

    if request.method == "POST":
        if ha_vincoli:
            messages.error(
                request,
                "Impossibile eliminare il provider: ha conti o connessioni collegate. "
                "Puoi disattivarlo invece di eliminarlo.",
            )
            return redirect("lista_provider_bancari")

        provider.delete()
        messages.success(request, "Provider bancario eliminato correttamente.")
        return redirect("lista_provider_bancari")

    return render(
        request,
        "gestione_finanziaria/provider_confirm_delete.html",
        {
            "provider": provider,
            "count_conti": count_conti,
            "count_connessioni": count_connessioni,
            "ha_vincoli": ha_vincoli,
        },
    )


# =========================================================================
#  Conti bancari - CRUD
# =========================================================================


def lista_conti_bancari(request):
    conti = list(
        ContoBancario.objects.select_related("provider", "connessione")
        .order_by("nome_conto")
    )
    saldo_totale = Decimal("0")
    for conto in conti:
        ultimo_saldo = conto.storico_saldi.order_by("-data_riferimento", "-id").first()
        conto.ultimo_saldo_registrato = ultimo_saldo
        conto.saldo_calcolato = calcola_saldo_conto_alla_data(conto)
        saldo_totale += conto.saldo_calcolato

    return render(
        request,
        "gestione_finanziaria/conti_bancari_list.html",
        {
            "conti": conti,
            "saldo_totale": saldo_totale,
        },
    )


def crea_conto_bancario(request):
    popup = is_popup_request(request)
    if request.method == "POST":
        form = ContoBancarioForm(request.POST)
        if form.is_valid():
            conto = form.save()
            if popup:
                return popup_select_response(request, "conto_bancario", conto.pk, str(conto))
            messages.success(request, f"Conto bancario \"{conto.nome_conto}\" creato correttamente.")
            return redirect("lista_conti_bancari")
    else:
        form = ContoBancarioForm(initial={"valuta": "EUR", "attivo": True})

    if popup:
        return render(
            request,
            "gestione_finanziaria/entity_popup_form.html",
            _generic_popup_form_context(request, form, "Nuovo conto"),
        )

    return render(
        request,
        "gestione_finanziaria/conto_form.html",
        {"form": form, "conto": None},
    )


def modifica_conto_bancario(request, pk):
    popup = is_popup_request(request)
    conto = get_object_or_404(ContoBancario, pk=pk)
    if request.method == "POST":
        form = ContoBancarioForm(request.POST, instance=conto)
        if form.is_valid():
            conto = form.save()
            if popup:
                return popup_select_response(request, "conto_bancario", conto.pk, str(conto))
            messages.success(request, "Conto bancario aggiornato correttamente.")
            return redirect("lista_conti_bancari")
    else:
        form = ContoBancarioForm(instance=conto)

    if popup:
        return render(
            request,
            "gestione_finanziaria/entity_popup_form.html",
            _generic_popup_form_context(request, form, f"Conto {conto.nome_conto}"),
        )

    return render(
        request,
        "gestione_finanziaria/conto_form.html",
        {"form": form, "conto": conto},
    )


def elimina_conto_bancario(request, pk):
    popup = is_popup_request(request)
    conto = get_object_or_404(ContoBancario, pk=pk)
    count_movimenti = conto.movimenti.count()
    count_saldi = conto.storico_saldi.count()
    ha_vincoli = bool(count_movimenti or count_saldi)

    if request.method == "POST":
        if ha_vincoli:
            if popup:
                return render(
                    request,
                    "gestione_finanziaria/entity_popup_delete.html",
                    _generic_popup_delete_context(
                        request,
                        "Elimina conto",
                        str(conto),
                        True,
                        "Questo conto ha movimenti o saldi storici collegati: puoi disattivarlo invece di eliminarlo.",
                    ),
                )
            messages.error(
                request,
                "Impossibile eliminare il conto: ha movimenti o saldi storici collegati. "
                "Puoi disattivarlo invece di eliminarlo.",
            )
            return redirect("lista_conti_bancari")

        object_id = conto.pk
        conto.delete()
        if popup:
            return popup_delete_response(request, "conto_bancario", object_id)
        messages.success(request, "Conto bancario eliminato correttamente.")
        return redirect("lista_conti_bancari")

    if popup:
        return render(
            request,
            "gestione_finanziaria/entity_popup_delete.html",
            _generic_popup_delete_context(
                request,
                "Elimina conto",
                str(conto),
                ha_vincoli,
                "Questo conto ha movimenti o saldi storici collegati: puoi disattivarlo invece di eliminarlo.",
            ),
        )

    return render(
        request,
        "gestione_finanziaria/conto_confirm_delete.html",
        {
            "conto": conto,
            "count_movimenti": count_movimenti,
            "count_saldi": count_saldi,
            "ha_vincoli": ha_vincoli,
        },
    )


def ricalcola_saldo_conto_bancario(request, pk):
    conto = get_object_or_404(ContoBancario, pk=pk)

    if request.method == "POST":
        nuovo_saldo = ricalcola_saldo_corrente_conto(conto)
        messages.success(
            request,
            f"Saldo del conto \"{conto.nome_conto}\" ricalcolato: {nuovo_saldo} {conto.valuta}.",
        )
        return redirect("lista_conti_bancari")

    return redirect("lista_conti_bancari")


# =========================================================================
#  Saldi conti - CRUD + import CSV
# =========================================================================


def _normalizza_header_csv(value):
    text = unicodedata.normalize("NFKD", value or "").encode("ascii", "ignore").decode("ascii").lower()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    return text.strip("_")


def _csv_get(row, *keys):
    for key in keys:
        value = row.get(key)
        if value not in (None, ""):
            return value
    return ""


def _parse_decimal_locale(value):
    raw = str(value or "").strip().replace("€", "").replace("EUR", "").replace("eur", "").replace(" ", "")
    if not raw:
        raise ValueError("valore vuoto")
    if "," in raw:
        raw = raw.replace(".", "").replace(",", ".")
    return Decimal(raw)


def _parse_saldo_datetime(value):
    raw = str(value or "").strip()
    if not raw:
        raise ValueError("data vuota")
    parsed_datetime = parse_datetime(raw)
    if parsed_datetime is not None:
        return timezone.make_aware(parsed_datetime) if timezone.is_naive(parsed_datetime) else parsed_datetime
    parsed_date = parse_date(raw)
    if parsed_date is not None:
        return timezone.make_aware(datetime.combine(parsed_date, time.max.replace(microsecond=0)))

    for fmt in ("%d/%m/%Y %H:%M", "%d/%m/%Y", "%d-%m-%Y %H:%M", "%d-%m-%Y"):
        try:
            parsed = datetime.strptime(raw, fmt)
        except ValueError:
            continue
        if fmt in ("%d/%m/%Y", "%d-%m-%Y"):
            parsed = datetime.combine(parsed.date(), time.max.replace(microsecond=0))
        return timezone.make_aware(parsed)
    raise ValueError(f"data non riconosciuta: {raw}")


def _parse_saldo_datetime_from_filename(filename):
    match = re.search(
        r"(?P<day>\d{2})_(?P<month>\d{2})_(?P<year>\d{4})(?:_(?P<hour>\d{2})\.(?P<minute>\d{2})\.(?P<second>\d{2}))?",
        filename or "",
    )
    if not match:
        return None
    parts = match.groupdict()
    parsed = datetime(
        int(parts["year"]),
        int(parts["month"]),
        int(parts["day"]),
        int(parts.get("hour") or 23),
        int(parts.get("minute") or 59),
        int(parts.get("second") or 59),
    )
    return timezone.make_aware(parsed)


def _conto_da_iban(iban):
    iban_clean = _clean_account_piece(iban)
    if not iban_clean:
        return None
    for conto in ContoBancario.objects.filter(attivo=True):
        if _clean_account_piece(conto.iban) == iban_clean:
            return conto
    return None


def _conto_da_rapporto(rapporto):
    numero = _clean_account_piece(rapporto)
    if not numero:
        return None
    for conto in ContoBancario.objects.filter(attivo=True):
        iban = _clean_account_piece(conto.iban)
        if iban and numero[-12:] and iban.endswith(numero[-12:]):
            return conto
        if numero in _clean_account_piece(conto.external_account_id) or numero in _clean_account_piece(conto.nome_conto):
            return conto
    return None


def _crea_conto_da_import_saldo(row):
    iban = (_csv_get(row, "iban") or "").strip().replace(" ", "")
    rapporto = (_csv_get(row, "rapporto", "numero_conto", "account") or "").strip()
    banca = (_csv_get(row, "banca", "istituto") or "").strip()
    intestatario = (_csv_get(row, "ragione_sociale", "intestatario") or "").strip()
    if not iban and not rapporto:
        return None

    numero = rapporto.split("-")[-1].strip() if rapporto else ""
    if banca and numero:
        nome_conto = f"{banca} - {numero}"
    elif banca:
        nome_conto = banca
    elif iban:
        nome_conto = f"Conto {iban[-4:]}"
    else:
        nome_conto = f"Conto {numero}"

    original_name = nome_conto
    suffix = 2
    while ContoBancario.objects.filter(nome_conto=nome_conto).exists():
        nome_conto = f"{original_name} ({suffix})"
        suffix += 1

    return ContoBancario.objects.create(
        nome_conto=nome_conto,
        iban=iban,
        banca=banca,
        intestatario=intestatario,
        attivo=True,
    )


def _trova_conto_per_import_saldo(row):
    conto_id = _csv_get(row, "conto_id", "id_conto", "id")
    if conto_id and str(conto_id).strip().isdigit():
        conto = ContoBancario.objects.filter(pk=str(conto_id).strip()).first()
        if conto:
            return conto

    nome_conto = _csv_get(row, "nome_conto", "conto", "account", "nome")
    if nome_conto:
        conto = ContoBancario.objects.filter(nome_conto__iexact=str(nome_conto).strip()).first()
        if conto:
            return conto

    conto = _conto_da_iban(_csv_get(row, "iban"))
    if conto:
        return conto

    conto = _conto_da_rapporto(_csv_get(row, "rapporto", "numero_conto"))
    if conto:
        return conto

    return _crea_conto_da_import_saldo(row)


def _aggiorna_saldo_corrente_da_snapshot(conto):
    nuovo_saldo = ricalcola_saldo_corrente_conto(conto)
    return nuovo_saldo


def lista_saldi_conti(request):
    saldi = (
        SaldoConto.objects.select_related("conto", "creato_da", "aggiornato_da")
        .order_by("-data_riferimento", "-id")
    )
    conto_filter = request.GET.get("conto")
    if conto_filter:
        saldi = saldi.filter(conto_id=conto_filter)

    conti = list(ContoBancario.objects.filter(attivo=True).order_by("nome_conto"))
    saldo_totale = Decimal("0")
    for conto in conti:
        conto.saldo_calcolato = calcola_saldo_conto_alla_data(conto)
        saldo_totale += conto.saldo_calcolato

    return render(
        request,
        "gestione_finanziaria/saldi_conti_list.html",
        {
            "saldi": saldi,
            "conti": conti,
            "saldo_totale": saldo_totale,
            "conto_selezionato": conto_filter or "",
        },
    )


def crea_saldo_conto(request):
    popup = is_popup_request(request)
    if request.method == "POST":
        form = SaldoContoForm(request.POST)
        if form.is_valid():
            saldo = form.save(commit=False)
            if request.user.is_authenticated:
                saldo.creato_da = request.user
                saldo.aggiornato_da = request.user
            saldo.save()
            _aggiorna_saldo_corrente_da_snapshot(saldo.conto)
            if popup:
                return popup_select_response(request, "saldo_conto", saldo.pk, str(saldo))
            messages.success(request, "Saldo registrato correttamente.")
            return redirect("lista_saldi_conti")
    else:
        conto_iniziale = ContoBancario.objects.filter(
            pk=request.GET.get("conto"),
            attivo=True,
        ).first()
        form = SaldoContoForm(
            initial={
                "conto": conto_iniziale.pk if conto_iniziale else None,
                "data_riferimento": timezone.localtime().strftime("%Y-%m-%dT%H:%M"),
                "valuta": "EUR",
                "fonte": FonteSaldo.MANUALE,
            }
        )

    if popup:
        return render(
            request,
            "gestione_finanziaria/entity_popup_form.html",
            _generic_popup_form_context(request, form, "Nuovo saldo conto"),
        )

    return render(
        request,
        "gestione_finanziaria/saldo_conto_form.html",
        {"form": form, "saldo": None},
    )


def modifica_saldo_conto(request, pk):
    popup = is_popup_request(request)
    saldo = get_object_or_404(SaldoConto, pk=pk)
    conto_precedente = saldo.conto
    if request.method == "POST":
        form = SaldoContoForm(request.POST, instance=saldo)
        if form.is_valid():
            saldo = form.save(commit=False)
            if request.user.is_authenticated:
                saldo.aggiornato_da = request.user
            saldo.save()
            _aggiorna_saldo_corrente_da_snapshot(saldo.conto)
            if conto_precedente != saldo.conto:
                _aggiorna_saldo_corrente_da_snapshot(conto_precedente)
            if popup:
                return popup_select_response(request, "saldo_conto", saldo.pk, str(saldo))
            messages.success(request, "Saldo aggiornato correttamente.")
            return redirect("lista_saldi_conti")
    else:
        form = SaldoContoForm(instance=saldo)

    if popup:
        return render(
            request,
            "gestione_finanziaria/entity_popup_form.html",
            _generic_popup_form_context(request, form, "Modifica saldo conto"),
        )

    return render(
        request,
        "gestione_finanziaria/saldo_conto_form.html",
        {"form": form, "saldo": saldo},
    )


def elimina_saldo_conto(request, pk):
    saldo = get_object_or_404(SaldoConto, pk=pk)
    conto = saldo.conto
    if request.method == "POST":
        saldo.delete()
        _aggiorna_saldo_corrente_da_snapshot(conto)
        messages.success(request, "Saldo eliminato correttamente.")
        return redirect("lista_saldi_conti")
    return render(
        request,
        "gestione_finanziaria/saldo_conto_confirm_delete.html",
        {"saldo": saldo},
    )


def import_saldi_conti(request):
    if request.method == "POST":
        form = ImportSaldiContoCsvForm(request.POST, request.FILES)
        if form.is_valid():
            uploaded = form.cleaned_data["file"]
            raw_bytes = uploaded.read()
            try:
                text = raw_bytes.decode("utf-8-sig")
            except UnicodeDecodeError:
                text = raw_bytes.decode("cp1252")

            sample = text[:2048]
            try:
                dialect = csv.Sniffer().sniff(sample, delimiters=";,")
            except csv.Error:
                class FallbackDialect(csv.excel):
                    delimiter = ";"

                dialect = FallbackDialect

            reader = csv.DictReader(io.StringIO(text), dialect=dialect)
            if not reader.fieldnames:
                messages.error(request, "Il file CSV non contiene intestazioni leggibili.")
                return redirect("import_saldi_conti")

            reader.fieldnames = [_normalizza_header_csv(field) for field in reader.fieldnames]
            creati = 0
            aggiornati = 0
            errori = []
            conti_aggiornati = set()
            data_da_nome_file = _parse_saldo_datetime_from_filename(getattr(uploaded, "name", ""))
            for index, row in enumerate(reader, start=2):
                try:
                    conto = _trova_conto_per_import_saldo(row)
                    if not conto:
                        raise ValueError("conto non trovato")
                    data_raw = _csv_get(row, "data_riferimento", "data", "data_saldo", "riferimento")
                    data_riferimento = (
                        _parse_saldo_datetime(data_raw)
                        if data_raw
                        else data_da_nome_file or timezone.now()
                    )
                    saldo_contabile = _parse_decimal_locale(
                        _csv_get(
                            row,
                            "saldo_contabile",
                            "saldo",
                            "saldo_conto",
                            "saldo_divisa",
                            "saldo_finale",
                        )
                    )
                    saldo_disponibile_raw = _csv_get(
                        row,
                        "saldo_disponibile",
                        "disponibile",
                        "saldo_liquido",
                    )
                    saldo_disponibile = (
                        _parse_decimal_locale(saldo_disponibile_raw) if saldo_disponibile_raw else None
                    )
                    valuta = (_csv_get(row, "valuta", "currency", "div", "divisa") or conto.valuta or "EUR").strip().upper()[:3]
                except Exception as exc:
                    errori.append(f"Riga {index}: {exc}")
                    continue

                _saldo, created = SaldoConto.objects.update_or_create(
                    conto=conto,
                    data_riferimento=data_riferimento,
                    fonte=FonteSaldo.IMPORT_FILE,
                    defaults={
                        "saldo_contabile": saldo_contabile,
                        "saldo_disponibile": saldo_disponibile,
                        "valuta": valuta,
                        "note": f"Import file: {getattr(uploaded, 'name', '')}".strip(),
                        "aggiornato_da": request.user if request.user.is_authenticated else None,
                    },
                )
                if created:
                    if request.user.is_authenticated:
                        _saldo.creato_da = request.user
                        _saldo.save(update_fields=["creato_da"])
                    creati += 1
                else:
                    aggiornati += 1
                conti_aggiornati.add(conto.pk)

            for conto in ContoBancario.objects.filter(pk__in=conti_aggiornati):
                _aggiorna_saldo_corrente_da_snapshot(conto)

            if creati:
                messages.success(request, f"Import completato: {creati} saldi registrati, {aggiornati} aggiornati.")
            elif aggiornati:
                messages.success(request, f"Import completato: {aggiornati} saldi aggiornati.")
            if errori:
                messages.warning(request, "Alcune righe non sono state importate: " + " | ".join(errori[:5]))
            return redirect("lista_saldi_conti")
    else:
        form = ImportSaldiContoCsvForm()

    return render(
        request,
        "gestione_finanziaria/saldi_conti_import.html",
        {"form": form},
    )


def scarica_template_saldi_conti_csv(_request):
    content = (
        "nome_conto;data_riferimento;saldo_contabile;saldo_disponibile;valuta\n"
        "Conto operativo;30/04/2026 23:59;10000,00;10000,00;EUR\n"
        "Cassa contanti;30/04/2026 23:59;250,00;;EUR\n"
    )
    response = HttpResponse(content, content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="template_saldi_conti.csv"'
    return response


# =========================================================================
#  Movimenti finanziari - lista + CRUD manuale
# =========================================================================


def lista_movimenti_finanziari(request):
    movimenti = (
        MovimentoFinanziario.objects.select_related("conto", "categoria", "categoria__parent")
        .annotate(
            riconciliazioni_rate_count=Count("riconciliazioni_rate", distinct=True),
            pagamenti_fornitori_count=Count("pagamenti_fornitori", distinct=True),
        )
        .order_by("-data_contabile", "-id")
    )

    conti_filter = request.GET.get("conto")
    categoria_filter = request.GET.get("categoria")
    origine_filter = request.GET.get("origine")
    canale_filter = request.GET.get("canale")

    if conti_filter:
        movimenti = movimenti.filter(conto_id=conti_filter)
    if categoria_filter == "none":
        movimenti = movimenti.filter(categoria__isnull=True)
    elif categoria_filter:
        movimenti = movimenti.filter(categoria_id=categoria_filter)
    if origine_filter:
        movimenti = movimenti.filter(origine=origine_filter)
    if canale_filter:
        movimenti = movimenti.filter(canale=canale_filter)

    return render(
        request,
        "gestione_finanziaria/movimenti_list.html",
        {
            "movimenti": movimenti,
            "conti_disponibili": ContoBancario.objects.filter(attivo=True).order_by("nome_conto"),
            "categorie_disponibili": CategoriaFinanziaria.objects.filter(attiva=True).order_by(
                "parent__nome", "nome"
            ),
            "origini_disponibili": OrigineMovimento.choices,
            "canali_disponibili": CanaleMovimento.choices,
            "conto_selezionato": conti_filter or "",
            "categoria_selezionata": categoria_filter or "",
            "origine_selezionata": origine_filter or "",
            "canale_selezionato": canale_filter or "",
        },
    )


def _movimenti_da_pulire_queryset(ambito):
    queryset = MovimentoFinanziario.objects.all()
    if ambito == PuliziaMovimentiFinanziariForm.AMBITO_AUTOMATICI:
        return queryset.filter(origine__in=[OrigineMovimento.IMPORT_FILE, OrigineMovimento.BANCA])
    if ambito == PuliziaMovimentiFinanziariForm.AMBITO_MANUALI:
        return queryset.filter(origine=OrigineMovimento.MANUALE)
    return queryset


def _statistiche_pulizia_movimenti(queryset):
    return {
        "totale": queryset.count(),
        "automatici": queryset.filter(origine__in=[OrigineMovimento.IMPORT_FILE, OrigineMovimento.BANCA]).count(),
        "import_file": queryset.filter(origine=OrigineMovimento.IMPORT_FILE).count(),
        "banca": queryset.filter(origine=OrigineMovimento.BANCA).count(),
        "manuali": queryset.filter(origine=OrigineMovimento.MANUALE).count(),
        "riconciliati_rate": queryset.filter(rata_iscrizione__isnull=False).count(),
        "collegati_scadenze": ScadenzaPagamentoFornitore.objects.filter(movimento_finanziario__in=queryset).count(),
        "collegati_buste": BustaPagaDipendente.objects.filter(movimento_pagamento__in=queryset).count(),
    }


def pulizia_movimenti_finanziari(request):
    if request.method == "POST":
        form = PuliziaMovimentiFinanziariForm(request.POST)
        if form.is_valid():
            ambito = form.cleaned_data["ambito"]
            queryset = _movimenti_da_pulire_queryset(ambito)
            statistiche = _statistiche_pulizia_movimenti(queryset)
            conti_da_ricalcolare_ids = list(
                queryset.filter(conto__isnull=False, incide_su_saldo_banca=True)
                .values_list("conto_id", flat=True)
                .distinct()
            )

            if statistiche["totale"] == 0:
                messages.info(request, "Nessun movimento da eliminare per l'ambito selezionato.")
                return redirect("pulizia_movimenti_finanziari")

            with transaction.atomic():
                eliminati, _ = queryset.delete()

            for conto in ContoBancario.objects.filter(pk__in=conti_da_ricalcolare_ids):
                ricalcola_saldo_corrente_conto(conto)

            messaggio = f"Pulizia completata: eliminati {eliminati} movimenti."
            if statistiche["riconciliati_rate"] or statistiche["collegati_scadenze"] or statistiche["collegati_buste"]:
                messaggio += (
                    f" Rimosso anche il riferimento a {statistiche['riconciliati_rate']} movimenti "
                    f"riconciliati con rate, {statistiche['collegati_scadenze']} collegati a scadenze fornitori "
                    f"e {statistiche['collegati_buste']} collegati a buste paga."
                )
            messages.success(request, messaggio)
            return redirect("lista_movimenti_finanziari")
    else:
        form = PuliziaMovimentiFinanziariForm()

    statistiche = _statistiche_pulizia_movimenti(MovimentoFinanziario.objects.all())

    return render(
        request,
        "gestione_finanziaria/movimenti_pulizia.html",
        {
            "form": form,
            "statistiche": statistiche,
        },
    )


def _movimento_manuale_initial(request):
    initial = {
        "data_contabile": timezone.now().date(),
        "valuta": "EUR",
        "canale": CanaleMovimento.BANCA,
    }
    allowed_fields = [
        "data_contabile",
        "data_valuta",
        "importo",
        "valuta",
        "descrizione",
        "controparte",
        "iban_controparte",
        "categoria",
        "conto",
        "canale",
        "incide_su_saldo_banca",
        "sostenuta_da_terzi",
        "rimborsabile",
        "sostenitore",
        "note",
    ]
    for field_name in allowed_fields:
        value = (request.GET.get(field_name) or "").strip()
        if value:
            initial[field_name] = value
    return initial


def _busta_paga_pagamento_id(request):
    value = (request.GET.get("busta_paga_pagamento") or request.POST.get("busta_paga_pagamento") or "").strip()
    if not value:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _collega_movimento_a_busta_paga(movimento, busta_id):
    if not busta_id:
        return
    busta = BustaPagaDipendente.objects.filter(pk=busta_id).first()
    if not busta:
        return
    movimento_precedente_id = busta.movimento_pagamento_id
    busta.movimento_pagamento = movimento
    update_fields = ["movimento_pagamento", "data_aggiornamento"]
    if not busta.data_pagamento_effettiva:
        busta.data_pagamento_effettiva = movimento.data_contabile
        update_fields.append("data_pagamento_effettiva")
    busta.save(update_fields=update_fields)
    movimento_ids = {movimento_id for movimento_id in (movimento_precedente_id, movimento.pk) if movimento_id}
    for movimento_collegato in MovimentoFinanziario.objects.filter(pk__in=movimento_ids):
        aggiorna_stato_riconciliazione_movimento(movimento_collegato)


def crea_movimento_manuale(request):
    popup = is_popup_request(request)
    busta_paga_pagamento_id = _busta_paga_pagamento_id(request)
    if request.method == "POST":
        form = MovimentoFinanziarioForm(request.POST)
        if form.is_valid():
            movimento = form.save(commit=False)
            movimento.origine = OrigineMovimento.MANUALE
            if movimento.canale == CanaleMovimento.PERSONALE:
                movimento.sostenuta_da_terzi = True
                movimento.incide_su_saldo_banca = False

            if not movimento.categoria_id:
                applica_regole_a_movimento(movimento)

            movimento.save()
            _collega_movimento_a_busta_paga(movimento, busta_paga_pagamento_id)

            if movimento.conto_id and movimento.incide_su_saldo_banca:
                ricalcola_saldo_corrente_conto(movimento.conto)

            if popup:
                return popup_select_response(request, "movimento_finanziario", movimento.pk, str(movimento))
            messages.success(request, "Movimento manuale registrato correttamente.")
            return redirect("lista_movimenti_finanziari")
    else:
        form = MovimentoFinanziarioForm(initial=_movimento_manuale_initial(request))

    if popup:
        context = _generic_popup_form_context(request, form, "Nuovo movimento")
        context["busta_paga_pagamento_id"] = busta_paga_pagamento_id
        return render(
            request,
            "gestione_finanziaria/entity_popup_form.html",
            context,
        )

    return render(
        request,
        "gestione_finanziaria/movimento_form.html",
        {"form": form, "movimento": None},
    )


def modifica_movimento_finanziario(request, pk):
    popup = is_popup_request(request)
    movimento = get_object_or_404(MovimentoFinanziario, pk=pk)
    conto_precedente = movimento.conto
    incide_precedente = movimento.incide_su_saldo_banca

    if request.method == "POST":
        form = MovimentoFinanziarioForm(request.POST, instance=movimento)
        if form.is_valid():
            movimento = form.save(commit=False)
            if movimento.canale == CanaleMovimento.PERSONALE:
                movimento.sostenuta_da_terzi = True
                movimento.incide_su_saldo_banca = False

            if "categoria" in form.changed_data and movimento.categoria_id:
                movimento.categorizzazione_automatica = False
                movimento.categorizzato_da = request.user if request.user.is_authenticated else None
                movimento.categorizzato_il = timezone.now()

            movimento.save()

            conti_da_ricalcolare = set()
            if movimento.conto_id and movimento.incide_su_saldo_banca:
                conti_da_ricalcolare.add(movimento.conto)
            if conto_precedente and (
                conto_precedente != movimento.conto or incide_precedente
            ):
                conti_da_ricalcolare.add(conto_precedente)
            for conto in conti_da_ricalcolare:
                ricalcola_saldo_corrente_conto(conto)

            if popup:
                return popup_select_response(request, "movimento_finanziario", movimento.pk, str(movimento))
            messages.success(request, "Movimento aggiornato correttamente.")
            return redirect("lista_movimenti_finanziari")
    else:
        form = MovimentoFinanziarioForm(instance=movimento)

    if popup:
        return render(
            request,
            "gestione_finanziaria/entity_popup_form.html",
            _generic_popup_form_context(request, form, "Modifica movimento"),
        )

    return render(
        request,
        "gestione_finanziaria/movimento_form.html",
        {"form": form, "movimento": movimento},
    )


def elimina_movimento_finanziario(request, pk):
    popup = is_popup_request(request)
    movimento = get_object_or_404(MovimentoFinanziario, pk=pk)

    if request.method == "POST":
        conto_da_ricalcolare = movimento.conto if (movimento.conto_id and movimento.incide_su_saldo_banca) else None
        object_id = movimento.pk
        movimento.delete()
        if conto_da_ricalcolare:
            ricalcola_saldo_corrente_conto(conto_da_ricalcolare)
        if popup:
            return popup_delete_response(request, "movimento_finanziario", object_id)
        messages.success(request, "Movimento eliminato correttamente.")
        return redirect("lista_movimenti_finanziari")

    if popup:
        return render(
            request,
            "gestione_finanziaria/entity_popup_delete.html",
            _generic_popup_delete_context(request, "Elimina movimento", str(movimento)),
        )

    return render(
        request,
        "gestione_finanziaria/movimento_confirm_delete.html",
        {"movimento": movimento},
    )


def elimina_movimenti_finanziari_multipla(request):
    if request.method != "POST":
        return redirect("lista_movimenti_finanziari")

    next_url = _safe_bulk_next_url(request, "lista_movimenti_finanziari")
    selected_ids = _ids_selezionati_da_post(request)
    if not selected_ids:
        messages.error(request, "Seleziona almeno un movimento da eliminare.")
        return redirect(next_url)

    queryset = (
        MovimentoFinanziario.objects.select_related("conto", "categoria", "categoria__parent")
        .filter(pk__in=selected_ids)
        .order_by("-data_contabile", "-id")
    )
    movimenti = list(queryset)
    if not movimenti:
        messages.error(request, "I movimenti selezionati non sono piu disponibili.")
        return redirect(next_url)

    if request.POST.get("conferma") == "1":
        conti_da_ricalcolare_ids = list(
            queryset.filter(conto__isnull=False, incide_su_saldo_banca=True)
            .values_list("conto_id", flat=True)
            .distinct()
        )
        count = len(movimenti)
        with transaction.atomic():
            MovimentoFinanziario.objects.filter(pk__in=[movimento.pk for movimento in movimenti]).delete()

        for conto in ContoBancario.objects.filter(pk__in=conti_da_ricalcolare_ids):
            ricalcola_saldo_corrente_conto(conto)

        messages.success(request, f"Eliminati {count} movimenti selezionati.")
        return redirect(next_url)

    totale_importi = sum(
        ((movimento.importo or Decimal("0.00")) for movimento in movimenti),
        Decimal("0.00"),
    )
    conti_count = len({movimento.conto_id for movimento in movimenti if movimento.conto_id})
    riconciliazioni_rate_count = (
        MovimentoFinanziario.objects.filter(pk__in=[movimento.pk for movimento in movimenti])
        .filter(Q(rata_iscrizione__isnull=False) | Q(riconciliazioni_rate__isnull=False))
        .distinct()
        .count()
    )
    scadenze_collegate_count = ScadenzaPagamentoFornitore.objects.filter(
        movimento_finanziario__in=movimenti
    ).count()
    pagamenti_collegati_count = PagamentoFornitore.objects.filter(movimento_finanziario__in=movimenti).count()
    buste_collegate_count = BustaPagaDipendente.objects.filter(movimento_pagamento__in=movimenti).count()

    return render(
        request,
        "gestione_finanziaria/movimenti_bulk_confirm_delete.html",
        {
            "movimenti": movimenti,
            "selected_ids": selected_ids,
            "next_url": next_url,
            "totale_importi": totale_importi,
            "conti_count": conti_count,
            "riconciliazioni_rate_count": riconciliazioni_rate_count,
            "scadenze_collegate_count": scadenze_collegate_count,
            "pagamenti_collegati_count": pagamenti_collegati_count,
            "buste_collegate_count": buste_collegate_count,
        },
    )


def annulla_riconciliazione_movimento(request, pk):
    movimento = get_object_or_404(
        MovimentoFinanziario.objects.select_related("conto", "categoria", "rata_iscrizione").prefetch_related(
            "riconciliazioni_rate__rata",
            "pagamenti_fornitori__scadenza__documento__fornitore",
        ),
        pk=pk,
    )
    next_url = _safe_next_url(request, "lista_movimenti_finanziari")
    riconciliazioni_rate = list(movimento.riconciliazioni_rate.all())
    pagamenti_fornitori = list(movimento.pagamenti_fornitori.all())
    ha_riconciliazioni = bool(movimento.rata_iscrizione_id or riconciliazioni_rate or pagamenti_fornitori)

    if request.method == "POST":
        if not ha_riconciliazioni:
            messages.info(request, "Il movimento non ha riconciliazioni da annullare.")
            return redirect(next_url)

        rate_count = len(riconciliazioni_rate) or (1 if movimento.rata_iscrizione_id else 0)
        fornitori_count = len(pagamenti_fornitori)
        if movimento.rata_iscrizione_id or riconciliazioni_rate:
            annulla_riconciliazione(movimento)
        for pagamento in pagamenti_fornitori:
            annulla_pagamento_fornitore(pagamento)

        dettagli = []
        if rate_count:
            dettagli.append(f"{rate_count} collegamento/i rata")
        if fornitori_count:
            dettagli.append(f"{fornitori_count} pagamento/i fornitore")
        messages.success(request, "Riconciliazione annullata: " + ", ".join(dettagli) + ".")
        return redirect(next_url)

    return render(
        request,
        "gestione_finanziaria/movimento_annulla_riconciliazione.html",
        {
            "movimento": movimento,
            "riconciliazioni_rate": riconciliazioni_rate,
            "pagamenti_fornitori": pagamenti_fornitori,
            "ha_riconciliazioni": ha_riconciliazioni,
            "next_url": next_url,
        },
    )


# =========================================================================
#  Regole di categorizzazione - CRUD
# =========================================================================


def lista_regole_categorizzazione(request):
    regole = (
        RegolaCategorizzazione.objects.select_related("categoria_da_assegnare")
        .order_by("priorita", "nome")
    )
    return render(
        request,
        "gestione_finanziaria/regole_list.html",
        {"regole": regole},
    )


def crea_regola_categorizzazione(request):
    if request.method == "POST":
        form = RegolaCategorizzazioneForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Regola creata correttamente.")
            return redirect("lista_regole_categorizzazione")
    else:
        form = RegolaCategorizzazioneForm(initial={"priorita": 100, "attiva": True})

    return render(
        request,
        "gestione_finanziaria/regola_form.html",
        {"form": form, "regola": None},
    )


def modifica_regola_categorizzazione(request, pk):
    regola = get_object_or_404(RegolaCategorizzazione, pk=pk)
    if request.method == "POST":
        form = RegolaCategorizzazioneForm(request.POST, instance=regola)
        if form.is_valid():
            form.save()
            messages.success(request, "Regola aggiornata correttamente.")
            return redirect("lista_regole_categorizzazione")
    else:
        form = RegolaCategorizzazioneForm(instance=regola)

    return render(
        request,
        "gestione_finanziaria/regola_form.html",
        {"form": form, "regola": regola},
    )


def elimina_regola_categorizzazione(request, pk):
    regola = get_object_or_404(RegolaCategorizzazione, pk=pk)
    if request.method == "POST":
        regola.delete()
        messages.success(request, "Regola eliminata correttamente.")
        return redirect("lista_regole_categorizzazione")

    return render(
        request,
        "gestione_finanziaria/regola_confirm_delete.html",
        {"regola": regola},
    )


def applica_regole_massiva(request):
    """
    Applica le regole attive a tutti i movimenti ancora non categorizzati.
    Azione manuale usata dall'utente dalla lista regole / dashboard.
    """

    if request.method != "POST":
        return redirect("lista_regole_categorizzazione")

    movimenti = MovimentoFinanziario.objects.filter(categoria__isnull=True)
    categorizzati = 0
    for movimento in movimenti:
        regola = applica_regole_a_movimento(movimento)
        if regola is not None:
            movimento.save(
                update_fields=[
                    "categoria",
                    "categorizzazione_automatica",
                    "regola_categorizzazione",
                    "categorizzato_il",
                ]
            )
            categorizzati += 1

    if categorizzati:
        messages.success(
            request,
            f"Regole applicate: {categorizzati} movimenti sono stati categorizzati automaticamente.",
        )
    else:
        messages.info(request, "Nessun movimento e' stato categorizzato: nessuna regola ha trovato match.")

    return redirect("lista_regole_categorizzazione")


# =========================================================================
#  Categorie finanziarie - CRUD (invariato rispetto all'iterazione precedente)
# =========================================================================


def lista_categorie_finanziarie(request):
    categorie = list(
        CategoriaFinanziaria.objects.select_related("parent").order_by("ordine", "nome", "id")
    )
    icon_symbol_by_value = {
        icon["value"]: icon["symbol"]
        for icon in CategoriaFinanziariaForm.ICON_CHOICES
    }
    figli_by_parent = {}
    for categoria in categorie:
        figli_by_parent.setdefault(categoria.parent_id, []).append(categoria)

    def build_node(categoria, livello=0):
        figli = [
            build_node(figlia, livello + 1)
            for figlia in figli_by_parent.get(categoria.pk, [])
        ]
        discendenti_count = sum(1 + figlia["discendenti_count"] for figlia in figli)
        row_tone = categoria.tipo
        if row_tone not in {
            TipoCategoriaFinanziaria.ENTRATA,
            TipoCategoriaFinanziaria.SPESA,
            TipoCategoriaFinanziaria.TRASFERIMENTO,
        }:
            row_tone = "neutra"
        return {
            "categoria": categoria,
            "figli": figli,
            "livello": livello,
            "row_id": f"categoria-{categoria.pk}",
            "row_tone": row_tone,
            "discendenti_count": discendenti_count,
            "icon_symbol": icon_symbol_by_value.get(categoria.icona, ""),
        }

    categorie_tree = [
        build_node(categoria)
        for categoria in figli_by_parent.get(None, [])
    ]
    return render(
        request,
        "gestione_finanziaria/categorie_list.html",
        {
            "categorie": categorie,
            "categorie_tree": categorie_tree,
            "tipo_choices": TipoCategoriaFinanziaria.choices,
        },
    )


def crea_categoria_finanziaria(request):
    popup = is_popup_request(request)
    if request.method == "POST":
        form = CategoriaFinanziariaForm(request.POST)
        if form.is_valid():
            categoria = form.save()
            if popup:
                return popup_select_response(request, "categoria_finanziaria", categoria.pk, str(categoria))
            messages.success(request, "Categoria finanziaria creata correttamente.")
            return redirect("lista_categorie_finanziarie")
    else:
        form = CategoriaFinanziariaForm(initial={"attiva": True})

    if popup:
        return render(
            request,
            "gestione_finanziaria/entity_popup_form.html",
            _generic_popup_form_context(request, form, "Nuova categoria finanziaria"),
        )

    return render(
        request,
        "gestione_finanziaria/categoria_form.html",
        {
            "form": form,
            "categoria": None,
            "icon_choices": CategoriaFinanziariaForm.ICON_CHOICES,
        },
    )


def modifica_categoria_finanziaria(request, pk):
    popup = is_popup_request(request)
    categoria = get_object_or_404(CategoriaFinanziaria, pk=pk)

    if request.method == "POST":
        form = CategoriaFinanziariaForm(request.POST, instance=categoria)
        if form.is_valid():
            categoria = form.save()
            if popup:
                return popup_select_response(request, "categoria_finanziaria", categoria.pk, str(categoria))
            messages.success(request, "Categoria finanziaria aggiornata correttamente.")
            return redirect("lista_categorie_finanziarie")
    else:
        form = CategoriaFinanziariaForm(instance=categoria)

    if popup:
        return render(
            request,
            "gestione_finanziaria/entity_popup_form.html",
            _generic_popup_form_context(request, form, f"Categoria {categoria.nome}"),
        )

    return render(
        request,
        "gestione_finanziaria/categoria_form.html",
        {
            "form": form,
            "categoria": categoria,
            "icon_choices": CategoriaFinanziariaForm.ICON_CHOICES,
        },
    )


def elimina_categoria_finanziaria(request, pk):
    popup = is_popup_request(request)
    categoria = get_object_or_404(CategoriaFinanziaria, pk=pk)

    count_movimenti = categoria.movimenti.count()
    count_fornitori = categoria.fornitori.count()
    count_documenti = categoria.documenti_fornitori.count()
    count_figlie = categoria.figli.count()
    count_regole = categoria.regole.count()
    count_voci_budget = categoria.voci_budget.count()
    ha_vincoli = bool(count_movimenti or count_fornitori or count_documenti or count_figlie or count_regole or count_voci_budget)

    if request.method == "POST":
        if ha_vincoli:
            if popup:
                return render(
                    request,
                    "gestione_finanziaria/entity_popup_delete.html",
                    _generic_popup_delete_context(
                        request,
                        f"Elimina categoria {categoria.nome}",
                        str(categoria),
                        True,
                        "Impossibile eliminare la categoria: ha elementi collegati. Puoi disattivarla invece di eliminarla.",
                    ),
                )
            messages.error(
                request,
                "Impossibile eliminare la categoria: ha elementi collegati. Puoi disattivarla invece di eliminarla.",
            )
            return redirect("lista_categorie_finanziarie")

        object_id = categoria.pk
        categoria.delete()
        if popup:
            return popup_delete_response(request, "categoria_finanziaria", object_id)
        messages.success(request, "Categoria finanziaria eliminata correttamente.")
        return redirect("lista_categorie_finanziarie")

    if popup:
        return render(
            request,
            "gestione_finanziaria/entity_popup_delete.html",
            _generic_popup_delete_context(
                request,
                f"Elimina categoria {categoria.nome}",
                str(categoria),
                ha_vincoli,
                "Impossibile eliminare la categoria: ha elementi collegati. Puoi disattivarla invece di eliminarla.",
            ),
        )

    return render(
        request,
        "gestione_finanziaria/categoria_confirm_delete.html",
        {
            "categoria": categoria,
            "count_movimenti": count_movimenti,
            "count_fornitori": count_fornitori,
            "count_documenti": count_documenti,
            "count_figlie": count_figlie,
            "count_regole": count_regole,
            "count_voci_budget": count_voci_budget,
            "ha_vincoli": ha_vincoli,
        },
    )


# =========================================================================
#  Import estratti conto (CAMT.053 / CSV)
# =========================================================================


_CSV_COL_FIELDS = [
    ("csv_col_data_contabile", "colonna_data_contabile"),
    ("csv_col_data_valuta", "colonna_data_valuta"),
    ("csv_col_importo", "colonna_importo"),
    ("csv_col_entrate", "colonna_entrate"),
    ("csv_col_uscite", "colonna_uscite"),
    ("csv_col_valuta", "colonna_valuta"),
    ("csv_col_descrizione", "colonna_descrizione"),
    ("csv_col_controparte", "colonna_controparte"),
    ("csv_col_iban_controparte", "colonna_iban_controparte"),
    ("csv_col_transaction_id", "colonna_transaction_id"),
]


def _build_manual_csv_config(form):
    cfg = CsvImporterConfig(
        delimiter=form.cleaned_data.get("csv_delimiter") or "",
        encoding=form.cleaned_data.get("csv_encoding") or "utf-8-sig",
        ha_intestazione=form.cleaned_data.get("csv_ha_intestazione") or False,
        formato_data=form.cleaned_data.get("csv_formato_data") or "%d/%m/%Y",
        separatore_decimale=form.cleaned_data.get("csv_sep_decimale") or ",",
        separatore_migliaia=form.cleaned_data.get("csv_sep_migliaia") or ".",
    )
    for form_field, cfg_field in _CSV_COL_FIELDS:
        setattr(
            cfg,
            cfg_field,
            ImportEstrattoContoForm.parse_column_ref(form.cleaned_data.get(form_field)),
        )
    return cfg


def _csv_config_to_dict(config):
    return {
        "delimiter": config.delimiter,
        "encoding": config.encoding,
        "ha_intestazione": config.ha_intestazione,
        "righe_da_saltare": config.righe_da_saltare,
        "colonna_data_contabile": config.colonna_data_contabile,
        "colonna_data_valuta": config.colonna_data_valuta,
        "colonna_importo": config.colonna_importo,
        "colonna_entrate": config.colonna_entrate,
        "colonna_uscite": config.colonna_uscite,
        "colonna_valuta": config.colonna_valuta,
        "colonna_descrizione": config.colonna_descrizione,
        "colonne_descrizione_extra": list(config.colonne_descrizione_extra or []),
        "colonna_controparte": config.colonna_controparte,
        "colonna_iban_controparte": config.colonna_iban_controparte,
        "colonna_transaction_id": config.colonna_transaction_id,
        "formato_data": config.formato_data,
        "separatore_decimale": config.separatore_decimale,
        "separatore_migliaia": config.separatore_migliaia,
        "valuta_default": config.valuta_default,
    }


def _csv_config_from_dict(data):
    return CsvImporterConfig(**(data or {}))


def _build_import_parser(parser_type, csv_config=None):
    if parser_type == "camt053":
        return Camt053Parser()
    if parser_type == "excel":
        return ExcelImporter(_csv_config_from_dict(csv_config))
    return CsvImporter(_csv_config_from_dict(csv_config))


def _is_probable_xml(raw_bytes, filename=""):
    if filename.lower().endswith((".xml", ".camt", ".camt053")):
        return True
    return raw_bytes.lstrip().startswith(b"<")


def _clean_account_piece(value):
    return "".join(ch for ch in (value or "") if ch.isalnum()).upper()


def _find_conto_from_cbi_metadata(detection):
    conti = list(ContoBancario.objects.filter(attivo=True).select_related("provider"))
    if len(conti) == 1 and not getattr(detection, "numero_conto", ""):
        return conti[0]

    abi = _clean_account_piece(getattr(detection, "abi", ""))
    cab = _clean_account_piece(getattr(detection, "cab", ""))
    numero = _clean_account_piece(getattr(detection, "numero_conto", ""))
    if not numero:
        return None

    numero_padded = numero.zfill(12)
    for conto in conti:
        iban = _clean_account_piece(conto.iban)
        if iban.startswith("IT") and len(iban) >= 27:
            iban_abi = iban[5:10]
            iban_cab = iban[10:15]
            iban_numero = iban[15:27]
            if iban_numero == numero_padded and (not abi or iban_abi == abi) and (not cab or iban_cab == cab):
                return conto
        if numero in _clean_account_piece(conto.external_account_id) or numero in _clean_account_piece(conto.nome_conto):
            return conto
    return None


def _build_import_preview(parser, raw_bytes, conto):
    parsed = list(parser.parse(raw_bytes))
    entrate = Decimal("0.00")
    uscite = Decimal("0.00")
    duplicati = 0
    esempi = []
    date = []
    preview_hashes = []
    existing_hashes = set()
    existing_tx_ids = set()

    if conto and parsed:
        hash_set = set()
        tx_set = set()
        for movimento in parsed:
            hash_dedup = calcola_hash_deduplica_movimento(
                conto_id=conto.id,
                data_contabile=movimento.data_contabile,
                importo=movimento.importo,
                descrizione=movimento.descrizione,
                controparte=movimento.controparte,
                iban_controparte=movimento.iban_controparte,
            )
            preview_hashes.append(hash_dedup)
            hash_set.add(hash_dedup)
            if movimento.provider_transaction_id:
                tx_set.add(movimento.provider_transaction_id)

        if hash_set:
            existing_hashes = set(
                MovimentoFinanziario.objects.filter(
                    conto=conto,
                    hash_deduplica__in=hash_set,
                ).values_list("hash_deduplica", flat=True)
            )
        if tx_set:
            existing_tx_ids = set(
                MovimentoFinanziario.objects.filter(
                    conto=conto,
                    provider_transaction_id__in=tx_set,
                ).values_list("provider_transaction_id", flat=True)
            )
    else:
        preview_hashes = [""] * len(parsed)

    seen_hashes = set()
    seen_tx_ids = set()

    for index, movimento in enumerate(parsed):
        date.append(movimento.data_contabile)
        if movimento.importo > 0:
            entrate += movimento.importo
        elif movimento.importo < 0:
            uscite += abs(movimento.importo)

        is_duplicate = False
        if conto:
            hash_dedup = preview_hashes[index]
            provider_tx_id = movimento.provider_transaction_id or ""
            is_duplicate = (
                hash_dedup in existing_hashes
                or hash_dedup in seen_hashes
                or (provider_tx_id and provider_tx_id in existing_tx_ids)
                or (provider_tx_id and provider_tx_id in seen_tx_ids)
            )
            if is_duplicate:
                duplicati += 1
            seen_hashes.add(hash_dedup)
            if provider_tx_id:
                seen_tx_ids.add(provider_tx_id)

        if len(esempi) < 8:
            esempi.append(
                {
                    "data": movimento.data_contabile,
                    "data_valuta": movimento.data_valuta,
                    "importo": movimento.importo,
                    "descrizione": movimento.descrizione,
                    "duplicato": is_duplicate,
                }
            )

    return {
        "totale_letti": len(parsed),
        "nuovi_stimati": max(len(parsed) - duplicati, 0),
        "duplicati_stimati": duplicati,
        "entrate": entrate,
        "uscite": uscite,
        "data_da": min(date) if date else None,
        "data_a": max(date) if date else None,
        "esempi": esempi,
    }


def import_estratto_conto(request):
    risultato = None
    preview = None
    import_token = ""
    detection = None
    detected_conto = None
    selected_conto = None

    if request.method == "POST" and request.POST.get("import_action") == "confirm":
        import_token = (request.POST.get("import_token") or "").strip()
        payload = cache.get(f"gf-import-estratto:{import_token}") if import_token else None
        conto = ContoBancario.objects.filter(pk=request.POST.get("conto"), attivo=True).select_related("provider").first()
        if not payload:
            messages.error(request, "Anteprima scaduta. Ricarica il file e ripeti l'import.")
            return redirect("import_estratto_conto")
        if not conto:
            messages.error(request, "Seleziona il conto bancario su cui importare i movimenti.")
            return redirect("import_estratto_conto")

        try:
            parser = _build_import_parser(payload["parser_type"], payload.get("csv_config"))
            risultato = importa_movimenti_da_file(
                parser=parser,
                raw_bytes=payload["raw_bytes"],
                conto=conto,
                provider=conto.provider,
                nome_file=payload.get("nome_file", ""),
                riconcilia_automaticamente=False,
            )
            cache.delete(f"gf-import-estratto:{import_token}")

            if risultato.inseriti:
                messages.success(
                    request,
                    f"Import completato: {risultato.inseriti} movimenti inseriti "
                    f"(duplicati scartati: {risultato.duplicati}). "
                    "La riconciliazione delle rette può essere avviata dalla pagina dedicata.",
                )
            elif risultato.errori:
                messages.error(
                    request,
                    "Import terminato con errori. Controlla i dettagli sotto.",
                )
            else:
                messages.info(
                    request,
                    f"Nessun nuovo movimento inserito "
                    f"(letti: {risultato.totale_letti}, duplicati: {risultato.duplicati}).",
                )
        except Exception as exc:
            messages.error(request, f"Import fallito: {exc}")

    is_preview_post = request.method == "POST" and request.POST.get("import_action") != "confirm"
    form = ImportEstrattoContoForm(
        request.POST if is_preview_post else None,
        request.FILES if is_preview_post else None,
    )

    if is_preview_post and form.is_valid():
        conto = form.cleaned_data["conto"]
        formato = form.cleaned_data["formato"]
        uploaded = form.cleaned_data["file"]
        raw_bytes = uploaded.read()

        try:
            if formato == "auto":
                if is_probable_excel_file(raw_bytes, getattr(uploaded, "name", "")):
                    detection = detect_excel_import_config(raw_bytes)
                    parser_type = "excel"
                    parser = ExcelImporter(detection.config)
                    detected_conto = _find_conto_from_cbi_metadata(detection)
                elif _is_probable_xml(raw_bytes, getattr(uploaded, "name", "")):
                    parser_type = "camt053"
                    parser = Camt053Parser()
                else:
                    detection = detect_csv_import_config(raw_bytes)
                    parser_type = "csv"
                    parser = CsvImporter(detection.config)
                    detected_conto = _find_conto_from_cbi_metadata(detection)
            elif formato == "camt053":
                parser_type = "camt053"
                parser = Camt053Parser()
            elif formato == "excel":
                parser_type = "excel"
                parser = ExcelImporter(_build_manual_csv_config(form))
            else:
                parser_type = "csv"
                parser = CsvImporter(_build_manual_csv_config(form))

            selected_conto = conto or detected_conto
            preview = _build_import_preview(parser, raw_bytes, selected_conto)
            if not preview["totale_letti"]:
                messages.error(request, "Non ho trovato movimenti importabili nel file caricato.")
            else:
                import_token = secrets.token_urlsafe(24)
                csv_config = _csv_config_to_dict(parser.config) if isinstance(parser, (CsvImporter, ExcelImporter)) else None
                cache.set(
                    f"gf-import-estratto:{import_token}",
                    {
                        "raw_bytes": raw_bytes,
                        "nome_file": getattr(uploaded, "name", ""),
                        "parser_type": parser_type,
                        "csv_config": csv_config,
                    },
                    30 * 60,
                )
                if selected_conto:
                    form.initial["conto"] = selected_conto.pk
        except Exception as exc:
            messages.error(request, f"Anteprima import fallita: {exc}")

    return render(
        request,
        "gestione_finanziaria/import_estratto_conto.html",
        {
            "form": form,
            "risultato": risultato,
            "preview": preview,
            "import_token": import_token,
            "detection": detection,
            "detected_conto": detected_conto,
            "selected_conto": selected_conto,
            "conti_import": ContoBancario.objects.filter(attivo=True).order_by("nome_conto"),
        },
    )


# =========================================================================
#  Connessioni PSD2 (configurazione provider + flusso consenso)
# =========================================================================


def lista_connessioni_bancarie(request):
    psd2_qs = ProviderBancario.objects.filter(tipo=TipoProviderBancario.PSD2).order_by("nome")
    # Tupla (provider, credenziali complete) per UI: Enable Banking non usa secret_key_cifrata.
    provider_psd2 = [
        (p, configurazione_completa(p)) for p in psd2_qs
    ]
    connessioni = (
        ConnessioneBancaria.objects.select_related("provider")
        .prefetch_related("conti")
        .order_by("provider__nome", "etichetta")
    )
    log_recenti = SincronizzazioneLog.objects.select_related("conto", "connessione").order_by(
        "-data_operazione"
    )[:20]
    return render(
        request,
        "gestione_finanziaria/connessioni_list.html",
        {
            "provider_psd2": provider_psd2,
            "connessioni": connessioni,
            "log_recenti": log_recenti,
        },
    )


def configura_provider_psd2(request, pk):
    provider = get_object_or_404(ProviderBancario, pk=pk)
    if provider.tipo != TipoProviderBancario.PSD2:
        messages.error(request, "Il provider selezionato non e' di tipo PSD2.")
        return redirect("lista_provider_bancari")

    cfg_attuale = provider.configurazione or {}

    if request.method == "POST":
        form = ProviderPsd2ConfigForm(request.POST, provider=provider)
        if form.is_valid():
            nuova_cfg = dict(cfg_attuale)
            nuova_cfg["adapter"] = cfg_attuale.get("adapter") or "gocardless_bad"
            nuova_cfg["secret_id"] = form.cleaned_data["secret_id"]
            if form.cleaned_data.get("secret_key"):
                nuova_cfg["secret_key_cifrata"] = cifra_testo(form.cleaned_data["secret_key"])
            if form.cleaned_data.get("environment"):
                nuova_cfg["environment"] = form.cleaned_data["environment"]
            if form.cleaned_data.get("base_url"):
                nuova_cfg["base_url"] = form.cleaned_data["base_url"]
            else:
                nuova_cfg.pop("base_url", None)
            if form.cleaned_data.get("redirect_uri"):
                nuova_cfg["redirect_uri"] = form.cleaned_data["redirect_uri"]
            else:
                # Permette di rimuovere un redirect_uri precedente lasciando il campo vuoto.
                nuova_cfg.pop("redirect_uri", None)
            providers_default_raw = (form.cleaned_data.get("providers_default") or "").strip()
            if providers_default_raw:
                # Normalizza in una singola stringa con spazi singoli.
                nuova_cfg["providers_default"] = " ".join(providers_default_raw.split())
            else:
                nuova_cfg.pop("providers_default", None)
            if form.cleaned_data.get("country_default"):
                nuova_cfg["country_default"] = form.cleaned_data["country_default"].upper()
            # Campi specifici Salt Edge (il checkbox viene sempre inviato).
            nuova_cfg["include_fake_providers"] = bool(
                form.cleaned_data.get("include_fake_providers")
            )
            if form.cleaned_data.get("locale"):
                nuova_cfg["locale"] = form.cleaned_data["locale"].lower()
            else:
                nuova_cfg.pop("locale", None)
            psu_tipo = (form.cleaned_data.get("psu_type") or "").strip()
            if psu_tipo in ("personal", "business"):
                nuova_cfg["psu_type"] = psu_tipo
            else:
                nuova_cfg.pop("psu_type", None)
            # Private key RSA per la firma delle richieste Salt Edge:
            # trattata come i secret (cifrata prima di salvare; campo vuoto
            # => mantiene la chiave esistente).
            pem_nuovo = (form.cleaned_data.get("private_key_pem") or "").strip()
            if pem_nuovo:
                nuova_cfg["private_key_pem_cifrato"] = cifra_testo(pem_nuovo)
            passphrase_nuova = form.cleaned_data.get("private_key_passphrase") or ""
            if passphrase_nuova:
                nuova_cfg["private_key_passphrase_cifrata"] = cifra_testo(passphrase_nuova)

            provider.configurazione = nuova_cfg
            provider.save(update_fields=["configurazione", "data_aggiornamento"])
            messages.success(request, f"Credenziali del provider '{provider.nome}' aggiornate.")
            return redirect("lista_connessioni_bancarie")
    else:
        form = ProviderPsd2ConfigForm(
            provider=provider,
            initial={
                "secret_id": cfg_attuale.get("secret_id", ""),
                "environment": cfg_attuale.get("environment", ""),
                "base_url": cfg_attuale.get("base_url", ""),
                "redirect_uri": cfg_attuale.get("redirect_uri", ""),
                "providers_default": cfg_attuale.get("providers_default", ""),
                "country_default": cfg_attuale.get("country_default", "IT"),
                "include_fake_providers": bool(
                    cfg_attuale.get("include_fake_providers") or False
                ),
                "locale": cfg_attuale.get("locale", "it"),
                "psu_type": cfg_attuale.get("psu_type", ""),
            }
        )

    # Redirect URI "suggerito" calcolato dal request: lo mostriamo in UI per
    # permettere all'utente di copiarlo nella console del provider OAuth2
    # (TrueLayer richiede il whitelisting esatto anche in sandbox).
    redirect_uri_calcolato = request.build_absolute_uri(reverse("callback_oauth_psd2"))

    saltedge_return_url = request.build_absolute_uri(
        reverse("callback_connessione_psd2", args=[0])
    ).replace("/0/callback/", "/<id>/callback/")

    return render(
        request,
        "gestione_finanziaria/provider_psd2_config_form.html",
        {
            "provider": provider,
            "form": form,
            "ha_secret_key": bool(cfg_attuale.get("secret_key_cifrata")),
            "ha_private_key": bool(cfg_attuale.get("private_key_pem_cifrato")),
            "ha_private_key_passphrase": bool(
                cfg_attuale.get("private_key_passphrase_cifrata")
            ),
            "redirect_uri_calcolato": redirect_uri_calcolato,
            "redirect_uri_configurato": cfg_attuale.get("redirect_uri", ""),
            "is_oauth_adapter": is_oauth_adapter(provider),
            "is_saltedge_adapter": is_saltedge_adapter(provider),
            "is_enablebanking_adapter": is_enablebanking_adapter(provider),
            "is_redirect_callback_adapter": is_redirect_callback_adapter(provider),
            "saltedge_return_url_template": saltedge_return_url,
        },
    )


def nuova_connessione_psd2(request, provider_pk):
    provider = get_object_or_404(ProviderBancario, pk=provider_pk)
    if provider.tipo != TipoProviderBancario.PSD2:
        messages.error(request, "Il provider selezionato non e' di tipo PSD2.")
        return redirect("lista_connessioni_bancarie")

    if not configurazione_completa(provider):
        messages.error(
            request,
            "Provider non configurato: completa le credenziali tecniche (console PSD2) "
            "prima di avviare una connessione.",
        )
        return redirect("configura_provider_psd2", pk=provider.pk)

    country = (provider.configurazione or {}).get("country_default", "IT") or "IT"
    istituti = []
    errore_lista = ""
    try:
        adapter = adapter_for_provider(provider)
        istituti = adapter.lista_istituti(country=country)
    except ProviderConfigurazioneMancante as exc:
        errore_lista = str(exc)
    except Exception as exc:
        errore_lista = f"Errore durante la lettura degli istituti: {exc}"

    if request.method == "POST":
        form = NuovaConnessioneBancariaForm(request.POST, provider=provider)
        if form.is_valid():
            try:
                adapter = adapter_for_provider(provider)
                connessione = ConnessioneBancaria.objects.create(
                    provider=provider,
                    etichetta=form.cleaned_data["etichetta"],
                    external_institution_id=form.cleaned_data["institution_id"],
                    stato=StatoConnessioneBancaria.ATTIVA,
                )
                # Provider OAuth2 (es. TrueLayer) richiedono un redirect_uri *fisso*
                # pre-registrato nella console dello sviluppatore. Usiamo allora
                # l'URL generico 'callback_oauth_psd2' e passiamo il pk via 'state'.
                if is_redirect_callback_adapter(provider):
                    redirect_url = _oauth_redirect_uri(request, provider)
                else:
                    redirect_url = request.build_absolute_uri(
                        reverse("callback_connessione_psd2", args=[connessione.pk])
                    )
                info = adapter.crea_connessione(
                    institution_id=form.cleaned_data["institution_id"],
                    redirect_url=redirect_url,
                    reference=f"arboris-{connessione.pk}",
                    max_historical_days=form.cleaned_data["max_historical_days"],
                    access_valid_for_days=form.cleaned_data["access_valid_for_days"],
                )
                connessione.external_connection_id = info.external_connection_id
                update_fields = ["external_connection_id", "data_aggiornamento"]
                # Per Salt Edge il customer_id e' stato creato dall'adapter:
                # lo conserviamo cifrato su ``access_token_cifrato`` cosi' al
                # callback sappiamo quale customer interrogare per trovare la
                # connection_id effettiva.
                if isinstance(adapter, SaltEdgeAdapter) and adapter.customer_id:
                    connessione.access_token_cifrato = cifra_testo(adapter.customer_id)
                    update_fields.append("access_token_cifrato")
                if info.expires_at:
                    connessione.consenso_scadenza = info.expires_at
                    update_fields.append("consenso_scadenza")
                connessione.save(update_fields=update_fields)
                return redirect(info.authorization_url)
            except Exception as exc:
                messages.error(request, f"Impossibile avviare la connessione: {exc}")
    else:
        form = NuovaConnessioneBancariaForm(provider=provider)

    return render(
        request,
        "gestione_finanziaria/nuova_connessione_form.html",
        {
            "provider": provider,
            "form": form,
            "istituti": istituti,
            "errore_lista": errore_lista,
            "country": country,
            "is_truelayer": is_oauth_adapter(provider),
        },
    )


def _finalizza_connessione_psd2(request, connessione, adapter):
    """
    Step comune a tutti i provider dopo che il consenso e' stato concesso:
    1. chiede l'elenco dei conti al provider;
    2. crea/aggiorna i :class:`ContoBancario` corrispondenti;
    3. segna la connessione come ATTIVA.
    """
    try:
        conti_provider = adapter.lista_conti(connessione.external_connection_id)
    except Exception as exc:
        connessione.stato = StatoConnessioneBancaria.ERRORE
        connessione.ultimo_errore = str(exc)[:1000]
        connessione.save(update_fields=["stato", "ultimo_errore", "data_aggiornamento"])
        messages.error(request, f"Errore durante il recupero dei conti: {exc}")
        return redirect("lista_connessioni_bancarie")

    provider = connessione.provider
    creati = 0
    for account in conti_provider:
        conto, is_new = ContoBancario.objects.get_or_create(
            provider=provider,
            external_account_id=account.external_account_id,
            defaults={
                "nome_conto": account.name or f"Conto {account.iban or account.external_account_id}",
                "iban": account.iban,
                "intestatario": account.owner_name,
                "valuta": account.currency or "EUR",
                "connessione": connessione,
                "attivo": True,
            },
        )
        if not is_new:
            conto.connessione = connessione
            if account.iban and not conto.iban:
                conto.iban = account.iban
            if account.owner_name and not conto.intestatario:
                conto.intestatario = account.owner_name
            conto.save()
        else:
            creati += 1

    connessione.stato = StatoConnessioneBancaria.ATTIVA
    connessione.ultimo_refresh_at = timezone.now()
    connessione.ultimo_errore = ""
    connessione.save(
        update_fields=[
            "stato",
            "ultimo_refresh_at",
            "ultimo_errore",
            "data_aggiornamento",
        ]
    )

    messages.success(
        request,
        f"Connessione autorizzata. Conti collegati: {len(conti_provider)} "
        f"(nuovi: {creati}).",
    )
    return redirect("lista_connessioni_bancarie")


def callback_connessione_psd2(request, pk):
    """
    URL di ritorno dal consenso utente per provider *non* OAuth2 standard
    (es. GoCardless Bank Account Data). Il provider redirige qui con un
    parametro ``ref`` e/o ``error``. Interroghiamo l'API per:
    - verificare lo stato della requisition;
    - recuperare gli ``accounts`` collegati;
    - creare/aggiornare i :class:`ContoBancario` corrispondenti.
    """

    connessione = get_object_or_404(ConnessioneBancaria, pk=pk)
    provider = connessione.provider
    if provider.tipo != TipoProviderBancario.PSD2:
        raise Http404()

    error = request.GET.get("error")
    if error:
        connessione.stato = StatoConnessioneBancaria.ERRORE
        connessione.ultimo_errore = f"Error return: {error}"
        connessione.save(update_fields=["stato", "ultimo_errore", "data_aggiornamento"])
        messages.error(request, f"Autorizzazione negata o fallita: {error}")
        return redirect("lista_connessioni_bancarie")

    try:
        adapter = adapter_for_provider(provider, connessione=connessione)
    except Exception as exc:
        connessione.stato = StatoConnessioneBancaria.ERRORE
        connessione.ultimo_errore = str(exc)[:1000]
        connessione.save(update_fields=["stato", "ultimo_errore", "data_aggiornamento"])
        messages.error(request, f"Errore provider: {exc}")
        return redirect("lista_connessioni_bancarie")

    # Salt Edge: al callback la connection_id vera non arriva come query
    # param (non c'e' OAuth2). Dobbiamo interrogare /connections?customer_id=
    # e prendere la piu' recente creata dopo l'inizio del flusso.
    if isinstance(adapter, SaltEdgeAdapter) and not connessione.external_connection_id:
        try:
            connection_id = adapter.trova_connection_id(
                customer_id=adapter.customer_id,
                created_after=connessione.data_creazione,
            )
        except SaltEdgeError as exc:
            connessione.stato = StatoConnessioneBancaria.ERRORE
            connessione.ultimo_errore = str(exc)[:1000]
            connessione.save(
                update_fields=["stato", "ultimo_errore", "data_aggiornamento"]
            )
            messages.error(request, f"Salt Edge: {exc}")
            return redirect("lista_connessioni_bancarie")
        connessione.external_connection_id = connection_id
        connessione.save(
            update_fields=["external_connection_id", "data_aggiornamento"]
        )

    return _finalizza_connessione_psd2(request, connessione, adapter)


def callback_oauth_psd2(request):
    """
    Callback *fisso* per TrueLayer (OAuth2) e Enable Banking (code -> sessione).

    Il provider redirige qui con ``?code=...&state=arboris-<pk>`` (oppure
    ``?error=...&state=...``). Per TrueLayer: scambio ``code`` in access/refresh
    token. Per Enable Banking: ``POST /sessions`` con il ``code`` e salvataggio
    del ``session_id`` come ``external_connection_id``. Poi flusso comune
    (lista conti, ecc.).
    """
    state = request.GET.get("state") or ""
    error = request.GET.get("error") or ""
    code = request.GET.get("code") or ""

    pk = None
    if state.startswith("arboris-"):
        try:
            pk = int(state.split("arboris-", 1)[1])
        except (ValueError, IndexError):
            pk = None

    if not pk:
        messages.error(
            request,
            "Callback OAuth2 non valido: parametro 'state' mancante o malformato.",
        )
        return redirect("lista_connessioni_bancarie")

    connessione = get_object_or_404(ConnessioneBancaria, pk=pk)
    provider = connessione.provider
    if provider.tipo != TipoProviderBancario.PSD2:
        raise Http404()

    if error:
        connessione.stato = StatoConnessioneBancaria.ERRORE
        connessione.ultimo_errore = f"Error return: {error}"
        connessione.save(update_fields=["stato", "ultimo_errore", "data_aggiornamento"])
        messages.error(request, f"Autorizzazione negata o fallita: {error}")
        return redirect("lista_connessioni_bancarie")

    if not code:
        messages.error(request, "Callback OAuth2 senza 'code': autorizzazione non completata.")
        return redirect("lista_connessioni_bancarie")

    try:
        adapter = adapter_for_provider(provider, connessione=connessione)
    except Exception as exc:
        connessione.stato = StatoConnessioneBancaria.ERRORE
        connessione.ultimo_errore = str(exc)[:1000]
        connessione.save(update_fields=["stato", "ultimo_errore", "data_aggiornamento"])
        messages.error(request, f"Errore provider: {exc}")
        return redirect("lista_connessioni_bancarie")

    redirect_url = _oauth_redirect_uri(request, provider)

    if isinstance(adapter, TrueLayerAdapter):
        try:
            tokens = adapter.scambia_codice_autorizzazione(code, redirect_url=redirect_url)
        except TrueLayerError as exc:
            connessione.stato = StatoConnessioneBancaria.ERRORE
            connessione.ultimo_errore = str(exc)[:1000]
            connessione.save(update_fields=["stato", "ultimo_errore", "data_aggiornamento"])
            messages.error(request, f"Scambio code -> token fallito: {exc}")
            return redirect("lista_connessioni_bancarie")

        connessione.access_token_cifrato = cifra_testo(tokens.access_token) if tokens.access_token else ""
        connessione.refresh_token_cifrato = (
            cifra_testo(tokens.refresh_token) if tokens.refresh_token else ""
        )
        connessione.access_token_scadenza = tokens.access_token_expires_at
        connessione.save(
            update_fields=[
                "access_token_cifrato",
                "refresh_token_cifrato",
                "access_token_scadenza",
                "data_aggiornamento",
            ]
        )
        return _finalizza_connessione_psd2(request, connessione, adapter)

    if isinstance(adapter, EnableBankingAdapter):
        try:
            session_id = adapter.scambia_codice_sessione(code)
        except EnableBankingError as exc:
            connessione.stato = StatoConnessioneBancaria.ERRORE
            connessione.ultimo_errore = str(exc)[:1000]
            connessione.save(update_fields=["stato", "ultimo_errore", "data_aggiornamento"])
            messages.error(request, f"Scambio code -> sessione fallito: {exc}")
            return redirect("lista_connessioni_bancarie")

        connessione.external_connection_id = session_id
        connessione.save(
            update_fields=["external_connection_id", "data_aggiornamento"]
        )
        return _finalizza_connessione_psd2(request, connessione, adapter)

    messages.error(
        request,
        "Callback ricevuto ma l'adapter del provider non supporta questo flusso.",
    )
    return redirect("lista_connessioni_bancarie")


def sincronizza_conto_bancario(request, pk):
    conto = get_object_or_404(ContoBancario, pk=pk)

    if request.method != "POST":
        return redirect("lista_conti_bancari")

    if conto.provider is None or conto.provider.tipo != TipoProviderBancario.PSD2:
        messages.error(request, "Questo conto non e' collegato a un provider PSD2.")
        return redirect("lista_conti_bancari")

    try:
        log = sincronizza_conto_psd2(conto)
    except ProviderConfigurazioneMancante as exc:
        messages.error(request, str(exc))
        return redirect("lista_conti_bancari")
    except Exception as exc:
        messages.error(request, f"Sincronizzazione fallita: {exc}")
        return redirect("lista_conti_bancari")

    if log.esito == "ok":
        messages.success(
            request,
            f"Sincronizzazione del conto '{conto.nome_conto}' completata: "
            f"{log.movimenti_inseriti} nuovi movimenti.",
        )
    else:
        messages.warning(
            request,
            f"Sincronizzazione conclusa con stato '{log.get_esito_display()}'. "
            "Controlla i log per i dettagli.",
        )
    return redirect("lista_conti_bancari")


def elimina_connessione_psd2(request, pk):
    connessione = get_object_or_404(ConnessioneBancaria, pk=pk)

    count_conti = connessione.conti.count()

    if request.method == "POST":
        if count_conti:
            messages.error(
                request,
                "Impossibile eliminare la connessione: ha conti bancari collegati. "
                "Scollega o elimina prima i conti.",
            )
            return redirect("lista_connessioni_bancarie")

        connessione.delete()
        messages.success(request, "Connessione eliminata correttamente.")
        return redirect("lista_connessioni_bancarie")

    return render(
        request,
        "gestione_finanziaria/connessione_confirm_delete.html",
        {"connessione": connessione, "count_conti": count_conti},
    )


# =========================================================================
#  Pianificazione sincronizzazione PSD2
# =========================================================================


def pianificazione_sincronizzazione(request):
    """Configurazione dello scheduler di sincronizzazione PSD2 (singleton)."""
    config = get_or_create_singleton()

    if request.method == "POST":
        azione = request.POST.get("azione", "salva")

        if azione == "esegui":
            try:
                risultato = maybe_run_scheduled_sync(triggered_by=request.user, force=True)
            except Exception as exc:
                messages.error(request, f"Esecuzione fallita: {exc}")
            else:
                if risultato is None:
                    messages.warning(
                        request,
                        "Impossibile avviare la sincronizzazione: un'altra esecuzione "
                        "e' gia' in corso.",
                    )
                else:
                    messages.success(
                        request,
                        f"Sincronizzazione eseguita: {risultato.conti_sincronizzati} conti ok, "
                        f"{risultato.conti_in_errore} in errore.",
                    )
            return redirect("pianificazione_sincronizzazione")

        form = PianificazioneSincronizzazioneForm(request.POST, instance=config)
        if form.is_valid():
            form.save()
            messages.success(request, "Pianificazione aggiornata.")
            return redirect("pianificazione_sincronizzazione")
    else:
        form = PianificazioneSincronizzazioneForm(instance=config)

    conti = list(
        ContoBancario.objects.filter(
            attivo=True,
            provider__tipo=TipoProviderBancario.PSD2,
        )
        .exclude(external_account_id="")
        .select_related("provider", "connessione")
        .order_by("provider__nome", "nome_conto")
    )

    return render(
        request,
        "gestione_finanziaria/pianificazione_sincronizzazione.html",
        {
            "form": form,
            "config": config,
            "conti_target": conti,
            "prossima_esecuzione": prossima_esecuzione_prevista(config),
        },
    )


# =========================================================================
#  Riconciliazione movimenti con rate iscrizione
# =========================================================================


def lista_movimenti_da_riconciliare(request):
    """Elenco dei movimenti non ancora riconciliati, con filtri base."""
    queryset = (
        MovimentoFinanziario.objects.select_related("conto", "categoria", "rata_iscrizione")
        .exclude(stato_riconciliazione=StatoRiconciliazione.IGNORATO)
        .filter(stato_riconciliazione=StatoRiconciliazione.NON_RICONCILIATO)
        .filter(rata_iscrizione__isnull=True)
    )

    conto_id = request.GET.get("conto") or ""
    if conto_id.isdigit():
        queryset = queryset.filter(conto_id=int(conto_id))

    solo_entrate = request.GET.get("solo_entrate") == "1"
    if solo_entrate:
        queryset = queryset.filter(importo__gt=0)

    ordinamento = request.GET.get("ordinamento", "data")
    if ordinamento == "importo":
        queryset = queryset.order_by("-importo", "-data_contabile")
    else:
        queryset = queryset.order_by("-data_contabile", "-id")

    movimenti = list(queryset[:200])
    conti = ContoBancario.objects.filter(attivo=True).order_by("nome_conto")

    return render(
        request,
        "gestione_finanziaria/movimenti_da_riconciliare.html",
        {
            "movimenti": movimenti,
            "conti": conti,
            "conto_selezionato": conto_id,
            "solo_entrate": solo_entrate,
            "ordinamento": ordinamento,
            "totale_visualizzati": len(movimenti),
        },
    )


def riconcilia_movimento(request, pk):
    """Vista di riconciliazione di un singolo movimento."""
    movimento = get_object_or_404(
        MovimentoFinanziario.objects.select_related("conto", "categoria", "rata_iscrizione").prefetch_related(
            "riconciliazioni_rate__rata"
        ),
        pk=pk,
    )

    if request.method == "POST":
        azione = request.POST.get("azione", "")

        if azione == "annulla":
            annulla_riconciliazione(movimento)
            messages.success(request, "Riconciliazione annullata.")
            return redirect("riconcilia_movimento", pk=movimento.pk)

        if azione == "ignora":
            movimento.stato_riconciliazione = StatoRiconciliazione.IGNORATO
            movimento.save(update_fields=["stato_riconciliazione", "data_aggiornamento"])
            messages.success(request, "Movimento marcato come da ignorare.")
            return redirect("lista_movimenti_da_riconciliare")

        rata_pk = request.POST.get("rata_pk")
        if not rata_pk or not rata_pk.isdigit():
            messages.error(request, "Seleziona una rata candidata da collegare.")
        else:
            from economia.models.iscrizioni import RataIscrizione
            try:
                rata = RataIscrizione.objects.select_related(
                    "iscrizione__studente"
                ).get(pk=int(rata_pk))
            except RataIscrizione.DoesNotExist:
                messages.error(request, "Rata selezionata non trovata.")
                return redirect("riconcilia_movimento", pk=movimento.pk)

            marca = request.POST.get("marca_rata_pagata") == "1"
            try:
                riconcilia_movimento_con_rata(movimento, rata, utente=request.user, marca_rata_pagata=marca)
            except ValidationError as exc:
                for message in exc.messages:
                    messages.error(request, message)
            else:
                messages.success(
                    request,
                    f"Movimento riconciliato con {rata}. "
                    + ("Rata marcata come pagata." if marca else "Rata non modificata."),
                )
                return redirect("lista_movimenti_da_riconciliare")

    candidati = trova_rate_candidate(movimento)

    return render(
        request,
        "gestione_finanziaria/movimento_riconciliazione.html",
        {
            "movimento": movimento,
            "candidati": candidati,
            "gia_riconciliato": movimento.rata_iscrizione_id is not None or movimento.riconciliazioni_rate.exists(),
        },
    )


# =========================================================================
#  Report per categoria
# =========================================================================


def _anni_disponibili():
    from django.db.models.functions import ExtractYear

    anni = (
        MovimentoFinanziario.objects.annotate(anno=ExtractYear("data_contabile"))
        .values_list("anno", flat=True)
        .distinct()
        .order_by("-anno")
    )
    return [a for a in anni if a]


def _anni_scolastici_report():
    return AnnoScolastico.objects.order_by("-data_inizio", "-id")


def _resolve_anno_report(anni, raw_value):
    try:
        return int(raw_value) if raw_value else (anni[0] if anni else timezone.now().year)
    except ValueError:
        return anni[0] if anni else timezone.now().year


def _add_months_start(data_inizio, mesi):
    mese_index = (data_inizio.year * 12 + data_inizio.month - 1) + mesi
    return date(mese_index // 12, mese_index % 12 + 1, 1)


def _fine_mese(data_mese):
    return data_mese.replace(day=monthrange(data_mese.year, data_mese.month)[1])


def _periodo_rate_anno_scolastico(anno_scolastico):
    """
    Per i report finanziari scolastici usiamo il periodo economico delle rate,
    non per forza l'intero intervallo amministrativo dell'anno scolastico.
    """
    from economia.models.iscrizioni import CondizioneIscrizione

    condizioni = list(
        CondizioneIscrizione.objects.filter(
            anno_scolastico=anno_scolastico,
            attiva=True,
        )
    )
    if not condizioni:
        condizioni = list(
            CondizioneIscrizione.objects.filter(anno_scolastico=anno_scolastico)
        )

    periodi = []
    for condizione in condizioni:
        inizio = condizione.resolve_mese_prima_retta_date()
        if not inizio:
            continue
        numero_rate = max(condizione.numero_mensilita_default or 0, 1)
        fine = _fine_mese(_add_months_start(inizio, numero_rate - 1))
        periodi.append((inizio, fine))

    if periodi:
        return min(p[0] for p in periodi), max(p[1] for p in periodi)

    return anno_scolastico.data_inizio, anno_scolastico.data_fine


def _report_periodo_context(request, anni):
    anni_scolastici = list(_anni_scolastici_report())
    periodo_tipo = request.GET.get("periodo") or "solare"
    anno = _resolve_anno_report(anni, request.GET.get("anno"))
    anno_scolastico = None
    anno_scolastico_id = request.GET.get("anno_scolastico") or ""

    if periodo_tipo == "scolastico":
        if anno_scolastico_id.isdigit():
            anno_scolastico = next(
                (item for item in anni_scolastici if item.pk == int(anno_scolastico_id)),
                None,
            )
        if anno_scolastico is None and anni_scolastici:
            oggi = timezone.localdate()
            anno_scolastico = next(
                (
                    item
                    for item in anni_scolastici
                    if item.data_inizio <= oggi <= item.data_fine
                ),
                anni_scolastici[0],
            )
        if anno_scolastico is not None:
            anno_scolastico_id = str(anno_scolastico.pk)
            data_inizio, data_fine = _periodo_rate_anno_scolastico(anno_scolastico)
            periodo_label = f"anno scolastico {anno_scolastico.nome_anno_scolastico}"
        else:
            periodo_tipo = "solare"
            data_inizio = date(anno, 1, 1)
            data_fine = date(anno, 12, 31)
            periodo_label = f"anno {anno}"
    else:
        periodo_tipo = "solare"
        data_inizio = date(anno, 1, 1)
        data_fine = date(anno, 12, 31)
        periodo_label = f"anno {anno}"

    query_params = {
        "periodo": periodo_tipo,
        "anno": anno,
    }
    if anno_scolastico_id:
        query_params["anno_scolastico"] = anno_scolastico_id

    return {
        "periodo_tipo": periodo_tipo,
        "anno": anno,
        "anni_scolastici": anni_scolastici,
        "anno_scolastico": anno_scolastico,
        "anno_scolastico_selezionato": anno_scolastico_id,
        "data_inizio": data_inizio,
        "data_fine": data_fine,
        "periodo_label": periodo_label,
        "query_params": query_params,
    }


def _build_report_query(periodo_context, conto_id):
    params = dict(periodo_context["query_params"])
    if conto_id:
        params["conto"] = conto_id
    return urlencode(params)


def _mesi_report_periodo(data_inizio, data_fine):
    mesi_label = [
        "Gen", "Feb", "Mar", "Apr", "Mag", "Giu",
        "Lug", "Ago", "Set", "Ott", "Nov", "Dic",
    ]
    mesi = []
    anno = data_inizio.year
    mese = data_inizio.month
    while (anno, mese) <= (data_fine.year, data_fine.month):
        mesi.append(
            {
                "anno": anno,
                "mese": mese,
                "label": f"{mesi_label[mese - 1]} {anno}",
            }
        )
        mese += 1
        if mese > 12:
            mese = 1
            anno += 1
    return mesi


def _filtra_movimenti_report(request, queryset):
    conto_id = request.GET.get("conto") or ""
    if conto_id.isdigit():
        queryset = queryset.filter(conto_id=int(conto_id))
    return queryset, conto_id


def _categorie_report_tree():
    categorie = list(
        CategoriaFinanziaria.objects.filter(attiva=True)
        .select_related("parent")
        .order_by("tipo", "ordine", "nome")
    )
    figli_by_parent = {}
    for categoria in categorie:
        figli_by_parent.setdefault(categoria.parent_id, []).append(categoria)
    return figli_by_parent.get(None, []), figli_by_parent


def _categoria_discendant_ids(categoria, figli_by_parent):
    ids = [categoria.pk]
    for figlia in figli_by_parent.get(categoria.pk, []):
        ids.extend(_categoria_discendant_ids(figlia, figli_by_parent))
    return ids


def _report_category_tone(categoria, netto):
    if categoria.tipo == TipoCategoriaFinanziaria.ENTRATA:
        return "entrata"
    if categoria.tipo == TipoCategoriaFinanziaria.SPESA:
        return "spesa"
    return "entrata" if netto >= 0 else "spesa"


def _build_report_mensile_riga(categoria, livello, mappa, mesi_periodo, figli_by_parent):
    valori_mese = {(m["anno"], m["mese"]): Decimal("0") for m in mesi_periodo}
    for cid in _categoria_discendant_ids(categoria, figli_by_parent):
        for key, importo in (mappa.get(cid) or {}).items():
            if key in valori_mese:
                valori_mese[key] += importo or Decimal("0")

    figli = []
    for figlia in figli_by_parent.get(categoria.pk, []):
        riga_figlia = _build_report_mensile_riga(
            figlia,
            livello + 1,
            mappa,
            mesi_periodo,
            figli_by_parent,
        )
        if riga_figlia:
            figli.append(riga_figlia)

    totale_riga = sum(valori_mese.values(), Decimal("0"))
    if totale_riga == 0 and not figli:
        return None

    return {
        "categoria": categoria,
        "valori_mese": [valori_mese[(m["anno"], m["mese"])] for m in mesi_periodo],
        "valori_mese_map": valori_mese,
        "totale": totale_riga,
        "figli": figli,
        "livello": livello,
        "row_id": f"categoria-{categoria.pk}",
        "row_tone": _report_category_tone(categoria, totale_riga),
    }


def _build_report_annuale_riga(categoria, livello, per_categoria, figli_by_parent):
    entrate = Decimal("0")
    uscite = Decimal("0")
    for cid in _categoria_discendant_ids(categoria, figli_by_parent):
        blocco = per_categoria.get(cid)
        if blocco:
            entrate += blocco["entrate"]
            uscite += blocco["uscite"]

    figli = []
    for figlia in figli_by_parent.get(categoria.pk, []):
        riga_figlia = _build_report_annuale_riga(
            figlia,
            livello + 1,
            per_categoria,
            figli_by_parent,
        )
        if riga_figlia:
            figli.append(riga_figlia)

    if entrate == 0 and uscite == 0 and not figli:
        return None

    return {
        "categoria": categoria,
        "entrate": entrate,
        "uscite": uscite,
        "netto": entrate + uscite,
        "figli": figli,
        "livello": livello,
        "row_id": f"categoria-{categoria.pk}",
        "row_tone": _report_category_tone(categoria, entrate + uscite),
    }


def _sort_report_rows(righe, key):
    righe.sort(key=key)
    for riga in righe:
        _sort_report_rows(riga.get("figli", []), key)


def report_categorie_mensile(request):
    """
    Report entrate/uscite per categoria, pivot mensile su anno solare o scolastico.

    Rollup gerarchico: per ogni categoria radice il totale mostrato
    include i movimenti delle sottocategorie.
    """
    from django.db.models.functions import ExtractMonth, ExtractYear

    anni = _anni_disponibili()
    periodo_context = _report_periodo_context(request, anni)

    queryset = MovimentoFinanziario.objects.filter(
        data_contabile__gte=periodo_context["data_inizio"],
        data_contabile__lte=periodo_context["data_fine"],
    ).exclude(
        categoria__isnull=True
    )
    queryset, conto_id = _filtra_movimenti_report(request, queryset)

    aggregato = (
        queryset.annotate(anno_movimento=ExtractYear("data_contabile"), mese=ExtractMonth("data_contabile"))
        .values("categoria_id", "anno_movimento", "mese")
        .annotate(totale=Sum("importo"))
    )
    sintesi = queryset.aggregate(
        totale_entrate=Sum("importo", filter=Q(importo__gt=0)),
        totale_uscite=Sum("importo", filter=Q(importo__lt=0)),
    )
    totale_entrate = sintesi["totale_entrate"] or Decimal("0")
    totale_uscite = sintesi["totale_uscite"] or Decimal("0")

    mappa = {}
    for riga in aggregato:
        cat_id = riga["categoria_id"]
        anno_movimento = riga["anno_movimento"]
        mese = riga["mese"]
        if anno_movimento is None or mese is None:
            continue
        mappa.setdefault(cat_id, {})[(int(anno_movimento), int(mese))] = riga["totale"] or Decimal("0")

    categorie_root, figli_by_parent = _categorie_report_tree()

    mesi_periodo = _mesi_report_periodo(periodo_context["data_inizio"], periodo_context["data_fine"])
    righe_report = []
    totali_mensili = {(m["anno"], m["mese"]): Decimal("0") for m in mesi_periodo}
    totale_generale = Decimal("0")

    for root in categorie_root:
        riga = _build_report_mensile_riga(root, 0, mappa, mesi_periodo, figli_by_parent)
        if not riga:
            continue
        righe_report.append(riga)
        for m in mesi_periodo:
            key = (m["anno"], m["mese"])
            totali_mensili[key] += riga["valori_mese_map"][key]
        totale_generale += riga["totale"]

    conti = ContoBancario.objects.filter(attivo=True).order_by("nome_conto")
    report_querystring = _build_report_query(periodo_context, conto_id)

    return render(
        request,
        "gestione_finanziaria/report_categorie_mensile.html",
        {
            "anno": periodo_context["anno"],
            "anni_disponibili": anni,
            "anni_scolastici": periodo_context["anni_scolastici"],
            "periodo_tipo": periodo_context["periodo_tipo"],
            "periodo_label": periodo_context["periodo_label"],
            "anno_scolastico_selezionato": periodo_context["anno_scolastico_selezionato"],
            "righe": righe_report,
            "totali_mensili": [totali_mensili[(m["anno"], m["mese"])] for m in mesi_periodo],
            "totale_generale": totale_generale,
            "totale_entrate": totale_entrate,
            "totale_uscite": totale_uscite,
            "saldo_netto": totale_entrate + totale_uscite,
            "mesi": [m["label"] for m in mesi_periodo],
            "conti": conti,
            "conto_selezionato": conto_id,
            "report_querystring": report_querystring,
        },
    )


def report_categorie_annuale(request):
    """
    Report annuale per categoria: entrate totali, uscite totali, netto
    e peso % sul totale; rollup gerarchico su categorie radice.
    """
    anni = _anni_disponibili()
    periodo_context = _report_periodo_context(request, anni)

    queryset = MovimentoFinanziario.objects.filter(
        data_contabile__gte=periodo_context["data_inizio"],
        data_contabile__lte=periodo_context["data_fine"],
    ).exclude(
        categoria__isnull=True
    )
    queryset, conto_id = _filtra_movimenti_report(request, queryset)

    aggregato = (
        queryset.values("categoria_id")
        .annotate(
            totale_entrate=Sum("importo", filter=Q(importo__gt=0)),
            totale_uscite=Sum("importo", filter=Q(importo__lt=0)),
        )
    )
    per_categoria = {
        r["categoria_id"]: {
            "entrate": r["totale_entrate"] or Decimal("0"),
            "uscite": r["totale_uscite"] or Decimal("0"),
        }
        for r in aggregato
    }

    categorie_root, figli_by_parent = _categorie_report_tree()

    righe_entrate = []
    righe_uscite = []
    tot_entrate = Decimal("0")
    tot_uscite = Decimal("0")

    for root in categorie_root:
        riga = _build_report_annuale_riga(root, 0, per_categoria, figli_by_parent)
        if not riga:
            continue

        if root.tipo == TipoCategoriaFinanziaria.ENTRATA:
            righe_entrate.append(riga)
            tot_entrate += riga["entrate"]
        elif root.tipo == TipoCategoriaFinanziaria.SPESA:
            righe_uscite.append(riga)
            tot_uscite += riga["uscite"]
        else:
            # trasferimenti / misti: li collochiamo dove prevalgono
            if riga["netto"] >= 0:
                righe_entrate.append(riga)
                tot_entrate += riga["entrate"]
            else:
                righe_uscite.append(riga)
                tot_uscite += riga["uscite"]

    def _aggiungi_percentuali(righe, totale):
        if totale == 0:
            for r in righe:
                r["percentuale"] = Decimal("0")
                _aggiungi_percentuali(r.get("figli", []), totale)
            return
        for r in righe:
            delta = r["entrate"] if r["entrate"] else (r["uscite"].copy_abs() if r["uscite"] else Decimal("0"))
            totale_abs = totale.copy_abs() if hasattr(totale, "copy_abs") else abs(totale)
            if totale_abs == 0:
                r["percentuale"] = Decimal("0")
            else:
                r["percentuale"] = (delta / totale_abs * Decimal("100")).quantize(Decimal("0.1"))
            _aggiungi_percentuali(r.get("figli", []), totale)

    _aggiungi_percentuali(righe_entrate, tot_entrate)
    _aggiungi_percentuali(righe_uscite, tot_uscite)

    _sort_report_rows(righe_entrate, key=lambda r: r["entrate"] * Decimal("-1"))
    _sort_report_rows(righe_uscite, key=lambda r: r["uscite"])  # piu' negativo prima

    conti = ContoBancario.objects.filter(attivo=True).order_by("nome_conto")
    report_querystring = _build_report_query(periodo_context, conto_id)

    return render(
        request,
        "gestione_finanziaria/report_categorie_annuale.html",
        {
            "anno": periodo_context["anno"],
            "anni_disponibili": anni,
            "anni_scolastici": periodo_context["anni_scolastici"],
            "periodo_tipo": periodo_context["periodo_tipo"],
            "periodo_label": periodo_context["periodo_label"],
            "anno_scolastico_selezionato": periodo_context["anno_scolastico_selezionato"],
            "righe_entrate": righe_entrate,
            "righe_uscite": righe_uscite,
            "totale_entrate": tot_entrate,
            "totale_uscite": tot_uscite,
            "saldo_netto": tot_entrate + tot_uscite,
            "conti": conti,
            "conto_selezionato": conto_id,
            "report_querystring": report_querystring,
        },
    )


