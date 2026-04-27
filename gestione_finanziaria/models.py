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


# =========================================================================
#  Categorie spesa e fornitori
# =========================================================================


class CategoriaSpesa(models.Model):
    """
    Categoria trasversale per classificare fornitori, documenti passivi e,
    in futuro, voci di budget previsionale.
    """

    nome = models.CharField(max_length=140, unique=True)
    descrizione = models.TextField(blank=True)
    ordine = models.IntegerField(blank=True, null=True)
    attiva = models.BooleanField(default=True)
    data_creazione = models.DateTimeField(auto_now_add=True)
    data_aggiornamento = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "gestione_finanziaria_categoria_spesa"
        ordering = ["ordine", "nome"]
        verbose_name = "Categoria spesa"
        verbose_name_plural = "Categorie spesa"

    def __str__(self):
        return self.nome

    def save(self, *args, **kwargs):
        if self.ordine is None:
            self.ordine = next_order_value(CategoriaSpesa)
        super().save(*args, **kwargs)


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
        CategoriaSpesa,
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


def documento_fornitore_upload_to(_instance, filename):
    return f"documenti_fornitori/{timezone.localdate():%Y/%m}/{filename}"


class DocumentoFornitore(models.Model):
    fornitore = models.ForeignKey(
        Fornitore,
        on_delete=models.PROTECT,
        related_name="documenti",
    )
    categoria_spesa = models.ForeignKey(
        CategoriaSpesa,
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
        ]

    def __str__(self):
        return f"{self.get_tipo_documento_display()} {self.numero_documento} - {self.fornitore}"

    def clean(self):
        super().clean()
        if self.mese_competenza is not None and not 1 <= self.mese_competenza <= 12:
            raise ValidationError({"mese_competenza": "Il mese di competenza deve essere compreso tra 1 e 12."})

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
    iban = models.CharField(max_length=34, blank=True)
    intestatario = models.CharField(max_length=200, blank=True)
    banca = models.CharField(max_length=150, blank=True)
    bic = models.CharField(max_length=15, blank=True)
    valuta = models.CharField(max_length=3, default="EUR")
    provider = models.ForeignKey(
        ProviderBancario,
        on_delete=models.PROTECT,
        related_name="conti",
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
    data_creazione = models.DateTimeField(auto_now_add=True)

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
    pattern = models.CharField(max_length=255, blank=True)
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
