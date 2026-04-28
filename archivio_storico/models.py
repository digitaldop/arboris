from django.conf import settings
from django.db import models
from django.utils import timezone


class ArchivioAnnoScolastico(models.Model):
    anno_scolastico = models.OneToOneField(
        "scuola.AnnoScolastico",
        on_delete=models.PROTECT,
        related_name="archivio_storico",
    )
    nome_anno_scolastico = models.CharField(max_length=50)
    data_inizio = models.DateField()
    data_fine = models.DateField()
    data_archiviazione = models.DateTimeField(default=timezone.now)
    archiviato_da = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="anni_scolastici_archiviati",
        blank=True,
        null=True,
    )
    note = models.TextField(blank=True)
    totale_snapshot = models.PositiveIntegerField(default=0)
    totale_studenti = models.PositiveIntegerField(default=0)
    totale_famiglie = models.PositiveIntegerField(default=0)
    totale_iscrizioni = models.PositiveIntegerField(default=0)
    totale_rate = models.PositiveIntegerField(default=0)
    totale_osservazioni = models.PositiveIntegerField(default=0)
    totale_documenti = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = "archivio_storico_anno_scolastico"
        ordering = ["-data_inizio", "-id"]
        verbose_name = "Archivio anno scolastico"
        verbose_name_plural = "Archivio anni scolastici"

    def __str__(self):
        return f"Archivio {self.nome_anno_scolastico}"


class TipoSnapshotStorico(models.TextChoices):
    CLASSE = "classe", "Classe"
    FAMIGLIA = "famiglia", "Famiglia"
    FAMILIARE = "familiare", "Familiare"
    STUDENTE = "studente", "Studente"
    ISCRIZIONE = "iscrizione", "Iscrizione"
    RATA = "rata", "Rata"
    OSSERVAZIONE = "osservazione", "Osservazione"
    DOCUMENTO = "documento", "Documento"


class ArchivioSnapshot(models.Model):
    archivio = models.ForeignKey(
        ArchivioAnnoScolastico,
        on_delete=models.CASCADE,
        related_name="snapshot",
    )
    tipo = models.CharField(max_length=30, choices=TipoSnapshotStorico.choices)
    source_app_label = models.CharField(max_length=80)
    source_model = models.CharField(max_length=80)
    source_pk = models.CharField(max_length=80)
    titolo = models.CharField(max_length=255)
    dati = models.JSONField(default=dict)
    ordine = models.PositiveIntegerField(default=0)
    data_creazione = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "archivio_storico_snapshot"
        ordering = ["tipo", "ordine", "titolo", "id"]
        verbose_name = "Snapshot storico"
        verbose_name_plural = "Snapshot storici"
        indexes = [
            models.Index(fields=["archivio", "tipo"], name="arch_stor_snap_arch_tipo_idx"),
            models.Index(fields=["source_app_label", "source_model", "source_pk"], name="arch_stor_snap_source_idx"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["archivio", "tipo", "source_app_label", "source_model", "source_pk"],
                name="unique_archivio_snapshot_source",
            )
        ]

    def __str__(self):
        return f"{self.get_tipo_display()} - {self.titolo}"
