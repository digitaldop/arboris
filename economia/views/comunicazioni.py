from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render

from economia.comunicazioni_famiglie import (
    ComunicazioneFamiglieError,
    costruisci_destinatari_famiglie,
    destinatari_da_chiavi,
    invia_comunicazione_famiglie,
)
from economia.forms import ComunicazioneFamiglieForm
from scuola.models import AnnoScolastico
from scuola.utils import resolve_default_anno_scolastico
from sistema.models import ComunicazioneFamigliaLog, ConfigurazioneEmailSMTP


COMUNICAZIONI_STORICO_PER_PAGE = 20


def comunicazioni_famiglie(request):
    gruppi_destinatari = []
    destinatari = []
    statistiche = {
        "studenti": 0,
        "studenti_senza_email": 0,
        "destinatari": 0,
        "email_uniche": 0,
        "duplicati": 0,
    }
    riepilogo_invio = None
    selected_keys = set()
    anni_selezionati = []

    if request.method == "POST":
        form = ComunicazioneFamiglieForm(request.POST)
        action = request.POST.get("action") or "preview"
        if form.is_valid():
            anni_selezionati = list(form.cleaned_data["anni_scolastici"])
            gruppi_destinatari, destinatari, statistiche = costruisci_destinatari_famiglie(anni_selezionati)
            posted_keys = request.POST.getlist("destinatari")
            selected_keys = set(posted_keys) if posted_keys else {destinatario["key"] for destinatario in destinatari}

            if action == "send":
                oggetto = (form.cleaned_data.get("oggetto") or "").strip()
                messaggio = (form.cleaned_data.get("messaggio") or "").strip()
                if not oggetto:
                    form.add_error("oggetto", "Inserisci l'oggetto dell'email.")
                if not messaggio:
                    form.add_error("messaggio", "Inserisci il testo della comunicazione.")

                destinatari_selezionati = destinatari_da_chiavi(destinatari, posted_keys)
                if not destinatari_selezionati:
                    form.add_error(None, "Seleziona almeno un destinatario.")

                if not form.errors:
                    configurazione = ConfigurazioneEmailSMTP.get_solo()
                    try:
                        riepilogo_invio = invia_comunicazione_famiglie(
                            configurazione=configurazione,
                            destinatari=destinatari_selezionati,
                            oggetto=oggetto,
                            messaggio=messaggio,
                            anni_scolastici=anni_selezionati,
                            utente=request.user,
                        )
                    except ComunicazioneFamiglieError as exc:
                        messages.error(request, str(exc))
                    else:
                        if riepilogo_invio["fallite"]:
                            messages.warning(
                                request,
                                "Invio completato con errori. Controlla il riepilogo e il log interno.",
                            )
                        else:
                            messages.success(request, "Comunicazione inviata correttamente alle famiglie selezionate.")
        else:
            action = "preview"
    else:
        anni_attivi = AnnoScolastico.objects.filter(attivo=True)
        anno_default = resolve_default_anno_scolastico(anni_attivi)
        initial = {"anni_scolastici": [anno_default.pk]} if anno_default else {}
        form = ComunicazioneFamiglieForm(initial=initial)
        if anno_default:
            anni_selezionati = [anno_default]
            gruppi_destinatari, destinatari, statistiche = costruisci_destinatari_famiglie(anni_selezionati)
            selected_keys = {destinatario["key"] for destinatario in destinatari}

    if request.method == "POST" and not selected_keys:
        selected_keys = {destinatario["key"] for destinatario in destinatari}

    return render(
        request,
        "economia/comunicazioni_famiglie.html",
        {
            "form": form,
            "gruppi_destinatari": gruppi_destinatari,
            "destinatari": destinatari,
            "statistiche": statistiche,
            "selected_keys": selected_keys,
            "anni_selezionati": anni_selezionati,
            "riepilogo_invio": riepilogo_invio,
            "smtp_configurata": ConfigurazioneEmailSMTP.get_solo().configurata,
        },
    )


def storico_comunicazioni_famiglie(request):
    q = (request.GET.get("q") or "").strip()
    logs = ComunicazioneFamigliaLog.objects.select_related("utente").all()
    if q:
        logs = logs.filter(Q(oggetto__icontains=q) | Q(messaggio__icontains=q))

    paginator = Paginator(logs, COMUNICAZIONI_STORICO_PER_PAGE)
    page_obj = paginator.get_page(request.GET.get("page"))

    return render(
        request,
        "economia/comunicazioni_famiglie_storico.html",
        {
            "page_obj": page_obj,
            "logs": page_obj.object_list,
            "q": q,
            "total_count": paginator.count,
        },
    )


def dettaglio_comunicazione_famiglia(request, pk):
    log = get_object_or_404(ComunicazioneFamigliaLog.objects.select_related("utente"), pk=pk)
    dettagli = log.dettagli_destinatari or []
    destinatari_inviati = [item for item in dettagli if item.get("esito") == "inviata"]
    destinatari_errori = [item for item in dettagli if item.get("esito") == "errore"]
    destinatari_duplicati = [item for item in dettagli if item.get("esito") == "duplicato"]

    return render(
        request,
        "economia/comunicazioni_famiglie_dettaglio.html",
        {
            "log": log,
            "dettagli": dettagli,
            "destinatari_inviati": destinatari_inviati,
            "destinatari_errori": destinatari_errori,
            "destinatari_duplicati": destinatari_duplicati,
        },
    )
