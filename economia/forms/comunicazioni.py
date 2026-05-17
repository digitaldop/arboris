from django import forms

from scuola.models import AnnoScolastico


class ComunicazioneFamiglieForm(forms.Form):
    anni_scolastici = forms.ModelMultipleChoiceField(
        label="Anni scolastici",
        queryset=AnnoScolastico.objects.none(),
        widget=forms.CheckboxSelectMultiple,
        required=True,
    )
    oggetto = forms.CharField(
        label="Oggetto",
        max_length=255,
        required=False,
        widget=forms.TextInput(attrs={"placeholder": "Oggetto dell'email"}),
    )
    messaggio = forms.CharField(
        label="Messaggio",
        required=False,
        widget=forms.Textarea(attrs={"rows": 9, "placeholder": "Scrivi il testo della comunicazione..."}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["anni_scolastici"].queryset = AnnoScolastico.objects.filter(attivo=True).order_by(
            "-data_inizio",
            "-id",
        )
