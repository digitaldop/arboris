from django import forms
from django.contrib.contenttypes.forms import BaseGenericInlineFormSet, generic_inlineformset_factory
from django.db import DatabaseError
from django.db.models import Case, IntegerField, Prefetch, Q, When
from django.forms import HiddenInput
from django.forms.models import BaseInlineFormSet, BaseModelFormSet
from django.forms.utils import ErrorDict
from django.utils.functional import cached_property
from decimal import Decimal
import re
from .contact_services import (
    ensure_default_contact_labels,
    set_familiare_studenti,
    set_studente_familiari,
    sync_legacy_contact_fields_from_links,
    sync_principal_contacts,
)
from .utils import citta_choice_label, validate_and_normalize_phone_number
from economia.models import Iscrizione, StatoIscrizione, CondizioneIscrizione, Agevolazione
from scuola.utils import resolve_default_anno_scolastico
from scuola.models import AnnoScolastico, Classe, GruppoClasse
from arboris.form_widgets import italian_decimal_to_python, merge_widget_classes

from django.forms import inlineformset_factory, modelformset_factory
from .models import (
    CAP, Citta, Indirizzo,
    Familiare, Studente, Documento, RelazioneFamiliare, TipoDocumento, Nazione,
    AnagraficaIndirizzo, AnagraficaTelefono, AnagraficaEmail,
    LabelIndirizzo, LabelTelefono, LabelEmail,
    SESSO_CHOICES,
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


def anagrafica_address_link_queryset():
    return AnagraficaIndirizzo.objects.select_related(
        "indirizzo",
        "indirizzo__citta",
        "indirizzo__provincia",
        "indirizzo__regione",
    )


def studente_direct_relation_label(studente):
    return f"{studente.cognome} {studente.nome}".strip()


def familiare_direct_relation_label(familiare):
    persona = getattr(familiare, "persona", None)
    cognome = getattr(persona, "cognome", None) or familiare.cognome
    nome = getattr(persona, "nome", None) or familiare.nome
    relation = f" ({familiare.relazione_familiare})" if getattr(familiare, "relazione_familiare", None) else ""
    return f"{cognome} {nome}{relation}".strip()


def _active_label_queryset(label_model, selected_id=None):
    qs_filter = Q(attiva=True)
    if selected_id:
        qs_filter |= Q(pk=selected_id)
    return label_model.objects.filter(qs_filter).order_by("ordine", "nome")


class AnagraficaContactFormMixin:
    label_model = None
    label_default_name = "Principale"
    value_field_name = ""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        selected_label_id = getattr(self.instance, "label_id", None)
        if "label" in self.fields and self.label_model:
            self.fields["label"].required = False
            self.fields["label"].queryset = _active_label_queryset(self.label_model, selected_label_id)
            self.fields["label"].empty_label = "--- etichetta ---"
        if "principale" in self.fields:
            self.fields["principale"].required = False
            self.fields["principale"].widget.attrs.update({"class": "contact-primary-input"})
        if "ordine" in self.fields:
            self.fields["ordine"].required = False
            self.fields["ordine"].widget.attrs.update({"min": "1", "inputmode": "numeric"})
        if "note" in self.fields:
            self.fields["note"].required = False
            self.fields["note"].widget = forms.TextInput(
                attrs={
                    **self.fields["note"].widget.attrs,
                    "placeholder": "Nota breve",
                }
            )

    def _value_is_present(self, value):
        if value is None:
            return False
        if isinstance(value, str):
            return bool(value.strip())
        return True

    def clean(self):
        cleaned_data = super().clean()
        if cleaned_data.get("DELETE"):
            return cleaned_data

        value = cleaned_data.get(self.value_field_name)
        if self._value_is_present(value) and not cleaned_data.get("label") and self.label_model:
            labels = ensure_default_contact_labels()
            label_groups = {
                LabelIndirizzo: "indirizzi",
                LabelTelefono: "telefoni",
                LabelEmail: "email",
            }
            group = label_groups.get(self.label_model)
            cleaned_data["label"] = labels.get(group, {}).get(self.label_default_name)

        return cleaned_data


class AnagraficaIndirizzoForm(AnagraficaContactFormMixin, forms.ModelForm):
    label_model = LabelIndirizzo
    value_field_name = "indirizzo"

    class Meta:
        model = AnagraficaIndirizzo
        fields = ["indirizzo", "label", "principale", "ordine", "note"]
        widgets = {
            "note": forms.TextInput(attrs={"placeholder": "Nota breve"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["indirizzo"].required = False
        self.fields["indirizzo"].queryset = (
            Indirizzo.objects.select_related("citta", "provincia", "regione").order_by("via", "numero_civico")
        )
        self.fields["indirizzo"].label_from_instance = lambda obj: obj.label_select()
        self.fields["indirizzo"].empty_label = "--- indirizzo ---"


class AnagraficaTelefonoForm(AnagraficaContactFormMixin, forms.ModelForm):
    label_model = LabelTelefono
    value_field_name = "numero"

    class Meta:
        model = AnagraficaTelefono
        fields = ["numero", "label", "principale", "ordine", "note"]
        widgets = {
            "numero": forms.TextInput(attrs={"placeholder": "Es. 333 1234567"}),
            "note": forms.TextInput(attrs={"placeholder": "Nota breve"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["numero"].required = False

    def clean_numero(self):
        return validate_and_normalize_phone_number(self.cleaned_data.get("numero"))


class AnagraficaEmailForm(AnagraficaContactFormMixin, forms.ModelForm):
    label_model = LabelEmail
    value_field_name = "email"

    class Meta:
        model = AnagraficaEmail
        fields = ["email", "label", "principale", "ordine", "note"]
        widgets = {
            "email": forms.EmailInput(attrs={"placeholder": "esempio@email.com"}),
            "note": forms.TextInput(attrs={"placeholder": "Nota breve"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["email"].required = False


class BaseAnagraficaContactFormSet(BaseGenericInlineFormSet):
    value_field_name = ""

    def _form_has_value(self, form):
        value = form.cleaned_data.get(self.value_field_name)
        if value is None:
            return False
        if isinstance(value, str):
            return bool(value.strip())
        return True

    def clean(self):
        super().clean()
        principal_count = 0
        for form in self.forms:
            if not hasattr(form, "cleaned_data") or not form.cleaned_data:
                continue
            if form.cleaned_data.get("DELETE") or not self._form_has_value(form):
                continue
            if form.cleaned_data.get("principale"):
                principal_count += 1
        if principal_count > 1:
            raise forms.ValidationError("Puoi indicare un solo recapito principale per sezione.")


class BaseAnagraficaIndirizzoFormSet(BaseAnagraficaContactFormSet):
    value_field_name = "indirizzo"


class BaseAnagraficaTelefonoFormSet(BaseAnagraficaContactFormSet):
    value_field_name = "numero"


class BaseAnagraficaEmailFormSet(BaseAnagraficaContactFormSet):
    value_field_name = "email"


AnagraficaIndirizzoFormSet = generic_inlineformset_factory(
    AnagraficaIndirizzo,
    form=AnagraficaIndirizzoForm,
    formset=BaseAnagraficaIndirizzoFormSet,
    extra=1,
    can_delete=True,
)

AnagraficaTelefonoFormSet = generic_inlineformset_factory(
    AnagraficaTelefono,
    form=AnagraficaTelefonoForm,
    formset=BaseAnagraficaTelefonoFormSet,
    extra=1,
    can_delete=True,
)

AnagraficaEmailFormSet = generic_inlineformset_factory(
    AnagraficaEmail,
    form=AnagraficaEmailForm,
    formset=BaseAnagraficaEmailFormSet,
    extra=1,
    can_delete=True,
)


def build_anagrafica_contact_formsets(data=None, instance=None):
    return {
        "indirizzi_formset": AnagraficaIndirizzoFormSet(
            data=data,
            instance=instance,
            prefix="contatti_indirizzi",
        ),
        "telefoni_formset": AnagraficaTelefonoFormSet(
            data=data,
            instance=instance,
            prefix="contatti_telefoni",
        ),
        "email_formset": AnagraficaEmailFormSet(
            data=data,
            instance=instance,
            prefix="contatti_email",
        ),
    }


def anagrafica_contact_formsets_are_valid(contact_formsets):
    return all(
        _anagrafica_contact_formset_has_management_data(formset) and formset.is_valid()
        or not _anagrafica_contact_formset_has_management_data(formset)
        for formset in contact_formsets.values()
    )


def save_anagrafica_contact_formsets(instance, contact_formsets):
    has_contact_changes = False
    for formset in contact_formsets.values():
        if not _anagrafica_contact_formset_has_management_data(formset):
            continue
        formset.instance = instance
        if formset.has_changed():
            formset.save()
            has_contact_changes = True
    if has_contact_changes:
        sync_legacy_contact_fields_from_links(instance)
    return has_contact_changes


def anagrafica_contact_formsets_have_errors(contact_formsets):
    return any(
        _anagrafica_contact_formset_has_management_data(formset)
        and (formset.total_error_count() or formset.non_form_errors())
        for formset in contact_formsets.values()
    )


def _anagrafica_contact_formset_has_management_data(formset):
    if not formset.is_bound:
        return True
    data = getattr(formset, "data", None)
    if data is None:
        return False
    return f"{formset.prefix}-TOTAL_FORMS" in data


class StudenteDirectFamiliariForm(forms.Form):
    direct_familiari_collegati = forms.ModelMultipleChoiceField(
        queryset=Familiare.objects.none(),
        required=False,
        label="Genitori e tutori collegati",
        help_text="Seleziona i familiari collegati allo studente. Deseleziona e salva per rimuovere un collegamento.",
        widget=forms.SelectMultiple(
            attrs={
                "class": "form-control direct-relation-select",
                "size": 3,
            }
        ),
    )

    def __init__(self, *args, studente=None, **kwargs):
        self.studente = studente
        super().__init__(*args, **kwargs)

        selected_ids = set()
        if getattr(studente, "pk", None):
            relazioni_prefetched = getattr(studente, "relazioni_familiari_attive_prefetch", None)
            if relazioni_prefetched is not None:
                selected_ids.update(
                    relazione.familiare_id
                    for relazione in relazioni_prefetched
                    if relazione.familiare_id
                )
            else:
                selected_ids.update(
                    studente.relazioni_familiari.filter(attivo=True).values_list("familiare_id", flat=True)
                )

        queryset = (
            Familiare.objects.select_related(
                "persona",
                "persona__indirizzo",
                "persona__indirizzo__citta",
                "persona__indirizzo__provincia",
                "persona__indirizzo__regione",
                "relazione_familiare",
            )
            .prefetch_related(
                Prefetch("persona__indirizzi_anagrafici", queryset=anagrafica_address_link_queryset()),
                Prefetch("indirizzi_anagrafici", queryset=anagrafica_address_link_queryset()),
            )
            .filter(Q(persona__pk__isnull=False) | Q(pk__in=selected_ids))
            .order_by("persona__cognome", "persona__nome", "pk")
        )
        field = self.fields["direct_familiari_collegati"]
        field.queryset = queryset
        field.label_from_instance = familiare_direct_relation_label
        if selected_ids and not self.is_bound:
            self.initial["direct_familiari_collegati"] = list(selected_ids)

    def save(self):
        if self.studente is not None:
            set_studente_familiari(self.studente, self.cleaned_data.get("direct_familiari_collegati", []))


class FamiliareDirectStudentiForm(forms.Form):
    direct_studenti_collegati = forms.ModelMultipleChoiceField(
        queryset=Studente.objects.none(),
        required=False,
        label="Figli e figlie collegati",
        help_text="Seleziona gli studenti collegati al familiare. Deseleziona e salva per rimuovere un collegamento.",
        widget=forms.SelectMultiple(
            attrs={
                "class": "form-control direct-relation-select",
                "size": 3,
            }
        ),
    )

    def __init__(self, *args, familiare=None, **kwargs):
        self.familiare = familiare
        super().__init__(*args, **kwargs)

        selected_ids = set()
        if getattr(familiare, "pk", None):
            relazioni_prefetched = getattr(familiare, "relazioni_studenti_attive_prefetch", None)
            if relazioni_prefetched is not None:
                selected_ids.update(
                    relazione.studente_id
                    for relazione in relazioni_prefetched
                    if relazione.studente_id
                )
            else:
                selected_ids.update(
                    familiare.relazioni_studenti.filter(attivo=True).values_list("studente_id", flat=True)
                )

        queryset = (
            Studente.objects.filter(Q(attivo=True) | Q(pk__in=selected_ids))
            .order_by("cognome", "nome", "pk")
        )
        field = self.fields["direct_studenti_collegati"]
        field.queryset = queryset
        field.label_from_instance = studente_direct_relation_label
        if selected_ids and not self.is_bound:
            self.initial["direct_studenti_collegati"] = list(selected_ids)

    def save(self):
        if self.familiare is not None:
            set_familiare_studenti(self.familiare, self.cleaned_data.get("direct_studenti_collegati", []))


def classe_principale_reference_choices(selected_classe_id=None, selected_gruppo_id=None):
    classe_filter = Q(attiva=True)
    gruppo_filter = Q(attivo=True)
    if selected_classe_id:
        classe_filter |= Q(pk=selected_classe_id)
    if selected_gruppo_id:
        gruppo_filter |= Q(pk=selected_gruppo_id)

    classi = (
        Classe.objects.filter(classe_filter)
        .annotate(
            _inactive_order=Case(
                When(attiva=True, then=0),
                default=1,
                output_field=IntegerField(),
            )
        )
        .order_by("_inactive_order", "ordine_classe", "nome_classe", "sezione_classe")
    )
    gruppi = (
        GruppoClasse.objects.filter(gruppo_filter)
        .select_related("anno_scolastico")
        .prefetch_related("classi")
        .annotate(
            _inactive_order=Case(
                When(attivo=True, then=0),
                default=1,
                output_field=IntegerField(),
            )
        )
        .order_by("_inactive_order", "-anno_scolastico__data_inizio", "nome_gruppo_classe", "id")
    )

    choices = [("", "--- nessuna classe principale ---")]
    classi_choices = [(str(classe.pk), str(classe)) for classe in classi]
    gruppi_choices = [
        (f"gruppo:{gruppo.pk}", f"{gruppo.nome_gruppo_classe} - {gruppo.anno_scolastico}")
        for gruppo in gruppi
    ]
    if classi_choices:
        choices.append(("Classi", classi_choices))
    if gruppi_choices:
        choices.append(("Gruppi classe / pluriclassi", gruppi_choices))
    return choices


def split_classe_principale_reference(value):
    value = str(value or "").strip()
    if not value:
        return None, None
    if value.startswith("gruppo:"):
        gruppo_id = value.split(":", 1)[1]
        return None, int(gruppo_id) if gruppo_id.isdigit() else None
    if value.startswith("classe:"):
        classe_id = value.split(":", 1)[1]
        return int(classe_id) if classe_id.isdigit() else None, None
    return int(value) if value.isdigit() else None, None


def classe_principale_reference_initial(profilo):
    if not profilo:
        return ""
    if getattr(profilo, "gruppo_classe_principale_id", None):
        return f"gruppo:{profilo.gruppo_classe_principale_id}"
    if getattr(profilo, "classe_principale_id", None):
        return str(profilo.classe_principale_id)
    return ""


def prime_queryset(queryset):
    list(queryset)
    return queryset


def bind_primed_queryset(field, queryset):
    """Attach an already-evaluated queryset without letting ModelChoiceField clone it."""
    field._queryset = queryset
    field.widget.choices = field.choices
    return queryset


def indirizzo_choice_queryset():
    return (
        Indirizzo.objects
        .select_related("citta", "provincia", "regione")
        .order_by("via", "numero_civico", "id")
    )


def configure_indirizzo_choice_field(field, queryset=None):
    if queryset is None:
        field.queryset = indirizzo_choice_queryset()
    else:
        bind_primed_queryset(field, queryset)
    field.required = False
    field.label_from_instance = lambda obj: obj.label_select()
    make_searchable_select(field, "Cerca un indirizzo...")
    field.widget.attrs["data-searchable-min-chars"] = "3"


def nazione_choice_queryset():
    nazioni = (
        Nazione.objects
        .filter(attiva=True)
        .exclude(nome_nazionalita="")
        .only("id", "nome_nazionalita", "ordine", "nome")
        .order_by("nome_nazionalita", "ordine", "id")
    )

    ids = []
    nazionalita_viste = set()
    for nazione in nazioni:
        chiave = nazione.nome_nazionalita.strip().casefold()
        if chiave in nazionalita_viste:
            continue
        nazionalita_viste.add(chiave)
        ids.append(nazione.pk)

    if not ids:
        return Nazione.objects.none()

    ordine = Case(
        *[When(pk=pk, then=posizione) for posizione, pk in enumerate(ids)],
        output_field=IntegerField(),
    )
    return Nazione.objects.filter(pk__in=ids).order_by(ordine)


def configure_nazionalita_field(field, queryset=None):
    if queryset is None:
        field.queryset = nazione_choice_queryset()
    else:
        bind_primed_queryset(field, queryset)
    field.required = False
    field.label_from_instance = lambda obj: obj.label_nazionalita
    make_searchable_select(field, "Cerca una nazionalita...")


def default_italia_nazione_id():
    return (
        Nazione.objects.filter(nome__iexact="Italia", attiva=True)
        .values_list("pk", flat=True)
        .first()
    )


class ClasseInlineSelect(forms.Select):
    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        return super().create_option(name, value, label, selected, index, subindex=subindex, attrs=attrs)


class GruppoClasseInlineSelect(forms.Select):
    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        option = super().create_option(name, value, label, selected, index, subindex=subindex, attrs=attrs)

        if value and hasattr(value, "instance"):
            option["attrs"]["data-anno-scolastico"] = value.instance.anno_scolastico_id
            option["attrs"]["data-class-ids"] = ",".join(
                str(classe.pk) for classe in value.instance.classi.all()
            )

        return option


class AnnoScolasticoInlineSelect(forms.Select):
    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        option = super().create_option(name, value, label, selected, index, subindex=subindex, attrs=attrs)

        if value and hasattr(value, "instance"):
            if value.instance.data_inizio:
                option["attrs"]["data-data-inizio"] = value.instance.data_inizio.isoformat()
            if value.instance.data_fine:
                option["attrs"]["data-data-fine"] = value.instance.data_fine.isoformat()

        return option


class CondizioneIscrizioneInlineSelect(forms.Select):
    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        option = super().create_option(name, value, label, selected, index, subindex=subindex, attrs=attrs)

        if value and hasattr(value, "instance"):
            option["attrs"]["data-anno-scolastico"] = value.instance.anno_scolastico_id
            option["attrs"]["data-riduzione-speciale-ammessa"] = "1" if value.instance.riduzione_speciale_ammessa else "0"

        return option


class FamiliareRelationSelectMultiple(forms.SelectMultiple):
    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        option = super().create_option(name, value, label, selected, index, subindex=subindex, attrs=attrs)

        if value and hasattr(value, "instance"):
            familiare = value.instance
            indirizzo = getattr(familiare, "indirizzo_effettivo", None)
            if indirizzo and getattr(indirizzo, "pk", None):
                option["attrs"]["data-address-id"] = str(indirizzo.pk)
                option["attrs"]["data-address-label"] = indirizzo.label_select()
                option["attrs"]["data-address-full"] = indirizzo.label_full()
                option["attrs"]["data-person-label"] = familiare.nome_completo

        return option


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
            if not selected:
                selected = getattr(self.instance, "indirizzo_effettivo", None)
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
    luogo_nascita_custom = forms.CharField(
        required=False,
        widget=forms.HiddenInput(attrs={"data-luogo-nascita-custom": "1"}),
    )
    nazione_nascita = forms.ModelChoiceField(
        queryset=Nazione.objects.none(),
        required=False,
        widget=forms.HiddenInput(attrs={"data-nazione-hidden": "1"}),
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

        if "nazione_nascita" not in self.fields:
            self.fields["nazione_nascita"] = forms.ModelChoiceField(
                queryset=Nazione.objects.none(),
                required=False,
                widget=forms.HiddenInput(attrs={"data-nazione-hidden": "1"}),
            )
        if "luogo_nascita_custom" not in self.fields:
            self.fields["luogo_nascita_custom"] = forms.CharField(
                required=False,
                widget=forms.HiddenInput(attrs={"data-luogo-nascita-custom": "1"}),
            )

        self.fields["luogo_nascita"].widget = forms.HiddenInput(attrs={"data-citta-hidden": "1"})
        self.fields["luogo_nascita"].queryset = Citta.objects.none()
        self.fields["nazione_nascita"].widget = forms.HiddenInput(attrs={"data-nazione-hidden": "1"})
        self.fields["nazione_nascita"].queryset = Nazione.objects.none()
        self.fields["luogo_nascita_custom"].widget = forms.HiddenInput(attrs={"data-luogo-nascita-custom": "1"})
        self.fields["luogo_nascita_search"].widget.attrs.update(
            {
                "placeholder": "Cerca una città...",
                "data-citta-search": "1",
                "data-include-nazioni": "1",
            }
        )

        self.fields["luogo_nascita_search"].widget.attrs["placeholder"] = "Cerca una città o uno stato estero..."

        luogo_nascita_id = None
        nazione_nascita_id = None
        luogo_nascita_label = ""
        luogo_nascita_custom = ""
        citta = None
        nazione = None

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
            nazione_nascita_id = (
                self.data.get(self.add_prefix("nazione_nascita"))
                or self.data.get("nazione_nascita")
            )
            luogo_nascita_custom = (
                self.data.get(self.add_prefix("luogo_nascita_custom"))
                or self.data.get("luogo_nascita_custom")
                or ""
            ).strip()
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
            if not luogo_nascita_id:
                nazione = self.initial.get("nazione_nascita") or getattr(self.instance, "nazione_nascita", None)
                if nazione:
                    if hasattr(nazione, "pk"):
                        nazione_nascita_id = nazione.pk
                        luogo_nascita_label = str(nazione)
                    else:
                        nazione_nascita_id = nazione
                        nazione_obj = Nazione.objects.filter(pk=nazione, attiva=True).first()
                        if nazione_obj:
                            nazione = nazione_obj
                            luogo_nascita_label = str(nazione_obj)
                        else:
                            nazione = None
            if not luogo_nascita_id and not nazione_nascita_id:
                luogo_nascita_custom = (
                    self.initial.get("luogo_nascita_custom")
                    or getattr(self.instance, "luogo_nascita_custom", "")
                    or ""
                ).strip()
                luogo_nascita_label = luogo_nascita_custom

        if luogo_nascita_id:
            self.initial["luogo_nascita"] = luogo_nascita_id
        if nazione_nascita_id:
            self.initial["nazione_nascita"] = nazione_nascita_id
        if luogo_nascita_custom:
            self.initial["luogo_nascita_custom"] = luogo_nascita_custom
        if luogo_nascita_label:
            self.initial["luogo_nascita_search"] = luogo_nascita_label
        if luogo_nascita_id:
            self.fields["luogo_nascita"].queryset = (
                Citta.objects.filter(pk=luogo_nascita_id, attiva=True)
                .select_related("provincia")
            )
        if nazione_nascita_id:
            self.fields["nazione_nascita"].queryset = Nazione.objects.filter(pk=nazione_nascita_id, attiva=True)
        if not self.is_bound and luogo_nascita_id and citta:
            self.fields["luogo_nascita"].widget.attrs["data-codice-catastale"] = citta.codice_catastale or ""
        if not self.is_bound and nazione_nascita_id and nazione:
            self.fields["nazione_nascita"].widget.attrs["data-codice-catastale"] = nazione.codice_belfiore or ""

    def clean(self):
        cleaned_data = super().clean()
        luogo_nascita = cleaned_data.get("luogo_nascita")
        nazione_nascita = cleaned_data.get("nazione_nascita")
        luogo_nascita_search = (cleaned_data.get("luogo_nascita_search") or "").strip()

        if luogo_nascita:
            cleaned_data["nazione_nascita"] = None
            cleaned_data["luogo_nascita_custom"] = ""
            return cleaned_data

        if nazione_nascita:
            cleaned_data["luogo_nascita"] = None
            cleaned_data["luogo_nascita_custom"] = ""
            return cleaned_data

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
            matched_nazione = re.match(r"^(?P<nome>.+?) \((?P<codice>Z\d{3})\)$", luogo_nascita_search, re.IGNORECASE)
            if matched_nazione:
                nazione = Nazione.objects.filter(
                    nome__iexact=matched_nazione.group("nome").strip(),
                    codice_belfiore__iexact=matched_nazione.group("codice").strip(),
                    attiva=True,
                ).first()
                if nazione:
                    cleaned_data["nazione_nascita"] = nazione
                    cleaned_data["luogo_nascita_custom"] = ""
                    cleaned_data["luogo_nascita"] = None
                    return cleaned_data

            nazione_qs = Nazione.objects.filter(nome__iexact=luogo_nascita_search, attiva=True)
            if nazione_qs.count() == 1:
                cleaned_data["nazione_nascita"] = nazione_qs.first()
                cleaned_data["luogo_nascita_custom"] = ""
            else:
                cleaned_data["nazione_nascita"] = None
                cleaned_data["luogo_nascita_custom"] = luogo_nascita_search
            cleaned_data["luogo_nascita"] = None
            return cleaned_data

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

        self.fields["via"].label = "Via / Strada / Piazza"
        self.fields["via"].widget.attrs["placeholder"] = "Via Roma, Piazza Maggiore, Viale dei Mille, etc."
        self.fields["numero_civico"].widget.attrs["placeholder"] = "Es. 15, 3/B, interno 2, etc."
        self.fields["citta"].widget = forms.HiddenInput(attrs={"data-citta-hidden": "1"})
        self.fields["citta"].queryset = Citta.objects.none()
        self.fields["citta_search"].widget.attrs.update(
            {
                "placeholder": "Cerca una città...",
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

#FORMS PER LE FAMIGLIE LOGICHE
class FamigliaForm(forms.Form):
    cognome_famiglia = forms.CharField(required=False, disabled=True)
    indirizzo_principale = forms.CharField(required=False, disabled=True)
    attiva = forms.BooleanField(required=False, disabled=True)
    note = forms.CharField(required=False, disabled=True, widget=forms.Textarea(attrs={"rows": 3}))

    def __init__(self, *args, **kwargs):
        kwargs.pop("instance", None)
        super().__init__(*args, **kwargs)
#FINE FORMS PER LE FAMIGLIE

#INIZIO FORMS PER I FAMILIARI
class FamiliareForm(IndirizzoSearchMixin, LuogoNascitaCittaFkMixin, forms.ModelForm):
    PERSONA_FORM_FIELDS = (
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
        "attivo",
        "note",
    )

    indirizzo = forms.ModelChoiceField(queryset=Indirizzo.objects.none(), required=False)
    nome = forms.CharField(max_length=100)
    cognome = forms.CharField(max_length=100)
    telefono = forms.CharField(max_length=40, required=False)
    email = forms.EmailField(required=False)
    codice_fiscale = forms.CharField(max_length=16, required=False)
    sesso = forms.ChoiceField(choices=[("", "---------")] + SESSO_CHOICES, required=False)
    data_nascita = forms.DateField(
        required=False,
        input_formats=["%Y-%m-%d", "%d/%m/%Y"],
        widget=html5_date_input(),
    )
    luogo_nascita = forms.ModelChoiceField(queryset=Citta.objects.none(), required=False)
    nazione_nascita = forms.ModelChoiceField(
        queryset=Nazione.objects.none(),
        required=False,
        widget=forms.HiddenInput(attrs={"data-nazione-hidden": "1"}),
    )
    luogo_nascita_custom = forms.CharField(
        required=False,
        widget=forms.HiddenInput(attrs={"data-luogo-nascita-custom": "1"}),
    )
    nazionalita = forms.ModelChoiceField(queryset=Nazione.objects.none(), required=False)
    attivo = forms.BooleanField(required=False)
    note = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 4}))

    class Meta:
        model = Familiare
        fields = [
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
            "nazione_nascita",
            "luogo_nascita_custom",
            "nazionalita",
            "convivente",
            "referente_principale",
            "abilitato_scambio_retta",
            "attivo",
            "note",
        ]

    def __init__(self, *args, **kwargs):
        shared_lookups = kwargs.pop("shared_lookups", None) or {}
        enable_work_profile_fields = kwargs.pop("enable_work_profile_fields", False)
        enable_direct_relations_field = kwargs.pop("enable_direct_relations_field", False)
        super().__init__(*args, **kwargs)

        if getattr(self.instance, "pk", None) and not self.is_bound:
            for field_name in self.PERSONA_FORM_FIELDS:
                if field_name == "attivo":
                    self.initial.setdefault(field_name, getattr(self.instance, "attivo", True))
                    continue
                value = getattr(self.instance, field_name, None)
                if value is not None:
                    self.initial.setdefault(field_name, value)

        if enable_work_profile_fields:
            self.setup_work_profile_fields()
        if enable_direct_relations_field:
            self.setup_studenti_collegati_field()

        self.fields["attivo"].widget = forms.HiddenInput()
        self.fields["indirizzo"].required = False
        self.fields["indirizzo"].help_text = (
            "Se lasci vuoto, verra usato automaticamente l'indirizzo principale collegato, quando disponibile."
        )
        relazioni = shared_lookups.get("relazioni_familiari")
        if relazioni is None:
            self.fields["relazione_familiare"].queryset = (
                RelazioneFamiliare.objects.order_by("ordine", "relazione")
            )
        else:
            bind_primed_queryset(self.fields["relazione_familiare"], relazioni)
        self.fields["relazione_familiare"].empty_label = None
        configure_indirizzo_choice_field(self.fields["indirizzo"], shared_lookups.get("indirizzi"))

        self.setup_indirizzo_search()
        self.setup_luogo_nascita_autocomplete_fk()
        configure_nazionalita_field(self.fields["nazionalita"], shared_lookups.get("nazionalita"))
        self.fields["nome"].widget.attrs["data-cf-nome"] = "1"
        self.fields["cognome"].widget.attrs["data-cf-cognome"] = "1"
        self.fields["data_nascita"].widget.attrs["data-cf-data-nascita"] = "1"
        self.fields["sesso"].widget.attrs["data-cf-sesso"] = "1"
        self.fields["luogo_nascita"].widget.attrs["data-cf-luogo-id"] = "1"
        self.fields["nazione_nascita"].widget.attrs["data-cf-nazione-id"] = "1"
        self.fields["codice_fiscale"].widget.attrs["data-cf-output"] = "1"

        if not self.instance.pk and not self.is_bound and "attivo" not in self.initial:
            self.initial["attivo"] = True
        if not self.instance.pk and not self.is_bound and "referente_principale" not in self.initial:
            self.initial["referente_principale"] = True
        if not self.instance.pk and not self.is_bound and not self.initial.get("nazionalita"):
            italia_id = shared_lookups.get("default_italia_id") or default_italia_nazione_id()
            if italia_id:
                self.initial["nazionalita"] = italia_id
                self.fields["nazionalita"].initial = italia_id

        if not self.instance.pk and not self.is_bound and not self.initial.get("relazione_familiare"):
            prima_relazione = self.fields["relazione_familiare"].queryset.first()
            if prima_relazione:
                self.initial["relazione_familiare"] = prima_relazione.pk

    def _submitted_pk_values(self, field_name):
        values = []
        if hasattr(self.data, "getlist"):
            raw_values = self.data.getlist(self.add_prefix(field_name))
        else:
            raw_values = self.data.get(self.add_prefix(field_name), [])
            if raw_values is None:
                raw_values = []
            elif not isinstance(raw_values, (list, tuple)):
                raw_values = [raw_values]
        for raw_value in raw_values:
            try:
                values.append(int(raw_value))
            except (TypeError, ValueError):
                continue
        return values

    def setup_studenti_collegati_field(self):
        selected_ids = set()
        if getattr(self.instance, "pk", None):
            selected_ids.update(
                self.instance.relazioni_studenti.filter(attivo=True).values_list("studente_id", flat=True)
            )
        elif not self.is_bound:
            initial_studenti = self.initial.get("studenti_collegati") or []
            if not isinstance(initial_studenti, (list, tuple, set)):
                initial_studenti = [initial_studenti]
            for studente_id in initial_studenti:
                try:
                    selected_ids.add(int(studente_id))
                except (TypeError, ValueError):
                    continue
        if self.is_bound:
            selected_ids.update(self._submitted_pk_values("studenti_collegati"))

        queryset = (
            Studente.objects.filter(Q(attivo=True) | Q(pk__in=selected_ids))
            .order_by("cognome", "nome", "pk")
        )
        self.fields["studenti_collegati"] = forms.ModelMultipleChoiceField(
            queryset=queryset,
            required=False,
            label="Figli e figlie collegati",
            help_text="Collega direttamente il familiare a bambini o studenti",
            widget=forms.SelectMultiple(
                attrs={
                    "class": "form-control direct-relation-select",
                    "size": 3,
                    "data-student-surname-suggestions": "1",
                    "data-student-surname-min-chars": "3",
                }
            ),
        )
        self.fields["studenti_collegati"].label_from_instance = studente_direct_relation_label
        if selected_ids and not self.is_bound:
            self.initial["studenti_collegati"] = list(selected_ids)

    def setup_work_profile_fields(self):
        from gestione_amministrativa.models import Dipendente, RuoloAnagraficoDipendente, StatoDipendente

        profilo = None
        if getattr(self.instance, "pk", None):
            persona_id = getattr(self.instance, "persona_id", None)
            if persona_id:
                profilo = Dipendente.objects.filter(persona_collegata_id=persona_id).first()

        self.fields["profilo_dipendente_attivo"] = forms.BooleanField(
            required=False,
            label="Anche dipendente",
            help_text="Crea o collega il profilo amministrativo senza duplicare l'anagrafica.",
        )
        self.fields["profilo_educatore_attivo"] = forms.BooleanField(
            required=False,
            label="Anche educatore",
            help_text="Abilita classe principale o materia, studenti collegati, contratto, buste paga e documenti.",
        )
        self.fields["classe_principale_educatore"] = forms.ChoiceField(
            choices=classe_principale_reference_choices(
                selected_classe_id=getattr(profilo, "classe_principale_id", None),
                selected_gruppo_id=getattr(profilo, "gruppo_classe_principale_id", None),
            ),
            required=False,
            label="Classe principale",
            help_text="Per educatori con classe fissa: mostra studenti collegati o pluriclasse.",
        )
        make_searchable_select(self.fields["classe_principale_educatore"], "Cerca una classe o pluriclasse...")
        self.fields["materia_educatore"] = forms.CharField(
            required=False,
            label="Materia",
            help_text="Per educatori che seguono una materia su piu classi, ad esempio Inglese o Musica.",
            max_length=120,
            widget=forms.TextInput(attrs={"placeholder": "Es. Inglese, Musica, Arte..."}),
        )
        self.fields["profilo_mansione"] = forms.CharField(
            required=False,
            label="Mansione",
            help_text="Usata per i profili dipendente.",
            max_length=160,
            widget=forms.TextInput(attrs={"placeholder": "Es. Segreteria, cucina, amministrazione..."}),
        )
        self.fields["profilo_iban"] = forms.CharField(
            required=False,
            label="Dati di pagamento",
            help_text="IBAN o riferimento utile per pagamenti e buste paga.",
            max_length=34,
            widget=forms.TextInput(attrs={"placeholder": "Es. IT60X0542811101000000123456"}),
        )
        self.fields["profilo_stato"] = forms.ChoiceField(
            choices=StatoDipendente.choices,
            required=False,
            label="Stato lavorativo",
        )

        if not profilo:
            self.initial.setdefault("profilo_stato", StatoDipendente.ATTIVO)
            return

        self.initial["profilo_dipendente_attivo"] = profilo.ruolo_anagrafico == RuoloAnagraficoDipendente.DIPENDENTE
        self.initial["profilo_educatore_attivo"] = profilo.ruolo_anagrafico == RuoloAnagraficoDipendente.EDUCATORE
        self.initial["classe_principale_educatore"] = classe_principale_reference_initial(profilo)
        self.initial["materia_educatore"] = profilo.materia
        self.initial["profilo_mansione"] = profilo.mansione
        self.initial["profilo_iban"] = profilo.iban
        self.initial["profilo_stato"] = profilo.stato

    def clean(self):
        cleaned_data = super().clean()
        if cleaned_data.get("profilo_dipendente_attivo") and cleaned_data.get("profilo_educatore_attivo"):
            message = "Scegli Dipendente oppure Educatore: la stessa persona non puo avere entrambi i profili."
            self.add_error("profilo_dipendente_attivo", message)
            self.add_error("profilo_educatore_attivo", message)
        return cleaned_data

    def save(self, commit=True):
        familiare = super().save(commit=False)
        for field_name in self.PERSONA_FORM_FIELDS:
            if field_name == "attivo" or field_name not in self.cleaned_data:
                continue
            setattr(familiare, field_name, self.cleaned_data.get(field_name))

        if commit:
            familiare.save()
            self.save_m2m()
            sync_principal_contacts(
                familiare,
                indirizzo=familiare.indirizzo,
                telefono=familiare.telefono,
                email=familiare.email,
            )
            if "studenti_collegati" in self.fields:
                set_familiare_studenti(familiare, self.cleaned_data.get("studenti_collegati", []))
        return familiare

    def clean_telefono(self):
        return validate_and_normalize_phone_number(self.cleaned_data.get("telefono"))


class FamiliareInlineForm(FamiliareForm):
    class Meta(FamiliareForm.Meta):
        fields = FamiliareForm.Meta.fields

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


class CachedEmptyFormSetMixin:
    @cached_property
    def empty_form(self):
        return super().empty_form


class IgnoreBlankExtraFormSetMixin(CachedEmptyFormSetMixin):
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


class IgnoreBlankExtraModelFormSet(IgnoreBlankExtraFormSetMixin, BaseModelFormSet):
    pass


class IgnoreBlankExtraInlineFormSet(IgnoreBlankExtraFormSetMixin, BaseInlineFormSet):
    pass


def build_person_inline_shared_lookups(*, include_relazioni=False):
    lookups = {
        "indirizzi": prime_queryset(indirizzo_choice_queryset()),
        "nazionalita": prime_queryset(nazione_choice_queryset()),
        "default_italia_id": default_italia_nazione_id(),
    }
    if include_relazioni:
        lookups["relazioni_familiari"] = prime_queryset(
            RelazioneFamiliare.objects.order_by("ordine", "relazione")
        )
    return lookups


class FamiliareInlineBaseFormSet(IgnoreBlankExtraModelFormSet):
    meaningful_field_names = (
        "cognome",
        "nome",
        "telefono",
        "email",
        "codice_fiscale",
        "data_nascita",
        "luogo_nascita_search",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.shared_lookups = build_person_inline_shared_lookups(include_relazioni=True)

    def get_form_kwargs(self, index):
        kwargs = super().get_form_kwargs(index)
        kwargs["shared_lookups"] = self.shared_lookups
        return kwargs


LogicalFamiliareFormSet = modelformset_factory(
    Familiare,
    form=FamiliareInlineForm,
    formset=FamiliareInlineBaseFormSet,
    extra=1,
    can_delete=True,
)
FamiliareFormSet = LogicalFamiliareFormSet

#FINE FORMS PER I FAMILIARI

#INIZIO FORM PER I DOCUMENTI DEI FAMILIARI
class DocumentoBaseForm(forms.ModelForm):
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
        shared_lookups = kwargs.pop("shared_lookups", None) or {}
        super().__init__(*args, **kwargs)

        tipi_documento = shared_lookups.get("tipi_documento")
        primo_tipo = shared_lookups.get("primo_tipo_documento")
        if tipi_documento is None:
            tipi_documento = prime_queryset(
                TipoDocumento.objects.filter(attivo=True).order_by("ordine", "tipo_documento")
            )
            primo_tipo = next(iter(tipi_documento), None)

        bind_primed_queryset(self.fields["tipo_documento"], tipi_documento)
        self.fields["tipo_documento"].error_messages["required"] = "Seleziona un tipo documento."

        if primo_tipo:
            self.fields["tipo_documento"].empty_label = None
            if (
                not self.is_bound
                and not getattr(self.instance, "pk", None)
                and not self.initial.get("tipo_documento")
            ):
                self.initial["tipo_documento"] = primo_tipo.pk
                self.fields["tipo_documento"].initial = primo_tipo.pk


class DocumentoInlineForm(DocumentoBaseForm):
    def _has_uploaded_file(self):
        return bool(self.files.get(self.add_prefix("file")))

    def has_changed(self):
        changed = super().has_changed()
        if not changed:
            return False

        if self.data.get(self.add_prefix("DELETE")):
            return True

        meaningful_values = [
            self.data.get(self.add_prefix("descrizione"), ""),
            self.data.get(self.add_prefix("scadenza"), ""),
            self.data.get(self.add_prefix("note"), ""),
        ]

        if not self._has_uploaded_file() and not any((value or "").strip() for value in meaningful_values):
            return False

        return True


class DocumentoInlineBaseFormSet(IgnoreBlankExtraInlineFormSet):
    meaningful_field_names = (
        "descrizione",
        "scadenza",
        "note",
    )

    def _is_meaningfully_filled(self, form):
        return bool(form.files.get(form.add_prefix("file"))) or super()._is_meaningfully_filled(form)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        tipi_documento = prime_queryset(
            TipoDocumento.objects.filter(attivo=True).order_by("ordine", "tipo_documento")
        )
        self.shared_lookups = {
            "tipi_documento": tipi_documento,
            "primo_tipo_documento": next(iter(tipi_documento), None),
        }

    def get_form_kwargs(self, index):
        kwargs = super().get_form_kwargs(index)
        kwargs["shared_lookups"] = self.shared_lookups
        return kwargs


class DocumentoFamiliareForm(DocumentoInlineForm):
    pass


DocumentoFamiliareFormSet = inlineformset_factory(
    Familiare,
    Documento,
    form=DocumentoFamiliareForm,
    formset=DocumentoInlineBaseFormSet,
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
            "nazione_nascita",
            "luogo_nascita_custom",
            "nazionalita",
            "codice_fiscale",
            "indirizzo",
            "attivo",
        ]
        widgets = {
            "data_nascita": html5_date_input(),
        }

    def __init__(self, *args, **kwargs):
        shared_lookups = kwargs.pop("shared_lookups", None) or {}
        super().__init__(*args, **kwargs)

        configure_indirizzo_choice_field(self.fields["indirizzo"], shared_lookups.get("indirizzi"))
        self.fields["attivo"].widget = forms.HiddenInput()

        self.setup_indirizzo_search()
        self.setup_luogo_nascita_autocomplete_fk()
        configure_nazionalita_field(self.fields["nazionalita"], shared_lookups.get("nazionalita"))
        self.fields["nome"].widget.attrs["data-cf-nome"] = "1"
        self.fields["cognome"].widget.attrs["data-cf-cognome"] = "1"
        self.fields["data_nascita"].widget.attrs["data-cf-data-nascita"] = "1"
        self.fields["sesso"].widget.attrs["data-cf-sesso"] = "1"
        self.fields["luogo_nascita"].widget.attrs["data-cf-luogo-id"] = "1"
        self.fields["nazione_nascita"].widget.attrs["data-cf-nazione-id"] = "1"
        self.fields["codice_fiscale"].widget.attrs["data-cf-output"] = "1"

        if not self.instance.pk and not self.is_bound and "attivo" not in self.initial:
            self.initial["attivo"] = True
        if not self.instance.pk and not self.is_bound and not self.initial.get("nazionalita"):
            italia_id = shared_lookups.get("default_italia_id") or default_italia_nazione_id()
            if italia_id:
                self.initial["nazionalita"] = italia_id
                self.fields["nazionalita"].initial = italia_id

    def clean(self):
        return super().clean()

    def save(self, commit=True):
        studente = super().save(commit=commit)
        if commit:
            sync_principal_contacts(studente, indirizzo=studente.indirizzo)
        return studente


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


class StudenteInlineBaseFormSet(IgnoreBlankExtraModelFormSet):
    meaningful_field_names = (
        "nome",
        "data_nascita",
        "luogo_nascita_search",
        "codice_fiscale",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.shared_lookups = build_person_inline_shared_lookups()

    def get_form_kwargs(self, index):
        kwargs = super().get_form_kwargs(index)
        kwargs["shared_lookups"] = self.shared_lookups
        return kwargs


LogicalStudenteFormSet = modelformset_factory(
    Studente,
    form=StudenteInlineForm,
    formset=StudenteInlineBaseFormSet,
    extra=1,
    can_delete=True,
)
StudenteFormSet = LogicalStudenteFormSet

class StudenteStandaloneForm(IndirizzoSearchMixin, LuogoNascitaCittaFkMixin, forms.ModelForm):
    class Meta:
        model = Studente
        fields = [
            "cognome",
            "nome",
            "sesso",
            "data_nascita",
            "luogo_nascita",
            "nazione_nascita",
            "luogo_nascita_custom",
            "nazionalita",
            "codice_fiscale",
            "indirizzo",
            "attivo",
            "note",
        ]
        widgets = {
            "data_nascita": html5_date_input(),
            "note": forms.Textarea(attrs={"rows": 4}),
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
        self.setup_familiari_collegati_field()

        self.setup_indirizzo_search()
        self.setup_luogo_nascita_autocomplete_fk()
        configure_nazionalita_field(self.fields["nazionalita"])
        self.fields["attivo"].widget = forms.HiddenInput()
        self.fields["nome"].widget.attrs["data-cf-nome"] = "1"
        self.fields["cognome"].widget.attrs["data-cf-cognome"] = "1"
        self.fields["data_nascita"].widget.attrs["data-cf-data-nascita"] = "1"
        self.fields["sesso"].widget.attrs["data-cf-sesso"] = "1"
        self.fields["luogo_nascita"].widget.attrs["data-cf-luogo-id"] = "1"
        self.fields["nazione_nascita"].widget.attrs["data-cf-nazione-id"] = "1"
        self.fields["codice_fiscale"].widget.attrs["data-cf-output"] = "1"

        if not self.instance.pk and not self.is_bound and "attivo" not in self.initial:
            self.initial["attivo"] = True
        if not self.instance.pk and not self.is_bound and not self.initial.get("nazionalita"):
            italia_id = default_italia_nazione_id()
            if italia_id:
                self.initial["nazionalita"] = italia_id
                self.fields["nazionalita"].initial = italia_id

    def _submitted_pk_values(self, field_name):
        values = []
        if hasattr(self.data, "getlist"):
            raw_values = self.data.getlist(self.add_prefix(field_name))
        else:
            raw_values = self.data.get(self.add_prefix(field_name), [])
            if raw_values is None:
                raw_values = []
            elif not isinstance(raw_values, (list, tuple)):
                raw_values = [raw_values]
        for raw_value in raw_values:
            try:
                values.append(int(raw_value))
            except (TypeError, ValueError):
                continue
        return values

    def setup_familiari_collegati_field(self):
        selected_ids = set()
        if getattr(self.instance, "pk", None):
            prefetched_relations = getattr(self.instance, "relazioni_familiari_attive_prefetch", None)
            if prefetched_relations is not None:
                selected_ids.update(relation.familiare_id for relation in prefetched_relations)
            else:
                selected_ids.update(
                    self.instance.relazioni_familiari.filter(attivo=True).values_list("familiare_id", flat=True)
                )
        elif not self.is_bound:
            initial_familiari = self.initial.get("familiari_collegati") or []
            if not isinstance(initial_familiari, (list, tuple, set)):
                initial_familiari = [initial_familiari]
            for familiare_id in initial_familiari:
                try:
                    selected_ids.add(int(familiare_id))
                except (TypeError, ValueError):
                    continue
        if self.is_bound:
            selected_ids.update(self._submitted_pk_values("familiari_collegati"))

        queryset = (
            Familiare.objects.select_related(
                "persona",
                "persona__indirizzo",
                "persona__indirizzo__citta",
                "persona__indirizzo__provincia",
                "persona__indirizzo__regione",
                "relazione_familiare",
            )
            .prefetch_related(
                Prefetch("persona__indirizzi_anagrafici", queryset=anagrafica_address_link_queryset()),
                Prefetch("indirizzi_anagrafici", queryset=anagrafica_address_link_queryset()),
            )
            .filter(Q(persona__pk__isnull=False) | Q(pk__in=selected_ids))
            .order_by("persona__cognome", "persona__nome", "pk")
        )
        self.fields["familiari_collegati"] = forms.ModelMultipleChoiceField(
            queryset=queryset,
            required=False,
            label="Genitori e tutori collegati",
            help_text="Digita almeno 3 lettere del cognome: vedrai i familiari gia presenti che possono essere collegati.",
            widget=FamiliareRelationSelectMultiple(
                attrs={
                    "class": "form-control direct-relation-select",
                    "size": 3,
                    "data-parent-surname-suggestions": "1",
                    "data-parent-surname-min-chars": "3",
                }
            ),
        )
        self.fields["familiari_collegati"].label_from_instance = familiare_direct_relation_label
        if selected_ids and not self.is_bound:
            self.initial["familiari_collegati"] = list(selected_ids)

    def clean(self):
        return super().clean()

    def save(self, commit=True):
        studente = super().save(commit=commit)
        if commit:
            sync_principal_contacts(studente, indirizzo=studente.indirizzo)
            set_studente_familiari(studente, self.cleaned_data.get("familiari_collegati", []))
        return studente

#FINE FORM PER GLI STUDENTI

#INIZIO FORM PER I DOCUMENTI

class DocumentoFamigliaForm(DocumentoBaseForm):
    pass


class DocumentoFamigliaInlineForm(DocumentoInlineForm):
    pass


DocumentoFamigliaFormSet = modelformset_factory(
    Documento,
    form=DocumentoFamigliaInlineForm,
    extra=1,
    can_delete=True,
)

class DocumentoStudenteForm(DocumentoInlineForm):
    pass

DocumentoStudenteFormSet = inlineformset_factory(
    Studente,
    Documento,
    form=DocumentoStudenteForm,
    formset=DocumentoInlineBaseFormSet,
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
            "gruppo_classe",
            "data_iscrizione",
            "data_fine_iscrizione",
            "stato_iscrizione",
            "condizione_iscrizione",
            "rate_custom",
            "agevolazione",
            "riduzione_speciale",
            "importo_riduzione_speciale",
            "non_pagante",
            "modalita_pagamento_retta",
            "sconto_unica_soluzione_tipo",
            "sconto_unica_soluzione_valore",
            "scadenza_pagamento_unica",
            "attiva",
            "note_amministrative",
            "note",
        ]
        widgets = {
            "anno_scolastico": AnnoScolasticoInlineSelect(),
            "classe": ClasseInlineSelect(),
            "gruppo_classe": GruppoClasseInlineSelect(),
            "condizione_iscrizione": CondizioneIscrizioneInlineSelect(),
            "data_iscrizione": html5_date_input(),
            "data_fine_iscrizione": html5_date_input(),
            "scadenza_pagamento_unica": html5_date_input(),
            "note_amministrative": forms.TextInput(),
            "note": forms.TextInput(),
        }

    def __init__(self, *args, **kwargs):
        shared_lookups = kwargs.pop("shared_lookups", None) or {}
        super().__init__(*args, **kwargs)

        anno_scolastico_qs = shared_lookups.get("anno_scolastico_queryset")
        if anno_scolastico_qs is None:
            anno_scolastico_qs = prime_queryset(
                self.fields["anno_scolastico"].queryset.order_by("-data_inizio", "-id")
            )
        bind_primed_queryset(self.fields["anno_scolastico"], anno_scolastico_qs)

        classe_qs = shared_lookups.get("classe_queryset")
        if classe_qs is None:
            classe_qs = prime_queryset(
                self.fields["classe"].queryset.order_by(
                    "ordine_classe",
                    "nome_classe",
                    "sezione_classe",
                )
            )
        bind_primed_queryset(self.fields["classe"], classe_qs)

        gruppo_classe_qs = shared_lookups.get("gruppo_classe_queryset")
        if gruppo_classe_qs is None:
            gruppo_classe_qs = prime_queryset(
                GruppoClasse.objects.select_related("anno_scolastico").prefetch_related("classi").order_by(
                    "-anno_scolastico__data_inizio",
                    "nome_gruppo_classe",
                    "id",
                )
            )
        bind_primed_queryset(self.fields["gruppo_classe"], gruppo_classe_qs)
        self.fields["gruppo_classe"].label = "Pluriclasse"
        self.fields["gruppo_classe"].help_text = (
            "Compila solo se lo studente frequenta una Pluriclasse; la Classe resta l'assegnazione standard."
        )
        self.fields["gruppo_classe"].required = False

        stato_iscrizione_qs = shared_lookups.get("stato_iscrizione_queryset")
        if stato_iscrizione_qs is None:
            stato_iscrizione_qs = prime_queryset(
                StatoIscrizione.objects.filter(attiva=True).order_by("ordine", "stato_iscrizione")
            )
        bind_primed_queryset(self.fields["stato_iscrizione"], stato_iscrizione_qs)
        primo_stato_iscrizione = shared_lookups.get("primo_stato_iscrizione")
        if primo_stato_iscrizione is None:
            primo_stato_iscrizione = next(iter(stato_iscrizione_qs), None)

        condizione_qs = shared_lookups.get("condizione_queryset")
        if condizione_qs is None:
            condizione_qs = prime_queryset(
                CondizioneIscrizione.objects.select_related("anno_scolastico").filter(attiva=True).order_by(
                    "-anno_scolastico__data_inizio",
                    "nome_condizione_iscrizione",
                )
            )
        bind_primed_queryset(self.fields["condizione_iscrizione"], condizione_qs)
        self.fields["rate_custom"].label = "Numero rate personalizzato"
        self.fields["rate_custom"].required = False
        self.fields["rate_custom"].widget.attrs.update(
            {
                "min": "1",
                "max": "36",
                "inputmode": "numeric",
                "placeholder": "Default",
                "data-rate-custom-input": "1",
            }
        )
        if self.instance.pk:
            self.fields["rate_custom"].disabled = True
            self.fields["rate_custom"].help_text = "Per modificare un piano avviato usa Rimodula rate future."
            self.fields["rate_custom"].widget.attrs["data-rate-custom-locked"] = "1"
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
        self.fields["modalita_pagamento_retta"].label = "Modalita pagamento retta"
        self.fields["sconto_unica_soluzione_tipo"].label = "Sconto unica soluzione"
        self.fields["sconto_unica_soluzione_valore"].label = "Valore sconto"
        self.fields["sconto_unica_soluzione_valore"].required = False
        self.fields["sconto_unica_soluzione_valore"].localize = True
        self.fields["sconto_unica_soluzione_valore"].to_python = (
            lambda value, _field=self.fields["sconto_unica_soluzione_valore"]: italian_decimal_to_python(_field, value)
        )
        self.fields["sconto_unica_soluzione_valore"].widget = forms.TextInput()
        merge_widget_classes(
            self.fields["sconto_unica_soluzione_valore"].widget,
            "currency-field",
            "currency-field-compact",
        )
        self.fields["sconto_unica_soluzione_valore"].widget.attrs.update(
            {
                "autocomplete": "off",
                "inputmode": "decimal",
                "placeholder": "0,00",
                "maxlength": "12",
            }
        )
        self.fields["scadenza_pagamento_unica"].label = "Scadenza pagamento unico"
        self.fields["scadenza_pagamento_unica"].required = False
        self.fields["agevolazione"].required = False
        agevolazione_qs = shared_lookups.get("agevolazione_queryset")
        if agevolazione_qs is None:
            try:
                agevolazione_qs = prime_queryset(
                    Agevolazione.objects.filter(attiva=True).order_by("nome_agevolazione")
                )
            except DatabaseError:
                agevolazione_qs = Agevolazione.objects.none()
        bind_primed_queryset(self.fields["agevolazione"], agevolazione_qs)

        if not self.instance.pk and not self.is_bound and not self.initial.get("anno_scolastico"):
            anno_predefinito = shared_lookups.get("default_anno_scolastico")
            if anno_predefinito is None:
                anno_predefinito = resolve_default_anno_scolastico(self.fields["anno_scolastico"].queryset)
            if anno_predefinito:
                self.initial["anno_scolastico"] = anno_predefinito.pk
                if not self.initial.get("data_iscrizione") and anno_predefinito.data_inizio:
                    self.initial["data_iscrizione"] = anno_predefinito.data_inizio
                if not self.initial.get("data_fine_iscrizione") and anno_predefinito.data_fine:
                    self.initial["data_fine_iscrizione"] = anno_predefinito.data_fine

        if not self.instance.pk and not self.is_bound and not self.initial.get("data_iscrizione"):
            anno_id = self.initial.get("anno_scolastico")
            if anno_id:
                anno = next((item for item in anno_scolastico_qs if str(item.pk) == str(anno_id)), None)
                if anno and anno.data_inizio:
                    self.initial["data_iscrizione"] = anno.data_inizio

        if not self.instance.pk and not self.is_bound and not self.initial.get("stato_iscrizione"):
            if primo_stato_iscrizione:
                self.initial["stato_iscrizione"] = primo_stato_iscrizione.pk

        if not getattr(self.instance, "pk", None):
            self.fields["data_fine_iscrizione"].widget = HiddenInput()

    def clean(self):
        cleaned_data = super().clean()
        if cleaned_data.get("sconto_unica_soluzione_valore") is None:
            cleaned_data["sconto_unica_soluzione_valore"] = Decimal("0.00")
        anno_scolastico = cleaned_data.get("anno_scolastico")
        if anno_scolastico:
            if not cleaned_data.get("data_iscrizione"):
                cleaned_data["data_iscrizione"] = anno_scolastico.data_inizio
            if not cleaned_data.get("data_fine_iscrizione"):
                cleaned_data["data_fine_iscrizione"] = anno_scolastico.data_fine
        return cleaned_data

    def has_changed(self):
        if getattr(self.instance, "pk", None) or not self.is_bound:
            return super().has_changed()

        return self._has_meaningful_bound_data()

    def _has_meaningful_bound_data(self):
        def raw_value(field_name):
            value = self.data.get(self.add_prefix(field_name), "")
            return str(value or "").strip()

        meaningful_text_fields = [
            "classe",
            "gruppo_classe",
            "condizione_iscrizione",
            "rate_custom",
            "agevolazione",
            "scadenza_pagamento_unica",
            "note_amministrative",
            "note",
        ]
        if any(raw_value(field_name) for field_name in meaningful_text_fields):
            return True

        if raw_value("modalita_pagamento_retta") == Iscrizione.MODALITA_PAGAMENTO_UNICA_SOLUZIONE:
            return True
        if raw_value("sconto_unica_soluzione_tipo") not in {"", Iscrizione.SCONTO_UNICA_NESSUNO}:
            return True
        for field_name in ("riduzione_speciale", "non_pagante"):
            if raw_value(field_name).lower() not in {"", "0", "false"}:
                return True

        for field_name in ("importo_riduzione_speciale", "sconto_unica_soluzione_valore"):
            if self._decimal_bound_value_is_nonzero(raw_value(field_name)):
                return True

        return False

    @staticmethod
    def _decimal_bound_value_is_nonzero(value):
        value = str(value or "").strip()
        if not value:
            return False

        normalized = value.replace("EUR", "").replace(" ", "")
        if "," in normalized:
            normalized = normalized.replace(".", "").replace(",", ".")

        try:
            return Decimal(normalized) != Decimal("0")
        except Exception:
            return True


class IscrizioneStudenteInlineBaseFormSet(CachedEmptyFormSetMixin, BaseInlineFormSet):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        anno_scolastico_queryset = prime_queryset(
            AnnoScolastico.objects.order_by("-data_inizio", "-id")
        )
        classe_queryset = prime_queryset(
            Classe.objects.order_by(
                "ordine_classe",
                "nome_classe",
                "sezione_classe",
            )
        )
        gruppo_classe_queryset = prime_queryset(
            GruppoClasse.objects.select_related("anno_scolastico").prefetch_related("classi").order_by(
                "-anno_scolastico__data_inizio",
                "nome_gruppo_classe",
                "id",
            )
        )
        stato_iscrizione_queryset = prime_queryset(
            StatoIscrizione.objects.filter(attiva=True).order_by("ordine", "stato_iscrizione")
        )
        condizione_queryset = prime_queryset(
            CondizioneIscrizione.objects.select_related("anno_scolastico").filter(attiva=True).order_by(
                "-anno_scolastico__data_inizio",
                "nome_condizione_iscrizione",
            )
        )
        try:
            agevolazione_queryset = prime_queryset(
                Agevolazione.objects.filter(attiva=True).order_by("nome_agevolazione")
            )
        except DatabaseError:
            agevolazione_queryset = Agevolazione.objects.none()

        self.shared_lookups = {
            "anno_scolastico_queryset": anno_scolastico_queryset,
            "classe_queryset": classe_queryset,
            "gruppo_classe_queryset": gruppo_classe_queryset,
            "stato_iscrizione_queryset": stato_iscrizione_queryset,
            "primo_stato_iscrizione": next(iter(stato_iscrizione_queryset), None),
            "condizione_queryset": condizione_queryset,
            "agevolazione_queryset": agevolazione_queryset,
            "default_anno_scolastico": resolve_default_anno_scolastico(anno_scolastico_queryset),
        }

    def get_form_kwargs(self, index):
        kwargs = super().get_form_kwargs(index)
        kwargs["shared_lookups"] = self.shared_lookups
        return kwargs


IscrizioneStudenteFormSet = inlineformset_factory(
    Studente,
    Iscrizione,
    form=IscrizioneStudenteInlineForm,
    formset=IscrizioneStudenteInlineBaseFormSet,
    fk_name="studente",
    extra=1,
    can_delete=True,
)

#FINE FORM PER I DOCUMENTI
