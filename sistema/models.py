from pathlib import Path
from urllib.parse import quote, quote_plus

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.contrib.auth.models import User
from django.core.cache import cache
from django.db import models
from django.db.models import Max
from django.template.defaultfilters import filesizeformat
from django.utils import timezone
from django.utils.text import get_valid_filename

from anagrafica.models import Indirizzo
from .terminology import get_educator_terminology, get_family_member_terminology, get_student_terminology


def next_order_value(model_cls):
    max_value = model_cls.objects.aggregate(max_ordine=Max("ordine"))["max_ordine"]
    return (max_value or 0) + 1


def sistema_database_backup_upload_to(_instance, filename):
    prefix = (getattr(settings, "DATABASE_BACKUPS_UPLOAD_PREFIX", "db_backups") or "db_backups").strip().strip("/")
    safe_name = get_valid_filename(Path(filename or "backup.sql.gz").name) or "backup.sql.gz"
    return f"{prefix}/{timezone.localtime():%Y/%m}/{safe_name}"


class Scuola(models.Model):
    nome_scuola = models.CharField(max_length=200)
    ragione_sociale = models.CharField(max_length=200, blank=True)
    indirizzo_sede_legale = models.ForeignKey(
        Indirizzo,
        on_delete=models.SET_NULL,
        related_name="scuole_sede_legale",
        blank=True,
        null=True,
    )
    indirizzo_operativo = models.ForeignKey(
        Indirizzo,
        on_delete=models.SET_NULL,
        related_name="scuole_sede_operativa",
        blank=True,
        null=True,
    )
    indirizzo_operativo_diverso = models.BooleanField(default=False)
    codice_fiscale = models.CharField(max_length=16, blank=True)
    partita_iva = models.CharField(max_length=11, blank=True)
    sito_web = models.URLField(blank=True)
    note = models.TextField(blank=True)
    data_creazione = models.DateTimeField(auto_now_add=True)
    data_aggiornamento = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "sistema_scuola"
        ordering = ["nome_scuola"]
        verbose_name = "Scuola"
        verbose_name_plural = "Scuola"

    def __str__(self):
        return self.nome_scuola

    def clean(self):
        super().clean()
        if Scuola.objects.exclude(pk=self.pk).exists():
            raise ValidationError("È possibile configurare una sola scuola.")
        if not self.indirizzo_operativo_diverso:
            self.indirizzo_operativo = None

    @property
    def indirizzo_header(self):
        if self.indirizzo_operativo_diverso and self.indirizzo_operativo:
            return self.indirizzo_operativo
        return self.indirizzo_sede_legale

    @property
    def telefono_header(self):
        record = self.telefoni.order_by("ordine", "id").first()
        return record.telefono if record else ""

    @property
    def telefono_header_formattato(self):
        from anagrafica.utils import format_phone_number

        raw = self.telefono_header
        if not raw:
            return ""
        return format_phone_number(raw) or raw

    @property
    def email_header(self):
        record = self.email.order_by("ordine", "id").first()
        return record.email if record else ""

    @property
    def indirizzo_header_label(self):
        return self.indirizzo_header.label_full() if self.indirizzo_header else ""

    @property
    def header_info_line(self):
        parti = []
        if self.indirizzo_header_label:
            parti.append(self.indirizzo_header_label)
        if self.telefono_header:
            parti.append(self.telefono_header)
        if self.email_header:
            parti.append(self.email_header)
        return " - ".join(parti)

    @property
    def telefono_header_whatsapp_url(self):
        if not self.telefono_header:
            return ""

        digits = "".join(ch for ch in self.telefono_header if ch.isdigit())
        if not digits:
            return ""

        if self.telefono_header.strip().startswith("+"):
            target = f"+{digits}"
        else:
            target = digits

        return f"https://wa.me/{quote(target.lstrip('+'))}"

    @property
    def email_header_mailto_url(self):
        if not self.email_header:
            return ""
        return f"mailto:{self.email_header}"


class ScuolaSocial(models.Model):
    scuola = models.ForeignKey(
        Scuola,
        on_delete=models.CASCADE,
        related_name="socials",
    )
    nome_social = models.CharField(max_length=100)
    link = models.URLField()
    ordine = models.IntegerField(blank=True, null=True)

    class Meta:
        db_table = "sistema_scuola_social"
        ordering = ["ordine", "nome_social"]
        verbose_name = "Social scuola"
        verbose_name_plural = "Social scuola"

    def __str__(self):
        return self.nome_social

    def save(self, *args, **kwargs):
        if self.ordine is None:
            self.ordine = next_order_value(ScuolaSocial)
        super().save(*args, **kwargs)


class ScuolaTelefono(models.Model):
    scuola = models.ForeignKey(
        Scuola,
        on_delete=models.CASCADE,
        related_name="telefoni",
    )
    descrizione = models.CharField(max_length=100)
    telefono = models.CharField(max_length=30)
    ordine = models.IntegerField(blank=True, null=True)

    class Meta:
        db_table = "sistema_scuola_telefono"
        ordering = ["ordine", "descrizione"]
        verbose_name = "Telefono scuola"
        verbose_name_plural = "Telefoni scuola"

    def __str__(self):
        return self.descrizione

    def save(self, *args, **kwargs):
        if self.ordine is None:
            self.ordine = next_order_value(ScuolaTelefono)
        super().save(*args, **kwargs)


class ScuolaEmail(models.Model):
    scuola = models.ForeignKey(
        Scuola,
        on_delete=models.CASCADE,
        related_name="email",
    )
    descrizione = models.CharField(max_length=100)
    email = models.EmailField()
    ordine = models.IntegerField(blank=True, null=True)

    class Meta:
        db_table = "sistema_scuola_email"
        ordering = ["ordine", "descrizione"]
        verbose_name = "Email scuola"
        verbose_name_plural = "Email scuola"

    def __str__(self):
        return self.descrizione

    def save(self, *args, **kwargs):
        if self.ordine is None:
            self.ordine = next_order_value(ScuolaEmail)
        super().save(*args, **kwargs)


class TerminologiaStudente(models.TextChoices):
    STUDENTE = "studente", "STUDENTE"
    ALUNNO = "alunno", "ALUNNO"
    BAMBINO = "bambino", "BAMBINO"


class TerminologiaFamiliare(models.TextChoices):
    FAMILIARE = "familiare", "FAMILIARE"
    GENITORE = "genitore", "GENITORE"
    PARENTE = "parente", "PARENTE"


class TerminologiaEducatore(models.TextChoices):
    EDUCATORE = "educatore", "EDUCATORE"
    MAESTRO = "maestro", "MAESTRO"
    INSEGNANTE = "insegnante", "INSEGNANTE"


class GoogleFontChoice(models.TextChoices):
    MANROPE = "manrope", "Manrope"
    DM_SANS = "dm_sans", "DM Sans"
    INTER = "inter", "Inter"
    NUNITO_SANS = "nunito_sans", "Nunito Sans"
    PLUS_JAKARTA_SANS = "plus_jakarta_sans", "Plus Jakarta Sans"
    POPPINS = "poppins", "Poppins"
    WORK_SANS = "work_sans", "Work Sans"
    SOURCE_SANS_3 = "source_sans_3", "Source Sans 3"
    OUTFIT = "outfit", "Outfit"
    RUBIK = "rubik", "Rubik"


GOOGLE_FONT_LIBRARY = {
    GoogleFontChoice.MANROPE: {
        "family": "Manrope",
        "weights": "400;500;600;700;800",
    },
    GoogleFontChoice.DM_SANS: {
        "family": "DM Sans",
        "weights": "400;500;600;700;800",
    },
    GoogleFontChoice.INTER: {
        "family": "Inter",
        "weights": "400;500;600;700;800",
    },
    GoogleFontChoice.NUNITO_SANS: {
        "family": "Nunito Sans",
        "weights": "400;500;600;700;800",
    },
    GoogleFontChoice.PLUS_JAKARTA_SANS: {
        "family": "Plus Jakarta Sans",
        "weights": "400;500;600;700;800",
    },
    GoogleFontChoice.POPPINS: {
        "family": "Poppins",
        "weights": "400;500;600;700;800",
    },
    GoogleFontChoice.WORK_SANS: {
        "family": "Work Sans",
        "weights": "400;500;600;700;800",
    },
    GoogleFontChoice.SOURCE_SANS_3: {
        "family": "Source Sans 3",
        "weights": "400;500;600;700;800",
    },
    GoogleFontChoice.OUTFIT: {
        "family": "Outfit",
        "weights": "400;500;600;700;800",
    },
    GoogleFontChoice.RUBIK: {
        "family": "Rubik",
        "weights": "400;500;600;700;800",
    },
}

DEFAULT_SITE_BODY_FONT = GoogleFontChoice.MANROPE
DEFAULT_SITE_HEADING_FONT = GoogleFontChoice.MANROPE


class CronologiaRetentionPeriodo(models.IntegerChoices):
    SEI_MESI = 6, "6 mesi"
    DODICI_MESI = 12, "12 mesi"
    VENTIQUATTRO_MESI = 24, "24 mesi"
    TRENTASEI_MESI = 36, "36 mesi"
    SEMPRE = 0, "Conserva sempre"


class PhoneDisplayFormat(models.TextChoices):
    """Solo visualizzazione; in database i numeri sono senza spazi (vedi anagrafica.utils)."""

    IT_PLUS_N3_2_2_3 = (
        "it_plus_n3_2_2_3",
        "+ prefisso (se presente) 345 67 89 675",
    )
    IT_PLUS_N3_3_2_2 = (
        "it_plus_n3_3_2_2",
        "+ prefisso (se presente) 345 678 96 75",
    )
    IT_PLUS_N10 = (
        "it_plus_n10",
        "+ prefisso (se presente) 3456789675",
    )


class GestioneIscrizioneCorsoAnno(models.TextChoices):
    MESE_ISCRIZIONE_INTERO = "mese_iscrizione_intero", "Mese di iscrizione incluso per intero"
    MESE_SUCCESSIVO_DOPO_SOGLIA = "mese_successivo_dopo_soglia", "Mese successivo dopo soglia"
    PRO_RATA_GIORNALIERO = "pro_rata_giornaliero", "Pro-rata giornaliero"


MODULE_SETTINGS_CACHE_KEY = "sistema:module_enabled_map"
GENERAL_SETTINGS_CACHE_KEY = "sistema:general_settings"

MODULE_TOGGLE_DEFINITIONS = [
    {
        "key": "anagrafica",
        "field": "modulo_anagrafica_attivo",
        "label": "Anagrafica",
        "description": "Famiglie, familiari, studenti, documenti e ricerche anagrafiche.",
        "icon": "family",
        "tone": "blue",
    },
    {
        "key": "famiglie_interessate",
        "field": "modulo_famiglie_interessate_attivo",
        "label": "Famiglie interessate",
        "description": "Prospect, contatti pre-iscrizione, bambini interessati e follow-up.",
        "icon": "supplier",
        "tone": "green",
    },
    {
        "key": "economia",
        "field": "modulo_economia_attivo",
        "label": "Economia",
        "description": "Rette, verifiche pagamenti, fondo accantonamento e impostazioni rette.",
        "icon": "coins",
        "tone": "emerald",
    },
    {
        "key": "calendario",
        "field": "modulo_calendario_attivo",
        "label": "Calendario",
        "description": "Agenda, eventi, categorie e scadenze collegate al calendario.",
        "icon": "calendar",
        "tone": "amber",
    },
    {
        "key": "gestione_finanziaria",
        "field": "modulo_gestione_finanziaria_attivo",
        "label": "Gestione finanziaria",
        "description": "Banche, movimenti, fornitori, fatture e riconciliazioni.",
        "icon": "finance",
        "tone": "sky",
    },
    {
        "key": "gestione_amministrativa",
        "field": "modulo_gestione_amministrativa_attivo",
        "label": "Dipendenti e collaboratori",
        "description": "Dipendenti, contratti, buste paga e simulazioni costo.",
        "icon": "user",
        "tone": "rose",
    },
    {
        "key": "servizi_extra",
        "field": "modulo_servizi_extra_attivo",
        "label": "Servizi extra",
        "description": "Servizi opzionali, iscrizioni, tariffe e rate dedicate.",
        "icon": "briefcase",
        "tone": "violet",
    },
]

MODULE_TOGGLE_FIELDS = {
    definition["key"]: definition["field"]
    for definition in MODULE_TOGGLE_DEFINITIONS
}
MODULES_ALWAYS_ENABLED = {"sistema"}


def get_module_enabled_map(general_settings=None):
    impostazioni = general_settings or SistemaImpostazioniGenerali.objects.first()
    enabled_map = {module_name: True for module_name in MODULES_ALWAYS_ENABLED}
    for definition in MODULE_TOGGLE_DEFINITIONS:
        enabled_map[definition["key"]] = bool(
            getattr(impostazioni, definition["field"], True)
            if impostazioni
            else True
        )
    return enabled_map


def get_google_font_config(font_key):
    return GOOGLE_FONT_LIBRARY.get(font_key, GOOGLE_FONT_LIBRARY[DEFAULT_SITE_BODY_FONT])


def get_google_font_css_stack(font_key):
    family = get_google_font_config(font_key)["family"]
    return f'"{family}", Arial, Helvetica, sans-serif'


def build_google_fonts_url(font_keys):
    unique_keys = []
    for font_key in font_keys:
        normalized_key = font_key or DEFAULT_SITE_BODY_FONT
        if normalized_key not in unique_keys:
            unique_keys.append(normalized_key)

    family_params = []
    for font_key in unique_keys:
        font_config = get_google_font_config(font_key)
        family_name = quote_plus(font_config["family"])
        family_params.append(f"family={family_name}:wght@{font_config['weights']}")

    return f"https://fonts.googleapis.com/css2?{'&'.join(family_params)}&display=swap"


def get_site_font_settings(general_settings=None):
    body_font_key = getattr(general_settings, "font_principale", DEFAULT_SITE_BODY_FONT)
    heading_font_key = getattr(general_settings, "font_titoli", DEFAULT_SITE_HEADING_FONT)
    body_font_config = get_google_font_config(body_font_key)
    heading_font_config = get_google_font_config(heading_font_key)

    return {
        "body_font_key": body_font_key,
        "heading_font_key": heading_font_key,
        "body_font_label": body_font_config["family"],
        "heading_font_label": heading_font_config["family"],
        "body_css_stack": get_google_font_css_stack(body_font_key),
        "heading_css_stack": get_google_font_css_stack(heading_font_key),
        "google_fonts_url": build_google_fonts_url([body_font_key, heading_font_key]),
    }


class SistemaImpostazioniGenerali(models.Model):
    terminologia_studente = models.CharField(
        max_length=20,
        choices=TerminologiaStudente.choices,
        default=TerminologiaStudente.STUDENTE,
        help_text=(
            "Scegli il termine da visualizzare nel software per riferirti agli studenti. "
            "La modifica agisce solo sulle etichette mostrate a video."
        ),
    )
    terminologia_familiare = models.CharField(
        max_length=20,
        choices=TerminologiaFamiliare.choices,
        default=TerminologiaFamiliare.FAMILIARE,
        help_text="Scegli la dicitura da visualizzare per i familiari nelle interfacce anagrafiche.",
    )
    terminologia_educatore = models.CharField(
        max_length=20,
        choices=TerminologiaEducatore.choices,
        default=TerminologiaEducatore.EDUCATORE,
        help_text="Scegli la dicitura da visualizzare per educatori, maestri o insegnanti.",
    )
    mostra_dashboard_prossimo_anno_scolastico = models.BooleanField(
        default=False,
        help_text=(
            "Quando attiva, la dashboard mostra anche i riepiloghi generali ed economici "
            "del prossimo anno scolastico configurato."
        ),
    )
    osservazioni_solo_autori_visualizzazione = models.BooleanField(
        default=False,
        help_text=(
            "Quando attiva, le osservazioni collegate agli studenti sono visibili solo "
            "all'autore, salvo amministratori e superuser."
        ),
    )
    osservazioni_solo_autori_modifica = models.BooleanField(
        default=True,
        help_text=(
            "Quando attiva, solo l'autore puo modificare o cancellare le proprie osservazioni, "
            "salvo amministratori e superuser."
        ),
    )
    interfaccia_colorata_attiva = models.BooleanField(
        default=True,
        help_text=(
            "Quando attiva usa accenti colore morbidi per differenziare moduli, icone e azioni principali. "
            "Disattivala per un'interfaccia piu uniforme."
        ),
    )
    interfaccia_professionale_attiva = models.BooleanField(
        default=False,
        help_text=(
            "Quando attiva applica un layout piu SaaS e professionale: sidebar lineare, "
            "tabelle piu compatte, card meno arrotondate e spaziature piu operative."
        ),
    )
    stile_streamline_attivo = models.BooleanField(
        default=False,
        help_text=(
            "Quando attivo usa icone emozionali multicolore per dashboard, riepiloghi e intestazioni. "
            "Le icone funzionali di menu, pulsanti, tabelle e form restano lineari."
        ),
    )
    stile_iconscout_3d_attivo = models.BooleanField(
        default=False,
        help_text=(
            "Quando attivo usa icone emozionali in stile 3D per dashboard, riepiloghi e intestazioni. "
            "Se attivo insieme allo Streamline, lo stile 3D ha priorita sulle icone principali."
        ),
    )
    font_principale = models.CharField(
        max_length=40,
        choices=GoogleFontChoice.choices,
        default=DEFAULT_SITE_BODY_FONT,
        help_text="Scegli il font Google da usare per il testo principale del software.",
    )
    font_titoli = models.CharField(
        max_length=40,
        choices=GoogleFontChoice.choices,
        default=DEFAULT_SITE_HEADING_FONT,
        help_text="Scegli il font Google da usare per titoli, intestazioni e sezioni del software.",
    )
    formato_visualizzazione_telefono = models.CharField(
        max_length=32,
        choices=PhoneDisplayFormat.choices,
        default=PhoneDisplayFormat.IT_PLUS_N3_2_2_3,
        help_text="Come mostrare i numeri di telefono in elenchi e schede (in archivio restano senza spazi).",
    )
    cronologia_retention_mesi = models.PositiveSmallIntegerField(
        choices=CronologiaRetentionPeriodo.choices,
        default=CronologiaRetentionPeriodo.VENTIQUATTRO_MESI,
        help_text=(
            "Periodo di conservazione della cronologia operazioni. Le operazioni piu vecchie "
            "vengono rimosse automaticamente."
        ),
    )
    gestione_iscrizione_corso_anno = models.CharField(
        max_length=40,
        choices=GestioneIscrizioneCorsoAnno.choices,
        default=GestioneIscrizioneCorsoAnno.MESE_ISCRIZIONE_INTERO,
        help_text=(
            "Definisce come calcolare le rette quando lo studente viene iscritto dopo "
            "il mese iniziale previsto dalla condizione di iscrizione."
        ),
    )
    giorno_soglia_iscrizione_corso_anno = models.PositiveSmallIntegerField(
        default=15,
        validators=[MinValueValidator(1), MaxValueValidator(31)],
        help_text=(
            "Usato solo con la regola 'mese successivo dopo soglia': se l'iscrizione "
            "avviene dopo questo giorno, la prima retta parte dal mese successivo."
        ),
    )
    modulo_anagrafica_attivo = models.BooleanField(
        default=True,
        help_text="Attiva o disattiva globalmente il modulo Anagrafica.",
    )
    modulo_famiglie_interessate_attivo = models.BooleanField(
        default=True,
        help_text="Attiva o disattiva globalmente il modulo Famiglie interessate.",
    )
    modulo_economia_attivo = models.BooleanField(
        default=True,
        help_text="Attiva o disattiva globalmente il modulo Economia.",
    )
    modulo_calendario_attivo = models.BooleanField(
        default=True,
        help_text="Attiva o disattiva globalmente il modulo Calendario.",
    )
    modulo_gestione_finanziaria_attivo = models.BooleanField(
        default=True,
        help_text="Attiva o disattiva globalmente il modulo Gestione finanziaria.",
    )
    modulo_gestione_amministrativa_attivo = models.BooleanField(
        default=True,
        help_text="Attiva o disattiva globalmente il modulo Dipendenti e collaboratori.",
    )
    gestione_dipendenti_dettagliata_attiva = models.BooleanField(
        default=False,
        help_text=(
            "Se attiva mostra parametri payroll, simulazioni costo dettagliate e campi contrattuali tecnici. "
            "Se disattiva mantiene una gestione semplificata con dipendenti, contratti e buste paga."
        ),
    )
    modulo_servizi_extra_attivo = models.BooleanField(
        default=True,
        help_text="Attiva o disattiva globalmente il modulo Servizi extra.",
    )
    data_creazione = models.DateTimeField(auto_now_add=True)
    data_aggiornamento = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "sistema_impostazioni_generali"
        ordering = ["id"]
        verbose_name = "Impostazioni generali"
        verbose_name_plural = "Impostazioni generali"

    def __str__(self):
        return "Impostazioni generali"

    def clean(self):
        super().clean()
        if SistemaImpostazioniGenerali.objects.exclude(pk=self.pk).exists():
            raise ValidationError("E possibile configurare un solo record di impostazioni generali.")

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        cache.delete_many([GENERAL_SETTINGS_CACHE_KEY, MODULE_SETTINGS_CACHE_KEY])

    def delete(self, *args, **kwargs):
        result = super().delete(*args, **kwargs)
        cache.delete_many([GENERAL_SETTINGS_CACHE_KEY, MODULE_SETTINGS_CACHE_KEY])
        return result

    @property
    def student_terminology(self):
        return get_student_terminology(self.terminologia_studente)

    @property
    def family_member_terminology(self):
        return get_family_member_terminology(self.terminologia_familiare)

    @property
    def educator_terminology(self):
        return get_educator_terminology(self.terminologia_educatore)

    @property
    def termine_studente_singolare(self):
        return self.student_terminology["selected_singular"]

    @property
    def termine_studente_plurale(self):
        return self.student_terminology["selected_plural"]

    @property
    def termine_familiare_singolare(self):
        return self.family_member_terminology["selected_singular"]

    @property
    def termine_familiare_plurale(self):
        return self.family_member_terminology["selected_plural"]

    @property
    def termine_educatore_singolare(self):
        return self.educator_terminology["selected_singular"]

    @property
    def termine_educatore_plurale(self):
        return self.educator_terminology["selected_plural"]


class FrequenzaBackupAutomatico(models.TextChoices):
    DISATTIVATO = "", "Disattivato"
    GIORNALIERO = "giornaliero", "Giornaliero"
    SETTIMANALE = "settimanale", "Settimanale"
    MENSILE = "mensile", "Mensile"


class TipoBackupDatabase(models.TextChoices):
    MANUALE = "manuale", "Manuale"
    AUTOMATICO = "automatico", "Automatico"
    SICUREZZA_RIPRISTINO = "sicurezza_ripristino", "Sicurezza pre-ripristino"


class SistemaBackupDatabaseConfigurazione(models.Model):
    frequenza_backup_automatico = models.CharField(
        max_length=20,
        choices=FrequenzaBackupAutomatico.choices,
        default=FrequenzaBackupAutomatico.DISATTIVATO,
        blank=True,
        help_text="Scegli la frequenza con cui il sistema deve generare automaticamente i backup del database.",
    )
    ultimo_backup_automatico_at = models.DateTimeField(blank=True, null=True)
    ultimo_errore_backup_automatico = models.TextField(blank=True)
    backup_automatico_in_corso = models.BooleanField(default=False)
    backup_automatico_avviato_at = models.DateTimeField(blank=True, null=True)
    data_creazione = models.DateTimeField(auto_now_add=True)
    data_aggiornamento = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "sistema_backup_database_configurazione"
        ordering = ["id"]
        verbose_name = "Configurazione backup database"
        verbose_name_plural = "Configurazioni backup database"

    def __str__(self):
        return "Configurazione backup database"

    def clean(self):
        super().clean()
        if SistemaBackupDatabaseConfigurazione.objects.exclude(pk=self.pk).exists():
            raise ValidationError("E possibile configurare un solo record di backup database.")

    @property
    def frequenza_label(self):
        return self.get_frequenza_backup_automatico_display() or "Disattivato"

    @property
    def has_recent_error(self):
        return bool(self.ultimo_errore_backup_automatico.strip())


class SistemaDatabaseBackup(models.Model):
    tipo_backup = models.CharField(
        max_length=30,
        choices=TipoBackupDatabase.choices,
        default=TipoBackupDatabase.MANUALE,
    )
    file_backup = models.FileField(upload_to=sistema_database_backup_upload_to)
    nome_file = models.CharField(max_length=255)
    dimensione_file_bytes = models.BigIntegerField(default=0)
    creato_da = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="backup_database_creati",
        blank=True,
        null=True,
    )
    note = models.TextField(blank=True)
    data_creazione = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "sistema_database_backup"
        ordering = ["-data_creazione", "-id"]
        verbose_name = "Backup database"
        verbose_name_plural = "Backup database"

    def __str__(self):
        return self.nome_file

    @property
    def dimensione_label(self):
        return filesizeformat(self.dimensione_file_bytes or 0)

    @property
    def tipo_label(self):
        return self.get_tipo_backup_display()

    @property
    def data_creazione_label(self):
        if not self.data_creazione:
            return ""
        local_value = timezone.localtime(self.data_creazione)
        return local_value.strftime("%d/%m/%Y %H:%M")


class StatoRipristinoDatabase(models.TextChoices):
    IN_ATTESA_CONFERMA = "in_attesa_conferma", "In attesa di conferma"
    IN_CODA = "in_coda", "In coda"
    IN_CORSO = "in_corso", "In corso"
    COMPLETATO = "completato", "Completato"
    ERRORE = "errore", "Errore"
    ANNULLATO = "annullato", "Annullato"


class SistemaDatabaseRestoreJob(models.Model):
    """
    Traccia un file di backup caricato per ripristino: prima viene salvato su disco (senza
    elaborazione), quindi l'elaborazione avviene in un task in background (Celery o thread).
    """
    stato = models.CharField(
        max_length=32,
        choices=StatoRipristinoDatabase.choices,
        default=StatoRipristinoDatabase.IN_ATTESA_CONFERMA,
    )
    percorso_file = models.TextField(help_text="Percorso assoluto del file in attesa o appena usato per il restore.")
    nome_file_originale = models.CharField(max_length=400)
    dimensione_file_bytes = models.BigIntegerField(default=0)
    creato_da = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="ripristini_database",
        null=True,
        blank=True,
    )
    data_creazione = models.DateTimeField(auto_now_add=True)
    data_avvio_ripristino = models.DateTimeField(null=True, blank=True)
    data_completamento = models.DateTimeField(null=True, blank=True)
    messaggio_errore = models.TextField(blank=True)
    backup_sicurezza = models.ForeignKey(
        SistemaDatabaseBackup,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ripristino_job_collegato",
    )
    celery_task_id = models.CharField(max_length=120, blank=True)

    class Meta:
        db_table = "sistema_database_restore_job"
        ordering = ["-data_creazione", "-id"]
        verbose_name = "Job ripristino database"
        verbose_name_plural = "Job ripristino database"

    def __str__(self):
        return f"Ripristino {self.get_stato_display()} - {self.nome_file_originale}"

    @property
    def size_label(self):
        return filesizeformat(self.dimensione_file_bytes or 0)


class TipoFeedbackSegnalazione(models.TextChoices):
    BUG = "bug", "Segnalazione bug"
    FUNZIONE = "funzione", "Suggerimento funzione"


class StatoFeedbackSegnalazione(models.TextChoices):
    NUOVA = "nuova", "Nuova"
    LETTA = "letta", "Letta"
    ARCHIVIATA = "archiviata", "Archiviata"


class FeedbackSegnalazione(models.Model):
    tipo = models.CharField(
        max_length=20,
        choices=TipoFeedbackSegnalazione.choices,
        db_index=True,
    )
    stato = models.CharField(
        max_length=20,
        choices=StatoFeedbackSegnalazione.choices,
        default=StatoFeedbackSegnalazione.NUOVA,
        db_index=True,
    )
    messaggio = models.TextField()
    utente = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="feedback_segnalazioni",
        blank=True,
        null=True,
    )
    utente_nome = models.CharField(max_length=255, blank=True)
    utente_email = models.EmailField(blank=True)
    utente_ruolo = models.CharField(max_length=255, blank=True)
    pagina_url = models.TextField(blank=True)
    pagina_path = models.CharField(max_length=700, blank=True)
    pagina_titolo = models.CharField(max_length=255, blank=True)
    breadcrumb = models.TextField(blank=True)
    user_agent = models.TextField(blank=True)
    referer = models.TextField(blank=True)
    ip_address = models.GenericIPAddressField(blank=True, null=True)
    email_destinatario = models.EmailField(default="gliptica.software@gmail.com")
    email_inviata_at = models.DateTimeField(blank=True, null=True)
    email_errore = models.TextField(blank=True)
    data_creazione = models.DateTimeField(auto_now_add=True, db_index=True)
    data_aggiornamento = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "sistema_feedback_segnalazione"
        ordering = ["-data_creazione", "-id"]
        verbose_name = "Feedback beta"
        verbose_name_plural = "Feedback beta"
        indexes = [
            models.Index(fields=["tipo", "data_creazione"], name="sistema_feedback_tipo_idx"),
            models.Index(fields=["stato", "data_creazione"], name="sistema_feedback_stato_idx"),
        ]

    def __str__(self):
        return f"{self.get_tipo_display()} - {self.utente_display}"

    @property
    def utente_display(self):
        return self.utente_nome or self.utente_email or "Utente non disponibile"

    @property
    def email_status_label(self):
        if self.email_inviata_at:
            return "Inviata"
        if self.email_errore:
            return "Errore invio"
        return "Da inviare"

    @property
    def email_status_class(self):
        if self.email_inviata_at:
            return "feedback-email-sent"
        if self.email_errore:
            return "feedback-email-error"
        return "feedback-email-pending"

    @property
    def tipo_badge_class(self):
        if self.tipo == TipoFeedbackSegnalazione.BUG:
            return "feedback-type-bug"
        return "feedback-type-feature"


class AzioneOperazioneCronologia(models.TextChoices):
    CREAZIONE = "create", "Creazione"
    MODIFICA = "update", "Modifica"
    ELIMINAZIONE = "delete", "Eliminazione"


class ModuloOperazioneCronologia(models.TextChoices):
    ANAGRAFICA = "anagrafica", "Anagrafica"
    FAMIGLIE_INTERESSATE = "famiglie_interessate", "Famiglie interessate"
    ECONOMIA = "economia", "Economia"
    SCUOLA = "scuola", "Scuola"
    CALENDARIO = "calendario", "Calendario"
    SERVIZI_EXTRA = "servizi_extra", "Servizi extra"
    GESTIONE_FINANZIARIA = "gestione_finanziaria", "Gestione finanziaria"
    GESTIONE_AMMINISTRATIVA = "gestione_amministrativa", "Gestione amministrativa"
    SISTEMA = "sistema", "Sistema"


class SistemaOperazioneCronologia(models.Model):
    azione = models.CharField(
        max_length=20,
        choices=AzioneOperazioneCronologia.choices,
    )
    modulo = models.CharField(
        max_length=30,
        choices=ModuloOperazioneCronologia.choices,
        default=ModuloOperazioneCronologia.SISTEMA,
    )
    utente = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="operazioni_cronologia",
        blank=True,
        null=True,
    )
    utente_label = models.CharField(max_length=255, blank=True)
    app_label = models.CharField(max_length=60)
    model_name = models.CharField(max_length=80)
    model_verbose_name = models.CharField(max_length=120)
    oggetto_id = models.CharField(max_length=64, blank=True)
    oggetto_label = models.CharField(max_length=255, blank=True)
    descrizione = models.TextField()
    campi_coinvolti = models.JSONField(default=list, blank=True)
    data_operazione = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = "sistema_operazione_cronologia"
        ordering = ["-data_operazione", "-id"]
        verbose_name = "Operazione cronologia"
        verbose_name_plural = "Cronologia operazioni"
        indexes = [
            models.Index(fields=["azione"], name="sistema_ope_azione_aecbff_idx"),
            models.Index(fields=["modulo"], name="sistema_ope_modulo_642ec3_idx"),
            models.Index(
                fields=["app_label", "model_name", "oggetto_id", "azione", "data_operazione"],
                name="sistema_ope_obj_audit_idx",
            ),
        ]

    def __str__(self):
        return f"{self.get_azione_display()} - {self.descrizione}"

    @property
    def utente_display(self):
        if self.utente_label:
            return self.utente_label
        if self.utente_id:
            nome = self.utente.get_full_name().strip()
            return nome or self.utente.email or self.utente.username
        return "Sistema"

    @property
    def modulo_label(self):
        return self.get_modulo_display()

    @property
    def oggetto_label_display(self):
        if self.oggetto_label:
            return self.oggetto_label
        if self.oggetto_id:
            return f"{self.model_verbose_name} #{self.oggetto_id}"
        return self.model_verbose_name

    @property
    def campi_coinvolti_display(self):
        return ", ".join(self.campi_coinvolti or [])

    @property
    def azione_badge_class(self):
        mapping = {
            AzioneOperazioneCronologia.CREAZIONE: "audit-action-badge-create",
            AzioneOperazioneCronologia.MODIFICA: "audit-action-badge-update",
            AzioneOperazioneCronologia.ELIMINAZIONE: "audit-action-badge-delete",
        }
        return mapping.get(self.azione, "audit-action-badge-update")


class LivelloPermesso(models.TextChoices):
    NESSUNO = "none", "Nessun accesso"
    VISUALIZZAZIONE = "view", "Sola visualizzazione"
    GESTIONE = "manage", "Anche gestione"


class RuoloUtente(models.TextChoices):
    AMMINISTRATORE = "amministratore", "Amministratore"
    SEGRETERIA_AMMINISTRATIVA = "segreteria_amministrativa", "Segreteria Amministrativa"
    SEGRETERIA_DIDATTICA = "segreteria_didattica", "Segreteria Didattica"
    INSEGNANTE = "insegnante", "Insegnante"
    MEMBRO_CDA = "membro_cda", "Membro del CDA"
    VISUALIZZATORE = "visualizzatore", "Visualizzatore"


PERMISSION_MODULE_FIELDS = {
    "anagrafica": "permesso_anagrafica",
    "famiglie_interessate": "permesso_famiglie_interessate",
    "economia": "permesso_economia",
    "sistema": "permesso_sistema",
    "calendario": "permesso_calendario",
    "gestione_finanziaria": "permesso_gestione_finanziaria",
    "gestione_amministrativa": "permesso_gestione_amministrativa",
    "servizi_extra": "permesso_servizi_extra",
}


def normalize_hex_color(value, fallback="#417690"):
    color = (value or "").strip()
    if len(color) != 7 or not color.startswith("#"):
        return fallback
    try:
        int(color[1:], 16)
    except ValueError:
        return fallback
    return color.lower()


def mix_hex_colors(first, second, second_weight):
    first = normalize_hex_color(first)
    second = normalize_hex_color(second, "#ffffff")
    first_weight = 1 - second_weight
    channels = []
    for index in (1, 3, 5):
        first_value = int(first[index : index + 2], 16)
        second_value = int(second[index : index + 2], 16)
        channels.append(round(first_value * first_weight + second_value * second_weight))
    return "#{:02x}{:02x}{:02x}".format(*channels)


def readable_text_color(background_color):
    color = normalize_hex_color(background_color)
    red = int(color[1:3], 16)
    green = int(color[3:5], 16)
    blue = int(color[5:7], 16)
    luminance = (red * 0.299 + green * 0.587 + blue * 0.114) / 255
    return "#203642" if luminance > 0.62 else "#ffffff"


class SistemaRuoloPermessi(models.Model):
    nome = models.CharField(max_length=120, unique=True)
    descrizione = models.TextField(blank=True)
    chiave_legacy = models.CharField(
        max_length=120,
        blank=True,
        null=True,
        unique=True,
        choices=RuoloUtente.choices,
    )
    colore_principale = models.CharField(max_length=7, default="#417690")
    attivo = models.BooleanField(default=True)
    amministratore_operativo = models.BooleanField(
        default=False,
        help_text="Consente l'accesso alle funzioni amministrative operative del sistema.",
    )
    accesso_backup_database = models.BooleanField(
        default=False,
        help_text="Consente l'accesso alla pagina Backup Database.",
    )
    controllo_completo = models.BooleanField(
        default=False,
        help_text="Permette agli utenti con questo ruolo di accedere e gestire tutte le sezioni del software.",
    )
    permesso_anagrafica = models.CharField(
        max_length=10,
        choices=LivelloPermesso.choices,
        default=LivelloPermesso.NESSUNO,
    )
    permesso_famiglie_interessate = models.CharField(
        max_length=10,
        choices=LivelloPermesso.choices,
        default=LivelloPermesso.NESSUNO,
    )
    permesso_economia = models.CharField(
        max_length=10,
        choices=LivelloPermesso.choices,
        default=LivelloPermesso.NESSUNO,
    )
    permesso_sistema = models.CharField(
        max_length=10,
        choices=LivelloPermesso.choices,
        default=LivelloPermesso.NESSUNO,
    )
    permesso_calendario = models.CharField(
        max_length=10,
        choices=LivelloPermesso.choices,
        default=LivelloPermesso.NESSUNO,
    )
    permesso_gestione_finanziaria = models.CharField(
        max_length=10,
        choices=LivelloPermesso.choices,
        default=LivelloPermesso.NESSUNO,
    )
    permesso_gestione_amministrativa = models.CharField(
        max_length=10,
        choices=LivelloPermesso.choices,
        default=LivelloPermesso.NESSUNO,
    )
    permesso_servizi_extra = models.CharField(
        max_length=10,
        choices=LivelloPermesso.choices,
        default=LivelloPermesso.NESSUNO,
    )
    data_creazione = models.DateTimeField(auto_now_add=True)
    data_aggiornamento = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "sistema_ruolo_permessi"
        ordering = ["nome"]
        verbose_name = "Ruolo e permessi"
        verbose_name_plural = "Ruoli e permessi"

    def __str__(self):
        return self.nome

    def clean(self):
        super().clean()
        color = (self.colore_principale or "").strip()
        if len(color) != 7 or not color.startswith("#"):
            raise ValidationError("Il colore deve essere nel formato esadecimale #RRGGBB.")
        try:
            int(color[1:], 16)
        except ValueError as exc:
            raise ValidationError("Il colore deve essere nel formato esadecimale #RRGGBB.") from exc
        self.colore_principale = color.lower()

    def get_module_level(self, module_name):
        field_name = PERMISSION_MODULE_FIELDS.get(module_name)
        if not field_name:
            return LivelloPermesso.NESSUNO
        return getattr(self, field_name, LivelloPermesso.NESSUNO)

    def has_module_permission(self, module_name, level=LivelloPermesso.VISUALIZZAZIONE):
        if not self.attivo:
            return False
        if self.controllo_completo:
            return True

        current_level = self.get_module_level(module_name)
        if level == LivelloPermesso.VISUALIZZAZIONE:
            return current_level in {
                LivelloPermesso.VISUALIZZAZIONE,
                LivelloPermesso.GESTIONE,
            }
        return current_level == LivelloPermesso.GESTIONE

    def get_module_level_display_value(self, module_name):
        return LivelloPermesso(self.get_module_level(module_name)).label

    @property
    def theme_variables(self):
        primary = normalize_hex_color(self.colore_principale)
        return {
            "primary": primary,
            "primary_dark": mix_hex_colors(primary, "#000000", 0.24),
            "primary_soft": mix_hex_colors(primary, "#ffffff", 0.86),
            "primary_muted": mix_hex_colors(primary, "#ffffff", 0.70),
            "primary_hover": mix_hex_colors(primary, "#ffffff", 0.78),
            "primary_text": readable_text_color(primary),
            "sidebar_bg": mix_hex_colors(primary, "#ffffff", 0.90),
            "sidebar_module_bg": mix_hex_colors(primary, "#ffffff", 0.82),
            "sidebar_module_border": mix_hex_colors(primary, "#ffffff", 0.68),
        }


class SistemaUtentePermessi(models.Model):
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="profilo_permessi",
    )
    ruolo_permessi = models.ForeignKey(
        SistemaRuoloPermessi,
        on_delete=models.PROTECT,
        related_name="utenti",
        blank=True,
        null=True,
    )
    ruolo = models.CharField(
        max_length=120,
        blank=True,
        choices=RuoloUtente.choices,
        help_text="Ruolo operativo della persona che utilizza l'account.",
    )
    controllo_completo = models.BooleanField(
        default=False,
        help_text="Permette all'utente di accedere e gestire tutte le sezioni del software senza essere superuser Django.",
    )
    permesso_anagrafica = models.CharField(
        max_length=10,
        choices=LivelloPermesso.choices,
        default=LivelloPermesso.NESSUNO,
    )
    permesso_famiglie_interessate = models.CharField(
        max_length=10,
        choices=LivelloPermesso.choices,
        default=LivelloPermesso.NESSUNO,
    )
    permesso_economia = models.CharField(
        max_length=10,
        choices=LivelloPermesso.choices,
        default=LivelloPermesso.NESSUNO,
    )
    permesso_sistema = models.CharField(
        max_length=10,
        choices=LivelloPermesso.choices,
        default=LivelloPermesso.NESSUNO,
    )
    permesso_calendario = models.CharField(
        max_length=10,
        choices=LivelloPermesso.choices,
        default=LivelloPermesso.NESSUNO,
    )
    permesso_gestione_finanziaria = models.CharField(
        max_length=10,
        choices=LivelloPermesso.choices,
        default=LivelloPermesso.NESSUNO,
    )
    permesso_gestione_amministrativa = models.CharField(
        max_length=10,
        choices=LivelloPermesso.choices,
        default=LivelloPermesso.NESSUNO,
    )
    permesso_servizi_extra = models.CharField(
        max_length=10,
        choices=LivelloPermesso.choices,
        default=LivelloPermesso.NESSUNO,
    )
    data_creazione = models.DateTimeField(auto_now_add=True)
    data_aggiornamento = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "sistema_utente_permessi"
        verbose_name = "Permessi utente"
        verbose_name_plural = "Permessi utenti"
        ordering = ["user__last_name", "user__first_name", "user__email"]

    def __str__(self):
        nome = self.user.get_full_name().strip()
        return nome or self.user.email or self.user.username

    def get_module_level(self, module_name):
        if self.ruolo_permessi_id and self.ruolo_permessi and self.ruolo_permessi.attivo:
            return self.ruolo_permessi.get_module_level(module_name)

        mapping = {
            "anagrafica": self.permesso_anagrafica,
            "famiglie_interessate": self.permesso_famiglie_interessate,
            "economia": self.permesso_economia,
            "sistema": self.permesso_sistema,
            "calendario": self.permesso_calendario,
            "gestione_finanziaria": self.permesso_gestione_finanziaria,
            "gestione_amministrativa": self.permesso_gestione_amministrativa,
            "servizi_extra": self.permesso_servizi_extra,
        }
        return mapping.get(module_name, LivelloPermesso.NESSUNO)

    def has_module_permission(self, module_name, level=LivelloPermesso.VISUALIZZAZIONE):
        if self.ruolo_permessi_id and self.ruolo_permessi:
            return self.ruolo_permessi.has_module_permission(module_name, level=level)

        if self.controllo_completo:
            return True

        current_level = self.get_module_level(module_name)
        if level == LivelloPermesso.VISUALIZZAZIONE:
            return current_level in {
                LivelloPermesso.VISUALIZZAZIONE,
                LivelloPermesso.GESTIONE,
            }
        return current_level == LivelloPermesso.GESTIONE

    @property
    def ruolo_display(self):
        if self.ruolo_permessi_id:
            return self.ruolo_permessi.nome
        if self.ruolo:
            return self.get_ruolo_display()
        return ""

    @property
    def controllo_completo_effettivo(self):
        if self.ruolo_permessi_id and self.ruolo_permessi and self.ruolo_permessi.attivo:
            return self.ruolo_permessi.controllo_completo
        if self.ruolo_permessi_id:
            return False
        return self.controllo_completo

    @property
    def amministratore_operativo_effettivo(self):
        if self.ruolo_permessi_id and self.ruolo_permessi and self.ruolo_permessi.attivo:
            return self.ruolo_permessi.amministratore_operativo
        if self.ruolo_permessi_id:
            return False
        return self.ruolo == RuoloUtente.AMMINISTRATORE

    @property
    def accesso_backup_database_effettivo(self):
        if self.ruolo_permessi_id and self.ruolo_permessi and self.ruolo_permessi.attivo:
            return self.ruolo_permessi.accesso_backup_database
        if self.ruolo_permessi_id:
            return False
        return self.ruolo == RuoloUtente.AMMINISTRATORE

    def get_module_level_display_value(self, module_name):
        return LivelloPermesso(self.get_module_level(module_name)).label

    @property
    def permesso_anagrafica_effettivo_display(self):
        return self.get_module_level_display_value("anagrafica")

    @property
    def permesso_famiglie_interessate_effettivo_display(self):
        return self.get_module_level_display_value("famiglie_interessate")

    @property
    def permesso_economia_effettivo_display(self):
        return self.get_module_level_display_value("economia")

    @property
    def permesso_gestione_finanziaria_effettivo_display(self):
        return self.get_module_level_display_value("gestione_finanziaria")

    @property
    def permesso_sistema_effettivo_display(self):
        return self.get_module_level_display_value("sistema")

    @property
    def permesso_calendario_effettivo_display(self):
        return self.get_module_level_display_value("calendario")

    @property
    def permesso_gestione_amministrativa_effettivo_display(self):
        return self.get_module_level_display_value("gestione_amministrativa")

    @property
    def permesso_servizi_extra_effettivo_display(self):
        return self.get_module_level_display_value("servizi_extra")

    @property
    def role_theme_variables(self):
        if self.ruolo_permessi_id and self.ruolo_permessi and self.ruolo_permessi.attivo:
            return self.ruolo_permessi.theme_variables
        return None
