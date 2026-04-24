"""
Sincronizzazione movimenti di accantonamento da percentuale sulle rate (economia).
"""

from __future__ import annotations

import logging
from decimal import Decimal, ROUND_HALF_UP

from django.db.models import Q
from django.utils import timezone

from ..models import MovimentoFondo, PianoAccantonamento, TipoModalitaPiano, TipoMovimentoFondo

logger = logging.getLogger(__name__)

NOTE_AUTO = "Accantonamento automatico da rata (percentuale su importo pagato)."


def _piani_con_percentuale(anno_scolastico_id: int):
    return PianoAccantonamento.objects.filter(
        Q(anno_scolastico_id=anno_scolastico_id) | Q(sempre_attivo=True),
        attivo=True,
        modalita__in=(
            TipoModalitaPiano.PERCENTUALE_RETTE,
            TipoModalitaPiano.MISTO,
        ),
        percentuale_su_rette__isnull=False,
    ).order_by("nome", "id")


def _importo_target_su_pagato(importo_pagato: Decimal, percent: Decimal) -> Decimal:
    base = importo_pagato or Decimal("0")
    raw = (base * (percent or Decimal("0"))) / Decimal("100")
    return raw.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def sincronizza_versamento_fondo_da_rata(rata) -> None:
    """
    Crea, aggiorna o rimuove un versamento collegato alla rata in base
    a ``importo_pagato`` e al piano attivo con percentuale sull'anno.
    Un solo movimento per (piano, rata) per i versamenti da percentuale.
    Le rate di preiscrizione sono ignorate.
    """
    if getattr(rata, "is_preiscrizione", False):
        return

    if not rata.iscrizione_id or not rata.iscrizione.anno_scolastico_id:
        return

    anno_id = rata.iscrizione.anno_scolastico_id
    piani = list(_piani_con_percentuale(anno_id))
    if not piani:
        return
    if len(piani) > 1:
        logger.warning(
            "Fondo accantonamento: piu' piani con percentuale (anno / sempre attivo) per l'anno %s: "
            "si applica l'ordine per nome, solo il primo sara' usato per la sincronizzazione.",
            anno_id,
        )
        piani = [piani[0]]

    importo_pagato = rata.importo_pagato or Decimal("0")
    data_mov = rata.data_pagamento or timezone.localdate()

    for piano in piani:
        percent = piano.percentuale_su_rette
        if percent is None:
            continue
        target = _importo_target_su_pagato(importo_pagato, percent)
        managed = MovimentoFondo.objects.filter(
            piano=piano,
            rata_iscrizione_id=rata.pk,
            tipo=TipoMovimentoFondo.VERSAMENTO,
        ).order_by("id")
        if target <= 0:
            n, _ = managed.delete()
            if n:
                logger.debug(
                    "Fondo: rimossi %s movimenti da-reatta per rata %s, piano %s",
                    n,
                    rata.pk,
                    piano.pk,
                )
            continue

        pks = list(managed.values_list("pk", flat=True))
        if len(pks) > 1:
            MovimentoFondo.objects.filter(pk__in=pks[1:]).delete()

        mov = MovimentoFondo.objects.filter(
            piano=piano,
            rata_iscrizione_id=rata.pk,
            tipo=TipoMovimentoFondo.VERSAMENTO,
        ).order_by("id").first()
        if mov is None:
            MovimentoFondo.objects.create(
                piano=piano,
                tipo=TipoMovimentoFondo.VERSAMENTO,
                data=data_mov,
                importo=target,
                note=NOTE_AUTO,
                rata_iscrizione_id=rata.pk,
            )
        else:
            to_update: list[str] = []
            if mov.importo != target:
                mov.importo = target
                to_update.append("importo")
            if mov.data != data_mov:
                mov.data = data_mov
                to_update.append("data")
            if mov.note != NOTE_AUTO:
                mov.note = NOTE_AUTO
                to_update.append("note")
            if to_update:
                mov.save(update_fields=to_update)
