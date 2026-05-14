from calendar import monthrange
from datetime import date
from decimal import Decimal

from django.contrib.contenttypes.fields import GenericRelation
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Max, Q
from django.utils import timezone


ZERO = Decimal("0.00")
ONE_HUNDRED = Decimal("100.00")


def next_order_value(model_cls):
    max_value = model_cls.objects.aggregate(max_ordine=Max("ordine"))["max_ordine"]
    return (max_value or 0) + 1


class StatoDipendente(models.TextChoices):
    ATTIVO = "attivo", "Attivo"
    SOSPESO = "sospeso", "Sospeso"
    CESSATO = "cessato", "Cessato"


class SessoDipendente(models.TextChoices):
    MASCHIO = "M", "Maschio"
    FEMMINA = "F", "Femmina"


class RuoloAziendaleDipendente(models.TextChoices):
    DIPENDENTE = "dipendente", "Dipendente"
    EDUCATORE = "educatore", "Educatore"


RuoloAnagraficoDipendente = RuoloAziendaleDipendente


class RegimeOrarioDipendente(models.TextChoices):
    TEMPO_PIENO = "tempo_pieno", "Tempo pieno"
    TEMPO_PARZIALE = "tempo_parziale", "Part-time"


class StatoBustaPaga(models.TextChoices):
    BOZZA = "bozza", "Bozza"
    PREVISTA = "prevista", "Previsione calcolata"
    EFFETTIVA = "effettiva", "Effettiva caricata"
    VERIFICATA = "verificata", "Verificata"


class ScenarioValorePayroll(models.TextChoices):
    PREVISTO = "previsto", "Previsto"
    EFFETTIVO = "effettivo", "Effettivo"


class CategoriaDatoPayrollUfficiale(models.TextChoices):
    FONTE = "fonte", "Fonte informativa"
    CONTRIBUTI = "contributi", "Contributi INPS"
    INAIL = "inail", "INAIL"
    TFR = "tfr", "TFR"
    IRPEF = "irpef", "IRPEF"
    ADDIZIONALE_REGIONALE = "addizionale_regionale", "Addizionale regionale IRPEF"
    ADDIZIONALE_COMUNALE = "addizionale_comunale", "Addizionale comunale IRPEF"
    CCNL = "ccnl", "CCNL"
    ALTRO = "altro", "Altro"


class TipoVocePayroll(models.TextChoices):
    RETRIBUZIONE = "retribuzione", "Retribuzione"
    CONTRIBUTO_DATORE = "contributo_datore", "Contributi datore"
    CONTRIBUTO_DIPENDENTE = "contributo_dipendente", "Contributi dipendente"
    TREDICESIMA = "tredicesima", "Rateo tredicesima/mensilita"
    TFR = "tfr", "Rateo TFR"
    TRATTENUTA = "trattenuta", "Trattenuta"
    RIMBORSO = "rimborso", "Rimborso"
    BONUS = "bonus", "Premio / bonus"
    ONERE = "onere", "Altro onere azienda"
    ALTRO = "altro", "Altro"


class TipoDocumentoDipendente(models.TextChoices):
    CONTRATTO = "contratto", "Contratto"
    BUSTA_PAGA = "busta_paga", "Busta paga"
    DOCUMENTO_IDENTITA = "documento_identita", "Documento identita"
    COMUNICAZIONE = "comunicazione", "Comunicazione"
    ALTRO = "altro", "Altro"


class TipoContrattoDipendente(models.Model):
    nome = models.CharField(max_length=100, unique=True)
    ordine = models.IntegerField(blank=True, null=True)
    attivo = models.BooleanField(default=True)
    note = models.TextField(blank=True)

    class Meta:
        db_table = "gestione_amministrativa_tipo_contratto_dipendente"
        ordering = ["ordine", "nome"]
        verbose_name = "Tipo contratto dipendente"
        verbose_name_plural = "Tipi contratto dipendente"

    def __str__(self):
        return self.nome

    def save(self, *args, **kwargs):
        if self.ordine is None:
            self.ordine = next_order_value(TipoContrattoDipendente)
        super().save(*args, **kwargs)


class DipendenteQuerySet(models.QuerySet):
    LEGACY_PERSONA_LOOKUPS = {
        "nome": "persona_collegata__nome",
        "cognome": "persona_collegata__cognome",
        "codice_fiscale": "persona_collegata__codice_fiscale",
        "email": "persona_collegata__email",
        "telefono": "persona_collegata__telefono",
    }
    LEGACY_LOOKUPS = {
        "ruolo_anagrafico": "ruolo_aziendale",
        "familiare_collegato": "persona_collegata__profilo_familiare",
        "familiare_collegato_id": "persona_collegata__profilo_familiare_id",
    }

    def _translate_legacy_kwargs(self, kwargs):
        translated = {}
        for key, value in kwargs.items():
            lookup_root, separator, lookup_tail = key.partition("__")
            if lookup_root in self.LEGACY_PERSONA_LOOKUPS:
                key = f"{self.LEGACY_PERSONA_LOOKUPS[lookup_root]}{separator}{lookup_tail}" if separator else self.LEGACY_PERSONA_LOOKUPS[lookup_root]
            elif lookup_root in self.LEGACY_LOOKUPS:
                key = f"{self.LEGACY_LOOKUPS[lookup_root]}{separator}{lookup_tail}" if separator else self.LEGACY_LOOKUPS[lookup_root]
            translated[key] = value
        return translated

    def filter(self, *args, **kwargs):
        return super().filter(*args, **self._translate_legacy_kwargs(kwargs))

    def exclude(self, *args, **kwargs):
        return super().exclude(*args, **self._translate_legacy_kwargs(kwargs))

    def get(self, *args, **kwargs):
        return super().get(*args, **self._translate_legacy_kwargs(kwargs))


class Dipendente(models.Model):
    indirizzi_anagrafici = GenericRelation(
        "anagrafica.AnagraficaIndirizzo",
        related_query_name="dipendenti",
    )
    telefoni_anagrafici = GenericRelation(
        "anagrafica.AnagraficaTelefono",
        related_query_name="dipendenti",
    )
    email_anagrafiche = GenericRelation(
        "anagrafica.AnagraficaEmail",
        related_query_name="dipendenti",
    )
    ruolo_aziendale = models.CharField(
        max_length=30,
        choices=RuoloAziendaleDipendente.choices,
        default=RuoloAziendaleDipendente.DIPENDENTE,
        db_index=True,
    )
    persona_collegata = models.ForeignKey(
        "anagrafica.Persona",
        on_delete=models.SET_NULL,
        related_name="profili_lavorativi",
        blank=True,
        null=True,
        help_text="Anagrafica persona condivisa con familiari, educatori e dipendenti.",
    )
    classe_principale = models.ForeignKey(
        "scuola.Classe",
        on_delete=models.SET_NULL,
        related_name="educatori_principali",
        blank=True,
        null=True,
        help_text="Classe di riferimento per gli educatori.",
    )
    gruppo_classe_principale = models.ForeignKey(
        "scuola.GruppoClasse",
        on_delete=models.SET_NULL,
        related_name="educatori_principali",
        blank=True,
        null=True,
        help_text="Gruppo classe o pluriclasse di riferimento per gli educatori.",
    )
    materia = models.CharField(
        max_length=120,
        blank=True,
        help_text="Materia di riferimento per educatori trasversali a piu classi.",
    )
    mansione = models.CharField(max_length=160, blank=True)
    iban = models.CharField(max_length=34, blank=True)
    stato = models.CharField(
        max_length=20,
        choices=StatoDipendente.choices,
        default=StatoDipendente.ATTIVO,
    )
    note = models.TextField(blank=True)
    data_creazione = models.DateTimeField(auto_now_add=True)
    data_aggiornamento = models.DateTimeField(auto_now=True)

    objects = DipendenteQuerySet.as_manager()

    class Meta:
        db_table = "gestione_amministrativa_dipendente"
        ordering = ["persona_collegata__cognome", "persona_collegata__nome"]
        verbose_name = "Dipendente"
        verbose_name_plural = "Dipendenti"

    def __init__(self, *args, **kwargs):
        self._persona_pending_values = {}
        self._persona_dirty_fields = set()
        super().__init__(*args, **kwargs)

    @property
    def formatted_telefono(self):
        from anagrafica.utils import format_phone_number

        return format_phone_number(self.telefono_principale) if self.telefono_principale else ""

    @property
    def indirizzo_effettivo(self):
        from anagrafica.models import _first_principal_link

        link = _first_principal_link(self.indirizzi_anagrafici)
        if link and link.indirizzo_id:
            return link.indirizzo
        return self.persona_collegata.indirizzo_effettivo if self.persona_collegata_id else None

    @property
    def telefono_principale(self):
        from anagrafica.models import _first_principal_link

        link = _first_principal_link(self.telefoni_anagrafici)
        if link and link.numero:
            return link.numero
        return self.persona_collegata.telefono_principale if self.persona_collegata_id else ""

    @property
    def email_principale(self):
        from anagrafica.models import _first_principal_link

        link = _first_principal_link(self.email_anagrafiche)
        if link and link.email:
            return link.email
        return self.persona_collegata.email_principale if self.persona_collegata_id else ""

    def __str__(self):
        return self.nome_completo

    def clean(self):
        super().clean()
        if self.iban:
            self.iban = self.iban.replace(" ", "").upper().strip()
        if not self.is_educatore:
            self.classe_principale = None
            self.gruppo_classe_principale = None
            self.materia = ""
        elif self.materia:
            self.materia = self.materia.strip()
        if not self.is_dipendente_operativo:
            self.mansione = ""
        if self.classe_principale_id and self.gruppo_classe_principale_id:
            raise ValidationError({"classe_principale": "Scegli una sola classe principale o una sola pluriclasse."})

    def _ensure_persona_collegata(self):
        from anagrafica.models import Persona

        pending = getattr(self, "_persona_pending_values", {})
        dirty_fields = getattr(self, "_persona_dirty_fields", set())

        if self.persona_collegata_id:
            if pending:
                for field_name, value in pending.items():
                    setattr(self.persona_collegata, field_name, value)
                    dirty_fields.add(field_name)
                pending.clear()
            if dirty_fields:
                self.persona_collegata.save(update_fields=sorted(dirty_fields) + ["data_aggiornamento"])
                dirty_fields.clear()
            return

        persona_payload = {
            "nome": pending.pop("nome", "") or "",
            "cognome": pending.pop("cognome", "") or "",
        }
        for field_name in (
            "indirizzo",
            "sesso",
            "data_nascita",
            "luogo_nascita",
            "nazione_nascita",
            "luogo_nascita_custom",
            "nazionalita",
            "codice_fiscale",
            "email",
            "telefono",
            "note",
        ):
            if field_name in pending:
                persona_payload[field_name] = pending.pop(field_name)
        self.persona_collegata = Persona.objects.create(**persona_payload)
        dirty_fields.clear()

    def save(self, *args, **kwargs):
        self._ensure_persona_collegata()
        super().save(*args, **kwargs)

    @property
    def nome_completo(self):
        return self.persona_collegata.nome_completo if self.persona_collegata_id else ""

    @property
    def nome(self):
        return self.persona_collegata.nome if self.persona_collegata_id else ""

    @nome.setter
    def nome(self, value):
        self._set_persona_field("nome", value or "")

    @property
    def cognome(self):
        return self.persona_collegata.cognome if self.persona_collegata_id else ""

    @cognome.setter
    def cognome(self, value):
        self._set_persona_field("cognome", value or "")

    @property
    def codice_fiscale(self):
        return self.persona_collegata.codice_fiscale if self.persona_collegata_id else ""

    @codice_fiscale.setter
    def codice_fiscale(self, value):
        self._set_persona_field("codice_fiscale", (value or "").upper().strip())

    @property
    def sesso(self):
        return self.persona_collegata.sesso if self.persona_collegata_id else ""

    @sesso.setter
    def sesso(self, value):
        self._set_persona_field("sesso", value or "")

    @property
    def data_nascita(self):
        return self.persona_collegata.data_nascita if self.persona_collegata_id else None

    @data_nascita.setter
    def data_nascita(self, value):
        self._set_persona_field("data_nascita", value)

    @property
    def luogo_nascita(self):
        return self.persona_collegata.luogo_nascita_display if self.persona_collegata_id else ""

    @luogo_nascita.setter
    def luogo_nascita(self, value):
        if hasattr(value, "pk"):
            self._set_persona_field("luogo_nascita", value)
            self._set_persona_field("luogo_nascita_custom", "")
        else:
            self._set_persona_field("luogo_nascita", None)
            self._set_persona_field("luogo_nascita_custom", value or "")

    @property
    def nazionalita(self):
        return self.persona_collegata.nazionalita_display if self.persona_collegata_id else ""

    @nazionalita.setter
    def nazionalita(self, value):
        if hasattr(value, "pk"):
            self._set_persona_field("nazionalita", value)
            return
        label = (value or "").strip()
        if not label:
            self._set_persona_field("nazionalita", None)
            return
        from anagrafica.models import Nazione

        nazione = (
            Nazione.objects.filter(nome_nazionalita__iexact=label, attiva=True).first()
            or Nazione.objects.filter(nome__iexact=label, attiva=True).first()
        )
        self._set_persona_field("nazionalita", nazione)

    @property
    def email(self):
        return self.persona_collegata.email if self.persona_collegata_id else ""

    @email.setter
    def email(self, value):
        self._set_persona_field("email", value or "")

    @property
    def telefono(self):
        return self.persona_collegata.telefono if self.persona_collegata_id else ""

    @telefono.setter
    def telefono(self, value):
        self._set_persona_field("telefono", value or "")

    @property
    def indirizzo(self):
        return self.persona_collegata.indirizzo if self.persona_collegata_id else None

    @indirizzo.setter
    def indirizzo(self, value):
        self._set_persona_field("indirizzo", value)

    @property
    def familiare_collegato(self):
        if not self.persona_collegata_id:
            return None
        try:
            return self.persona_collegata.profilo_familiare
        except Exception:
            return None

    @familiare_collegato.setter
    def familiare_collegato(self, value):
        self.persona_collegata = value.persona if value and value.persona_id else None

    @property
    def familiare_collegato_id(self):
        familiare = self.familiare_collegato
        return familiare.pk if familiare else None

    @property
    def codice_dipendente(self):
        return ""

    @codice_dipendente.setter
    def codice_dipendente(self, value):
        return None

    @property
    def ruolo_anagrafico(self):
        return self.ruolo_aziendale

    @ruolo_anagrafico.setter
    def ruolo_anagrafico(self, value):
        self.ruolo_aziendale = value

    def _set_persona_field(self, field_name, value):
        if not self.persona_collegata_id:
            self._persona_pending_values[field_name] = value
            return
        setattr(self.persona_collegata, field_name, value)
        self._persona_dirty_fields.add(field_name)

    @property
    def classe_principale_label(self):
        if self.gruppo_classe_principale_id:
            return str(self.gruppo_classe_principale)
        if self.classe_principale_id:
            return str(self.classe_principale)
        return ""

    @property
    def classe_principale_tipo_label(self):
        if self.gruppo_classe_principale_id:
            return "Gruppo classe"
        if self.classe_principale_id:
            return "Classe"
        return ""

    @property
    def materia_label(self):
        return (self.materia or "").strip()

    @property
    def is_educatore(self):
        return self.ruolo_aziendale == RuoloAziendaleDipendente.EDUCATORE

    @property
    def is_dipendente_operativo(self):
        return self.ruolo_aziendale == RuoloAziendaleDipendente.DIPENDENTE

    @property
    def contratto_corrente(self):
        oggi = timezone.localdate()
        return (
            self.contratti.filter(attivo=True)
            .filter(data_inizio__lte=oggi)
            .filter(Q(data_fine__isnull=True) | Q(data_fine__gte=oggi))
            .order_by("-data_inizio", "-id")
            .first()
        )


class ContrattoDipendente(models.Model):
    dipendente = models.ForeignKey(
        Dipendente,
        on_delete=models.CASCADE,
        related_name="contratti",
        blank=True,
        null=True,
    )
    descrizione = models.CharField(max_length=180, blank=True)
    tipo_contratto = models.ForeignKey(
        TipoContrattoDipendente,
        on_delete=models.PROTECT,
        related_name="contratti",
        null=True,
    )
    parametro_calcolo = models.ForeignKey(
        "ParametroCalcoloStipendio",
        on_delete=models.SET_NULL,
        related_name="contratti",
        blank=True,
        null=True,
    )
    data_inizio = models.DateField()
    data_fine = models.DateField(blank=True, null=True)
    ccnl = models.CharField(max_length=120, blank=True)
    livello = models.CharField(max_length=60, blank=True)
    qualifica = models.CharField(max_length=120, blank=True)
    mansione = models.CharField(max_length=160, blank=True)
    regime_orario = models.CharField(
        max_length=30,
        choices=RegimeOrarioDipendente.choices,
        default=RegimeOrarioDipendente.TEMPO_PIENO,
    )
    ore_settimanali = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    percentuale_part_time = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=ONE_HUNDRED,
        validators=[MinValueValidator(Decimal("0.00")), MaxValueValidator(ONE_HUNDRED)],
    )
    retribuzione_lorda_mensile = models.DecimalField(max_digits=12, decimal_places=2, default=ZERO)
    tariffa_oraria = models.DecimalField(max_digits=12, decimal_places=2, default=ZERO)
    superminimo_mensile = models.DecimalField(max_digits=12, decimal_places=2, default=ZERO)
    indennita_fisse_mensili = models.DecimalField(max_digits=12, decimal_places=2, default=ZERO)
    mensilita_annue = models.DecimalField(
        max_digits=4,
        decimal_places=2,
        default=Decimal("13.00"),
        validators=[MinValueValidator(Decimal("1.00"))],
    )
    valuta = models.CharField(max_length=3, default="EUR")
    attivo = models.BooleanField(default=True)
    note = models.TextField(blank=True)
    data_creazione = models.DateTimeField(auto_now_add=True)
    data_aggiornamento = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "gestione_amministrativa_contratto_dipendente"
        ordering = ["dipendente__persona_collegata__cognome", "dipendente__persona_collegata__nome", "-data_inizio"]
        verbose_name = "Contratto dipendente"
        verbose_name_plural = "Contratti dipendenti"
        indexes = [
            models.Index(fields=["dipendente", "data_inizio"], name="ga_contr_dip_data_idx"),
            models.Index(fields=["attivo"], name="ga_contr_attivo_idx"),
        ]

    def __str__(self):
        label = self.descrizione or str(self.tipo_contratto or "")
        if not label:
            label = "Contratto"
        if self.dipendente_id:
            return f"{self.dipendente} - {label}"
        return label

    def label_select(self, include_dipendente=True):
        parti = []
        if include_dipendente and self.dipendente_id:
            parti.append(str(self.dipendente))
        if self.descrizione:
            parti.append(self.descrizione)
        elif self.tipo_contratto_id:
            parti.append(str(self.tipo_contratto))
        if self.data_inizio:
            periodo = f"dal {self.data_inizio:%d/%m/%Y}"
            if self.data_fine:
                periodo = f"{periodo} al {self.data_fine:%d/%m/%Y}"
            parti.append(periodo)
        if self.retribuzione_lorda_totale_mensile:
            parti.append(f"{self.retribuzione_lorda_totale_mensile} {self.valuta}")
        return " - ".join(parti) or "Contratto"

    def clean(self):
        super().clean()
        if self.data_fine and self.data_fine < self.data_inizio:
            raise ValidationError({"data_fine": "La data fine non puo' precedere la data inizio."})
        if self.regime_orario == RegimeOrarioDipendente.TEMPO_PIENO:
            self.percentuale_part_time = ONE_HUNDRED

    @property
    def retribuzione_lorda_totale_mensile(self):
        return (
            (self.retribuzione_lorda_mensile or ZERO)
            + (self.superminimo_mensile or ZERO)
            + (self.indennita_fisse_mensili or ZERO)
        )


class SimulazioneCostoDipendente(models.Model):
    contratto = models.ForeignKey(
        ContrattoDipendente,
        on_delete=models.CASCADE,
        related_name="simulazioni_costo",
    )
    titolo = models.CharField(max_length=180, blank=True)
    data_elaborazione = models.DateField(blank=True, null=True)
    valido_dal = models.DateField()
    valido_al = models.DateField(blank=True, null=True)

    netto_mensile = models.DecimalField(max_digits=12, decimal_places=2, default=ZERO)
    lordo_mensile = models.DecimalField(max_digits=12, decimal_places=2, default=ZERO)
    costo_azienda_mensile = models.DecimalField(max_digits=12, decimal_places=2, default=ZERO)
    contributi_previdenziali_azienda = models.DecimalField(max_digits=12, decimal_places=2, default=ZERO)
    contributi_assicurativi_azienda = models.DecimalField(max_digits=12, decimal_places=2, default=ZERO)
    contributi_previdenza_complementare_azienda = models.DecimalField(max_digits=12, decimal_places=2, default=ZERO)
    contributi_previdenziali_dipendente = models.DecimalField(max_digits=12, decimal_places=2, default=ZERO)
    contributi_assicurativi_dipendente = models.DecimalField(max_digits=12, decimal_places=2, default=ZERO)
    contributi_previdenza_complementare_dipendente = models.DecimalField(max_digits=12, decimal_places=2, default=ZERO)
    irpef_lorda = models.DecimalField(max_digits=12, decimal_places=2, default=ZERO)
    irpef_netto = models.DecimalField(max_digits=12, decimal_places=2, default=ZERO)
    addizionale_regionale = models.DecimalField(max_digits=12, decimal_places=2, default=ZERO)
    addizionale_comunale = models.DecimalField(max_digits=12, decimal_places=2, default=ZERO)
    bonus_fiscali = models.DecimalField(max_digits=12, decimal_places=2, default=ZERO)
    trattamento_fine_rapporto = models.DecimalField(max_digits=12, decimal_places=2, default=ZERO)
    costo_mensilita_aggiuntive = models.DecimalField(max_digits=12, decimal_places=2, default=ZERO)
    costo_rateo_ferie = models.DecimalField(max_digits=12, decimal_places=2, default=ZERO)
    costo_rateo_permessi = models.DecimalField(max_digits=12, decimal_places=2, default=ZERO)
    costo_rateo_rol = models.DecimalField(max_digits=12, decimal_places=2, default=ZERO)
    costo_rateo_ex_festivita = models.DecimalField(max_digits=12, decimal_places=2, default=ZERO)

    mensilita_annue = models.DecimalField(
        max_digits=4,
        decimal_places=2,
        default=Decimal("13.00"),
        validators=[MinValueValidator(Decimal("1.00"))],
    )
    ore_mensili = models.DecimalField(max_digits=7, decimal_places=2, default=ZERO)
    giorni_mensili = models.DecimalField(max_digits=7, decimal_places=2, default=ZERO)
    percentuale_part_time = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=ONE_HUNDRED,
        validators=[MinValueValidator(Decimal("0.00")), MaxValueValidator(ONE_HUNDRED)],
    )
    tasso_inail_per_mille = models.DecimalField(max_digits=7, decimal_places=2, default=ZERO)
    livello = models.CharField(max_length=60, blank=True)
    qualifica = models.CharField(max_length=120, blank=True)
    valuta = models.CharField(max_length=3, default="EUR")
    file_simulazione = models.FileField(
        upload_to="gestione_amministrativa/simulazioni_costo/%Y/%m",
        blank=True,
    )
    attiva = models.BooleanField(default=True)
    note = models.TextField(blank=True)
    data_creazione = models.DateTimeField(auto_now_add=True)
    data_aggiornamento = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "gestione_amministrativa_simulazione_costo_dipendente"
        ordering = ["contratto", "-valido_dal", "-id"]
        verbose_name = "Simulazione costo dipendente"
        verbose_name_plural = "Simulazioni costo dipendenti"
        indexes = [
            models.Index(fields=["contratto", "valido_dal"], name="ga_sim_costo_contr_idx"),
            models.Index(fields=["attiva"], name="ga_sim_costo_attiva_idx"),
        ]

    def __str__(self):
        if self.titolo:
            return self.titolo
        return f"Simulazione costo dal {self.valido_dal:%d/%m/%Y}"

    def clean(self):
        super().clean()
        if self.valido_al and self.valido_al < self.valido_dal:
            raise ValidationError({"valido_al": "La data fine validita non puo' precedere la data iniziale."})

    @property
    def contributi_datore_totali(self):
        return (
            (self.contributi_previdenziali_azienda or ZERO)
            + (self.contributi_assicurativi_azienda or ZERO)
            + (self.contributi_previdenza_complementare_azienda or ZERO)
        )

    @property
    def contributi_dipendente_totali(self):
        return (
            (self.contributi_previdenziali_dipendente or ZERO)
            + (self.contributi_assicurativi_dipendente or ZERO)
            + (self.contributi_previdenza_complementare_dipendente or ZERO)
        )

    @property
    def altri_oneri_previsti_totali(self):
        return (
            (self.costo_rateo_ferie or ZERO)
            + (self.costo_rateo_permessi or ZERO)
            + (self.costo_rateo_rol or ZERO)
            + (self.costo_rateo_ex_festivita or ZERO)
        )


class ParametroCalcoloStipendio(models.Model):
    nome = models.CharField(max_length=140)
    valido_dal = models.DateField()
    valido_al = models.DateField(blank=True, null=True)
    aliquota_contributi_datore = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=ZERO,
        validators=[MinValueValidator(ZERO), MaxValueValidator(ONE_HUNDRED)],
        help_text="Percentuale configurabile, non aggiornata automaticamente dal sistema.",
    )
    aliquota_contributi_dipendente = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=ZERO,
        validators=[MinValueValidator(ZERO), MaxValueValidator(ONE_HUNDRED)],
    )
    aliquota_tfr = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=ZERO,
        validators=[MinValueValidator(ZERO), MaxValueValidator(ONE_HUNDRED)],
    )
    aliquota_inail = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=ZERO,
        validators=[MinValueValidator(ZERO), MaxValueValidator(ONE_HUNDRED)],
    )
    aliquota_altri_oneri = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=ZERO,
        validators=[MinValueValidator(ZERO), MaxValueValidator(ONE_HUNDRED)],
    )
    attivo = models.BooleanField(default=True)
    note = models.TextField(blank=True)
    data_creazione = models.DateTimeField(auto_now_add=True)
    data_aggiornamento = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "gestione_amministrativa_parametro_calcolo_stipendio"
        ordering = ["-valido_dal", "nome"]
        verbose_name = "Parametro calcolo stipendio"
        verbose_name_plural = "Parametri calcolo stipendi"
        indexes = [
            models.Index(fields=["valido_dal", "valido_al"], name="ga_param_data_idx"),
            models.Index(fields=["attivo"], name="ga_param_attivo_idx"),
        ]
        constraints = [
            models.UniqueConstraint(fields=["nome", "valido_dal"], name="ga_param_nome_data_unique"),
        ]

    def __str__(self):
        return f"{self.nome} dal {self.valido_dal:%d/%m/%Y}"

    def clean(self):
        super().clean()
        if self.valido_al and self.valido_al < self.valido_dal:
            raise ValidationError({"valido_al": "La data di fine validita non puo' precedere la data iniziale."})


class DatoPayrollUfficiale(models.Model):
    categoria = models.CharField(max_length=40, choices=CategoriaDatoPayrollUfficiale.choices)
    codice = models.CharField(max_length=80)
    nome = models.CharField(max_length=180)
    descrizione = models.TextField(blank=True)
    anno = models.PositiveSmallIntegerField(blank=True, null=True, db_index=True)
    valido_dal = models.DateField(blank=True, null=True)
    valido_al = models.DateField(blank=True, null=True)
    valore_percentuale = models.DecimalField(
        max_digits=8,
        decimal_places=4,
        blank=True,
        null=True,
        validators=[MinValueValidator(ZERO), MaxValueValidator(Decimal("1000.00"))],
    )
    valore_importo = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True)
    valore_testo = models.CharField(max_length=255, blank=True)
    ente = models.CharField(max_length=120, blank=True)
    fonte_url = models.URLField(max_length=500, blank=True)
    data_pubblicazione = models.DateField(blank=True, null=True)
    data_rilevazione = models.DateTimeField(auto_now=True)
    attivo = models.BooleanField(default=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "gestione_amministrativa_dato_payroll_ufficiale"
        ordering = ["categoria", "-anno", "nome", "codice"]
        verbose_name = "Dato payroll ufficiale"
        verbose_name_plural = "Dati payroll ufficiali"
        indexes = [
            models.Index(fields=["categoria", "anno"], name="ga_payroll_cat_anno_idx"),
            models.Index(fields=["attivo"], name="ga_payroll_attivo_idx"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["categoria", "codice", "anno", "valido_dal"],
                name="ga_payroll_dato_unique",
            ),
        ]

    def __str__(self):
        anno = f" {self.anno}" if self.anno else ""
        return f"{self.nome}{anno}"

    @property
    def valore_display(self):
        if self.valore_percentuale is not None:
            return f"{self.valore_percentuale}%"
        if self.valore_importo is not None:
            return f"{self.valore_importo} EUR"
        return self.valore_testo or "-"

    def clean(self):
        super().clean()
        if self.valido_dal and self.valido_al and self.valido_al < self.valido_dal:
            raise ValidationError({"valido_al": "La data di fine validita non puo' precedere la data iniziale."})


class BustaPagaDipendente(models.Model):
    dipendente = models.ForeignKey(
        Dipendente,
        on_delete=models.CASCADE,
        related_name="buste_paga",
    )
    contratto = models.ForeignKey(
        ContrattoDipendente,
        on_delete=models.SET_NULL,
        related_name="buste_paga",
        blank=True,
        null=True,
    )
    anno = models.PositiveSmallIntegerField()
    mese = models.PositiveSmallIntegerField(validators=[MinValueValidator(1), MaxValueValidator(12)])
    stato = models.CharField(
        max_length=20,
        choices=StatoBustaPaga.choices,
        default=StatoBustaPaga.BOZZA,
    )
    valuta = models.CharField(max_length=3, default="EUR")

    lordo_previsto = models.DecimalField(max_digits=12, decimal_places=2, default=ZERO)
    contributi_datore_previsti = models.DecimalField(max_digits=12, decimal_places=2, default=ZERO)
    contributi_dipendente_previsti = models.DecimalField(max_digits=12, decimal_places=2, default=ZERO)
    rateo_tredicesima_previsto = models.DecimalField(max_digits=12, decimal_places=2, default=ZERO)
    rateo_tfr_previsto = models.DecimalField(max_digits=12, decimal_places=2, default=ZERO)
    altri_oneri_previsti = models.DecimalField(max_digits=12, decimal_places=2, default=ZERO)
    netto_previsto = models.DecimalField(max_digits=12, decimal_places=2, default=ZERO)
    costo_azienda_previsto = models.DecimalField(max_digits=12, decimal_places=2, default=ZERO)

    lordo_effettivo = models.DecimalField(max_digits=12, decimal_places=2, default=ZERO)
    contributi_datore_effettivi = models.DecimalField(max_digits=12, decimal_places=2, default=ZERO)
    contributi_dipendente_effettivi = models.DecimalField(max_digits=12, decimal_places=2, default=ZERO)
    rateo_tredicesima_effettivo = models.DecimalField(max_digits=12, decimal_places=2, default=ZERO)
    rateo_tfr_effettivo = models.DecimalField(max_digits=12, decimal_places=2, default=ZERO)
    altri_oneri_effettivi = models.DecimalField(max_digits=12, decimal_places=2, default=ZERO)
    netto_effettivo = models.DecimalField(max_digits=12, decimal_places=2, default=ZERO)
    costo_azienda_effettivo = models.DecimalField(max_digits=12, decimal_places=2, default=ZERO)

    file_busta_paga = models.FileField(
        upload_to="gestione_amministrativa/buste_paga/%Y/%m",
        blank=True,
    )
    data_pagamento_effettiva = models.DateField(blank=True, null=True)
    movimento_pagamento = models.ForeignKey(
        "gestione_finanziaria.MovimentoFinanziario",
        on_delete=models.SET_NULL,
        related_name="buste_paga_dipendenti",
        blank=True,
        null=True,
    )
    note_previsione = models.TextField(blank=True)
    note_effettivo = models.TextField(blank=True)
    data_creazione = models.DateTimeField(auto_now_add=True)
    data_aggiornamento = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "gestione_amministrativa_busta_paga"
        ordering = ["-anno", "-mese", "dipendente__persona_collegata__cognome", "dipendente__persona_collegata__nome"]
        verbose_name = "Busta paga dipendente"
        verbose_name_plural = "Buste paga dipendenti"
        indexes = [
            models.Index(fields=["anno", "mese"], name="ga_busta_periodo_idx"),
            models.Index(fields=["dipendente", "anno", "mese"], name="ga_busta_dip_per_idx"),
            models.Index(fields=["stato"], name="ga_busta_stato_idx"),
        ]
        constraints = [
            models.UniqueConstraint(fields=["dipendente", "anno", "mese"], name="ga_busta_dip_per_unique"),
        ]

    def __str__(self):
        return f"{self.dipendente} - {self.periodo_label}"

    @property
    def periodo_label(self):
        return f"{self.mese:02d}/{self.anno}"

    @property
    def importo_netto_riepilogo(self):
        return self.netto_effettivo or self.netto_previsto or ZERO

    @property
    def costo_azienda_riepilogo(self):
        return self.costo_azienda_effettivo or self.costo_azienda_previsto or ZERO

    @property
    def ha_costo_azienda_riepilogo(self):
        return bool(self.costo_azienda_effettivo or self.costo_azienda_previsto)

    @property
    def risulta_pagata(self):
        return bool(self.data_pagamento_effettiva or self.movimento_pagamento_id)

    @property
    def data_pagamento_suggerita(self):
        if self.data_pagamento_effettiva:
            return self.data_pagamento_effettiva
        last_day = monthrange(self.anno, self.mese)[1]
        return date(self.anno, self.mese, last_day)

    @property
    def ha_previsione(self):
        return any(
            [
                self.lordo_previsto,
                self.netto_previsto,
                self.costo_azienda_previsto,
            ]
        )

    @property
    def ha_effettivo(self):
        return any(
            [
                self.lordo_effettivo,
                self.netto_effettivo,
                self.costo_azienda_effettivo,
                self.file_busta_paga,
            ]
        )

    @property
    def scostamento_costo_azienda(self):
        return (self.costo_azienda_effettivo or ZERO) - (self.costo_azienda_previsto or ZERO)

    @property
    def scostamento_netto(self):
        return (self.netto_effettivo or ZERO) - (self.netto_previsto or ZERO)


class VoceBustaPaga(models.Model):
    busta_paga = models.ForeignKey(
        BustaPagaDipendente,
        on_delete=models.CASCADE,
        related_name="voci",
    )
    scenario = models.CharField(
        max_length=20,
        choices=ScenarioValorePayroll.choices,
        default=ScenarioValorePayroll.PREVISTO,
    )
    tipo_voce = models.CharField(
        max_length=30,
        choices=TipoVocePayroll.choices,
        default=TipoVocePayroll.RETRIBUZIONE,
    )
    codice = models.CharField(max_length=40, blank=True)
    descrizione = models.CharField(max_length=200)
    quantita = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("1.00"))
    importo_unitario = models.DecimalField(max_digits=12, decimal_places=2, default=ZERO)
    importo = models.DecimalField(max_digits=12, decimal_places=2, default=ZERO)
    aliquota_percentuale = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        blank=True,
        null=True,
        validators=[MinValueValidator(ZERO), MaxValueValidator(ONE_HUNDRED)],
    )
    ordine = models.IntegerField(default=0)
    note = models.TextField(blank=True)
    data_creazione = models.DateTimeField(auto_now_add=True)
    data_aggiornamento = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "gestione_amministrativa_voce_busta_paga"
        ordering = ["busta_paga", "scenario", "ordine", "id"]
        verbose_name = "Voce busta paga"
        verbose_name_plural = "Voci busta paga"
        indexes = [
            models.Index(fields=["scenario", "tipo_voce"], name="ga_voce_scenario_idx"),
            models.Index(fields=["busta_paga", "scenario"], name="ga_voce_busta_idx"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["busta_paga", "scenario", "codice"],
                condition=~Q(codice=""),
                name="ga_voce_cod_unique",
            ),
        ]

    def __str__(self):
        return f"{self.busta_paga} - {self.get_scenario_display()} - {self.descrizione}"


class DocumentoDipendente(models.Model):
    dipendente = models.ForeignKey(
        Dipendente,
        on_delete=models.CASCADE,
        related_name="documenti",
    )
    busta_paga = models.ForeignKey(
        BustaPagaDipendente,
        on_delete=models.SET_NULL,
        related_name="documenti",
        blank=True,
        null=True,
    )
    tipo_documento = models.CharField(
        max_length=30,
        choices=TipoDocumentoDipendente.choices,
        default=TipoDocumentoDipendente.ALTRO,
    )
    titolo = models.CharField(max_length=180)
    file = models.FileField(upload_to="gestione_amministrativa/documenti/%Y/%m")
    data_documento = models.DateField(blank=True, null=True)
    note = models.TextField(blank=True)
    data_creazione = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "gestione_amministrativa_documento_dipendente"
        ordering = ["dipendente__persona_collegata__cognome", "dipendente__persona_collegata__nome", "-data_documento", "-id"]
        verbose_name = "Documento dipendente"
        verbose_name_plural = "Documenti dipendenti"
        indexes = [
            models.Index(fields=["dipendente", "tipo_documento"], name="ga_doc_dip_tipo_idx"),
        ]

    def __str__(self):
        return f"{self.dipendente} - {self.titolo}"
