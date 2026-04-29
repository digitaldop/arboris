from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils import timezone


class AnnoScolastico(models.Model):
    nome_anno_scolastico = models.CharField(max_length=50, unique=True)
    data_inizio = models.DateField()
    data_fine = models.DateField()
    attivo = models.BooleanField(default=True)
    note = models.TextField(blank=True)

    class Meta:
        db_table = "scuola_anno_scolastico"
        ordering = ["-data_inizio", "-id"]
        verbose_name = "Anno scolastico"
        verbose_name_plural = "Anni scolastici"
        constraints = [
            models.CheckConstraint(
                check=Q(data_fine__gte=models.F("data_inizio")),
                name="scuola_anno_data_fine_gte_data_inizio",
            )
        ]

    def __str__(self):
        return self.nome_anno_scolastico

    @property
    def is_corrente(self):
        oggi = timezone.localdate()
        return bool(self.data_inizio and self.data_fine and self.data_inizio <= oggi <= self.data_fine)

    @property
    def corrente(self):
        return self.is_corrente

    def clean(self):
        super().clean()

        if not self.data_inizio or not self.data_fine:
            return

        if self.data_fine < self.data_inizio:
            raise ValidationError("La data di fine non può essere precedente alla data di inizio.")

        if self.attivo:
            overlapping_qs = AnnoScolastico.objects.exclude(pk=self.pk).filter(
                attivo=True,
                data_inizio__lte=self.data_fine,
                data_fine__gte=self.data_inizio,
            )
            if overlapping_qs.exists():
                raise ValidationError(
                    "Esiste già un anno scolastico attivo con date sovrapposte. "
                    "Modifica le date o disattiva uno dei due anni scolastici."
                )


class Classe(models.Model):
    nome_classe = models.CharField(max_length=100)
    sezione_classe = models.CharField(max_length=20, blank=True)
    ordine_classe = models.PositiveIntegerField()
    attiva = models.BooleanField(default=True)
    note = models.TextField(blank=True)

    class Meta:
        db_table = "scuola_classe"
        ordering = ["ordine_classe", "nome_classe", "sezione_classe"]
        verbose_name = "Classe"
        verbose_name_plural = "Classi"

    def __str__(self):
        if self.sezione_classe:
            return f"{self.nome_classe} {self.sezione_classe}"
        return self.nome_classe


class GruppoClasse(models.Model):
    nome_gruppo_classe = models.CharField(max_length=150)
    anno_scolastico = models.ForeignKey(
        AnnoScolastico,
        on_delete=models.PROTECT,
        related_name="gruppi_classe",
    )
    classi = models.ManyToManyField(
        Classe,
        related_name="gruppi_classe",
        verbose_name="Classi incluse",
    )
    attivo = models.BooleanField(default=True)
    note = models.TextField(blank=True)

    class Meta:
        db_table = "scuola_gruppo_classe"
        ordering = ["anno_scolastico__data_inizio", "nome_gruppo_classe", "id"]
        verbose_name = "Pluriclasse"
        verbose_name_plural = "Pluriclassi"
        constraints = [
            models.UniqueConstraint(
                fields=["anno_scolastico", "nome_gruppo_classe"],
                name="unique_scuola_gruppo_classe_per_anno",
            )
        ]

    def __str__(self):
        return f"{self.nome_gruppo_classe} - {self.anno_scolastico}"

    @property
    def classi_label(self):
        return ", ".join(str(classe) for classe in self.classi.all())
