from __future__ import annotations

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q, Sum

from scuola.models import AnnoScolastico


class TipoModalitaPiano(models.TextChoices):
    """
    I versamenti e prelievi manuali restano sempre disponibili in ogni modalità.
    Le opzioni attivano regole aggiuntive (percentuale e/o scadenze periodiche).
    """

    SOLO_MANUALE = "solo_manuale", "Solo versamenti e prelievi manuali"
    PERCENTUALE_RETTE = "percentuale_rette", "Percentuale sulle rette"
    VERSAMENTI_PERIODICI = "versamenti_periodici", "Versamenti periodici (date calcolate)"
    MISTO = "misto", "Percentuale sulle rette e Versamenti periodici"


class TipoDeposito(models.TextChoices):
    CONTO_CORRENTE = "conto", "Conto corrente"
    CONTANTI = "contanti", "Contanti"
    PAYPAL = "paypal", "PayPal o portafoglio elettronico"
    ALTRO = "altro", "Altro"


class PeriodicitaVersamento(models.TextChoices):
    MENSILE = "mensile", "Mensile"
    BIMESTRALE = "bimestrale", "Bimestrale"
    TRIMESTRALE = "trimestrale", "Trimestrale"
    SEMESTRALE = "semestrale", "Semestrale"
    ANNUALE = "annuale", "Annuale"


class StatoScadenza(models.TextChoices):
    PIANIFICATO = "pianificato", "Pianificato"
    SODDISFATTO = "soddisfatto", "Soddisfatto (versamento registrato)"
    ANNULLATO = "annullato", "Annullato"


class TipoMovimentoFondo(models.TextChoices):
    VERSAMENTO = "versamento", "Versamento in entrata"
    PRELIEVO = "prelievo", "Prelievo o utilizzo in uscita"
    SCONTO_RETTA = "sconto_retta", "Sconto accantonamento su retta (economia)"


class PianoAccantonamento(models.Model):
    """
    Ogni piano e' o legato a un :class:`AnnoScolastico`, o marcato *sempre attivo* e
    valido per ogni iscrizione/anno a livello di regole automatiche.
    """
    sempre_attivo = models.BooleanField(
        default=False,
        help_text="Se attivo, il piano non e' vincolato a un singolo anno scolastico (es. conto comune a tutti gli anni).",
    )
    anno_scolastico = models.ForeignKey(
        AnnoScolastico,
        on_delete=models.PROTECT,
        related_name="piani_fondo_accantonamento",
        blank=True,
        null=True,
    )
    nome = models.CharField(max_length=200)
    descrizione = models.TextField(blank=True)
    attivo = models.BooleanField(default=True)
    modalita = models.CharField(
        max_length=40,
        choices=TipoModalitaPiano.choices,
        default=TipoModalitaPiano.SOLO_MANUALE,
    )
    # Percentuale sulle rette (es. 5 = 5%)
    percentuale_su_rette = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        blank=True,
        null=True,
        validators=[MinValueValidator(Decimal("0")), MaxValueValidator(Decimal("100"))],
        help_text="Usata se la modalita' include percentuale sulle rette. Conviene un solo piano attivo con percentuale per ogni contesto (anno o piano sempre attivo), altrimenti ne viene usato uno solo (il primo per nome).",
    )
    periodicita = models.CharField(
        max_length=20,
        choices=PeriodicitaVersamento.choices,
        blank=True,
    )
    data_primo_versamento = models.DateField(
        blank=True,
        null=True,
        help_text="Data del primo versamento periodico atteso (base per le scadenze).",
    )
    importo_versamento_periodico = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        blank=True,
        null=True,
    )
    tipo_deposito = models.CharField(
        max_length=20,
        choices=TipoDeposito.choices,
        default=TipoDeposito.ALTRO,
    )
    descrizione_deposito = models.CharField(
        max_length=255,
        blank=True,
        help_text="Es. Nome banca, cassa, piattaforma.",
    )
    coordinate_riferimento = models.TextField(
        blank=True,
        help_text="IBAN, riferimenti o note per l'accesso. Trattare come informazioni sensibili.",
    )
    data_creazione = models.DateTimeField(auto_now_add=True)
    data_aggiornamento = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "fondo_accantonamento_piano"
        ordering = ["-sempre_attivo", "-anno_scolastico__data_inizio", "nome"]
        verbose_name = "Piano di accantonamento"
        verbose_name_plural = "Piani di accantonamento"
        constraints = [
            models.UniqueConstraint(
                fields=["anno_scolastico", "nome"],
                condition=Q(anno_scolastico__isnull=False),
                name="fondo_acc_piano_unico_anno_nome",
            ),
            models.UniqueConstraint(
                fields=["nome"],
                condition=Q(sempre_attivo=True),
                name="fondo_acc_piano_unico_nome_sempre_attivo",
            ),
        ]

    def __str__(self) -> str:
        if self.sempre_attivo:
            return f"{self.nome} (sempre attivo)"
        if self.anno_scolastico_id:
            return f"{self.nome} ({self.anno_scolastico})"
        return self.nome

    def clean(self) -> None:
        super().clean()
        if self.sempre_attivo:
            if self.anno_scolastico_id:
                raise ValidationError(
                    {
                        "anno_scolastico": "Per un piano «sempre attivo» l'anno scolastico va lasciato vuoto.",
                    }
                )
        elif not self.anno_scolastico_id:
            raise ValidationError(
                {
                    "anno_scolastico": "Seleziona l'anno scolastico oppure abilita l'opzione Sempre attivo.",
                }
            )

    def totale_versamenti(self) -> Decimal:
        return (
            self.movimenti.filter(tipo=TipoMovimentoFondo.VERSAMENTO).aggregate(
                t=Sum("importo")
            )["t"]
            or Decimal("0")
        )

    def totale_uscite(self) -> Decimal:
        return (
            self.movimenti.filter(
                tipo__in=(TipoMovimentoFondo.PRELIEVO, TipoMovimentoFondo.SCONTO_RETTA)
            ).aggregate(t=Sum("importo"))["t"]
            or Decimal("0")
        )

    @property
    def saldo_disponibile(self) -> Decimal:
        return self.totale_versamenti() - self.totale_uscite()


class ScadenzaVersamento(models.Model):
    piano = models.ForeignKey(
        PianoAccantonamento,
        on_delete=models.CASCADE,
        related_name="scadenze",
    )
    data_scadenza = models.DateField()
    importo_previsto = models.DecimalField(max_digits=10, decimal_places=2)
    stato = models.CharField(
        max_length=20,
        choices=StatoScadenza.choices,
        default=StatoScadenza.PIANIFICATO,
    )
    movimento_versamento = models.ForeignKey(
        "MovimentoFondo",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="scadenze_soddisfatte",
    )
    note = models.TextField(blank=True)

    class Meta:
        db_table = "fondo_accantonamento_scadenza"
        ordering = ["data_scadenza", "id"]
        verbose_name = "Scadenza versamento"
        verbose_name_plural = "Scadenze versamento"
        constraints = [
            models.UniqueConstraint(
                fields=["piano", "data_scadenza"],
                name="fondo_acc_scad_unica_data_per_piano",
            )
        ]
        indexes = [
            models.Index(fields=["piano", "data_scadenza"], name="fondo_acc_scad_piano_data"),
        ]

    def __str__(self) -> str:
        return f"{self.piano} — {self.data_scadenza}"


class MovimentoFondo(models.Model):
    piano = models.ForeignKey(
        PianoAccantonamento,
        on_delete=models.CASCADE,
        related_name="movimenti",
    )
    tipo = models.CharField(
        max_length=20,
        choices=TipoMovimentoFondo.choices,
    )
    data = models.DateField()
    importo = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    note = models.TextField(blank=True)
    richiedente = models.CharField(
        max_length=200,
        blank=True,
        help_text="Per prelievi: chi ha prelevato o approvato.",
    )
    motivo = models.TextField(
        blank=True,
        help_text="Per prelievi: motivazione.",
    )
    rata_iscrizione = models.ForeignKey(
        "economia.RataIscrizione",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="movimenti_fondo_accantonamento",
    )
    scadenza_versamento = models.ForeignKey(
        ScadenzaVersamento,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="movimenti_collegati",
    )
    data_creazione = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "fondo_accantonamento_movimento"
        ordering = ["-data", "-id"]
        verbose_name = "Movimento fondo"
        verbose_name_plural = "Movimenti fondo"
        indexes = [
            models.Index(fields=["piano", "data"], name="fondo_acc_mov_piano_data"),
        ]

    def __str__(self) -> str:
        return f"{self.get_tipo_display()} {self.importo} — {self.data}"


# Fix forward ref: ScadenzaVersamento.movimento_versamento -> MovimentoFondo; already string ok
