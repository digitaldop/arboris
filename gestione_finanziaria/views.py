import secrets
from datetime import date
from decimal import Decimal
from urllib.parse import urlencode

from django.contrib import messages
from django.core.cache import cache
from django.db.models import Count, Q, Sum
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from anagrafica.views import is_popup_request, popup_delete_response, popup_select_response
from scuola.models import AnnoScolastico

from .forms import (
    CategoriaSpesaForm,
    CategoriaFinanziariaForm,
    ContoBancarioForm,
    DocumentoFornitoreForm,
    FornitoreForm,
    ImportEstrattoContoForm,
    MovimentoFinanziarioForm,
    NuovaConnessioneBancariaForm,
    PianificazioneSincronizzazioneForm,
    ProviderBancarioForm,
    ProviderPsd2ConfigForm,
    RegolaCategorizzazioneForm,
    ScadenzaPagamentoFornitoreFormSet,
)
from .importers import Camt053Parser, CsvImporter, CsvImporterConfig, detect_csv_import_config
from .importers.service import importa_movimenti_da_file
from .models import (
    CategoriaSpesa,
    CategoriaFinanziaria,
    ConnessioneBancaria,
    ContoBancario,
    DocumentoFornitore,
    Fornitore,
    MovimentoFinanziario,
    OrigineMovimento,
    ProviderBancario,
    RegolaCategorizzazione,
    ScadenzaPagamentoFornitore,
    SincronizzazioneLog,
    StatoConnessioneBancaria,
    StatoDocumentoFornitore,
    StatoScadenzaFornitore,
    StatoRiconciliazione,
    TipoCategoriaFinanziaria,
    TipoProviderBancario,
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
    annulla_riconciliazione,
    applica_regole_a_movimento,
    calcola_hash_deduplica_movimento,
    ricalcola_saldo_corrente_conto,
    riconcilia_movimento_con_rata,
    sincronizza_conto_psd2,
    trova_rate_candidate,
)


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
    conti = ContoBancario.objects.filter(attivo=True).order_by("nome_conto")
    saldo_totale = conti.aggregate(totale=Sum("saldo_corrente"))["totale"] or Decimal("0")

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

    return render(
        request,
        "gestione_finanziaria/dashboard.html",
        {
            "conti": conti,
            "saldo_totale": saldo_totale,
            "ultimi_movimenti": ultimi_movimenti,
            "movimenti_senza_categoria": movimenti_senza_categoria,
            "categorie_attive": categorie_attive,
            "regole_attive": regole_attive,
            "fornitori_attivi": fornitori_attivi,
            "scadenze_fornitori_aperte": scadenze_fornitori_aperte,
        },
    )


# =========================================================================
#  Fornitori, categorie spesa e documenti passivi
# =========================================================================


def _aggiorna_stato_documento_da_scadenze(documento):
    if documento.stato == StatoDocumentoFornitore.ANNULLATO:
        return documento

    scadenze = documento.scadenze.exclude(stato=StatoScadenzaFornitore.ANNULLATA)
    if not scadenze.exists():
        return documento

    pagato = scadenze.aggregate(totale=Sum("importo_pagato"))["totale"] or Decimal("0.00")
    totale = documento.totale or Decimal("0.00")
    if totale > Decimal("0.00") and pagato >= totale:
        nuovo_stato = StatoDocumentoFornitore.PAGATO
    elif pagato > Decimal("0.00"):
        nuovo_stato = StatoDocumentoFornitore.PARZIALMENTE_PAGATO
    else:
        nuovo_stato = StatoDocumentoFornitore.DA_PAGARE

    if documento.stato != nuovo_stato:
        documento.stato = nuovo_stato
        documento.save(update_fields=["stato", "data_aggiornamento"])
    return documento


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
    categorie = CategoriaSpesa.objects.annotate(
        numero_fornitori=Count("fornitori", distinct=True),
        numero_documenti=Count("documenti_fornitori", distinct=True),
    ).order_by("ordine", "nome")
    return render(
        request,
        "gestione_finanziaria/categorie_spesa_list.html",
        {"categorie": categorie},
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
    categoria = get_object_or_404(CategoriaSpesa, pk=pk)
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
    categoria = get_object_or_404(CategoriaSpesa, pk=pk)
    count_fornitori = categoria.fornitori.count()
    count_documenti = categoria.documenti_fornitori.count()
    ha_vincoli = bool(count_fornitori or count_documenti)

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
                        "ha_vincoli": ha_vincoli,
                        "target_input_name": _popup_target_input_name(request),
                    },
                )
            messages.error(
                request,
                "Impossibile eliminare la categoria: e' collegata a fornitori o documenti. "
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
            "categorie": CategoriaSpesa.objects.filter(attiva=True).order_by("ordine", "nome"),
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
        {"form": form, "fornitore": None},
    )


def modifica_fornitore(request, pk):
    popup = is_popup_request(request)
    fornitore = get_object_or_404(Fornitore.objects.select_related("categoria_spesa"), pk=pk)
    if request.method == "POST":
        form = FornitoreForm(request.POST, instance=fornitore)
        if form.is_valid():
            fornitore = form.save()
            if popup:
                return popup_select_response(request, "fornitore", fornitore.pk, str(fornitore))
            messages.success(request, "Fornitore aggiornato correttamente.")
            return redirect("modifica_fornitore", pk=fornitore.pk)
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
        DocumentoFornitore.objects.select_related("fornitore", "categoria_spesa")
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
        documenti = documenti.filter(categoria_spesa_id=int(categoria_id))
    if stato:
        documenti = documenti.filter(stato=stato)

    return render(
        request,
        "gestione_finanziaria/documenti_fornitori_list.html",
        {
            "documenti": documenti,
            "fornitori": Fornitore.objects.filter(attivo=True).order_by("denominazione"),
            "categorie": CategoriaSpesa.objects.filter(attiva=True).order_by("ordine", "nome"),
            "stati": StatoDocumentoFornitore.choices,
            "q": q,
            "fornitore_selezionato": fornitore_id,
            "categoria_selezionata": categoria_id,
            "stato": stato,
        },
    )


def _documento_form_context(form, formset, documento):
    return {
        "form": form,
        "formset": formset,
        "documento": documento,
    }


def crea_documento_fornitore(request):
    if request.method == "POST":
        form = DocumentoFornitoreForm(request.POST, request.FILES)
        formset = ScadenzaPagamentoFornitoreFormSet(request.POST, instance=DocumentoFornitore())
        if form.is_valid() and formset.is_valid():
            documento = form.save()
            formset.instance = documento
            formset.save()
            _aggiorna_stato_documento_da_scadenze(documento)
            messages.success(request, "Documento fornitore creato correttamente.")
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
        formset = ScadenzaPagamentoFornitoreFormSet(instance=DocumentoFornitore())

    return render(
        request,
        "gestione_finanziaria/documento_fornitore_form.html",
        _documento_form_context(form, formset, None),
    )


def modifica_documento_fornitore(request, pk):
    documento = get_object_or_404(DocumentoFornitore.objects.select_related("fornitore", "categoria_spesa"), pk=pk)
    if request.method == "POST":
        form = DocumentoFornitoreForm(request.POST, request.FILES, instance=documento)
        formset = ScadenzaPagamentoFornitoreFormSet(request.POST, instance=documento)
        if form.is_valid() and formset.is_valid():
            documento = form.save()
            formset.save()
            _aggiorna_stato_documento_da_scadenze(documento)
            messages.success(request, "Documento fornitore aggiornato correttamente.")
            return redirect("modifica_documento_fornitore", pk=documento.pk)
    else:
        form = DocumentoFornitoreForm(instance=documento)
        formset = ScadenzaPagamentoFornitoreFormSet(instance=documento)

    return render(
        request,
        "gestione_finanziaria/documento_fornitore_form.html",
        _documento_form_context(form, formset, documento),
    )


def elimina_documento_fornitore(request, pk):
    documento = get_object_or_404(DocumentoFornitore.objects.select_related("fornitore"), pk=pk)
    if request.method == "POST":
        documento.delete()
        messages.success(request, "Documento fornitore eliminato correttamente.")
        return redirect("lista_documenti_fornitori")

    return render(
        request,
        "gestione_finanziaria/documento_fornitore_confirm_delete.html",
        {"documento": documento},
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
            "categorie": CategoriaSpesa.objects.filter(attiva=True).order_by("ordine", "nome"),
            "fornitori": Fornitore.objects.filter(attivo=True).order_by("denominazione"),
            "categoria_selezionata": categoria_id,
            "fornitore_selezionato": fornitore_id,
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
    conti = (
        ContoBancario.objects.select_related("provider", "connessione")
        .order_by("nome_conto")
    )
    return render(
        request,
        "gestione_finanziaria/conti_bancari_list.html",
        {"conti": conti},
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
#  Movimenti finanziari - lista + CRUD manuale
# =========================================================================


def lista_movimenti_finanziari(request):
    movimenti = (
        MovimentoFinanziario.objects.select_related("conto", "categoria", "categoria__parent")
        .order_by("-data_contabile", "-id")
    )

    conti_filter = request.GET.get("conto")
    categoria_filter = request.GET.get("categoria")
    origine_filter = request.GET.get("origine")

    if conti_filter:
        movimenti = movimenti.filter(conto_id=conti_filter)
    if categoria_filter == "none":
        movimenti = movimenti.filter(categoria__isnull=True)
    elif categoria_filter:
        movimenti = movimenti.filter(categoria_id=categoria_filter)
    if origine_filter:
        movimenti = movimenti.filter(origine=origine_filter)

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
            "conto_selezionato": conti_filter or "",
            "categoria_selezionata": categoria_filter or "",
            "origine_selezionata": origine_filter or "",
        },
    )


def crea_movimento_manuale(request):
    popup = is_popup_request(request)
    if request.method == "POST":
        form = MovimentoFinanziarioForm(request.POST)
        if form.is_valid():
            movimento = form.save(commit=False)
            movimento.origine = OrigineMovimento.MANUALE

            if not movimento.categoria_id:
                applica_regole_a_movimento(movimento)

            movimento.save()

            if movimento.conto_id and movimento.incide_su_saldo_banca:
                ricalcola_saldo_corrente_conto(movimento.conto)

            if popup:
                return popup_select_response(request, "movimento_finanziario", movimento.pk, str(movimento))
            messages.success(request, "Movimento manuale registrato correttamente.")
            return redirect("lista_movimenti_finanziari")
    else:
        form = MovimentoFinanziarioForm(
            initial={
                "data_contabile": timezone.now().date(),
                "valuta": "EUR",
            }
        )

    if popup:
        return render(
            request,
            "gestione_finanziaria/entity_popup_form.html",
            _generic_popup_form_context(request, form, "Nuovo movimento"),
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
    categorie = (
        CategoriaFinanziaria.objects.select_related("parent")
        .order_by("parent__nome", "ordine", "nome")
    )
    return render(
        request,
        "gestione_finanziaria/categorie_list.html",
        {
            "categorie": categorie,
            "tipo_choices": TipoCategoriaFinanziaria.choices,
        },
    )


def crea_categoria_finanziaria(request):
    if request.method == "POST":
        form = CategoriaFinanziariaForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Categoria finanziaria creata correttamente.")
            return redirect("lista_categorie_finanziarie")
    else:
        form = CategoriaFinanziariaForm()

    return render(
        request,
        "gestione_finanziaria/categoria_form.html",
        {"form": form, "categoria": None},
    )


def modifica_categoria_finanziaria(request, pk):
    categoria = get_object_or_404(CategoriaFinanziaria, pk=pk)

    if request.method == "POST":
        form = CategoriaFinanziariaForm(request.POST, instance=categoria)
        if form.is_valid():
            form.save()
            messages.success(request, "Categoria finanziaria aggiornata correttamente.")
            return redirect("lista_categorie_finanziarie")
    else:
        form = CategoriaFinanziariaForm(instance=categoria)

    return render(
        request,
        "gestione_finanziaria/categoria_form.html",
        {"form": form, "categoria": categoria},
    )


def elimina_categoria_finanziaria(request, pk):
    categoria = get_object_or_404(CategoriaFinanziaria, pk=pk)

    count_movimenti = categoria.movimenti.count()
    count_figlie = categoria.figli.count()
    count_regole = categoria.regole.count()
    ha_vincoli = bool(count_movimenti or count_figlie or count_regole)

    if request.method == "POST":
        if ha_vincoli:
            messages.error(
                request,
                "Impossibile eliminare la categoria: ha elementi collegati. Puoi disattivarla invece di eliminarla.",
            )
            return redirect("lista_categorie_finanziarie")

        categoria.delete()
        messages.success(request, "Categoria finanziaria eliminata correttamente.")
        return redirect("lista_categorie_finanziarie")

    return render(
        request,
        "gestione_finanziaria/categoria_confirm_delete.html",
        {
            "categoria": categoria,
            "count_movimenti": count_movimenti,
            "count_figlie": count_figlie,
            "count_regole": count_regole,
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

    for movimento in parsed:
        date.append(movimento.data_contabile)
        if movimento.importo > 0:
            entrate += movimento.importo
        elif movimento.importo < 0:
            uscite += abs(movimento.importo)

        is_duplicate = False
        if conto:
            hash_dedup = calcola_hash_deduplica_movimento(
                conto_id=conto.id,
                data_contabile=movimento.data_contabile,
                importo=movimento.importo,
                descrizione=movimento.descrizione,
                controparte=movimento.controparte,
                iban_controparte=movimento.iban_controparte,
            )
            duplicate_filter = Q(conto=conto, hash_deduplica=hash_dedup)
            if movimento.provider_transaction_id:
                duplicate_filter |= Q(conto=conto, provider_transaction_id=movimento.provider_transaction_id)
            is_duplicate = MovimentoFinanziario.objects.filter(duplicate_filter).exists()
            if is_duplicate:
                duplicati += 1

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
            )
            cache.delete(f"gf-import-estratto:{import_token}")

            if risultato.inseriti:
                messages.success(
                    request,
                    f"Import completato: {risultato.inseriti} movimenti inseriti "
                    f"(riconciliati: {risultato.riconciliati}, duplicati scartati: {risultato.duplicati}).",
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
                if _is_probable_xml(raw_bytes, getattr(uploaded, "name", "")):
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
            else:
                parser_type = "csv"
                parser = CsvImporter(_build_manual_csv_config(form))

            selected_conto = conto or detected_conto
            preview = _build_import_preview(parser, raw_bytes, selected_conto)
            if not preview["totale_letti"]:
                messages.error(request, "Non ho trovato movimenti importabili nel file caricato.")
            else:
                import_token = secrets.token_urlsafe(24)
                csv_config = _csv_config_to_dict(parser.config) if isinstance(parser, CsvImporter) else None
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
        form = ProviderPsd2ConfigForm(request.POST)
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
            config.ultimo_run_at = None
            config.save(update_fields=["ultimo_run_at", "data_aggiornamento"])
            try:
                risultato = maybe_run_scheduled_sync(triggered_by=request.user)
            except Exception as exc:
                messages.error(request, f"Esecuzione fallita: {exc}")
            else:
                if risultato is None:
                    messages.warning(
                        request,
                        "Impossibile avviare la sincronizzazione: pianificazione disattivata "
                        "o un'altra esecuzione e' gia' in corso.",
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
        MovimentoFinanziario.objects.select_related("conto", "categoria", "rata_iscrizione"),
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
                    "iscrizione__studente__famiglia"
                ).get(pk=int(rata_pk))
            except RataIscrizione.DoesNotExist:
                messages.error(request, "Rata selezionata non trovata.")
                return redirect("riconcilia_movimento", pk=movimento.pk)

            marca = request.POST.get("marca_rata_pagata") == "1"
            riconcilia_movimento_con_rata(movimento, rata, utente=request.user, marca_rata_pagata=marca)
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
            "gia_riconciliato": movimento.rata_iscrizione_id is not None,
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
            data_inizio = anno_scolastico.data_inizio
            data_fine = anno_scolastico.data_fine
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


def _espandi_categoria_root(categoria):
    """Ritorna la lista di id delle categorie (self + tutti i discendenti)."""
    ids = [categoria.pk]
    stack = [categoria]
    while stack:
        corrente = stack.pop()
        figli = list(CategoriaFinanziaria.objects.filter(parent=corrente).only("id"))
        for f in figli:
            ids.append(f.pk)
            stack.append(f)
    return ids


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

    mappa = {}
    for riga in aggregato:
        cat_id = riga["categoria_id"]
        anno_movimento = riga["anno_movimento"]
        mese = riga["mese"]
        if anno_movimento is None or mese is None:
            continue
        mappa.setdefault(cat_id, {})[(int(anno_movimento), int(mese))] = riga["totale"] or Decimal("0")

    categorie_root = list(
        CategoriaFinanziaria.objects.filter(parent__isnull=True, attiva=True).order_by(
            "tipo", "ordine", "nome"
        )
    )

    mesi_periodo = _mesi_report_periodo(periodo_context["data_inizio"], periodo_context["data_fine"])
    righe_report = []
    totali_mensili = {(m["anno"], m["mese"]): Decimal("0") for m in mesi_periodo}
    totale_generale = Decimal("0")

    for root in categorie_root:
        ids_inclusi = _espandi_categoria_root(root)
        valori_mese = {(m["anno"], m["mese"]): Decimal("0") for m in mesi_periodo}
        for cid in ids_inclusi:
            for key, importo in (mappa.get(cid) or {}).items():
                if key in valori_mese:
                    valori_mese[key] += importo or Decimal("0")

        totale_riga = sum(valori_mese.values(), Decimal("0"))
        if totale_riga == 0:
            # nascondiamo le categorie senza movimenti per mantenere il report leggibile
            continue
        righe_report.append(
            {
                "categoria": root,
                "valori_mese": [valori_mese[(m["anno"], m["mese"])] for m in mesi_periodo],
                "totale": totale_riga,
            }
        )
        for m in mesi_periodo:
            key = (m["anno"], m["mese"])
            totali_mensili[key] += valori_mese[key]
        totale_generale += totale_riga

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

    categorie_root = list(
        CategoriaFinanziaria.objects.filter(parent__isnull=True, attiva=True).order_by(
            "tipo", "ordine", "nome"
        )
    )

    righe_entrate = []
    righe_uscite = []
    tot_entrate = Decimal("0")
    tot_uscite = Decimal("0")

    for root in categorie_root:
        ids_inclusi = _espandi_categoria_root(root)
        entrate = Decimal("0")
        uscite = Decimal("0")
        for cid in ids_inclusi:
            blocco = per_categoria.get(cid)
            if blocco:
                entrate += blocco["entrate"]
                uscite += blocco["uscite"]

        if entrate == 0 and uscite == 0:
            continue

        riga = {
            "categoria": root,
            "entrate": entrate,
            "uscite": uscite,
            "netto": entrate + uscite,
        }
        if root.tipo == TipoCategoriaFinanziaria.ENTRATA:
            righe_entrate.append(riga)
            tot_entrate += entrate
        elif root.tipo == TipoCategoriaFinanziaria.USCITA:
            righe_uscite.append(riga)
            tot_uscite += uscite
        else:
            # trasferimenti / misti: li collochiamo dove prevalgono
            if entrate + uscite >= 0:
                righe_entrate.append(riga)
                tot_entrate += entrate
            else:
                righe_uscite.append(riga)
                tot_uscite += uscite

    def _aggiungi_percentuali(righe, totale):
        if totale == 0:
            for r in righe:
                r["percentuale"] = Decimal("0")
            return
        for r in righe:
            delta = r["entrate"] if r["entrate"] else (r["uscite"].copy_abs() if r["uscite"] else Decimal("0"))
            totale_abs = totale.copy_abs() if hasattr(totale, "copy_abs") else abs(totale)
            if totale_abs == 0:
                r["percentuale"] = Decimal("0")
            else:
                r["percentuale"] = (delta / totale_abs * Decimal("100")).quantize(Decimal("0.1"))

    _aggiungi_percentuali(righe_entrate, tot_entrate)
    _aggiungi_percentuali(righe_uscite, tot_uscite)

    righe_entrate.sort(key=lambda r: r["entrate"], reverse=True)
    righe_uscite.sort(key=lambda r: r["uscite"])  # piu' negativo prima

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


