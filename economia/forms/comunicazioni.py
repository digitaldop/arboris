from django import forms

from scuola.models import AnnoScolastico


class ComunicazioneFamiglieForm(forms.Form):
    ambito_destinatari = forms.ChoiceField(
        label="Destinatari per classe",
        choices=(("tutti", "Tutte le classi"), ("classi", "Classi selezionate")),
        initial="tutti", required=False, widget=forms.RadioSelect,
    )
    classi = forms.MultipleChoiceField(
        label="Classi e pluriclassi", choices=(), required=False,
        widget=forms.CheckboxSelectMultiple,
    )
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

    def clean(self):
        cleaned = super().clean()
        cleaned["ambito_destinatari"] = cleaned.get("ambito_destinatari") or "tutti"
        if cleaned["ambito_destinatari"] == "classi" and not cleaned.get("classi"):
            self.add_error("classi", "Seleziona almeno una classe oppure scegli Tutte le classi.")
        return cleaned
