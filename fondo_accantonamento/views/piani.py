from __future__ import annotations

from django.contrib import messages
from django.db import transaction
from django.db.models import F
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from scuola.utils import resolve_default_anno_scolastico

from ..forms import PianoAccantonamentoForm, PrelievoFondoForm, VersamentoFondoForm
from ..models import (
    MovimentoFondo,
    PianoAccantonamento,
    ScadenzaVersamento,
    TipoModalitaPiano,
    TipoMovimentoFondo,
)
from ..services import genera_scadenze_periodiche, soddisfa_scadenza_con_versamento


def _is_popup_request(request) -> bool:
    return request.GET.get("popup") == "1" or request.POST.get("popup") == "1"


def _popup_close(request, message: str):
    return render(request, "popup/popup_close.html", {"message": message})


def lista_piani(request):
    piani_qs = (
        PianoAccantonamento.objects.select_related("anno_scolastico")
        .all()
        .order_by(
            "-sempre_attivo",
            F("anno_scolastico__data_inizio").desc(nulls_last=True),
            "nome",
        )
    )
    piani = list(piani_qs)
    depositi = {
        (
            piano.tipo_deposito,
            (piano.descrizione_deposito or "").strip().lower(),
        )
        for piano in piani
        if piano.tipo_deposito or piano.descrizione_deposito
    }
    return render(
        request,
        "fondo_accantonamento/piani_list.html",
        {
            "piani": piani,
            "totale_piani": len(piani),
            "piani_attivi": sum(1 for piano in piani if piano.attivo),
            "depositi_count": len(depositi),
            "anno_scolastico_corrente": resolve_default_anno_scolastico(
                today=timezone.localdate()
            ),
        },
    )


def dettaglio_piano(request, pk: int):
    piano = get_object_or_404(
        PianoAccantonamento.objects.select_related("anno_scolastico"),
        pk=pk,
    )
    movimenti = list(
        piano.movimenti.select_related(
            "rata_iscrizione",
            "rata_iscrizione__iscrizione",
            "rata_iscrizione__iscrizione__studente",
            "scadenza_versamento",
        )
        .all()
        .order_by("-data", "-id")[:200]
    )
    scadenze = list(piano.scadenze.all().order_by("data_scadenza")[:500])
    totale_versamenti = piano.totale_versamenti()
    totale_uscite = piano.totale_uscite()
    return render(
        request,
        "fondo_accantonamento/piano_dettaglio.html",
        {
            "piano": piano,
            "movimenti": movimenti,
            "movimenti_count": len(movimenti),
            "scadenze": scadenze,
            "totale_versamenti": totale_versamenti,
            "totale_uscite": totale_uscite,
            "saldo_disponibile": totale_versamenti - totale_uscite,
            "mostra_sezione_scadenze": piano.modalita
            in (TipoModalitaPiano.VERSAMENTI_PERIODICI, TipoModalitaPiano.MISTO),
        },
    )


@transaction.atomic
def nuovo_piano(request):
    if request.method == "POST":
        form = PianoAccantonamentoForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Piano di accantonamento creato.")
            return redirect("fondo_piano_lista")
    else:
        form = PianoAccantonamentoForm()
    return render(
        request,
        "fondo_accantonamento/piano_form.html",
        {
            "form": form,
            "titolo": "Nuovo piano di accantonamento",
            "piano": None,
        },
    )


@transaction.atomic
def modifica_piano(request, pk: int):
    piano = get_object_or_404(PianoAccantonamento, pk=pk)
    if request.method == "POST":
        form = PianoAccantonamentoForm(request.POST, instance=piano)
        if form.is_valid():
            form.save()
            messages.success(request, "Piano aggiornato.")
            return redirect("fondo_piano_dettaglio", pk=piano.pk)
    else:
        form = PianoAccantonamentoForm(instance=piano)
    return render(
        request,
        "fondo_accantonamento/piano_form.html",
        {
            "form": form,
            "titolo": "Modifica piano",
            "piano": piano,
        },
    )


@transaction.atomic
def elimina_piano(request, pk: int):
    piano = get_object_or_404(PianoAccantonamento, pk=pk)
    if request.method == "POST":
        piano.delete()
        messages.success(request, "Piano eliminato.")
        return redirect("fondo_piano_lista")
    return render(
        request,
        "fondo_accantonamento/piano_confirm_delete.html",
        {"piano": piano},
    )


@transaction.atomic
def aggiungi_versamento(request, piano_pk: int):
    piano = get_object_or_404(PianoAccantonamento, pk=piano_pk)
    popup = _is_popup_request(request)
    if request.method == "POST":
        form = VersamentoFondoForm(request.POST)
        if form.is_valid():
            m: MovimentoFondo = form.save(commit=False)
            m.piano = piano
            m.tipo = TipoMovimentoFondo.VERSAMENTO
            m.save()
            messages.success(request, "Versamento registrato.")
            if popup:
                return _popup_close(request, "Versamento registrato.")
            return redirect("fondo_piano_dettaglio", pk=piano.pk)
    else:
        form = VersamentoFondoForm()
    return render(
        request,
        "fondo_accantonamento/movimento_form.html",
        {
            "form": form,
            "piano": piano,
            "titolo": "Registra versamento",
            "tipo_label": "Versamento",
            "popup": popup,
        },
    )


@transaction.atomic
def aggiungi_prelievo(request, piano_pk: int):
    piano = get_object_or_404(PianoAccantonamento, pk=piano_pk)
    popup = _is_popup_request(request)
    if request.method == "POST":
        form = PrelievoFondoForm(request.POST)
        if form.is_valid():
            if form.cleaned_data["importo"] > piano.saldo_disponibile:
                form.add_error(
                    "importo",
                    "L'importo supera il saldo disponibile del piano.",
                )
            else:
                m: MovimentoFondo = form.save(commit=False)
                m.piano = piano
                m.tipo = TipoMovimentoFondo.PRELIEVO
                m.save()
                messages.success(request, "Prelievo registrato.")
                if popup:
                    return _popup_close(request, "Prelievo registrato.")
                return redirect("fondo_piano_dettaglio", pk=piano.pk)
    else:
        form = PrelievoFondoForm()
    return render(
        request,
        "fondo_accantonamento/movimento_form.html",
        {
            "form": form,
            "piano": piano,
            "titolo": "Registra prelievo",
            "tipo_label": "Prelievo",
            "saldo": piano.saldo_disponibile,
            "popup": popup,
        },
    )


@transaction.atomic
def genera_scadenze(request, piano_pk: int):
    if request.method != "POST":
        return redirect("fondo_piano_dettaglio", pk=piano_pk)
    piano = get_object_or_404(PianoAccantonamento, pk=piano_pk)
    n, msg = genera_scadenze_periodiche(piano, rigenera_pianificati=True)
    if n or "generate" in msg.lower():
        messages.success(request, msg)
    else:
        messages.info(request, msg)
    return redirect("fondo_piano_dettaglio", pk=piano.pk)


@transaction.atomic
def soddisfa_scadenza(request, scadenza_pk: int):
    if request.method != "POST":
        return redirect("fondo_piano_lista")
    sc = get_object_or_404(ScadenzaVersamento, pk=scadenza_pk)
    piano_pk = sc.piano_id
    try:
        soddisfa_scadenza_con_versamento(
            sc,
            data_effettiva=timezone.localdate(),
        )
        messages.success(
            request,
            "Versamento registrato e scadenza segnata come soddisfatta.",
        )
    except ValueError as exc:
        messages.error(request, str(exc))
    return redirect("fondo_piano_dettaglio", pk=piano_pk)
