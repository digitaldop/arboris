from datetime import date
from decimal import Decimal

from django import forms
from django.db.models import Q

from anagrafica.contact_services import sync_principal_contacts
from anagrafica.forms import (
    classe_principale_reference_choices,
    classe_principale_reference_initial,
    html5_date_input,
    make_searchable_select,
    split_classe_principale_reference,
)
from anagrafica.models import Citta, Familiare, Indirizzo, Nazione
from anagrafica.utils import validate_and_normalize_phone_number

from .models import (
    BustaPagaDipendente,
    ContrattoDipendente,
    Dipendente,
    ParametroCalcoloStipendio,
    RegimeOrarioDipendente,
    RuoloAnagraficoDipendente,
    SimulazioneCostoDipendente,
    TipoContrattoDipendente,
)


class CittaCodiceCatastaleSelect(forms.Select):
    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        option = super().create_option(name, value, label, selected, index, subindex=subindex, attrs=attrs)
        if value and hasattr(value, "instance"):
            option["attrs"]["data-codice-catastale"] = value.instance.codice_catastale or ""
            nazionalita_label = self.attrs.get("data-default-nazionalita-label", "")
            if nazionalita_label:
                option["attrs"]["data-nazionalita-label"] = nazionalita_label
        return option


class FamiliareCollegatoSelect(forms.Select):
    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        option = super().create_option(name, value, label, selected, index, subindex=subindex, attrs=attrs)
        if value and hasattr(value, "instance"):
            familiare = value.instance
            indirizzo = familiare.indirizzo_effettivo
            option["attrs"].update(
                {
                    "data-nome": familiare.nome or "",
                    "data-cognome": familiare.cognome or "",
                    "data-telefono": familiare.telefono_principale or "",
                    "data-email": familiare.email_principale or "",
                    "data-codice-fiscale": (familiare.codice_fiscale or "").upper().strip(),
                    "data-sesso": familiare.sesso or "",
                    "data-data-nascita": familiare.data_nascita.isoformat() if familiare.data_nascita else "",
                    "data-luogo-nascita-id": familiare.luogo_nascita_id or "",
                    "data-nazionalita-label": familiare.nazionalita_display or "",
                    "data-indirizzo-id": indirizzo.pk if indirizzo else "",
                }
            )
        return option


def default_italia_nazionalita_label():
    italia = (
        Nazione.objects.filter(nome__iexact="Italia", attiva=True)
        .only("nome", "nome_nazionalita")
        .first()
    )
    return italia.label_nazionalita if italia else "Italiana"


def tipo_contratto_queryset(selected_id=None):
    qs_filter = Q(attivo=True)
    if selected_id:
        qs_filter |= Q(pk=selected_id)
    return TipoContrattoDipendente.objects.filter(qs_filter).order_by("ordine", "nome")


def parametro_calcolo_queryset(selected_id=None):
    qs_filter = Q(attivo=True)
    if selected_id:
        qs_filter |= Q(pk=selected_id)
    return ParametroCalcoloStipendio.objects.filter(qs_filter).order_by("-valido_dal", "nome")


PARAMETRO_CALCOLO_PERCENT_FIELDS = [
    "aliquota_contributi_datore",
    "aliquota_contributi_dipendente",
    "aliquota_tfr",
    "aliquota_inail",
    "aliquota_altri_oneri",
]

PARAMETRO_CALCOLO_BASE_ALIQUOTE = {
    "aliquota_contributi_datore": Decimal("30.00"),
    "aliquota_contributi_dipendente": Decimal("9.19"),
    "aliquota_tfr": Decimal("7.41"),
    "aliquota_inail": Decimal("1.00"),
    "aliquota_altri_oneri": Decimal("2.00"),
}


def suggested_parametro_calcolo_name(valid_from):
    base_name = f"Profilo previsionale {valid_from.year}"
    if not ParametroCalcoloStipendio.objects.filter(nome=base_name, valido_dal=valid_from).exists():
        return base_name
    suffix = 2
    while True:
        name = f"{base_name} ({suffix})"
        if not ParametroCalcoloStipendio.objects.filter(nome=name, valido_dal=valid_from).exists():
            return name
        suffix += 1


class DipendenteForm(forms.ModelForm):
    classe_principale_ref = forms.ChoiceField(
        choices=[],
        required=False,
        label="Classe principale",
        help_text="Per gli educatori, collega una classe o un gruppo classe di riferimento.",
    )
    contratto = forms.ModelChoiceField(
        queryset=ContrattoDipendente.objects.none(),
        required=False,
        label="Contratto",
    )
    luogo_nascita = forms.ModelChoiceField(
        queryset=Citta.objects.none(),
        required=False,
        label="Luogo di nascita",
        widget=CittaCodiceCatastaleSelect(),
    )

    class Meta:
        model = Dipendente
        fields = [
            "ruolo_anagrafico",
            "familiare_collegato",
            "classe_principale_ref",
            "mansione",
            "nome",
            "cognome",
            "data_nascita",
            "luogo_nascita",
            "nazionalita",
            "sesso",
            "codice_fiscale",
            "indirizzo",
            "telefono",
            "email",
            "iban",
            "codice_dipendente",
            "stato",
            "data_assunzione",
            "data_cessazione",
            "note",
        ]
        labels = {
            "ruolo_anagrafico": "Profilo anagrafico",
            "familiare_collegato": "Familiare collegato",
            "mansione": "Mansione",
            "codice_dipendente": "Matricola / codice interno",
            "nome": "Nome",
            "cognome": "Cognome",
            "codice_fiscale": "Codice fiscale",
            "data_nascita": "Data nascita",
            "luogo_nascita": "Luogo nascita",
            "nazionalita": "Nazionalita",
            "sesso": "Sesso",
            "email": "Email",
            "telefono": "Telefono",
            "indirizzo": "Indirizzo",
            "iban": "IBAN",
            "stato": "Stato",
            "data_assunzione": "Data assunzione",
            "data_cessazione": "Data cessazione",
            "note": "Note",
        }
        widgets = {
            "data_nascita": html5_date_input(),
            "data_assunzione": html5_date_input(),
            "data_cessazione": html5_date_input(),
            "note": forms.Textarea(attrs={"rows": 4}),
            "iban": forms.TextInput(attrs={"placeholder": "IT00X0000000000000000000000"}),
            "mansione": forms.TextInput(attrs={"placeholder": "Es. Segreteria, cucina, amministrazione..."}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        optional_fields = [
            "codice_dipendente",
            "familiare_collegato",
            "classe_principale_ref",
            "mansione",
            "codice_fiscale",
            "data_nascita",
            "luogo_nascita",
            "nazionalita",
            "sesso",
            "email",
            "telefono",
            "indirizzo",
            "iban",
            "data_assunzione",
            "data_cessazione",
            "note",
        ]
        for field_name in optional_fields:
            self.fields[field_name].required = False

        self.fields["ruolo_anagrafico"].choices = RuoloAnagraficoDipendente.choices
        linked_familiare_id = self.data.get(self.add_prefix("familiare_collegato")) if self.is_bound else None
        if linked_familiare_id:
            self.fields["nome"].required = False
            self.fields["cognome"].required = False

        familiare_filter = Q(profilo_lavorativo__isnull=True)
        if getattr(self.instance, "familiare_collegato_id", None):
            familiare_filter |= Q(pk=self.instance.familiare_collegato_id)
        familiare_widget_attrs = self.fields["familiare_collegato"].widget.attrs.copy()
        self.fields["familiare_collegato"].widget = FamiliareCollegatoSelect(attrs=familiare_widget_attrs)
        self.fields["familiare_collegato"].queryset = (
            Familiare.objects.select_related(
                "relazione_familiare",
                "indirizzo",
                "indirizzo__citta",
                "indirizzo__provincia",
                "luogo_nascita",
                "luogo_nascita__provincia",
                "nazionalita",
            )
            .filter(familiare_filter)
            .order_by("cognome", "nome")
        )
        self.fields["familiare_collegato"].label_from_instance = lambda obj: str(obj)
        make_searchable_select(self.fields["familiare_collegato"], "Cerca un familiare gia presente...")
        self.fields["familiare_collegato"].empty_label = "--- nessun familiare collegato ---"

        self.fields["classe_principale_ref"].choices = classe_principale_reference_choices(
            selected_classe_id=getattr(self.instance, "classe_principale_id", None),
            selected_gruppo_id=getattr(self.instance, "gruppo_classe_principale_id", None),
        )
        make_searchable_select(self.fields["classe_principale_ref"], "Cerca una classe o pluriclasse...")
        if not self.is_bound:
            self.initial["classe_principale_ref"] = classe_principale_reference_initial(self.instance)

        self.fields["luogo_nascita"].queryset = (
            Citta.objects.filter(attiva=True).select_related("provincia").order_by("nome")
        )
        self.fields["luogo_nascita"].label_from_instance = lambda obj: f"{obj.nome} ({obj.provincia.sigla})"
        default_nazionalita = default_italia_nazionalita_label()
        self.fields["luogo_nascita"].widget.attrs["data-default-nazionalita-label"] = default_nazionalita
        self.fields["nazionalita"].widget.attrs.update(
            {
                "data-default-nazionalita-label": default_nazionalita,
                "placeholder": default_nazionalita,
            }
        )
        make_searchable_select(self.fields["luogo_nascita"], "Cerca una citta...")

        self.fields["indirizzo"].queryset = (
            Indirizzo.objects.select_related("citta", "provincia", "regione").order_by("via", "numero_civico")
        )
        self.fields["indirizzo"].label_from_instance = lambda obj: obj.label_select()
        make_searchable_select(self.fields["indirizzo"], "Cerca un indirizzo...")
        self.fields["indirizzo"].empty_label = "--- nessun indirizzo collegato ---"
        self._setup_contratto_field()
        self.fields["codice_dipendente"].help_text = (
            "Campo opzionale per una matricola interna, un codice consulente paghe o un identificativo usato nei file esterni."
        )
        self.fields["nome"].widget.attrs["data-cf-nome"] = "1"
        self.fields["cognome"].widget.attrs["data-cf-cognome"] = "1"
        self.fields["data_nascita"].widget.attrs["data-cf-data-nascita"] = "1"
        self.fields["sesso"].widget.attrs["data-cf-sesso"] = "1"
        self.fields["luogo_nascita"].widget.attrs["data-cf-luogo-id"] = "1"
        self.fields["codice_fiscale"].widget.attrs["data-cf-output"] = "1"

        if self.is_bound:
            return

        if not getattr(self.instance, "pk", None) and not self.initial.get("nazionalita"):
            self.initial["nazionalita"] = default_nazionalita
            self.fields["nazionalita"].initial = default_nazionalita

        luogo_nascita_value = (getattr(self.instance, "luogo_nascita", "") or "").strip()
        if luogo_nascita_value:
            citta = self._find_citta_from_label(luogo_nascita_value)
            if citta:
                self.initial["luogo_nascita"] = citta.pk
                self.fields["luogo_nascita"].widget.attrs["data-codice-catastale"] = citta.codice_catastale or ""

    def _setup_contratto_field(self):
        contratto_id = self.data.get(self.add_prefix("contratto")) if self.is_bound else self.initial.get("contratto")
        if not contratto_id and getattr(self.instance, "pk", None):
            contratto_corrente = self.instance.contratto_corrente
            if contratto_corrente:
                contratto_id = contratto_corrente.pk
                self.initial["contratto"] = contratto_corrente.pk

        qs_filter = Q(dipendente__isnull=True)
        if getattr(self.instance, "pk", None):
            qs_filter |= Q(dipendente=self.instance)
        if contratto_id:
            qs_filter |= Q(pk=contratto_id)

        self.fields["contratto"].queryset = (
            ContrattoDipendente.objects.select_related("dipendente", "tipo_contratto")
            .filter(qs_filter)
            .order_by("-data_inizio", "-id")
        )
        self.fields["contratto"].label_from_instance = lambda obj: obj.label_select(include_dipendente=False)
        make_searchable_select(self.fields["contratto"], "Cerca un contratto...")
        self.fields["contratto"].empty_label = "--- nessun contratto collegato ---"

    @staticmethod
    def _find_citta_from_label(value):
        value = (value or "").strip()
        if not value:
            return None

        if value.endswith(")") and " (" in value:
            nome, sigla = value.rsplit(" (", 1)
            sigla = sigla.rstrip(")")
            return (
                Citta.objects.filter(nome__iexact=nome.strip(), provincia__sigla__iexact=sigla.strip(), attiva=True)
                .select_related("provincia")
                .first()
            )

        qs = Citta.objects.filter(nome__iexact=value, attiva=True).select_related("provincia")
        return qs.first() if qs.count() == 1 else None

    def save(self, commit=True):
        dipendente = super().save(commit=False)
        familiare = self.cleaned_data.get("familiare_collegato")
        if familiare:
            self._apply_familiare_to_dipendente(dipendente, familiare)
        else:
            citta = self.cleaned_data.get("luogo_nascita")
            dipendente.luogo_nascita = f"{citta.nome} ({citta.provincia.sigla})" if citta else ""

        classe_id, gruppo_id = split_classe_principale_reference(self.cleaned_data.get("classe_principale_ref"))
        if dipendente.is_educatore:
            dipendente.classe_principale_id = classe_id
            dipendente.gruppo_classe_principale_id = gruppo_id
        else:
            dipendente.classe_principale = None
            dipendente.gruppo_classe_principale = None
        if not dipendente.is_dipendente_operativo:
            dipendente.mansione = ""
        if commit:
            dipendente.save()
            self.save_m2m()
            sync_principal_contacts(
                dipendente,
                indirizzo=dipendente.indirizzo,
                telefono=dipendente.telefono,
                email=dipendente.email,
            )
            contratto = self.cleaned_data.get("contratto")
            if contratto and contratto.dipendente_id != dipendente.pk:
                contratto.dipendente = dipendente
                contratto.save(update_fields=["dipendente"])
        return dipendente

    @staticmethod
    def _apply_familiare_to_dipendente(dipendente, familiare):
        indirizzo = familiare.indirizzo_effettivo
        dipendente.nome = familiare.nome or ""
        dipendente.cognome = familiare.cognome or ""
        dipendente.codice_fiscale = (familiare.codice_fiscale or "").upper().strip()
        dipendente.sesso = familiare.sesso or ""
        dipendente.data_nascita = familiare.data_nascita
        dipendente.luogo_nascita = (familiare.luogo_nascita_display or "")[:120]
        dipendente.nazionalita = (familiare.nazionalita_display or "")[:80]
        dipendente.email = familiare.email_principale or ""
        dipendente.telefono = familiare.telefono_principale or ""
        dipendente.indirizzo = indirizzo

    def clean_telefono(self):
        return validate_and_normalize_phone_number(self.cleaned_data.get("telefono"))

    def clean_contratto(self):
        contratto = self.cleaned_data.get("contratto")
        if not contratto:
            return contratto
        instance_pk = getattr(self.instance, "pk", None)
        if contratto.dipendente_id and contratto.dipendente_id != instance_pk:
            raise forms.ValidationError("Il contratto selezionato appartiene a un altro dipendente.")
        return contratto


class ContrattoDipendenteForm(forms.ModelForm):
    costo_azienda_ipotizzato = forms.DecimalField(
        label="Costo aziendale ipotizzato",
        max_digits=12,
        decimal_places=2,
        min_value=Decimal("0.00"),
        required=True,
        widget=forms.NumberInput(attrs={"step": "0.01", "inputmode": "decimal", "placeholder": "0,00"}),
    )
    lordo_ipotizzato = forms.DecimalField(
        label="Lordo ipotizzato",
        max_digits=12,
        decimal_places=2,
        min_value=Decimal("0.00"),
        required=True,
        widget=forms.NumberInput(attrs={"step": "0.01", "inputmode": "decimal", "placeholder": "0,00"}),
    )
    netto_ipotizzato = forms.DecimalField(
        label="Netto ipotizzato",
        max_digits=12,
        decimal_places=2,
        min_value=Decimal("0.00"),
        required=True,
        widget=forms.NumberInput(attrs={"step": "0.01", "inputmode": "decimal", "placeholder": "0,00"}),
    )
    contributi_mensili_ipotizzati = forms.DecimalField(
        label="Contributi mensili ipotizzati",
        max_digits=12,
        decimal_places=2,
        min_value=Decimal("0.00"),
        required=False,
        widget=forms.NumberInput(attrs={"step": "0.01", "inputmode": "decimal", "placeholder": "Automatico"}),
        help_text="Se lasciato vuoto, Arboris stima il valore come differenza fra costo aziendale e lordo.",
    )

    class Meta:
        model = ContrattoDipendente
        fields = [
            "descrizione",
            "tipo_contratto",
            "parametro_calcolo",
            "data_inizio",
            "data_fine",
            "ccnl",
            "livello",
            "qualifica",
            "mansione",
            "regime_orario",
            "ore_settimanali",
            "percentuale_part_time",
            "retribuzione_lorda_mensile",
            "tariffa_oraria",
            "superminimo_mensile",
            "indennita_fisse_mensili",
            "mensilita_annue",
            "valuta",
            "attivo",
            "note",
        ]
        labels = {
            "descrizione": "Descrizione",
            "tipo_contratto": "Tipo contratto",
            "parametro_calcolo": "Parametro di calcolo",
            "data_inizio": "Data inizio",
            "data_fine": "Data fine",
            "ccnl": "CCNL",
            "livello": "Livello",
            "qualifica": "Qualifica",
            "mansione": "Mansione",
            "regime_orario": "Regime orario",
            "ore_settimanali": "Ore settimanali",
            "percentuale_part_time": "Percentuale part-time",
            "retribuzione_lorda_mensile": "Compenso lordo mensile",
            "tariffa_oraria": "Tariffa oraria",
            "superminimo_mensile": "Superminimo mensile",
            "indennita_fisse_mensili": "Indennita fisse mensili",
            "mensilita_annue": "Mensilita annue",
            "valuta": "Valuta",
            "attivo": "Attivo",
            "note": "Note",
        }
        widgets = {
            "data_inizio": html5_date_input(),
            "data_fine": html5_date_input(),
            "note": forms.Textarea(attrs={"rows": 3}),
            "valuta": forms.TextInput(attrs={"placeholder": "EUR"}),
        }

    def __init__(self, *args, **kwargs):
        self.detailed_mode = kwargs.pop("detailed_mode", False)
        super().__init__(*args, **kwargs)
        self.simple_mode = not self.detailed_mode
        tipo_contratto_id = self.data.get(self.add_prefix("tipo_contratto")) if self.is_bound else self.initial.get(
            "tipo_contratto",
            getattr(self.instance, "tipo_contratto_id", None),
        )
        self.fields["tipo_contratto"].queryset = tipo_contratto_queryset(tipo_contratto_id)
        make_searchable_select(self.fields["tipo_contratto"], "Cerca un tipo di contratto...")
        parametro_calcolo_id = (
            self.data.get(self.add_prefix("parametro_calcolo"))
            if self.is_bound
            else self.initial.get(
                "parametro_calcolo",
                getattr(self.instance, "parametro_calcolo_id", None),
            )
        )
        self.fields["parametro_calcolo"].queryset = parametro_calcolo_queryset(parametro_calcolo_id)
        self.fields["parametro_calcolo"].empty_label = "--- parametro automatico per periodo ---"
        make_searchable_select(self.fields["parametro_calcolo"], "Cerca un parametro di calcolo...")
        optional_fields = [
            "descrizione",
            "parametro_calcolo",
            "data_fine",
            "ccnl",
            "livello",
            "qualifica",
            "mansione",
            "note",
        ]
        for field_name in optional_fields:
            self.fields[field_name].required = False
        if self.simple_mode:
            self._setup_simple_mode()
        else:
            for field_name in [
                "costo_azienda_ipotizzato",
                "lordo_ipotizzato",
                "netto_ipotizzato",
                "contributi_mensili_ipotizzati",
            ]:
                self.fields[field_name].required = False

    def _setup_simple_mode(self):
        technical_fields = [
            "parametro_calcolo",
            "ccnl",
            "livello",
            "qualifica",
            "regime_orario",
            "ore_settimanali",
            "percentuale_part_time",
            "retribuzione_lorda_mensile",
            "tariffa_oraria",
            "superminimo_mensile",
            "indennita_fisse_mensili",
        ]
        for field_name in technical_fields:
            self.fields[field_name].required = False

        if self.is_bound:
            return

        simulazione = None
        if getattr(self.instance, "pk", None):
            simulazione = (
                self.instance.simulazioni_costo.filter(attiva=True)
                .order_by("-valido_dal", "-id")
                .first()
            )

        costo = getattr(simulazione, "costo_azienda_mensile", None)
        lordo = getattr(simulazione, "lordo_mensile", None)
        netto = getattr(simulazione, "netto_mensile", None)
        contributi = getattr(simulazione, "contributi_datore_totali", None)

        if costo is None:
            costo = getattr(self.instance, "retribuzione_lorda_totale_mensile", Decimal("0.00")) or Decimal("0.00")
        if lordo is None:
            lordo = getattr(self.instance, "retribuzione_lorda_totale_mensile", Decimal("0.00")) or Decimal("0.00")
        if netto is None:
            netto = Decimal("0.00")
        if contributi is None:
            contributi = max((costo or Decimal("0.00")) - (lordo or Decimal("0.00")), Decimal("0.00"))

        self.initial.setdefault("costo_azienda_ipotizzato", costo)
        self.initial.setdefault("lordo_ipotizzato", lordo)
        self.initial.setdefault("netto_ipotizzato", netto)
        self.initial.setdefault("contributi_mensili_ipotizzati", contributi)

    def save(self, commit=True):
        contratto = super().save(commit=False)

        if self.simple_mode:
            lordo = self.cleaned_data.get("lordo_ipotizzato") or Decimal("0.00")
            contratto.regime_orario = RegimeOrarioDipendente.TEMPO_PIENO
            contratto.ore_settimanali = Decimal("0.00")
            contratto.percentuale_part_time = Decimal("100.00")
            contratto.retribuzione_lorda_mensile = lordo
            contratto.tariffa_oraria = Decimal("0.00")
            contratto.superminimo_mensile = Decimal("0.00")
            contratto.indennita_fisse_mensili = Decimal("0.00")
            contratto.parametro_calcolo = None
            contratto.ccnl = ""
            contratto.livello = ""
            contratto.qualifica = ""

        if commit:
            contratto.save()
            self.save_m2m()
            if self.simple_mode:
                self._save_simple_simulation(contratto)

        return contratto

    def _save_simple_simulation(self, contratto):
        costo = self.cleaned_data.get("costo_azienda_ipotizzato") or Decimal("0.00")
        lordo = self.cleaned_data.get("lordo_ipotizzato") or Decimal("0.00")
        netto = self.cleaned_data.get("netto_ipotizzato") or Decimal("0.00")
        contributi = self.cleaned_data.get("contributi_mensili_ipotizzati")
        if contributi is None:
            contributi = max(costo - lordo, Decimal("0.00"))

        simulazione = (
            contratto.simulazioni_costo.filter(attiva=True)
            .order_by("-valido_dal", "-id")
            .first()
        )
        if simulazione is None:
            simulazione = SimulazioneCostoDipendente(contratto=contratto)

        simulazione.titolo = "Profilo previsionale semplificato"
        simulazione.valido_dal = contratto.data_inizio
        simulazione.valido_al = contratto.data_fine
        simulazione.netto_mensile = netto
        simulazione.lordo_mensile = lordo
        simulazione.costo_azienda_mensile = costo
        simulazione.contributi_previdenziali_azienda = contributi
        simulazione.contributi_assicurativi_azienda = Decimal("0.00")
        simulazione.contributi_previdenza_complementare_azienda = Decimal("0.00")
        simulazione.mensilita_annue = contratto.mensilita_annue
        simulazione.percentuale_part_time = Decimal("100.00")
        simulazione.livello = ""
        simulazione.qualifica = contratto.mansione or ""
        simulazione.valuta = contratto.valuta
        simulazione.attiva = True
        simulazione.note = (
            "Simulazione generata dalla gestione semplificata dipendenti. "
            "Usata per budgeting e confronti con le buste paga reali."
        )
        simulazione.save()


class TipoContrattoDipendenteForm(forms.ModelForm):
    class Meta:
        model = TipoContrattoDipendente
        fields = ["nome", "ordine", "attivo", "note"]
        labels = {
            "nome": "Tipo di contratto",
            "ordine": "Ordine",
            "attivo": "Attivo",
            "note": "Note",
        }
        widgets = {
            "note": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["ordine"].required = False
        self.fields["note"].required = False


class ParametroCalcoloStipendioForm(forms.ModelForm):
    class Meta:
        model = ParametroCalcoloStipendio
        fields = [
            "nome",
            "valido_dal",
            "valido_al",
            "aliquota_contributi_datore",
            "aliquota_contributi_dipendente",
            "aliquota_tfr",
            "aliquota_inail",
            "aliquota_altri_oneri",
            "attivo",
            "note",
        ]
        labels = {
            "nome": "Nome parametro",
            "valido_dal": "Valido dal",
            "valido_al": "Valido al",
            "aliquota_contributi_datore": "Contributi datore (%)",
            "aliquota_contributi_dipendente": "Contributi dipendente (%)",
            "aliquota_tfr": "TFR (%)",
            "aliquota_inail": "INAIL (%)",
            "aliquota_altri_oneri": "Altri oneri (%)",
            "attivo": "Attivo",
            "note": "Note",
        }
        widgets = {
            "valido_dal": forms.DateInput(attrs={"placeholder": "gg/mm/aaaa"}),
            "valido_al": forms.DateInput(attrs={"placeholder": "gg/mm/aaaa"}),
            "note": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["valido_al"].required = False
        self.fields["note"].required = False
        self.prefill_source_label = ""
        self.prefill_warning = ""
        self.setup_initial_profile()

    def setup_initial_profile(self):
        if self.is_bound or self.instance.pk:
            return

        valid_from = date.today()
        defaults = {
            "nome": suggested_parametro_calcolo_name(valid_from),
            "valido_dal": valid_from,
            "valido_al": None,
            "attivo": True,
        }
        latest = (
            ParametroCalcoloStipendio.objects.filter(attivo=True)
            .order_by("-valido_dal", "-id")
            .first()
        )
        if latest:
            for field_name in PARAMETRO_CALCOLO_PERCENT_FIELDS:
                defaults[field_name] = getattr(latest, field_name)
            self.prefill_source_label = f"Aliquote copiate dall'ultimo parametro attivo: {latest.nome}"
            self.prefill_warning = (
                "Controlla comunque le percentuali prima del salvataggio: INPS, INAIL e oneri possono variare "
                "per contratto, qualifica, posizione aziendale e voce tariffa."
            )
        else:
            defaults.update(PARAMETRO_CALCOLO_BASE_ALIQUOTE)
            self.prefill_source_label = "Profilo indicativo iniziale precompilato"
            self.prefill_warning = (
                "Sono valori prudenziali per preventivazione, non aliquote ufficiali gia' validate: "
                "vanno verificati con consulente del lavoro prima dell'uso operativo."
            )

        for field_name, value in defaults.items():
            if field_name in self.fields and field_name not in self.initial:
                self.initial[field_name] = value


class SimulazioneCostoDipendenteForm(forms.ModelForm):
    class Meta:
        model = SimulazioneCostoDipendente
        fields = [
            "contratto",
            "titolo",
            "data_elaborazione",
            "valido_dal",
            "valido_al",
            "netto_mensile",
            "lordo_mensile",
            "costo_azienda_mensile",
            "contributi_previdenziali_azienda",
            "contributi_assicurativi_azienda",
            "contributi_previdenza_complementare_azienda",
            "contributi_previdenziali_dipendente",
            "contributi_assicurativi_dipendente",
            "contributi_previdenza_complementare_dipendente",
            "irpef_lorda",
            "irpef_netto",
            "addizionale_regionale",
            "addizionale_comunale",
            "bonus_fiscali",
            "trattamento_fine_rapporto",
            "costo_mensilita_aggiuntive",
            "costo_rateo_ferie",
            "costo_rateo_permessi",
            "costo_rateo_rol",
            "costo_rateo_ex_festivita",
            "mensilita_annue",
            "ore_mensili",
            "giorni_mensili",
            "percentuale_part_time",
            "tasso_inail_per_mille",
            "livello",
            "qualifica",
            "valuta",
            "file_simulazione",
            "attiva",
            "note",
        ]
        labels = {
            "contratto": "Contratto",
            "titolo": "Titolo simulazione",
            "data_elaborazione": "Data elaborazione consulente",
            "valido_dal": "Valida dal",
            "valido_al": "Valida al",
            "netto_mensile": "Netto mensile previsto",
            "lordo_mensile": "Lordo mensile previsto",
            "costo_azienda_mensile": "Costo azienda mensile previsto",
            "contributi_previdenziali_azienda": "Contributi previdenziali azienda",
            "contributi_assicurativi_azienda": "Contributi assicurativi azienda",
            "contributi_previdenza_complementare_azienda": "Previdenza complementare azienda",
            "contributi_previdenziali_dipendente": "Contributi previdenziali dipendente",
            "contributi_assicurativi_dipendente": "Contributi assicurativi dipendente",
            "contributi_previdenza_complementare_dipendente": "Previdenza complementare dipendente",
            "irpef_lorda": "IRPEF lorda",
            "irpef_netto": "IRPEF netta",
            "addizionale_regionale": "Addizionale regionale",
            "addizionale_comunale": "Addizionale comunale",
            "bonus_fiscali": "Bonus fiscali erogati",
            "trattamento_fine_rapporto": "TFR previsto",
            "costo_mensilita_aggiuntive": "Costo mensilita aggiuntive",
            "costo_rateo_ferie": "Costo rateo ferie",
            "costo_rateo_permessi": "Costo rateo permessi",
            "costo_rateo_rol": "Costo rateo ROL",
            "costo_rateo_ex_festivita": "Costo rateo ex festivita",
            "mensilita_annue": "Mensilita annue",
            "ore_mensili": "Ore mensili",
            "giorni_mensili": "Giorni mensili",
            "percentuale_part_time": "Percentuale part-time",
            "tasso_inail_per_mille": "Tasso INAIL per mille",
            "livello": "Livello",
            "qualifica": "Qualifica",
            "valuta": "Valuta",
            "file_simulazione": "PDF simulazione consulente",
            "attiva": "Attiva",
            "note": "Note",
        }
        widgets = {
            "data_elaborazione": html5_date_input(),
            "valido_dal": html5_date_input(),
            "valido_al": html5_date_input(),
            "note": forms.Textarea(attrs={"rows": 4}),
            "valuta": forms.TextInput(attrs={"placeholder": "EUR"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        contratto_id = self.data.get(self.add_prefix("contratto")) if self.is_bound else self.initial.get(
            "contratto",
            getattr(self.instance, "contratto_id", None),
        )
        qs_filter = Q(dipendente__isnull=False)
        if contratto_id:
            qs_filter |= Q(pk=contratto_id)
        self.fields["contratto"].queryset = (
            ContrattoDipendente.objects.select_related("dipendente", "tipo_contratto")
            .filter(qs_filter)
            .order_by("dipendente__cognome", "dipendente__nome", "-data_inizio", "-id")
        )
        self.fields["contratto"].label_from_instance = lambda obj: obj.label_select(include_dipendente=True)
        make_searchable_select(self.fields["contratto"], "Cerca un contratto...")

        optional_fields = [
            "titolo",
            "data_elaborazione",
            "valido_al",
            "file_simulazione",
            "livello",
            "qualifica",
            "note",
        ]
        for field_name in optional_fields:
            self.fields[field_name].required = False


class BustaPagaDipendenteForm(forms.ModelForm):
    FORECAST_AMOUNT_FIELDS = [
        "lordo_previsto",
        "contributi_datore_previsti",
        "contributi_dipendente_previsti",
        "rateo_tredicesima_previsto",
        "rateo_tfr_previsto",
        "altri_oneri_previsti",
        "netto_previsto",
        "costo_azienda_previsto",
    ]
    REAL_AMOUNT_FIELDS = [
        "lordo_effettivo",
        "contributi_datore_effettivi",
        "contributi_dipendente_effettivi",
        "rateo_tredicesima_effettivo",
        "rateo_tfr_effettivo",
        "altri_oneri_effettivi",
        "netto_effettivo",
        "costo_azienda_effettivo",
    ]

    class Meta:
        model = BustaPagaDipendente
        fields = [
            "dipendente",
            "contratto",
            "anno",
            "mese",
            "stato",
            "valuta",
            "lordo_previsto",
            "contributi_datore_previsti",
            "contributi_dipendente_previsti",
            "rateo_tredicesima_previsto",
            "rateo_tfr_previsto",
            "altri_oneri_previsti",
            "netto_previsto",
            "costo_azienda_previsto",
            "lordo_effettivo",
            "contributi_datore_effettivi",
            "contributi_dipendente_effettivi",
            "rateo_tredicesima_effettivo",
            "rateo_tfr_effettivo",
            "altri_oneri_effettivi",
            "netto_effettivo",
            "costo_azienda_effettivo",
            "file_busta_paga",
            "data_pagamento_effettiva",
            "movimento_pagamento",
            "note_previsione",
            "note_effettivo",
        ]
        labels = {
            "dipendente": "Dipendente",
            "contratto": "Contratto",
            "anno": "Anno",
            "mese": "Mese",
            "stato": "Stato",
            "valuta": "Valuta",
            "lordo_previsto": "Lordo previsto",
            "contributi_datore_previsti": "Contributi datore previsti",
            "contributi_dipendente_previsti": "Contributi dipendente previsti",
            "rateo_tredicesima_previsto": "Rateo tredicesima previsto",
            "rateo_tfr_previsto": "Rateo TFR previsto",
            "altri_oneri_previsti": "Altri oneri previsti",
            "netto_previsto": "Netto previsto",
            "costo_azienda_previsto": "Costo azienda previsto",
            "lordo_effettivo": "Lordo effettivo",
            "contributi_datore_effettivi": "Contributi datore effettivi",
            "contributi_dipendente_effettivi": "Contributi dipendente effettivi",
            "rateo_tredicesima_effettivo": "Rateo tredicesima effettivo",
            "rateo_tfr_effettivo": "Rateo TFR effettivo",
            "altri_oneri_effettivi": "Altri oneri effettivi",
            "netto_effettivo": "Netto effettivo",
            "costo_azienda_effettivo": "Costo azienda effettivo",
            "file_busta_paga": "File busta paga",
            "data_pagamento_effettiva": "Data pagamento effettiva",
            "movimento_pagamento": "Movimento pagamento",
            "note_previsione": "Note previsione",
            "note_effettivo": "Note effettivo",
        }
        widgets = {
            "data_pagamento_effettiva": html5_date_input(),
            "valuta": forms.TextInput(attrs={"placeholder": "EUR"}),
            "note_previsione": forms.Textarea(attrs={"rows": 3}),
            "note_effettivo": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        self.detailed_mode = kwargs.pop("detailed_mode", False)
        super().__init__(*args, **kwargs)
        self.fields["contratto"].required = False
        self.fields["file_busta_paga"].required = False
        self.fields["data_pagamento_effettiva"].required = False
        self.fields["movimento_pagamento"].required = False
        self.fields["note_previsione"].required = False
        self.fields["note_effettivo"].required = False
        for field_name in self.FORECAST_AMOUNT_FIELDS + self.REAL_AMOUNT_FIELDS:
            self.fields[field_name].required = False
        self.fields["dipendente"].queryset = Dipendente.objects.order_by("cognome", "nome")
        self.fields["contratto"].queryset = ContrattoDipendente.objects.select_related(
            "dipendente",
            "tipo_contratto",
            "parametro_calcolo",
        ).order_by(
            "dipendente__cognome",
            "dipendente__nome",
            "-data_inizio",
        )
        self.fields["contratto"].empty_label = "--- nessun contratto collegato ---"
        self.fields["movimento_pagamento"].empty_label = "--- nessun movimento collegato ---"

    def clean(self):
        cleaned_data = super().clean()
        dipendente = cleaned_data.get("dipendente")
        contratto = cleaned_data.get("contratto")
        if dipendente and contratto and contratto.dipendente_id != dipendente.pk:
            self.add_error("contratto", "Il contratto selezionato appartiene a un altro dipendente.")
        for field_name in self.FORECAST_AMOUNT_FIELDS + self.REAL_AMOUNT_FIELDS:
            if cleaned_data.get(field_name) is None:
                cleaned_data[field_name] = Decimal("0.00")
        return cleaned_data
