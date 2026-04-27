from django import forms
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.models import User
from django.forms import inlineformset_factory

from anagrafica.models import Indirizzo
from anagrafica.forms import make_searchable_select
from anagrafica.utils import validate_and_normalize_phone_number
from .models import (
    LivelloPermesso,
    RuoloUtente,
    Scuola,
    ScuolaSocial,
    ScuolaTelefono,
    ScuolaEmail,
    SistemaImpostazioniGenerali,
    SistemaBackupDatabaseConfigurazione,
    SistemaUtentePermessi,
)


class ArborisAuthenticationForm(AuthenticationForm):
    remember_me = forms.BooleanField(
        label="Mantieni accesso",
        required=False,
    )

    username = forms.CharField(
        label="Email o username",
        widget=forms.TextInput(
            attrs={
                "autofocus": True,
                "autocomplete": "username",
                "autocapitalize": "none",
                "placeholder": "Inserisci email o username",
                "spellcheck": "false",
            }
        ),
    )
    password = forms.CharField(
        label="Password",
        strip=False,
        widget=forms.PasswordInput(
            attrs={
                "autocomplete": "current-password",
                "placeholder": "Inserisci la password",
            }
        ),
    )

    error_messages = {
        "invalid_login": "Credenziali non valide. Verifica username e password.",
        "inactive": "Questo account e disattivato.",
    }


class ScuolaForm(forms.ModelForm):
    class Meta:
        model = Scuola
        fields = [
            "nome_scuola",
            "ragione_sociale",
            "indirizzo_sede_legale",
            "indirizzo_operativo_diverso",
            "indirizzo_operativo",
            "codice_fiscale",
            "partita_iva",
            "sito_web",
            "note",
        ]
        widgets = {
            "note": forms.Textarea(attrs={"rows": 4}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        indirizzi_qs = (
            Indirizzo.objects.select_related("citta", "provincia", "regione")
            .order_by("via", "numero_civico")
        )
        self.fields["indirizzo_sede_legale"].queryset = indirizzi_qs
        self.fields["indirizzo_operativo"].queryset = indirizzi_qs
        self.fields["indirizzo_sede_legale"].required = False
        self.fields["indirizzo_operativo"].required = False
        self.fields["indirizzo_sede_legale"].label_from_instance = lambda obj: obj.label_select()
        self.fields["indirizzo_operativo"].label_from_instance = lambda obj: obj.label_select()
        make_searchable_select(self.fields["indirizzo_sede_legale"], "Cerca un indirizzo...")
        make_searchable_select(self.fields["indirizzo_operativo"], "Cerca un indirizzo...")

    def clean(self):
        cleaned_data = super().clean()
        if not cleaned_data.get("indirizzo_operativo_diverso"):
            cleaned_data["indirizzo_operativo"] = None
        return cleaned_data


class ScuolaSocialForm(forms.ModelForm):
    class Meta:
        model = ScuolaSocial
        fields = ["nome_social", "link", "ordine"]
        widgets = {"link": forms.URLInput()}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["ordine"].required = False


ScuolaSocialFormSet = inlineformset_factory(
    Scuola,
    ScuolaSocial,
    form=ScuolaSocialForm,
    extra=1,
    can_delete=True,
)


class ScuolaTelefonoForm(forms.ModelForm):
    class Meta:
        model = ScuolaTelefono
        fields = ["descrizione", "telefono", "ordine"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["ordine"].required = False

    def clean_telefono(self):
        return validate_and_normalize_phone_number(self.cleaned_data.get("telefono"))


ScuolaTelefonoFormSet = inlineformset_factory(
    Scuola,
    ScuolaTelefono,
    form=ScuolaTelefonoForm,
    extra=1,
    can_delete=True,
)


class ScuolaEmailForm(forms.ModelForm):
    class Meta:
        model = ScuolaEmail
        fields = ["descrizione", "email", "ordine"]
        widgets = {"email": forms.EmailInput()}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["ordine"].required = False


ScuolaEmailFormSet = inlineformset_factory(
    Scuola,
    ScuolaEmail,
    form=ScuolaEmailForm,
    extra=1,
    can_delete=True,
)


class SistemaImpostazioniGeneraliForm(forms.ModelForm):
    class Meta:
        model = SistemaImpostazioniGenerali
        fields = [
            "terminologia_studente",
            "mostra_dashboard_prossimo_anno_scolastico",
            "osservazioni_solo_autori_visualizzazione",
            "osservazioni_solo_autori_modifica",
            "formato_visualizzazione_telefono",
            "font_principale",
            "font_titoli",
        ]
        labels = {
            "terminologia_studente": "Dicitura visualizzata per gli studenti",
            "mostra_dashboard_prossimo_anno_scolastico": "Mostra in Dashboard i riepiloghi del prossimo anno scolastico",
            "osservazioni_solo_autori_visualizzazione": "Solo gli autori possono vedere le loro osservazioni",
            "osservazioni_solo_autori_modifica": "Solo gli autori possono modificare o cancellare",
            "formato_visualizzazione_telefono": "Formato numeri di telefono (solo visualizzazione)",
            "font_principale": "Font principale",
            "font_titoli": "Titoli",
        }


class SistemaBackupDatabaseConfigurazioneForm(forms.ModelForm):
    class Meta:
        model = SistemaBackupDatabaseConfigurazione
        fields = ["frequenza_backup_automatico"]
        labels = {
            "frequenza_backup_automatico": "Backup automatici",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["frequenza_backup_automatico"].help_text = (
            "Scegli la cadenza dei backup automatici. Arboris li esegue al primo accesso utile "
            "dopo la scadenza configurata ed espone anche un comando server dedicato per la schedulazione."
        )


class SistemaBackupDatabaseUploadForm(forms.Form):
    file_backup = forms.FileField(
        label="File di backup",
        help_text=(
            "File .sql o .sql.gz (pg_dump) generato da Arboris o da PostgreSQL. "
            "Il file viene caricato nello storage configurato; il ripristino parte dopo la conferma e viene eseguito in background."
        ),
    )

    def clean_file_backup(self):
        uploaded_file = self.cleaned_data["file_backup"]
        lower_name = uploaded_file.name.lower()
        if not (lower_name.endswith(".sql") or lower_name.endswith(".sql.gz")):
            raise forms.ValidationError("Carica un file di backup PostgreSQL in formato .sql o .sql.gz.")
        return uploaded_file


class SistemaBackupDatabaseRestoreConfirmForm(forms.Form):
    testo_conferma = forms.CharField(
        label="Conferma operazione",
        help_text='Digita esattamente RIPRISTINA DATABASE per procedere.',
    )
    conferma_sostituzione = forms.BooleanField(
        label="Confermo che il database corrente verra sostituito integralmente.",
        required=True,
    )

    def clean_testo_conferma(self):
        value = (self.cleaned_data.get("testo_conferma") or "").strip().upper()
        if value != "RIPRISTINA DATABASE":
            raise forms.ValidationError("Per sicurezza devi digitare esattamente RIPRISTINA DATABASE.")
        return value


class SistemaUtenteForm(forms.ModelForm):
    email = forms.EmailField(label="Email")
    ruolo = forms.ChoiceField(
        label="Ruolo",
        required=False,
        choices=[("", "---------"), *RuoloUtente.choices],
        help_text="Definisce il ruolo della persona che possiede l'account.",
    )
    password = forms.CharField(
        label="Password",
        widget=forms.PasswordInput(render_value=False),
        required=False,
        help_text="Obbligatoria in creazione. In modifica, lascia vuoto per non cambiarla.",
    )
    controllo_completo = forms.BooleanField(
        label="Controllo completo",
        required=False,
        help_text="Concede pieno accesso applicativo senza rendere l'utente superuser Django.",
    )
    permesso_anagrafica = forms.ChoiceField(
        label="Modulo anagrafica",
        choices=LivelloPermesso.choices,
        initial=LivelloPermesso.NESSUNO,
    )
    permesso_economia = forms.ChoiceField(
        label="Modulo economia",
        choices=LivelloPermesso.choices,
        initial=LivelloPermesso.NESSUNO,
    )
    permesso_sistema = forms.ChoiceField(
        label="Modulo sistema",
        choices=LivelloPermesso.choices,
        initial=LivelloPermesso.NESSUNO,
    )
    permesso_calendario = forms.ChoiceField(
        label="Modulo calendario",
        choices=LivelloPermesso.choices,
        initial=LivelloPermesso.NESSUNO,
    )
    permesso_gestione_finanziaria = forms.ChoiceField(
        label="Modulo gestione finanziaria",
        choices=LivelloPermesso.choices,
        initial=LivelloPermesso.NESSUNO,
    )
    permesso_gestione_amministrativa = forms.ChoiceField(
        label="Modulo gestione amministrativa",
        choices=LivelloPermesso.choices,
        initial=LivelloPermesso.NESSUNO,
    )
    permesso_servizi_extra = forms.ChoiceField(
        label="Modulo servizi extra",
        choices=LivelloPermesso.choices,
        initial=LivelloPermesso.NESSUNO,
    )

    class Meta:
        model = User
        fields = ["first_name", "last_name", "email", "password"]
        labels = {
            "first_name": "Nome",
            "last_name": "Cognome",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["first_name"].required = True
        self.fields["last_name"].required = True
        self.fields["email"].required = True

        if self.instance and self.instance.pk:
            self.fields["email"].initial = self.instance.email or self.instance.username
            profilo = getattr(self.instance, "profilo_permessi", None)
            if profilo:
                self.fields["ruolo"].initial = profilo.ruolo
                self.fields["controllo_completo"].initial = profilo.controllo_completo
                self.fields["permesso_anagrafica"].initial = profilo.permesso_anagrafica
                self.fields["permesso_economia"].initial = profilo.permesso_economia
                self.fields["permesso_sistema"].initial = profilo.permesso_sistema
                self.fields["permesso_calendario"].initial = profilo.permesso_calendario
                self.fields["permesso_gestione_finanziaria"].initial = profilo.permesso_gestione_finanziaria
                self.fields["permesso_gestione_amministrativa"].initial = profilo.permesso_gestione_amministrativa
                self.fields["permesso_servizi_extra"].initial = profilo.permesso_servizi_extra
        else:
            self.fields["password"].required = True

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()

        existing_username = User.objects.filter(username__iexact=email)
        existing_email = User.objects.filter(email__iexact=email)
        if self.instance and self.instance.pk:
            existing_username = existing_username.exclude(pk=self.instance.pk)
            existing_email = existing_email.exclude(pk=self.instance.pk)

        if existing_username.exists() or existing_email.exists():
            raise forms.ValidationError("Esiste giÃ  un utente con questa email.")

        return email

    def clean_password(self):
        password = self.cleaned_data.get("password", "")
        if not self.instance.pk and not password:
            raise forms.ValidationError("La password Ã¨ obbligatoria.")
        return password

    def save(self, commit=True):
        user = super().save(commit=False)
        email = self.cleaned_data["email"]

        user.email = email
        user.username = email

        password = self.cleaned_data.get("password")
        if password:
            user.set_password(password)

        if commit:
            user.save()
            SistemaUtentePermessi.objects.update_or_create(
                user=user,
                defaults={
                    "ruolo": self.cleaned_data["ruolo"],
                    "controllo_completo": self.cleaned_data["controllo_completo"],
                    "permesso_anagrafica": self.cleaned_data["permesso_anagrafica"],
                    "permesso_economia": self.cleaned_data["permesso_economia"],
                    "permesso_sistema": self.cleaned_data["permesso_sistema"],
                    "permesso_calendario": self.cleaned_data["permesso_calendario"],
                    "permesso_gestione_finanziaria": self.cleaned_data["permesso_gestione_finanziaria"],
                    "permesso_gestione_amministrativa": self.cleaned_data["permesso_gestione_amministrativa"],
                    "permesso_servizi_extra": self.cleaned_data["permesso_servizi_extra"],
                },
            )

        return user
