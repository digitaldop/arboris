from decimal import Decimal
import uuid
from decimal import Decimal

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Max, Sum
from django.utils import timezone


def next_order_value(model_cls):
    max_value = model_cls.objects.aggregate(max_ordine=Max("ordine"))["max_ordine"]
    return (max_value or 0) + 1


# =========================================================================
#  Categorie finanziarie
# =========================================================================


class TipoCategoriaFinanziaria(models.TextChoices):
    SPESA = "spesa", "Spesa"
    ENTRATA = "entrata", "Entrata"
    TRASFERIMENTO = "trasferimento", "Trasferimento"


class CategoriaFinanziaria(models.Model):
    """
    Categoria definita dall'utente per classificare movimenti bancari
    e voci manuali. Supporta una gerarchia a piu' livelli tramite `parent`
    per permettere rollup nei report (es. Utenze > Luce, Utenze > Gas).
    """

    nome = models.CharField(max_length=120)
    tipo = models.CharField(
        max_length=20,
        choices=TipoCategoriaFinanziaria.choices,
        default=TipoCategoriaFinanziaria.SPESA,
        help_text="Natura della categoria: spesa, entrata o trasferimento fra conti.",
    )
    parent = models.ForeignKey(
        "self",
        on_delete=models.PROTECT,
        related_name="figli",
        blank=True,
        null=True,
        help_text="Categoria padre, per creare una gerarchia (es. Utenze > Luce).",
    )
    colore = models.CharField(
        max_length=20,
        blank=True,
        help_text="Colore esadecimale usato nei report e nei grafici (es. #336699).",
    )
    icona = models.CharField(max_length=60, blank=True)
    attiva = models.BooleanField(default=True)
    ordine = models.IntegerField(blank=True, null=True)
    note = models.TextField(blank=True)
    data_creazione = models.DateTimeField(auto_now_add=True)
    data_aggiornamento = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "gestione_finanziaria_categoria"
        ordering = ["ordine", "nome"]
        verbose_name = "Categoria finanziaria"
        verbose_name_plural = "Categorie finanziarie"
        constraints = [
            models.UniqueConstraint(
                fields=["nome", "parent"],
                name="gestione_finanziaria_categoria_nome_parent_unique",
            ),
        ]

    def __str__(self):
        if self.parent_id:
            return f"{self.parent} / {self.nome}"
        return self.nome

    def clean(self):
        super().clean()
        if self.parent_id and self.parent_id == self.pk:
            raise ValidationError({"parent": "Una categoria non puo' essere figlia di se stessa."})

        parent = self.parent
        visited_ids = {self.pk} if self.pk else set()
        while parent is not None:
            if parent.pk in visited_ids:
                raise ValidationError({"parent": "La gerarchia delle categorie contiene un ciclo."})
            visited_ids.add(parent.pk)
            parent = parent.parent

        if self.pk and self.tipo != TipoCategoriaFinanziaria.SPESA:
            if self.fornitori.exists() or self.documenti_fornitori.exists():
                raise ValidationError(
                    {"tipo": "Una categoria collegata a fornitori o documenti fornitori deve restare di tipo spesa."}
                )

    def save(self, *args, **kwargs):
        if self.ordine is None:
            self.ordine = next_order_value(CategoriaFinanziaria)
        super().save(*args, **kwargs)

    @property
    def percorso_label(self):
        parti = [self.nome]
        parent = self.parent
        while parent is not None:
            parti.append(parent.nome)
            parent = parent.parent
        return " / ".join(reversed(parti))

    @property
    def descrizione(self):
        return self.note


# =========================================================================
#  Fornitori e documenti passivi
# =========================================================================


class TipoSoggettoFornitore(models.TextChoices):
    AZIENDA = "azienda", "Azienda"
    PROFESSIONISTA = "professionista", "Professionista"
    ASSOCIAZIONE = "associazione", "Associazione"
    PERSONA_FISICA = "persona_fisica", "Persona fisica"
    ALTRO = "altro", "Altro"


class Fornitore(models.Model):
    denominazione = models.CharField(max_length=220)
    tipo_soggetto = models.CharField(
        max_length=30,
        choices=TipoSoggettoFornitore.choices,
        default=TipoSoggettoFornitore.AZIENDA,
    )
    categoria_spesa = models.ForeignKey(
        CategoriaFinanziaria,
        on_delete=models.PROTECT,
        related_name="fornitori",
        blank=True,
        null=True,
        help_text="Categoria prevalente usata come default sui documenti del fornitore.",
    )
    codice_fiscale = models.CharField(max_length=16, blank=True)
    partita_iva = models.CharField(max_length=11, blank=True)
    indirizzo = models.CharField(max_length=255, blank=True)
    telefono = models.CharField(max_length=40, blank=True)
    email = models.EmailField(blank=True)
    pec = models.EmailField(blank=True)
    codice_sdi = models.CharField(max_length=7, blank=True)
    referente = models.CharField(max_length=160, blank=True)
    iban = models.CharField(max_length=34, blank=True)
    banca = models.CharField(max_length=160, blank=True)
    note = models.TextField(blank=True)
    attivo = models.BooleanField(default=True)
    data_creazione = models.DateTimeField(auto_now_add=True)
    data_aggiornamento = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "gestione_finanziaria_fornitore"
        ordering = ["denominazione"]
        verbose_name = "Fornitore"
        verbose_name_plural = "Fornitori"

    def __str__(self):
        return self.denominazione

    def clean(self):
        super().clean()
        if self.categoria_spesa_id and self.categoria_spesa.tipo != TipoCategoriaFinanziaria.SPESA:
            raise ValidationError({"categoria_spesa": "Seleziona una categoria di tipo spesa."})


class TipoVoceBudget(models.TextChoices):
    ENTRATA = "entrata", "Entrata"
    USCITA = "uscita", "Uscita"


class FrequenzaVoceBudget(models.TextChoices):
    UNA_TANTUM = "una_tantum", "Una tantum"
    MENSILE = "mensile", "Mensile"
    BIMESTRALE = "bimestrale", "Bimestrale"
    TRIMESTRALE = "trimestrale", "Trimestrale"
    SEMESTRALE = "semestrale", "Semestrale"
    ANNUALE = "annuale", "Annuale"


class VoceBudgetRicorrente(models.Model):
    """
    Voce previsionale usata dal modulo Budgeting per stimare entrate
    e uscite non ancora presenti come movimenti, rette o fatture.
    """

    nome = models.CharField(max_length=160)
    tipo = models.CharField(max_length=20, choices=TipoVoceBudget.choices, default=TipoVoceBudget.USCITA)
    categoria = models.ForeignKey(
        CategoriaFinanziaria,
        on_delete=models.PROTECT,
        related_name="voci_budget",
        blank=True,
        null=True,
    )
    fornitore = models.ForeignKey(
        Fornitore,
        on_delete=models.SET_NULL,
        related_name="voci_budget",
        blank=True,
        null=True,
    )
    importo = models.DecimalField(max_digits=12, decimal_places=2)
    frequenza = models.CharField(
        max_length=20,
        choices=FrequenzaVoceBudget.choices,
        default=FrequenzaVoceBudget.MENSILE,
    )
    data_inizio = models.DateField(db_index=True)
    data_fine = models.DateField(blank=True, null=True, db_index=True)
    giorno_previsto = models.PositiveSmallIntegerField(default=1)
    mese_previsto = models.PositiveSmallIntegerField(blank=True, null=True)
    attiva = models.BooleanField(default=True)
    note = models.TextField(blank=True)
    data_creazione = models.DateTimeField(auto_now_add=True)
    data_aggiornamento = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "gestione_finanziaria_voce_budget_ricorrente"
        ordering = ["tipo", "categoria__nome", "nome"]
        verbose_name = "Voce budget ricorrente"
        verbose_name_plural = "Voci budget ricorrenti"
        indexes = [
            models.Index(fields=["tipo", "attiva"], name="gf_budget_tipo_attiva_idx"),
            models.Index(fields=["data_inizio", "data_fine"], name="gf_budget_periodo_idx"),
        ]

    def __str__(self):
        return self.nome

    def clean(self):
        super().clean()
        if self.importo is not None and self.importo <= Decimal("0.00"):
            raise ValidationError({"importo": "L'importo deve essere maggiore di zero."})
        if self.giorno_previsto and not 1 <= self.giorno_previsto <= 31:
            raise ValidationError({"giorno_previsto": "Il giorno previsto deve essere compreso tra 1 e 31."})
        if self.mese_previsto and not 1 <= self.mese_previsto <= 12:
            raise ValidationError({"mese_previsto": "Il mese previsto deve essere compreso tra 1 e 12."})
        if self.data_fine and self.data_fine < self.data_inizio:
            raise ValidationError({"data_fine": "La data di fine non puo essere precedente alla data di inizio."})
        if self.categoria_id:
            expected_tipo = (
                TipoCategoriaFinanziaria.ENTRATA
                if self.tipo == TipoVoceBudget.ENTRATA
                else TipoCategoriaFinanziaria.SPESA
            )
            if self.categoria.tipo != expected_tipo:
                raise ValidationError({"categoria": "La categoria deve essere coerente con il tipo della voce."})


class TipoDocumentoFornitore(models.TextChoices):
    FATTURA = "fattura", "Fattura"
    PROFORMA = "proforma", "Proforma"
    PARCELLA = "parcella", "Parcella"
    RICEVUTA = "ricevuta", "Ricevuta"
    NOTA_CREDITO = "nota_credito", "Nota di credito"
    ALTRO = "altro", "Altro"


class StatoDocumentoFornitore(models.TextChoices):
    DA_PAGARE = "da_pagare", "Da pagare"
    PARZIALMENTE_PAGATO = "parzialmente_pagato", "Parzialmente pagato"
    PAGATO = "pagato", "Pagato"
    ANNULLATO = "annullato", "Annullato"


class OrigineDocumentoFornitore(models.TextChoices):
    MANUALE = "manuale", "Inserimento manuale"
    FATTURE_IN_CLOUD = "fatture_in_cloud", "Fatture in Cloud"


def documento_fornitore_upload_to(_instance, filename):
    return f"documenti_fornitori/{timezone.localdate():%Y/%m}/{filename}"


class DocumentoFornitore(models.Model):
    fornitore = models.ForeignKey(
        Fornitore,
        on_delete=models.PROTECT,
        related_name="documenti",
    )
    categoria_spesa = models.ForeignKey(
        CategoriaFinanziaria,
        on_delete=models.PROTECT,
        related_name="documenti_fornitori",
        blank=True,
        null=True,
    )
    tipo_documento = models.CharField(
        max_length=30,
        choices=TipoDocumentoFornitore.choices,
        default=TipoDocumentoFornitore.FATTURA,
    )
    numero_documento = models.CharField(max_length=80)
    data_documento = models.DateField(db_index=True)
    data_ricezione = models.DateField(blank=True, null=True)
    anno_competenza = models.PositiveIntegerField(blank=True, null=True)
    mese_competenza = models.PositiveSmallIntegerField(blank=True, null=True)
    descrizione = models.CharField(max_length=255, blank=True)
    imponibile = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    aliquota_iva = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("22.00"))
    iva = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    totale = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    stato = models.CharField(
        max_length=30,
        choices=StatoDocumentoFornitore.choices,
        default=StatoDocumentoFornitore.DA_PAGARE,
    )
    allegato = models.FileField(
        upload_to=documento_fornitore_upload_to,
        blank=True,
    )
    note = models.TextField(blank=True)
    origine = models.CharField(
        max_length=30,
        choices=OrigineDocumentoFornitore.choices,
        default=OrigineDocumentoFornitore.MANUALE,
        db_index=True,
    )
    external_source = models.CharField(max_length=60, blank=True, db_index=True)
    external_id = models.CharField(max_length=120, blank=True, db_index=True)
    external_type = models.CharField(max_length=60, blank=True)
    external_url = models.URLField(max_length=1000, blank=True)
    external_payload = models.JSONField(default=dict, blank=True)
    importato_at = models.DateTimeField(blank=True, null=True)
    external_updated_at = models.DateTimeField(blank=True, null=True)
    data_creazione = models.DateTimeField(auto_now_add=True)
    data_aggiornamento = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "gestione_finanziaria_documento_fornitore"
        ordering = ["-data_documento", "-id"]
        verbose_name = "Documento fornitore"
        verbose_name_plural = "Documenti fornitori"
        indexes = [
            models.Index(fields=["fornitore", "data_documento"], name="gf_doc_forn_data_idx"),
            models.Index(fields=["categoria_spesa", "data_documento"], name="gf_doc_catsp_data_idx"),
            models.Index(fields=["stato"], name="gf_doc_forn_stato_idx"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["fornitore", "tipo_documento", "numero_documento", "data_documento"],
                name="gf_doc_forn_unique_numero_data",
            ),
            models.UniqueConstraint(
                fields=["external_source", "external_id"],
                condition=~models.Q(external_source="") & ~models.Q(external_id=""),
                name="gf_doc_forn_unique_external",
            ),
        ]

    def __str__(self):
        return f"{self.get_tipo_documento_display()} {self.numero_documento} - {self.fornitore}"

    @property
    def categoria_spesa_effettiva(self):
        return self.categoria_spesa or getattr(self.fornitore, "categoria_spesa", None)

    @property
    def data_ricezione_effettiva(self):
        if self.data_ricezione:
            return self.data_ricezione
        if self.importato_at:
            return timezone.localtime(self.importato_at).date()
        return None

    @property
    def mese_competenza_nome(self):
        mesi = {
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
        return mesi.get(self.mese_competenza, "")

    def clean(self):
        super().clean()
        if self.mese_competenza is not None and not 1 <= self.mese_competenza <= 12:
            raise ValidationError({"mese_competenza": "Il mese di competenza deve essere compreso tra 1 e 12."})
        if self.categoria_spesa_id and self.categoria_spesa.tipo != TipoCategoriaFinanziaria.SPESA:
            raise ValidationError({"categoria_spesa": "Seleziona una categoria di tipo spesa."})

    def save(self, *args, **kwargs):
        if not self.categoria_spesa_id and self.fornitore_id:
            self.categoria_spesa = self.fornitore.categoria_spesa
        if not self.anno_competenza and self.data_documento:
            self.anno_competenza = self.data_documento.year
        if not self.mese_competenza and self.data_documento:
            self.mese_competenza = self.data_documento.month
        super().save(*args, **kwargs)

    @property
    def importo_pagato(self):
        totale = self.scadenze.aggregate(totale=Sum("importo_pagato"))["totale"]
        return totale or Decimal("0.00")

    @property
    def residuo_da_pagare(self):
        residuo = (self.totale or Decimal("0.00")) - self.importo_pagato
        return max(residuo, Decimal("0.00"))


class StatoScadenzaFornitore(models.TextChoices):
    PREVISTA = "prevista", "Prevista"
    SCADUTA = "scaduta", "Scaduta"
    PARZIALMENTE_PAGATA = "parzialmente_pagata", "Parzialmente pagata"
    PAGATA = "pagata", "Pagata"
    ANNULLATA = "annullata", "Annullata"


class ScadenzaPagamentoFornitore(models.Model):
    documento = models.ForeignKey(
        DocumentoFornitore,
        on_delete=models.CASCADE,
        related_name="scadenze",
    )
    data_scadenza = models.DateField(db_index=True)
    importo_previsto = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    importo_pagato = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    data_pagamento = models.DateField(blank=True, null=True)
    stato = models.CharField(
        max_length=30,
        choices=StatoScadenzaFornitore.choices,
        default=StatoScadenzaFornitore.PREVISTA,
    )
    conto_bancario = models.ForeignKey(
        "ContoBancario",
        on_delete=models.SET_NULL,
        related_name="scadenze_fornitori",
        blank=True,
        null=True,
    )
    movimento_finanziario = models.ForeignKey(
        "MovimentoFinanziario",
        on_delete=models.SET_NULL,
        related_name="scadenze_fornitori",
        blank=True,
        null=True,
    )
    note = models.TextField(blank=True)
    data_creazione = models.DateTimeField(auto_now_add=True)
    data_aggiornamento = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "gestione_finanziaria_scadenza_fornitore"
        ordering = ["data_scadenza", "id"]
        verbose_name = "Scadenza pagamento fornitore"
        verbose_name_plural = "Scadenze pagamento fornitori"
        indexes = [
            models.Index(fields=["data_scadenza", "stato"], name="gf_scad_forn_data_stato_idx"),
            models.Index(fields=["documento", "data_scadenza"], name="gf_scad_doc_data_idx"),
        ]

    def __str__(self):
        return f"{self.documento} - {self.data_scadenza:%d/%m/%Y}"

    @property
    def importo_residuo(self):
        residuo = (self.importo_previsto or Decimal("0.00")) - (self.importo_pagato or Decimal("0.00"))
        return max(residuo, Decimal("0.00"))

    @property
    def pagamento_parziale(self):
        return (self.importo_pagato or Decimal("0.00")) > Decimal("0.00") and self.importo_residuo > Decimal("0.00")

    def calcola_stato_automatico(self):
        if self.stato == StatoScadenzaFornitore.ANNULLATA:
            return self.stato

        previsto = self.importo_previsto or Decimal("0.00")
        pagato = self.importo_pagato or Decimal("0.00")
        if previsto > Decimal("0.00") and pagato >= previsto:
            return StatoScadenzaFornitore.PAGATA
        if pagato > Decimal("0.00"):
            return StatoScadenzaFornitore.PARZIALMENTE_PAGATA
        if self.data_scadenza and self.data_scadenza < timezone.localdate():
            return StatoScadenzaFornitore.SCADUTA
        return StatoScadenzaFornitore.PREVISTA

    @property
    def e_scaduta(self):
        return (
            self.stato in {StatoScadenzaFornitore.PREVISTA, StatoScadenzaFornitore.PARZIALMENTE_PAGATA}
            and self.data_scadenza
            and self.data_scadenza < timezone.localdate()
        )

    def save(self, *args, **kwargs):
        if not getattr(self, "_preserve_manual_stato", False):
            self.stato = self.calcola_stato_automatico()
        super().save(*args, **kwargs)


class MetodoPagamentoFornitore(models.TextChoices):
    BANCA = "banca", "Movimento bancario"
    MANUALE = "manuale", "Registrazione manuale"
    CONTANTI = "contanti", "Contanti"
    CARTA = "carta", "Carta"
    ALTRO = "altro", "Altro"


class PagamentoFornitore(models.Model):
    scadenza = models.ForeignKey(
        ScadenzaPagamentoFornitore,
        on_delete=models.CASCADE,
        related_name="pagamenti",
    )
    movimento_finanziario = models.ForeignKey(
        "MovimentoFinanziario",
        on_delete=models.SET_NULL,
        related_name="pagamenti_fornitori",
        blank=True,
        null=True,
    )
    data_pagamento = models.DateField(db_index=True)
    importo = models.DecimalField(max_digits=12, decimal_places=2)
    metodo = models.CharField(
        max_length=20,
        choices=MetodoPagamentoFornitore.choices,
        default=MetodoPagamentoFornitore.MANUALE,
    )
    conto_bancario = models.ForeignKey(
        "ContoBancario",
        on_delete=models.SET_NULL,
        related_name="pagamenti_fornitori",
        blank=True,
        null=True,
    )
    note = models.TextField(blank=True)
    creato_da = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="pagamenti_fornitori_creati",
        blank=True,
        null=True,
    )
    data_creazione = models.DateTimeField(auto_now_add=True)
    data_aggiornamento = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "gestione_finanziaria_pagamento_fornitore"
        ordering = ["-data_pagamento", "-id"]
        verbose_name = "Pagamento fornitore"
        verbose_name_plural = "Pagamenti fornitori"
        constraints = [
            models.CheckConstraint(
                check=models.Q(importo__gt=0),
                name="gf_pag_forn_importo_pos",
            ),
            models.UniqueConstraint(
                fields=["scadenza", "movimento_finanziario"],
                condition=models.Q(movimento_finanziario__isnull=False),
                name="gf_pag_forn_unique_scad_mov",
            ),
        ]
        indexes = [
            models.Index(fields=["scadenza", "data_pagamento"], name="gf_pag_forn_scad_data_idx"),
            models.Index(fields=["movimento_finanziario"], name="gf_pag_forn_mov_idx"),
        ]

    def __str__(self):
        return f"{self.scadenza} - {self.importo}"


class TipoSpesaOperativa(models.TextChoices):
    MANUALE = "manuale", "Spesa manuale"
    CONTANTI = "contanti", "Contanti"
    BUSTA_PAGA = "busta_paga", "Busta paga"
    F24 = "f24", "F24 / contributi"
    RATA_PIANO = "rata_piano", "Rata piano"
    FINANZIAMENTO = "finanziamento", "Finanziamento"
    ALTRO = "altro", "Altro"


class TipoPianoRatealeSpesa(models.TextChoices):
    FINANZIAMENTO = "finanziamento", "Finanziamento"
    F24 = "f24", "F24 / contributi"
    FORNITORE = "fornitore", "Rateizzazione fornitore"
    ALTRO = "altro", "Altro piano rateale"


class PianoRatealeSpesa(models.Model):
    descrizione = models.CharField(max_length=180)
    tipo = models.CharField(
        max_length=30,
        choices=TipoPianoRatealeSpesa.choices,
        default=TipoPianoRatealeSpesa.FINANZIAMENTO,
    )
    categoria = models.ForeignKey(
        CategoriaFinanziaria,
        on_delete=models.PROTECT,
        related_name="piani_rateali_spesa",
        blank=True,
        null=True,
    )
    fornitore = models.ForeignKey(
        Fornitore,
        on_delete=models.SET_NULL,
        related_name="piani_rateali_spesa",
        blank=True,
        null=True,
    )
    importo_totale = models.DecimalField(max_digits=12, decimal_places=2)
    numero_rate = models.PositiveSmallIntegerField(default=1)
    frequenza_mesi = models.PositiveSmallIntegerField(default=1)
    data_prima_scadenza = models.DateField(db_index=True)
    giorno_scadenza = models.PositiveSmallIntegerField(
        blank=True,
        null=True,
        help_text="Giorno del mese da usare per le rate successive. Se vuoto usa il giorno della prima scadenza.",
    )
    attivo = models.BooleanField(default=True)
    note = models.TextField(blank=True)
    creato_da = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="piani_rateali_spesa_creati",
        blank=True,
        null=True,
    )
    data_creazione = models.DateTimeField(auto_now_add=True)
    data_aggiornamento = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "gestione_finanziaria_piano_rateale_spesa"
        ordering = ["data_prima_scadenza", "id"]
        verbose_name = "Piano rateale di spesa"
        verbose_name_plural = "Piani rateali di spesa"
        indexes = [
            models.Index(fields=["data_prima_scadenza", "attivo"], name="gf_piano_spesa_data_idx"),
            models.Index(fields=["categoria"], name="gf_piano_spesa_cat_idx"),
        ]
        constraints = [
            models.CheckConstraint(check=models.Q(importo_totale__gt=0), name="gf_piano_spesa_importo_pos"),
            models.CheckConstraint(check=models.Q(numero_rate__gt=0), name="gf_piano_spesa_rate_pos"),
            models.CheckConstraint(check=models.Q(frequenza_mesi__gt=0), name="gf_piano_spesa_freq_pos"),
        ]

    def __str__(self):
        return self.descrizione

    def clean(self):
        super().clean()
        if self.categoria_id and self.categoria.tipo != TipoCategoriaFinanziaria.SPESA:
            raise ValidationError({"categoria": "La categoria deve essere di tipo spesa."})
        if self.giorno_scadenza and not 1 <= self.giorno_scadenza <= 31:
            raise ValidationError({"giorno_scadenza": "Il giorno scadenza deve essere compreso tra 1 e 31."})


class SpesaOperativa(models.Model):
    piano_rateale = models.ForeignKey(
        PianoRatealeSpesa,
        on_delete=models.CASCADE,
        related_name="rate",
        blank=True,
        null=True,
    )
    numero_rata = models.PositiveSmallIntegerField(blank=True, null=True)
    totale_rate = models.PositiveSmallIntegerField(blank=True, null=True)
    tipo = models.CharField(
        max_length=30,
        choices=TipoSpesaOperativa.choices,
        default=TipoSpesaOperativa.MANUALE,
    )
    descrizione = models.CharField(max_length=220)
    categoria = models.ForeignKey(
        CategoriaFinanziaria,
        on_delete=models.PROTECT,
        related_name="spese_operative",
        blank=True,
        null=True,
    )
    fornitore = models.ForeignKey(
        Fornitore,
        on_delete=models.SET_NULL,
        related_name="spese_operative",
        blank=True,
        null=True,
    )
    dipendente = models.ForeignKey(
        "gestione_amministrativa.Dipendente",
        on_delete=models.SET_NULL,
        related_name="spese_operative",
        blank=True,
        null=True,
    )
    data_scadenza = models.DateField(db_index=True)
    importo_previsto = models.DecimalField(max_digits=12, decimal_places=2)
    importo_pagato = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    data_pagamento = models.DateField(blank=True, null=True)
    conto_bancario = models.ForeignKey(
        "ContoBancario",
        on_delete=models.SET_NULL,
        related_name="spese_operative",
        blank=True,
        null=True,
    )
    movimento_finanziario = models.ForeignKey(
        "MovimentoFinanziario",
        on_delete=models.SET_NULL,
        related_name="spese_operative",
        blank=True,
        null=True,
    )
    note = models.TextField(blank=True)
    creato_da = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="spese_operative_create",
        blank=True,
        null=True,
    )
    data_creazione = models.DateTimeField(auto_now_add=True)
    data_aggiornamento = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "gestione_finanziaria_spesa_operativa"
        ordering = ["data_scadenza", "id"]
        verbose_name = "Spesa operativa"
        verbose_name_plural = "Spese operative"
        indexes = [
            models.Index(fields=["data_scadenza", "tipo"], name="gf_spesa_op_data_tipo_idx"),
            models.Index(fields=["categoria", "data_scadenza"], name="gf_spesa_op_cat_data_idx"),
            models.Index(fields=["piano_rateale"], name="gf_spesa_op_piano_idx"),
        ]
        constraints = [
            models.CheckConstraint(check=models.Q(importo_previsto__gt=0), name="gf_spesa_op_previsto_pos"),
            models.CheckConstraint(check=models.Q(importo_pagato__gte=0), name="gf_spesa_op_pagato_gte0"),
        ]

    def __str__(self):
        return self.descrizione

    @property
    def soggetto_label(self):
        return self.fornitore or self.dipendente or ""

    @property
    def importo_residuo(self):
        residuo = (self.importo_previsto or Decimal("0.00")) - (self.importo_pagato or Decimal("0.00"))
        return max(residuo, Decimal("0.00"))

    @property
    def e_pagata(self):
        return self.importo_residuo <= Decimal("0.00")

    @property
    def pagamento_parziale(self):
        return (self.importo_pagato or Decimal("0.00")) > Decimal("0.00") and self.importo_residuo > Decimal("0.00")

    @property
    def e_scaduta(self):
        return self.importo_residuo > Decimal("0.00") and self.data_scadenza and self.data_scadenza < timezone.localdate()

    def clean(self):
        super().clean()
        if self.categoria_id and self.categoria.tipo != TipoCategoriaFinanziaria.SPESA:
            raise ValidationError({"categoria": "La categoria deve essere di tipo spesa."})
        if self.importo_pagato and self.importo_previsto and self.importo_pagato > self.importo_previsto:
            raise ValidationError({"importo_pagato": "L'importo pagato non puo superare l'importo previsto."})


# =========================================================================
#  Provider bancari e connessioni
# =========================================================================


class TipoProviderBancario(models.TextChoices):
    PSD2 = "psd2", "Aggregatore PSD2"
    IMPORT_FILE = "import_file", "Import estratto conto (file)"
    MANUALE = "manuale", "Inserimento manuale"


class ProviderBancario(models.Model):
    """
    Rappresenta un canale attraverso cui il software puo' ricevere dati
    bancari: un aggregatore PSD2 (es. GoCardless BAD, Fabrick, Tink),
    un importatore di file (CAMT/CSV) o la registrazione manuale.
    """

    nome = models.CharField(max_length=120, unique=True)
    tipo = models.CharField(
        max_length=20,
        choices=TipoProviderBancario.choices,
        default=TipoProviderBancario.PSD2,
    )
    configurazione = models.JSONField(
        default=dict,
        blank=True,
        help_text="Parametri tecnici di configurazione del provider (base URL, secret reference, ecc.).",
    )
    attivo = models.BooleanField(default=True)
    note = models.TextField(blank=True)
    data_creazione = models.DateTimeField(auto_now_add=True)
    data_aggiornamento = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "gestione_finanziaria_provider_bancario"
        ordering = ["nome"]
        verbose_name = "Provider bancario"
        verbose_name_plural = "Provider bancari"

    def __str__(self):
        return self.nome


class StatoConnessioneBancaria(models.TextChoices):
    ATTIVA = "attiva", "Attiva"
    SCADUTA = "scaduta", "Consenso scaduto"
    REVOCATA = "revocata", "Revocata dal titolare"
    ERRORE = "errore", "In errore"


class ConnessioneBancaria(models.Model):
    """
    Consenso/collegamento applicativo fra Arboris e una banca tramite
    un provider PSD2. Una connessione puo' esporre uno o piu' conti.
    """

    provider = models.ForeignKey(
        ProviderBancario,
        on_delete=models.PROTECT,
        related_name="connessioni",
    )
    etichetta = models.CharField(
        max_length=150,
        help_text="Etichetta descrittiva per riconoscere la connessione (es. 'Banca Sella - Conto operativo').",
    )
    stato = models.CharField(
        max_length=20,
        choices=StatoConnessioneBancaria.choices,
        default=StatoConnessioneBancaria.ATTIVA,
    )
    external_institution_id = models.CharField(
        max_length=512,
        blank=True,
        help_text="Id istituto lato provider (es. TrueLayer, o NomeASPSP|IT per Enable Banking).",
    )
    external_connection_id = models.CharField(max_length=120, blank=True)
    access_token_cifrato = models.TextField(
        blank=True,
        help_text="Token di accesso cifrato. Non mostrare mai in chiaro nelle interfacce.",
    )
    refresh_token_cifrato = models.TextField(blank=True)
    access_token_scadenza = models.DateTimeField(
        blank=True,
        null=True,
        help_text="Scadenza dell'access token a breve durata (es. OAuth2 TrueLayer: 1h).",
    )
    consenso_scadenza = models.DateTimeField(
        blank=True,
        null=True,
        help_text="Scadenza del consenso complessivo (es. 90 giorni PSD2).",
    )
    ultimo_refresh_at = models.DateTimeField(blank=True, null=True)
    ultimo_errore = models.TextField(blank=True)
    data_creazione = models.DateTimeField(auto_now_add=True)
    data_aggiornamento = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "gestione_finanziaria_connessione_bancaria"
        ordering = ["provider__nome", "etichetta"]
        verbose_name = "Connessione bancaria"
        verbose_name_plural = "Connessioni bancarie"

    def __str__(self):
        return f"{self.provider} - {self.etichetta}"


# =========================================================================
#  Conti bancari e saldi
# =========================================================================


class TipoContoFinanziario(models.TextChoices):
    CONTO_CORRENTE = "conto_corrente", "Conto corrente"
    CASSA_CONTANTI = "cassa_contanti", "Cassa contanti"
    CARTA_PREPAGATA = "carta_prepagata", "Carta prepagata"
    CARTA_CREDITO = "carta_credito", "Carta di credito"
    ALTRO = "altro", "Altro"


class ContoBancario(models.Model):
    """
    Conto corrente (reale o interno tipo 'cassa') monitorato dal software.
    Il saldo corrente viene tenuto denormalizzato qui per comodita' in UI,
    ma la storia dei saldi vive in `SaldoConto`.
    """

    nome_conto = models.CharField(
        max_length=150,
        help_text="Nome interno del conto, visibile nelle liste (es. 'Conto operativo BNL').",
    )
    tipo_conto = models.CharField(
        max_length=30,
        choices=TipoContoFinanziario.choices,
        default=TipoContoFinanziario.CONTO_CORRENTE,
        help_text="Distingue conti bancari reali, cassa contanti, carte o altri saldi interni.",
    )
    iban = models.CharField(max_length=34, blank=True)
    intestatario = models.CharField(max_length=200, blank=True)
    banca = models.CharField(max_length=150, blank=True)
    bic = models.CharField(max_length=15, blank=True)
    valuta = models.CharField(max_length=3, default="EUR")
    provider = models.ForeignKey(
        ProviderBancario,
        on_delete=models.PROTECT,
        related_name="conti",
        blank=True,
        null=True,
    )
    connessione = models.ForeignKey(
        ConnessioneBancaria,
        on_delete=models.SET_NULL,
        related_name="conti",
        blank=True,
        null=True,
        help_text="Solo per provider PSD2: riferimento alla connessione/consenso.",
    )
    external_account_id = models.CharField(max_length=120, blank=True)
    external_account_hash = models.CharField(
        max_length=512,
        blank=True,
        db_index=True,
        help_text=(
            "Identificativo stabile lato provider, se disponibile. Per Enable Banking "
            "corrisponde a identification_hash e aiuta a riconoscere lo stesso conto "
            "fra sessioni diverse."
        ),
    )
    external_account_type = models.CharField(
        max_length=40,
        blank=True,
        help_text="Tipo conto lato provider (es. Enable Banking cash_account_type: CACC, CARD, SVGS).",
    )
    external_account_product = models.CharField(
        max_length=200,
        blank=True,
        help_text="Prodotto/dettaglio conto restituito dal provider PSD2, se disponibile.",
    )
    attivo = models.BooleanField(default=True)
    saldo_corrente = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=Decimal("0"),
        help_text="Ultimo saldo contabile noto. Aggiornato dalle sincronizzazioni.",
    )
    saldo_corrente_aggiornato_al = models.DateTimeField(blank=True, null=True)
    data_ultima_sincronizzazione = models.DateTimeField(blank=True, null=True)
    note = models.TextField(blank=True)
    data_creazione = models.DateTimeField(auto_now_add=True)
    data_aggiornamento = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "gestione_finanziaria_conto_bancario"
        ordering = ["nome_conto"]
        verbose_name = "Conto bancario"
        verbose_name_plural = "Conti bancari"

    def __str__(self):
        return self.nome_conto


class FonteSaldo(models.TextChoices):
    PROVIDER = "provider", "Provider PSD2"
    IMPORT_FILE = "import_file", "Import file"
    MANUALE = "manuale", "Manuale"


class SaldoConto(models.Model):
    """
    Snapshot storico del saldo di un conto, usato per ricostruire
    l'andamento nel tempo e alimentare grafici e previsioni.
    """

    conto = models.ForeignKey(
        ContoBancario,
        on_delete=models.CASCADE,
        related_name="storico_saldi",
    )
    data_riferimento = models.DateTimeField(db_index=True)
    saldo_contabile = models.DecimalField(max_digits=14, decimal_places=2)
    saldo_disponibile = models.DecimalField(max_digits=14, decimal_places=2, blank=True, null=True)
    valuta = models.CharField(max_length=3, default="EUR")
    fonte = models.CharField(max_length=20, choices=FonteSaldo.choices, default=FonteSaldo.PROVIDER)
    note = models.TextField(blank=True)
    creato_da = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="saldi_conto_creati",
        blank=True,
        null=True,
    )
    aggiornato_da = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="saldi_conto_aggiornati",
        blank=True,
        null=True,
    )
    data_creazione = models.DateTimeField(auto_now_add=True)
    data_aggiornamento = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "gestione_finanziaria_saldo_conto"
        ordering = ["-data_riferimento", "-id"]
        verbose_name = "Saldo conto"
        verbose_name_plural = "Saldi conto"
        indexes = [
            models.Index(fields=["conto", "data_riferimento"], name="gf_saldo_conto_data_idx"),
        ]

    def __str__(self):
        return f"{self.conto} - {self.data_riferimento:%d/%m/%Y %H:%M}: {self.saldo_contabile}"


# =========================================================================
#  Regole di categorizzazione automatica
# =========================================================================


class CondizioneRegolaCategorizzazione(models.TextChoices):
    DESCRIZIONE_CONTIENE = "descrizione_contiene", "Descrizione contiene"
    CONTROPARTE_CONTIENE = "controparte_contiene", "Controparte contiene"
    IBAN_CONTROPARTE_UGUALE = "iban_controparte_uguale", "IBAN controparte uguale a"
    IMPORTO_RANGE = "importo_range", "Importo compreso fra"
    SEGNO = "segno", "Solo segno"


class SegnoMovimento(models.TextChoices):
    USCITA = "uscita", "Uscita (importo negativo)"
    ENTRATA = "entrata", "Entrata (importo positivo)"


class RegolaCategorizzazione(models.Model):
    """
    Regola che, in fase di import o sincronizzazione, prova ad assegnare
    automaticamente una categoria a un movimento. L'utente puo' sempre
    sovrascrivere: quella scelta manuale non viene toccata da re-applicazioni.
    """

    nome = models.CharField(max_length=150)
    priorita = models.IntegerField(
        default=100,
        help_text="A parita' di match viene usata la regola con priorita' piu' bassa.",
    )
    condizione_tipo = models.CharField(
        max_length=30,
        choices=CondizioneRegolaCategorizzazione.choices,
    )
    pattern = models.TextField(blank=True)
    importo_min = models.DecimalField(max_digits=14, decimal_places=2, blank=True, null=True)
    importo_max = models.DecimalField(max_digits=14, decimal_places=2, blank=True, null=True)
    segno_filtro = models.CharField(max_length=10, choices=SegnoMovimento.choices, blank=True)
    categoria_da_assegnare = models.ForeignKey(
        CategoriaFinanziaria,
        on_delete=models.PROTECT,
        related_name="regole",
    )
    attiva = models.BooleanField(default=True)
    volte_applicata = models.PositiveIntegerField(default=0)
    ultima_applicazione_at = models.DateTimeField(blank=True, null=True)
    note = models.TextField(blank=True)
    data_creazione = models.DateTimeField(auto_now_add=True)
    data_aggiornamento = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "gestione_finanziaria_regola_categorizzazione"
        ordering = ["priorita", "nome"]
        verbose_name = "Regola di categorizzazione"
        verbose_name_plural = "Regole di categorizzazione"

    def __str__(self):
        return self.nome


# =========================================================================
#  Movimenti finanziari (bancari e manuali, modello unificato)
# =========================================================================


class OrigineMovimento(models.TextChoices):
    BANCA = "banca", "Movimento bancario"
    IMPORT_FILE = "import_file", "Import estratto conto"
    MANUALE = "manuale", "Inserimento manuale"


class CanaleMovimento(models.TextChoices):
    BANCA = "banca", "Banca"
    CONTANTI = "contanti", "Contanti"
    PERSONALE = "personale", "Spesa sostenuta da terzi"
    CARTA = "carta", "Carta"
    PREPAGATA = "prepagata", "Prepagata"
    ALTRO = "altro", "Altro"


class StatoRiconciliazione(models.TextChoices):
    NON_RICONCILIATO = "non_riconciliato", "Non riconciliato"
    RICONCILIATO = "riconciliato", "Riconciliato"
    IGNORATO = "ignorato", "Ignorato"


class MovimentoFinanziario(models.Model):
    """
    Movimento unificato: puo' provenire dalla banca (via provider o file)
    oppure essere inserito manualmente. La categoria e' assegnabile in
    entrambi i casi cosi' i report per categoria girano sull'intero dataset.

    Per i movimenti bancari `incide_su_saldo_banca` e' True; per le voci
    puramente manuali di norma e' False, perche' non intaccano il saldo
    del conto reale ma servono al controllo di gestione.
    """

    conto = models.ForeignKey(
        ContoBancario,
        on_delete=models.SET_NULL,
        related_name="movimenti",
        blank=True,
        null=True,
    )
    origine = models.CharField(
        max_length=20,
        choices=OrigineMovimento.choices,
        default=OrigineMovimento.MANUALE,
    )
    canale = models.CharField(
        max_length=20,
        choices=CanaleMovimento.choices,
        default=CanaleMovimento.BANCA,
        db_index=True,
        help_text="Canale operativo: banca, contanti, carta/prepagata o spesa sostenuta da terzi.",
    )
    data_contabile = models.DateField(db_index=True)
    data_valuta = models.DateField(blank=True, null=True)
    importo = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        help_text="Negativo per le uscite, positivo per le entrate.",
    )
    valuta = models.CharField(max_length=3, default="EUR")
    descrizione = models.TextField(blank=True)
    controparte = models.CharField(max_length=200, blank=True)
    iban_controparte = models.CharField(max_length=34, blank=True)

    categoria = models.ForeignKey(
        CategoriaFinanziaria,
        on_delete=models.PROTECT,
        related_name="movimenti",
        blank=True,
        null=True,
    )
    categorizzazione_automatica = models.BooleanField(
        default=False,
        help_text="True se la categoria e' stata assegnata da una regola, False se confermata dall'utente.",
    )
    regola_categorizzazione = models.ForeignKey(
        RegolaCategorizzazione,
        on_delete=models.SET_NULL,
        related_name="movimenti_categorizzati",
        blank=True,
        null=True,
    )
    categorizzato_da = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="movimenti_categorizzati",
        blank=True,
        null=True,
    )
    categorizzato_il = models.DateTimeField(blank=True, null=True)

    provider_transaction_id = models.CharField(max_length=120, blank=True, db_index=True)
    hash_deduplica = models.CharField(
        max_length=64,
        blank=True,
        db_index=True,
        help_text="Hash per riconoscere duplicati negli import file (data+importo+descrizione).",
    )
    incide_su_saldo_banca = models.BooleanField(
        default=False,
        help_text="True per movimenti che corrispondono al saldo reale del conto. False per voci gestionali.",
    )
    sostenuta_da_terzi = models.BooleanField(
        default=False,
        help_text="True per spese sostenute da soci/genitori senza uscita dal conto della scuola.",
    )
    rimborsabile = models.BooleanField(
        default=False,
        help_text="True se la spesa sostenuta da terzi dovra' essere rimborsata.",
    )
    sostenitore = models.CharField(
        max_length=160,
        blank=True,
        help_text="Persona o soggetto che ha sostenuto la spesa, se diversa dalla scuola.",
    )

    stato_riconciliazione = models.CharField(
        max_length=25,
        choices=StatoRiconciliazione.choices,
        default=StatoRiconciliazione.NON_RICONCILIATO,
    )
    rata_iscrizione = models.ForeignKey(
        "economia.RataIscrizione",
        on_delete=models.SET_NULL,
        related_name="movimenti_finanziari",
        blank=True,
        null=True,
        help_text="Rata del modulo Economia eventualmente riconciliata con questo movimento.",
    )

    note = models.TextField(blank=True)
    data_creazione = models.DateTimeField(auto_now_add=True)
    data_aggiornamento = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "gestione_finanziaria_movimento"
        ordering = ["-data_contabile", "-id"]
        verbose_name = "Movimento finanziario"
        verbose_name_plural = "Movimenti finanziari"
        indexes = [
            models.Index(fields=["conto", "data_contabile"], name="gf_mov_conto_data_idx"),
            models.Index(fields=["categoria", "data_contabile"], name="gf_mov_cat_data_idx"),
            models.Index(fields=["canale", "data_contabile"], name="gf_mov_canale_data_idx"),
            models.Index(fields=["stato_riconciliazione"], name="gf_mov_stato_ric_idx"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["conto", "provider_transaction_id"],
                condition=~models.Q(provider_transaction_id=""),
                name="gf_mov_unique_provider_tx_per_conto",
            ),
        ]

    def __str__(self):
        return f"{self.data_contabile} {self.importo} - {self.descrizione[:40]}"

    @property
    def e_uscita(self):
        return self.importo is not None and self.importo < 0

    @property
    def e_entrata(self):
        return self.importo is not None and self.importo > 0


class RiconciliazioneRataMovimento(models.Model):
    movimento = models.ForeignKey(
        MovimentoFinanziario,
        on_delete=models.CASCADE,
        related_name="riconciliazioni_rate",
    )
    rata = models.ForeignKey(
        "economia.RataIscrizione",
        on_delete=models.CASCADE,
        related_name="riconciliazioni_movimenti",
    )
    importo = models.DecimalField(max_digits=12, decimal_places=2)
    note = models.TextField(blank=True)
    creato_da = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="riconciliazioni_rate_movimenti_create",
        blank=True,
        null=True,
    )
    data_creazione = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "gestione_finanziaria_riconciliazione_rata_movimento"
        ordering = ["-data_creazione", "-id"]
        verbose_name = "Riconciliazione rata movimento"
        verbose_name_plural = "Riconciliazioni rate movimenti"
        constraints = [
            models.UniqueConstraint(
                fields=["movimento", "rata"],
                name="gf_ric_rata_mov_unique",
            ),
            models.CheckConstraint(
                check=models.Q(importo__gt=0),
                name="gf_ric_rata_mov_importo_pos",
            ),
        ]
        indexes = [
            models.Index(fields=["movimento"], name="gf_ric_rata_mov_idx"),
            models.Index(fields=["rata"], name="gf_ric_rata_rata_idx"),
        ]

    def __str__(self):
        return f"{self.movimento_id} -> {self.rata_id}: {self.importo}"


# =========================================================================
#  Log delle sincronizzazioni
# =========================================================================


class TipoOperazioneSincronizzazione(models.TextChoices):
    SYNC_SALDO = "sync_saldo", "Sincronizzazione saldo"
    SYNC_MOVIMENTI = "sync_movimenti", "Sincronizzazione movimenti"
    IMPORT_FILE = "import_file", "Import file estratto conto"
    REFRESH_CONSENSO = "refresh_consenso", "Refresh consenso PSD2"


class EsitoSincronizzazione(models.TextChoices):
    OK = "ok", "Completata"
    PARZIALE = "parziale", "Parziale"
    ERRORE = "errore", "Errore"


class PianificazioneSincronizzazione(models.Model):
    """
    Configurazione singleton della pianificazione di sincronizzazione PSD2.

    Un solo record (pk=1) con il classico pattern "get_or_create(pk=1)".
    Il campo ``in_corso`` fa da lock per evitare esecuzioni sovrapposte
    quando piu' worker / thread potrebbero partire contemporaneamente
    (middleware su richieste concorrenti, management command, ecc.).
    """

    attivo = models.BooleanField(default=False)
    intervallo_ore = models.PositiveIntegerField(
        default=12,
        help_text="Ogni quante ore tentare la sincronizzazione automatica.",
    )
    sync_saldo = models.BooleanField(default=True)
    sync_movimenti = models.BooleanField(default=True)
    giorni_storico = models.PositiveIntegerField(
        default=14,
        help_text="Per i movimenti: quanti giorni indietro richiedere ad ogni esecuzione.",
    )
    ultimo_run_at = models.DateTimeField(blank=True, null=True)
    avviato_at = models.DateTimeField(blank=True, null=True)
    in_corso = models.BooleanField(default=False)
    ultimo_esito = models.CharField(
        max_length=20,
        choices=EsitoSincronizzazione.choices,
        blank=True,
    )
    ultimo_messaggio = models.TextField(blank=True)
    conti_sincronizzati = models.PositiveIntegerField(default=0)
    conti_in_errore = models.PositiveIntegerField(default=0)
    data_creazione = models.DateTimeField(auto_now_add=True)
    data_aggiornamento = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "gestione_finanziaria_pianificazione_sync"
        verbose_name = "Pianificazione sincronizzazione"
        verbose_name_plural = "Pianificazione sincronizzazione"

    def __str__(self):
        stato = "attiva" if self.attivo else "disattivata"
        return f"Pianificazione PSD2 ({stato}, ogni {self.intervallo_ore}h)"


class StatoConnessioneFattureInCloud(models.TextChoices):
    DA_CONFIGURARE = "da_configurare", "Da configurare"
    ATTIVA = "attiva", "Attiva"
    ERRORE = "errore", "In errore"


class FattureInCloudConnessione(models.Model):
    nome = models.CharField(max_length=150, default="Fatture in Cloud")
    company_id = models.PositiveIntegerField(
        blank=True,
        null=True,
        help_text="ID azienda Fatture in Cloud.",
    )
    client_id = models.CharField(max_length=160, blank=True)
    client_secret_cifrato = models.TextField(blank=True)
    access_token_cifrato = models.TextField(blank=True)
    refresh_token_cifrato = models.TextField(blank=True)
    token_scadenza = models.DateTimeField(blank=True, null=True)
    redirect_uri = models.URLField(blank=True)
    base_url = models.URLField(default="https://api-v2.fattureincloud.it")
    stato = models.CharField(
        max_length=20,
        choices=StatoConnessioneFattureInCloud.choices,
        default=StatoConnessioneFattureInCloud.DA_CONFIGURARE,
    )
    attiva = models.BooleanField(default=True)
    sincronizza_documenti_registrati = models.BooleanField(default=True)
    sincronizza_documenti_da_registrare = models.BooleanField(default=True)
    sync_automatico = models.BooleanField(
        default=False,
        help_text="Se attivo, Arboris prova a sincronizzare periodicamente questa connessione.",
    )
    intervallo_sync_ore = models.PositiveIntegerField(
        default=6,
        help_text="Ogni quante ore tentare la sincronizzazione automatica.",
    )
    ultimo_sync_at = models.DateTimeField(blank=True, null=True)
    avviato_at = models.DateTimeField(blank=True, null=True)
    in_corso = models.BooleanField(default=False)
    ultimo_esito = models.CharField(
        max_length=20,
        choices=EsitoSincronizzazione.choices,
        blank=True,
    )
    ultimo_messaggio = models.TextField(blank=True)
    oauth_state = models.CharField(max_length=120, blank=True)
    webhook_key = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    data_creazione = models.DateTimeField(auto_now_add=True)
    data_aggiornamento = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "gestione_finanziaria_fic_connessione"
        ordering = ["nome"]
        verbose_name = "Connessione Fatture in Cloud"
        verbose_name_plural = "Connessioni Fatture in Cloud"

    def __str__(self):
        return self.nome


class TipoSyncFattureInCloud(models.TextChoices):
    COMPLETA = "completa", "Sincronizzazione completa"
    DOCUMENTO = "documento", "Singolo documento"
    WEBHOOK = "webhook", "Webhook"


class FattureInCloudSyncLog(models.Model):
    connessione = models.ForeignKey(
        FattureInCloudConnessione,
        on_delete=models.SET_NULL,
        related_name="log_sincronizzazioni",
        blank=True,
        null=True,
    )
    tipo_operazione = models.CharField(
        max_length=20,
        choices=TipoSyncFattureInCloud.choices,
        default=TipoSyncFattureInCloud.COMPLETA,
    )
    esito = models.CharField(
        max_length=10,
        choices=EsitoSincronizzazione.choices,
        default=EsitoSincronizzazione.OK,
    )
    documenti_creati = models.PositiveIntegerField(default=0)
    documenti_aggiornati = models.PositiveIntegerField(default=0)
    scadenze_create = models.PositiveIntegerField(default=0)
    notifiche_create = models.PositiveIntegerField(default=0)
    durata_millisecondi = models.PositiveIntegerField(blank=True, null=True)
    messaggio = models.TextField(blank=True)
    data_operazione = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = "gestione_finanziaria_fic_sync_log"
        ordering = ["-data_operazione", "-id"]
        verbose_name = "Log sincronizzazione Fatture in Cloud"
        verbose_name_plural = "Log sincronizzazioni Fatture in Cloud"

    def __str__(self):
        return f"{self.get_tipo_operazione_display()} - {self.data_operazione:%d/%m/%Y %H:%M}"


class SincronizzazioneLog(models.Model):
    conto = models.ForeignKey(
        ContoBancario,
        on_delete=models.SET_NULL,
        related_name="log_sincronizzazioni",
        blank=True,
        null=True,
    )
    connessione = models.ForeignKey(
        ConnessioneBancaria,
        on_delete=models.SET_NULL,
        related_name="log_sincronizzazioni",
        blank=True,
        null=True,
    )
    tipo_operazione = models.CharField(
        max_length=30,
        choices=TipoOperazioneSincronizzazione.choices,
    )
    esito = models.CharField(
        max_length=10,
        choices=EsitoSincronizzazione.choices,
        default=EsitoSincronizzazione.OK,
    )
    movimenti_inseriti = models.PositiveIntegerField(default=0)
    movimenti_aggiornati = models.PositiveIntegerField(default=0)
    durata_millisecondi = models.PositiveIntegerField(blank=True, null=True)
    messaggio = models.TextField(blank=True)
    data_operazione = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = "gestione_finanziaria_sincronizzazione_log"
        ordering = ["-data_operazione", "-id"]
        verbose_name = "Log sincronizzazione"
        verbose_name_plural = "Log sincronizzazioni"

    def __str__(self):
        return f"{self.get_tipo_operazione_display()} - {self.data_operazione:%d/%m/%Y %H:%M}"


# =========================================================================
#  Notifiche finanziarie
# =========================================================================


class TipoNotificaFinanziaria(models.TextChoices):
    FATTURA_RICEVUTA = "fattura_ricevuta", "Fattura ricevuta"
    SCADENZA_PROSSIMA = "scadenza_prossima", "Scadenza prossima"
    SCADENZA_INSOLUTA = "scadenza_insoluta", "Scadenza insoluta"
    RICONCILIAZIONE = "riconciliazione", "Riconciliazione"
    INTEGRAZIONE = "integrazione", "Integrazione"


class LivelloNotificaFinanziaria(models.TextChoices):
    INFO = "info", "Informazione"
    WARNING = "warning", "Attenzione"
    ERRORE = "errore", "Errore"


class NotificaFinanziaria(models.Model):
    titolo = models.CharField(max_length=180)
    messaggio = models.TextField(blank=True)
    tipo = models.CharField(
        max_length=30,
        choices=TipoNotificaFinanziaria.choices,
        default=TipoNotificaFinanziaria.INTEGRAZIONE,
    )
    livello = models.CharField(
        max_length=20,
        choices=LivelloNotificaFinanziaria.choices,
        default=LivelloNotificaFinanziaria.INFO,
    )
    richiede_gestione = models.BooleanField(
        default=False,
        help_text="Se attivo, la notifica e' visibile solo agli utenti con gestione finanziaria.",
    )
    url = models.CharField(max_length=300, blank=True)
    documento = models.ForeignKey(
        DocumentoFornitore,
        on_delete=models.CASCADE,
        related_name="notifiche",
        blank=True,
        null=True,
    )
    scadenza = models.ForeignKey(
        ScadenzaPagamentoFornitore,
        on_delete=models.CASCADE,
        related_name="notifiche",
        blank=True,
        null=True,
    )
    movimento_finanziario = models.ForeignKey(
        MovimentoFinanziario,
        on_delete=models.CASCADE,
        related_name="notifiche_fornitori",
        blank=True,
        null=True,
    )
    chiave_deduplica = models.CharField(max_length=180, blank=True, db_index=True)
    payload = models.JSONField(default=dict, blank=True)
    data_creazione = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = "gestione_finanziaria_notifica"
        ordering = ["-data_creazione", "-id"]
        verbose_name = "Notifica finanziaria"
        verbose_name_plural = "Notifiche finanziarie"
        constraints = [
            models.UniqueConstraint(
                fields=["chiave_deduplica"],
                condition=~models.Q(chiave_deduplica=""),
                name="gf_notifica_unique_dedup",
            ),
        ]

    def __str__(self):
        return self.titolo


class NotificaFinanziariaLettura(models.Model):
    notifica = models.ForeignKey(
        NotificaFinanziaria,
        on_delete=models.CASCADE,
        related_name="letture",
    )
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="notifiche_finanziarie_lette",
    )
    letta_il = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "gestione_finanziaria_notifica_lettura"
        ordering = ["-letta_il"]
        verbose_name = "Lettura notifica finanziaria"
        verbose_name_plural = "Letture notifiche finanziarie"
        constraints = [
            models.UniqueConstraint(
                fields=["notifica", "user"],
                name="gf_notifica_lettura_unique",
            ),
        ]

    def __str__(self):
        return f"{self.user} - {self.notifica_id}"
