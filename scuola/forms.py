from django import forms

from .models import AnnoScolastico, Classe


class DateInput(forms.DateInput):
    input_type = "date"


class AnnoScolasticoForm(forms.ModelForm):
    class Meta:
        model = AnnoScolastico
        fields = [
            "nome_anno_scolastico",
            "data_inizio",
            "data_fine",
            "corrente",
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
            primo_anno = self.fields["anno_scolastico"].queryset.first()
            if primo_anno:
                self.initial["anno_scolastico"] = primo_anno.pk
