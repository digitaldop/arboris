from django import forms

from .models import AnnoScolastico, Classe, GruppoClasse
from .utils import resolve_default_anno_scolastico


class DateInput(forms.DateInput):
    input_type = "date"


class AnnoScolasticoForm(forms.ModelForm):
    class Meta:
        model = AnnoScolastico
        fields = [
            "nome_anno_scolastico",
            "data_inizio",
            "data_fine",
            "attivo",
            "note",
        ]
        widgets = {
            "data_inizio": DateInput(),
            "data_fine": DateInput(),
            "note": forms.Textarea(attrs={"rows": 4}),
        }


class ClasseForm(forms.ModelForm):
    class Meta:
        model = Classe
        fields = [
            "nome_classe",
            "sezione_classe",
            "ordine_classe",
            "attiva",
            "note",
        ]
        labels = {
            "sezione_classe": "Sezione",
        }
        widgets = {
            "note": forms.Textarea(attrs={"rows": 4}),
        }


class GruppoClasseForm(forms.ModelForm):
    class Meta:
        model = GruppoClasse
        fields = [
            "nome_gruppo_classe",
            "anno_scolastico",
            "classi",
            "attivo",
            "note",
        ]
        widgets = {
            "classi": forms.SelectMultiple(attrs={"size": 8}),
            "note": forms.Textarea(attrs={"rows": 4}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["anno_scolastico"].queryset = self.fields["anno_scolastico"].queryset.order_by("-data_inizio", "-id")
        self.fields["anno_scolastico"].empty_label = None
        self.fields["nome_gruppo_classe"].label = "Nome Pluriclasse"
        self.fields["classi"].help_text = (
            "Seleziona le classi standard che compongono questa Pluriclasse per l'anno scolastico indicato. "
            "Se non esiste una Pluriclasse, lo studente resta assegnato solo alla sua Classe."
        )

        anno_scolastico_id = self.initial.get("anno_scolastico") or getattr(self.instance, "anno_scolastico_id", None)

        if not self.instance.pk and not self.is_bound and not anno_scolastico_id:
            anno_predefinito = resolve_default_anno_scolastico(self.fields["anno_scolastico"].queryset)
            if anno_predefinito:
                self.initial["anno_scolastico"] = anno_predefinito.pk

        classi_queryset = Classe.objects.order_by(
            "ordine_classe",
            "nome_classe",
            "sezione_classe",
        )
        self.fields["classi"].queryset = classi_queryset

    def clean(self):
        cleaned_data = super().clean()
        classi = cleaned_data.get("classi")

        if classi and classi.count() < 2:
            self.add_error(
                "classi",
                "Una Pluriclasse dovrebbe includere almeno due classi standard.",
            )

        return cleaned_data
