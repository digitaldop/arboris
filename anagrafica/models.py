from django.core.exceptions import ValidationError
import os

from django.contrib.contenttypes.fields import GenericForeignKey, GenericRelation
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.db.models import Max, Q
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


def _first_principal_link(manager):
    if not manager:
        return None
    try:
        links = list(manager.all().order_by("ordine", "id"))
        return next((link for link in links if link.principale), links[0] if links else None)
    except (AttributeError, TypeError):
        return None

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


class LabelIndirizzo(models.Model):
    nome = models.CharField(max_length=80, unique=True)
    ordine = models.IntegerField(blank=True, null=True)
    attiva = models.BooleanField(default=True)
    note = models.TextField(blank=True)

    class Meta:
        ordering = ["ordine", "nome"]
        verbose_name = "Etichetta indirizzo"
        verbose_name_plural = "Etichette indirizzi"

    def __str__(self):
        return self.nome

    def save(self, *args, **kwargs):
        self.nome = (self.nome or "").strip()
        if self.ordine is None:
            self.ordine = next_order_value(LabelIndirizzo)
        super().save(*args, **kwargs)


class LabelTelefono(models.Model):
    nome = models.CharField(max_length=80, unique=True)
    ordine = models.IntegerField(blank=True, null=True)
    attiva = models.BooleanField(default=True)
    note = models.TextField(blank=True)

    class Meta:
        ordering = ["ordine", "nome"]
        verbose_name = "Etichetta telefono"
        verbose_name_plural = "Etichette telefoni"

    def __str__(self):
        return self.nome

    def save(self, *args, **kwargs):
        self.nome = (self.nome or "").strip()
        if self.ordine is None:
            self.ordine = next_order_value(LabelTelefono)
        super().save(*args, **kwargs)


class LabelEmail(models.Model):
    nome = models.CharField(max_length=80, unique=True)
    ordine = models.IntegerField(blank=True, null=True)
    attiva = models.BooleanField(default=True)
    note = models.TextField(blank=True)

    class Meta:
        ordering = ["ordine", "nome"]
        verbose_name = "Etichetta email"
        verbose_name_plural = "Etichette email"

    def __str__(self):
        return self.nome

    def save(self, *args, **kwargs):
        self.nome = (self.nome or "").strip()
        if self.ordine is None:
            self.ordine = next_order_value(LabelEmail)
        super().save(*args, **kwargs)


class AnagraficaIndirizzo(models.Model):
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    content_object = GenericForeignKey("content_type", "object_id")
    indirizzo = models.ForeignKey(
        Indirizzo,
        on_delete=models.CASCADE,
        related_name="collegamenti_anagrafici",
    )
    label = models.ForeignKey(
        LabelIndirizzo,
        on_delete=models.PROTECT,
        related_name="collegamenti",
    )
    principale = models.BooleanField(default=False)
    ordine = models.IntegerField(blank=True, null=True)
    note = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["ordine", "id"]
        verbose_name = "Indirizzo anagrafico"
        verbose_name_plural = "Indirizzi anagrafici"
        indexes = [
            models.Index(fields=["content_type", "object_id"], name="anag_ind_owner_idx"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["content_type", "object_id"],
                condition=Q(principale=True),
                name="unique_indirizzo_principale",
            )
        ]

    def __str__(self):
        return f"{self.label} - {self.indirizzo}"

    def save(self, *args, **kwargs):
        if self.ordine is None:
            self.ordine = next_order_value(AnagraficaIndirizzo)
        super().save(*args, **kwargs)


class AnagraficaTelefono(models.Model):
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    content_object = GenericForeignKey("content_type", "object_id")
    numero = models.CharField(max_length=40)
    label = models.ForeignKey(
        LabelTelefono,
        on_delete=models.PROTECT,
        related_name="collegamenti",
    )
    principale = models.BooleanField(default=False)
    ordine = models.IntegerField(blank=True, null=True)
    note = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["ordine", "id"]
        verbose_name = "Telefono anagrafico"
        verbose_name_plural = "Telefoni anagrafici"
        indexes = [
            models.Index(fields=["content_type", "object_id"], name="anag_tel_owner_idx"),
            models.Index(fields=["numero"], name="anag_tel_numero_idx"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["content_type", "object_id"],
                condition=Q(principale=True),
                name="unique_telefono_principale",
            )
        ]

    def __str__(self):
        return f"{self.label} - {format_phone_number(self.numero)}"

    def save(self, *args, **kwargs):
        self.numero = (self.numero or "").strip()
        if self.ordine is None:
            self.ordine = next_order_value(AnagraficaTelefono)
        super().save(*args, **kwargs)

    @property
    def numero_formattato(self):
        return format_phone_number(self.numero)

    @property
    def whatsapp_url(self):
        return whatsapp_url_from_phone(self.numero)


class AnagraficaEmail(models.Model):
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    content_object = GenericForeignKey("content_type", "object_id")
    email = models.EmailField()
    label = models.ForeignKey(
        LabelEmail,
        on_delete=models.PROTECT,
        related_name="collegamenti",
    )
    principale = models.BooleanField(default=False)
    ordine = models.IntegerField(blank=True, null=True)
    note = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["ordine", "id"]
        verbose_name = "Email anagrafica"
        verbose_name_plural = "Email anagrafiche"
        indexes = [
            models.Index(fields=["content_type", "object_id"], name="anag_email_owner_idx"),
            models.Index(fields=["email"], name="anag_email_value_idx"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["content_type", "object_id"],
                condition=Q(principale=True),
                name="unique_email_principale",
            )
        ]

    def __str__(self):
        return f"{self.label} - {self.email}"

    def save(self, *args, **kwargs):
        self.email = (self.email or "").strip().lower()
        if self.ordine is None:
            self.ordine = next_order_value(AnagraficaEmail)
        super().save(*args, **kwargs)

#FINE MODELLI PER GLI INDIRIZZI

#INIZIO MODELLI PER I FAMILIARI

class Persona(models.Model):
    indirizzi_anagrafici = GenericRelation(
        AnagraficaIndirizzo,
        related_query_name="persone",
    )
    telefoni_anagrafici = GenericRelation(
        AnagraficaTelefono,
        related_query_name="persone",
    )
    email_anagrafiche = GenericRelation(
        AnagraficaEmail,
        related_query_name="persone",
    )
    indirizzo = models.ForeignKey(
        Indirizzo,
        on_delete=models.SET_NULL,
        related_name="persone",
        blank=True,
        null=True,
    )
    nome = models.CharField(max_length=100)
    cognome = models.CharField(max_length=100)
    sesso = models.CharField(max_length=1, choices=SESSO_CHOICES, blank=True)
    data_nascita = models.DateField(blank=True, null=True)
    luogo_nascita = models.ForeignKey(
        Citta,
        on_delete=models.PROTECT,
        related_name="persone_nate",
        blank=True,
        null=True,
    )
    nazione_nascita = models.ForeignKey(
        Nazione,
        on_delete=models.PROTECT,
        related_name="persone_nate",
        blank=True,
        null=True,
    )
    luogo_nascita_custom = models.CharField(max_length=160, blank=True)
    nazionalita = models.ForeignKey(
        Nazione,
        on_delete=models.PROTECT,
        related_name="persone_nazionalita",
        blank=True,
        null=True,
    )
    codice_fiscale = models.CharField(max_length=16, blank=True)
    email = models.EmailField(blank=True)
    telefono = models.CharField(max_length=40, blank=True)
    note = models.TextField(blank=True)
    data_creazione = models.DateTimeField(auto_now_add=True)
    data_aggiornamento = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "anagrafica_persona"
        ordering = ["cognome", "nome"]
        verbose_name = "Persona"
        verbose_name_plural = "Persone"
        constraints = [
            models.UniqueConstraint(
                fields=["codice_fiscale"],
                condition=~Q(codice_fiscale=""),
                name="anagrafica_persona_cf_unique",
            )
        ]

    def __str__(self):
        return self.nome_completo

    @property
    def nome_completo(self):
        return f"{self.cognome} {self.nome}".strip()

    @property
    def indirizzo_effettivo(self):
        link = _first_principal_link(self.indirizzi_anagrafici)
        if link and link.indirizzo_id:
            return link.indirizzo
        return self.indirizzo

    @property
    def telefono_principale(self):
        link = _first_principal_link(self.telefoni_anagrafici)
        if link and link.numero:
            return link.numero
        return self.telefono

    @property
    def email_principale(self):
        link = _first_principal_link(self.email_anagrafiche)
        if link and link.email:
            return link.email
        return self.email

    @property
    def formatted_telefono(self):
        return format_phone_number(self.telefono_principale)

    @property
    def telefono_whatsapp_url(self):
        return whatsapp_url_from_phone(self.telefono_principale)

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
    

class FamiliareQuerySet(models.QuerySet):
    PERSONA_LOOKUP_FIELDS = {
        "indirizzo",
        "nome",
        "cognome",
        "telefono",
        "email",
        "codice_fiscale",
        "sesso",
        "data_nascita",
        "luogo_nascita",
        "nazione_nascita",
        "luogo_nascita_custom",
        "nazionalita",
        "note",
    }

    def _translate_lookup(self, lookup):
        root, separator, suffix = lookup.partition("__")
        if root in self.PERSONA_LOOKUP_FIELDS:
            return f"persona__{root}{separator}{suffix}" if separator else f"persona__{root}"
        return lookup

    def _translate_kwargs(self, kwargs, *, exclude=False):
        translated = {}
        force_empty = False
        for key, value in kwargs.items():
            root = key.partition("__")[0]
            if root == "attivo":
                is_active = bool(value)
                if (not exclude and not is_active) or (exclude and is_active):
                    force_empty = True
                continue
            translated[self._translate_lookup(key)] = value
        return translated, force_empty

    def _translate_q(self, q_object):
        if not isinstance(q_object, Q):
            return q_object

        translated = Q()
        translated.connector = q_object.connector
        translated.negated = q_object.negated
        children = []
        for child in q_object.children:
            if isinstance(child, Q):
                children.append(self._translate_q(child))
                continue

            lookup, value = child
            root = lookup.partition("__")[0]
            if root == "attivo":
                if bool(value):
                    continue
                children.append(("pk__in", []))
                continue
            children.append((self._translate_lookup(lookup), value))
        translated.children = children
        return translated

    def filter(self, *args, **kwargs):
        args = tuple(self._translate_q(arg) for arg in args)
        kwargs, force_empty = self._translate_kwargs(kwargs)
        queryset = super().filter(*args, **kwargs)
        return queryset.none() if force_empty else queryset

    def exclude(self, *args, **kwargs):
        args = tuple(self._translate_q(arg) for arg in args)
        kwargs, force_empty = self._translate_kwargs(kwargs, exclude=True)
        queryset = super().exclude(*args, **kwargs)
        return queryset.none() if force_empty else queryset

    def order_by(self, *field_names):
        translated = []
        for field_name in field_names:
            if not isinstance(field_name, str):
                translated.append(field_name)
                continue
            prefix = "-" if field_name.startswith("-") else ""
            raw_name = field_name[1:] if prefix else field_name
            translated.append(f"{prefix}{self._translate_lookup(raw_name)}")
        return super().order_by(*translated)

    def select_related(self, *fields):
        translated = []
        for field_name in fields:
            if field_name in {"indirizzo", "luogo_nascita", "nazione_nascita", "nazionalita"}:
                translated.append(f"persona__{field_name}")
            elif field_name.startswith(("indirizzo__", "luogo_nascita__", "nazione_nascita__", "nazionalita__")):
                translated.append(f"persona__{field_name}")
            else:
                translated.append(field_name)
        return super().select_related(*translated)


class Familiare(models.Model):
    PERSONA_PROXY_FIELDS = {
        "indirizzo",
        "nome",
        "cognome",
        "telefono",
        "email",
        "codice_fiscale",
        "sesso",
        "data_nascita",
        "luogo_nascita",
        "nazione_nascita",
        "luogo_nascita_custom",
        "nazionalita",
        "note",
    }

    persona = models.OneToOneField(
        Persona,
        on_delete=models.CASCADE,
        related_name="profilo_familiare",
        help_text="Anagrafica persona condivisa con eventuali profili lavorativi.",
    )
    indirizzi_anagrafici = GenericRelation(
        AnagraficaIndirizzo,
        related_query_name="familiari",
    )
    telefoni_anagrafici = GenericRelation(
        AnagraficaTelefono,
        related_query_name="familiari",
    )
    email_anagrafiche = GenericRelation(
        AnagraficaEmail,
        related_query_name="familiari",
    )
    relazione_familiare = models.ForeignKey(
        RelazioneFamiliare,
        on_delete=models.PROTECT,
        related_name="familiari",
    )
    convivente = models.BooleanField(default=False)
    referente_principale = models.BooleanField(default=False)
    abilitato_scambio_retta = models.BooleanField(default=False)

    objects = FamiliareQuerySet.as_manager()

    class Meta:
        ordering = ["persona__cognome", "persona__nome"]
        verbose_name = "Familiare"
        verbose_name_plural = "Familiari"

    def __init__(self, *args, **kwargs):
        pending_persona_payload = {}
        for field_name in self.PERSONA_PROXY_FIELDS:
            if field_name in kwargs:
                pending_persona_payload[field_name] = kwargs.pop(field_name)
        kwargs.pop("attivo", None)
        super().__init__(*args, **kwargs)
        self._pending_persona_payload = pending_persona_payload

    def __str__(self):
        return self.persona.nome_completo if self.persona_id else self._pending_full_name()

    def _pending_full_name(self):
        return " ".join(
            part
            for part in [
                self._pending_persona_payload.get("cognome", ""),
                self._pending_persona_payload.get("nome", ""),
            ]
            if part
        ).strip()

    def _get_persona_value(self, field_name):
        if self.persona_id:
            return getattr(self.persona, field_name)
        return self._pending_persona_payload.get(field_name)

    def _set_persona_value(self, field_name, value):
        if field_name == "codice_fiscale":
            value = (value or "").upper().strip()
        if self.persona_id:
            setattr(self.persona, field_name, value)
        else:
            self._pending_persona_payload[field_name] = value

    @property
    def indirizzo(self):
        return self._get_persona_value("indirizzo")

    @indirizzo.setter
    def indirizzo(self, value):
        self._set_persona_value("indirizzo", value)

    @property
    def nome(self):
        return self._get_persona_value("nome") or ""

    @nome.setter
    def nome(self, value):
        self._set_persona_value("nome", value or "")

    @property
    def cognome(self):
        return self._get_persona_value("cognome") or ""

    @cognome.setter
    def cognome(self, value):
        self._set_persona_value("cognome", value or "")

    @property
    def telefono(self):
        return self._get_persona_value("telefono") or ""

    @telefono.setter
    def telefono(self, value):
        self._set_persona_value("telefono", value or "")

    @property
    def email(self):
        return self._get_persona_value("email") or ""

    @email.setter
    def email(self, value):
        self._set_persona_value("email", value or "")

    @property
    def codice_fiscale(self):
        return self._get_persona_value("codice_fiscale") or ""

    @codice_fiscale.setter
    def codice_fiscale(self, value):
        self._set_persona_value("codice_fiscale", value)

    @property
    def sesso(self):
        return self._get_persona_value("sesso") or ""

    @sesso.setter
    def sesso(self, value):
        self._set_persona_value("sesso", value or "")

    @property
    def data_nascita(self):
        return self._get_persona_value("data_nascita")

    @data_nascita.setter
    def data_nascita(self, value):
        self._set_persona_value("data_nascita", value)

    @property
    def luogo_nascita(self):
        return self._get_persona_value("luogo_nascita")

    @luogo_nascita.setter
    def luogo_nascita(self, value):
        self._set_persona_value("luogo_nascita", value)

    @property
    def nazione_nascita(self):
        return self._get_persona_value("nazione_nascita")

    @nazione_nascita.setter
    def nazione_nascita(self, value):
        self._set_persona_value("nazione_nascita", value)

    @property
    def luogo_nascita_custom(self):
        return self._get_persona_value("luogo_nascita_custom") or ""

    @luogo_nascita_custom.setter
    def luogo_nascita_custom(self, value):
        self._set_persona_value("luogo_nascita_custom", value or "")

    @property
    def nazionalita(self):
        return self._get_persona_value("nazionalita")

    @nazionalita.setter
    def nazionalita(self, value):
        self._set_persona_value("nazionalita", value)

    @property
    def note(self):
        return self._get_persona_value("note") or ""

    @note.setter
    def note(self, value):
        self._set_persona_value("note", value or "")

    @property
    def attivo(self):
        return True

    @attivo.setter
    def attivo(self, value):
        return None

    @property
    def nome_completo(self):
        return f"{self.cognome} {self.nome}".strip()

    def get_sesso_display(self):
        return dict(SESSO_CHOICES).get(self.sesso, self.sesso)

    def _normalizzato_persona_payload(self):
        payload = {}
        for field_name in self.PERSONA_PROXY_FIELDS:
            value = self._pending_persona_payload.get(field_name)
            if field_name in {"nome", "cognome", "telefono", "email", "codice_fiscale", "sesso", "luogo_nascita_custom", "note"}:
                value = value or ""
            payload[field_name] = value
        payload["codice_fiscale"] = (payload.get("codice_fiscale") or "").upper().strip()
        return payload

    def _persona_payload(self):
        if self.persona_id:
            payload = {field_name: getattr(self.persona, field_name) for field_name in self.PERSONA_PROXY_FIELDS}
            payload.update(self._pending_persona_payload)
            self._pending_persona_payload = payload
        return self._normalizzato_persona_payload()

    def save(self, *args, **kwargs):
        payload = self._persona_payload()
        if self.persona_id:
            persona = self.persona
            changed_fields = []
            for field_name, value in payload.items():
                if getattr(persona, field_name) != value:
                    setattr(persona, field_name, value)
                    changed_fields.append(field_name)
            if changed_fields:
                persona.save(update_fields=changed_fields + ["data_aggiornamento"])
        else:
            self.persona = Persona.objects.create(**payload)
        super().save(*args, **kwargs)
        self._pending_persona_payload = {}

    @property
    def indirizzo_effettivo(self):
        link = _first_principal_link(self.persona.indirizzi_anagrafici) if self.persona_id else None
        if not link:
            link = _first_principal_link(self.indirizzi_anagrafici)
        if link and link.indirizzo_id:
            return link.indirizzo
        return self.indirizzo

    @property
    def telefono_principale(self):
        link = _first_principal_link(self.persona.telefoni_anagrafici) if self.persona_id else None
        if not link:
            link = _first_principal_link(self.telefoni_anagrafici)
        if link and link.numero:
            return link.numero
        return self.telefono

    @property
    def email_principale(self):
        link = _first_principal_link(self.persona.email_anagrafiche) if self.persona_id else None
        if not link:
            link = _first_principal_link(self.email_anagrafiche)
        if link and link.email:
            return link.email
        return self.email

    @property
    def formatted_telefono(self):
        return format_phone_number(self.telefono_principale)

    @property
    def telefono_whatsapp_url(self):
        return whatsapp_url_from_phone(self.telefono_principale)

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
    indirizzi_anagrafici = GenericRelation(
        AnagraficaIndirizzo,
        related_query_name="studenti",
    )
    telefoni_anagrafici = GenericRelation(
        AnagraficaTelefono,
        related_query_name="studenti",
    )
    email_anagrafiche = GenericRelation(
        AnagraficaEmail,
        related_query_name="studenti",
    )
    familiari = models.ManyToManyField(
        Familiare,
        through="StudenteFamiliare",
        related_name="studenti_collegati",
        blank=True,
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
        link = _first_principal_link(self.indirizzi_anagrafici)
        if link and link.indirizzo_id:
            return link.indirizzo
        return self.indirizzo

    @property
    def telefono_principale(self):
        link = _first_principal_link(self.telefoni_anagrafici)
        return link.numero if link and link.numero else ""

    @property
    def email_principale(self):
        link = _first_principal_link(self.email_anagrafiche)
        return link.email if link and link.email else ""

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


class StudenteFamiliare(models.Model):
    studente = models.ForeignKey(
        Studente,
        on_delete=models.CASCADE,
        related_name="relazioni_familiari",
    )
    familiare = models.ForeignKey(
        Familiare,
        on_delete=models.CASCADE,
        related_name="relazioni_studenti",
    )
    relazione_familiare = models.ForeignKey(
        RelazioneFamiliare,
        on_delete=models.SET_NULL,
        related_name="relazioni_studenti",
        blank=True,
        null=True,
    )
    referente_principale = models.BooleanField(default=False)
    convivente = models.BooleanField(default=False)
    attivo = models.BooleanField(default=True)
    note = models.TextField(blank=True)
    data_creazione = models.DateTimeField(auto_now_add=True)
    data_aggiornamento = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["studente__cognome", "studente__nome", "familiare__persona__cognome", "familiare__persona__nome"]
        verbose_name = "Relazione studente-familiare"
        verbose_name_plural = "Relazioni studenti-familiari"
        constraints = [
            models.UniqueConstraint(
                fields=["studente", "familiare"],
                name="unique_studente_familiare",
            )
        ]

    def __str__(self):
        relazione = f" ({self.relazione_familiare})" if self.relazione_familiare_id else ""
        return f"{self.studente} - {self.familiare}{relazione}"
    
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
        owners = [self.familiare_id, self.studente_id]
        valorizzati = sum(bool(x) for x in owners)
        if valorizzati > 1:
            raise ValidationError(
                "Un documento può essere collegato a una sola entità: familiare oppure studente."
            )
        
# FINE MODELLI PER I DOCUMENTI
