from decimal import Decimal
from datetime import date, datetime

from django.core.exceptions import ValidationError
from django.db import models

from anagrafica.models import Famiglia, Familiare, Studente
from scuola.models import AnnoScolastico


class TariffaScambioRetta(models.Model):
    valore_orario = models.DecimalField(max_digits=10, decimal_places=2)
    definizione = models.CharField(max_length=150, blank=True)
    note = models.TextField(blank=True)

    class Meta:
        db_table = "economia_tariffa_scambio_retta"
        ordering = ["valore_orario", "definizione", "id"]
        verbose_name = "Tariffa scambio retta"
        verbose_name_plural = "Tariffe scambio retta"

    def __str__(self):
        if self.definizione:
            return f"{self.definizione} - {self.valore_orario}"
        return f"{self.valore_orario}"


class ScambioRetta(models.Model):
    familiare = models.ForeignKey(
        Familiare,
        on_delete=models.PROTECT,
        related_name="scambi_retta",
    )
    famiglia = models.ForeignKey(
        Famiglia,
        on_delete=models.PROTECT,
        related_name="scambi_retta",
    )
    studente = models.ForeignKey(
        Studente,
        on_delete=models.PROTECT,
        related_name="scambi_retta",
    )
    anno_scolastico = models.ForeignKey(
        AnnoScolastico,
        on_delete=models.PROTECT,
        related_name="scambi_retta",
    )
    mese_riferimento = models.PositiveSmallIntegerField()
    descrizione = models.TextField(blank=True)
    ore_lavorate = models.DecimalField(max_digits=8, decimal_places=2)
    tariffa_scambio_retta = models.ForeignKey(
        TariffaScambioRetta,
        on_delete=models.PROTECT,
        related_name="scambi_retta",
    )
    importo_maturato = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    approvata = models.BooleanField(default=False)
    contabilizzata = models.BooleanField(default=False)
    note = models.TextField(blank=True)

    class Meta:
        db_table = "economia_scambio_retta"
        ordering = ["-anno_scolastico__data_inizio", "-mese_riferimento", "famiglia__cognome_famiglia", "studente__cognome"]
        verbose_name = "Scambio retta"
        verbose_name_plural = "Scambi retta"

    def __str__(self):
        return f"{self.studente} - mese {self.mese_riferimento} - {self.anno_scolastico}"

    @property
    def periodo_riferimento(self):
        anno_inizio = self.anno_scolastico.data_inizio.year
        mese_inizio = self.anno_scolastico.data_inizio.month
        anno = anno_inizio if self.mese_riferimento >= mese_inizio else anno_inizio + 1
        return date(anno, self.mese_riferimento, 1)

    @property
    def prossimo_periodo(self):
        periodo = self.periodo_riferimento
        if periodo.month == 12:
            return date(periodo.year + 1, 1, 1)
        return date(periodo.year, periodo.month + 1, 1)

    def calcola_importo_maturato(self):
        ore_lavorate = self.ore_lavorate or Decimal("0.00")
        valore_orario = self.tariffa_scambio_retta.valore_orario if self.tariffa_scambio_retta_id else Decimal("0.00")
        return ore_lavorate * valore_orario

    def clean(self):
        super().clean()

        if self.mese_riferimento < 1 or self.mese_riferimento > 12:
            raise ValidationError("Il mese di riferimento deve essere compreso tra 1 e 12.")

        if self.familiare_id and self.famiglia_id and self.familiare.famiglia_id != self.famiglia_id:
            raise ValidationError("Il familiare selezionato non appartiene alla famiglia indicata.")

        if self.studente_id and self.famiglia_id and self.studente.famiglia_id != self.famiglia_id:
            raise ValidationError("Lo studente selezionato non appartiene alla famiglia indicata.")

        if self.familiare_id and not self.familiare.abilitato_scambio_retta:
            raise ValidationError("Il familiare selezionato non e abilitato allo scambio retta.")

        self.importo_maturato = self.calcola_importo_maturato()

    def save(self, *args, **kwargs):
        self.importo_maturato = self.calcola_importo_maturato()
        super().save(*args, **kwargs)

    def get_prossima_rata(self):
        from economia.models import RataIscrizione

        return (
            RataIscrizione.objects.filter(
                iscrizione__studente=self.studente,
                iscrizione__anno_scolastico=self.anno_scolastico,
                tipo_rata=RataIscrizione.TIPO_MENSILE,
                anno_riferimento__gte=self.prossimo_periodo.year,
            )
            .exclude(
                anno_riferimento=self.prossimo_periodo.year,
                mese_riferimento__lt=self.prossimo_periodo.month,
            )
            .order_by("anno_riferimento", "mese_riferimento", "numero_rata")
            .first()
        )


class PrestazioneScambioRetta(models.Model):
    familiare = models.ForeignKey(
        Familiare,
        on_delete=models.PROTECT,
        related_name="prestazioni_scambio_retta",
    )
    famiglia = models.ForeignKey(
        Famiglia,
        on_delete=models.PROTECT,
        related_name="prestazioni_scambio_retta",
    )
    studente = models.ForeignKey(
        Studente,
        on_delete=models.PROTECT,
        related_name="prestazioni_scambio_retta",
        blank=True,
        null=True,
    )
    anno_scolastico = models.ForeignKey(
        AnnoScolastico,
        on_delete=models.PROTECT,
        related_name="prestazioni_scambio_retta",
    )
    data = models.DateField()
    ora_ingresso = models.TimeField(blank=True, null=True)
    ora_uscita = models.TimeField(blank=True, null=True)
    descrizione = models.CharField(max_length=255, verbose_name="Mansione svolta")
    ore_lavorate = models.DecimalField(max_digits=6, decimal_places=2)
    tariffa_scambio_retta = models.ForeignKey(
        TariffaScambioRetta,
        on_delete=models.PROTECT,
        related_name="prestazioni_scambio_retta",
    )
    importo_maturato = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    note = models.TextField(blank=True)

    class Meta:
        db_table = "economia_prestazione_scambio_retta"
        ordering = ["-data", "-ora_ingresso", "-id"]
        verbose_name = "Prestazione scambio retta"
        verbose_name_plural = "Prestazioni scambio retta"

    def __str__(self):
        return f"{self.familiare} - {self.data.strftime('%d/%m/%Y')}"

    @property
    def fascia_oraria_label(self):
        if self.ora_ingresso and self.ora_uscita:
            return f"{self.ora_ingresso.strftime('%H:%M')} - {self.ora_uscita.strftime('%H:%M')}"
        return "Ore inserite manualmente"

    @property
    def ha_orari_registrati(self):
        return bool(self.ora_ingresso and self.ora_uscita)

    def resolve_anno_scolastico_da_data(self):
        if not self.data:
            return None

        return (
            AnnoScolastico.objects.filter(data_inizio__lte=self.data, data_fine__gte=self.data)
            .order_by("-data_inizio", "-id")
            .first()
        )

    def calcola_ore_lavorate(self):
        if not (self.ora_ingresso and self.ora_uscita):
            return (self.ore_lavorate or Decimal("0.00")).quantize(Decimal("0.01"))

        ingresso = datetime.combine(date.min, self.ora_ingresso)
        uscita = datetime.combine(date.min, self.ora_uscita)
        minuti = Decimal((uscita - ingresso).total_seconds()) / Decimal("60")
        return (minuti / Decimal("60")).quantize(Decimal("0.01"))

    def calcola_importo_maturato(self):
        ore_lavorate = self.ore_lavorate or Decimal("0.00")
        valore_orario = self.tariffa_scambio_retta.valore_orario if self.tariffa_scambio_retta_id else Decimal("0.00")
        return (ore_lavorate * valore_orario).quantize(Decimal("0.01"))

    def clean(self):
        super().clean()
        errors = {}

        if self.familiare_id:
            self.famiglia = self.familiare.famiglia

            if not self.familiare.abilitato_scambio_retta:
                errors["familiare"] = "Il familiare selezionato non e abilitato allo scambio retta."

        if self.studente_id and self.famiglia_id and self.studente.famiglia_id != self.famiglia_id:
            errors["studente"] = "Lo studente selezionato non appartiene alla famiglia del familiare."

        anno_risolto = self.resolve_anno_scolastico_da_data()
        if self.data:
            if not anno_risolto:
                errors["data"] = "La data selezionata non rientra in nessun anno scolastico configurato."
            elif self.anno_scolastico_id and self.anno_scolastico_id != anno_risolto.id:
                errors["data"] = "La data selezionata non appartiene all'anno scolastico associato alla prestazione."
            else:
                self.anno_scolastico = anno_risolto

        if self.ora_ingresso and not self.ora_uscita:
            errors["ora_uscita"] = "Inserisci anche l'ora di uscita."
        elif self.ora_uscita and not self.ora_ingresso:
            errors["ora_ingresso"] = "Inserisci anche l'ora di ingresso."
        elif self.ora_ingresso and self.ora_uscita:
            if self.ora_uscita <= self.ora_ingresso:
                errors["ora_uscita"] = "L'ora di uscita deve essere successiva all'ora di ingresso."
            else:
                self.ore_lavorate = self.calcola_ore_lavorate()

        if not (self.ora_ingresso and self.ora_uscita):
            if not self.ore_lavorate or self.ore_lavorate <= 0:
                errors["ore_lavorate"] = "Inserisci il totale ore oppure compila ora di ingresso e ora di uscita."
            else:
                self.ore_lavorate = Decimal(self.ore_lavorate).quantize(Decimal("0.01"))

        self.importo_maturato = self.calcola_importo_maturato()

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        if self.familiare_id:
            self.famiglia = self.familiare.famiglia

        if self.data and not self.anno_scolastico_id:
            anno_risolto = self.resolve_anno_scolastico_da_data()
            if anno_risolto:
                self.anno_scolastico = anno_risolto

        if self.ora_ingresso and self.ora_uscita and self.ora_uscita > self.ora_ingresso:
            self.ore_lavorate = self.calcola_ore_lavorate()
        else:
            self.ore_lavorate = (self.ore_lavorate or Decimal("0.00")).quantize(Decimal("0.01"))

        self.importo_maturato = self.calcola_importo_maturato()
        super().save(*args, **kwargs)
