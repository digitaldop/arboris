from calendar import monthrange
from datetime import date
from decimal import Decimal, ROUND_DOWN, ROUND_HALF_UP

from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Max

from anagrafica.models import Famiglia, Studente
from scuola.models import AnnoScolastico, Classe, GruppoClasse


def next_order_value(model_cls, field_name="ordine", **filters):
    max_value = model_cls.objects.filter(**filters).aggregate(max_value=Max(field_name))["max_value"]
    return (max_value or 0) + 1


def add_months_safe(base_date, months, target_day=None):
    month_offset = base_date.month - 1 + months
    year = base_date.year + month_offset // 12
    month = (month_offset % 12) + 1
    desired_day = target_day if target_day is not None else base_date.day
    day = min(desired_day, monthrange(year, month)[1])
    return date(year, month, day)


MONTH_NUMBER_CHOICES = (
    (1, "Gennaio"),
    (2, "Febbraio"),
    (3, "Marzo"),
    (4, "Aprile"),
    (5, "Maggio"),
    (6, "Giugno"),
    (7, "Luglio"),
    (8, "Agosto"),
    (9, "Settembre"),
    (10, "Ottobre"),
    (11, "Novembre"),
    (12, "Dicembre"),
)

RATE_TYPE_MENSILE = "mensile"
RATE_TYPE_PREISCRIZIONE = "preiscrizione"
RATE_TYPE_UNICA_SOLUZIONE = "unica_soluzione"
RATE_TYPE_CHOICES = (
    (RATE_TYPE_MENSILE, "Mensile"),
    (RATE_TYPE_PREISCRIZIONE, "Preiscrizione"),
    (RATE_TYPE_UNICA_SOLUZIONE, "Unica soluzione"),
)

PAYMENT_MODE_RATEALE = "rateale"
PAYMENT_MODE_UNICA_SOLUZIONE = "unica_soluzione"
PAYMENT_MODE_CHOICES = (
    (PAYMENT_MODE_RATEALE, "Rateale"),
    (PAYMENT_MODE_UNICA_SOLUZIONE, "Unica soluzione"),
)

DISCOUNT_TYPE_NONE = "nessuno"
DISCOUNT_TYPE_PERCENT = "percentuale"
DISCOUNT_TYPE_AMOUNT = "importo"
DISCOUNT_TYPE_CHOICES = (
    (DISCOUNT_TYPE_NONE, "Nessuno"),
    (DISCOUNT_TYPE_PERCENT, "Percentuale"),
    (DISCOUNT_TYPE_AMOUNT, "Importo fisso"),
)

MID_YEAR_RULE_MONTH_INCLUDED = "mese_iscrizione_intero"
MID_YEAR_RULE_NEXT_MONTH_AFTER_THRESHOLD = "mese_successivo_dopo_soglia"
MID_YEAR_RULE_DAILY_PRORATA = "pro_rata_giornaliero"
MID_YEAR_DEFAULT_THRESHOLD_DAY = 15


def get_mid_year_enrollment_settings():
    try:
        from sistema.models import SistemaImpostazioniGenerali
    except ImportError:  # pragma: no cover
        return MID_YEAR_RULE_MONTH_INCLUDED, MID_YEAR_DEFAULT_THRESHOLD_DAY

    impostazioni = (
        SistemaImpostazioniGenerali.objects.only(
            "gestione_iscrizione_corso_anno",
            "giorno_soglia_iscrizione_corso_anno",
        )
        .order_by("id")
        .first()
    )
    if not impostazioni:
        return MID_YEAR_RULE_MONTH_INCLUDED, MID_YEAR_DEFAULT_THRESHOLD_DAY

    return (
        impostazioni.gestione_iscrizione_corso_anno or MID_YEAR_RULE_MONTH_INCLUDED,
        impostazioni.giorno_soglia_iscrizione_corso_anno or MID_YEAR_DEFAULT_THRESHOLD_DAY,
    )


class StatoIscrizione(models.Model):
    stato_iscrizione = models.CharField(max_length=100, unique=True)
    ordine = models.PositiveIntegerField(blank=True)
    attiva = models.BooleanField(default=True, db_column="attivo")
    note = models.TextField(blank=True)

    class Meta:
        db_table = "economia_stato_iscrizione"
        ordering = ["ordine", "stato_iscrizione"]
        verbose_name = "Stato iscrizione"
        verbose_name_plural = "Stati iscrizione"

    def __str__(self):
        return self.stato_iscrizione

    def save(self, *args, **kwargs):
        if not self.ordine:
            self.ordine = next_order_value(StatoIscrizione)
        super().save(*args, **kwargs)


class CondizioneIscrizione(models.Model):
    DEFAULT_MESE_PRIMA_RETTA = 9

    anno_scolastico = models.ForeignKey(
        AnnoScolastico,
        on_delete=models.PROTECT,
        related_name="condizioni_iscrizione",
    )
    nome_condizione_iscrizione = models.CharField(max_length=150)
    numero_mensilita_default = models.PositiveIntegerField()
    mese_prima_retta = models.PositiveSmallIntegerField(
        choices=MONTH_NUMBER_CHOICES,
        default=DEFAULT_MESE_PRIMA_RETTA,
        help_text="Mese di competenza da cui iniziare a generare le rette dell'anno scolastico.",
    )
    giorno_scadenza_rate = models.PositiveSmallIntegerField(
        blank=True,
        null=True,
        validators=[MinValueValidator(1), MaxValueValidator(31)],
        help_text="Giorno del mese usato per calcolare la scadenza di ciascuna rata.",
    )
    riduzione_speciale_ammessa = models.BooleanField(default=False)
    attiva = models.BooleanField(default=True)
    note = models.TextField(blank=True)

    class Meta:
        db_table = "economia_condizione_iscrizione"
        ordering = ["-anno_scolastico__data_inizio", "nome_condizione_iscrizione"]
        verbose_name = "Condizione iscrizione"
        verbose_name_plural = "Condizioni iscrizione"
        constraints = [
            models.UniqueConstraint(
                fields=["anno_scolastico", "nome_condizione_iscrizione"],
                name="unique_economia_condizione_iscrizione_per_anno",
            )
        ]

    def __str__(self):
        return f"{self.nome_condizione_iscrizione} - {self.anno_scolastico}"

    def resolve_mese_prima_retta_date(self):
        if not self.anno_scolastico_id or not self.anno_scolastico or not self.anno_scolastico.data_inizio:
            return None

        mese_prima_retta = self.mese_prima_retta or self.DEFAULT_MESE_PRIMA_RETTA
        anno_iniziale = self.anno_scolastico.data_inizio.year
        mese_iniziale = self.anno_scolastico.data_inizio.month
        anno_mese_prima_retta = anno_iniziale if mese_prima_retta >= mese_iniziale else anno_iniziale + 1
        return date(anno_mese_prima_retta, mese_prima_retta, 1)

    def clean(self):
        super().clean()

        mese_prima_retta_date = self.resolve_mese_prima_retta_date()
        if (
            not mese_prima_retta_date
            or not self.anno_scolastico_id
            or not self.anno_scolastico
            or not self.anno_scolastico.data_inizio
            or not self.anno_scolastico.data_fine
        ):
            return

        data_inizio_anno = self.anno_scolastico.data_inizio.replace(day=1)
        data_fine_anno = self.anno_scolastico.data_fine.replace(day=1)

        if mese_prima_retta_date < data_inizio_anno or mese_prima_retta_date > data_fine_anno:
            raise ValidationError(
                {
                    "mese_prima_retta": (
                        "Il mese della prima retta deve rientrare nell'intervallo dell'anno scolastico selezionato."
                    )
                }
            )


class TariffaCondizioneIscrizione(models.Model):
    condizione_iscrizione = models.ForeignKey(
        CondizioneIscrizione,
        on_delete=models.CASCADE,
        related_name="tariffe",
    )
    ordine_figlio_da = models.PositiveIntegerField(blank=True)
    ordine_figlio_a = models.PositiveIntegerField(blank=True, null=True)
    retta_annuale = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    preiscrizione = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    attiva = models.BooleanField(default=True)
    note = models.TextField(blank=True)

    class Meta:
        db_table = "economia_tariffa_condizione_iscrizione"
        ordering = ["condizione_iscrizione", "ordine_figlio_da", "ordine_figlio_a", "id"]
        verbose_name = "Tariffa condizione iscrizione"
        verbose_name_plural = "Tariffe condizione iscrizione"

    @property
    def fascia_figli_label(self):
        if self.ordine_figlio_a is None:
            return f"{self.ordine_figlio_da}+"
        if self.ordine_figlio_da == self.ordine_figlio_a:
            return str(self.ordine_figlio_da)
        return f"{self.ordine_figlio_da}-{self.ordine_figlio_a}"

    def __str__(self):
        return f"{self.condizione_iscrizione} - Figli {self.fascia_figli_label}"

    def save(self, *args, **kwargs):
        if not self.ordine_figlio_da:
            self.ordine_figlio_da = next_order_value(
                TariffaCondizioneIscrizione,
                field_name="ordine_figlio_da",
                condizione_iscrizione=self.condizione_iscrizione,
            )
        super().save(*args, **kwargs)

    def clean(self):
        super().clean()

        if self.ordine_figlio_a is not None and self.ordine_figlio_a < self.ordine_figlio_da:
            raise ValidationError("Il figlio finale della fascia non puo essere inferiore al figlio iniziale.")

        if not self.condizione_iscrizione_id or not self.ordine_figlio_da:
            return

        overlapping_tariffe = TariffaCondizioneIscrizione.objects.filter(
            condizione_iscrizione_id=self.condizione_iscrizione_id,
        ).exclude(pk=self.pk)

        current_end = self.ordine_figlio_a if self.ordine_figlio_a is not None else float("inf")

        for tariffa in overlapping_tariffe:
            other_end = tariffa.ordine_figlio_a if tariffa.ordine_figlio_a is not None else float("inf")
            if self.ordine_figlio_da <= other_end and tariffa.ordine_figlio_da <= current_end:
                raise ValidationError("Le fasce figli della stessa condizione non possono sovrapporsi.")


class Agevolazione(models.Model):
    nome_agevolazione = models.CharField(max_length=150, unique=True)
    importo_annuale_agevolazione = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    attiva = models.BooleanField(default=True)

    class Meta:
        db_table = "economia_agevolazione"
        ordering = ["nome_agevolazione"]
        verbose_name = "Agevolazione"
        verbose_name_plural = "Agevolazioni"

    def __str__(self):
        return self.nome_agevolazione


class Iscrizione(models.Model):
    MODALITA_PAGAMENTO_RATEALE = PAYMENT_MODE_RATEALE
    MODALITA_PAGAMENTO_UNICA_SOLUZIONE = PAYMENT_MODE_UNICA_SOLUZIONE
    MODALITA_PAGAMENTO_CHOICES = PAYMENT_MODE_CHOICES
    SCONTO_UNICA_NESSUNO = DISCOUNT_TYPE_NONE
    SCONTO_UNICA_PERCENTUALE = DISCOUNT_TYPE_PERCENT
    SCONTO_UNICA_IMPORTO = DISCOUNT_TYPE_AMOUNT
    SCONTO_UNICA_CHOICES = DISCOUNT_TYPE_CHOICES

    studente = models.ForeignKey(
        Studente,
        on_delete=models.CASCADE,
        related_name="iscrizioni",
    )
    classe = models.ForeignKey(
        Classe,
        on_delete=models.SET_NULL,
        related_name="iscrizioni",
        blank=True,
        null=True,
    )
    gruppo_classe = models.ForeignKey(
        GruppoClasse,
        verbose_name="Pluriclasse",
        on_delete=models.SET_NULL,
        related_name="iscrizioni",
        blank=True,
        null=True,
    )
    data_iscrizione = models.DateField(blank=True, null=True)
    data_fine_iscrizione = models.DateField(blank=True, null=True)
    anno_scolastico = models.ForeignKey(
        AnnoScolastico,
        on_delete=models.PROTECT,
        related_name="iscrizioni",
    )
    stato_iscrizione = models.ForeignKey(
        StatoIscrizione,
        on_delete=models.PROTECT,
        related_name="iscrizioni",
    )
    condizione_iscrizione = models.ForeignKey(
        CondizioneIscrizione,
        on_delete=models.PROTECT,
        related_name="iscrizioni",
    )
    agevolazione = models.ForeignKey(
        Agevolazione,
        on_delete=models.SET_NULL,
        related_name="iscrizioni",
        blank=True,
        null=True,
    )
    riduzione_speciale = models.BooleanField(default=False)
    importo_riduzione_speciale = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    non_pagante = models.BooleanField(default=False)
    modalita_pagamento_retta = models.CharField(
        max_length=20,
        choices=PAYMENT_MODE_CHOICES,
        default=PAYMENT_MODE_RATEALE,
    )
    sconto_unica_soluzione_tipo = models.CharField(
        max_length=20,
        choices=DISCOUNT_TYPE_CHOICES,
        default=DISCOUNT_TYPE_NONE,
    )
    sconto_unica_soluzione_valore = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    scadenza_pagamento_unica = models.DateField(blank=True, null=True)
    attiva = models.BooleanField(default=True)
    note_amministrative = models.TextField(blank=True)
    note = models.TextField(blank=True)

    class Meta:
        db_table = "economia_iscrizione"
        ordering = ["-anno_scolastico__data_inizio", "studente__cognome", "studente__nome"]
        verbose_name = "Iscrizione"
        verbose_name_plural = "Iscrizioni"
        constraints = [
            models.UniqueConstraint(
                fields=["studente", "anno_scolastico"],
                name="unique_economia_iscrizione_studente_anno",
            )
        ]

    def __str__(self):
        return f"{self.studente} - {self.anno_scolastico}"

    @property
    def famiglia(self):
        return self.studente.famiglia

    @property
    def tariffa_applicabile(self):
        return self.get_tariffa_applicabile()

    def get_ordine_figlio(self):
        if not self.studente_id or not self.anno_scolastico_id or not self.studente.famiglia_id:
            return 1

        iscrizioni_ids = list(
            Iscrizione.objects.filter(
                studente__famiglia_id=self.studente.famiglia_id,
                anno_scolastico_id=self.anno_scolastico_id,
            )
            .order_by("studente__data_nascita", "studente__cognome", "studente__nome", "studente_id", "id")
            .values_list("id", flat=True)
        )

        if self.pk in iscrizioni_ids:
            return iscrizioni_ids.index(self.pk) + 1

        return len(iscrizioni_ids) + 1

    def get_tariffa_applicabile(self):
        if not self.condizione_iscrizione_id:
            return None

        target_order = self.get_ordine_figlio()
        return (
            self.condizione_iscrizione.tariffe.filter(
                attiva=True,
                ordine_figlio_da__lte=target_order,
            )
            .filter(
                models.Q(ordine_figlio_a__isnull=True)
                | models.Q(ordine_figlio_a__gte=target_order)
            )
            .order_by("ordine_figlio_da", "ordine_figlio_a", "id")
            .first()
        )

    def get_importo_agevolazione_applicata(self):
        if self.non_pagante or not self.agevolazione_id:
            return Decimal("0.00")
        return self.agevolazione.importo_annuale_agevolazione or Decimal("0.00")

    def get_importo_riduzione_applicata(self):
        if self.non_pagante or not self.riduzione_speciale:
            return Decimal("0.00")
        return self.importo_riduzione_speciale or Decimal("0.00")

    @property
    def is_pagamento_unica_soluzione(self):
        return self.modalita_pagamento_retta == PAYMENT_MODE_UNICA_SOLUZIONE

    def get_importo_annuo_base_dovuto(self):
        if self.non_pagante:
            return Decimal("0.00")

        tariffa = self.get_tariffa_applicabile()
        if not tariffa:
            return Decimal("0.00")

        importo = tariffa.retta_annuale

        importo -= self.get_importo_agevolazione_applicata()
        importo -= self.get_importo_riduzione_applicata()

        return max(importo, Decimal("0.00"))

    def get_importo_sconto_unica_soluzione_applicato(self, importo_base=None):
        if self.non_pagante or not self.is_pagamento_unica_soluzione:
            return Decimal("0.00")

        tipo_sconto = self.sconto_unica_soluzione_tipo or DISCOUNT_TYPE_NONE
        valore_sconto = self.sconto_unica_soluzione_valore or Decimal("0.00")
        if tipo_sconto == DISCOUNT_TYPE_NONE or valore_sconto <= 0:
            return Decimal("0.00")

        importo_base = importo_base if importo_base is not None else self.get_importo_periodo_base_dovuto()
        if importo_base <= 0:
            return Decimal("0.00")

        if tipo_sconto == DISCOUNT_TYPE_PERCENT:
            sconto = (importo_base * valore_sconto / Decimal("100")).quantize(
                Decimal("0.01"),
                rounding=ROUND_HALF_UP,
            )
        else:
            sconto = valore_sconto

        return min(max(sconto, Decimal("0.00")), importo_base)

    def get_importo_annuo_dovuto(self):
        importo = self.get_importo_periodo_base_dovuto()
        importo -= self.get_importo_sconto_unica_soluzione_applicato(importo)
        return max(importo, Decimal("0.00"))

    def get_importo_preiscrizione_dovuto(self):
        if self.non_pagante:
            return Decimal("0.00")

        tariffa = self.get_tariffa_applicabile()
        if not tariffa:
            return Decimal("0.00")

        return tariffa.preiscrizione or Decimal("0.00")

    def get_data_partenza_rate(self):
        if self.condizione_iscrizione_id and self.condizione_iscrizione:
            data_prima_retta = self.condizione_iscrizione.resolve_mese_prima_retta_date()
            if data_prima_retta:
                return data_prima_retta

        if self.anno_scolastico_id and self.anno_scolastico and self.anno_scolastico.data_inizio:
            return self.anno_scolastico.data_inizio.replace(day=1)

        return self.data_iscrizione or getattr(self.anno_scolastico, "data_inizio", None)

    def get_giorno_scadenza_rate(self):
        if self.condizione_iscrizione_id and self.condizione_iscrizione and self.condizione_iscrizione.giorno_scadenza_rate:
            return self.condizione_iscrizione.giorno_scadenza_rate

        if self.anno_scolastico_id and self.anno_scolastico and self.anno_scolastico.data_inizio:
            return self.anno_scolastico.data_inizio.day

        if self.data_iscrizione:
            return self.data_iscrizione.day

        return 1

    @property
    def data_fine_effettiva(self):
        if self.data_fine_iscrizione:
            return self.data_fine_iscrizione
        if self.anno_scolastico_id and self.anno_scolastico:
            return self.anno_scolastico.data_fine
        return None

    def get_prima_scadenza_rate(self):
        data_partenza = self.get_data_partenza_rate()
        if not data_partenza:
            return None

        giorno_scadenza = self.get_giorno_scadenza_rate()

        prima_scadenza = date(
            data_partenza.year,
            data_partenza.month,
            min(giorno_scadenza, monthrange(data_partenza.year, data_partenza.month)[1]),
        )

        return prima_scadenza

    def get_mese_partenza_effettivo_rate(self, prima_scadenza):
        if not prima_scadenza:
            return None, False

        mese_partenza_standard = prima_scadenza.replace(day=1)
        if not self.data_iscrizione:
            return mese_partenza_standard, False

        mese_iscrizione = self.data_iscrizione.replace(day=1)
        if mese_iscrizione < mese_partenza_standard:
            return mese_partenza_standard, False

        regola, giorno_soglia = get_mid_year_enrollment_settings()
        if regola == MID_YEAR_RULE_NEXT_MONTH_AFTER_THRESHOLD and self.data_iscrizione.day > giorno_soglia:
            return add_months_safe(mese_iscrizione, 1, target_day=1).replace(day=1), False

        return mese_iscrizione, regola == MID_YEAR_RULE_DAILY_PRORATA

    def build_rate_mensili_entries_for_importo(self, importo_annuo):
        if not self.condizione_iscrizione_id or not self.studente_id or not self.studente.famiglia_id:
            return []

        prima_scadenza = self.get_prima_scadenza_rate()
        if not prima_scadenza:
            return []

        tariffa = self.get_tariffa_applicabile()
        if not self.non_pagante and not tariffa:
            return []

        numero_rate = max(self.condizione_iscrizione.numero_mensilita_default or 0, 1)
        importo_annuo_base = importo_annuo or Decimal("0.00")
        importo_base = (importo_annuo_base / numero_rate).quantize(Decimal("0.01"), rounding=ROUND_DOWN)
        importo_residuo = importo_annuo_base - (importo_base * numero_rate)

        mese_partenza_effettivo, applica_pro_rata = self.get_mese_partenza_effettivo_rate(prima_scadenza)
        data_fine_effettiva = self.data_fine_effettiva
        mese_fine_effettiva = data_fine_effettiva.replace(day=1) if data_fine_effettiva else None
        giorno_scadenza = self.get_giorno_scadenza_rate()
        piano = []

        for indice in range(numero_rate):
            data_scadenza = add_months_safe(prima_scadenza, indice, target_day=giorno_scadenza)
            mese_rata = data_scadenza.replace(day=1)
            if mese_partenza_effettivo and mese_rata < mese_partenza_effettivo:
                continue
            if mese_fine_effettiva and mese_rata > mese_fine_effettiva:
                break

            importo_rata = importo_base + (importo_residuo if indice == numero_rate - 1 else Decimal("0.00"))
            descrizione_extra = ""

            if (
                applica_pro_rata
                and self.data_iscrizione
                and mese_rata == self.data_iscrizione.replace(day=1)
            ):
                giorni_mese = monthrange(mese_rata.year, mese_rata.month)[1]
                giorni_da_pagare = giorni_mese - self.data_iscrizione.day + 1
                importo_rata = (importo_rata * Decimal(giorni_da_pagare) / Decimal(giorni_mese)).quantize(
                    Decimal("0.01"),
                    rounding=ROUND_HALF_UP,
                )
                descrizione_extra = " (pro-rata)"

            if self.data_iscrizione and mese_rata == self.data_iscrizione.replace(day=1) and data_scadenza < self.data_iscrizione:
                data_scadenza = self.data_iscrizione

            piano.append(
                {
                    "famiglia_id": self.studente.famiglia_id,
                    "tipo_rata": RATE_TYPE_MENSILE,
                    "numero_rata": indice + 1,
                    "mese_riferimento": mese_rata.month,
                    "anno_riferimento": mese_rata.year,
                    "descrizione": f"Rata {indice + 1}/{numero_rate} - {mese_rata.strftime('%m/%Y')}{descrizione_extra}",
                    "importo_dovuto": importo_rata,
                    "data_scadenza": data_scadenza,
                    "credito_applicato": Decimal("0.00"),
                    "altri_sgravi": Decimal("0.00"),
                    "importo_finale": importo_rata,
                }
            )

        return piano

    def build_rate_mensili_base_entries(self):
        return self.build_rate_mensili_entries_for_importo(self.get_importo_annuo_base_dovuto())

    def get_importo_periodo_base_dovuto(self):
        return sum(
            (item.get("importo_dovuto") or Decimal("0.00"))
            for item in self.build_rate_mensili_base_entries()
        )

    def get_prima_scadenza_rate_effettiva(self):
        piano = self.build_rate_mensili_base_entries()
        if piano:
            return piano[0]["data_scadenza"]
        return self.get_prima_scadenza_rate()

    def get_scadenza_pagamento_unica_soluzione(self):
        return self.scadenza_pagamento_unica or self.get_prima_scadenza_rate_effettiva()

    def build_preiscrizione_rate_entry(self):
        importo_preiscrizione = self.get_importo_preiscrizione_dovuto()
        if importo_preiscrizione <= 0:
            return None

        anno_scolastico_label = ""
        if self.anno_scolastico_id and self.anno_scolastico:
            anno_scolastico_label = self.anno_scolastico.nome_anno_scolastico or str(self.anno_scolastico)
        anno_riferimento = (
            self.anno_scolastico.data_inizio.year
            if self.anno_scolastico_id and self.anno_scolastico and self.anno_scolastico.data_inizio
            else date.today().year
        )
        descrizione = (
            f"Preiscrizione AS {anno_scolastico_label}"
            if anno_scolastico_label
            else "Preiscrizione"
        )

        return {
            "famiglia_id": self.studente.famiglia_id,
            "tipo_rata": RATE_TYPE_PREISCRIZIONE,
            "numero_rata": 0,
            "mese_riferimento": 1,
            "anno_riferimento": anno_riferimento,
            "descrizione": descrizione,
            "importo_dovuto": importo_preiscrizione,
            "data_scadenza": None,
            "credito_applicato": Decimal("0.00"),
            "altri_sgravi": Decimal("0.00"),
            "importo_finale": importo_preiscrizione,
        }

    def build_unica_soluzione_rate_entry(self, importo_annuo):
        data_scadenza = self.get_scadenza_pagamento_unica_soluzione()
        if not data_scadenza:
            data_scadenza = (
                self.anno_scolastico.data_inizio
                if self.anno_scolastico_id and self.anno_scolastico and self.anno_scolastico.data_inizio
                else date.today()
            )

        anno_scolastico_label = ""
        if self.anno_scolastico_id and self.anno_scolastico:
            anno_scolastico_label = self.anno_scolastico.nome_anno_scolastico or str(self.anno_scolastico)
        descrizione = (
            f"Retta annuale in unica soluzione - AS {anno_scolastico_label}"
            if anno_scolastico_label
            else "Retta annuale in unica soluzione"
        )

        return {
            "famiglia_id": self.studente.famiglia_id,
            "tipo_rata": RATE_TYPE_UNICA_SOLUZIONE,
            "numero_rata": 1,
            "mese_riferimento": data_scadenza.month,
            "anno_riferimento": data_scadenza.year,
            "descrizione": descrizione,
            "importo_dovuto": importo_annuo,
            "data_scadenza": data_scadenza,
            "credito_applicato": Decimal("0.00"),
            "altri_sgravi": Decimal("0.00"),
            "importo_finale": importo_annuo,
        }

    def build_rate_plan(self):
        if not self.condizione_iscrizione_id or not self.studente_id or not self.studente.famiglia_id:
            return []

        piano_mensile = self.build_rate_mensili_base_entries()
        if not piano_mensile:
            return []

        piano = []
        rata_preiscrizione = self.build_preiscrizione_rate_entry()

        if rata_preiscrizione:
            piano.append(rata_preiscrizione)

        if self.is_pagamento_unica_soluzione:
            importo_periodo_base = sum(item["importo_dovuto"] for item in piano_mensile)
            importo_annuo = max(
                importo_periodo_base - self.get_importo_sconto_unica_soluzione_applicato(importo_periodo_base),
                Decimal("0.00"),
            )
            piano.append(self.build_unica_soluzione_rate_entry(importo_annuo))
            return piano

        piano.extend(piano_mensile)
        return piano

    def rate_have_payment_activity(self):
        return any(rata.has_locking_payment_activity() for rata in self.rate.all())

    def rate_matches_expected(self, rata, attesa):
        return (
            rata.famiglia_id == attesa["famiglia_id"]
            and (rata.tipo_rata or RATE_TYPE_MENSILE) == attesa.get("tipo_rata", RATE_TYPE_MENSILE)
            and rata.numero_rata == attesa["numero_rata"]
            and rata.mese_riferimento == attesa["mese_riferimento"]
            and rata.anno_riferimento == attesa["anno_riferimento"]
            and rata.importo_dovuto == attesa["importo_dovuto"]
            and rata.data_scadenza == attesa["data_scadenza"]
            and (rata.descrizione or "") == attesa["descrizione"]
        )

    def rate_plan_matches(self, piano_atteso):
        rate_esistenti = list(self.rate.order_by("anno_riferimento", "mese_riferimento", "numero_rata", "id"))
        if len(rate_esistenti) != len(piano_atteso):
            return False

        for rata, attesa in zip(rate_esistenti, piano_atteso):
            if not self.rate_matches_expected(rata, attesa):
                return False

        return True

    def get_missing_preiscrizione_rate_entry(self, piano_atteso):
        rata_preiscrizione = next(
            (item for item in piano_atteso if item.get("tipo_rata") == RATE_TYPE_PREISCRIZIONE),
            None,
        )
        if not rata_preiscrizione:
            return None

        rate_esistenti = list(self.rate.order_by("anno_riferimento", "mese_riferimento", "numero_rata", "id"))
        if any((rata.tipo_rata or RATE_TYPE_MENSILE) == RATE_TYPE_PREISCRIZIONE for rata in rate_esistenti):
            return None

        piano_senza_preiscrizione = [
            item for item in piano_atteso if item.get("tipo_rata") != RATE_TYPE_PREISCRIZIONE
        ]
        if len(rate_esistenti) != len(piano_senza_preiscrizione):
            return None

        for rata, attesa in zip(rate_esistenti, piano_senza_preiscrizione):
            if not self.rate_matches_expected(rata, attesa):
                return None

        return rata_preiscrizione

    def _sincronizza_fondo_accantonamento_su_agevolazione(self) -> None:
        """Vedi fondo_accantonamento: sconti SCONTO_RETTA su agev. collegate a un piano."""
        if not self.pk:
            return
        try:
            from fondo_accantonamento.services.sconti_agevolazione import (
                sincronizza_sconti_fondo_da_iscrizione,
            )
        except ImportError:
            return
        sincronizza_sconti_fondo_da_iscrizione(self)

    def sync_rate_schedule(self):
        if not self.pk:
            return "missing"

        piano_atteso = self.build_rate_plan()
        if not piano_atteso:
            self._sincronizza_fondo_accantonamento_su_agevolazione()
            return "missing"

        if not self.rate.exists():
            RataIscrizione.objects.bulk_create(
                [RataIscrizione(iscrizione=self, **dati_rata) for dati_rata in piano_atteso]
            )
            self._sincronizza_fondo_accantonamento_su_agevolazione()
            return "created"

        rata_preiscrizione_mancante = self.get_missing_preiscrizione_rate_entry(piano_atteso)
        if rata_preiscrizione_mancante:
            RataIscrizione.objects.create(iscrizione=self, **rata_preiscrizione_mancante)
            self._sincronizza_fondo_accantonamento_su_agevolazione()
            return "precreated"

        if self.rate_have_payment_activity():
            self._sincronizza_fondo_accantonamento_su_agevolazione()
            return "locked"

        if self.rate_plan_matches(piano_atteso):
            self._sincronizza_fondo_accantonamento_su_agevolazione()
            return "unchanged"

        self.rate.all().delete()
        RataIscrizione.objects.bulk_create(
            [RataIscrizione(iscrizione=self, **dati_rata) for dati_rata in piano_atteso]
        )
        self._sincronizza_fondo_accantonamento_su_agevolazione()
        return "regenerated"

    def get_riepilogo_economico(self):
        tariffa = self.get_tariffa_applicabile()
        piano = self.build_rate_plan()
        piano_mensile = [item for item in piano if item.get("tipo_rata") == RATE_TYPE_MENSILE]
        piano_unica_soluzione = [item for item in piano if item.get("tipo_rata") == RATE_TYPE_UNICA_SOLUZIONE]
        importo_base = tariffa.retta_annuale if tariffa else Decimal("0.00")
        importo_preiscrizione = self.get_importo_preiscrizione_dovuto()
        agevolazione = self.get_importo_agevolazione_applicata()
        riduzione = self.get_importo_riduzione_applicata()
        sconto_unica_soluzione = self.get_importo_sconto_unica_soluzione_applicato()
        importo_annuo = self.get_importo_annuo_dovuto()

        rata_standard = piano_mensile[0]["importo_dovuto"] if piano_mensile else Decimal("0.00")
        rata_finale = piano_mensile[-1]["importo_dovuto"] if piano_mensile else Decimal("0.00")
        rata_unica = piano_unica_soluzione[0]["importo_dovuto"] if piano_unica_soluzione else Decimal("0.00")

        return {
            "retta_annuale_base": importo_base,
            "importo_preiscrizione": importo_preiscrizione,
            "importo_agevolazione": agevolazione,
            "importo_riduzione_speciale": riduzione,
            "sconto_unica_soluzione": sconto_unica_soluzione,
            "totale_annuo_netto": importo_annuo,
            "totale_complessivo": importo_annuo + importo_preiscrizione,
            "modalita_pagamento": self.get_modalita_pagamento_retta_display(),
            "pagamento_unica_soluzione": self.is_pagamento_unica_soluzione,
            "scadenza_pagamento_unica": self.get_scadenza_pagamento_unica_soluzione()
            if self.is_pagamento_unica_soluzione
            else None,
            "numero_mensilita": max(self.condizione_iscrizione.numero_mensilita_default or 0, 1)
            if self.condizione_iscrizione_id
            else 0,
            "rata_standard": rata_standard,
            "rata_finale": rata_finale,
            "rata_unica": rata_unica,
            "ultima_rata_diversa": bool(piano_mensile) and rata_finale != rata_standard,
        }

    def clean(self):
        super().clean()

        if (
            self.gruppo_classe_id
            and self.gruppo_classe
            and self.gruppo_classe.anno_scolastico_id != self.anno_scolastico_id
        ):
            raise ValidationError("La Pluriclasse selezionata non appartiene all'anno scolastico scelto.")

        if self.gruppo_classe_id and not self.classe_id:
            raise ValidationError(
                "Per assegnare una Pluriclasse seleziona anche la Classe standard dello studente."
            )

        if self.gruppo_classe_id and self.classe_id and self.gruppo_classe:
            if not self.gruppo_classe.classi.filter(pk=self.classe_id).exists():
                raise ValidationError("La classe selezionata deve essere inclusa nella Pluriclasse scelta.")

        if (
            self.condizione_iscrizione_id
            and self.condizione_iscrizione
            and self.condizione_iscrizione.anno_scolastico_id != self.anno_scolastico_id
        ):
            raise ValidationError("La condizione di iscrizione selezionata non appartiene all'anno scolastico scelto.")

        if self.data_fine_effettiva and self.data_iscrizione and self.data_fine_effettiva < self.data_iscrizione:
            raise ValidationError("La data di fine iscrizione non puo essere precedente alla data di iscrizione.")

        if not self.riduzione_speciale and self.importo_riduzione_speciale:
            raise ValidationError("L'importo della riduzione speciale puo essere valorizzato solo se la riduzione speciale e attiva.")

        if self.non_pagante:
            self.sconto_unica_soluzione_tipo = DISCOUNT_TYPE_NONE
            self.sconto_unica_soluzione_valore = Decimal("0.00")
            self.scadenza_pagamento_unica = None
        elif not self.is_pagamento_unica_soluzione:
            self.sconto_unica_soluzione_tipo = DISCOUNT_TYPE_NONE
            self.sconto_unica_soluzione_valore = Decimal("0.00")
            self.scadenza_pagamento_unica = None
        else:
            valore_sconto = self.sconto_unica_soluzione_valore or Decimal("0.00")
            if valore_sconto < 0:
                raise ValidationError("Lo sconto per unica soluzione non puo essere negativo.")
            if self.sconto_unica_soluzione_tipo == DISCOUNT_TYPE_NONE:
                self.sconto_unica_soluzione_valore = Decimal("0.00")
            if self.sconto_unica_soluzione_tipo == DISCOUNT_TYPE_PERCENT and valore_sconto > 100:
                raise ValidationError("Lo sconto percentuale per unica soluzione non puo superare il 100%.")

        if (
            self.riduzione_speciale
            and self.condizione_iscrizione_id
            and self.condizione_iscrizione
            and not self.condizione_iscrizione.riduzione_speciale_ammessa
        ):
            raise ValidationError("La condizione di iscrizione selezionata non ammette riduzione speciale.")

        if (
            not self.non_pagante
            and self.studente_id
            and self.anno_scolastico_id
            and self.condizione_iscrizione_id
            and not self.get_tariffa_applicabile()
        ):
            raise ValidationError(
                "Per la condizione di iscrizione selezionata non esiste una tariffa attiva applicabile. "
                "Configura prima la tariffa della condizione."
            )


class RataIscrizione(models.Model):
    TIPO_MENSILE = RATE_TYPE_MENSILE
    TIPO_PREISCRIZIONE = RATE_TYPE_PREISCRIZIONE
    TIPO_UNICA_SOLUZIONE = RATE_TYPE_UNICA_SOLUZIONE

    iscrizione = models.ForeignKey(
        Iscrizione,
        on_delete=models.CASCADE,
        related_name="rate",
    )
    famiglia = models.ForeignKey(
        Famiglia,
        on_delete=models.PROTECT,
        related_name="rate_iscrizione",
    )
    tipo_rata = models.CharField(max_length=20, choices=RATE_TYPE_CHOICES, default=RATE_TYPE_MENSILE)
    numero_rata = models.PositiveIntegerField()
    mese_riferimento = models.PositiveIntegerField()
    anno_riferimento = models.PositiveIntegerField()
    descrizione = models.CharField(max_length=255, blank=True)
    importo_dovuto = models.DecimalField(max_digits=10, decimal_places=2)
    data_scadenza = models.DateField(blank=True, null=True)
    pagata = models.BooleanField(default=False)
    importo_pagato = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    data_pagamento = models.DateField(blank=True, null=True)
    metodo_pagamento = models.ForeignKey(
        "economia.MetodoPagamento",
        on_delete=models.SET_NULL,
        related_name="rate_iscrizione",
        blank=True,
        null=True,
    )
    credito_applicato = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    altri_sgravi = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    importo_finale = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    note = models.TextField(blank=True)

    class Meta:
        db_table = "economia_rata_iscrizione"
        ordering = ["anno_riferimento", "mese_riferimento", "numero_rata"]
        verbose_name = "Rata iscrizione"
        verbose_name_plural = "Rate iscrizione"

    def __str__(self):
        return f"{self.display_label} - {self.iscrizione}"

    @property
    def is_preiscrizione(self):
        return self.tipo_rata == self.TIPO_PREISCRIZIONE

    @property
    def is_unica_soluzione(self):
        return self.tipo_rata == self.TIPO_UNICA_SOLUZIONE

    @property
    def display_label(self):
        if self.is_preiscrizione:
            return (self.descrizione or "").strip() or f"Preiscrizione AS {self.iscrizione.anno_scolastico}"
        if self.is_unica_soluzione:
            return (self.descrizione or "").strip() or "Retta annuale in unica soluzione"
        return f"Rata {self.numero_rata}"

    @property
    def display_period_label(self):
        if self.is_preiscrizione or self.is_unica_soluzione:
            return self.display_label
        month_label = dict(MONTH_NUMBER_CHOICES).get(self.mese_riferimento, self.mese_riferimento)
        return f"{month_label} {self.anno_riferimento}"

    def calcola_importo_finale(self):
        importo_dovuto = self.importo_dovuto or Decimal("0.00")
        credito_applicato = self.credito_applicato or Decimal("0.00")
        altri_sgravi = self.altri_sgravi or Decimal("0.00")
        return max(importo_dovuto - credito_applicato - altri_sgravi, Decimal("0.00"))

    def has_locking_payment_activity(self):
        importo_pagato = self.importo_pagato or Decimal("0.00")
        importo_finale = self.importo_finale or Decimal("0.00")
        credito_applicato = self.credito_applicato or Decimal("0.00")
        altri_sgravi = self.altri_sgravi or Decimal("0.00")

        if credito_applicato > 0 or altri_sgravi > 0:
            return True

        if self.pagata:
            return True

        if importo_pagato <= 0:
            return False

        if importo_finale <= 0:
            return True

        return importo_pagato < importo_finale

    def clean(self):
        super().clean()

        if self.famiglia_id and self.iscrizione_id and self.famiglia_id != self.iscrizione.studente.famiglia_id:
            raise ValidationError("La famiglia della rata deve coincidere con la famiglia dello studente iscritto.")

        if self.is_preiscrizione:
            self.data_scadenza = None

        self.importo_finale = self.calcola_importo_finale()

    def save(self, *args, **kwargs):
        if self.is_preiscrizione:
            self.data_scadenza = None
        self.importo_finale = self.calcola_importo_finale()
        super().save(*args, **kwargs)


class MovimentoCreditoRetta(models.Model):
    famiglia = models.ForeignKey(
        Famiglia,
        on_delete=models.PROTECT,
        related_name="movimenti_credito_retta",
    )
    studente = models.ForeignKey(
        Studente,
        on_delete=models.SET_NULL,
        related_name="movimenti_credito_retta",
        blank=True,
        null=True,
    )
    iscrizione = models.ForeignKey(
        Iscrizione,
        on_delete=models.SET_NULL,
        related_name="movimenti_credito_retta",
        blank=True,
        null=True,
    )
    rata_iscrizione = models.ForeignKey(
        RataIscrizione,
        on_delete=models.SET_NULL,
        related_name="movimenti_credito_retta",
        blank=True,
        null=True,
    )
    scambio_retta = models.ForeignKey(
        "economia.ScambioRetta",
        on_delete=models.SET_NULL,
        related_name="movimenti_credito_retta",
        blank=True,
        null=True,
    )
    data_movimento = models.DateField()
    tipo_movimento_credito = models.ForeignKey(
        "economia.TipoMovimentoCredito",
        on_delete=models.PROTECT,
        related_name="movimenti_credito_retta",
    )
    importo = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    saldo_progressivo = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    descrizione = models.TextField(blank=True)
    note = models.TextField(blank=True)

    class Meta:
        db_table = "economia_movimento_credito_retta"
        ordering = ["data_movimento", "id"]
        verbose_name = "Movimento credito retta"
        verbose_name_plural = "Movimenti credito retta"

    def __str__(self):
        return f"{self.tipo_movimento_credito} - {self.data_movimento}"
