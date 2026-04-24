from decimal import Decimal

from django.contrib import messages
from django.db.models import Count, Prefetch, Q
from django.db.models.deletion import ProtectedError
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from servizi_extra.forms import (
    ServizioExtraForm,
    TariffaServizioExtraForm,
    TariffaServizioExtraRataFormSet,
    IscrizioneServizioExtraForm,
    RataServizioExtraPagamentoForm,
)
from servizi_extra.models import (
    ServizioExtra,
    TariffaServizioExtra,
    IscrizioneServizioExtra,
    RataServizioExtra,
)


def sync_tariffa_rate_schedules(tariffa):
    summary = {}

    iscrizioni = (
        tariffa.iscrizioni.select_related(
            "studente",
            "servizio",
            "tariffa",
        )
        .prefetch_related("rate")
        .all()
    )

    for iscrizione in iscrizioni:
        outcome = iscrizione.sync_rate_schedule()
        summary[outcome] = summary.get(outcome, 0) + 1

    return summary


def build_tariffa_sync_feedback(summary):
    if not summary:
        return ""

    feedback_parts = []

    if summary.get("created"):
        feedback_parts.append(f"{summary['created']} piano/i rate creati")
    if summary.get("regenerated"):
        feedback_parts.append(f"{summary['regenerated']} piano/i rate riallineati")
    if summary.get("unchanged"):
        feedback_parts.append(f"{summary['unchanged']} gia allineati")
    if summary.get("locked"):
        feedback_parts.append(f"{summary['locked']} non modificati perche con pagamenti")
    if summary.get("missing"):
        feedback_parts.append(f"{summary['missing']} non generabili per assenza di rate tariffarie")

    return ". ".join(feedback_parts)


def _calcola_stato_cella_rata(rata):
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


def _classe_sort_key(classe):
    if classe is None:
        return (10**9, "", "", 0)

    return (
        classe.ordine_classe or 0,
        classe.nome_classe or "",
        classe.sezione_classe or "",
        classe.pk,
    )


def _build_servizio_extra_class_map(servizio, student_ids):
    if not student_ids:
        return {}

    from economia.models import Iscrizione as IscrizioneEconomia

    class_map = {}
    iscrizioni_economia = (
        IscrizioneEconomia.objects.filter(
            anno_scolastico=servizio.anno_scolastico,
            studente_id__in=student_ids,
        )
        .select_related("classe")
        .order_by("-attiva", "id")
    )

    for iscrizione in iscrizioni_economia:
        class_map.setdefault(iscrizione.studente_id, iscrizione.classe)

    return class_map


def _build_servizio_extra_overview(servizio):
    today = timezone.localdate()
    tariffe_cards = []

    for tariffa in servizio.tariffe.all():
        rate_config = list(tariffa.rate_config.all())
        totale_importo = Decimal("0.00")
        prima_scadenza = None
        ultima_scadenza = None

        for rata_config in rate_config:
            totale_importo += rata_config.importo or Decimal("0.00")
            if prima_scadenza is None or rata_config.data_scadenza < prima_scadenza:
                prima_scadenza = rata_config.data_scadenza
            if ultima_scadenza is None or rata_config.data_scadenza > ultima_scadenza:
                ultima_scadenza = rata_config.data_scadenza

        tariffe_cards.append(
            {
                "pk": tariffa.pk,
                "nome_tariffa": tariffa.nome_tariffa,
                "attiva": tariffa.attiva,
                "rateizzata": tariffa.rateizzata,
                "numero_rate": len(rate_config),
                "totale_importo": totale_importo,
                "count_iscrizioni": getattr(tariffa, "count_iscrizioni", 0),
                "count_iscrizioni_attive": getattr(tariffa, "count_iscrizioni_attive", 0),
                "prima_scadenza": prima_scadenza,
                "ultima_scadenza": ultima_scadenza,
            }
        )

    rate_summary_rows = list(
        RataServizioExtra.objects.filter(iscrizione__servizio=servizio)
        .values("data_scadenza", "importo_finale", "importo_dovuto", "importo_pagato")
    )

    totale_dovuto = Decimal("0.00")
    totale_pagato = Decimal("0.00")
    count_rate_aperte = 0
    count_rate_scadute = 0
    prossima_scadenza = None

    for rata in rate_summary_rows:
        importo_finale = rata["importo_finale"] or rata["importo_dovuto"] or Decimal("0.00")
        importo_pagato = rata["importo_pagato"] or Decimal("0.00")
        data_scadenza = rata["data_scadenza"]
        saldo_aperto = max(importo_finale - importo_pagato, Decimal("0.00"))

        totale_dovuto += importo_finale
        totale_pagato += importo_pagato

        if saldo_aperto > 0:
            count_rate_aperte += 1
            if data_scadenza and data_scadenza < today:
                count_rate_scadute += 1
            if data_scadenza and (prossima_scadenza is None or data_scadenza < prossima_scadenza):
                prossima_scadenza = data_scadenza

    totale_aperto = max(totale_dovuto - totale_pagato, Decimal("0.00"))

    overview_cards = [
        {
            "label": "Servizio",
            "value": servizio.nome_servizio,
            "value_type": "text",
            "note": servizio.descrizione or "Nessuna descrizione inserita.",
        },
        {
            "label": "Anno scolastico",
            "value": servizio.anno_scolastico.nome_anno_scolastico,
            "value_type": "text",
            "note": f"Ordine menu: {servizio.ordine}",
        },
        {
            "label": "Stato servizio",
            "value": "Attivo" if servizio.attiva else "Inattivo",
            "value_type": "text",
            "note": f"Tariffe attive: {getattr(servizio, 'count_tariffe_attive', 0)} su {getattr(servizio, 'count_tariffe', 0)}",
        },
        {
            "label": "Note interne",
            "value": servizio.note or "-",
            "value_type": "text",
            "note": "Note amministrative del servizio.",
        },
        {
            "label": "Iscrizioni",
            "value": f"{getattr(servizio, 'count_iscrizioni_attive', 0)} attive",
            "value_type": "text",
            "note": f"Totali registrate: {getattr(servizio, 'count_iscrizioni', 0)}",
        },
        {
            "label": "Totale dovuto",
            "value": totale_dovuto,
            "value_type": "currency",
            "note": "Somma di tutte le rate generate per il servizio.",
        },
        {
            "label": "Totale incassato",
            "value": totale_pagato,
            "value_type": "currency",
            "note": "Pagamenti registrati sulle rate del servizio.",
        },
        {
            "label": "Totale aperto",
            "value": totale_aperto,
            "value_type": "currency",
            "note": f"Rate ancora aperte: {count_rate_aperte}",
        },
        {
            "label": "Prossima scadenza",
            "value": prossima_scadenza,
            "value_type": "date",
            "note": f"Rate scadute non saldate: {count_rate_scadute}",
        },
    ]

    return {
        "overview_cards": overview_cards,
        "tariffe_cards": tariffe_cards,
    }


def lista_servizi_extra(request):
    servizi = (
        ServizioExtra.objects.select_related("anno_scolastico")
        .annotate(count_tariffe=Count("tariffe", distinct=True), count_iscrizioni=Count("iscrizioni", distinct=True))
        .all()
    )
    return render(request, "servizi_extra/servizi_list.html", {"servizi": servizi})


def dettaglio_servizio_extra(request, pk):
    servizio = get_object_or_404(
        ServizioExtra.objects.select_related("anno_scolastico")
        .annotate(
            count_tariffe=Count("tariffe", distinct=True),
            count_tariffe_attive=Count("tariffe", filter=Q(tariffe__attiva=True), distinct=True),
            count_iscrizioni=Count("iscrizioni", distinct=True),
            count_iscrizioni_attive=Count("iscrizioni", filter=Q(iscrizioni__attiva=True), distinct=True),
        )
        .prefetch_related(
            Prefetch(
                "tariffe",
                queryset=TariffaServizioExtra.objects.annotate(
                    count_iscrizioni=Count("iscrizioni", distinct=True),
                    count_iscrizioni_attive=Count(
                        "iscrizioni",
                        filter=Q(iscrizioni__attiva=True),
                        distinct=True,
                    ),
                )
                .prefetch_related("rate_config")
                .order_by("nome_tariffa", "id"),
            ),
            Prefetch(
                "iscrizioni",
                queryset=IscrizioneServizioExtra.objects.filter(attiva=True)
                .select_related(
                    "studente",
                    "studente__famiglia",
                    "tariffa",
                    "servizio",
                    "servizio__anno_scolastico",
                )
                .prefetch_related("rate")
                .order_by("studente__cognome", "studente__nome", "id"),
                to_attr="iscrizioni_attive_list",
            ),
        ),
        pk=pk,
    )

    overview_data = _build_servizio_extra_overview(servizio)
    iscrizioni_attive = list(getattr(servizio, "iscrizioni_attive_list", []))
    class_map = _build_servizio_extra_class_map(
        servizio,
        [iscrizione.studente_id for iscrizione in iscrizioni_attive],
    )

    iscrizioni_attive.sort(
        key=lambda iscrizione: (
            _classe_sort_key(class_map.get(iscrizione.studente_id)),
            (iscrizione.studente.cognome or "").lower(),
            (iscrizione.studente.nome or "").lower(),
            iscrizione.studente_id,
        )
    )

    colonne_map = {}
    for iscrizione in iscrizioni_attive:
        for rata in iscrizione.rate.all():
            chiave = (rata.data_scadenza, rata.numero_rata)
            colonne_map.setdefault(
                chiave,
                {
                    "key": chiave,
                    "numero_rata": rata.numero_rata,
                    "data_scadenza": rata.data_scadenza,
                    "descrizione": rata.display_label,
                },
            )

    colonne = [
        colonne_map[chiave]
        for chiave in sorted(
            colonne_map.keys(),
            key=lambda item: (
                item[0],
                item[1],
            ),
        )
    ]

    gruppi = {}
    for iscrizione in iscrizioni_attive:
        classe = class_map.get(iscrizione.studente_id)
        classe_key = classe.pk if classe else None
        gruppo = gruppi.setdefault(
            classe_key,
            {
                "classe": classe,
                "classe_label": str(classe) if classe else "Senza classe",
                "righe": [],
            },
        )

        rate_per_chiave = {(rata.data_scadenza, rata.numero_rata): rata for rata in iscrizione.rate.all()}
        celle = []
        for colonna in colonne:
            rata = rate_per_chiave.get(colonna["key"])
            celle.append(
                {
                    "colonna": colonna,
                    "rata": rata,
                    "stato": _calcola_stato_cella_rata(rata),
                    "url": reverse("modifica_rata_servizio_extra", args=[rata.pk]) if rata else "",
                }
            )

        gruppo["righe"].append(
            {
                "iscrizione": iscrizione,
                "studente": iscrizione.studente,
                "riepilogo": iscrizione.get_riepilogo(),
                "celle": celle,
            }
        )

    righe_per_classe = list(gruppi.values())

    return render(
        request,
        "servizi_extra/servizio_detail.html",
        {
            "servizio": servizio,
            "overview_cards": overview_data["overview_cards"],
            "tariffe_cards": overview_data["tariffe_cards"],
            "colonne": colonne,
            "righe_per_classe": righe_per_classe,
            "num_colonne": len(colonne) + 1,
        },
    )


def crea_servizio_extra(request):
    if request.method == "POST":
        form = ServizioExtraForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Servizio extra creato correttamente.")
            return redirect("lista_servizi_extra")
    else:
        form = ServizioExtraForm()

    return render(request, "servizi_extra/servizio_form.html", {"form": form, "servizio": None})


def modifica_servizio_extra(request, pk):
    servizio = get_object_or_404(ServizioExtra, pk=pk)

    if request.method == "POST":
        form = ServizioExtraForm(request.POST, instance=servizio)
        if form.is_valid():
            form.save()
            messages.success(request, "Servizio extra aggiornato correttamente.")
            return redirect("lista_servizi_extra")
    else:
        form = ServizioExtraForm(instance=servizio)

    return render(request, "servizi_extra/servizio_form.html", {"form": form, "servizio": servizio})


def elimina_servizio_extra(request, pk):
    servizio = get_object_or_404(
        ServizioExtra.objects.annotate(
            count_tariffe=Count("tariffe", distinct=True),
            count_iscrizioni=Count("iscrizioni", distinct=True),
        ),
        pk=pk,
    )

    if request.method == "POST":
        try:
            servizio.delete()
        except ProtectedError:
            messages.error(request, "Non puoi eliminare questo servizio extra perche e collegato a iscrizioni esistenti.")
            return redirect("modifica_servizio_extra", pk=servizio.pk)

        messages.success(request, "Servizio extra eliminato correttamente.")
        return redirect("lista_servizi_extra")

    return render(request, "servizi_extra/servizio_confirm_delete.html", {"servizio": servizio})


def lista_tariffe_servizi_extra(request):
    servizio_id = request.GET.get("servizio") or ""
    servizio = None

    tariffe = (
        TariffaServizioExtra.objects.select_related("servizio", "servizio__anno_scolastico")
        .annotate(count_iscrizioni=Count("iscrizioni", distinct=True))
        .prefetch_related("rate_config")
        .all()
    )

    if servizio_id.isdigit():
        servizio = get_object_or_404(ServizioExtra.objects.select_related("anno_scolastico"), pk=servizio_id)
        tariffe = tariffe.filter(servizio_id=servizio.pk)

    return render(
        request,
        "servizi_extra/tariffe_list.html",
        {
            "tariffe": tariffe,
            "servizio_filtro": servizio,
        },
    )


def crea_tariffa_servizio_extra(request):
    tariffa = TariffaServizioExtra()

    if request.method == "POST":
        form = TariffaServizioExtraForm(request.POST, instance=tariffa)
        formset = TariffaServizioExtraRataFormSet(request.POST, instance=tariffa, prefix="rate")
        if form.is_valid() and formset.is_valid():
            tariffa = form.save()
            formset.instance = tariffa
            formset.save()
            messages.success(request, "Tariffa servizio extra creata correttamente.")
            return redirect("lista_tariffe_servizi_extra")
    else:
        form = TariffaServizioExtraForm(instance=tariffa)
        formset = TariffaServizioExtraRataFormSet(instance=tariffa, prefix="rate")

    return render(
        request,
        "servizi_extra/tariffa_form.html",
        {
            "form": form,
            "formset": formset,
            "tariffa": None,
        },
    )


def modifica_tariffa_servizio_extra(request, pk):
    tariffa = get_object_or_404(TariffaServizioExtra, pk=pk)

    if request.method == "POST":
        form = TariffaServizioExtraForm(request.POST, instance=tariffa)
        formset = TariffaServizioExtraRataFormSet(request.POST, instance=tariffa, prefix="rate")
        if form.is_valid() and formset.is_valid():
            has_changed = bool(form.changed_data) or formset.has_changed()
            tariffa = form.save()
            formset.instance = tariffa
            formset.save()

            sync_feedback = ""
            if has_changed:
                sync_feedback = build_tariffa_sync_feedback(sync_tariffa_rate_schedules(tariffa))

            success_message = "Tariffa servizio extra aggiornata correttamente."
            if sync_feedback:
                success_message = f"{success_message} {sync_feedback}."

            messages.success(request, success_message)
            return redirect("lista_tariffe_servizi_extra")
    else:
        form = TariffaServizioExtraForm(instance=tariffa)
        formset = TariffaServizioExtraRataFormSet(instance=tariffa, prefix="rate")

    return render(
        request,
        "servizi_extra/tariffa_form.html",
        {
            "form": form,
            "formset": formset,
            "tariffa": tariffa,
        },
    )


def elimina_tariffa_servizio_extra(request, pk):
    tariffa = get_object_or_404(
        TariffaServizioExtra.objects.select_related("servizio", "servizio__anno_scolastico").annotate(
            count_iscrizioni=Count("iscrizioni", distinct=True)
        ),
        pk=pk,
    )

    if request.method == "POST":
        try:
            tariffa.delete()
        except ProtectedError:
            messages.error(request, "Non puoi eliminare questa tariffa perche e collegata a iscrizioni esistenti.")
            return redirect("modifica_tariffa_servizio_extra", pk=tariffa.pk)

        messages.success(request, "Tariffa servizio extra eliminata correttamente.")
        return redirect("lista_tariffe_servizi_extra")

    return render(
        request,
        "servizi_extra/tariffa_confirm_delete.html",
        {
            "tariffa": tariffa,
            "count_rate": tariffa.rate_config.count(),
        },
    )


def lista_iscrizioni_servizi_extra(request):
    servizio_id = request.GET.get("servizio") or ""
    servizio = None

    iscrizioni = (
        IscrizioneServizioExtra.objects.select_related(
            "studente",
            "servizio",
            "servizio__anno_scolastico",
            "tariffa",
        )
        .annotate(count_rate=Count("rate", distinct=True))
        .all()
    )

    if servizio_id.isdigit():
        servizio = get_object_or_404(ServizioExtra.objects.select_related("anno_scolastico"), pk=servizio_id)
        iscrizioni = iscrizioni.filter(servizio_id=servizio.pk)

    return render(
        request,
        "servizi_extra/iscrizioni_list.html",
        {
            "iscrizioni": iscrizioni,
            "servizio_filtro": servizio,
        },
    )


def crea_iscrizione_servizio_extra(request):
    if request.method == "POST":
        form = IscrizioneServizioExtraForm(request.POST)
        if form.is_valid():
            iscrizione = form.save()
            esito_rate = iscrizione.sync_rate_schedule()

            if esito_rate == "created":
                messages.success(request, "Iscrizione al servizio extra creata correttamente e rate generate in automatico.")
            elif esito_rate == "missing":
                messages.warning(
                    request,
                    "Iscrizione creata correttamente, ma il piano rate non e stato generato: verifica la tariffa selezionata.",
                )
            else:
                messages.success(request, "Iscrizione al servizio extra creata correttamente.")

            return redirect("lista_iscrizioni_servizi_extra")
    else:
        form = IscrizioneServizioExtraForm()

    return render(
        request,
        "servizi_extra/iscrizione_form.html",
        {
            "form": form,
            "iscrizione": None,
            "riepilogo_servizio": None,
        },
    )


def modifica_iscrizione_servizio_extra(request, pk):
    iscrizione = get_object_or_404(IscrizioneServizioExtra, pk=pk)

    if request.method == "POST":
        form = IscrizioneServizioExtraForm(request.POST, instance=iscrizione)
        if form.is_valid():
            iscrizione = form.save()
            esito_rate = iscrizione.sync_rate_schedule()

            if esito_rate == "regenerated":
                messages.success(request, "Iscrizione aggiornata correttamente. Il piano rate e stato riallineato.")
            elif esito_rate == "missing":
                messages.warning(
                    request,
                    "Iscrizione aggiornata correttamente, ma il piano rate non e stato generato: verifica la tariffa selezionata.",
                )
            elif esito_rate == "locked":
                messages.success(
                    request,
                    "Iscrizione aggiornata correttamente. Le rate esistenti non sono state rigenerate perche contengono gia pagamenti.",
                )
            else:
                messages.success(request, "Iscrizione aggiornata correttamente.")

            return redirect("lista_iscrizioni_servizi_extra")
    else:
        form = IscrizioneServizioExtraForm(instance=iscrizione)

    return render(
        request,
        "servizi_extra/iscrizione_form.html",
        {
            "form": form,
            "iscrizione": iscrizione,
            "riepilogo_servizio": iscrizione.get_riepilogo(),
        },
    )


@require_POST
def ricalcola_rate_iscrizione_servizio_extra(request, pk):
    iscrizione = get_object_or_404(IscrizioneServizioExtra, pk=pk)
    esito_rate = iscrizione.sync_rate_schedule()
    next_url = request.POST.get("next", "")

    if esito_rate == "created":
        messages.success(request, "Piano rate generato correttamente.")
    elif esito_rate == "regenerated":
        messages.success(request, "Piano rate ricalcolato correttamente.")
    elif esito_rate == "unchanged":
        messages.info(request, "Il piano rate era gia allineato.")
    elif esito_rate == "locked":
        messages.warning(request, "Le rate esistenti non sono state rigenerate perche contengono gia pagamenti.")
    else:
        messages.warning(request, "Impossibile generare il piano rate: verifica la tariffa selezionata.")

    if next_url and url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
        return redirect(next_url)

    return redirect("modifica_iscrizione_servizio_extra", pk=iscrizione.pk)


def elimina_iscrizione_servizio_extra(request, pk):
    iscrizione = get_object_or_404(IscrizioneServizioExtra, pk=pk)
    count_rate = iscrizione.rate.count()

    if request.method == "POST":
        confirm_rates = request.POST.get("confirm_delete_rates") == "1"
        confirm_text = (request.POST.get("confirm_delete_text") or "").strip().upper()

        if count_rate and (not confirm_rates or confirm_text != "ELIMINA"):
            messages.error(
                request,
                "Per eliminare l'iscrizione devi confermare esplicitamente anche l'eliminazione delle rate associate.",
            )
            return render(
                request,
                "servizi_extra/iscrizione_confirm_delete.html",
                {"iscrizione": iscrizione, "count_rate": count_rate},
            )

        iscrizione.delete()
        messages.success(request, "Iscrizione al servizio extra eliminata correttamente.")
        return redirect("lista_iscrizioni_servizi_extra")

    return render(
        request,
        "servizi_extra/iscrizione_confirm_delete.html",
        {"iscrizione": iscrizione, "count_rate": count_rate},
    )


def lista_rate_servizi_extra(request):
    iscrizione_id = request.GET.get("iscrizione")
    servizio_id = request.GET.get("servizio") or ""
    iscrizione = None
    servizio = None

    rate = RataServizioExtra.objects.select_related(
        "famiglia",
        "iscrizione",
        "iscrizione__studente",
        "iscrizione__servizio",
        "iscrizione__servizio__anno_scolastico",
    ).all()

    if iscrizione_id:
        rate = rate.filter(iscrizione_id=iscrizione_id)
        iscrizione = (
            IscrizioneServizioExtra.objects.select_related("studente", "servizio", "servizio__anno_scolastico")
            .filter(pk=iscrizione_id)
            .first()
        )
        if iscrizione:
            servizio = iscrizione.servizio

    if servizio is None and servizio_id.isdigit():
        servizio = get_object_or_404(ServizioExtra.objects.select_related("anno_scolastico"), pk=servizio_id)
        rate = rate.filter(iscrizione__servizio_id=servizio.pk)

    rate = rate.order_by(
        "-iscrizione__servizio__anno_scolastico__data_inizio",
        "iscrizione__servizio__nome_servizio",
        "iscrizione__studente__cognome",
        "iscrizione__studente__nome",
        "data_scadenza",
        "numero_rata",
    )

    return render(
        request,
        "servizi_extra/rate_list.html",
        {
            "rate": rate,
            "iscrizione_filtro": iscrizione,
            "servizio_filtro": servizio,
        },
    )


def modifica_rata_servizio_extra(request, pk):
    rata = get_object_or_404(
        RataServizioExtra.objects.select_related(
            "famiglia",
            "iscrizione",
            "iscrizione__studente",
            "iscrizione__servizio",
            "iscrizione__servizio__anno_scolastico",
        ),
        pk=pk,
    )

    fallback_back_url = f"{reverse('lista_rate_servizi_extra')}?iscrizione={rata.iscrizione_id}"
    requested_back_url = request.GET.get("next") or request.META.get("HTTP_REFERER", "")
    back_url = (
        requested_back_url
        if requested_back_url and url_has_allowed_host_and_scheme(requested_back_url, allowed_hosts={request.get_host()}, require_https=request.is_secure())
        else fallback_back_url
    )

    if request.method == "POST":
        form = RataServizioExtraPagamentoForm(request.POST, instance=rata)
        if form.is_valid():
            form.save()
            messages.success(request, "Dati pagamento rata aggiornati correttamente.")
            return redirect(back_url)
    else:
        form = RataServizioExtraPagamentoForm(instance=rata)

    return render(
        request,
        "servizi_extra/rata_form.html",
        {
            "form": form,
            "rata": rata,
            "back_url": back_url,
        },
    )
