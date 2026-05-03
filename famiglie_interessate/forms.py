from django import forms
from django.contrib.auth.models import User
from django.forms import inlineformset_factory

from scuola.models import AnnoScolastico, Classe

from .models import (
    AttivitaFamigliaInteressata,
    FamigliaInteressata,
    MinoreInteressato,
    ReferenteFamigliaInteressata,
    StatoAttivitaFamigliaInteressata,
)


DATE_INPUT_FORMATS = ("%Y-%m-%d", "%d/%m/%Y")
DATETIME_INPUT_FORMATS = ("%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M", "%d/%m/%Y %H:%M")


class FamigliaInteressataForm(forms.ModelForm):
    class Meta:
        model = FamigliaInteressata
        fields = [
            "nome",
            "referente_principale",
            "telefono",
            "email",
            "fonte_contatto",
            "fonte_note",
            "stato",
            "priorita",
            "anno_scolastico_interesse",
            "classe_eta_interesse",
            "privacy_consenso",
            "note",
        ]
        labels = {
            "nome": "Nome famiglia / riferimento",
            "referente_principale": "Referente principale",
            "telefono": "Telefono",
            "email": "Email",
            "fonte_contatto": "Fonte contatto",
            "fonte_note": "Dettaglio fonte",
            "stato": "Stato",
            "priorita": "Priorita",
            "anno_scolastico_interesse": "Anno scolastico di interesse",
            "classe_eta_interesse": "Classe / fascia di interesse",
            "privacy_consenso": "Consenso privacy raccolto",
            "note": "Note interne",
        }
        widgets = {
            "note": forms.Textarea(attrs={"rows": 5}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["anno_scolastico_interesse"].queryset = AnnoScolastico.objects.order_by("-data_inizio", "-id")
        self.fields["anno_scolastico_interesse"].required = False
        placeholders = {
            "nome": "Es. Rossi - famiglia",
            "referente_principale": "Nome e cognome",
            "telefono": "Es. 333 1234567",
            "email": "esempio@email.com",
            "fonte_note": "Es. Open day, sito web, passaparola...",
            "classe_eta_interesse": "Es. Scuola primaria, fascia 3-6 anni...",
            "note": "Scrivi eventuali note utili...",
        }
        for field in self.fields.values():
            css_class = field.widget.attrs.get("class", "")
            field.widget.attrs["class"] = f"{css_class} interested-input".strip()
        for field_name, placeholder in placeholders.items():
            self.fields[field_name].widget.attrs.setdefault("placeholder", placeholder)

    def clean(self):
        cleaned_data = super().clean()
        has_main_contact = any(
            (cleaned_data.get(field_name) or "").strip()
            for field_name in ("nome", "referente_principale", "telefono", "email")
        )
        if not has_main_contact:
            raise forms.ValidationError(
                "Inserisci almeno un riferimento tra nome, referente, telefono o email."
            )
        return cleaned_data


class ReferenteFamigliaInteressataForm(forms.ModelForm):
    class Meta:
        model = ReferenteFamigliaInteressata
        fields = ["nome", "relazione", "telefono", "email", "principale", "note"]
        labels = {
            "nome": "Nome",
            "relazione": "Relazione",
            "telefono": "Telefono",
            "email": "Email",
            "principale": "Principale",
            "note": "Note",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["nome"].required = False
        placeholders = {
            "nome": "Nome e cognome",
            "relazione": "Es. Madre, padre, tutore",
            "telefono": "Es. 333 1234567",
            "email": "esempio@email.com",
            "note": "Note aggiuntive sul referente...",
        }
        for field_name, placeholder in placeholders.items():
            self.fields[field_name].widget.attrs.setdefault("placeholder", placeholder)


class MinoreInteressatoForm(forms.ModelForm):
    data_nascita = forms.DateField(
        required=False,
        input_formats=DATE_INPUT_FORMATS,
        widget=forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"}),
        label="Data nascita",
    )

    class Meta:
        model = MinoreInteressato
        fields = ["nome", "cognome", "data_nascita", "eta_indicativa", "classe_interesse", "note"]
        labels = {
            "nome": "Nome",
            "cognome": "Cognome",
            "eta_indicativa": "Eta indicativa",
            "classe_interesse": "Classe di interesse",
            "note": "Note",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["classe_interesse"].queryset = Classe.objects.order_by(
            "ordine_classe",
            "nome_classe",
            "sezione_classe",
            "id",
        )
        self.fields["classe_interesse"].required = False
        self.fields["classe_interesse"].empty_label = "Seleziona classe"
        placeholders = {
            "nome": "Nome",
            "cognome": "Cognome",
            "eta_indicativa": "Es. 6 anni",
            "note": "Note aggiuntive",
        }
        for field_name, placeholder in placeholders.items():
            self.fields[field_name].widget.attrs.setdefault("placeholder", placeholder)

    def save(self, commit=True):
        instance = super().save(commit=False)
        if instance.classe_interesse_id:
            instance.classe_eta_interesse = str(instance.classe_interesse)
        elif "classe_interesse" in self.changed_data:
            instance.classe_eta_interesse = ""
        if commit:
            instance.save()
            self.save_m2m()
        return instance


ReferenteFamigliaInteressataFormSet = inlineformset_factory(
    FamigliaInteressata,
    ReferenteFamigliaInteressata,
    form=ReferenteFamigliaInteressataForm,
    extra=1,
    can_delete=True,
)


MinoreInteressatoFormSet = inlineformset_factory(
    FamigliaInteressata,
    MinoreInteressato,
    form=MinoreInteressatoForm,
    extra=1,
    can_delete=True,
)


class AttivitaFamigliaInteressataForm(forms.ModelForm):
    data_programmata = forms.DateTimeField(
        required=False,
        input_formats=DATETIME_INPUT_FORMATS,
        widget=forms.DateTimeInput(format="%Y-%m-%dT%H:%M", attrs={"type": "datetime-local"}),
        label="Data e ora programmata",
    )
    data_svolgimento = forms.DateTimeField(
        required=False,
        input_formats=DATETIME_INPUT_FORMATS,
        widget=forms.DateTimeInput(format="%Y-%m-%dT%H:%M", attrs={"type": "datetime-local"}),
        label="Data svolgimento",
    )

    class Meta:
        model = AttivitaFamigliaInteressata
        fields = [
            "tipo",
            "titolo",
            "stato",
            "data_programmata",
            "durata_minuti",
            "calendarizza",
            "data_svolgimento",
            "luogo",
            "assegnata_a",
            "descrizione",
            "esito",
        ]
        labels = {
            "tipo": "Tipologia",
            "titolo": "Titolo",
            "stato": "Stato",
            "durata_minuti": "Durata minuti",
            "calendarizza": "Mostra nel calendario",
            "luogo": "Luogo",
            "assegnata_a": "Assegnata a",
            "descrizione": "Descrizione",
            "esito": "Esito",
        }
        widgets = {
            "descrizione": forms.Textarea(attrs={"rows": 4}),
            "esito": forms.Textarea(attrs={"rows": 4}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["assegnata_a"].queryset = User.objects.filter(is_active=True).order_by(
            "last_name",
            "first_name",
            "email",
        )
        self.fields["assegnata_a"].required = False
        self.fields["durata_minuti"].widget.attrs.update({"min": "5", "step": "5"})

    def clean(self):
        cleaned_data = super().clean()
        stato = cleaned_data.get("stato")
        data_programmata = cleaned_data.get("data_programmata")
        calendarizza = cleaned_data.get("calendarizza")
        if calendarizza and not data_programmata:
            raise forms.ValidationError("Per mostrare l'attivita in calendario serve una data programmata.")
        if stato == StatoAttivitaFamigliaInteressata.COMPLETATA and not cleaned_data.get("data_svolgimento"):
            cleaned_data["data_svolgimento"] = data_programmata
        return cleaned_data
