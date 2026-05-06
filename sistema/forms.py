from django import forms
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.models import User
from django.db.models import Q
from django.forms import inlineformset_factory

from anagrafica.models import Indirizzo
from anagrafica.forms import make_searchable_select
from anagrafica.utils import validate_and_normalize_phone_number
from .models import (
    FeedbackSegnalazione,
    Scuola,
    ScuolaSocial,
    ScuolaTelefono,
    ScuolaEmail,
    SistemaImpostazioniGenerali,
    SistemaBackupDatabaseConfigurazione,
    SistemaRuoloPermessi,
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
            "cronologia_retention_mesi",
            "gestione_iscrizione_corso_anno",
            "giorno_soglia_iscrizione_corso_anno",
            "modulo_anagrafica_attivo",
            "modulo_famiglie_interessate_attivo",
            "modulo_economia_attivo",
            "modulo_calendario_attivo",
            "modulo_gestione_finanziaria_attivo",
            "modulo_gestione_amministrativa_attivo",
            "modulo_servizi_extra_attivo",
            "font_principale",
            "font_titoli",
        ]
        labels = {
            "terminologia_studente": "Dicitura visualizzata per gli studenti",
            "mostra_dashboard_prossimo_anno_scolastico": "Mostra in Dashboard i riepiloghi del prossimo anno scolastico",
            "osservazioni_solo_autori_visualizzazione": "Solo gli autori possono vedere le loro osservazioni",
            "osservazioni_solo_autori_modifica": "Solo gli autori possono modificare o cancellare",
            "formato_visualizzazione_telefono": "Formato numeri di telefono (solo visualizzazione)",
            "cronologia_retention_mesi": "Conserva cronologia operazioni per",
            "gestione_iscrizione_corso_anno": "Iscrizioni in corso d'anno",
            "giorno_soglia_iscrizione_corso_anno": "Giorno soglia",
            "modulo_anagrafica_attivo": "Anagrafica",
            "modulo_famiglie_interessate_attivo": "Famiglie interessate",
            "modulo_economia_attivo": "Economia",
            "modulo_calendario_attivo": "Calendario",
            "modulo_gestione_finanziaria_attivo": "Gestione finanziaria",
            "modulo_gestione_amministrativa_attivo": "Dipendenti e collaboratori",
            "modulo_servizi_extra_attivo": "Servizi extra",
            "font_principale": "Font principale",
            "font_titoli": "Titoli",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["giorno_soglia_iscrizione_corso_anno"].widget.attrs.update(
            {
                "min": "1",
                "max": "31",
                "inputmode": "numeric",
            }
        )
        for field in self.fields.values():
            if isinstance(field.widget, forms.CheckboxInput):
                current_class = field.widget.attrs.get("class", "")
                field.widget.attrs["class"] = f"{current_class} settings-switch-checkbox".strip()


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


class FeedbackSegnalazioneForm(forms.ModelForm):
    class Meta:
        model = FeedbackSegnalazione
        fields = [
            "tipo",
            "messaggio",
            "pagina_url",
            "pagina_path",
            "pagina_titolo",
            "breadcrumb",
        ]
        widgets = {
            "messaggio": forms.Textarea(
                attrs={
                    "rows": 5,
                    "maxlength": "4000",
                    "placeholder": "Scrivi qui cosa hai notato o cosa ti piacerebbe aggiungere...",
                }
            ),
            "pagina_url": forms.HiddenInput(),
            "pagina_path": forms.HiddenInput(),
            "pagina_titolo": forms.HiddenInput(),
            "breadcrumb": forms.HiddenInput(),
        }
        labels = {
            "messaggio": "Messaggio",
        }

    def clean_messaggio(self):
        messaggio = (self.cleaned_data.get("messaggio") or "").strip()
        if not messaggio:
            raise forms.ValidationError("Scrivi un messaggio prima di inviare.")
        return messaggio


class SistemaRuoloPermessiForm(forms.ModelForm):
    class Meta:
        model = SistemaRuoloPermessi
        fields = [
            "nome",
            "descrizione",
            "colore_principale",
            "attivo",
            "amministratore_operativo",
            "accesso_backup_database",
            "controllo_completo",
            "permesso_anagrafica",
            "permesso_famiglie_interessate",
            "permesso_economia",
            "permesso_sistema",
            "permesso_calendario",
            "permesso_gestione_finanziaria",
            "permesso_gestione_amministrativa",
            "permesso_servizi_extra",
        ]
        labels = {
            "nome": "Nome ruolo",
            "descrizione": "Descrizione",
            "colore_principale": "Colore principale",
            "attivo": "Ruolo attivo",
            "amministratore_operativo": "Amministratore operativo",
            "accesso_backup_database": "Accesso Backup Database",
            "controllo_completo": "Controllo completo",
            "permesso_anagrafica": "Modulo anagrafica",
            "permesso_famiglie_interessate": "Modulo famiglie interessate",
            "permesso_economia": "Modulo economia",
            "permesso_sistema": "Modulo sistema",
            "permesso_calendario": "Modulo calendario",
            "permesso_gestione_finanziaria": "Modulo gestione finanziaria",
            "permesso_gestione_amministrativa": "Modulo dipendenti e collaboratori",
            "permesso_servizi_extra": "Modulo servizi extra",
        }
        widgets = {
            "descrizione": forms.Textarea(attrs={"rows": 3}),
            "colore_principale": forms.TextInput(attrs={"type": "color"}),
        }
        help_texts = {
            "colore_principale": "Il colore personalizza header, label delle tabelle e tinte della sidebar per gli utenti con questo ruolo.",
            "controllo_completo": "Concede pieno accesso applicativo senza rendere l'utente superuser Django.",
        }


class SistemaUtenteForm(forms.ModelForm):
    email = forms.EmailField(label="Email")
    ruolo_permessi = forms.ModelChoiceField(
        label="Ruolo",
        queryset=SistemaRuoloPermessi.objects.none(),
        empty_label="---------",
        required=True,
        help_text="I permessi dell'account vengono ereditati dal ruolo selezionato.",
    )
    password = forms.CharField(
        label="Password",
        widget=forms.PasswordInput(render_value=False),
        required=False,
        help_text="Obbligatoria in creazione. In modifica, lascia vuoto per non cambiarla.",
    )

    class Meta:
        model = User
        fields = ["first_name", "last_name", "email", "is_active", "password"]
        labels = {
            "first_name": "Nome",
            "last_name": "Cognome",
            "is_active": "Utente attivo",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["first_name"].required = True
        self.fields["last_name"].required = True
        self.fields["email"].required = True
        self.fields["is_active"].required = False
        role_queryset = SistemaRuoloPermessi.objects.filter(attivo=True).order_by("nome")

        if self.instance and self.instance.pk:
            self.fields["email"].initial = self.instance.email or self.instance.username
            profilo = getattr(self.instance, "profilo_permessi", None)
            if profilo:
                if profilo.ruolo_permessi_id:
                    role_queryset = SistemaRuoloPermessi.objects.filter(
                        Q(attivo=True) | Q(pk=profilo.ruolo_permessi_id)
                    ).order_by("nome")
                self.fields["ruolo_permessi"].initial = profilo.ruolo_permessi
        else:
            self.fields["password"].required = True
            self.fields["is_active"].initial = True
        self.fields["ruolo_permessi"].queryset = role_queryset

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()

        existing_username = User.objects.filter(username__iexact=email)
        existing_email = User.objects.filter(email__iexact=email)
        if self.instance and self.instance.pk:
            existing_username = existing_username.exclude(pk=self.instance.pk)
            existing_email = existing_email.exclude(pk=self.instance.pk)

        if existing_username.exists() or existing_email.exists():
            raise forms.ValidationError("Esiste gia un utente con questa email.")

        return email

    def clean_password(self):
        password = self.cleaned_data.get("password", "")
        if not self.instance.pk and not password:
            raise forms.ValidationError("La password e obbligatoria.")
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
            ruolo_permessi = self.cleaned_data["ruolo_permessi"]
            SistemaUtentePermessi.objects.update_or_create(
                user=user,
                defaults={
                    "ruolo_permessi": ruolo_permessi,
                    "ruolo": ruolo_permessi.chiave_legacy or "",
                    "controllo_completo": ruolo_permessi.controllo_completo,
                    "permesso_anagrafica": ruolo_permessi.permesso_anagrafica,
                    "permesso_famiglie_interessate": ruolo_permessi.permesso_famiglie_interessate,
                    "permesso_economia": ruolo_permessi.permesso_economia,
                    "permesso_sistema": ruolo_permessi.permesso_sistema,
                    "permesso_calendario": ruolo_permessi.permesso_calendario,
                    "permesso_gestione_finanziaria": ruolo_permessi.permesso_gestione_finanziaria,
                    "permesso_gestione_amministrativa": ruolo_permessi.permesso_gestione_amministrativa,
                    "permesso_servizi_extra": ruolo_permessi.permesso_servizi_extra,
                },
            )

        return user
