from datetime import datetime, time

from django import forms

from anagrafica.models import Famiglia, Familiare, Studente
from anagrafica.forms import make_searchable_select
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


class FamiliareScambioRettaSelect(forms.Select):
    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        option = super().create_option(name, value, label, selected, index, subindex=subindex, attrs=attrs)

        if value and hasattr(value, "instance"):
            familiare = value.instance
            option["attrs"]["data-famiglia-id"] = familiare.famiglia_id
            option["attrs"]["data-famiglia-label"] = str(familiare.famiglia)

        return option


class StudenteScambioRettaSelect(forms.Select):
    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        option = super().create_option(name, value, label, selected, index, subindex=subindex, attrs=attrs)

        if value and hasattr(value, "instance"):
            studente = value.instance
            option["attrs"]["data-famiglia-id"] = studente.famiglia_id

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
        self.fields["valore_orario"].widget.attrs.update(
            {
                "step": "0.01",
                "min": "0",
                "inputmode": "decimal",
                "data-currency": "EUR",
            }
        )


class ScambioRettaForm(forms.ModelForm):
    class Meta:
        model = ScambioRetta
        fields = [
            "familiare",
            "famiglia",
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
            "note": forms.Textarea(attrs={"rows": 4}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["familiare"].queryset = Familiare.objects.filter(attivo=True, abilitato_scambio_retta=True).order_by(
            "cognome", "nome"
        )
        self.fields["famiglia"].queryset = Famiglia.objects.filter(attiva=True).order_by("cognome_famiglia")
        self.fields["studente"].queryset = Studente.objects.filter(attivo=True).order_by("cognome", "nome")
        self.fields["anno_scolastico"].queryset = AnnoScolastico.objects.filter(attivo=True).order_by("-data_inizio", "-id")
        self.fields["tariffa_scambio_retta"].queryset = TariffaScambioRetta.objects.order_by("valore_orario", "definizione")
        self.fields["mese_riferimento"].widget = forms.Select(choices=MONTH_CHOICES)
        self.fields["anno_scolastico"].empty_label = None
        self.fields["tariffa_scambio_retta"].empty_label = None
        make_searchable_select(self.fields["famiglia"], "Cerca una famiglia...")

        self.fields["ore_lavorate"].help_text = "Numero ore lavorate per il mese selezionato."
        self.fields["ore_lavorate"].widget.attrs.update(
            {
                "step": "0.25",
                "min": "0",
                "inputmode": "decimal",
            }
        )

        self.fields["famiglia"].help_text = "Viene proposta automaticamente quando selezioni il familiare."

        if not self.instance.pk and not self.is_bound:
            if not self.initial.get("anno_scolastico"):
                anno_predefinito = resolve_default_anno_scolastico(self.fields["anno_scolastico"].queryset)
                if anno_predefinito:
                    self.initial["anno_scolastico"] = anno_predefinito.pk

            if not self.initial.get("tariffa_scambio_retta"):
                prima_tariffa = self.fields["tariffa_scambio_retta"].queryset.first()
                if prima_tariffa:
                    self.initial["tariffa_scambio_retta"] = prima_tariffa.pk


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
        self.fields["studente"].help_text = "Facoltativo. Se selezionato deve appartenere alla stessa famiglia del familiare."
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

        famiglia_id = None
        if self.is_bound:
            familiare_pk = self.data.get("familiare")
            if familiare_pk:
                famiglia_id = (
                    self.fields["familiare"].queryset.filter(pk=familiare_pk).values_list("famiglia_id", flat=True).first()
                )
        elif self.instance.pk and self.instance.famiglia_id:
            famiglia_id = self.instance.famiglia_id
        elif familiare_id:
            familiare = self.fields["familiare"].queryset.filter(pk=familiare_id).select_related("famiglia").first()
            famiglia_id = familiare.famiglia_id if familiare else None

        self.filter_studenti_by_famiglia(famiglia_id)

    def filter_studenti_by_famiglia(self, famiglia_id):
        queryset = Studente.objects.filter(attivo=True).order_by("cognome", "nome")
        if famiglia_id:
            queryset = queryset.filter(famiglia_id=famiglia_id)
        self.fields["studente"].queryset = queryset
