from decimal import Decimal

from django.contrib import messages
from django.db import models
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from economia.forms import (
    StatoIscrizioneForm,
    CondizioneIscrizioneForm,
    TariffaCondizioneIscrizioneForm,
    AgevolazioneForm,
    IscrizioneForm,
    RataIscrizionePagamentoForm,
    RataIscrizionePagamentoRapidoForm,
    RitiroAnticipatoIscrizioneForm,
)
from economia.models import (
    StatoIscrizione,
    CondizioneIscrizione,
    TariffaCondizioneIscrizione,
    Agevolazione,
    Iscrizione,
    RataIscrizione,
)
from scuola.models import AnnoScolastico


def is_popup_request(request):
    return request.GET.get("popup") == "1" or request.POST.get("popup") == "1"


LAST_METODO_PAGAMENTO_SESSION_KEY = "ultima_metodo_pagamento_retta_id"


def get_stato_ritirato():
    return StatoIscrizione.objects.filter(stato_iscrizione__iexact="Ritirato").first()


def get_safe_next_url(request, fallback_url):
    next_url = request.GET.get("next") or request.POST.get("next") or ""
    if next_url and url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
        return next_url
    return fallback_url


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


def sync_condizione_rate_schedules(condizione):
    summary = {}

    iscrizioni = (
        condizione.iscrizioni.select_related(
            "studente",
            "anno_scolastico",
            "condizione_iscrizione",
        )
        .prefetch_related("rate")
        .all()
    )

    for iscrizione in iscrizioni:
        outcome = iscrizione.sync_rate_schedule()
        summary[outcome] = summary.get(outcome, 0) + 1

    return summary


def build_condizione_sync_feedback(summary):
    if not summary:
        return ""

    feedback_parts = []

    if summary.get("created"):
        feedback_parts.append(f"{summary['created']} piano/i rate creati")
    if summary.get("precreated"):
        feedback_parts.append(f"{summary['precreated']} preiscrizione/i aggiunte al piano rate")
    if summary.get("regenerated"):
        feedback_parts.append(f"{summary['regenerated']} piano/i rate riallineati")
    if summary.get("unchanged"):
        feedback_parts.append(f"{summary['unchanged']} gia allineati")
    if summary.get("locked"):
        feedback_parts.append(f"{summary['locked']} non modificati perche con movimenti o pagamenti")
    if summary.get("missing"):
        feedback_parts.append(f"{summary['missing']} non generabili per assenza dati tariffari")

    return ". ".join(feedback_parts)


def lista_stati_iscrizione(request):
    stati = StatoIscrizione.objects.all()
    return render(request, "economia/iscrizioni/stati_iscrizione_list.html", {"stati": stati})


def crea_stato_iscrizione(request):
    popup = is_popup_request(request)

    if request.method == "POST":
        form = StatoIscrizioneForm(request.POST)
        if form.is_valid():
            stato = form.save()

            if popup:
                return popup_select_response(request, "stato_iscrizione", stato.pk, str(stato))

            messages.success(request, "Stato iscrizione creato correttamente.")
            return redirect("lista_stati_iscrizione")
    else:
        form = StatoIscrizioneForm()

    return render(request, "economia/iscrizioni/stato_iscrizione_form.html", {"form": form, "stato": None, "popup": popup})


def modifica_stato_iscrizione(request, pk):
    stato = get_object_or_404(StatoIscrizione, pk=pk)
    popup = is_popup_request(request)

    if request.method == "POST":
        form = StatoIscrizioneForm(request.POST, instance=stato)
        if form.is_valid():
            stato = form.save()

            if popup:
                return popup_select_response(request, "stato_iscrizione", stato.pk, str(stato))

            messages.success(request, "Stato iscrizione aggiornato correttamente.")
            return redirect("lista_stati_iscrizione")
    else:
        form = StatoIscrizioneForm(instance=stato)

    return render(request, "economia/iscrizioni/stato_iscrizione_form.html", {"form": form, "stato": stato, "popup": popup})


def elimina_stato_iscrizione(request, pk):
    stato = get_object_or_404(StatoIscrizione, pk=pk)
    popup = is_popup_request(request)

    if request.method == "POST":
        object_id = stato.pk
        stato.delete()

        if popup:
            return popup_delete_response(request, "stato_iscrizione", object_id)

        messages.success(request, "Stato iscrizione eliminato correttamente.")
        return redirect("lista_stati_iscrizione")

    return render(request, "economia/iscrizioni/stato_iscrizione_confirm_delete.html", {"stato": stato, "popup": popup})


def lista_condizioni_iscrizione(request):
    condizioni = CondizioneIscrizione.objects.select_related("anno_scolastico").all()
    return render(request, "economia/iscrizioni/condizioni_iscrizione_list.html", {"condizioni": condizioni})


def crea_condizione_iscrizione(request):
    popup = is_popup_request(request)

    if request.method == "POST":
        form = CondizioneIscrizioneForm(request.POST)
        if form.is_valid():
            condizione = form.save()

            if popup:
                return popup_select_response(request, "condizione_iscrizione", condizione.pk, str(condizione))

            messages.success(request, "Condizione economica creata correttamente.")
            return redirect("lista_condizioni_iscrizione")
    else:
        form = CondizioneIscrizioneForm()

    return render(
        request,
        "economia/iscrizioni/condizione_iscrizione_form.html",
        {"form": form, "condizione": None, "popup": popup},
    )


def modifica_condizione_iscrizione(request, pk):
    condizione = get_object_or_404(CondizioneIscrizione, pk=pk)
    popup = is_popup_request(request)

    if request.method == "POST":
        form = CondizioneIscrizioneForm(request.POST, instance=condizione)
        if form.is_valid():
            changed_data = set(form.changed_data)
            condizione = form.save()
            sync_feedback = ""

            if {"anno_scolastico", "numero_mensilita_default", "mese_prima_retta", "giorno_scadenza_rate"} & changed_data:
                sync_feedback = build_condizione_sync_feedback(sync_condizione_rate_schedules(condizione))

            if popup:
                return popup_select_response(request, "condizione_iscrizione", condizione.pk, str(condizione))

            success_message = "Condizione economica aggiornata correttamente."
            if sync_feedback:
                success_message = f"{success_message} {sync_feedback}."

            messages.success(request, success_message)
            return redirect("lista_condizioni_iscrizione")
    else:
        form = CondizioneIscrizioneForm(instance=condizione)

    return render(
        request,
        "economia/iscrizioni/condizione_iscrizione_form.html",
        {"form": form, "condizione": condizione, "popup": popup},
    )


def elimina_condizione_iscrizione(request, pk):
    condizione = get_object_or_404(CondizioneIscrizione, pk=pk)
    popup = is_popup_request(request)

    if request.method == "POST":
        object_id = condizione.pk
        condizione.delete()

        if popup:
            return popup_delete_response(request, "condizione_iscrizione", object_id)

        messages.success(request, "Condizione economica eliminata correttamente.")
        return redirect("lista_condizioni_iscrizione")

    return render(
        request,
        "economia/iscrizioni/condizione_iscrizione_confirm_delete.html",
        {
            "condizione": condizione,
            "count_tariffe": condizione.tariffe.count(),
            "popup": popup,
        },
    )


def lista_tariffe_condizione_iscrizione(request):
    tariffe = TariffaCondizioneIscrizione.objects.select_related(
        "condizione_iscrizione",
        "condizione_iscrizione__anno_scolastico",
    ).all()
    return render(request, "economia/iscrizioni/tariffe_condizione_iscrizione_list.html", {"tariffe": tariffe})


def crea_tariffa_condizione_iscrizione(request):
    popup = is_popup_request(request)

    if request.method == "POST":
        form = TariffaCondizioneIscrizioneForm(request.POST)
        if form.is_valid():
            tariffa = form.save()

            if popup:
                return popup_select_response(request, "tariffa_condizione_iscrizione", tariffa.pk, str(tariffa))

            messages.success(request, "Tariffa condizione creata correttamente.")
            return redirect("lista_tariffe_condizione_iscrizione")
    else:
        form = TariffaCondizioneIscrizioneForm()

    return render(
        request,
        "economia/iscrizioni/tariffa_condizione_iscrizione_form.html",
        {"form": form, "tariffa": None, "popup": popup},
    )


def modifica_tariffa_condizione_iscrizione(request, pk):
    tariffa = get_object_or_404(TariffaCondizioneIscrizione, pk=pk)
    popup = is_popup_request(request)

    if request.method == "POST":
        form = TariffaCondizioneIscrizioneForm(request.POST, instance=tariffa)
        if form.is_valid():
            tariffa = form.save()

            if popup:
                return popup_select_response(request, "tariffa_condizione_iscrizione", tariffa.pk, str(tariffa))

            messages.success(request, "Tariffa condizione aggiornata correttamente.")
            return redirect("lista_tariffe_condizione_iscrizione")
    else:
        form = TariffaCondizioneIscrizioneForm(instance=tariffa)

    return render(
        request,
        "economia/iscrizioni/tariffa_condizione_iscrizione_form.html",
        {"form": form, "tariffa": tariffa, "popup": popup},
    )


def elimina_tariffa_condizione_iscrizione(request, pk):
    tariffa = get_object_or_404(TariffaCondizioneIscrizione, pk=pk)
    popup = is_popup_request(request)

    if request.method == "POST":
        object_id = tariffa.pk
        tariffa.delete()

        if popup:
            return popup_delete_response(request, "tariffa_condizione_iscrizione", object_id)

        messages.success(request, "Tariffa condizione eliminata correttamente.")
        return redirect("lista_tariffe_condizione_iscrizione")

    return render(
        request,
        "economia/iscrizioni/tariffa_condizione_iscrizione_confirm_delete.html",
        {"tariffa": tariffa, "popup": popup},
    )


def lista_agevolazioni(request):
    agevolazioni = Agevolazione.objects.all()
    return render(request, "economia/iscrizioni/agevolazioni_list.html", {"agevolazioni": agevolazioni})


def crea_agevolazione(request):
    popup = is_popup_request(request)

    if request.method == "POST":
        form = AgevolazioneForm(request.POST)
        if form.is_valid():
            agevolazione = form.save()

            if popup:
                return popup_select_response(request, "agevolazione", agevolazione.pk, str(agevolazione))

            messages.success(request, "Agevolazione creata correttamente.")
            return redirect("lista_agevolazioni")
    else:
        form = AgevolazioneForm()

    return render(
        request,
        "economia/iscrizioni/agevolazione_form.html",
        {"form": form, "agevolazione": None, "popup": popup},
    )


def modifica_agevolazione(request, pk):
    agevolazione = get_object_or_404(Agevolazione, pk=pk)
    popup = is_popup_request(request)

    if request.method == "POST":
        form = AgevolazioneForm(request.POST, instance=agevolazione)
        if form.is_valid():
            agevolazione = form.save()

            if popup:
                return popup_select_response(request, "agevolazione", agevolazione.pk, str(agevolazione))

            messages.success(request, "Agevolazione aggiornata correttamente.")
            return redirect("lista_agevolazioni")
    else:
        form = AgevolazioneForm(instance=agevolazione)

    return render(
        request,
        "economia/iscrizioni/agevolazione_form.html",
        {"form": form, "agevolazione": agevolazione, "popup": popup},
    )


def elimina_agevolazione(request, pk):
    agevolazione = get_object_or_404(Agevolazione, pk=pk)
    popup = is_popup_request(request)

    if request.method == "POST":
        object_id = agevolazione.pk
        agevolazione.delete()

        if popup:
            return popup_delete_response(request, "agevolazione", object_id)

        messages.success(request, "Agevolazione eliminata correttamente.")
        return redirect("lista_agevolazioni")

    return render(
        request,
        "economia/iscrizioni/agevolazione_confirm_delete.html",
        {"agevolazione": agevolazione, "popup": popup},
    )


def lista_iscrizioni(request):
    iscrizioni = Iscrizione.objects.select_related(
        "studente",
        "anno_scolastico",
        "classe",
        "stato_iscrizione",
        "condizione_iscrizione",
        "agevolazione",
    ).all()
    return render(request, "economia/iscrizioni/iscrizione_list.html", {"iscrizioni": iscrizioni})


def lista_rate_iscrizione(request):
    iscrizione_id = request.GET.get("iscrizione")
    iscrizione = None

    rate = RataIscrizione.objects.select_related(
        "famiglia",
        "iscrizione",
        "iscrizione__studente",
        "iscrizione__anno_scolastico",
        "metodo_pagamento",
    ).all()

    if iscrizione_id:
        rate = rate.filter(iscrizione_id=iscrizione_id)
        iscrizione = (
            Iscrizione.objects.select_related("studente", "anno_scolastico")
            .filter(pk=iscrizione_id)
            .first()
        )

    rate = rate.order_by(
        "-iscrizione__anno_scolastico__data_inizio",
        "iscrizione__studente__cognome",
        "iscrizione__studente__nome",
        "anno_riferimento",
        "mese_riferimento",
        "numero_rata",
    )

    return render(
        request,
        "economia/iscrizioni/rate_iscrizione_list.html",
        {"rate": rate, "iscrizione_filtro": iscrizione},
    )


def crea_iscrizione(request):
    if request.method == "POST":
        form = IscrizioneForm(request.POST)
        if form.is_valid():
            iscrizione = form.save()
            esito_rate = iscrizione.sync_rate_schedule()
            if esito_rate == "created":
                messages.success(request, "Iscrizione creata correttamente e rate generate in automatico.")
            elif esito_rate == "precreated":
                messages.success(request, "Iscrizione creata correttamente. La preiscrizione e stata aggiunta al piano rate.")
            elif esito_rate == "missing":
                messages.warning(
                    request,
                    "Iscrizione creata correttamente, ma il piano rate non e stato generato: verifica la tariffa attiva della condizione selezionata.",
                )
            else:
                messages.success(request, "Iscrizione creata correttamente.")
            return redirect("lista_iscrizioni")
    else:
        form = IscrizioneForm()

    return render(
        request,
        "economia/iscrizioni/iscrizione_form.html",
        {"form": form, "iscrizione": None, "riepilogo_economico": None},
    )


def modifica_iscrizione(request, pk):
    iscrizione = get_object_or_404(Iscrizione, pk=pk)

    if request.method == "POST":
        form = IscrizioneForm(request.POST, instance=iscrizione)
        if form.is_valid():
            iscrizione = form.save()
            esito_rate = iscrizione.sync_rate_schedule()

            if esito_rate == "regenerated":
                messages.success(request, "Iscrizione aggiornata correttamente. Il piano rate e stato riallineato.")
            elif esito_rate == "precreated":
                messages.success(request, "Iscrizione aggiornata correttamente. La preiscrizione e stata aggiunta al piano rate.")
            elif esito_rate == "missing":
                messages.warning(
                    request,
                    "Iscrizione aggiornata correttamente, ma il piano rate non e stato generato: verifica la tariffa attiva della condizione selezionata.",
                )
            elif esito_rate == "locked":
                messages.success(
                    request,
                    "Iscrizione aggiornata correttamente. Le rate esistenti non sono state rigenerate perche contengono gia movimenti o pagamenti.",
                )
            else:
                messages.success(request, "Iscrizione aggiornata correttamente.")
            return redirect("lista_iscrizioni")
    else:
        form = IscrizioneForm(instance=iscrizione)

    return render(
        request,
        "economia/iscrizioni/iscrizione_form.html",
        {
            "form": form,
            "iscrizione": iscrizione,
            "riepilogo_economico": iscrizione.get_riepilogo_economico(),
        },
    )


@require_POST
def ricalcola_rate_iscrizione(request, pk):
    iscrizione = get_object_or_404(Iscrizione, pk=pk)
    esito_rate = iscrizione.sync_rate_schedule()
    next_url = request.POST.get("next", "")

    if esito_rate == "created":
        messages.success(request, "Piano rate generato correttamente.")
    elif esito_rate == "precreated":
        messages.success(request, "Preiscrizione aggiunta correttamente al piano rate.")
    elif esito_rate == "regenerated":
        messages.success(request, "Piano rate ricalcolato correttamente.")
    elif esito_rate == "unchanged":
        messages.info(request, "Il piano rate era gia allineato.")
    elif esito_rate == "locked":
        messages.warning(
            request,
            "Le rate esistenti non sono state rigenerate perche contengono gia movimenti o pagamenti.",
        )
    else:
        messages.warning(
            request,
            "Impossibile generare il piano rate: verifica la tariffa attiva della condizione selezionata.",
        )

    if next_url and url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
        return redirect(next_url)

    return redirect("modifica_iscrizione", pk=iscrizione.pk)


def ritiro_anticipato_iscrizione(request, pk):
    iscrizione = get_object_or_404(
        Iscrizione.objects.select_related("studente", "anno_scolastico", "stato_iscrizione"),
        pk=pk,
    )
    popup = is_popup_request(request)
    stato_ritirato = get_stato_ritirato()
    fallback_redirect_url = reverse("modifica_studente", kwargs={"pk": iscrizione.studente_id})
    next_url = get_safe_next_url(request, fallback_redirect_url)

    if not stato_ritirato:
        messages.error(request, 'Per usare il ritiro anticipato devi creare prima uno "Stato iscrizione" chiamato "Ritirato".')
        return redirect(next_url)

    if request.method == "POST":
        form = RitiroAnticipatoIscrizioneForm(request.POST, iscrizione=iscrizione)
        if form.is_valid():
            data_ritiro = form.cleaned_data["data_ritiro"]
            note = (form.cleaned_data.get("note") or "").strip()

            if iscrizione.rate.filter(
                data_scadenza__gte=data_ritiro,
            ).filter(
                models.Q(pagata=True)
                | models.Q(importo_pagato__gt=0)
                | models.Q(data_pagamento__isnull=False)
                | models.Q(metodo_pagamento__isnull=False)
                | models.Q(credito_applicato__gt=0)
                | models.Q(altri_sgravi__gt=0)
            ).exists():
                form.add_error(None, "Esistono gia rate con movimenti o pagamenti dalla data di ritiro in poi. Gestiscile prima manualmente.")
            else:
                iscrizione.data_fine_iscrizione = data_ritiro
                iscrizione.stato_iscrizione = stato_ritirato
                iscrizione.attiva = False
                if note:
                    prefix = "Ritiro anticipato"
                    note_entry = f"{prefix} ({data_ritiro.strftime('%d/%m/%Y')}): {note}"
                    iscrizione.note_amministrative = "\n".join(
                        filter(None, [(iscrizione.note_amministrative or "").strip(), note_entry])
                    )
                iscrizione.save(update_fields=["data_fine_iscrizione", "stato_iscrizione", "attiva", "note_amministrative"])
                iscrizione.rate.filter(
                    data_scadenza__gte=data_ritiro,
                ).filter(
                    pagata=False,
                    importo_pagato=0,
                    data_pagamento__isnull=True,
                    metodo_pagamento__isnull=True,
                    credito_applicato=0,
                    altri_sgravi=0,
                ).delete()

                if popup:
                    return render(
                        request,
                        "popup/popup_close.html",
                        {"message": "Ritiro anticipato registrato correttamente."},
                    )

                messages.success(request, "Ritiro anticipato registrato correttamente.")
                return redirect(next_url)
    else:
        form = RitiroAnticipatoIscrizioneForm(
            iscrizione=iscrizione,
            initial={"data_ritiro": timezone.localdate()},
        )

    return render(
        request,
        "economia/iscrizioni/ritiro_anticipato_iscrizione_form.html",
        {
            "form": form,
            "iscrizione": iscrizione,
            "popup": popup,
            "next_url": next_url,
        },
    )


def elimina_iscrizione(request, pk):
    iscrizione = get_object_or_404(Iscrizione, pk=pk)
    count_rate = iscrizione.rate.count()

    if request.method == "POST":
        confirm_rates = request.POST.get("confirm_delete_rates") == "1"
        confirm_text = (request.POST.get("confirm_delete_text") or "").strip().upper()

        if not confirm_rates or confirm_text != "ELIMINA":
            messages.error(
                request,
                "Per eliminare l'iscrizione devi confermare esplicitamente anche l'eliminazione delle rate associate.",
            )
            return render(
                request,
                "economia/iscrizioni/iscrizione_confirm_delete.html",
                {"iscrizione": iscrizione, "count_rate": count_rate},
            )

        iscrizione.delete()
        messages.success(request, "Iscrizione eliminata correttamente.")
        return redirect("lista_iscrizioni")

    return render(
        request,
        "economia/iscrizioni/iscrizione_confirm_delete.html",
        {"iscrizione": iscrizione, "count_rate": count_rate},
    )


def modifica_rata_iscrizione(request, pk):
    rata = get_object_or_404(
        RataIscrizione.objects.select_related(
            "famiglia",
            "iscrizione",
            "iscrizione__studente",
            "iscrizione__anno_scolastico",
            "metodo_pagamento",
        ),
        pk=pk,
    )

    fallback_back_url = f"{reverse('lista_rate_iscrizione')}?iscrizione={rata.iscrizione_id}"
    requested_back_url = request.GET.get("next") or request.META.get("HTTP_REFERER", "")
    back_url = (
        requested_back_url
        if requested_back_url and url_has_allowed_host_and_scheme(requested_back_url, allowed_hosts={request.get_host()}, require_https=request.is_secure())
        else fallback_back_url
    )

    if request.method == "POST":
        form = RataIscrizionePagamentoForm(request.POST, instance=rata)
        if form.is_valid():
            form.save()
            messages.success(request, "Dati pagamento rata aggiornati correttamente.")
            return redirect(back_url)
    else:
        form = RataIscrizionePagamentoForm(instance=rata)

    return render(
        request,
        "economia/iscrizioni/rata_iscrizione_form.html",
        {"form": form, "rata": rata, "back_url": back_url},
    )


def pagamento_rapido_rata_iscrizione(request, pk):
    rata = get_object_or_404(
        RataIscrizione.objects.select_related(
            "famiglia",
            "iscrizione",
            "iscrizione__studente",
            "iscrizione__anno_scolastico",
            "metodo_pagamento",
        ),
        pk=pk,
    )
    popup = is_popup_request(request)
    initial_metodo_pagamento_id = request.session.get(LAST_METODO_PAGAMENTO_SESSION_KEY)

    if request.method == "POST":
        form = RataIscrizionePagamentoRapidoForm(
            request.POST,
            rata=rata,
            initial_metodo_pagamento_id=initial_metodo_pagamento_id,
        )
        if form.is_valid():
            pagamento_integrale = form.cleaned_data["pagamento_integrale"]
            importo_pagato = (
                rata.importo_finale
                if pagamento_integrale
                else form.cleaned_data["importo_pagato_personalizzato"]
            )
            metodo_pagamento = form.cleaned_data["metodo_pagamento"]

            rata.importo_pagato = importo_pagato or 0
            rata.data_pagamento = form.cleaned_data["data_pagamento"]
            rata.metodo_pagamento = metodo_pagamento
            rata.pagata = bool(importo_pagato and importo_pagato >= (rata.importo_finale or 0))
            rata.save(update_fields=["importo_pagato", "data_pagamento", "metodo_pagamento", "pagata", "importo_finale"])

            if metodo_pagamento:
                request.session[LAST_METODO_PAGAMENTO_SESSION_KEY] = metodo_pagamento.pk

            if popup:
                return render(
                    request,
                    "popup/popup_close.html",
                    {"message": "Pagamento registrato correttamente."},
                )

            messages.success(request, "Pagamento registrato correttamente.")
            return redirect("modifica_rata_iscrizione", pk=rata.pk)
    else:
        form = RataIscrizionePagamentoRapidoForm(
            rata=rata,
            initial_metodo_pagamento_id=initial_metodo_pagamento_id,
            initial={
                "pagamento_integrale": True,
                "data_pagamento": rata.data_pagamento or timezone.localdate(),
                "metodo_pagamento": rata.metodo_pagamento_id or initial_metodo_pagamento_id,
            },
        )

    return render(
        request,
        "economia/iscrizioni/rata_iscrizione_pagamento_rapido_form.html",
        {
            "form": form,
            "rata": rata,
            "popup": popup,
        },
    )


# =========================================================================
#  Verifica situazione rette (vista a matrice classi/mesi)
# =========================================================================

VERIFICA_RETTE_MESI_LABELS = {
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


def _calcola_stato_cella_rata(rata):
    """Ritorna uno stato semantico per colorare la cella della rata.

    Valori possibili (formato CSS-friendly, con trattino):
    - ``pagata``:     importo_pagato >= importo_finale (e dovuto > 0)
    - ``parziale``:   0 < importo_pagato < importo_finale
    - ``non-pagata``: importo_pagato == 0 e importo_finale > 0
    - ``non-dovuta``: importo_finale == 0 (es. preiscrizione non prevista)
    - ``assente``:    nessuna rata presente per quella colonna
    """
    if rata is None:
        return "assente"

    dovuto = rata.importo_finale or rata.importo_dovuto or Decimal("0.00")
    pagato = rata.importo_pagato or Decimal("0.00")

    if dovuto <= 0:
        return "non-dovuta"
    if pagato <= 0:
        return "non-pagata"
    if pagato >= dovuto:
        return "pagata"
    return "parziale"


def _classe_sort_key(iscrizione):
    """Chiave di ordinamento per raggruppare le iscrizioni per classe."""
    classe = iscrizione.classe
    if classe is None:
        # Le iscrizioni senza classe vanno in fondo.
        return (10**9, "", "", 0)
    return (
        classe.ordine_classe or 0,
        classe.nome_classe or "",
        classe.sezione_classe or "",
        classe.pk,
    )


def verifica_situazione_rette(request):
    """
    Pagina "Verifica situazione rette":

    - dropdown di selezione anno scolastico (default: quello corrente);
    - riga per ogni studente iscritto in quell'anno (ordinati per classe,
      poi cognome/nome);
    - colonne: Preiscrizione + mensilita' settembre -> giugno;
    - ogni cella mostra importo dovuto, importo pagato e data pagamento
      con un colore semantico (verde/giallo/rosso);
    - click sulla cella -> form di gestione della rata.
    """

    anni_scolastici = list(
        AnnoScolastico.objects.filter(attivo=True).order_by("-data_inizio")
    )

    selected_id = request.GET.get("anno_scolastico") or ""
    anno_scolastico = None
    if selected_id.isdigit():
        anno_scolastico = next(
            (a for a in anni_scolastici if a.pk == int(selected_id)),
            None,
        )
    if anno_scolastico is None:
        anno_scolastico = next(
            (a for a in anni_scolastici if a.corrente),
            None,
        )
    if anno_scolastico is None and anni_scolastici:
        anno_scolastico = anni_scolastici[0]

    colonne = []
    righe_per_classe = []
    ha_preiscrizione = False

    if anno_scolastico is not None:
        iscrizioni_qs = (
            Iscrizione.objects.filter(anno_scolastico=anno_scolastico, attiva=True)
            .select_related(
                "studente",
                "classe",
                "anno_scolastico",
            )
            .prefetch_related("rate")
            .order_by("studente__cognome", "studente__nome")
        )

        iscrizioni = sorted(
            iscrizioni_qs,
            key=lambda i: (
                _classe_sort_key(i),
                (i.studente.cognome or "").lower(),
                (i.studente.nome or "").lower(),
            ),
        )

        # Calcoliamo dinamicamente le colonne dei mesi osservando il piano rate
        # effettivo delle iscrizioni dell'anno scolastico selezionato. Questo
        # evita ipotesi hard-coded settembre->giugno e supporta configurazioni
        # di condizione iscrizione diverse.
        mesi_set = set()
        for iscrizione in iscrizioni:
            for rata in iscrizione.rate.all():
                if rata.is_preiscrizione:
                    ha_preiscrizione = True
                else:
                    if rata.anno_riferimento and rata.mese_riferimento:
                        mesi_set.add((rata.anno_riferimento, rata.mese_riferimento))

        mesi_ordinati = sorted(mesi_set)  # tuple (anno, mese)

        if ha_preiscrizione:
            colonne.append(
                {
                    "tipo": "preiscrizione",
                    "mese": None,
                    "anno": None,
                    "key": "preiscrizione",
                    "label": "Preiscrizione",
                }
            )
        for anno_mese in mesi_ordinati:
            anno_r, mese_r = anno_mese
            colonne.append(
                {
                    "tipo": "mese",
                    "mese": mese_r,
                    "anno": anno_r,
                    "key": anno_mese,
                    "label": VERIFICA_RETTE_MESI_LABELS.get(mese_r, str(mese_r)),
                }
            )

        # Raggruppiamo le iscrizioni per classe preservando l'ordinamento.
        gruppi = {}
        for iscrizione in iscrizioni:
            classe = iscrizione.classe
            classe_key = classe.pk if classe else None
            if classe_key not in gruppi:
                gruppi[classe_key] = {
                    "classe": classe,
                    "classe_label": str(classe) if classe else "Senza classe",
                    "iscrizioni": [],
                }
            gruppi[classe_key]["iscrizioni"].append(iscrizione)

        for classe_key, gruppo in gruppi.items():
            righe = []
            for iscrizione in gruppo["iscrizioni"]:
                # Indicizziamo le rate dell'iscrizione per chiave colonna.
                rate_per_chiave = {}
                for rata in iscrizione.rate.all():
                    if rata.is_preiscrizione:
                        rate_per_chiave["preiscrizione"] = rata
                    else:
                        chiave = (rata.anno_riferimento, rata.mese_riferimento)
                        rate_per_chiave.setdefault(chiave, rata)

                celle = []
                for colonna in colonne:
                    rata = rate_per_chiave.get(colonna["key"])
                    stato = _calcola_stato_cella_rata(rata)
                    celle.append(
                        {
                            "colonna": colonna,
                            "rata": rata,
                            "stato": stato,
                            "url": (
                                reverse("modifica_rata_iscrizione", args=[rata.pk])
                                if rata
                                else ""
                            ),
                        }
                    )

                righe.append(
                    {
                        "iscrizione": iscrizione,
                        "studente": iscrizione.studente,
                        "celle": celle,
                    }
                )

            righe_per_classe.append(
                {
                    "classe": gruppo["classe"],
                    "classe_label": gruppo["classe_label"],
                    "righe": righe,
                }
            )

    return render(
        request,
        "economia/iscrizioni/verifica_situazione_rette.html",
        {
            "anni_scolastici": anni_scolastici,
            "anno_scolastico": anno_scolastico,
            "colonne": colonne,
            "righe_per_classe": righe_per_classe,
            "num_colonne": len(colonne) + 1,  # +1 per la prima colonna "Studente"
        },
    )
