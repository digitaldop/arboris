"""
Ponte verso le agevolazioni economiche: quale piano accantonamento copre lo
sconto (uscita SCONTO_RETTA) e su quante prime mensilita' ripartirlo.
"""

from __future__ import annotations

from django.db import models


class RegolaScontoAgevolazione(models.Model):
    """
    Ogni :class:`economia.Agevolazione` puo' avere al piu' una regola: lo sconto
    e' un'uscita dal fondo e viene ripartita sulle rate mensili selezionate.
    Il piano di accantonamento deve riferirsi allo stesso anno scolastico
    dell'iscrizione, altrimenti la sincronizzazione non genera movimenti.
    """

    agevolazione = models.OneToOneField(
        "economia.Agevolazione",
        on_delete=models.CASCADE,
        related_name="regola_sconto_fondo",
    )
    piano = models.ForeignKey(
        "PianoAccantonamento",
        on_delete=models.CASCADE,
        related_name="regole_sconto_agevolazione",
    )
    numero_mensilita = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Prime N rate mensili; lasciare vuoto per usare tutte le mensilita' del piano rate.",
    )
    attiva = models.BooleanField(default=True)

    class Meta:
        db_table = "fondo_acc_regola_sconto_agev"
        verbose_name = "Regola sconto fondo (agevolazione)"
        verbose_name_plural = "Regole sconto fondo (agevolazioni)"

    def __str__(self) -> str:
        return f"{self.agevolazione} -> {self.piano}"
