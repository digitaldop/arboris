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
            "anno_scolastico",
            "attiva",
            "note",
        ]
        widgets = {
            "note": forms.Textarea(attrs={"rows": 4}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["anno_scolastico"].queryset = self.fields["anno_scolastico"].queryset.order_by("-data_inizio", "-id")
        self.fields["anno_scolastico"].empty_label = None

        if not self.instance.pk and not self.is_bound and not self.initial.get("anno_scolastico"):
            anno_predefinito = resolve_default_anno_scolastico(self.fields["anno_scolastico"].queryset)
            if anno_predefinito:
                self.initial["anno_scolastico"] = anno_predefinito.pk


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
        self.fields["classi"].help_text = "Seleziona una o piu classi/livelli che compongono il gruppo operativo."
        self.fields["classi"].label_from_instance = lambda classe: f"{classe} - {classe.anno_scolastico}"

        anno_scolastico_id = self.initial.get("anno_scolastico") or getattr(self.instance, "anno_scolastico_id", None)

        if not self.instance.pk and not self.is_bound and not anno_scolastico_id:
            anno_predefinito = resolve_default_anno_scolastico(self.fields["anno_scolastico"].queryset)
            if anno_predefinito:
                self.initial["anno_scolastico"] = anno_predefinito.pk

        classi_queryset = Classe.objects.select_related("anno_scolastico").order_by(
            "-anno_scolastico__data_inizio",
            "ordine_classe",
            "nome_classe",
            "sezione_classe",
        )
        self.fields["classi"].queryset = classi_queryset

    def clean(self):
        cleaned_data = super().clean()
        anno_scolastico = cleaned_data.get("anno_scolastico")
        classi = cleaned_data.get("classi")

        if not anno_scolastico or not classi:
            return cleaned_data

        classi_fuori_anno = [classe for classe in classi if classe.anno_scolastico_id != anno_scolastico.pk]
        if classi_fuori_anno:
            self.add_error(
                "classi",
                "Tutte le classi incluse nel gruppo devono appartenere allo stesso anno scolastico del gruppo.",
            )

        return cleaned_data
