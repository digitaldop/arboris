from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone


class StatoFamigliaInteressata(models.TextChoices):
    NUOVO_CONTATTO = "nuovo_contatto", "Nuovo contatto"
    DA_RICONTATTARE = "da_ricontattare", "Da ricontattare"
    COLLOQUIO_FISSATO = "colloquio_fissato", "Colloquio fissato"
    COLLOQUIO_SVOLTO = "colloquio_svolto", "Colloquio svolto"
    IN_VALUTAZIONE = "in_valutazione", "In valutazione"
    LISTA_ATTESA = "lista_attesa", "Lista attesa"
    ISCRIZIONE_AVVIATA = "iscrizione_avviata", "Iscrizione avviata"
    CONVERTITA = "convertita", "Convertita"
    NON_INTERESSATA = "non_interessata", "Non interessata"
    ARCHIVIATA = "archiviata", "Archiviata"


class PrioritaFamigliaInteressata(models.TextChoices):
    BASSA = "bassa", "Bassa"
    NORMALE = "normale", "Normale"
    ALTA = "alta", "Alta"


class FonteContattoFamigliaInteressata(models.TextChoices):
    SITO = "sito", "Sito web"
    TELEFONO = "telefono", "Telefono"
    EMAIL = "email", "Email"
    OPEN_DAY = "open_day", "Open day"
    PASSAPAROLA = "passaparola", "Passaparola"
    SOCIAL = "social", "Social"
    ALTRO = "altro", "Altro"


class TipoAttivitaFamigliaInteressata(models.TextChoices):
    TELEFONATA = "telefonata", "Telefonata"
    EMAIL = "email", "Email"
    MESSAGGIO = "messaggio", "Messaggio"
    COLLOQUIO = "colloquio", "Colloquio"
    VISITA = "visita", "Visita"
    OPEN_DAY = "open_day", "Open day"
    FOLLOW_UP = "follow_up", "Follow-up"
    NOTA = "nota", "Nota"
    ALTRO = "altro", "Altro"


class StatoAttivitaFamigliaInteressata(models.TextChoices):
    PROGRAMMATA = "programmata", "Programmata"
    COMPLETATA = "completata", "Completata"
    ANNULLATA = "annullata", "Annullata"


class FamigliaInteressata(models.Model):
    nome = models.CharField(
        max_length=200,
        blank=True,
        help_text="Nome libero della famiglia o riferimento usato durante il primo contatto.",
    )
    referente_principale = models.CharField(max_length=200, blank=True)
    telefono = models.CharField(max_length=40, blank=True)
    email = models.EmailField(blank=True)
    fonte_contatto = models.CharField(
        max_length=30,
        choices=FonteContattoFamigliaInteressata.choices,
        default=FonteContattoFamigliaInteressata.ALTRO,
    )
    fonte_note = models.CharField(max_length=255, blank=True)
    stato = models.CharField(
        max_length=30,
        choices=StatoFamigliaInteressata.choices,
        default=StatoFamigliaInteressata.NUOVO_CONTATTO,
        db_index=True,
    )
    priorita = models.CharField(
        max_length=20,
        choices=PrioritaFamigliaInteressata.choices,
        default=PrioritaFamigliaInteressata.NORMALE,
        db_index=True,
    )
    anno_scolastico_interesse = models.ForeignKey(
        "scuola.AnnoScolastico",
        on_delete=models.SET_NULL,
        related_name="famiglie_interessate",
        blank=True,
        null=True,
    )
    classe_eta_interesse = models.CharField(max_length=120, blank=True)
    note = models.TextField(blank=True)
    privacy_consenso = models.BooleanField(default=False)
    convertita_in_famiglia = models.ForeignKey(
        "anagrafica.Famiglia",
        on_delete=models.SET_NULL,
        related_name="origini_interesse",
        blank=True,
        null=True,
    )
    creata_da = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="famiglie_interessate_create",
        blank=True,
        null=True,
    )
    aggiornata_da = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="famiglie_interessate_aggiornate",
        blank=True,
        null=True,
    )
    data_creazione = models.DateTimeField(auto_now_add=True)
    data_aggiornamento = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "famiglie_interessate_famiglia"
        ordering = ["-data_aggiornamento", "-id"]
        verbose_name = "Famiglia interessata"
        verbose_name_plural = "Famiglie interessate"
        indexes = [
            models.Index(fields=["stato", "priorita"], name="fam_int_stato_priorita_idx"),
            models.Index(fields=["fonte_contatto", "data_creazione"], name="fam_int_fonte_data_idx"),
        ]

    def __str__(self):
        return self.nome_display

    @property
    def nome_display(self):
        return (
            (self.nome or "").strip()
            or (self.referente_principale or "").strip()
            or (self.telefono or "").strip()
            or (self.email or "").strip()
            or f"Famiglia interessata #{self.pk or 'nuova'}"
        )

    @property
    def contatto_display(self):
        parts = [part for part in [self.telefono, self.email] if part]
        return " - ".join(parts)

    @property
    def stato_badge_class(self):
        if self.stato in {
            StatoFamigliaInteressata.CONVERTITA,
            StatoFamigliaInteressata.ISCRIZIONE_AVVIATA,
        }:
            return "is-success"
        if self.stato in {
            StatoFamigliaInteressata.NON_INTERESSATA,
            StatoFamigliaInteressata.ARCHIVIATA,
        }:
            return "is-muted"
        if self.stato in {
            StatoFamigliaInteressata.DA_RICONTATTARE,
            StatoFamigliaInteressata.COLLOQUIO_FISSATO,
        }:
            return "is-warning"
        return "is-info"

    @property
    def priorita_badge_class(self):
        if self.priorita == PrioritaFamigliaInteressata.ALTA:
            return "is-warning"
        if self.priorita == PrioritaFamigliaInteressata.BASSA:
            return "is-muted"
        return "is-info"


class ReferenteFamigliaInteressata(models.Model):
    famiglia = models.ForeignKey(
        FamigliaInteressata,
        on_delete=models.CASCADE,
        related_name="referenti",
    )
    nome = models.CharField(max_length=200)
    relazione = models.CharField(max_length=80, blank=True)
    telefono = models.CharField(max_length=40, blank=True)
    email = models.EmailField(blank=True)
    principale = models.BooleanField(default=False)
    note = models.CharField(max_length=255, blank=True)
    data_creazione = models.DateTimeField(auto_now_add=True)
    data_aggiornamento = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "famiglie_interessate_referente"
        ordering = ["-principale", "nome", "id"]
        verbose_name = "Referente famiglia interessata"
        verbose_name_plural = "Referenti famiglie interessate"

    def __str__(self):
        return self.nome


class MinoreInteressato(models.Model):
    famiglia = models.ForeignKey(
        FamigliaInteressata,
        on_delete=models.CASCADE,
        related_name="minori",
    )
    nome = models.CharField(max_length=100, blank=True)
    cognome = models.CharField(max_length=100, blank=True)
    data_nascita = models.DateField(blank=True, null=True)
    eta_indicativa = models.CharField(max_length=80, blank=True)
    classe_eta_interesse = models.CharField(max_length=120, blank=True)
    note = models.CharField(max_length=255, blank=True)
    data_creazione = models.DateTimeField(auto_now_add=True)
    data_aggiornamento = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "famiglie_interessate_minore"
        ordering = ["data_nascita", "cognome", "nome", "id"]
        verbose_name = "Minore interessato"
        verbose_name_plural = "Minori interessati"

    def __str__(self):
        return self.nome_display

    @property
    def nome_display(self):
        value = " ".join([part for part in [self.cognome, self.nome] if part]).strip()
        return value or self.eta_indicativa or "Minore interessato"


class AttivitaFamigliaInteressata(models.Model):
    famiglia = models.ForeignKey(
        FamigliaInteressata,
        on_delete=models.CASCADE,
        related_name="attivita",
    )
    tipo = models.CharField(
        max_length=30,
        choices=TipoAttivitaFamigliaInteressata.choices,
        default=TipoAttivitaFamigliaInteressata.FOLLOW_UP,
        db_index=True,
    )
    titolo = models.CharField(max_length=200, blank=True)
    stato = models.CharField(
        max_length=20,
        choices=StatoAttivitaFamigliaInteressata.choices,
        default=StatoAttivitaFamigliaInteressata.PROGRAMMATA,
        db_index=True,
    )
    data_programmata = models.DateTimeField(blank=True, null=True, db_index=True)
    durata_minuti = models.PositiveSmallIntegerField(default=30)
    data_svolgimento = models.DateTimeField(blank=True, null=True)
    calendarizza = models.BooleanField(default=True)
    luogo = models.CharField(max_length=200, blank=True)
    descrizione = models.TextField(blank=True)
    esito = models.TextField(blank=True)
    assegnata_a = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="attivita_famiglie_interessate_assegnate",
        blank=True,
        null=True,
    )
    creata_da = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="attivita_famiglie_interessate_create",
        blank=True,
        null=True,
    )
    data_creazione = models.DateTimeField(auto_now_add=True)
    data_aggiornamento = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "famiglie_interessate_attivita"
        ordering = ["-data_programmata", "-data_creazione", "-id"]
        verbose_name = "Attivita famiglia interessata"
        verbose_name_plural = "Attivita famiglie interessate"
        indexes = [
            models.Index(fields=["stato", "data_programmata"], name="fam_int_att_stato_data_idx"),
            models.Index(fields=["tipo", "data_programmata"], name="fam_int_att_tipo_data_idx"),
        ]

    def __str__(self):
        return self.calendar_title

    @property
    def calendar_title(self):
        return self.titolo or f"{self.get_tipo_display()} - {self.famiglia.nome_display}"

    @property
    def is_overdue(self):
        return bool(
            self.stato == StatoAttivitaFamigliaInteressata.PROGRAMMATA
            and self.data_programmata
            and self.data_programmata < timezone.now()
        )

    @property
    def calendar_start(self):
        if not self.data_programmata:
            return None
        return timezone.localtime(self.data_programmata)

    @property
    def calendar_end(self):
        start = self.calendar_start
        if not start:
            return None
        return start + timedelta(minutes=self.durata_minuti or 30)
