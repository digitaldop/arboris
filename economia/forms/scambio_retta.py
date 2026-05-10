from datetime import datetime, time

from django import forms
from anagrafica.models import Familiare, Studente, StudenteFamiliare
from anagrafica.forms import make_searchable_select
from arboris.form_widgets import apply_eur_currency_widget
from scuola.models import AnnoScolastico
from scuola.utils import resolve_default_anno_scolastico

from economia.models import PrestazioneScambioRetta, ScambioRetta, TariffaScambioRetta


MONTH_CHOICES = [
    (1, "Gennaio"),
    (2, "Febbraio"),
    (3, "Marzo"),
    (4, "Aprile"),
    (5, "Maggio"),
    (6, "Giugno"),
    (7, "Luglio"),
    (8, "Agosto"),
    (9, "Settembre"),
    (10, "Ottobre"),
    (11, "Novembre"),
    (12, "Dicembre"),
]


def parse_quarter_hour_choice(value):
    if not value:
        return None
    return datetime.strptime(value, "%H:%M").time()


TIME_SLOT_CHOICES = [("", "--:--")]
for hour in range(24):
    for minute in range(0, 60, 15):
        slot = time(hour=hour, minute=minute).strftime("%H:%M")
        TIME_SLOT_CHOICES.append((slot, slot))


def tariffa_scambio_retta_choice_label(tariffa):
    label = f"{tariffa.valore_orario} \u20ac"
    if tariffa.definizione:
        return f"{tariffa.definizione} - {label}"
    return label


def _csv(values):
    return ",".join(str(value) for value in values if value)


def student_ids_for_familiare(familiare):
    if not familiare or not getattr(familiare, "pk", None):
        return []

    direct_ids = list(
        StudenteFamiliare.objects.filter(
            familiare_id=familiare.pk,
            attivo=True,
            studente__attivo=True,
        )
        .order_by("studente__cognome", "studente__nome", "studente_id")
        .values_list("studente_id", flat=True)
    )
    return direct_ids


def familiare_ids_for_studente(studente):
    if not studente or not getattr(studente, "pk", None):
        return []

    direct_ids = list(
        StudenteFamiliare.objects.filter(
            studente_id=studente.pk,
            attivo=True,
            familiare__attivo=True,
            familiare__abilitato_scambio_retta=True,
        )
        .order_by("familiare__cognome", "familiare__nome", "familiare_id")
        .values_list("familiare_id", flat=True)
    )
    return direct_ids


def studenti_queryset_for_familiare(familiare):
    if not familiare:
        return Studente.objects.none()

    student_ids = student_ids_for_familiare(familiare)
    if not student_ids:
        return Studente.objects.none()

    return Studente.objects.filter(pk__in=student_ids, attivo=True).order_by("cognome", "nome", "id")


def has_direct_student_familiare_relation(studente, familiare):
    if not studente or not familiare:
        return False
    return StudenteFamiliare.objects.filter(
        studente=studente,
        familiare=familiare,
        attivo=True,
    ).exists()


class FamiliareScambioRettaSelect(forms.Select):
    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        option = super().create_option(name, value, label, selected, index, subindex=subindex, attrs=attrs)

        if value and hasattr(value, "instance"):
            familiare = value.instance
            option["attrs"]["data-studente-ids"] = _csv(student_ids_for_familiare(familiare))

        return option


class StudenteScambioRettaSelect(forms.Select):
    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        option = super().create_option(name, value, label, selected, index, subindex=subindex, attrs=attrs)

        if value and hasattr(value, "instance"):
            studente = value.instance
            option["attrs"]["data-familiare-ids"] = _csv(familiare_ids_for_studente(studente))

        return option


class TariffaScambioRettaSelect(forms.Select):
    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        option = super().create_option(name, value, label, selected, index, subindex=subindex, attrs=attrs)

        if value and hasattr(value, "instance"):
            tariffa = value.instance
            option["attrs"]["data-valore-orario"] = str(tariffa.valore_orario)

        return option


class TariffaScambioRettaForm(forms.ModelForm):
    class Meta:
        model = TariffaScambioRetta
        fields = ["valore_orario", "definizione", "note"]
        widgets = {
            "note": forms.Textarea(attrs={"rows": 4}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["valore_orario"].help_text = "Valore orario in euro."
        apply_eur_currency_widget(self.fields["valore_orario"])


class ScambioRettaForm(forms.ModelForm):
    class Meta:
        model = ScambioRetta
        fields = [
            "familiare",
            "studente",
            "anno_scolastico",
            "mese_riferimento",
            "descrizione",
            "ore_lavorate",
            "tariffa_scambio_retta",
            "approvata",
            "contabilizzata",
            "note",
        ]
        widgets = {
            "familiare": FamiliareScambioRettaSelect(),
            "studente": StudenteScambioRettaSelect(),
            "tariffa_scambio_retta": TariffaScambioRettaSelect(),
            "descrizione": forms.Textarea(attrs={"rows": 3}),
            "approvata": forms.Select(choices=((False, "No"), (True, "Si"))),
            "contabilizzata": forms.Select(choices=((False, "No"), (True, "Si"))),
            "note": forms.Textarea(attrs={"rows": 4}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["familiare"].queryset = Familiare.objects.filter(attivo=True, abilitato_scambio_retta=True).order_by(
            "cognome", "nome"
        )
        self.fields["studente"].queryset = Studente.objects.filter(attivo=True).order_by("cognome", "nome")
        self.fields["anno_scolastico"].queryset = AnnoScolastico.objects.filter(attivo=True).order_by("-data_inizio", "-id")
        self.fields["tariffa_scambio_retta"].queryset = TariffaScambioRetta.objects.order_by("valore_orario", "definizione")
        self.fields["tariffa_scambio_retta"].label_from_instance = tariffa_scambio_retta_choice_label
        self.fields["mese_riferimento"].widget = forms.Select(choices=MONTH_CHOICES)
        self.fields["anno_scolastico"].empty_label = None
        self.fields["tariffa_scambio_retta"].empty_label = None
        make_searchable_select(self.fields["familiare"], "Cerca un familiare...")

        self.fields["ore_lavorate"].help_text = "Numero ore lavorate per il mese selezionato."
        self.fields["ore_lavorate"].widget.attrs.update(
            {
                "step": "0.25",
                "min": "0",
                "inputmode": "decimal",
            }
        )

        familiare = self._resolve_selected_familiare()
        if self.is_bound:
            self.filter_studenti_by_familiare(familiare)

        if not self.instance.pk and not self.is_bound:
            if not self.initial.get("anno_scolastico"):
                anno_predefinito = resolve_default_anno_scolastico(self.fields["anno_scolastico"].queryset)
                if anno_predefinito:
                    self.initial["anno_scolastico"] = anno_predefinito.pk

            if not self.initial.get("tariffa_scambio_retta"):
                prima_tariffa = self.fields["tariffa_scambio_retta"].queryset.first()
                if prima_tariffa:
                    self.initial["tariffa_scambio_retta"] = prima_tariffa.pk

    def _resolve_selected_familiare(self):
        familiare_pk = None
        if self.is_bound:
            familiare_pk = self.data.get(self.add_prefix("familiare")) or self.data.get("familiare")
        elif self.instance.pk and self.instance.familiare_id:
            familiare_pk = self.instance.familiare_id
        elif self.initial.get("familiare"):
            familiare_pk = self.initial["familiare"]

        if not familiare_pk:
            return self.instance.familiare if self.instance.pk and self.instance.familiare_id else None

        return self.fields["familiare"].queryset.filter(pk=familiare_pk).first()

    def filter_studenti_by_familiare(self, familiare):
        self.fields["studente"].queryset = studenti_queryset_for_familiare(familiare)

    def clean(self):
        cleaned_data = super().clean()
        familiare = cleaned_data.get("familiare")
        studente = cleaned_data.get("studente")

        if familiare and studente and not has_direct_student_familiare_relation(studente, familiare):
            self.add_error("studente", "Seleziona uno studente collegato al familiare indicato.")

        return cleaned_data


class PrestazioneScambioRettaForm(forms.ModelForm):
    ora_ingresso = forms.TypedChoiceField(
        choices=TIME_SLOT_CHOICES,
        required=False,
        coerce=parse_quarter_hour_choice,
        empty_value=None,
    )
    ora_uscita = forms.TypedChoiceField(
        choices=TIME_SLOT_CHOICES,
        required=False,
        coerce=parse_quarter_hour_choice,
        empty_value=None,
    )

    class Meta:
        model = PrestazioneScambioRetta
        fields = [
            "familiare",
            "studente",
            "data",
            "ora_ingresso",
            "ora_uscita",
            "ore_lavorate",
            "tariffa_scambio_retta",
            "descrizione",
            "note",
        ]
        widgets = {
            "familiare": FamiliareScambioRettaSelect(),
            "studente": StudenteScambioRettaSelect(),
            "tariffa_scambio_retta": TariffaScambioRettaSelect(),
            "data": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "descrizione": forms.TextInput(attrs={"maxlength": 255}),
            "note": forms.Textarea(attrs={"rows": 4}),
        }

    def __init__(self, *args, **kwargs):
        familiare_id = kwargs.pop("familiare_id", None)
        super().__init__(*args, **kwargs)

        self.fields["familiare"].queryset = Familiare.objects.filter(attivo=True, abilitato_scambio_retta=True).order_by(
            "cognome", "nome"
        )
        self.fields["studente"].queryset = Studente.objects.filter(attivo=True).order_by("cognome", "nome")
        self.fields["tariffa_scambio_retta"].queryset = TariffaScambioRetta.objects.order_by("valore_orario", "definizione")
        self.fields["tariffa_scambio_retta"].label_from_instance = tariffa_scambio_retta_choice_label
        self.fields["tariffa_scambio_retta"].empty_label = None
        self.fields["studente"].required = False
        self.fields["ore_lavorate"].required = False
        self.fields["ore_lavorate"].help_text = (
            "Se indichi ingresso e uscita viene calcolato automaticamente. "
            "Lascia gli orari vuoti se vuoi inserire il totale manualmente."
        )
        self.fields["ore_lavorate"].widget.attrs.update(
            {
                "step": "0.25",
                "min": "0",
                "inputmode": "decimal",
            }
        )
        self.fields["descrizione"].help_text = "Mansione svolta."
        self.fields["studente"].help_text = "Facoltativo. Se selezionato deve essere collegato al familiare."
        make_searchable_select(self.fields["familiare"], "Cerca un familiare...")
        make_searchable_select(self.fields["studente"], "Cerca uno studente...")

        if not self.is_bound:
            if self.instance.pk:
                if self.instance.ora_ingresso:
                    self.initial["ora_ingresso"] = self.instance.ora_ingresso.strftime("%H:%M")
                if self.instance.ora_uscita:
                    self.initial["ora_uscita"] = self.instance.ora_uscita.strftime("%H:%M")
            elif familiare_id:
                self.initial.setdefault("familiare", familiare_id)

            if not self.initial.get("tariffa_scambio_retta"):
                prima_tariffa = self.fields["tariffa_scambio_retta"].queryset.first()
                if prima_tariffa:
                    self.initial["tariffa_scambio_retta"] = prima_tariffa.pk

        familiare = None
        if self.is_bound:
            familiare_pk = self.data.get("familiare")
            if familiare_pk:
                familiare = self.fields["familiare"].queryset.filter(pk=familiare_pk).first()
        elif self.instance.pk and self.instance.familiare_id:
            familiare = self.instance.familiare if self.instance.familiare_id else None
        elif familiare_id:
            familiare = self.fields["familiare"].queryset.filter(pk=familiare_id).first()

        if familiare:
            self.filter_studenti_by_familiare(familiare)
        elif self.is_bound:
            self.fields["studente"].queryset = Studente.objects.none()

    def filter_studenti_by_familiare(self, familiare):
        if not familiare:
            self.fields["studente"].queryset = Studente.objects.none()
            return
        self.fields["studente"].queryset = studenti_queryset_for_familiare(familiare)
