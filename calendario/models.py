from calendar import monthrange
from datetime import date, datetime, timedelta

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Max


def next_category_order_value():
    max_value = CategoriaCalendario.objects.aggregate(max_ordine=Max("ordine"))["max_ordine"]
    return (max_value or 0) + 1


def add_months_preserving_day(base_date, months):
    month_offset = base_date.month - 1 + months
    year = base_date.year + month_offset // 12
    month = (month_offset % 12) + 1
    day = min(base_date.day, monthrange(year, month)[1])
    return date(year, month, day)


def add_years_preserving_day(base_date, years):
    target_year = base_date.year + years
    day = min(base_date.day, monthrange(target_year, base_date.month)[1])
    return date(target_year, base_date.month, day)


SYSTEM_CATEGORY_RATE_DUE = "scadenze_rette"
SYSTEM_CATEGORY_DOCUMENTS = "documenti"
SYSTEM_CATEGORY_SUPPLIER_DUE = "scadenze_fornitori"
SYSTEM_CATEGORY_INTERESTED_FAMILIES = "famiglie_interessate"
SYSTEM_CATEGORY_DEFINITIONS = (
    {
        "key": SYSTEM_CATEGORY_RATE_DUE,
        "name": "Scadenze rette",
        "color": "#be123c",
    },
    {
        "key": SYSTEM_CATEGORY_DOCUMENTS,
        "name": "Documenti",
        "color": "#b45309",
    },
    {
        "key": SYSTEM_CATEGORY_SUPPLIER_DUE,
        "name": "Scadenze fornitori",
        "color": "#0f766e",
    },
    {
        "key": SYSTEM_CATEGORY_INTERESTED_FAMILIES,
        "name": "Famiglie interessate",
        "color": "#417690",
    },
)


def ensure_system_calendar_categories():
    categories = {}

    for definition in SYSTEM_CATEGORY_DEFINITIONS:
        categoria = CategoriaCalendario.objects.filter(chiave_sistema=definition["key"]).first()
        if not categoria:
            categoria = CategoriaCalendario.objects.filter(nome__iexact=definition["name"]).first()

        if categoria:
            updates = []
            if categoria.chiave_sistema != definition["key"]:
                categoria.chiave_sistema = definition["key"]
                updates.append("chiave_sistema")
            if not categoria.attiva:
                categoria.attiva = True
                updates.append("attiva")
            if not categoria.colore:
                categoria.colore = definition["color"]
                updates.append("colore")
            if updates:
                categoria.save(update_fields=updates)
        else:
            categoria = CategoriaCalendario.objects.create(
                nome=definition["name"],
                colore=definition["color"],
                chiave_sistema=definition["key"],
                attiva=True,
            )

        categories[definition["key"]] = categoria

    return categories


class CategoriaCalendario(models.Model):
    nome = models.CharField(max_length=100, unique=True)
    colore = models.CharField(max_length=7, default="#3b82f6")
    chiave_sistema = models.CharField(max_length=50, blank=True, null=True, unique=True)
    ordine = models.PositiveIntegerField(blank=True, null=True)
    attiva = models.BooleanField(default=True)
    data_creazione = models.DateTimeField(auto_now_add=True)
    data_aggiornamento = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "claendario_categoria_calendario"
        ordering = ["ordine", "nome"]
        verbose_name = "Categoria calendario"
        verbose_name_plural = "Categorie calendario"

    def __str__(self):
        return self.nome

    @property
    def is_system_category(self):
        return bool((self.chiave_sistema or "").strip())

    def clean(self):
        super().clean()

        colore = (self.colore or "").strip()
        if len(colore) != 7 or not colore.startswith("#"):
            raise ValidationError("Il colore deve essere nel formato esadecimale #RRGGBB.")

        try:
            int(colore[1:], 16)
        except ValueError as exc:
            raise ValidationError("Il colore deve essere nel formato esadecimale #RRGGBB.") from exc

        if self.is_system_category and not self.attiva:
            raise ValidationError("Le categorie di sistema devono restare attive.")

    def save(self, *args, **kwargs):
        if self.ordine is None:
            self.ordine = next_category_order_value()
        super().save(*args, **kwargs)


class EventoCalendario(models.Model):
    RIPETIZIONE_NESSUNA = "nessuna"
    RIPETIZIONE_GIORNALIERA = "giornaliera"
    RIPETIZIONE_GIORNI_FERIALI = "giorni_feriali"
    RIPETIZIONE_SETTIMANALE = "settimanale"
    RIPETIZIONE_MENSILE = "mensile"
    RIPETIZIONE_ANNUALE = "annuale"
    RIPETIZIONE_CHOICES = (
        (RIPETIZIONE_NESSUNA, "Non si ripete"),
        (RIPETIZIONE_GIORNALIERA, "Giornaliera"),
        (RIPETIZIONE_GIORNI_FERIALI, "Giorni feriali"),
        (RIPETIZIONE_SETTIMANALE, "Settimanale"),
        (RIPETIZIONE_MENSILE, "Mensile"),
        (RIPETIZIONE_ANNUALE, "Annuale"),
    )

    titolo = models.CharField(max_length=200)
    categoria_evento = models.ForeignKey(
        CategoriaCalendario,
        on_delete=models.PROTECT,
        related_name="eventi",
    )
    tipologia = models.CharField(max_length=120, blank=True)
    data_inizio = models.DateField()
    data_fine = models.DateField()
    ora_inizio = models.TimeField(blank=True, null=True)
    ora_fine = models.TimeField(blank=True, null=True)
    intera_giornata = models.BooleanField(default=True)
    ripetizione = models.CharField(max_length=20, choices=RIPETIZIONE_CHOICES, default=RIPETIZIONE_NESSUNA)
    ripeti_ogni_intervallo = models.PositiveSmallIntegerField(
        default=1,
        validators=[MinValueValidator(1), MaxValueValidator(365)],
    )
    ripetizione_numero_occorrenze = models.PositiveSmallIntegerField(
        blank=True,
        null=True,
        validators=[MinValueValidator(1), MaxValueValidator(260)],
    )
    ripetizione_fino_al = models.DateField(blank=True, null=True)
    luogo = models.CharField(max_length=200, blank=True)
    descrizione = models.TextField(blank=True)
    visibile = models.BooleanField(default=True)
    attivo = models.BooleanField(default=True)
    creato_da = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="eventi_calendario_creati",
    )
    aggiornato_da = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="eventi_calendario_aggiornati",
    )
    data_creazione = models.DateTimeField(auto_now_add=True)
    data_aggiornamento = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "claendario_evento_calendario"
        ordering = ["data_inizio", "ora_inizio", "titolo"]
        verbose_name = "Evento calendario"
        verbose_name_plural = "Eventi calendario"

    def __str__(self):
        return self.titolo

    @property
    def durata_minuti(self):
        if self.intera_giornata or not self.ora_inizio or not self.ora_fine:
            return None

        start_dt = datetime.combine(self.data_inizio, self.ora_inizio)
        end_dt = datetime.combine(self.data_fine, self.ora_fine)
        if end_dt <= start_dt:
            return None

        return int((end_dt - start_dt).total_seconds() // 60)

    @property
    def colore_categoria(self):
        return self.categoria_evento.colore if self.categoria_evento_id else "#3b82f6"

    @property
    def is_recurring(self):
        return self.ripetizione != self.RIPETIZIONE_NESSUNA

    @property
    def recurrence_interval_unit_label(self):
        unit_map = {
            self.RIPETIZIONE_GIORNALIERA: ("giorno", "giorni"),
            self.RIPETIZIONE_GIORNI_FERIALI: ("giorno feriale", "giorni feriali"),
            self.RIPETIZIONE_SETTIMANALE: ("settimana", "settimane"),
            self.RIPETIZIONE_MENSILE: ("mese", "mesi"),
            self.RIPETIZIONE_ANNUALE: ("anno", "anni"),
        }
        singular, plural = unit_map.get(self.ripetizione, ("volta", "volte"))
        return singular if (self.ripeti_ogni_intervallo or 1) == 1 else plural

    @property
    def recurrence_summary(self):
        if not self.is_recurring:
            return "Evento singolo"

        interval = self.ripeti_ogni_intervallo or 1
        if self.ripetizione == self.RIPETIZIONE_GIORNALIERA:
            base = "Ogni giorno" if interval == 1 else f"Ogni {interval} giorni"
        elif self.ripetizione == self.RIPETIZIONE_GIORNI_FERIALI:
            base = "Ogni giorno feriale"
        elif self.ripetizione == self.RIPETIZIONE_SETTIMANALE:
            base = "Ogni settimana" if interval == 1 else f"Ogni {interval} settimane"
        elif self.ripetizione == self.RIPETIZIONE_MENSILE:
            base = "Ogni mese" if interval == 1 else f"Ogni {interval} mesi"
        elif self.ripetizione == self.RIPETIZIONE_ANNUALE:
            base = "Ogni anno" if interval == 1 else f"Ogni {interval} anni"
        else:
            base = "Serie ricorrente"

        if self.ripetizione_numero_occorrenze:
            return f"{base} per {self.ripetizione_numero_occorrenze} occorrenze"
        if self.ripetizione_fino_al:
            return f"{base} fino al {self.ripetizione_fino_al.strftime('%d/%m/%Y')}"
        return base

    def get_next_occurrence_start(self, current_start):
        interval = self.ripeti_ogni_intervallo or 1

        if self.ripetizione == self.RIPETIZIONE_GIORNALIERA:
            return current_start + timedelta(days=interval)
        if self.ripetizione == self.RIPETIZIONE_GIORNI_FERIALI:
            next_start = current_start + timedelta(days=1)
            while next_start.weekday() >= 5:
                next_start += timedelta(days=1)
            return next_start
        if self.ripetizione == self.RIPETIZIONE_SETTIMANALE:
            return current_start + timedelta(weeks=interval)
        if self.ripetizione == self.RIPETIZIONE_MENSILE:
            return add_months_preserving_day(current_start, interval)
        if self.ripetizione == self.RIPETIZIONE_ANNUALE:
            return add_years_preserving_day(current_start, interval)
        return None

    def iter_occurrence_ranges(self):
        start_date = self.data_inizio
        end_date = self.data_fine

        if not start_date or not end_date:
            return []

        day_span = (end_date - start_date).days
        occurrence_index = 0
        current_start = start_date

        while True:
            current_end = current_start + timedelta(days=day_span)
            yield {
                "index": occurrence_index,
                "start_date": current_start,
                "end_date": current_end,
            }

            if not self.is_recurring:
                break

            occurrence_index += 1
            if self.ripetizione_numero_occorrenze and occurrence_index >= self.ripetizione_numero_occorrenze:
                break

            next_start = self.get_next_occurrence_start(current_start)
            if not next_start:
                break
            if self.ripetizione_fino_al and next_start > self.ripetizione_fino_al:
                break

            current_start = next_start

    def clean(self):
        super().clean()

        if not self.data_inizio or not self.data_fine:
            return

        if self.data_fine < self.data_inizio:
            raise ValidationError("La data di fine non puo essere precedente alla data di inizio.")

        if self.intera_giornata:
            self.ora_inizio = None
            self.ora_fine = None
        else:
            if not self.ora_inizio:
                raise ValidationError("Inserisci l'orario di inizio per gli eventi non di intera giornata.")

            if not self.ora_fine:
                raise ValidationError("Inserisci l'orario di fine per gli eventi non di intera giornata.")

            if self.data_inizio == self.data_fine and self.ora_fine <= self.ora_inizio:
                raise ValidationError("L'orario di fine deve essere successivo all'orario di inizio.")

            start_dt = datetime.combine(self.data_inizio, self.ora_inizio)
            end_dt = datetime.combine(self.data_fine, self.ora_fine)
            if end_dt <= start_dt:
                raise ValidationError("La fine dell'evento deve essere successiva all'inizio.")

        if self.ripetizione == self.RIPETIZIONE_NESSUNA:
            self.ripeti_ogni_intervallo = 1
            self.ripetizione_numero_occorrenze = None
            self.ripetizione_fino_al = None
            return

        if self.ripetizione == self.RIPETIZIONE_GIORNI_FERIALI:
            self.ripeti_ogni_intervallo = 1
            if self.data_inizio != self.data_fine:
                raise ValidationError("La ripetizione su giorni feriali e disponibile solo per eventi di singolo giorno.")
            if self.data_inizio.weekday() >= 5:
                raise ValidationError("Un evento ripetuto nei giorni feriali deve iniziare in un giorno da lunedi a venerdi.")

        if self.ripetizione not in {
            self.RIPETIZIONE_GIORNALIERA,
            self.RIPETIZIONE_GIORNI_FERIALI,
            self.RIPETIZIONE_SETTIMANALE,
            self.RIPETIZIONE_MENSILE,
            self.RIPETIZIONE_ANNUALE,
        }:
            raise ValidationError("La tipologia di ripetizione selezionata non e supportata.")

        if not self.ripeti_ogni_intervallo:
            raise ValidationError("Indica l'intervallo di ripetizione dell'evento.")

        has_occurrence_limit = bool(self.ripetizione_numero_occorrenze)
        has_date_limit = bool(self.ripetizione_fino_al)

        if has_occurrence_limit == has_date_limit:
            raise ValidationError(
                "Per una serie ricorrente devi indicare solo uno tra numero occorrenze oppure data fine ripetizione."
            )

        if self.ripetizione_numero_occorrenze and self.ripetizione_numero_occorrenze < 2:
            raise ValidationError("Per una serie ricorrente servono almeno 2 occorrenze totali.")

        if self.ripetizione_fino_al and self.ripetizione_fino_al < self.data_inizio:
            raise ValidationError("La data finale della ripetizione non puo essere precedente all'inizio dell'evento.")
