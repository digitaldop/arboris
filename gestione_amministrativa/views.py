import mimetypes
from decimal import Decimal
from pathlib import Path
from urllib.parse import urlencode

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db.models import Count, Q, Sum
from django.db.utils import OperationalError, ProgrammingError
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import content_disposition_header

from anagrafica.contact_services import sync_principal_contacts
from anagrafica.forms import (
    anagrafica_contact_formsets_are_valid,
    anagrafica_contact_formsets_have_errors,
    build_anagrafica_contact_formsets,
    save_anagrafica_contact_formsets,
)
from anagrafica.models import Familiare, Nazione, RelazioneFamiliare
from anagrafica.storage_utils import DOCUMENT_STORAGE_ERROR_TYPES, build_document_storage_error_message
from anagrafica.views import is_popup_request, popup_delete_response, popup_select_response
from economia.models import Iscrizione
from gestione_finanziaria.models import MovimentoFinanziario, OrigineMovimento, StatoRiconciliazione
from gestione_finanziaria.services import aggiorna_stato_riconciliazione_movimento, importo_movimento_disponibile_fornitori
from sistema.models import SistemaImpostazioniGenerali
from scuola.utils import resolve_default_anno_scolastico

from .forms import (
    BustaPagaDipendenteForm,
    ContrattoDipendenteForm,
    DipendenteForm,
    ParametroCalcoloStipendioForm,
    SimulazioneCostoDipendenteForm,
    TipoContrattoDipendenteForm,
)
from .models import (
    BustaPagaDipendente,
    CategoriaDatoPayrollUfficiale,
    ContrattoDipendente,
    DatoPayrollUfficiale,
    Dipendente,
    PagamentoBustaPagaDipendente,
    ParametroCalcoloStipendio,
    RuoloAnagraficoDipendente,
    SimulazioneCostoDipendente,
    StatoBustaPaga,
    StatoDipendente,
    TipoContrattoDipendente,
)
from .services import compensi_lavorativi_dipendente, contratto_applicabile, crea_o_aggiorna_previsione_busta_paga


ZERO = Decimal("0.00")


def gestione_dipendenti_dettagliata_attiva():
    try:
        impostazioni = SistemaImpostazioniGenerali.objects.first()
    except (OperationalError, ProgrammingError):
        return False
    return bool(getattr(impostazioni, "gestione_dipendenti_dettagliata_attiva", False))


def redirect_if_dipendenti_simple(request):
    if gestione_dipendenti_dettagliata_attiva():
        return None
    messages.info(
        request,
        "La gestione dettagliata dei dipendenti e disattivata: usa dipendenti, contratti e buste paga.",
    )
    return redirect("lista_dipendenti")


def _current_period():
    today = timezone.localdate()
    return today.year, today.month


def _aggiorna_riconciliazione_movimenti_busta(*movimento_ids):
    ids = {int(movimento_id) for movimento_id in movimento_ids if movimento_id}
    if not ids:
        return
    for movimento in MovimentoFinanziario.objects.filter(pk__in=ids):
        aggiorna_stato_riconciliazione_movimento(movimento)


def _importo_busta_paga_da_riconciliare(busta):
    return abs(busta.importo_residuo_pagamento or ZERO)


def _pagamenti_busta_movimento_ids(busta):
    if not getattr(busta, "pk", None):
        return set()
    return set(
        busta.pagamenti.filter(movimento_id__isnull=False).values_list("movimento_id", flat=True)
    )


def _movimento_disponibile_per_busta(movimento):
    return importo_movimento_disponibile_fornitori(movimento)


def _score_movimento_busta(movimento, busta, residuo_busta, disponibile, movimento_ids_collegati=None):
    score = 0
    motivazioni = []
    importo_assoluto = abs(movimento.importo or ZERO)
    movimento_ids_collegati = movimento_ids_collegati or set()
    if importo_assoluto == residuo_busta:
        score += 55
        motivazioni.append("Importo identico al residuo della busta")
    elif disponibile == residuo_busta:
        score += 45
        motivazioni.append("Disponibile identico al residuo della busta")
    elif disponibile > residuo_busta:
        score += 25
        motivazioni.append("Movimento capiente per il residuo della busta")
    elif ZERO < disponibile < residuo_busta:
        score += 20
        motivazioni.append("Movimento utilizzabile come pagamento parziale")

    data_suggerita = busta.data_pagamento_suggerita
    if data_suggerita and movimento.data_contabile:
        delta_giorni = abs((movimento.data_contabile - data_suggerita).days)
        if delta_giorni <= 7:
            score += 25
            motivazioni.append(f"Data vicina al pagamento previsto (+/- {delta_giorni} gg)")
        elif delta_giorni <= 30:
            score += 10
            motivazioni.append(f"Data entro 30 giorni dal pagamento previsto ({delta_giorni} gg)")

    testo_movimento = " ".join(
        [
            movimento.descrizione or "",
            movimento.controparte or "",
            movimento.sostenitore or "",
        ]
    ).lower()
    dipendente = busta.dipendente
    nome = (getattr(dipendente, "nome", "") or "").strip().lower()
    cognome = (getattr(dipendente, "cognome", "") or "").strip().lower()
    if nome and cognome and nome in testo_movimento and cognome in testo_movimento:
        score += 30
        motivazioni.append("Nome e cognome del dipendente presenti nella causale")
    elif cognome and cognome in testo_movimento:
        score += 15
        motivazioni.append("Cognome del dipendente presente nella causale")

    if busta.movimento_pagamento_id == movimento.pk or movimento.pk in movimento_ids_collegati:
        score += 80
        motivazioni.insert(0, "Movimento gia collegato a questa busta")

    return min(score, 100), motivazioni or ["Movimento disponibile per riconciliazione manuale"]


def _movimenti_candidati_busta_paga(busta, *, limite=20):
    residuo_busta = _importo_busta_paga_da_riconciliare(busta)
    if residuo_busta <= ZERO:
        return []
    movimento_ids_collegati = _pagamenti_busta_movimento_ids(busta)

    queryset = (
        MovimentoFinanziario.objects.select_related("conto", "categoria")
        .filter(importo__lt=0)
        .exclude(stato_riconciliazione=StatoRiconciliazione.IGNORATO)
        .filter(
            Q(origine__in=[OrigineMovimento.BANCA, OrigineMovimento.IMPORT_FILE])
            | Q(incide_su_saldo_banca=True)
            | Q(pk=busta.movimento_pagamento_id)
            | Q(pk__in=movimento_ids_collegati)
        )
        .order_by("-data_contabile", "-id")
    )

    candidati = []
    for movimento in queryset[:300]:
        disponibile = _movimento_disponibile_per_busta(movimento)
        is_current = movimento.pk == busta.movimento_pagamento_id or movimento.pk in movimento_ids_collegati
        if not is_current and disponibile <= ZERO:
            continue
        score, motivazioni = _score_movimento_busta(
            movimento,
            busta,
            residuo_busta,
            disponibile,
            movimento_ids_collegati,
        )
        candidati.append(
            {
                "movimento": movimento,
                "importo_disponibile": disponibile,
                "importo_collegabile": min(disponibile, residuo_busta),
                "score_percentuale": score,
                "motivazioni": motivazioni,
                "is_current": is_current,
            }
        )

    return sorted(
        candidati,
        key=lambda item: (0 if item["is_current"] else 1, -item["score_percentuale"], -item["movimento"].data_contabile.toordinal(), -item["movimento"].pk),
    )[:limite]


def _busta_paga_file_name(busta):
    if not busta or not busta.file_busta_paga:
        return ""
    return Path(busta.file_busta_paga.name).name


def _registra_pagamento_busta_da_movimento(busta, movimento, importo):
    residuo_busta = busta.importo_residuo_pagamento
    if residuo_busta <= ZERO and not busta.pagamenti.exists() and busta.movimento_pagamento_id == movimento.pk:
        residuo_busta = abs(busta.importo_netto_riepilogo or ZERO)
    importo = min(abs(Decimal(importo or ZERO)), residuo_busta)
    if importo <= ZERO:
        raise ValidationError("Il movimento selezionato non ha disponibilita residua per questa busta paga.")

    pagamento = PagamentoBustaPagaDipendente.objects.filter(
        busta_paga=busta,
        movimento=movimento,
    ).first()
    if pagamento:
        pagamento.importo = pagamento.importo + importo
        pagamento.data_pagamento = movimento.data_contabile
        pagamento.save(update_fields=["importo", "data_pagamento", "data_aggiornamento"])
    else:
        pagamento = PagamentoBustaPagaDipendente.objects.create(
            busta_paga=busta,
            movimento=movimento,
            importo=importo,
            data_pagamento=movimento.data_contabile,
            note="Riconciliazione pagamento busta paga",
        )

    busta.movimento_pagamento = movimento
    update_fields = ["movimento_pagamento", "data_aggiornamento"]
    if busta.importo_residuo_pagamento <= ZERO and not busta.data_pagamento_effettiva:
        busta.data_pagamento_effettiva = movimento.data_contabile
        update_fields.append("data_pagamento_effettiva")
    busta.save(update_fields=update_fields)
    return pagamento


def _sincronizza_pagamento_busta_da_movimento_field(busta):
    if not busta.movimento_pagamento_id:
        return None
    if busta.pagamenti.filter(movimento_id=busta.movimento_pagamento_id).exists():
        return None
    movimento = busta.movimento_pagamento
    disponibile = _movimento_disponibile_per_busta(movimento)
    importo = min(disponibile, abs(busta.importo_netto_riepilogo or ZERO))
    if importo <= ZERO:
        return None
    return _registra_pagamento_busta_da_movimento(busta, movimento, importo)


def _ruoli_for_scope(scope):
    if scope == "educatori":
        return [RuoloAnagraficoDipendente.EDUCATORE]
    return [RuoloAnagraficoDipendente.DIPENDENTE]


def _dipendente_labels(scope):
    if scope == "educatori":
        try:
            impostazioni = SistemaImpostazioniGenerali.objects.first()
        except (OperationalError, ProgrammingError):
            impostazioni = None
        singular_cap = getattr(impostazioni, "termine_educatore_singolare", "Educatore") if impostazioni else "Educatore"
        plural_cap = getattr(impostazioni, "termine_educatore_plurale", "Educatori") if impostazioni else "Educatori"
        singular = singular_cap.lower()
        plural = plural_cap.lower()
        return {
            "scope": "educatori",
            "title": plural_cap,
            "singular": singular,
            "singular_cap": singular_cap,
            "plural": plural,
            "plural_cap": plural_cap,
            "subtitle": f"Archivio {plural}, classi principali, contratti e documenti collegati",
            "list_title": f"Elenco {plural}",
            "new_label": f"Nuovo {singular}",
            "list_url": "lista_educatori",
            "create_url": "crea_educatore",
            "detail_url": "modifica_educatore",
            "delete_url": "elimina_educatore",
            "icon": "student",
        }
    return {
        "scope": "dipendenti",
        "title": "Dipendenti",
        "singular": "dipendente",
        "singular_cap": "Dipendente",
        "plural": "dipendenti",
        "plural_cap": "Dipendenti",
        "subtitle": "Archivio dipendenti, contratti e previsioni retributive",
        "list_title": "Elenco dipendenti",
        "new_label": "Nuovo dipendente",
        "list_url": "lista_dipendenti",
        "create_url": "crea_dipendente",
        "detail_url": "modifica_dipendente",
        "delete_url": "elimina_dipendente",
        "icon": "briefcase",
    }


def _studenti_classe_principale(dipendente):
    if not dipendente or not dipendente.is_educatore:
        return []

    if not dipendente.classe_principale_id and not getattr(dipendente, "gruppo_classe_principale_id", None):
        return []

    anno = resolve_default_anno_scolastico()
    iscrizioni = (
        Iscrizione.objects.select_related("studente")
        .filter(attiva=True)
        .order_by("studente__cognome", "studente__nome", "-id")
    )
    if getattr(dipendente, "gruppo_classe_principale_id", None):
        iscrizioni = iscrizioni.filter(gruppo_classe_id=dipendente.gruppo_classe_principale_id)
    else:
        iscrizioni = iscrizioni.filter(classe_id=dipendente.classe_principale_id)
    if anno:
        iscrizioni = iscrizioni.filter(anno_scolastico=anno)

    studenti = []
    seen = set()
    for iscrizione in iscrizioni[:80]:
        studente = iscrizione.studente
        if studente.pk in seen:
            continue
        seen.add(studente.pk)
        studenti.append(studente)
    return studenti


def _relazione_lavorativa_default():
    relazione = RelazioneFamiliare.objects.filter(relazione__iexact="Altro").first()
    if relazione:
        return relazione

    relazione = RelazioneFamiliare.objects.order_by("ordine", "relazione").first()
    if relazione:
        return relazione

    return RelazioneFamiliare.objects.create(relazione="Altro")


def _nazione_from_label(label):
    label = (label or "").strip()
    if not label:
        return None
    return (
        Nazione.objects.filter(Q(nome_nazionalita__iexact=label) | Q(nome__iexact=label))
        .order_by("nome")
        .first()
    )


def _find_familiare_for_profilo_lavorativo(dipendente):
    if dipendente.persona_collegata_id:
        try:
            return dipendente.persona_collegata.profilo_familiare
        except Familiare.DoesNotExist:
            pass
    codice_fiscale = (dipendente.codice_fiscale or "").strip()
    if not codice_fiscale:
        return None
    return (
        Familiare.objects.filter(codice_fiscale__iexact=codice_fiscale)
        .select_related("persona", "persona__indirizzo", "persona__luogo_nascita", "persona__nazionalita")
        .order_by("cognome", "nome", "pk")
        .first()
    )


def _ensure_familiare_for_profilo_lavorativo(dipendente):
    familiare = _find_familiare_for_profilo_lavorativo(dipendente)
    if familiare:
        if familiare.persona_id and dipendente.persona_collegata_id != familiare.persona_id:
            dipendente.persona_collegata = familiare.persona
            dipendente.save(update_fields=["persona_collegata"])
        sync_principal_contacts(
            dipendente,
            indirizzo=dipendente.indirizzo,
            telefono=dipendente.telefono,
            email=dipendente.email,
        )
        return familiare

    persona = dipendente.persona_collegata
    familiare = Familiare.objects.create(
        persona=persona,
        relazione_familiare=_relazione_lavorativa_default(),
        indirizzo=dipendente.indirizzo_effettivo,
        nome=dipendente.nome,
        cognome=dipendente.cognome,
        telefono=dipendente.telefono_principale,
        email=dipendente.email_principale,
        codice_fiscale=(dipendente.codice_fiscale or "").upper().strip(),
        sesso=dipendente.sesso,
        data_nascita=dipendente.data_nascita,
        luogo_nascita_custom=(dipendente.luogo_nascita or "")[:160],
        nazionalita=_nazione_from_label(dipendente.nazionalita),
        attivo=dipendente.stato == StatoDipendente.ATTIVO,
        note=dipendente.note,
    )
    sync_principal_contacts(
        familiare,
        indirizzo=familiare.indirizzo,
        telefono=familiare.telefono,
        email=familiare.email,
    )
    return familiare


def _redirect_to_scheda_anagrafica_lavorativa(dipendente):
    familiare = _ensure_familiare_for_profilo_lavorativo(dipendente)
    return redirect(f"{reverse('modifica_familiare', args=[familiare.pk])}#profilo-lavorativo-inline")


def dashboard_gestione_amministrativa(request):
    redirect_response = redirect_if_dipendenti_simple(request)
    if redirect_response:
        return redirect_response

    anno, mese = _current_period()
    buste_periodo = BustaPagaDipendente.objects.filter(anno=anno, mese=mese)
    ultimi_cedolini = (
        BustaPagaDipendente.objects.select_related("dipendente__persona_collegata", "contratto", "contratto__tipo_contratto")
        .order_by("-anno", "-mese", "dipendente__persona_collegata__cognome", "dipendente__persona_collegata__nome")[:12]
    )
    aggregates = buste_periodo.aggregate(
        costo_previsto=Sum("costo_azienda_previsto"),
        costo_effettivo=Sum("costo_azienda_effettivo"),
        netto_previsto=Sum("netto_previsto"),
        netto_effettivo=Sum("netto_effettivo"),
    )
    costo_previsto = aggregates["costo_previsto"] or ZERO
    costo_effettivo = aggregates["costo_effettivo"] or ZERO
    netto_previsto = aggregates["netto_previsto"] or ZERO
    netto_effettivo = aggregates["netto_effettivo"] or ZERO

    return render(
        request,
        "gestione_amministrativa/dashboard.html",
        {
            "anno": anno,
            "mese": mese,
            "periodo_corrente_label": f"{mese:02d}/{anno}",
            "dipendenti_attivi": Dipendente.objects.filter(stato=StatoDipendente.ATTIVO).count(),
            "dipendenti_totali": Dipendente.objects.count(),
            "contratti_attivi": ContrattoDipendente.objects.filter(attivo=True).count(),
            "contratti_totali": ContrattoDipendente.objects.count(),
            "simulazioni_attive": SimulazioneCostoDipendente.objects.filter(attiva=True).count(),
            "parametri_attivi": ParametroCalcoloStipendio.objects.filter(attivo=True).count(),
            "buste_periodo_count": buste_periodo.count(),
            "buste_previste_periodo": buste_periodo.filter(stato=StatoBustaPaga.PREVISTA).count(),
            "buste_effettive_periodo": buste_periodo.filter(
                stato__in=[StatoBustaPaga.EFFETTIVA, StatoBustaPaga.VERIFICATA]
            ).count(),
            "costo_previsto": costo_previsto,
            "costo_effettivo": costo_effettivo,
            "scostamento_costo": costo_effettivo - costo_previsto,
            "netto_previsto": netto_previsto,
            "netto_effettivo": netto_effettivo,
            "scostamento_netto": netto_effettivo - netto_previsto,
            "ultimi_cedolini": ultimi_cedolini,
        },
    )


def _lista_profili_lavoro(request, scope):
    labels = _dipendente_labels(scope)
    q = (request.GET.get("q") or "").strip()
    stato = (request.GET.get("stato") or "").strip()
    dipendenti = _profili_lavoro_queryset(scope, q=q, stato=stato)
    dipendenti_stats = _profili_lavoro_stats(dipendenti)
    educatori = None
    educatori_stats = None
    educatori_labels = None

    if scope == "dipendenti":
        educatori = _profili_lavoro_queryset("educatori", q=q, stato=stato)
        educatori_stats = _profili_lavoro_stats(educatori)
        educatori_labels = _dipendente_labels("educatori")

    anno, mese = _current_period()
    page_total = dipendenti_stats["totale"] + (educatori_stats["totale"] if educatori_stats else 0)
    return render(
        request,
        "gestione_amministrativa/dipendenti/dipendente_list.html",
        {
            "dipendenti": dipendenti,
            "educatori": educatori,
            "dipendenti_stats": dipendenti_stats,
            "educatori_stats": educatori_stats,
            "dipendenti_labels": labels,
            "educatori_labels": educatori_labels,
            "educatori_nella_lista_dipendenti": scope == "dipendenti",
            "page_total": page_total,
            "q": q,
            "stato": stato,
            "stati": StatoDipendente.choices,
            "anno_corrente": anno,
            "mese_corrente": mese,
        },
    )


def _profili_lavoro_queryset(scope, *, q="", stato=""):
    profili = (
        Dipendente.objects.select_related("persona_collegata", "classe_principale", "gruppo_classe_principale")
        .annotate(
            numero_contratti=Count("contratti", distinct=True),
            numero_buste=Count("buste_paga", distinct=True),
            numero_fatture_collegate=Count("fornitori_collegati__documenti", distinct=True),
            numero_documenti=Count("documenti", distinct=True),
        )
        .filter(ruolo_aziendale__in=_ruoli_for_scope(scope))
    )
    if q:
        profili = profili.filter(
            Q(persona_collegata__nome__icontains=q)
            | Q(persona_collegata__cognome__icontains=q)
            | Q(persona_collegata__codice_fiscale__icontains=q)
            | Q(persona_collegata__email__icontains=q)
            | Q(persona_collegata__telefono__icontains=q)
            | Q(materia__icontains=q)
        )
    if stato:
        profili = profili.filter(stato=stato)
    return profili


def _profili_lavoro_stats(profili):
    return {
        "totale": profili.count(),
        "attivi": profili.filter(stato=StatoDipendente.ATTIVO).count(),
        "sospesi": profili.filter(stato=StatoDipendente.SOSPESO).count(),
        "cessati": profili.filter(stato=StatoDipendente.CESSATO).count(),
        "contratti": profili.aggregate(totale=Count("contratti", distinct=True))["totale"] or 0,
        "buste": profili.aggregate(totale=Count("buste_paga", distinct=True))["totale"] or 0,
        "documenti": profili.aggregate(totale=Count("documenti", distinct=True))["totale"] or 0,
    }


def lista_dipendenti(request):
    return _lista_profili_lavoro(request, "dipendenti")


def lista_educatori(request):
    return _lista_profili_lavoro(request, "educatori")


def lista_contratti_dipendenti(request):
    contratti = ContrattoDipendente.objects.select_related("dipendente", "tipo_contratto").annotate(
        numero_buste=Count("buste_paga"),
        numero_simulazioni=Count("simulazioni_costo"),
    )
    dipendente_id = (request.GET.get("dipendente") or "").strip()
    attivo = (request.GET.get("attivo") or "").strip()
    if dipendente_id.isdigit():
        contratti = contratti.filter(dipendente_id=int(dipendente_id))
    if attivo in {"1", "0"}:
        contratti = contratti.filter(attivo=(attivo == "1"))

    contratti_stats = {
        "totale": contratti.count(),
        "attivi": contratti.filter(attivo=True).count(),
        "non_attivi": contratti.filter(attivo=False).count(),
        "buste": contratti.aggregate(totale=Count("buste_paga", distinct=True))["totale"] or 0,
        "simulazioni": contratti.aggregate(totale=Count("simulazioni_costo", distinct=True))["totale"] or 0,
    }

    return render(
        request,
        "gestione_amministrativa/dipendenti/contratto_list.html",
        {
            "contratti": contratti,
            "contratti_stats": contratti_stats,
            "dipendenti": Dipendente.objects.order_by("persona_collegata__cognome", "persona_collegata__nome"),
            "dipendente_id": dipendente_id,
            "attivo": attivo,
        },
    )


def lista_simulazioni_costo_dipendenti(request):
    redirect_response = redirect_if_dipendenti_simple(request)
    if redirect_response:
        return redirect_response

    simulazioni = SimulazioneCostoDipendente.objects.select_related(
        "contratto",
        "contratto__dipendente",
        "contratto__tipo_contratto",
    )
    dipendente_id = (request.GET.get("dipendente") or "").strip()
    contratto_id = (request.GET.get("contratto") or "").strip()
    attiva = (request.GET.get("attiva") or "").strip()

    if dipendente_id.isdigit():
        simulazioni = simulazioni.filter(contratto__dipendente_id=int(dipendente_id))
    if contratto_id.isdigit():
        simulazioni = simulazioni.filter(contratto_id=int(contratto_id))
    if attiva in {"1", "0"}:
        simulazioni = simulazioni.filter(attiva=(attiva == "1"))

    simulazioni_aggregate = simulazioni.aggregate(
        netto=Sum("netto_mensile"),
        lordo=Sum("lordo_mensile"),
        costo=Sum("costo_azienda_mensile"),
    )
    simulazioni_stats = {
        "totale": simulazioni.count(),
        "attive": simulazioni.filter(attiva=True).count(),
        "non_attive": simulazioni.filter(attiva=False).count(),
        "netto": simulazioni_aggregate["netto"] or ZERO,
        "lordo": simulazioni_aggregate["lordo"] or ZERO,
        "costo": simulazioni_aggregate["costo"] or ZERO,
    }

    return render(
        request,
        "gestione_amministrativa/dipendenti/simulazione_costo_list.html",
        {
            "simulazioni": simulazioni,
            "simulazioni_stats": simulazioni_stats,
            "dipendenti": Dipendente.objects.order_by("persona_collegata__cognome", "persona_collegata__nome"),
            "contratti": ContrattoDipendente.objects.select_related("dipendente", "tipo_contratto").order_by(
                "dipendente__persona_collegata__cognome", "dipendente__persona_collegata__nome", "-data_inizio"
            ),
            "dipendente_id": dipendente_id,
            "contratto_id": contratto_id,
            "attiva": attiva,
        },
    )


def _crea_profilo_lavoro(request, scope):
    labels = _dipendente_labels(scope)
    if request.method == "GET":
        profilo = "educatore" if scope == "educatori" else "dipendente"
        return redirect(f"{reverse('crea_familiare')}?profilo_lavorativo={profilo}")

    initial = {}
    if scope == "educatori":
        initial["ruolo_aziendale"] = RuoloAnagraficoDipendente.EDUCATORE
    else:
        initial["ruolo_aziendale"] = RuoloAnagraficoDipendente.DIPENDENTE

    form = DipendenteForm(request.POST, initial=initial)
    contact_formsets = build_anagrafica_contact_formsets(data=request.POST)
    if form.is_valid() and anagrafica_contact_formsets_are_valid(contact_formsets):
        dipendente = form.save()
        save_anagrafica_contact_formsets(dipendente, contact_formsets)
        messages.success(request, f"{labels['singular_cap']} creato correttamente.")
        return _redirect_to_scheda_anagrafica_lavorativa(dipendente)

    return render(
        request,
        "gestione_amministrativa/dipendenti/dipendente_form.html",
        {
            "form": form,
            **contact_formsets,
            "dipendente": None,
            "contratti": [],
            "buste_paga": [],
            "compensi_lavorativi": [],
            "simulazioni_costo": [],
            "documenti": [],
            "studenti_classe_principale": [],
            "dipendenti_labels": labels,
            "has_form_errors": bool(form.errors or anagrafica_contact_formsets_have_errors(contact_formsets)),
        },
    )


def crea_dipendente(request):
    return _crea_profilo_lavoro(request, "dipendenti")


def crea_educatore(request):
    return _crea_profilo_lavoro(request, "educatori")


def _modifica_profilo_lavoro(request, pk, scope=None):
    dipendente = get_object_or_404(Dipendente, pk=pk)
    if scope is None:
        scope = "educatori" if dipendente.is_educatore and not dipendente.is_dipendente_operativo else "dipendenti"
    labels = _dipendente_labels(scope)
    if request.method != "POST":
        return _redirect_to_scheda_anagrafica_lavorativa(dipendente)

    form = DipendenteForm(request.POST, instance=dipendente)
    contact_formsets = build_anagrafica_contact_formsets(data=request.POST, instance=dipendente)
    if form.is_valid() and anagrafica_contact_formsets_are_valid(contact_formsets):
        dipendente = form.save()
        save_anagrafica_contact_formsets(dipendente, contact_formsets)
        messages.success(request, f"{labels['singular_cap']} aggiornato correttamente.")
        return _redirect_to_scheda_anagrafica_lavorativa(dipendente)

    contratti = dipendente.contratti.all()
    buste_paga = dipendente.buste_paga.select_related("contratto").order_by("-anno", "-mese")[:12]
    compensi_lavorativi = compensi_lavorativi_dipendente(dipendente, limite=12)
    documenti = dipendente.documenti.order_by("-data_documento", "-id")[:12]
    simulazioni_costo = (
        SimulazioneCostoDipendente.objects.select_related("contratto", "contratto__tipo_contratto")
        .filter(contratto__dipendente=dipendente)
        .order_by("-valido_dal", "-id")[:12]
    )
    return render(
        request,
        "gestione_amministrativa/dipendenti/dipendente_form.html",
        {
            "form": form,
            **contact_formsets,
            "dipendente": dipendente,
            "contratti": contratti,
            "buste_paga": buste_paga,
            "compensi_lavorativi": compensi_lavorativi,
            "documenti": documenti,
            "simulazioni_costo": simulazioni_costo,
            "studenti_classe_principale": _studenti_classe_principale(dipendente),
            "dipendenti_labels": labels,
            "has_form_errors": bool(form.errors or anagrafica_contact_formsets_have_errors(contact_formsets)),
        },
    )


def modifica_dipendente(request, pk):
    return _modifica_profilo_lavoro(request, pk, "dipendenti")


def modifica_educatore(request, pk):
    return _modifica_profilo_lavoro(request, pk, "educatori")


def _elimina_profilo_lavoro(request, pk, scope):
    labels = _dipendente_labels(scope)
    dipendente = get_object_or_404(Dipendente, pk=pk)
    count_relazioni = (
        dipendente.contratti.count()
        + dipendente.buste_paga.count()
        + dipendente.fornitori_collegati.count()
        + dipendente.documenti.count()
    )
    if request.method == "POST":
        if count_relazioni:
            messages.error(
                request,
                (
                    f"Impossibile eliminare {labels['singular']} "
                    "perche sono presenti contratti, buste paga, fornitori o documenti collegati."
                ),
            )
            return redirect(labels["detail_url"], pk=dipendente.pk)
        dipendente.delete()
        messages.success(request, f"{labels['singular_cap']} eliminato correttamente.")
        return redirect(labels["list_url"])

    return render(
        request,
        "gestione_amministrativa/dipendenti/dipendente_confirm_delete.html",
        {"dipendente": dipendente, "count_relazioni": count_relazioni, "dipendenti_labels": labels},
    )


def elimina_dipendente(request, pk):
    return _elimina_profilo_lavoro(request, pk, "dipendenti")


def elimina_educatore(request, pk):
    return _elimina_profilo_lavoro(request, pk, "educatori")


def crea_contratto_dipendente(request, dipendente_pk=None):
    popup = is_popup_request(request)
    detailed_mode = gestione_dipendenti_dettagliata_attiva()
    dipendente = None
    requested_dipendente = dipendente_pk or request.GET.get("dipendente") or request.POST.get("dipendente")
    if requested_dipendente:
        dipendente = get_object_or_404(Dipendente, pk=requested_dipendente)

    if request.method == "POST":
        form = ContrattoDipendenteForm(request.POST, detailed_mode=detailed_mode)
        if form.is_valid():
            if dipendente:
                form.instance.dipendente = dipendente
            contratto = form.save()
            if popup:
                return popup_select_response(
                    request,
                    field_name="contratto",
                    object_id=contratto.pk,
                    object_label=contratto.label_select(include_dipendente=False),
                )
            messages.success(request, "Contratto dipendente creato correttamente.")
            if dipendente:
                return redirect("modifica_dipendente", pk=dipendente.pk)
            return redirect("lista_contratti_dipendenti")
    else:
        form = ContrattoDipendenteForm(detailed_mode=detailed_mode)

    return render(
        request,
        "gestione_amministrativa/dipendenti/contratto_form.html",
        {
            "form": form,
            "dipendente": dipendente,
            "contratto": None,
            "popup": popup,
            "gestione_dipendenti_dettagliata_attiva": detailed_mode,
        },
    )


def modifica_contratto_dipendente(request, pk):
    contratto = get_object_or_404(
        ContrattoDipendente.objects.select_related("dipendente", "tipo_contratto", "parametro_calcolo"),
        pk=pk,
    )
    popup = is_popup_request(request)
    detailed_mode = gestione_dipendenti_dettagliata_attiva()
    if request.method == "POST":
        form = ContrattoDipendenteForm(request.POST, instance=contratto, detailed_mode=detailed_mode)
        if form.is_valid():
            contratto = form.save()
            if popup:
                return popup_select_response(
                    request,
                    field_name="contratto",
                    object_id=contratto.pk,
                    object_label=contratto.label_select(include_dipendente=False),
                )
            messages.success(request, "Contratto dipendente aggiornato correttamente.")
            if contratto.dipendente_id:
                return redirect("modifica_dipendente", pk=contratto.dipendente_id)
            return redirect("lista_contratti_dipendenti")
    else:
        form = ContrattoDipendenteForm(instance=contratto, detailed_mode=detailed_mode)

    simulazioni_costo = contratto.simulazioni_costo.order_by("-valido_dal", "-id")
    return render(
        request,
        "gestione_amministrativa/dipendenti/contratto_form.html",
        {
            "form": form,
            "dipendente": contratto.dipendente,
            "contratto": contratto,
            "popup": popup,
            "simulazioni_costo": simulazioni_costo,
            "gestione_dipendenti_dettagliata_attiva": detailed_mode,
        },
    )


def elimina_contratto_dipendente(request, pk):
    contratto = get_object_or_404(
        ContrattoDipendente.objects.select_related("dipendente", "tipo_contratto", "parametro_calcolo"),
        pk=pk,
    )
    popup = is_popup_request(request)
    count_buste = contratto.buste_paga.count()
    count_simulazioni = contratto.simulazioni_costo.count()
    if request.method == "POST":
        if count_buste or count_simulazioni:
            if popup:
                return render(
                    request,
                    "gestione_amministrativa/dipendenti/contratto_confirm_delete.html",
                    {
                        "contratto": contratto,
                        "count_buste": count_buste,
                        "count_simulazioni": count_simulazioni,
                        "popup": popup,
                        "blocked": True,
                    },
                )
            messages.error(
                request,
                "Impossibile eliminare il contratto: ci sono buste paga o simulazioni costo collegate. Puoi disattivarlo o chiuderlo con una data fine.",
            )
            return redirect("modifica_contratto_dipendente", pk=contratto.pk)

        dipendente_pk = contratto.dipendente_id
        object_id = contratto.pk
        contratto.delete()
        if popup:
            return popup_delete_response(
                request,
                field_name="contratto",
                object_id=object_id,
            )
        messages.success(request, "Contratto dipendente eliminato correttamente.")
        if dipendente_pk:
            return redirect("modifica_dipendente", pk=dipendente_pk)
        return redirect("lista_contratti_dipendenti")

    return render(
        request,
        "gestione_amministrativa/dipendenti/contratto_confirm_delete.html",
        {
            "contratto": contratto,
            "count_buste": count_buste,
            "count_simulazioni": count_simulazioni,
            "popup": popup,
            "blocked": False,
        },
    )


def crea_simulazione_costo_dipendente(request):
    redirect_response = redirect_if_dipendenti_simple(request)
    if redirect_response:
        return redirect_response

    popup = is_popup_request(request)
    initial = {}
    contratto_id = (request.GET.get("contratto") or request.POST.get("contratto") or "").strip()
    if contratto_id.isdigit():
        initial["contratto"] = int(contratto_id)
    else:
        dipendente_id = (request.GET.get("dipendente") or "").strip()
        if dipendente_id.isdigit():
            dipendente = get_object_or_404(Dipendente, pk=int(dipendente_id))
            contratto_corrente = dipendente.contratto_corrente
            if contratto_corrente:
                initial["contratto"] = contratto_corrente.pk

    if request.method == "POST":
        form = SimulazioneCostoDipendenteForm(request.POST, request.FILES)
        if form.is_valid():
            simulazione = form.save()
            if popup:
                return popup_select_response(
                    request,
                    field_name="simulazione_costo",
                    object_id=simulazione.pk,
                    object_label=str(simulazione),
                )
            messages.success(request, "Simulazione costo dipendente salvata correttamente.")
            return redirect("modifica_simulazione_costo_dipendente", pk=simulazione.pk)
    else:
        form = SimulazioneCostoDipendenteForm(initial=initial)

    return render(
        request,
        "gestione_amministrativa/dipendenti/simulazione_costo_form.html",
        {"form": form, "simulazione": None, "popup": popup},
    )


def modifica_simulazione_costo_dipendente(request, pk):
    redirect_response = redirect_if_dipendenti_simple(request)
    if redirect_response:
        return redirect_response

    simulazione = get_object_or_404(
        SimulazioneCostoDipendente.objects.select_related("contratto", "contratto__dipendente", "contratto__tipo_contratto"),
        pk=pk,
    )
    popup = is_popup_request(request)
    if request.method == "POST":
        form = SimulazioneCostoDipendenteForm(request.POST, request.FILES, instance=simulazione)
        if form.is_valid():
            simulazione = form.save()
            if popup:
                return popup_select_response(
                    request,
                    field_name="simulazione_costo",
                    object_id=simulazione.pk,
                    object_label=str(simulazione),
                )
            messages.success(request, "Simulazione costo dipendente aggiornata correttamente.")
            return redirect("modifica_simulazione_costo_dipendente", pk=simulazione.pk)
    else:
        form = SimulazioneCostoDipendenteForm(instance=simulazione)

    return render(
        request,
        "gestione_amministrativa/dipendenti/simulazione_costo_form.html",
        {"form": form, "simulazione": simulazione, "popup": popup},
    )


def elimina_simulazione_costo_dipendente(request, pk):
    redirect_response = redirect_if_dipendenti_simple(request)
    if redirect_response:
        return redirect_response

    simulazione = get_object_or_404(
        SimulazioneCostoDipendente.objects.select_related("contratto", "contratto__dipendente"),
        pk=pk,
    )
    popup = is_popup_request(request)
    if request.method == "POST":
        contratto = simulazione.contratto
        object_id = simulazione.pk
        simulazione.delete()
        if popup:
            return popup_delete_response(request, field_name="simulazione_costo", object_id=object_id)
        messages.success(request, "Simulazione costo dipendente eliminata correttamente.")
        if contratto and contratto.dipendente_id:
            return redirect("modifica_dipendente", pk=contratto.dipendente_id)
        return redirect("lista_simulazioni_costo_dipendenti")

    return render(
        request,
        "gestione_amministrativa/dipendenti/simulazione_costo_confirm_delete.html",
        {"simulazione": simulazione, "popup": popup},
    )


def crea_tipo_contratto_dipendente(request):
    popup = is_popup_request(request)
    if request.method == "POST":
        form = TipoContrattoDipendenteForm(request.POST)
        if form.is_valid():
            tipo = form.save()
            if popup:
                return popup_select_response(
                    request,
                    field_name="tipo_contratto",
                    object_id=tipo.pk,
                    object_label=str(tipo),
                )
            messages.success(request, "Tipo contratto creato correttamente.")
            return redirect("lista_contratti_dipendenti")
    else:
        form = TipoContrattoDipendenteForm()

    return render(
        request,
        "gestione_amministrativa/dipendenti/tipo_contratto_popup_form.html",
        {
            "form": form,
            "titolo": "Nuovo tipo contratto",
            "popup": popup,
        },
    )


def modifica_tipo_contratto_dipendente(request, pk):
    tipo = get_object_or_404(TipoContrattoDipendente, pk=pk)
    popup = is_popup_request(request)
    if request.method == "POST":
        form = TipoContrattoDipendenteForm(request.POST, instance=tipo)
        if form.is_valid():
            tipo = form.save()
            if popup:
                return popup_select_response(
                    request,
                    field_name="tipo_contratto",
                    object_id=tipo.pk,
                    object_label=str(tipo),
                )
            messages.success(request, "Tipo contratto aggiornato correttamente.")
            return redirect("lista_contratti_dipendenti")
    else:
        form = TipoContrattoDipendenteForm(instance=tipo)

    return render(
        request,
        "gestione_amministrativa/dipendenti/tipo_contratto_popup_form.html",
        {
            "form": form,
            "titolo": "Modifica tipo contratto",
            "popup": popup,
            "tipo_contratto": tipo,
        },
    )


def elimina_tipo_contratto_dipendente(request, pk):
    tipo = get_object_or_404(TipoContrattoDipendente, pk=pk)
    popup = is_popup_request(request)
    usage_count = tipo.contratti.count()
    blocked = False

    if request.method == "POST":
        if usage_count:
            blocked = True
        else:
            object_id = tipo.pk
            tipo.delete()
            if popup:
                return popup_delete_response(
                    request,
                    field_name="tipo_contratto",
                    object_id=object_id,
                )
            messages.success(request, "Tipo contratto eliminato correttamente.")
            return redirect("lista_contratti_dipendenti")

    return render(
        request,
        "gestione_amministrativa/dipendenti/tipo_contratto_popup_delete.html",
        {
            "oggetto": tipo,
            "titolo": "Elimina tipo contratto",
            "popup": popup,
            "usage_count": usage_count,
            "blocked": blocked,
        },
    )


def genera_previsione_busta_paga(request, dipendente_pk):
    dipendente = get_object_or_404(Dipendente, pk=dipendente_pk)
    anno, mese = _current_period()
    if request.method == "POST":
        try:
            anno = int(request.POST.get("anno") or anno)
            mese = int(request.POST.get("mese") or mese)
        except ValueError:
            messages.error(request, "Periodo non valido per la previsione della busta paga.")
            return redirect("modifica_dipendente", pk=dipendente.pk)
    try:
        busta = crea_o_aggiorna_previsione_busta_paga(dipendente, anno, mese)
    except ValueError as exc:
        messages.error(request, str(exc))
        return redirect("modifica_dipendente", pk=dipendente.pk)

    messages.success(request, f"Previsione busta paga {busta.periodo_label} generata correttamente.")
    return redirect("modifica_busta_paga_dipendente", pk=busta.pk)


def lista_buste_paga_dipendenti(request):
    buste = BustaPagaDipendente.objects.select_related("dipendente", "contratto", "contratto__tipo_contratto")
    anno = (request.GET.get("anno") or "").strip()
    mese = (request.GET.get("mese") or "").strip()
    dipendente_id = (request.GET.get("dipendente") or "").strip()
    if anno.isdigit():
        buste = buste.filter(anno=int(anno))
    if mese.isdigit():
        buste = buste.filter(mese=int(mese))
    if dipendente_id.isdigit():
        buste = buste.filter(dipendente_id=int(dipendente_id))

    buste_aggregate = buste.aggregate(
        netto_previsto=Sum("netto_previsto"),
        netto_effettivo=Sum("netto_effettivo"),
        costo_previsto=Sum("costo_azienda_previsto"),
        costo_effettivo=Sum("costo_azienda_effettivo"),
    )
    buste_stats = {
        "totale": buste.count(),
        "previste": buste.filter(stato=StatoBustaPaga.PREVISTA).count(),
        "effettive": buste.filter(stato__in=[StatoBustaPaga.EFFETTIVA, StatoBustaPaga.VERIFICATA]).count(),
        "bozze": buste.filter(stato=StatoBustaPaga.BOZZA).count(),
        "netto_previsto": buste_aggregate["netto_previsto"] or ZERO,
        "netto_effettivo": buste_aggregate["netto_effettivo"] or ZERO,
        "costo_previsto": buste_aggregate["costo_previsto"] or ZERO,
        "costo_effettivo": buste_aggregate["costo_effettivo"] or ZERO,
    }

    return render(
        request,
        "gestione_amministrativa/dipendenti/busta_paga_list.html",
        {
            "buste": buste,
            "buste_stats": buste_stats,
            "anno": anno,
            "mese": mese,
            "dipendente_id": dipendente_id,
            "dipendenti": Dipendente.objects.order_by("persona_collegata__cognome", "persona_collegata__nome"),
        },
    )


def crea_busta_paga_dipendente(request):
    popup = is_popup_request(request)
    detailed_mode = gestione_dipendenti_dettagliata_attiva()
    initial = {}
    anno, mese = _current_period()
    initial["anno"] = anno
    initial["mese"] = mese
    dipendente_id = (request.GET.get("dipendente") or "").strip()
    if dipendente_id.isdigit():
        dipendente = Dipendente.objects.filter(pk=int(dipendente_id)).first()
        if dipendente:
            initial["dipendente"] = dipendente.pk
            contratto = contratto_applicabile(dipendente, anno, mese)
            if contratto:
                initial["contratto"] = contratto.pk

    if request.method == "POST":
        form = BustaPagaDipendenteForm(request.POST, request.FILES, detailed_mode=detailed_mode)
        if form.is_valid():
            busta = form.save()
            _sincronizza_pagamento_busta_da_movimento_field(busta)
            _aggiorna_riconciliazione_movimenti_busta(busta.movimento_pagamento_id)
            if popup:
                return popup_select_response(
                    request,
                    field_name="busta_paga",
                    object_id=busta.pk,
                    object_label=str(busta),
                )
            messages.success(request, "Busta paga salvata correttamente.")
            return redirect("modifica_busta_paga_dipendente", pk=busta.pk)
    else:
        form = BustaPagaDipendenteForm(initial=initial, detailed_mode=detailed_mode)

    return render(
        request,
        "gestione_amministrativa/dipendenti/busta_paga_form.html",
        {
            "form": form,
            "busta": None,
            "file_busta_paga_name": "",
            "popup": popup,
            "gestione_dipendenti_dettagliata_attiva": detailed_mode,
        },
    )


def modifica_busta_paga_dipendente(request, pk):
    busta = get_object_or_404(
        BustaPagaDipendente.objects.select_related(
            "dipendente",
            "contratto",
            "contratto__tipo_contratto",
            "movimento_pagamento",
        ),
        pk=pk,
    )
    popup = is_popup_request(request)
    detailed_mode = gestione_dipendenti_dettagliata_attiva()
    movimento_precedente_id = busta.movimento_pagamento_id
    if request.method == "POST":
        form = BustaPagaDipendenteForm(
            request.POST,
            request.FILES,
            instance=busta,
            detailed_mode=detailed_mode,
        )
        if form.is_valid():
            busta = form.save()
            _sincronizza_pagamento_busta_da_movimento_field(busta)
            _aggiorna_riconciliazione_movimenti_busta(movimento_precedente_id, busta.movimento_pagamento_id)
            if popup:
                return popup_select_response(
                    request,
                    field_name="busta_paga",
                    object_id=busta.pk,
                    object_label=str(busta),
                )
            messages.success(request, "Busta paga aggiornata correttamente.")
            return redirect("modifica_busta_paga_dipendente", pk=busta.pk)
    else:
        form = BustaPagaDipendenteForm(instance=busta, detailed_mode=detailed_mode)

    return render(
        request,
        "gestione_amministrativa/dipendenti/busta_paga_form.html",
        {
            "form": form,
            "busta": busta,
            "file_busta_paga_name": _busta_paga_file_name(busta),
            "voci": busta.voci.all(),
            "popup": popup,
            "gestione_dipendenti_dettagliata_attiva": detailed_mode,
        },
    )


def apri_file_busta_paga_dipendente(request, pk):
    busta = get_object_or_404(
        BustaPagaDipendente.objects.select_related("dipendente"),
        pk=pk,
    )
    if not busta.file_busta_paga:
        raise Http404("La busta paga non ha alcun file associato.")

    try:
        file_handle = busta.file_busta_paga.open("rb")
    except FileNotFoundError as exc:
        raise Http404("Il file della busta paga non e disponibile sul server.") from exc
    except DOCUMENT_STORAGE_ERROR_TYPES as exc:
        raise Http404(build_document_storage_error_message(exc)) from exc

    filename = _busta_paga_file_name(busta) or f"busta-paga-{busta.pk}.pdf"
    content_type, _encoding = mimetypes.guess_type(filename)
    response = FileResponse(file_handle, content_type=content_type or "application/octet-stream")
    response["Content-Disposition"] = content_disposition_header(False, filename)
    return response


def inserisci_pagamento_busta_paga_dipendente(request, pk):
    busta = get_object_or_404(
        BustaPagaDipendente.objects.select_related("dipendente"),
        pk=pk,
    )
    data_pagamento = busta.data_pagamento_suggerita
    importo = -(abs(busta.importo_netto_riepilogo or ZERO))
    params = {
        "popup": "1",
        "target_input_name": "movimento_pagamento",
        "busta_paga_pagamento": str(busta.pk),
        "data_contabile": data_pagamento.isoformat(),
        "valuta": busta.valuta or "EUR",
        "canale": "banca",
        "descrizione": f"Pagamento busta paga {busta.dipendente} - {busta.periodo_label}",
    }
    if importo:
        params["importo"] = f"{importo:.2f}"
    return redirect(f"{reverse('crea_movimento_manuale')}?{urlencode(params)}")


def riconcilia_busta_paga_dipendente(request, pk):
    busta = get_object_or_404(
        BustaPagaDipendente.objects.select_related(
            "dipendente",
            "contratto",
            "contratto__tipo_contratto",
            "movimento_pagamento",
        ).prefetch_related("pagamenti__movimento"),
        pk=pk,
    )
    popup = is_popup_request(request)
    importo_busta = _importo_busta_paga_da_riconciliare(busta)

    if request.method == "POST":
        azione = request.POST.get("azione", "")

        if azione == "annulla":
            movimento_precedente = busta.movimento_pagamento
            movimento_ids_collegati = _pagamenti_busta_movimento_ids(busta)
            movimento_precedente_id = busta.movimento_pagamento_id
            if not movimento_precedente_id and not movimento_ids_collegati:
                messages.info(request, "Questa busta paga non ha un movimento collegato.")
            else:
                update_fields = ["movimento_pagamento", "data_aggiornamento"]
                if movimento_precedente and busta.data_pagamento_effettiva == movimento_precedente.data_contabile:
                    busta.data_pagamento_effettiva = None
                    update_fields.append("data_pagamento_effettiva")
                busta.movimento_pagamento = None
                busta.pagamenti.all().delete()
                busta.save(update_fields=update_fields)
                _aggiorna_riconciliazione_movimenti_busta(movimento_precedente_id, *movimento_ids_collegati)
                messages.success(request, "Collegamento pagamento annullato.")

            if popup:
                return render(request, "popup/popup_close.html", {"message": "Collegamento pagamento annullato."})
            return redirect("modifica_busta_paga_dipendente", pk=busta.pk)

        if importo_busta <= ZERO:
            messages.error(request, "Inserisci il netto della busta paga prima di collegare un pagamento.")
        else:
            movimento_pk = request.POST.get("movimento_pk") or ""
            if not movimento_pk.isdigit():
                messages.error(request, "Seleziona un movimento bancario da collegare.")
            else:
                movimento = get_object_or_404(
                    MovimentoFinanziario.objects.select_related("conto", "categoria"),
                    pk=int(movimento_pk),
                    importo__lt=0,
                )
                disponibile = _movimento_disponibile_per_busta(movimento)
                if movimento.stato_riconciliazione == StatoRiconciliazione.IGNORATO:
                    messages.error(request, "Il movimento selezionato e marcato come da ignorare.")
                elif disponibile <= ZERO:
                    messages.error(
                        request,
                        "Il movimento selezionato non ha disponibilita residua per questa busta paga.",
                    )
                else:
                    movimento_precedente_id = busta.movimento_pagamento_id
                    importo_collegato = min(disponibile, importo_busta)
                    _registra_pagamento_busta_da_movimento(busta, movimento, importo_collegato)
                    _aggiorna_riconciliazione_movimenti_busta(movimento_precedente_id, movimento.pk)
                    if importo_collegato < importo_busta:
                        messages.success(request, "Pagamento parziale collegato alla busta paga.")
                    else:
                        messages.success(request, "Pagamento collegato alla busta paga.")
                    if popup:
                        return render(
                            request,
                            "popup/popup_close.html",
                            {
                                "message": (
                                    "Pagamento parziale collegato alla busta paga."
                                    if importo_collegato < importo_busta
                                    else "Pagamento collegato alla busta paga."
                                )
                            },
                        )
                    return redirect("modifica_busta_paga_dipendente", pk=busta.pk)

    return render(
        request,
        "gestione_amministrativa/dipendenti/busta_paga_riconciliazione_popup.html",
        {
            "busta": busta,
            "importo_busta": importo_busta,
            "importo_netto_busta": abs(busta.importo_netto_riepilogo or ZERO),
            "importo_pagato_busta": busta.importo_pagato_riconciliato,
            "pagamenti_busta": busta.pagamenti.select_related("movimento"),
            "candidati": _movimenti_candidati_busta_paga(busta),
            "popup": popup,
        },
    )


def elimina_busta_paga_dipendente(request, pk):
    busta = get_object_or_404(BustaPagaDipendente.objects.select_related("dipendente"), pk=pk)
    popup = is_popup_request(request)
    if request.method == "POST":
        object_id = busta.pk
        movimento_pagamento_id = busta.movimento_pagamento_id
        pagamento_movimento_ids = list(busta.pagamenti.filter(movimento_id__isnull=False).values_list("movimento_id", flat=True))
        busta.delete()
        _aggiorna_riconciliazione_movimenti_busta(movimento_pagamento_id, *pagamento_movimento_ids)
        if popup:
            return popup_delete_response(request, field_name="busta_paga", object_id=object_id)
        messages.success(request, "Busta paga eliminata correttamente.")
        return redirect("lista_buste_paga_dipendenti")

    return render(
        request,
        "gestione_amministrativa/dipendenti/busta_paga_confirm_delete.html",
        {"busta": busta, "popup": popup},
    )


def lista_parametri_calcolo_stipendi(request):
    redirect_response = redirect_if_dipendenti_simple(request)
    if redirect_response:
        return redirect_response

    parametri = ParametroCalcoloStipendio.objects.annotate(
        numero_contratti=Count("contratti", distinct=True),
    )
    parametri_stats = parametri.aggregate(
        totale=Count("id"),
        attivi=Count("id", filter=Q(attivo=True)),
        non_attivi=Count("id", filter=Q(attivo=False)),
        contratti_collegati=Count("contratti", distinct=True),
    )
    dati_payroll = DatoPayrollUfficiale.objects.filter(attivo=True)
    return render(
        request,
        "gestione_amministrativa/dipendenti/parametri_list.html",
        {
            "parametri": parametri,
            "parametri_stats": parametri_stats,
            "dati_payroll_count": dati_payroll.exclude(categoria=CategoriaDatoPayrollUfficiale.FONTE).count(),
            "fonti_payroll_count": dati_payroll.filter(categoria=CategoriaDatoPayrollUfficiale.FONTE).count(),
            "ultimo_dato_payroll": dati_payroll.order_by("-data_rilevazione").first(),
        },
    )


def lista_dati_payroll_ufficiali(request):
    redirect_response = redirect_if_dipendenti_simple(request)
    if redirect_response:
        return redirect_response

    dati = DatoPayrollUfficiale.objects.all()
    stats = dati.aggregate(
        totale=Count("id"),
        fonti=Count("id", filter=Q(categoria=CategoriaDatoPayrollUfficiale.FONTE)),
        valori=Count("id", filter=~Q(categoria=CategoriaDatoPayrollUfficiale.FONTE)),
        attivi=Count("id", filter=Q(attivo=True)),
    )
    per_categoria = dati.values("categoria").annotate(totale=Count("id")).order_by("categoria")
    ultimi_dati = dati.order_by("-data_rilevazione", "categoria", "nome")[:250]
    return render(
        request,
        "gestione_amministrativa/dipendenti/dati_payroll_ufficiali_list.html",
        {
            "dati_payroll": ultimi_dati,
            "dati_payroll_stats": stats,
            "dati_payroll_per_categoria": per_categoria,
            "categoria_fonte": CategoriaDatoPayrollUfficiale.FONTE,
        },
    )


def crea_parametro_calcolo_stipendio(request):
    redirect_response = redirect_if_dipendenti_simple(request)
    if redirect_response:
        return redirect_response

    popup = is_popup_request(request)
    if request.method == "POST":
        form = ParametroCalcoloStipendioForm(request.POST)
        if form.is_valid():
            parametro = form.save()
            if popup:
                return popup_select_response(
                    request,
                    field_name="parametro_calcolo",
                    object_id=parametro.pk,
                    object_label=str(parametro),
                )
            messages.success(request, "Parametro di calcolo creato correttamente.")
            return redirect("lista_parametri_calcolo_stipendi")
    else:
        form = ParametroCalcoloStipendioForm()

    return render(
        request,
        "gestione_amministrativa/dipendenti/parametro_form.html",
        {"form": form, "parametro": None, "popup": popup},
    )


def modifica_parametro_calcolo_stipendio(request, pk):
    redirect_response = redirect_if_dipendenti_simple(request)
    if redirect_response:
        return redirect_response

    parametro = get_object_or_404(ParametroCalcoloStipendio, pk=pk)
    popup = is_popup_request(request)
    if request.method == "POST":
        form = ParametroCalcoloStipendioForm(request.POST, instance=parametro)
        if form.is_valid():
            parametro = form.save()
            if popup:
                return popup_select_response(
                    request,
                    field_name="parametro_calcolo",
                    object_id=parametro.pk,
                    object_label=str(parametro),
                )
            messages.success(request, "Parametro di calcolo aggiornato correttamente.")
            return redirect("lista_parametri_calcolo_stipendi")
    else:
        form = ParametroCalcoloStipendioForm(instance=parametro)

    return render(
        request,
        "gestione_amministrativa/dipendenti/parametro_form.html",
        {"form": form, "parametro": parametro, "popup": popup},
    )


def elimina_parametro_calcolo_stipendio(request, pk):
    redirect_response = redirect_if_dipendenti_simple(request)
    if redirect_response:
        return redirect_response

    parametro = get_object_or_404(ParametroCalcoloStipendio, pk=pk)
    popup = is_popup_request(request)
    usage_count = parametro.contratti.count()

    if request.method == "POST":
        object_id = parametro.pk
        parametro.delete()
        if popup:
            return popup_delete_response(
                request,
                field_name="parametro_calcolo",
                object_id=object_id,
            )
        messages.success(request, "Parametro di calcolo eliminato correttamente.")
        return redirect("lista_parametri_calcolo_stipendi")

    return render(
        request,
        "gestione_amministrativa/dipendenti/parametro_confirm_delete.html",
        {"parametro": parametro, "popup": popup, "usage_count": usage_count},
    )
