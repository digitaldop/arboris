from django import forms

from .models import OsservazioneStudente


class OsservazioneStudenteForm(forms.ModelForm):
    class Meta:
        model = OsservazioneStudente
        fields = ["titolo", "data_inserimento", "testo"]
        widgets = {
            "data_inserimento": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "testo": forms.Textarea(attrs={"rows": 8, "data-rich-notes": "1"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["titolo"].required = False
        self.fields["titolo"].widget.attrs.setdefault("placeholder", "Titolo facoltativo")
        self.fields["testo"].widget.attrs.setdefault("placeholder", "Inserisci l'osservazione...")
