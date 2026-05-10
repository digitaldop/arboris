from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Max, Sum

from anagrafica.models import Studente
from scuola.models import AnnoScolastico


def next_order_value(model_cls, field_name="ordine", **filters):
    max_value = model_cls.objects.filter(**filters).aggregate(max_value=Max(field_name))["max_value"]
    return (max_value or 0) + 1


class ServizioExtra(models.Model):
    anno_scolastico = models.ForeignKey(
        AnnoScolastico,
        on_delete=models.PROTECT,
        related_name="servizi_extra",
    )
    nome_servizio = models.CharField(max_length=150)
    ordine = models.PositiveIntegerField(blank=True)
    descrizione = models.TextField(blank=True)
    attiva = models.BooleanField(default=True)
    note = models.TextField(blank=True)

    class Meta:
        db_table = "servizi_extra_servizio"
        ordering = ["-anno_scolastico__data_inizio", "ordine", "nome_servizio"]
        verbose_name = "Servizio extra"
        verbose_name_plural = "Servizi extra"
        constraints = [
            models.UniqueConstraint(
                fields=["anno_scolastico", "nome_servizio"],
                name="unique_servizi_extra_servizio_per_anno",
            )
        ]

    def __str__(self):
        return f"{self.nome_servizio} - {self.anno_scolastico}"

    def save(self, *args, **kwargs):
        if not self.ordine:
            self.ordine = next_order_value(ServizioExtra, anno_scolastico=self.anno_scolastico)
        super().save(*args, **kwargs)


class TariffaServizioExtra(models.Model):
    servizio = models.ForeignKey(
        ServizioExtra,
        on_delete=models.CASCADE,
        related_name="tariffe",
    )
    nome_tariffa = models.CharField(max_length=150)
    rateizzata = models.BooleanField(default=False)
    attiva = models.BooleanField(default=True)
    note = models.TextField(blank=True)

    class Meta:
        db_table = "servizi_extra_tariffa"
        ordering = ["servizio__anno_scolastico__data_inizio", "servizio__nome_servizio", "nome_tariffa"]
        verbose_name = "Tariffa servizio extra"
        verbose_name_plural = "Tariffe servizi extra"
        constraints = [
            models.UniqueConstraint(
                fields=["servizio", "nome_tariffa"],
                name="unique_servizi_extra_tariffa_per_servizio",
            )
        ]

    def __str__(self):
        return f"{self.nome_tariffa} - {self.servizio.nome_servizio}"

    @property
    def totale_importo(self):
        return self.rate_config.aggregate(total=Sum("importo"))["total"] or Decimal("0.00")

    @property
    def numero_rate(self):
        return self.rate_config.count()


class TariffaServizioExtraRata(models.Model):
    tariffa = models.ForeignKey(
        TariffaServizioExtra,
        on_delete=models.CASCADE,
        related_name="rate_config",
    )
    numero_rata = models.PositiveIntegerField()
    descrizione = models.CharField(max_length=255, blank=True)
    importo = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    data_scadenza = models.DateField()

    class Meta:
        db_table = "servizi_extra_tariffa_rata"
        ordering = ["numero_rata", "data_scadenza", "id"]
        verbose_name = "Rata tariffa servizio extra"
        verbose_name_plural = "Rate tariffa servizi extra"
        constraints = [
            models.UniqueConstraint(
                fields=["tariffa", "numero_rata"],
                name="unique_servizi_extra_tariffa_rata_numero",
            )
        ]

    def __str__(self):
        return self.descrizione or f"Rata {self.numero_rata}"

    def clean(self):
        super().clean()
        if self.importo is not None and self.importo < 0:
            raise ValidationError("L'importo della rata non puo essere negativo.")

    def save(self, *args, **kwargs):
        if not self.descrizione:
            self.descrizione = f"Rata {self.numero_rata}"
        super().save(*args, **kwargs)


class IscrizioneServizioExtra(models.Model):
    studente = models.ForeignKey(
        Studente,
        on_delete=models.CASCADE,
        related_name="iscrizioni_servizi_extra",
    )
    servizio = models.ForeignKey(
        ServizioExtra,
        on_delete=models.PROTECT,
        related_name="iscrizioni",
    )
    tariffa = models.ForeignKey(
        TariffaServizioExtra,
        on_delete=models.PROTECT,
        related_name="iscrizioni",
    )
    data_iscrizione = models.DateField(blank=True, null=True)
    data_fine_iscrizione = models.DateField(blank=True, null=True)
    attiva = models.BooleanField(default=True)
    note_amministrative = models.TextField(blank=True)
    note = models.TextField(blank=True)

    class Meta:
        db_table = "servizi_extra_iscrizione"
        ordering = ["-servizio__anno_scolastico__data_inizio", "studente__cognome", "studente__nome"]
        verbose_name = "Iscrizione servizio extra"
        verbose_name_plural = "Iscrizioni servizi extra"
        constraints = [
            models.UniqueConstraint(
                fields=["studente", "servizio"],
                name="unique_servizi_extra_iscrizione_studente_servizio",
            )
        ]

    def __str__(self):
        return f"{self.studente} - {self.servizio.nome_servizio}"

    def build_rate_plan(self):
        if not self.tariffa_id or not self.studente_id:
            return []

        rate_config = list(self.tariffa.rate_config.order_by("numero_rata", "data_scadenza", "id"))
        if not rate_config:
            return []

        piano = []
        for rata_config in rate_config:
            if self.data_fine_iscrizione and rata_config.data_scadenza > self.data_fine_iscrizione:
                continue

            piano.append(
                {
                    "numero_rata": rata_config.numero_rata,
                    "descrizione": rata_config.descrizione or f"Rata {rata_config.numero_rata}",
                    "importo_dovuto": rata_config.importo,
                    "data_scadenza": rata_config.data_scadenza,
                    "importo_finale": rata_config.importo,
                }
            )

        return piano

    def rate_have_payment_activity(self):
        return any(rata.has_locking_payment_activity() for rata in self.rate.all())

    def rate_matches_expected(self, rata, attesa):
        return (
            rata.numero_rata == attesa["numero_rata"]
            and (rata.descrizione or "") == attesa["descrizione"]
            and rata.importo_dovuto == attesa["importo_dovuto"]
            and rata.data_scadenza == attesa["data_scadenza"]
        )

    def rate_plan_matches(self, piano_atteso):
        rate_esistenti = list(self.rate.order_by("numero_rata", "data_scadenza", "id"))
        if len(rate_esistenti) != len(piano_atteso):
            return False

        for rata, attesa in zip(rate_esistenti, piano_atteso):
            if not self.rate_matches_expected(rata, attesa):
                return False

        return True

    def sync_rate_schedule(self):
        if not self.pk:
            return "missing"

        piano_atteso = self.build_rate_plan()
        if not piano_atteso:
            return "missing"

        if not self.rate.exists():
            RataServizioExtra.objects.bulk_create(
                [RataServizioExtra(iscrizione=self, **dati_rata) for dati_rata in piano_atteso]
            )
            return "created"

        if self.rate_have_payment_activity():
            return "locked"

        if self.rate_plan_matches(piano_atteso):
            return "unchanged"

        self.rate.all().delete()
        RataServizioExtra.objects.bulk_create(
            [RataServizioExtra(iscrizione=self, **dati_rata) for dati_rata in piano_atteso]
        )
        return "regenerated"

    def get_riepilogo(self):
        piano = list(self.rate.order_by("numero_rata", "data_scadenza", "id")) if self.pk else []
        if not piano:
            piano = self.build_rate_plan()

        totale_dovuto = Decimal("0.00")
        totale_pagato = Decimal("0.00")
        prossima_scadenza = None

        for rata in piano:
            if isinstance(rata, dict):
                importo_finale = rata.get("importo_finale") or rata.get("importo_dovuto") or Decimal("0.00")
                importo_pagato = Decimal("0.00")
                data_scadenza = rata.get("data_scadenza")
                saldo_aperto = importo_finale
            else:
                importo_finale = rata.importo_finale or rata.importo_dovuto or Decimal("0.00")
                importo_pagato = rata.importo_pagato or Decimal("0.00")
                data_scadenza = rata.data_scadenza
                saldo_aperto = max(importo_finale - importo_pagato, Decimal("0.00"))

            totale_dovuto += importo_finale
            totale_pagato += importo_pagato

            if saldo_aperto > 0 and data_scadenza and (prossima_scadenza is None or data_scadenza < prossima_scadenza):
                prossima_scadenza = data_scadenza

        return {
            "numero_rate": len(piano),
            "totale_dovuto": totale_dovuto,
            "totale_pagato": totale_pagato,
            "totale_rimanente": max(totale_dovuto - totale_pagato, Decimal("0.00")),
            "prossima_scadenza": prossima_scadenza,
        }

    def clean(self):
        super().clean()

        if self.tariffa_id and self.servizio_id and self.tariffa.servizio_id != self.servizio_id:
            raise ValidationError("La tariffa selezionata non appartiene al servizio extra scelto.")

        if self.data_fine_iscrizione and self.data_iscrizione and self.data_fine_iscrizione < self.data_iscrizione:
            raise ValidationError("La data di fine iscrizione non puo essere precedente alla data di iscrizione.")


class RataServizioExtra(models.Model):
    iscrizione = models.ForeignKey(
        IscrizioneServizioExtra,
        on_delete=models.CASCADE,
        related_name="rate",
    )
    numero_rata = models.PositiveIntegerField()
    descrizione = models.CharField(max_length=255, blank=True)
    importo_dovuto = models.DecimalField(max_digits=10, decimal_places=2)
    data_scadenza = models.DateField()
    pagata = models.BooleanField(default=False)
    importo_pagato = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    data_pagamento = models.DateField(blank=True, null=True)
    metodo_pagamento = models.CharField(max_length=100, blank=True)
    importo_finale = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    note = models.TextField(blank=True)

    class Meta:
        db_table = "servizi_extra_rata"
        ordering = ["data_scadenza", "numero_rata", "id"]
        verbose_name = "Rata servizio extra"
        verbose_name_plural = "Rate servizi extra"
        constraints = [
            models.UniqueConstraint(
                fields=["iscrizione", "numero_rata"],
                name="unique_servizi_extra_rata_per_iscrizione",
            )
        ]

    def __str__(self):
        return f"{self.display_label} - {self.iscrizione}"

    @property
    def display_label(self):
        return (self.descrizione or "").strip() or f"Rata {self.numero_rata}"

    def calcola_importo_finale(self):
        return max(self.importo_dovuto or Decimal("0.00"), Decimal("0.00"))

    def has_locking_payment_activity(self):
        return bool(
            self.pagata
            or (self.importo_pagato or Decimal("0.00")) > 0
            or self.data_pagamento
            or (self.metodo_pagamento or "").strip()
        )

    def clean(self):
        super().clean()
        self.importo_finale = self.calcola_importo_finale()

    def save(self, *args, **kwargs):
        self.importo_finale = self.calcola_importo_finale()
        super().save(*args, **kwargs)
