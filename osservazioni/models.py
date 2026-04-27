from django.conf import settings
from django.db import models
from django.utils import timezone

from anagrafica.models import Studente


class OsservazioneStudente(models.Model):
    studente = models.ForeignKey(
        Studente,
        on_delete=models.CASCADE,
        related_name="osservazioni",
        verbose_name="Studente",
    )
    titolo = models.CharField(max_length=255, blank=True, null=True, verbose_name="Titolo")
    data_inserimento = models.DateField(default=timezone.localdate, verbose_name="Data inserimento")
    testo = models.TextField(verbose_name="Testo")
    creato_da = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="osservazioni_studenti_create",
        blank=True,
        null=True,
        verbose_name="Creato da",
    )
    aggiornato_da = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="osservazioni_studenti_update",
        blank=True,
        null=True,
        verbose_name="Aggiornato da",
    )
    data_creazione = models.DateTimeField(auto_now_add=True)
    data_aggiornamento = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "osservazioni_osservazione_studente"
        ordering = ["data_inserimento", "id"]
        verbose_name = "Osservazione studente"
        verbose_name_plural = "Osservazioni studenti"
        indexes = [
            models.Index(fields=["studente", "data_inserimento", "id"], name="osservazioni_stud_data_idx"),
        ]

    @staticmethod
    def user_display_name(user):
        if not user:
            return "autore non registrato"
        full_name = user.get_full_name().strip()
        return full_name or user.email or user.username

    @property
    def creato_da_label(self):
        return self.user_display_name(self.creato_da)

    @property
    def aggiornato_da_label(self):
        return self.user_display_name(self.aggiornato_da)

    def __str__(self):
        title = (self.titolo or "").strip()
        if title:
            return f"{self.studente} - {title}"
        return f"{self.studente} - {self.data_inserimento:%d/%m/%Y}"
