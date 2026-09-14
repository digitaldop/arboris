from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render

from economia.comunicazioni_famiglie import (
    ComunicazioneFamiglieError,
    classi_comunicazione_disponibili,
    costruisci_destinatari_famiglie,
    destinatari_da_chiavi,
    filtra_destinatari_famiglie,
    invia_comunicazione_famiglie,
)
from economia.forms import ComunicazioneFamiglieForm
from scuola.models import AnnoScolastico
from scuola.utils import resolve_default_anno_scolastico
from sistema.models import ComunicazioneFamigliaLog, ConfigurazioneEmailSMTP


COMUNICAZIONI_STORICO_PER_PAGE = 20


def comunicazioni_famiglie(request):
    riepilogo_invio = None
    is_post = request.method == "POST"
    action = request.POST.get("action", "preview") if is_post else "preview"
    if is_post:
        year_ids = request.POST.getlist("anni_scolastici")
    else:
        anno_default = resolve_default_anno_scolastico(AnnoScolastico.objects.filter(attivo=True))
        year_ids = [anno_default.pk] if anno_default else []
    form = ComunicazioneFamiglieForm(request.POST if is_post else None, initial={"anni_scolastici": year_ids})
    # Class choices come from the same active enrollments as the recipients.
    try:
        anni_selezionati = list(form.fields["anni_scolastici"].clean(year_ids))
    except ValidationError:
        anni_selezionati = []
    gruppi_destinatari, tutti_destinatari, _ = costruisci_destinatari_famiglie(anni_selezionati)
    form.fields["classi"].choices = classi_comunicazione_disponibili(gruppi_destinatari)
    valid = form.is_valid() if is_post else True
    class_filter = None
    if is_post and form.cleaned_data.get("ambito_destinatari") == "classi":
        class_filter = form.cleaned_data.get("classi", [])
    if is_post and ("classi" in form.errors or "ambito_destinatari" in form.errors):
        class_filter = []
    gruppi_visibili, destinatari, statistiche = filtra_destinatari_famiglie(
        gruppi_destinatari, tutti_destinatari, class_filter,
    )
    allowed_keys = {item["key"] for item in destinatari}
    posted_keys = set(request.POST.getlist("destinatari")) if is_post else set()
    years_changed = set(request.POST.getlist("anni_destinatari")) != {str(anno.pk) for anno in anni_selezionati}
    first_preview = request.POST.get("selezione_presentata") != "1"
    selected_keys = (
        allowed_keys if not is_post or (action != "send" and (first_preview or years_changed))
        else posted_keys & allowed_keys
    )

    if is_post and valid and action == "send":
        oggetto = (form.cleaned_data.get("oggetto") or "").strip()
        messaggio = (form.cleaned_data.get("messaggio") or "").strip()
        if not oggetto:
            form.add_error("oggetto", "Inserisci l'oggetto dell'email.")
        if not messaggio:
            form.add_error("messaggio", "Inserisci il testo della comunicazione.")
        destinatari_selezionati = destinatari_da_chiavi(destinatari, posted_keys)
        if posted_keys - allowed_keys:
            form.add_error(None, "I destinatari o le classi sono cambiati. Aggiorna i destinatari e verifica la selezione prima di inviare.")
        if not destinatari_selezionati:
            form.add_error(None, "Seleziona almeno un destinatario.")
        if not form.errors:
            try:
                riepilogo_invio = invia_comunicazione_famiglie(
                    configurazione=ConfigurazioneEmailSMTP.get_solo(),
                    destinatari=destinatari_selezionati, oggetto=oggetto, messaggio=messaggio,
                    anni_scolastici=anni_selezionati, utente=request.user,
                )
            except ComunicazioneFamiglieError as exc:
                messages.error(request, str(exc))
            else:
                if riepilogo_invio["fallite"]:
                    messages.warning(request, "Invio completato con errori. Controlla il riepilogo e il log interno.")
                else:
                    messages.success(request, "Comunicazione inviata correttamente alle famiglie selezionate.")
    visible_ids = {id(gruppo) for gruppo in gruppi_visibili}
    for gruppo in gruppi_destinatari:
        gruppo["visibile"] = id(gruppo) in visible_ids
        gruppo["classi_tokens"] = " ".join(gruppo.get("classi_keys", []))

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
