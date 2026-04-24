from django.core.exceptions import ValidationError
from django.db import models


class AnnoScolastico(models.Model):
    nome_anno_scolastico = models.CharField(max_length=50, unique=True)
    data_inizio = models.DateField()
    data_fine = models.DateField()
    corrente = models.BooleanField(default=False)
    attivo = models.BooleanField(default=True)
    note = models.TextField(blank=True)

    class Meta:
        db_table = "scuola_anno_scolastico"
        ordering = ["-data_inizio", "-id"]
        verbose_name = "Anno scolastico"
        verbose_name_plural = "Anni scolastici"

    def __str__(self):
        return self.nome_anno_scolastico

    def clean(self):
        super().clean()

        if self.data_fine < self.data_inizio:
            raise ValidationError("La data di fine non puo essere precedente alla data di inizio.")

        if self.corrente and AnnoScolastico.objects.exclude(pk=self.pk).filter(corrente=True).exists():
            raise ValidationError("E possibile impostare come corrente un solo anno scolastico.")


class Classe(models.Model):
    nome_classe = models.CharField(max_length=100)
    sezione_classe = models.CharField(max_length=20, blank=True)
    ordine_classe = models.PositiveIntegerField()
    anno_scolastico = models.ForeignKey(
        AnnoScolastico,
        on_delete=models.PROTECT,
        related_name="classi",
    )
    attiva = models.BooleanField(default=True)
    note = models.TextField(blank=True)

    class Meta:
        db_table = "scuola_classe"
        ordering = ["anno_scolastico__data_inizio", "ordine_classe", "nome_classe", "sezione_classe"]
        verbose_name = "Classe"
        verbose_name_plural = "Classi"
        constraints = [
            models.UniqueConstraint(
                fields=["anno_scolastico", "nome_classe", "sezione_classe"],
                name="unique_scuola_classe_per_anno",
            )
        ]

    def __str__(self):
        if self.sezione_classe:
            return f"{self.nome_classe} {self.sezione_classe}"
        return self.nome_classe
