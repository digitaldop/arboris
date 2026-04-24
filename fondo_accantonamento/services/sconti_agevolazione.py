"""
Movimenti SCONTO_RETTA: uscite dal fondo collegate alle agev. economiche
(economia) tramite :class:`RegolaScontoAgevolazione`.
"""

from __future__ import annotations

import logging
from decimal import Decimal, ROUND_DOWN, ROUND_HALF_UP

from django.utils import timezone

from economia.models import Iscrizione, RataIscrizione

from ..models import (
    MovimentoFondo,
    RegolaScontoAgevolazione,
    TipoMovimentoFondo,
)

logger = logging.getLogger(__name__)

NOTE_SCONTO_AUTO = "Sconto a carico del fondo (agevolazione iscrizione)."


def _split_importo_su_mensilita(tot: Decimal, n: int) -> list[Decimal]:
    if n <= 0:
        return []
    t = (tot or Decimal("0")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if t <= 0:
        return [Decimal("0.00")] * n
    base = (t / Decimal(n)).quantize(Decimal("0.01"), rounding=ROUND_DOWN)
    out = [base] * n
    usato = base * n
    resto = (t - usato).quantize(Decimal("0.01"))
    if resto > 0:
        out[n - 1] = (out[n - 1] + resto).quantize(Decimal("0.01"))
    return out


def _cancella_sconti_automatici_iscrizione(iscrizione: Iscrizione) -> int:
    """
    Rimuove tutti i SCONTO_RETTA generati da questa logica per l'iscrizione.
    """
    n, _ = (
        MovimentoFondo.objects.filter(
            rata_iscrizione__iscrizione_id=iscrizione.pk,
            tipo=TipoMovimentoFondo.SCONTO_RETTA,
            note=NOTE_SCONTO_AUTO,
        ).delete()
    )
    return n


def sincronizza_sconti_fondo_da_iscrizione(iscrizione: Iscrizione) -> None:
    if not iscrizione.pk:
        return

    if not iscrizione.agevolazione_id:
        _cancella_sconti_automatici_iscrizione(iscrizione)
        return

    regola: RegolaScontoAgevolazione | None = (
        RegolaScontoAgevolazione.objects.filter(
            agevolazione_id=iscrizione.agevolazione_id,
            attiva=True,
        )
        .select_related("piano", "piano__anno_scolastico")
        .first()
    )

    if not regola:
        _cancella_sconti_automatici_iscrizione(iscrizione)
        return

    piano = regola.piano
    if not piano.attivo or (
        not piano.sempre_attivo
        and piano.anno_scolastico_id != iscrizione.anno_scolastico_id
    ):
        _cancella_sconti_automatici_iscrizione(iscrizione)
        return

    importo_agev = iscrizione.get_importo_agevolazione_applicata() or Decimal("0")
    if iscrizione.non_pagante or importo_agev <= 0:
        _rimuovi_sconti_su_piano_iscrizione(piano, iscrizione)
        return

    rate_qs = (
        RataIscrizione.objects.filter(
            iscrizione_id=iscrizione.pk,
            tipo_rata=RataIscrizione.TIPO_MENSILE,
        )
        .order_by("data_scadenza", "numero_rata", "id")
    )
    rate: list[RataIscrizione] = list(rate_qs)
    n_limit = regola.numero_mensilita
    if n_limit:
        rate = rate[: int(n_limit)]
    n = len(rate)
    if n == 0:
        _rimuovi_sconti_su_piano_iscrizione(piano, iscrizione)
        return

    tranches = _split_importo_su_mensilita(importo_agev, n)
    pks_toccati: set[int] = set()
    oggi = timezone.localdate()

    for rata, importo in zip(rate, tranches):
        pks_toccati.add(rata.pk)
        if importo <= 0:
            _elimina_sconto_rata(piano, rata.pk)
            continue
        data_s = rata.data_scadenza or oggi
        _upsert_sconto(
            piano=piano,
            rata=rata,
            importo=importo,
            data_mov=data_s,
        )

    _elimina_sconti_su_piano_iscrizione_extra(piano, iscrizione, pks_toccati)


def _rimuovi_sconti_su_piano_iscrizione(piano, iscrizione: Iscrizione) -> None:
    MovimentoFondo.objects.filter(
        piano=piano,
        tipo=TipoMovimentoFondo.SCONTO_RETTA,
        note=NOTE_SCONTO_AUTO,
        rata_iscrizione__iscrizione_id=iscrizione.pk,
    ).delete()


def _elimina_sconti_su_piano_iscrizione_extra(
    piano, iscrizione: Iscrizione, pks_ancora_validi: set[int]
) -> None:
    qs = MovimentoFondo.objects.filter(
        piano=piano,
        tipo=TipoMovimentoFondo.SCONTO_RETTA,
        note=NOTE_SCONTO_AUTO,
        rata_iscrizione__iscrizione_id=iscrizione.pk,
    )
    if pks_ancora_validi:
        qs = qs.exclude(rata_iscrizione_id__in=pks_ancora_validi)
    qs.delete()


def _elimina_sconto_rata(piano, rata_pk: int) -> None:
    MovimentoFondo.objects.filter(
        piano=piano,
        rata_iscrizione_id=rata_pk,
        tipo=TipoMovimentoFondo.SCONTO_RETTA,
        note=NOTE_SCONTO_AUTO,
    ).delete()


def _upsert_sconto(
    *, piano, rata: RataIscrizione, importo: Decimal, data_mov
) -> None:
    if (
        not MovimentoFondo.objects.filter(
            piano=piano,
            rata_iscrizione_id=rata.pk,
            tipo=TipoMovimentoFondo.SCONTO_RETTA,
            note=NOTE_SCONTO_AUTO,
        ).exists()
        and MovimentoFondo.objects.filter(
            piano=piano,
            rata_iscrizione_id=rata.pk,
            tipo=TipoMovimentoFondo.SCONTO_RETTA,
        ).exists()
    ):
        logger.warning(
            "Fondo: rata %s ha gia' uno sconto retta manuale, non inserire quello da agev.",
            rata.pk,
        )
        return

    mov = MovimentoFondo.objects.filter(
        piano=piano,
        rata_iscrizione_id=rata.pk,
        tipo=TipoMovimentoFondo.SCONTO_RETTA,
        note=NOTE_SCONTO_AUTO,
    ).first()

    if importo <= 0:
        if mov:
            mov.delete()
        return

    if mov is None:
        MovimentoFondo.objects.create(
            piano=piano,
            tipo=TipoMovimentoFondo.SCONTO_RETTA,
            data=data_mov,
            importo=importo,
            note=NOTE_SCONTO_AUTO,
            rata_iscrizione_id=rata.pk,
        )
    else:
        to_u: list[str] = []
        if mov.importo != importo:
            mov.importo = importo
            to_u.append("importo")
        if mov.data != data_mov:
            mov.data = data_mov
            to_u.append("data")
        if to_u:
            mov.save(update_fields=to_u)
