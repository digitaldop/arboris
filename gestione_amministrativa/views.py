from decimal import Decimal

from django.contrib import messages
from django.db.models import Count, Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from anagrafica.views import is_popup_request, popup_delete_response, popup_select_response

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
    ContrattoDipendente,
    Dipendente,
    ParametroCalcoloStipendio,
    SimulazioneCostoDipendente,
    StatoDipendente,
    TipoContrattoDipendente,
)
from .services import crea_o_aggiorna_previsione_busta_paga


ZERO = Decimal("0.00")


def _current_period():
    today = timezone.localdate()
    return today.year, today.month


def dashboard_gestione_amministrativa(request):
    anno, mese = _current_period()
    buste_periodo = BustaPagaDipendente.objects.filter(anno=anno, mese=mese)
    ultimi_cedolini = (
        BustaPagaDipendente.objects.select_related("dipendente", "contratto", "contratto__tipo_contratto")
        .order_by("-anno", "-mese", "dipendente__cognome", "dipendente__nome")[:12]
    )
    aggregates = buste_periodo.aggregate(
        costo_previsto=Sum("costo_azienda_previsto"),
        costo_effettivo=Sum("costo_azienda_effettivo"),
        netto_previsto=Sum("netto_previsto"),
        netto_effettivo=Sum("netto_effettivo"),
    )

    return render(
        request,
        "gestione_amministrativa/dashboard.html",
        {
            "anno": anno,
            "mese": mese,
            "dipendenti_attivi": Dipendente.objects.filter(stato=StatoDipendente.ATTIVO).count(),
            "dipendenti_totali": Dipendente.objects.count(),
            "contratti_attivi": ContrattoDipendente.objects.filter(attivo=True).count(),
            "simulazioni_attive": SimulazioneCostoDipendente.objects.filter(attiva=True).count(),
            "buste_periodo_count": buste_periodo.count(),
            "costo_previsto": aggregates["costo_previsto"] or ZERO,
            "costo_effettivo": aggregates["costo_effettivo"] or ZERO,
            "netto_previsto": aggregates["netto_previsto"] or ZERO,
            "netto_effettivo": aggregates["netto_effettivo"] or ZERO,
            "ultimi_cedolini": ultimi_cedolini,
        },
    )


def lista_dipendenti(request):
    dipendenti = Dipendente.objects.all()
    q = (request.GET.get("q") or "").strip()
    stato = (request.GET.get("stato") or "").strip()
    if q:
        dipendenti = dipendenti.filter(
            Q(nome__icontains=q)
            | Q(cognome__icontains=q)
            | Q(codice_dipendente__icontains=q)
            | Q(codice_fiscale__icontains=q)
            | Q(email__icontains=q)
        )
    if stato:
        dipendenti = dipendenti.filter(stato=stato)

    anno, mese = _current_period()
    return render(
        request,
        "gestione_amministrativa/dipendenti/dipendente_list.html",
        {
            "dipendenti": dipendenti,
            "q": q,
            "stato": stato,
            "stati": StatoDipendente.choices,
            "anno_corrente": anno,
            "mese_corrente": mese,
        },
    )


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

    return render(
        request,
        "gestione_amministrativa/dipendenti/contratto_list.html",
        {
            "contratti": contratti,
            "dipendenti": Dipendente.objects.order_by("cognome", "nome"),
            "dipendente_id": dipendente_id,
            "attivo": attivo,
        },
    )


def lista_simulazioni_costo_dipendenti(request):
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

    return render(
        request,
        "gestione_amministrativa/dipendenti/simulazione_costo_list.html",
        {
            "simulazioni": simulazioni,
            "dipendenti": Dipendente.objects.order_by("cognome", "nome"),
            "contratti": ContrattoDipendente.objects.select_related("dipendente", "tipo_contratto").order_by(
                "dipendente__cognome", "dipendente__nome", "-data_inizio"
            ),
            "dipendente_id": dipendente_id,
            "contratto_id": contratto_id,
            "attiva": attiva,
        },
    )


def crea_dipendente(request):
    if request.method == "POST":
        form = DipendenteForm(request.POST)
        if form.is_valid():
            dipendente = form.save()
            messages.success(request, "Dipendente creato correttamente.")
            return redirect("modifica_dipendente", pk=dipendente.pk)
    else:
        form = DipendenteForm()

    return render(
        request,
        "gestione_amministrativa/dipendenti/dipendente_form.html",
        {"form": form, "dipendente": None, "contratti": [], "buste_paga": [], "simulazioni_costo": []},
    )


def modifica_dipendente(request, pk):
    dipendente = get_object_or_404(Dipendente, pk=pk)
    if request.method == "POST":
        form = DipendenteForm(request.POST, instance=dipendente)
        if form.is_valid():
            form.save()
            messages.success(request, "Dipendente aggiornato correttamente.")
            return redirect("modifica_dipendente", pk=dipendente.pk)
    else:
        form = DipendenteForm(instance=dipendente)

    contratti = dipendente.contratti.all()
    buste_paga = dipendente.buste_paga.select_related("contratto").order_by("-anno", "-mese")[:12]
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
            "dipendente": dipendente,
            "contratti": contratti,
            "buste_paga": buste_paga,
            "simulazioni_costo": simulazioni_costo,
        },
    )


def elimina_dipendente(request, pk):
    dipendente = get_object_or_404(Dipendente, pk=pk)
    count_relazioni = (
        dipendente.contratti.count()
        + dipendente.buste_paga.count()
        + dipendente.documenti.count()
    )
    if request.method == "POST":
        if count_relazioni:
            messages.error(
                request,
                "Impossibile eliminare il dipendente: sono presenti contratti, buste paga o documenti collegati.",
            )
            return redirect("modifica_dipendente", pk=dipendente.pk)
        dipendente.delete()
        messages.success(request, "Dipendente eliminato correttamente.")
        return redirect("lista_dipendenti")

    return render(
        request,
        "gestione_amministrativa/dipendenti/dipendente_confirm_delete.html",
        {"dipendente": dipendente, "count_relazioni": count_relazioni},
    )


def crea_contratto_dipendente(request, dipendente_pk=None):
    popup = is_popup_request(request)
    dipendente = None
    requested_dipendente = dipendente_pk or request.GET.get("dipendente") or request.POST.get("dipendente")
    if requested_dipendente:
        dipendente = get_object_or_404(Dipendente, pk=requested_dipendente)

    if request.method == "POST":
        form = ContrattoDipendenteForm(request.POST)
        if form.is_valid():
            contratto = form.save(commit=False)
            if dipendente:
                contratto.dipendente = dipendente
            contratto.save()
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
        form = ContrattoDipendenteForm()

    return render(
        request,
        "gestione_amministrativa/dipendenti/contratto_popup_form.html" if popup else "gestione_amministrativa/dipendenti/contratto_form.html",
        {"form": form, "dipendente": dipendente, "contratto": None, "popup": popup},
    )


def modifica_contratto_dipendente(request, pk):
    contratto = get_object_or_404(
        ContrattoDipendente.objects.select_related("dipendente", "tipo_contratto", "parametro_calcolo"),
        pk=pk,
    )
    popup = is_popup_request(request)
    if request.method == "POST":
        form = ContrattoDipendenteForm(request.POST, instance=contratto)
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
        form = ContrattoDipendenteForm(instance=contratto)

    simulazioni_costo = contratto.simulazioni_costo.order_by("-valido_dal", "-id")
    return render(
        request,
        "gestione_amministrativa/dipendenti/contratto_popup_form.html" if popup else "gestione_amministrativa/dipendenti/contratto_form.html",
        {
            "form": form,
            "dipendente": contratto.dipendente,
            "contratto": contratto,
            "popup": popup,
            "simulazioni_costo": simulazioni_costo,
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
                    "gestione_amministrativa/dipendenti/contratto_popup_delete.html",
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
        "gestione_amministrativa/dipendenti/contratto_popup_delete.html" if popup else "gestione_amministrativa/dipendenti/contratto_confirm_delete.html",
        {
            "contratto": contratto,
            "count_buste": count_buste,
            "count_simulazioni": count_simulazioni,
            "popup": popup,
            "blocked": False,
        },
    )


def crea_simulazione_costo_dipendente(request):
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
            messages.success(request, "Simulazione costo dipendente salvata correttamente.")
            return redirect("modifica_simulazione_costo_dipendente", pk=simulazione.pk)
    else:
        form = SimulazioneCostoDipendenteForm(initial=initial)

    return render(
        request,
        "gestione_amministrativa/dipendenti/simulazione_costo_form.html",
        {"form": form, "simulazione": None},
    )


def modifica_simulazione_costo_dipendente(request, pk):
    simulazione = get_object_or_404(
        SimulazioneCostoDipendente.objects.select_related("contratto", "contratto__dipendente", "contratto__tipo_contratto"),
        pk=pk,
    )
    if request.method == "POST":
        form = SimulazioneCostoDipendenteForm(request.POST, request.FILES, instance=simulazione)
        if form.is_valid():
            simulazione = form.save()
            messages.success(request, "Simulazione costo dipendente aggiornata correttamente.")
            return redirect("modifica_simulazione_costo_dipendente", pk=simulazione.pk)
    else:
        form = SimulazioneCostoDipendenteForm(instance=simulazione)

    return render(
        request,
        "gestione_amministrativa/dipendenti/simulazione_costo_form.html",
        {"form": form, "simulazione": simulazione},
    )


def elimina_simulazione_costo_dipendente(request, pk):
    simulazione = get_object_or_404(
        SimulazioneCostoDipendente.objects.select_related("contratto", "contratto__dipendente"),
        pk=pk,
    )
    if request.method == "POST":
        contratto = simulazione.contratto
        simulazione.delete()
        messages.success(request, "Simulazione costo dipendente eliminata correttamente.")
        if contratto and contratto.dipendente_id:
            return redirect("modifica_dipendente", pk=contratto.dipendente_id)
        return redirect("lista_simulazioni_costo_dipendenti")

    return render(
        request,
        "gestione_amministrativa/dipendenti/simulazione_costo_confirm_delete.html",
        {"simulazione": simulazione},
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

    return render(
        request,
        "gestione_amministrativa/dipendenti/busta_paga_list.html",
        {
            "buste": buste,
            "anno": anno,
            "mese": mese,
            "dipendente_id": dipendente_id,
            "dipendenti": Dipendente.objects.order_by("cognome", "nome"),
        },
    )


def crea_busta_paga_dipendente(request):
    initial = {}
    anno, mese = _current_period()
    initial["anno"] = anno
    initial["mese"] = mese
    dipendente_id = (request.GET.get("dipendente") or "").strip()
    if dipendente_id.isdigit():
        initial["dipendente"] = int(dipendente_id)

    if request.method == "POST":
        form = BustaPagaDipendenteForm(request.POST, request.FILES)
        if form.is_valid():
            busta = form.save()
            messages.success(request, "Busta paga salvata correttamente.")
            return redirect("modifica_busta_paga_dipendente", pk=busta.pk)
    else:
        form = BustaPagaDipendenteForm(initial=initial)

    return render(
        request,
        "gestione_amministrativa/dipendenti/busta_paga_form.html",
        {"form": form, "busta": None},
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
    if request.method == "POST":
        form = BustaPagaDipendenteForm(request.POST, request.FILES, instance=busta)
        if form.is_valid():
            form.save()
            messages.success(request, "Busta paga aggiornata correttamente.")
            return redirect("modifica_busta_paga_dipendente", pk=busta.pk)
    else:
        form = BustaPagaDipendenteForm(instance=busta)

    return render(
        request,
        "gestione_amministrativa/dipendenti/busta_paga_form.html",
        {"form": form, "busta": busta, "voci": busta.voci.all()},
    )


def elimina_busta_paga_dipendente(request, pk):
    busta = get_object_or_404(BustaPagaDipendente.objects.select_related("dipendente"), pk=pk)
    if request.method == "POST":
        busta.delete()
        messages.success(request, "Busta paga eliminata correttamente.")
        return redirect("lista_buste_paga_dipendenti")

    return render(
        request,
        "gestione_amministrativa/dipendenti/busta_paga_confirm_delete.html",
        {"busta": busta},
    )


def lista_parametri_calcolo_stipendi(request):
    parametri = ParametroCalcoloStipendio.objects.all()
    return render(
        request,
        "gestione_amministrativa/dipendenti/parametri_list.html",
        {"parametri": parametri},
    )


def crea_parametro_calcolo_stipendio(request):
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
        "gestione_amministrativa/dipendenti/parametro_popup_form.html" if popup else "gestione_amministrativa/dipendenti/parametro_form.html",
        {"form": form, "parametro": None, "popup": popup},
    )


def modifica_parametro_calcolo_stipendio(request, pk):
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
        "gestione_amministrativa/dipendenti/parametro_popup_form.html" if popup else "gestione_amministrativa/dipendenti/parametro_form.html",
        {"form": form, "parametro": parametro, "popup": popup},
    )


def elimina_parametro_calcolo_stipendio(request, pk):
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
        "gestione_amministrativa/dipendenti/parametro_popup_delete.html" if popup else "gestione_amministrativa/dipendenti/parametro_confirm_delete.html",
        {"parametro": parametro, "popup": popup, "usage_count": usage_count},
    )
