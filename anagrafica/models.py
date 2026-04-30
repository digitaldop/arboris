from django.core.exceptions import ValidationError
import os

from django.db import models
from django.db.models import Max
from django.urls import reverse
from django.utils.text import get_valid_filename
from .utils import format_phone_number, whatsapp_url_from_phone


def next_order_value(model_cls):
    max_value = model_cls.objects.aggregate(max_ordine=Max("ordine"))["max_ordine"]
    return (max_value or 0) + 1


SESSO_CHOICES = [
    ("M", "Maschio"),
    ("F", "Femmina"),
]

#INIZIO MODELLI PER GLI INDIRIZZI
#Classe per la regione italiana, da utilizzare come scelta per i campi regione degli indirizzi
class Regione(models.Model):
    nome = models.CharField(max_length=100, unique=True)
    ordine = models.IntegerField(blank=True, null=True)
    attiva = models.BooleanField(default=True)

    class Meta:
        ordering = ["ordine", "nome"]
        verbose_name = "Regione"
        verbose_name_plural = "Regioni"

    def __str__(self):
        return self.nome

    def save(self, *args, **kwargs):
        if self.ordine is None:
            self.ordine = next_order_value(Regione)
        super().save(*args, **kwargs)


#Classe per le province italiane, da utilizzare come scelta per i campi provincia degli indirizzi
class Provincia(models.Model):
    sigla = models.CharField(max_length=2, unique=True)
    nome = models.CharField(max_length=100)

    regione = models.ForeignKey(
        Regione,
        on_delete=models.PROTECT,
        related_name="province",
        null=True,   # temporaneo per migrazione
        blank=True
    )

    ordine = models.IntegerField(blank=True, null=True)
    attiva = models.BooleanField(default=True)

    class Meta:
        ordering = ["ordine", "sigla"]
        verbose_name = "Provincia"
        verbose_name_plural = "Province"

    def __str__(self):
        return f"{self.sigla} - {self.nome}"

    def save(self, *args, **kwargs):
        if self.ordine is None:
            self.ordine = next_order_value(Provincia)
        super().save(*args, **kwargs)


#Classe per le città italiane, da utilizzare come scelta per i campi città degli indirizzi
class Citta(models.Model):
    nome = models.CharField(max_length=100)
    provincia = models.ForeignKey(
        Provincia,
        on_delete=models.PROTECT,
        related_name="citta",
    )
    codice_istat = models.CharField(max_length=10, blank=True, db_index=True)
    codice_catastale = models.CharField(max_length=4, blank=True, db_index=True)
    ordine = models.IntegerField(blank=True, null=True)
    attiva = models.BooleanField(default=True)

    class Meta:
        ordering = ["ordine", "nome"]
        verbose_name = "Città"
        verbose_name_plural = "Città"
        constraints = [
            models.UniqueConstraint(
                fields=["nome", "provincia"],
                name="unique_citta_provincia",
            )
        ]

    def __str__(self):
        return f"{self.nome} ({self.provincia.sigla})"

    def save(self, *args, **kwargs):
        if self.ordine is None:
            self.ordine = next_order_value(Citta)
        super().save(*args, **kwargs)


class Nazione(models.Model):
    nome = models.CharField(max_length=120, db_index=True)
    nome_nazionalita = models.CharField(max_length=120, blank=True)
    codice_iso2 = models.CharField(max_length=2, blank=True)
    codice_iso3 = models.CharField(max_length=3, blank=True)
    codice_belfiore = models.CharField(max_length=4, blank=True, db_index=True)
    ordine = models.IntegerField(blank=True, null=True)
    attiva = models.BooleanField(default=True)

    class Meta:
        ordering = ["ordine", "nome"]
        verbose_name = "Nazione"
        verbose_name_plural = "Nazioni"
        constraints = [
            models.UniqueConstraint(
                fields=["codice_belfiore"],
                condition=~models.Q(codice_belfiore=""),
                name="unique_nazione_codice_belfiore_non_vuoto",
            ),
        ]

    def __str__(self):
        return self._format_display_text(self.nome)

    @property
    def label_nazionalita(self):
        return self._format_display_text(self.nome_nazionalita or self.nome)

    @staticmethod
    def _format_display_text(value):
        text = (value or "").strip()
        if not text:
            return ""
        if not text.isupper() and not text.islower():
            return text
        lowercase_words = {
            "a",
            "al",
            "allo",
            "alla",
            "alle",
            "agli",
            "con",
            "da",
            "dal",
            "dalla",
            "de",
            "dei",
            "del",
            "della",
            "delle",
            "di",
            "e",
            "ed",
            "in",
            "per",
        }
        parts = []
        for index, word in enumerate(text.split(" ")):
            title_word = word.lower().title()
            lower_word = title_word.lower()
            if index and lower_word in lowercase_words:
                parts.append(lower_word)
            else:
                parts.append(title_word)
        return " ".join(parts)

    def save(self, *args, **kwargs):
        self.codice_iso2 = (self.codice_iso2 or "").upper().strip()
        self.codice_iso3 = (self.codice_iso3 or "").upper().strip()
        self.codice_belfiore = (self.codice_belfiore or "").upper().strip()
        self.nome_nazionalita = (self.nome_nazionalita or "").strip()
        if self.ordine is None:
            self.ordine = next_order_value(Nazione)
        super().save(*args, **kwargs)
    

#Classe per il CAP italiano, da utilizzare come scelta per i campi CAP degli indirizzi
class CAP(models.Model):
    codice = models.CharField(max_length=10)
    citta = models.ForeignKey(
        Citta,
        on_delete=models.CASCADE,
        related_name="cap_list",
    )
    ordine = models.IntegerField(blank=True, null=True)
    attivo = models.BooleanField(default=True)

    class Meta:
        ordering = ["ordine", "codice"]
        verbose_name = "CAP"
        verbose_name_plural = "CAP"
        constraints = [
            models.UniqueConstraint(
                fields=["codice", "citta"],
                name="unique_cap_citta",
            )
        ]

    def __str__(self):
        return self.codice

    def save(self, *args, **kwargs):
        if self.ordine is None:
            self.ordine = next_order_value(CAP)
        super().save(*args, **kwargs)
    

class Indirizzo(models.Model):
    via = models.CharField(max_length=200)
    numero_civico = models.CharField(max_length=20, blank=True)

    regione = models.ForeignKey(
        Regione,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="indirizzi",
    )
    provincia = models.ForeignKey(
        Provincia,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="indirizzi",
    )
    citta = models.ForeignKey(
        Citta,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="indirizzi",
    )
    cap_scelto = models.ForeignKey(
        CAP,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="indirizzi",
    )

    cap = models.CharField(max_length=10, blank=True)

    class Meta:
        verbose_name = "Indirizzo"
        verbose_name_plural = "Indirizzi"

    def save(self, *args, **kwargs):
        if self.citta:
            self.provincia = self.citta.provincia
            self.regione = self.citta.provincia.regione

        if self.cap_scelto:
            self.cap = self.cap_scelto.codice

        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.via} {self.numero_civico}".strip()
    
    #Rende più leggibile la scelta dell'indirizzo nei form, mostrando anche la città di riferimento
    def label_select(self):
        parti = [self.via]
        if self.numero_civico:
            parti.append(self.numero_civico)

        base = " ".join(parti)

        if self.citta:
            return f"{base} - {self.citta.nome}"
        return base

    def label_full(self):
        parti = [self.via]
        if self.numero_civico:
            parti.append(self.numero_civico)

        base = " ".join(parti).strip()
        dettagli = []

        if self.citta:
            citta = self.citta.nome
            if self.provincia:
                citta = f"{citta} ({self.provincia.sigla})"
            dettagli.append(citta)
        elif self.provincia:
            dettagli.append(self.provincia.sigla)

        if self.cap:
            dettagli.append(self.cap)

        if dettagli:
            return f"{base} - {' - '.join(dettagli)}"
        return base

#FINE MODELLI PER GLI INDIRIZZI

#INIZIO MODELLI PER LE FAMIGLIE

class StatoRelazioneFamiglia(models.Model):
    stato = models.CharField(max_length=100, unique=True)
    ordine = models.IntegerField(blank=True, null=True)
    attivo = models.BooleanField(default=True)
    note = models.TextField(blank=True)

    class Meta:
        ordering = ["ordine", "stato"]
        verbose_name = "Stato relazione famiglia"
        verbose_name_plural = "Stati relazione famiglia"

    def __str__(self):
        return self.stato

    def save(self, *args, **kwargs):
        if self.ordine is None:
            self.ordine = next_order_value(StatoRelazioneFamiglia)
        super().save(*args, **kwargs)


class Famiglia(models.Model):
    cognome_famiglia = models.CharField(max_length=150)
    stato_relazione_famiglia = models.ForeignKey(
        StatoRelazioneFamiglia,
        on_delete=models.PROTECT,
        related_name="famiglie",
    )
    indirizzo_principale = models.ForeignKey(
        Indirizzo,
        on_delete=models.SET_NULL,
        related_name="famiglie_principali",
        blank=True,
        null=True,
    )
    attiva = models.BooleanField(default=True)
    data_creazione = models.DateTimeField(auto_now_add=True)
    data_aggiornamento = models.DateTimeField(auto_now=True)
    note = models.TextField(blank=True)

    class Meta:
        ordering = ["cognome_famiglia"]
        verbose_name = "Famiglia"
        verbose_name_plural = "Famiglie"

    def __str__(self):
        return self.cognome_famiglia

    @staticmethod
    def _format_person_name(person):
        return " ".join(part for part in [person.nome, person.cognome] if part).strip()

    @staticmethod
    def _join_limited(items, limit=2):
        values = [item for item in items if item]
        if not values:
            return ""

        visible = values[:limit]
        label = ", ".join(visible)
        remaining = len(values) - len(visible)
        if remaining > 0:
            label = f"{label} +{remaining}"
        return label

    def referenti_label(self):
        familiari = list(self.familiari.all())
        referenti = [familiare for familiare in familiari if familiare.referente_principale]
        if not referenti:
            referenti = familiari

        return self._join_limited(
            [self._format_person_name(familiare) for familiare in referenti],
        )

    def studenti_label(self):
        return self._join_limited(
            [self._format_person_name(studente) for studente in self.studenti.all()],
        )

    def label_disambiguazione(self):
        dettagli = []

        referenti = self.referenti_label()
        if referenti:
            dettagli.append(f"Referenti: {referenti}")

        studenti = self.studenti_label()
        if studenti:
            dettagli.append(f"Studenti: {studenti}")

        if self.indirizzo_principale:
            dettagli.append(f"Indirizzo: {self.indirizzo_principale.label_select()}")

        return " | ".join(dettagli)

    def label_contesto_anagrafica(self):
        dettagli = []

        referenti = self.referenti_label()
        if referenti:
            dettagli.append(f"Referenti: {referenti}")

        studenti = self.studenti_label()
        if studenti:
            dettagli.append(f"Studenti: {studenti}")

        return " | ".join(dettagli)

    def label_select(self):
        dettagli = self.label_disambiguazione()
        if dettagli:
            return f"{self.cognome_famiglia} - {dettagli}"
        return self.cognome_famiglia
    
#FINE MODELLI PER LE FAMIGLIE

#INIZIO MODELLI PER I FAMILIARI

class RelazioneFamiliare(models.Model):
    relazione = models.CharField(max_length=100, unique=True)
    ordine = models.IntegerField(blank=True, null=True)
    note = models.TextField(blank=True)

    class Meta:
        ordering = ["ordine", "relazione"]
        verbose_name = "Relazione familiare"
        verbose_name_plural = "Relazioni familiari"

    def __str__(self):
        return self.relazione

    def save(self, *args, **kwargs):
        if self.ordine is None:
            self.ordine = next_order_value(RelazioneFamiliare)
        super().save(*args, **kwargs)
    

class Familiare(models.Model):
    famiglia = models.ForeignKey(
        Famiglia,
        on_delete=models.CASCADE,
        related_name="familiari",
    )
    relazione_familiare = models.ForeignKey(
        RelazioneFamiliare,
        on_delete=models.PROTECT,
        related_name="familiari",
    )
    indirizzo = models.ForeignKey(
        Indirizzo,
        on_delete=models.SET_NULL,
        related_name="familiari",
        blank=True,
        null=True,
    )
    nome = models.CharField(max_length=100)
    cognome = models.CharField(max_length=100)
    telefono = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)
    codice_fiscale = models.CharField(max_length=16, blank=True)
    sesso = models.CharField(max_length=1, choices=SESSO_CHOICES, blank=True)
    data_nascita = models.DateField(blank=True, null=True)
    luogo_nascita = models.ForeignKey(
        Citta,
        on_delete=models.PROTECT,
        related_name="familiari_nati",
        blank=True,
        null=True,
    )
    nazione_nascita = models.ForeignKey(
        Nazione,
        on_delete=models.PROTECT,
        related_name="familiari_nati",
        blank=True,
        null=True,
    )
    luogo_nascita_custom = models.CharField(max_length=160, blank=True)
    nazionalita = models.ForeignKey(
        Nazione,
        on_delete=models.PROTECT,
        related_name="familiari_nazionalita",
        blank=True,
        null=True,
    )
    convivente = models.BooleanField(default=False)
    referente_principale = models.BooleanField(default=False)
    abilitato_scambio_retta = models.BooleanField(default=False)
    attivo = models.BooleanField(default=True)
    note = models.TextField(blank=True)

    class Meta:
        ordering = ["cognome", "nome"]
        verbose_name = "Familiare"
        verbose_name_plural = "Familiari"

    def __str__(self):
        return f"{self.cognome} {self.nome}"

    @property
    def indirizzo_effettivo(self):
        return self.indirizzo or self.famiglia.indirizzo_principale

    @property
    def formatted_telefono(self):
        return format_phone_number(self.telefono)

    @property
    def telefono_whatsapp_url(self):
        return whatsapp_url_from_phone(self.telefono)

    @property
    def luogo_nascita_display(self):
        if self.luogo_nascita:
            return str(self.luogo_nascita)
        if self.nazione_nascita:
            return str(self.nazione_nascita)
        return self.luogo_nascita_custom

    @property
    def nazionalita_display(self):
        if self.nazionalita:
            return self.nazionalita.label_nazionalita
        return ""

# FINE MODELLI PER I FAMILIARI

# INIZIO MODELLI PER GLI STUDENTI

class Studente(models.Model):
    famiglia = models.ForeignKey(
        Famiglia,
        on_delete=models.CASCADE,
        related_name="studenti",
    )
    indirizzo = models.ForeignKey(
        Indirizzo,
        on_delete=models.SET_NULL,
        related_name="studenti",
        blank=True,
        null=True,
    )
    nome = models.CharField(max_length=100)
    cognome = models.CharField(max_length=100)
    data_nascita = models.DateField(blank=True, null=True)
    luogo_nascita = models.ForeignKey(
        Citta,
        on_delete=models.PROTECT,
        related_name="studenti_nati",
        blank=True,
        null=True,
    )
    nazione_nascita = models.ForeignKey(
        Nazione,
        on_delete=models.PROTECT,
        related_name="studenti_nati",
        blank=True,
        null=True,
    )
    luogo_nascita_custom = models.CharField(max_length=160, blank=True)
    nazionalita = models.ForeignKey(
        Nazione,
        on_delete=models.PROTECT,
        related_name="studenti_nazionalita",
        blank=True,
        null=True,
    )
    sesso = models.CharField(max_length=1, choices=SESSO_CHOICES, blank=True)
    codice_fiscale = models.CharField(max_length=16, blank=True)
    attivo = models.BooleanField(default=True)
    note = models.TextField(blank=True)

    class Meta:
        ordering = ["cognome", "nome"]
        verbose_name = "Studente"
        verbose_name_plural = "Studenti"

    def __str__(self):
        return f"{self.cognome} {self.nome}"

    @property
    def indirizzo_effettivo(self):
        return self.indirizzo or self.famiglia.indirizzo_principale

    @property
    def luogo_nascita_display(self):
        if self.luogo_nascita:
            return str(self.luogo_nascita)
        if self.nazione_nascita:
            return str(self.nazione_nascita)
        return self.luogo_nascita_custom

    @property
    def nazionalita_display(self):
        if self.nazionalita:
            return self.nazionalita.label_nazionalita
        return ""
    
# FINE MODELLI PER GLI STUDENTI

# INIZIO MODELLI PER I DOCUMENTI

def anno_scolastico_documenti_folder():
    from scuola.utils import resolve_default_anno_scolastico

    anno = resolve_default_anno_scolastico()
    if not anno:
        return "senza-anno-scolastico"

    raw_label = anno.nome_anno_scolastico
    if not raw_label and anno.data_inizio and anno.data_fine:
        raw_label = f"{anno.data_inizio.year}-{anno.data_fine.year}"

    normalized = (raw_label or "senza-anno-scolastico").replace("/", "-").replace("\\", "-")
    return get_valid_filename(normalized).strip("._-") or "senza-anno-scolastico"


def documento_upload_to(instance, filename):
    filename = os.path.basename(filename)
    anno_folder = anno_scolastico_documenti_folder()
    if getattr(instance, "studente_id", None):
        owner_folder = "studenti"
    elif getattr(instance, "familiare_id", None):
        owner_folder = "familiari"
    elif getattr(instance, "famiglia_id", None):
        owner_folder = "famiglie"
    else:
        owner_folder = "non_associati"

    return f"{anno_folder}/documenti/{owner_folder}/{filename}"


class TipoDocumento(models.Model):
    tipo_documento = models.CharField(max_length=100, unique=True)
    ordine = models.IntegerField(blank=True, null=True)
    attivo = models.BooleanField(default=True)
    note = models.TextField(blank=True)

    class Meta:
        ordering = ["ordine", "tipo_documento"]
        verbose_name = "Tipo documento"
        verbose_name_plural = "Tipi documento"

    def __str__(self):
        return self.tipo_documento

    def save(self, *args, **kwargs):
        if self.ordine is None:
            self.ordine = next_order_value(TipoDocumento)
        super().save(*args, **kwargs)


class Documento(models.Model):
    famiglia = models.ForeignKey(
        Famiglia,
        on_delete=models.CASCADE,
        related_name="documenti",
        blank=True,
        null=True,
    )
    familiare = models.ForeignKey(
        Familiare,
        on_delete=models.CASCADE,
        related_name="documenti",
        blank=True,
        null=True,
    )
    studente = models.ForeignKey(
        Studente,
        on_delete=models.CASCADE,
        related_name="documenti",
        blank=True,
        null=True,
    )
    tipo_documento = models.ForeignKey(
        TipoDocumento,
        on_delete=models.PROTECT,
        related_name="documenti",
    )
    descrizione = models.TextField(blank=True)
    file = models.FileField(upload_to=documento_upload_to, max_length=255)
    data_caricamento = models.DateField(auto_now_add=True)
    scadenza = models.DateField(blank=True, null=True)
    visibile = models.BooleanField(default=True)
    note = models.TextField(blank=True)

    class Meta:
        ordering = ["-data_caricamento", "-id"]
        verbose_name = "Documento"
        verbose_name_plural = "Documenti"

    def __str__(self):
        if self.descrizione:
            return self.descrizione
        return f"{self.tipo_documento}"

    @property
    def filename(self):
        if not self.file:
            return ""
        return os.path.basename(self.file.name)

    @property
    def download_url(self):
        if not self.file or not self.pk:
            return ""
        return reverse("apri_documento", kwargs={"pk": self.pk})

    def clean(self):
        owners = [self.famiglia_id, self.familiare_id, self.studente_id]
        valorizzati = sum(bool(x) for x in owners)
        if valorizzati > 1:
            raise ValidationError(
                "Un documento può essere collegato a una sola entità: famiglia, familiare oppure studente."
            )
        
# FINE MODELLI PER I DOCUMENTI
