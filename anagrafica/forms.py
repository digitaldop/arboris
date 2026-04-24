from django import forms
from django.db import DatabaseError
from django.forms import HiddenInput
from django.forms.models import BaseInlineFormSet
from django.forms.utils import ErrorDict
import re
from .utils import citta_choice_label, validate_and_normalize_phone_number
from .models import CAP, Citta, Indirizzo, Famiglia, StatoRelazioneFamiglia
from economia.models import Iscrizione, StatoIscrizione, CondizioneIscrizione, Agevolazione

from django.forms import inlineformset_factory
from .models import (
    CAP, Citta, Indirizzo, Famiglia, StatoRelazioneFamiglia,
    Familiare, Studente, Documento, RelazioneFamiliare, TipoDocumento
)


def html5_date_input():
    return forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"})


def make_searchable_select(field, placeholder):
    field.widget.attrs.update(
        {
            "data-searchable-select": "1",
            "data-searchable-placeholder": placeholder,
        }
    )


class ClasseInlineSelect(forms.Select):
    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        option = super().create_option(name, value, label, selected, index, subindex=subindex, attrs=attrs)

        if value and hasattr(value, "instance"):
            option["attrs"]["data-anno-scolastico"] = value.instance.anno_scolastico_id

        return option


class AnnoScolasticoInlineSelect(forms.Select):
    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        option = super().create_option(name, value, label, selected, index, subindex=subindex, attrs=attrs)

        if value and hasattr(value, "instance") and value.instance.data_fine:
            option["attrs"]["data-data-fine"] = value.instance.data_fine.isoformat()

        return option


class CondizioneIscrizioneInlineSelect(forms.Select):
    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        option = super().create_option(name, value, label, selected, index, subindex=subindex, attrs=attrs)

        if value and hasattr(value, "instance"):
            option["attrs"]["data-anno-scolastico"] = value.instance.anno_scolastico_id
            option["attrs"]["data-riduzione-speciale-ammessa"] = "1" if value.instance.riduzione_speciale_ammessa else "0"

        return option


class FamigliaStudenteSelect(forms.Select):
    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        option = super().create_option(name, value, label, selected, index, subindex=subindex, attrs=attrs)

        if value and hasattr(value, "instance"):
            famiglia = value.instance
            option["attrs"]["data-cognome-famiglia"] = famiglia.cognome_famiglia or ""
            option["attrs"]["data-indirizzo-famiglia"] = (
                famiglia.indirizzo_principale.label_full() if famiglia.indirizzo_principale else ""
            )
            option["attrs"]["data-indirizzo-famiglia-id"] = famiglia.indirizzo_principale_id or ""
            option["attrs"]["data-search-text"] = " ".join(
                part for part in [
                    famiglia.cognome_famiglia or "",
                    famiglia.indirizzo_principale.label_full() if famiglia.indirizzo_principale else "",
                ] if part
            ).strip()

        return option


class FamigliaSearchMixin:
    famiglia_search = forms.CharField(
        required=False,
        label="Famiglia",
        widget=forms.TextInput(
            attrs={
                "autocomplete": "new-password",
                "autocapitalize": "none",
                "spellcheck": "false",
            }
        ),
    )

    def setup_famiglia_search(self):
        if "famiglia_search" not in self.fields:
            self.fields["famiglia_search"] = forms.CharField(
                required=False,
                label="Famiglia",
                widget=forms.TextInput(
                    attrs={
                        "autocomplete": "new-password",
                        "autocapitalize": "none",
                        "spellcheck": "false",
                    }
                ),
            )

        self.fields["famiglia"].widget.attrs.update(
            {
                "data-famiglia-hidden": "1",
            }
        )
        self.fields["famiglia_search"].widget.attrs.update(
            {
                "placeholder": "Cerca una famiglia...",
                "data-famiglia-search": "1",
                "autocomplete": "new-password",
                "autocapitalize": "none",
                "spellcheck": "false",
            }
        )

        famiglia = None
        famiglia_id = None
        famiglia_label = ""

        if self.is_bound:
            famiglia_label = (
                self.data.get(self.add_prefix("famiglia_search"))
                or self.data.get("famiglia_search")
                or ""
            ).strip()
            famiglia_id = self.data.get(self.add_prefix("famiglia")) or self.data.get("famiglia")
            if famiglia_id:
                famiglia = self.fields["famiglia"].queryset.filter(pk=famiglia_id).first()
                if famiglia and not famiglia_label:
                    famiglia_label = str(famiglia)
        else:
            famiglia = self.initial.get("famiglia") or getattr(self.instance, "famiglia", None)
            if famiglia:
                if hasattr(famiglia, "pk"):
                    famiglia_id = famiglia.pk
                    famiglia_label = str(famiglia)
                else:
                    famiglia_id = famiglia
                    famiglia_obj = self.fields["famiglia"].queryset.filter(pk=famiglia).first()
                    if famiglia_obj:
                        famiglia = famiglia_obj
                        famiglia_label = str(famiglia_obj)

        if famiglia_id:
            self.initial["famiglia"] = famiglia_id
        if famiglia_label:
            self.initial["famiglia_search"] = famiglia_label

    def clean(self):
        cleaned_data = super().clean()
        famiglia = cleaned_data.get("famiglia")
        famiglia_search = (cleaned_data.get("famiglia_search") or "").strip()

        if famiglia_search and not famiglia:
            self.add_error("famiglia_search", "Seleziona una famiglia valida dall'elenco.")

        return cleaned_data


class IndirizzoSearchMixin:
    indirizzo_search = forms.CharField(
        required=False,
        label="Indirizzo",
        widget=forms.TextInput(
            attrs={
                "autocomplete": "new-password",
                "autocapitalize": "none",
                "spellcheck": "false",
            }
        ),
    )

    def setup_indirizzo_search(self, field_name="indirizzo", search_field_name="indirizzo_search"):
        if search_field_name not in self.fields:
            self.fields[search_field_name] = forms.CharField(
                required=False,
                label="Indirizzo",
                widget=forms.TextInput(
                    attrs={
                        "autocomplete": "new-password",
                        "autocapitalize": "none",
                        "spellcheck": "false",
                    }
                ),
            )

        self.fields[field_name].widget.attrs.update({"data-indirizzo-hidden": "1"})
        self.fields[search_field_name].widget.attrs.update(
            {
                "placeholder": "Cerca un indirizzo...",
                "data-indirizzo-search": "1",
                "autocomplete": "new-password",
                "autocapitalize": "none",
                "spellcheck": "false",
            }
        )

        selected = None
        selected_id = None
        selected_label = ""

        if self.is_bound:
            selected_label = (
                self.data.get(self.add_prefix(search_field_name))
                or self.data.get(search_field_name)
                or ""
            ).strip()
            selected_id = self.data.get(self.add_prefix(field_name)) or self.data.get(field_name)
            if selected_id:
                selected = self.fields[field_name].queryset.filter(pk=selected_id).first()
                if selected and not selected_label:
                    selected_label = selected.label_select()
        else:
            selected = self.initial.get(field_name) or getattr(self.instance, field_name, None)
            if selected:
                if hasattr(selected, "pk"):
                    selected_id = selected.pk
                    selected_label = selected.label_select()
                else:
                    selected_id = selected
                    selected_obj = self.fields[field_name].queryset.filter(pk=selected).first()
                    if selected_obj:
                        selected = selected_obj
                        selected_label = selected_obj.label_select()

        if selected_id:
            self.initial[field_name] = selected_id
        if selected_label:
            self.initial[search_field_name] = selected_label


class LuogoNascitaCittaMixin:
    luogo_nascita_citta = forms.ModelChoiceField(
        queryset=Citta.objects.filter(attiva=True).select_related("provincia").order_by("nome"),
        required=False,
        widget=forms.HiddenInput(attrs={"data-citta-hidden": "1"}),
    )

    luogo_nascita_pattern = re.compile(r"^(?P<nome>.+?) \((?P<sigla>[A-Z]{2})\)$")

    def setup_luogo_nascita_autocomplete(self):
        self.fields["luogo_nascita"].widget.attrs.update(
            {
                "autocomplete": "new-password",
                "autocapitalize": "none",
                "spellcheck": "false",
                "placeholder": "Cerca una città...",
                "data-citta-search": "1",
            }
        )
        self.fields["luogo_nascita_citta"].queryset = (
            Citta.objects.filter(attiva=True).select_related("provincia").order_by("nome")
        )

        self._initial_luogo_nascita = ""
        luogo_nascita_citta_id = None

        if self.is_bound:
            self._initial_luogo_nascita = (
                self.data.get(self.add_prefix("luogo_nascita"))
                or self.data.get("luogo_nascita")
                or ""
            ).strip()
            luogo_nascita_citta_id = (
                self.data.get(self.add_prefix("luogo_nascita_citta"))
                or self.data.get("luogo_nascita_citta")
            )
        else:
            self._initial_luogo_nascita = (
                self.initial.get("luogo_nascita")
                or getattr(self.instance, "luogo_nascita", "")
                or ""
            ).strip()
            luogo_nascita_citta_id = self.initial.get("luogo_nascita_citta")

            if not luogo_nascita_citta_id and self._initial_luogo_nascita:
                matched = self.luogo_nascita_pattern.match(self._initial_luogo_nascita)
                if matched:
                    citta = (
                        Citta.objects.filter(
                            nome=matched.group("nome"),
                            provincia__sigla=matched.group("sigla"),
                            attiva=True,
                        )
                        .select_related("provincia")
                        .first()
                    )
                    if citta:
                        luogo_nascita_citta_id = citta.pk

            if luogo_nascita_citta_id:
                self.initial["luogo_nascita_citta"] = luogo_nascita_citta_id

    def clean_luogo_nascita(self):
        value = (self.cleaned_data.get("luogo_nascita") or "").strip()
        citta = self.cleaned_data.get("luogo_nascita_citta")

        if citta:
            return citta_choice_label(citta)

        if value:
            if value == self._initial_luogo_nascita:
                return value
            raise forms.ValidationError("Seleziona una città valida dall'elenco.")

        return ""


class LuogoNascitaCittaFkMixin:
    luogo_nascita_search = forms.CharField(
        required=False,
        label="Luogo di nascita",
        widget=forms.TextInput(
            attrs={
                "autocomplete": "new-password",
                "autocapitalize": "none",
                "spellcheck": "false",
            }
        ),
    )

    def setup_luogo_nascita_autocomplete_fk(self):
        if "luogo_nascita_search" not in self.fields:
            self.fields["luogo_nascita_search"] = forms.CharField(
                required=False,
                label="Luogo di nascita",
                widget=forms.TextInput(
                    attrs={
                        "autocomplete": "new-password",
                        "autocapitalize": "none",
                        "spellcheck": "false",
                    }
                ),
            )

        self.fields["luogo_nascita"].widget = forms.HiddenInput(attrs={"data-citta-hidden": "1"})
        self.fields["luogo_nascita"].queryset = Citta.objects.none()
        self.fields["luogo_nascita_search"].widget.attrs.update(
            {
                "placeholder": "Cerca una città...",
                "data-citta-search": "1",
            }
        )

        luogo_nascita_id = None
        luogo_nascita_label = ""
        citta = None

        if self.is_bound:
            luogo_nascita_label = (
                self.data.get(self.add_prefix("luogo_nascita_search"))
                or self.data.get("luogo_nascita_search")
                or ""
            ).strip()
            luogo_nascita_id = (
                self.data.get(self.add_prefix("luogo_nascita"))
                or self.data.get("luogo_nascita")
            )
        else:
            citta = self.initial.get("luogo_nascita") or getattr(self.instance, "luogo_nascita", None)
            if citta:
                if hasattr(citta, "pk"):
                    luogo_nascita_id = citta.pk
                    luogo_nascita_label = str(citta)
                else:
                    luogo_nascita_id = citta
                    citta_obj = (
                        Citta.objects.filter(pk=citta, attiva=True)
                        .select_related("provincia")
                        .first()
                    )
                    if citta_obj:
                        citta = citta_obj
                        luogo_nascita_label = str(citta_obj)
                    else:
                        citta = None

        if luogo_nascita_id:
            self.initial["luogo_nascita"] = luogo_nascita_id
        if luogo_nascita_label:
            self.initial["luogo_nascita_search"] = luogo_nascita_label
        if luogo_nascita_id:
            self.fields["luogo_nascita"].queryset = (
                Citta.objects.filter(pk=luogo_nascita_id, attiva=True)
                .select_related("provincia")
            )
        if not self.is_bound and luogo_nascita_id and citta:
            self.fields["luogo_nascita"].widget.attrs["data-codice-catastale"] = citta.codice_catastale or ""

    def clean(self):
        cleaned_data = super().clean()
        luogo_nascita = cleaned_data.get("luogo_nascita")
        luogo_nascita_search = (cleaned_data.get("luogo_nascita_search") or "").strip()

        if luogo_nascita_search and not luogo_nascita:
            matched = re.match(r"^(?P<nome>.+?) \((?P<sigla>[A-Z]{2})\)$", luogo_nascita_search)
            if matched:
                luogo_nascita = (
                    Citta.objects.filter(
                        nome__iexact=matched.group("nome"),
                        provincia__sigla__iexact=matched.group("sigla"),
                        attiva=True,
                    )
                    .select_related("provincia")
                    .first()
                )
                if luogo_nascita:
                    cleaned_data["luogo_nascita"] = luogo_nascita

        if luogo_nascita_search and not cleaned_data.get("luogo_nascita"):
            citta_qs = (
                Citta.objects.filter(nome__iexact=luogo_nascita_search, attiva=True)
                .select_related("provincia")
            )
            if citta_qs.count() == 1:
                cleaned_data["luogo_nascita"] = citta_qs.first()

        if luogo_nascita_search and not cleaned_data.get("luogo_nascita"):
            self.add_error("luogo_nascita_search", "Seleziona una città valida dall'elenco.")

        return cleaned_data

#FORMS PER GLI INDIRIZZI
class IndirizzoForm(forms.ModelForm):
    citta_search = forms.CharField(
        required=False,
        label="Città",
        widget=forms.TextInput(
            attrs={
                "autocomplete": "off",
                "placeholder": "Inizia a digitare il nome della città...",
            }
        ),
    )

    class Meta:
        model = Indirizzo
        fields = [
            "via",
            "numero_civico",
            "citta",
            "cap_scelto",
        ]
        widgets = {
            "citta": forms.Select(attrs={"data-citta-hidden": "1"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["citta"].widget = forms.HiddenInput(attrs={"data-citta-hidden": "1"})
        self.fields["citta"].queryset = Citta.objects.none()
        self.fields["citta_search"].widget.attrs.update(
            {
                "placeholder": "Cerca una cittÃ ...",
                "data-citta-search": "1",
            }
        )
        self.fields["cap_scelto"].required = False
        self.fields["cap_scelto"].label = "CAP"
        self.fields["cap_scelto"].queryset = CAP.objects.none()

        # Caso 1: form inviato via POST
        citta_id = None
        if self.is_bound:
            citta_id = self.data.get("citta")
            self.fields["citta_search"].initial = (
                self.data.get("citta_search")
                or ""
            ).strip()

        # Caso 2: form in modifica con instance esistente
        elif self.instance.pk and self.instance.citta_id:
            citta_id = self.instance.citta_id
            self.fields["citta_search"].initial = citta_choice_label(self.instance.citta)

        # Popola il queryset CAP in base alla città
        if citta_id:
            try:
                citta_id = int(citta_id)
                citta = (
                    Citta.objects.filter(pk=citta_id, attiva=True)
                    .select_related("provincia", "provincia__regione")
                    .first()
                )
                if citta:
                    self.fields["citta"].queryset = Citta.objects.filter(pk=citta.pk)
                    self.fields["citta"].widget.attrs["data-codice-catastale"] = citta.codice_catastale or ""
                self.fields["cap_scelto"].queryset = (
                    CAP.objects.filter(citta_id=citta_id, attivo=True)
                    .order_by("codice")
                )
            except (TypeError, ValueError):
                self.fields["cap_scelto"].queryset = CAP.objects.none()

    def clean(self):
        cleaned_data = super().clean()

        citta = cleaned_data.get("citta")
        citta_search = cleaned_data.get("citta_search")
        cap_scelto = cleaned_data.get("cap_scelto")

        if citta_search and not citta:
            self.add_error("citta_search", "Seleziona una città valida dall'elenco.")

        if citta:
            caps = CAP.objects.filter(citta=citta, attivo=True).order_by("codice")
            num_caps = caps.count()

            if num_caps == 1 and not cap_scelto:
                cleaned_data["cap_scelto"] = caps.first()
            elif num_caps > 1 and not cap_scelto:
                self.add_error("cap_scelto", "Seleziona un CAP per questa città.")

            if cap_scelto and cap_scelto.citta_id != citta.id:
                self.add_error("cap_scelto", "Il CAP selezionato non appartiene alla città scelta.")

        return cleaned_data
    
#FINE FORMS PER GLI INDIRIZZI

#FORMS PER LE FAMIGLIE
class FamigliaForm(forms.ModelForm):
    class Meta:
        model = Famiglia
        fields = [
            "cognome_famiglia",
            "stato_relazione_famiglia",
            "indirizzo_principale",
            "attiva",
            "note",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["stato_relazione_famiglia"].queryset = (
            StatoRelazioneFamiglia.objects.filter(attivo=True)
            .order_by("ordine", "stato")
        )
        self.fields["stato_relazione_famiglia"].empty_label = None

        self.fields["indirizzo_principale"].queryset = (
            Indirizzo.objects.select_related("citta", "provincia", "regione")
            .order_by("via", "numero_civico")
        )

        self.fields["indirizzo_principale"].required = False
        self.fields["indirizzo_principale"].label_from_instance = lambda obj: obj.label_select()
        make_searchable_select(self.fields["indirizzo_principale"], "Cerca un indirizzo...")

        # DEFAULT SOLO IN CREAZIONE
        if not self.instance.pk and not self.initial.get("stato_relazione_famiglia"):
            primo = self.fields["stato_relazione_famiglia"].queryset.first()
            if primo:
                self.initial["stato_relazione_famiglia"] = primo.pk
        if not self.instance.pk and not self.is_bound and "attiva" not in self.initial:
            self.initial["attiva"] = True
#FINE FORMS PER LE FAMIGLIE

#INIZIO FORMS PER I FAMILIARI
class FamiliareForm(IndirizzoSearchMixin, FamigliaSearchMixin, LuogoNascitaCittaFkMixin, forms.ModelForm):
    class Meta:
        model = Familiare
        fields = [
            "famiglia",
            "relazione_familiare",
            "indirizzo",
            "nome",
            "cognome",
            "telefono",
            "email",
            "codice_fiscale",
            "sesso",
            "data_nascita",
            "luogo_nascita",
            "convivente",
            "referente_principale",
            "abilitato_scambio_retta",
            "attivo",
            "note",
        ]
        widgets = {
            "famiglia": FamigliaStudenteSelect(),
            "data_nascita": html5_date_input(),
            "note": forms.Textarea(attrs={"rows": 4}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["indirizzo"].required = False
        self.fields["indirizzo"].help_text = (
            "Se lasci vuoto, verrà usato automaticamente l'indirizzo principale della famiglia."
        )
        self.fields["famiglia"].queryset = (
            Famiglia.objects.select_related("stato_relazione_famiglia")
            .order_by("cognome_famiglia")
        )
        make_searchable_select(self.fields["famiglia"], "Cerca una famiglia...")
        self.fields["relazione_familiare"].queryset = (
            RelazioneFamiliare.objects.order_by("ordine", "relazione")
        )
        self.fields["relazione_familiare"].empty_label = None
        self.fields["indirizzo"].queryset = (
            Indirizzo.objects.select_related("citta", "provincia", "regione")
            .order_by("via", "numero_civico")
        )
        self.fields["indirizzo"].label_from_instance = lambda obj: obj.label_select()
        make_searchable_select(self.fields["indirizzo"], "Cerca un indirizzo...")

        famiglia_id = None
        if self.is_bound:
            famiglia_id = self.data.get(self.add_prefix("famiglia")) or self.data.get("famiglia")
        elif self.instance.pk and self.instance.famiglia_id:
            famiglia_id = self.instance.famiglia_id
        else:
            famiglia_id = self.initial.get("famiglia")

        if not self.is_bound and not self.initial.get("indirizzo") and not getattr(self.instance, "indirizzo_id", None) and famiglia_id:
            try:
                famiglia = Famiglia.objects.select_related("indirizzo_principale").get(pk=famiglia_id)
            except (Famiglia.DoesNotExist, TypeError, ValueError):
                famiglia = None

            if famiglia and famiglia.indirizzo_principale_id:
                self.initial["indirizzo"] = famiglia.indirizzo_principale_id
                self.fields["indirizzo"].widget.attrs["data-inherited-address"] = "1"

        self.setup_famiglia_search()
        self.setup_indirizzo_search()
        self.setup_luogo_nascita_autocomplete_fk()
        self.fields["nome"].widget.attrs["data-cf-nome"] = "1"
        self.fields["cognome"].widget.attrs["data-cf-cognome"] = "1"
        self.fields["data_nascita"].widget.attrs["data-cf-data-nascita"] = "1"
        self.fields["sesso"].widget.attrs["data-cf-sesso"] = "1"
        self.fields["luogo_nascita"].widget.attrs["data-cf-luogo-id"] = "1"
        self.fields["codice_fiscale"].widget.attrs["data-cf-output"] = "1"

        if not self.instance.pk and not self.is_bound and "attivo" not in self.initial:
            self.initial["attivo"] = True

        if not self.instance.pk and not self.is_bound and not self.initial.get("relazione_familiare"):
            prima_relazione = self.fields["relazione_familiare"].queryset.first()
            if prima_relazione:
                self.initial["relazione_familiare"] = prima_relazione.pk

    def clean(self):
        cleaned_data = super().clean()
        famiglia = cleaned_data.get("famiglia")
        indirizzo = cleaned_data.get("indirizzo")

        if (
            famiglia
            and indirizzo
            and getattr(famiglia, "indirizzo_principale_id", None)
            and indirizzo.pk == famiglia.indirizzo_principale_id
        ):
            cleaned_data["indirizzo"] = None

        return cleaned_data

    def clean_telefono(self):
        return validate_and_normalize_phone_number(self.cleaned_data.get("telefono"))


class FamiliareInlineForm(FamiliareForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if not self.is_bound and not getattr(self.instance, "pk", None):
            self.fields["attivo"].initial = True

    def has_changed(self):
        changed = super().has_changed()
        if not changed:
            return False

        meaningful_values = [
            self.data.get(self.add_prefix("cognome"), ""),
            self.data.get(self.add_prefix("nome"), ""),
            self.data.get(self.add_prefix("telefono"), ""),
            self.data.get(self.add_prefix("email"), ""),
            self.data.get(self.add_prefix("codice_fiscale"), ""),
            self.data.get(self.add_prefix("data_nascita"), ""),
            self.data.get(self.add_prefix("luogo_nascita_search"), ""),
        ]

        if not any((value or "").strip() for value in meaningful_values):
            return False

        return True


class IgnoreBlankExtraInlineFormSet(BaseInlineFormSet):
    meaningful_field_names = ()

    def _is_meaningfully_filled(self, form):
        meaningful_values = [
            form.data.get(form.add_prefix(field_name), "")
            for field_name in self.meaningful_field_names
        ]
        return any((value or "").strip() for value in meaningful_values)

    def full_clean(self):
        super().full_clean()

        if not self.is_bound:
            return

        for index, form in enumerate(self.forms):
            if form.instance.pk:
                continue

            if self._is_meaningfully_filled(form):
                continue

            while len(self._errors) <= index:
                self._errors.append(form.error_class())

            self._errors[index] = form.error_class()
            form._errors = ErrorDict()
            if hasattr(form, "cleaned_data"):
                form.cleaned_data = {}


class FamiliareInlineBaseFormSet(IgnoreBlankExtraInlineFormSet):
    meaningful_field_names = (
        "cognome",
        "nome",
        "telefono",
        "email",
        "codice_fiscale",
        "data_nascita",
        "luogo_nascita_search",
    )


FamiliareFormSet = inlineformset_factory(
    Famiglia,
    Familiare,
    form=FamiliareInlineForm,
    formset=FamiliareInlineBaseFormSet,
    extra=1,
    can_delete=True,
)

#FINE FORMS PER I FAMILIARI

#INIZIO FORM PER I DOCUMENTI DEI FAMILIARI
class DocumentoFamiliareForm(forms.ModelForm):
    class Meta:
        model = Documento
        fields = [
            "tipo_documento",
            "descrizione",
            "file",
            "scadenza",
            "visibile",
            "note",
        ]
        widgets = {
            "descrizione": forms.TextInput(),
            "scadenza": html5_date_input(),
            "note": forms.TextInput(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["tipo_documento"].queryset = (
            TipoDocumento.objects.filter(attivo=True).order_by("ordine", "tipo_documento")
        )


DocumentoFamiliareFormSet = inlineformset_factory(
    Familiare,
    Documento,
    form=DocumentoFamiliareForm,
    fk_name="familiare",
    extra=1,
    can_delete=True,
)

#FINE FORM PER I DOCUMENTI DEI FAMILIARI

#INIZIO FORM PER GLI STUDENTI

class StudenteForm(IndirizzoSearchMixin, LuogoNascitaCittaFkMixin, forms.ModelForm):
    class Meta:
        model = Studente
        fields = [
            "cognome",
            "nome",
            "sesso",
            "data_nascita",
            "luogo_nascita",
            "codice_fiscale",
            "indirizzo",
            "attivo",
        ]
        widgets = {
            "data_nascita": html5_date_input(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["indirizzo"].queryset = (
            Indirizzo.objects.select_related("citta", "provincia", "regione")
            .order_by("via", "numero_civico")
        )
        self.fields["indirizzo"].required = False
        self.fields["indirizzo"].label_from_instance = lambda obj: obj.label_select()
        make_searchable_select(self.fields["indirizzo"], "Cerca un indirizzo...")

        if (
            not self.is_bound
            and not self.initial.get("indirizzo")
            and not getattr(self.instance, "indirizzo_id", None)
            and getattr(self.instance, "famiglia_id", None)
        ):
            famiglia = getattr(self.instance, "famiglia", None)
            if famiglia is None:
                famiglia = (
                    Famiglia.objects.select_related("indirizzo_principale")
                    .filter(pk=self.instance.famiglia_id)
                    .first()
                )
            if famiglia and famiglia.indirizzo_principale_id:
                self.initial["indirizzo"] = famiglia.indirizzo_principale_id
                self.fields["indirizzo"].widget.attrs["data-inherited-address"] = "1"

        self.setup_indirizzo_search()
        self.setup_luogo_nascita_autocomplete_fk()
        self.fields["nome"].widget.attrs["data-cf-nome"] = "1"
        self.fields["cognome"].widget.attrs["data-cf-cognome"] = "1"
        self.fields["data_nascita"].widget.attrs["data-cf-data-nascita"] = "1"
        self.fields["sesso"].widget.attrs["data-cf-sesso"] = "1"
        self.fields["luogo_nascita"].widget.attrs["data-cf-luogo-id"] = "1"
        self.fields["codice_fiscale"].widget.attrs["data-cf-output"] = "1"

        if not self.instance.pk and not self.is_bound and "attivo" not in self.initial:
            self.initial["attivo"] = True

    def clean(self):
        cleaned_data = super().clean()
        indirizzo = cleaned_data.get("indirizzo")
        famiglia = getattr(self.instance, "famiglia", None)

        if famiglia is None and getattr(self.instance, "famiglia_id", None):
            famiglia = (
                Famiglia.objects.select_related("indirizzo_principale")
                .filter(pk=self.instance.famiglia_id)
                .first()
            )

        if (
            famiglia
            and indirizzo
            and getattr(famiglia, "indirizzo_principale_id", None)
            and indirizzo.pk == famiglia.indirizzo_principale_id
        ):
            cleaned_data["indirizzo"] = None

        return cleaned_data


class StudenteInlineForm(StudenteForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if not self.is_bound and not getattr(self.instance, "pk", None):
            self.fields["attivo"].initial = True

    def has_changed(self):
        changed = super().has_changed()
        if not changed:
            return False

        meaningful_values = [
            self.data.get(self.add_prefix("nome"), ""),
            self.data.get(self.add_prefix("data_nascita"), ""),
            self.data.get(self.add_prefix("luogo_nascita_search"), ""),
            self.data.get(self.add_prefix("codice_fiscale"), ""),
        ]

        if not any((value or "").strip() for value in meaningful_values):
            return False

        return True


class StudenteInlineBaseFormSet(IgnoreBlankExtraInlineFormSet):
    meaningful_field_names = (
        "nome",
        "data_nascita",
        "luogo_nascita_search",
        "codice_fiscale",
    )


StudenteFormSet = inlineformset_factory(
    Famiglia,
    Studente,
    form=StudenteInlineForm,
    formset=StudenteInlineBaseFormSet,
    extra=1,
    can_delete=True,
)

class StudenteStandaloneForm(IndirizzoSearchMixin, FamigliaSearchMixin, LuogoNascitaCittaFkMixin, forms.ModelForm):
    class Meta:
        model = Studente
        fields = [
            "famiglia",
            "cognome",
            "nome",
            "sesso",
            "data_nascita",
            "luogo_nascita",
            "codice_fiscale",
            "indirizzo",
            "attivo",
            "note",
        ]
        widgets = {
            "famiglia": FamigliaStudenteSelect(),
            "data_nascita": html5_date_input(),
            "note": forms.Textarea(attrs={"rows": 4}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["famiglia"].queryset = (
            Famiglia.objects.select_related("stato_relazione_famiglia")
            .order_by("cognome_famiglia")
        )
        make_searchable_select(self.fields["famiglia"], "Cerca una famiglia...")

        self.fields["indirizzo"].queryset = (
            Indirizzo.objects.select_related("citta", "provincia", "regione")
            .order_by("via", "numero_civico")
        )

        self.fields["indirizzo"].required = False
        self.fields["indirizzo"].label_from_instance = lambda obj: obj.label_select()
        make_searchable_select(self.fields["indirizzo"], "Cerca un indirizzo...")
        self.setup_famiglia_search()
        self.setup_indirizzo_search()
        self.fields["nome"].widget.attrs["data-cf-nome"] = "1"
        self.fields["cognome"].widget.attrs["data-cf-cognome"] = "1"
        self.fields["data_nascita"].widget.attrs["data-cf-data-nascita"] = "1"
        self.fields["sesso"].widget.attrs["data-cf-sesso"] = "1"
        self.fields["luogo_nascita"].widget.attrs["data-cf-luogo-id"] = "1"
        self.fields["codice_fiscale"].widget.attrs["data-cf-output"] = "1"
        self.setup_luogo_nascita_autocomplete_fk()

#FINE FORM PER GLI STUDENTI

#INIZIO FORM PER I DOCUMENTI

class DocumentoFamigliaForm(forms.ModelForm):
    class Meta:
        model = Documento
        fields = [
            "tipo_documento",
            "descrizione",
            "file",
            "scadenza",
            "visibile",
            "note",
        ]
        widgets = {
            "descrizione": forms.TextInput(),
            "scadenza": html5_date_input(),
            "note": forms.TextInput(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["tipo_documento"].queryset = (
            TipoDocumento.objects.filter(attivo=True).order_by("ordine", "tipo_documento")
        )


class DocumentoFamigliaInlineForm(DocumentoFamigliaForm):
    def has_changed(self):
        changed = super().has_changed()
        if not changed:
            return False

        meaningful_values = [
            self.data.get(self.add_prefix("tipo_documento"), ""),
            self.data.get(self.add_prefix("descrizione"), ""),
            self.data.get(self.add_prefix("file"), ""),
            self.data.get(self.add_prefix("scadenza"), ""),
            self.data.get(self.add_prefix("note"), ""),
        ]

        if not any((value or "").strip() for value in meaningful_values):
            return False

        return True


class DocumentoFamigliaInlineBaseFormSet(IgnoreBlankExtraInlineFormSet):
    meaningful_field_names = (
        "tipo_documento",
        "descrizione",
        "file",
        "scadenza",
        "note",
    )


DocumentoFamigliaFormSet = inlineformset_factory(
    Famiglia,
    Documento,
    form=DocumentoFamigliaInlineForm,
    formset=DocumentoFamigliaInlineBaseFormSet,
    fk_name="famiglia",
    extra=1,
    can_delete=True,
)

class DocumentoStudenteForm(forms.ModelForm):
    class Meta:
        model = Documento
        fields = [
            "tipo_documento",
            "descrizione",
            "file",
            "scadenza",
            "visibile",
            "note",
        ]
        widgets = {
            "descrizione": forms.TextInput(),
            "scadenza": html5_date_input(),
            "note": forms.TextInput(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["tipo_documento"].queryset = (
            TipoDocumento.objects.filter(attivo=True).order_by("ordine", "tipo_documento")
        )

DocumentoStudenteFormSet = inlineformset_factory(
    Studente,
    Documento,
    form=DocumentoStudenteForm,
    fk_name="studente",
    extra=1,
    can_delete=True,
)


class IscrizioneStudenteInlineForm(forms.ModelForm):
    class Meta:
        model = Iscrizione
        fields = [
            "anno_scolastico",
            "classe",
            "data_iscrizione",
            "data_fine_iscrizione",
            "stato_iscrizione",
            "condizione_iscrizione",
            "agevolazione",
            "riduzione_speciale",
            "importo_riduzione_speciale",
            "non_pagante",
            "attiva",
            "note_amministrative",
            "note",
        ]
        widgets = {
            "anno_scolastico": AnnoScolasticoInlineSelect(),
            "classe": ClasseInlineSelect(),
            "condizione_iscrizione": CondizioneIscrizioneInlineSelect(),
            "data_iscrizione": html5_date_input(),
            "data_fine_iscrizione": html5_date_input(),
            "note_amministrative": forms.TextInput(),
            "note": forms.TextInput(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["anno_scolastico"].queryset = self.fields["anno_scolastico"].queryset.order_by("-data_inizio")
        self.fields["classe"].queryset = self.fields["classe"].queryset.select_related("anno_scolastico").order_by(
            "-anno_scolastico__data_inizio",
            "ordine_classe",
            "nome_classe",
            "sezione_classe",
        )
        self.fields["stato_iscrizione"].queryset = StatoIscrizione.objects.filter(attiva=True).order_by("ordine", "stato_iscrizione")
        self.fields["condizione_iscrizione"].queryset = CondizioneIscrizione.objects.select_related("anno_scolastico").filter(
            attiva=True
        ).order_by("-anno_scolastico__data_inizio", "nome_condizione_iscrizione")
        self.fields["importo_riduzione_speciale"].label = "Importo riduzione speciale"
        self.fields["importo_riduzione_speciale"].widget = forms.TextInput()
        self.fields["importo_riduzione_speciale"].widget.attrs.update(
            {
                "autocomplete": "off",
                "inputmode": "decimal",
                "data-currency": "EUR",
                "placeholder": "0,00",
                "maxlength": "12",
            }
        )
        self.fields["agevolazione"].required = False
        try:
            self.fields["agevolazione"].queryset = Agevolazione.objects.filter(attiva=True).order_by("nome_agevolazione")
        except DatabaseError:
            self.fields["agevolazione"].queryset = Agevolazione.objects.none()

        if not getattr(self.instance, "pk", None):
            self.fields["data_fine_iscrizione"].widget = HiddenInput()


IscrizioneStudenteFormSet = inlineformset_factory(
    Studente,
    Iscrizione,
    form=IscrizioneStudenteInlineForm,
    fk_name="studente",
    extra=1,
    can_delete=True,
)

#FINE FORM PER I DOCUMENTI





