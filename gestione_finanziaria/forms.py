from __future__ import annotations

from decimal import Decimal
from typing import Optional

from django import forms
from django.forms import inlineformset_factory

from arboris.form_widgets import apply_eur_currency_widget

from .models import (
    CategoriaSpesa,
    CategoriaFinanziaria,
    ConnessioneBancaria,
    ContoBancario,
    DocumentoFornitore,
    Fornitore,
    MovimentoFinanziario,
    PianificazioneSincronizzazione,
    ProviderBancario,
    RegolaCategorizzazione,
    ScadenzaPagamentoFornitore,
    StatoScadenzaFornitore,
)


# =========================================================================
#  Categorie finanziarie
# =========================================================================


MESE_COMPETENZA_CHOICES = [
    ("", "---------"),
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


def make_searchable_select(field, placeholder):
    field.widget.attrs.update(
        {
            "data-searchable-select": "1",
            "data-searchable-placeholder": placeholder,
        }
    )


class CategoriaFinanziariaForm(forms.ModelForm):
    class Meta:
        model = CategoriaFinanziaria
        fields = [
            "nome",
            "tipo",
            "parent",
            "colore",
            "icona",
            "ordine",
            "attiva",
            "note",
        ]
        labels = {
            "nome": "Nome categoria",
            "tipo": "Tipo",
            "parent": "Categoria padre",
            "colore": "Colore",
            "icona": "Icona",
            "ordine": "Ordine",
            "attiva": "Attiva",
            "note": "Note",
        }
        widgets = {
            "note": forms.Textarea(attrs={"rows": 3}),
            "colore": forms.TextInput(attrs={"placeholder": "#336699"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["parent"].required = False
        self.fields["colore"].required = False
        self.fields["icona"].required = False
        self.fields["ordine"].required = False
        self.fields["note"].required = False

        queryset = CategoriaFinanziaria.objects.all().order_by("nome")
        if self.instance and self.instance.pk:
            queryset = queryset.exclude(pk=self.instance.pk)
        self.fields["parent"].queryset = queryset
        self.fields["parent"].empty_label = "--- nessuna (categoria radice) ---"


# =========================================================================
#  Categorie spesa, fornitori e documenti passivi
# =========================================================================


class CategoriaSpesaForm(forms.ModelForm):
    class Meta:
        model = CategoriaSpesa
        fields = ["nome", "descrizione", "ordine", "attiva"]
        labels = {
            "nome": "Nome categoria",
            "descrizione": "Descrizione",
            "ordine": "Ordine",
            "attiva": "Attiva",
        }
        widgets = {
            "descrizione": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["descrizione"].required = False
        self.fields["ordine"].required = False


class FornitoreForm(forms.ModelForm):
    class Meta:
        model = Fornitore
        fields = [
            "denominazione",
            "tipo_soggetto",
            "categoria_spesa",
            "codice_fiscale",
            "partita_iva",
            "indirizzo",
            "telefono",
            "email",
            "pec",
            "codice_sdi",
            "referente",
            "iban",
            "banca",
            "note",
            "attivo",
        ]
        labels = {
            "denominazione": "Denominazione / ragione sociale",
            "tipo_soggetto": "Tipo soggetto",
            "categoria_spesa": "Categoria di spesa",
            "codice_fiscale": "Codice fiscale",
            "partita_iva": "Partita IVA",
            "indirizzo": "Indirizzo",
            "telefono": "Telefono",
            "email": "Email",
            "pec": "PEC",
            "codice_sdi": "Codice SDI",
            "referente": "Referente",
            "iban": "IBAN",
            "banca": "Banca",
            "note": "Note",
            "attivo": "Attivo",
        }
        widgets = {
            "note": forms.Textarea(attrs={"rows": 3}),
            "iban": forms.TextInput(attrs={"placeholder": "IT00 X0000 0000 0000000000000"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        optional_fields = [
            "categoria_spesa",
            "codice_fiscale",
            "partita_iva",
            "indirizzo",
            "telefono",
            "email",
            "pec",
            "codice_sdi",
            "referente",
            "iban",
            "banca",
            "note",
        ]
        for field_name in optional_fields:
            self.fields[field_name].required = False
        self.fields["categoria_spesa"].queryset = CategoriaSpesa.objects.filter(attiva=True).order_by("ordine", "nome")
        self.fields["categoria_spesa"].empty_label = "--- nessuna ---"


class DocumentoFornitoreForm(forms.ModelForm):
    class Meta:
        model = DocumentoFornitore
        fields = [
            "fornitore",
            "categoria_spesa",
            "tipo_documento",
            "numero_documento",
            "data_documento",
            "data_ricezione",
            "anno_competenza",
            "mese_competenza",
            "descrizione",
            "imponibile",
            "aliquota_iva",
            "iva",
            "totale",
            "stato",
            "allegato",
            "note",
        ]
        labels = {
            "fornitore": "Fornitore",
            "categoria_spesa": "Categoria di spesa",
            "tipo_documento": "Tipo documento",
            "numero_documento": "Numero documento",
            "data_documento": "Data documento",
            "data_ricezione": "Data ricezione",
            "anno_competenza": "Anno competenza",
            "mese_competenza": "Mese competenza",
            "descrizione": "Descrizione",
            "imponibile": "Imponibile",
            "aliquota_iva": "Aliquota IVA %",
            "iva": "IVA",
            "totale": "Totale documento",
            "stato": "Stato",
            "allegato": "Allegato",
            "note": "Note",
        }
        widgets = {
            "data_documento": forms.DateInput(attrs={"type": "date"}),
            "data_ricezione": forms.DateInput(attrs={"type": "date"}),
            "mese_competenza": forms.Select(choices=MESE_COMPETENZA_CHOICES),
            "descrizione": forms.TextInput(attrs={"placeholder": "Causale o descrizione sintetica"}),
            "note": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        optional_fields = [
            "categoria_spesa",
            "data_ricezione",
            "anno_competenza",
            "mese_competenza",
            "descrizione",
            "imponibile",
            "iva",
            "totale",
            "allegato",
            "note",
        ]
        for field_name in optional_fields:
            self.fields[field_name].required = False
        self.fields["fornitore"].queryset = Fornitore.objects.filter(attivo=True).order_by("denominazione")
        make_searchable_select(self.fields["fornitore"], "Cerca un fornitore...")
        self.fields["categoria_spesa"].queryset = CategoriaSpesa.objects.filter(attiva=True).order_by("ordine", "nome")
        self.fields["categoria_spesa"].empty_label = "--- usa categoria del fornitore ---"
        self.fields["mese_competenza"].choices = MESE_COMPETENZA_CHOICES
        for field_name in ("imponibile", "iva", "totale"):
            apply_eur_currency_widget(self.fields[field_name], compact=False)

    def clean(self):
        cleaned = super().clean()
        imponibile = cleaned.get("imponibile")
        aliquota_iva = cleaned.get("aliquota_iva") or Decimal("0.00")
        iva = cleaned.get("iva")
        totale = cleaned.get("totale")

        if imponibile in (None, "") and totale in (None, ""):
            self.add_error("imponibile", "Inserisci l'imponibile oppure il totale documento.")
            self.add_error("totale", "Inserisci il totale documento oppure l'imponibile.")
            return cleaned

        moltiplicatore_iva = Decimal("1.00") + (aliquota_iva / Decimal("100"))

        total_is_source = totale not in (None, "") and (
            imponibile in (None, "") or (imponibile == Decimal("0.00") and totale != Decimal("0.00"))
        )

        if total_is_source:
            if moltiplicatore_iva == Decimal("0.00"):
                imponibile = totale
            else:
                imponibile = (totale / moltiplicatore_iva).quantize(Decimal("0.01"))
            iva = (totale - imponibile).quantize(Decimal("0.01"))
            cleaned["imponibile"] = imponibile
            cleaned["iva"] = iva
            cleaned["totale"] = totale.quantize(Decimal("0.01"))
            return cleaned

        if imponibile not in (None, ""):
            iva = (imponibile * aliquota_iva / Decimal("100")).quantize(Decimal("0.01"))
            cleaned["iva"] = iva
            cleaned["totale"] = (imponibile + iva).quantize(Decimal("0.01"))
        return cleaned


class ScadenzaPagamentoFornitoreForm(forms.ModelForm):
    class Meta:
        model = ScadenzaPagamentoFornitore
        fields = [
            "data_scadenza",
            "importo_previsto",
            "importo_pagato",
            "data_pagamento",
            "stato",
            "conto_bancario",
            "movimento_finanziario",
            "note",
        ]
        labels = {
            "data_scadenza": "Data scadenza",
            "importo_previsto": "Importo previsto",
            "importo_pagato": "Importo pagato",
            "data_pagamento": "Data pagamento",
            "stato": "Stato",
            "conto_bancario": "Conto",
            "movimento_finanziario": "Movimento collegato",
            "note": "Note",
        }
        widgets = {
            "data_scadenza": forms.DateInput(attrs={"type": "date"}),
            "data_pagamento": forms.DateInput(attrs={"type": "date"}),
            "note": forms.Textarea(attrs={"rows": 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        optional_fields = ["data_pagamento", "conto_bancario", "movimento_finanziario", "note"]
        for field_name in optional_fields:
            self.fields[field_name].required = False
        self.fields["conto_bancario"].queryset = ContoBancario.objects.filter(attivo=True).order_by("nome_conto")
        self.fields["conto_bancario"].empty_label = "--- nessuno ---"
        self.fields["movimento_finanziario"].queryset = MovimentoFinanziario.objects.order_by("-data_contabile", "-id")
        self.fields["movimento_finanziario"].empty_label = "--- nessuno ---"
        make_searchable_select(self.fields["conto_bancario"], "Cerca un conto...")
        make_searchable_select(self.fields["movimento_finanziario"], "Cerca un movimento...")
        apply_eur_currency_widget(self.fields["importo_previsto"])
        apply_eur_currency_widget(self.fields["importo_pagato"])

    def clean(self):
        cleaned = super().clean()
        if "stato" not in self.changed_data:
            temp = ScadenzaPagamentoFornitore(
                data_scadenza=cleaned.get("data_scadenza"),
                importo_previsto=cleaned.get("importo_previsto") or Decimal("0.00"),
                importo_pagato=cleaned.get("importo_pagato") or Decimal("0.00"),
                stato=cleaned.get("stato") or StatoScadenzaFornitore.PREVISTA,
            )
            cleaned["stato"] = temp.calcola_stato_automatico()
        return cleaned

    def save(self, commit=True):
        instance = super().save(commit=False)
        if "stato" in self.changed_data:
            instance._preserve_manual_stato = True
        if commit:
            instance.save()
            self.save_m2m()
        return instance


ScadenzaPagamentoFornitoreFormSet = inlineformset_factory(
    DocumentoFornitore,
    ScadenzaPagamentoFornitore,
    form=ScadenzaPagamentoFornitoreForm,
    extra=1,
    can_delete=True,
)


# =========================================================================
#  Provider bancari
# =========================================================================


class ProviderBancarioForm(forms.ModelForm):
    class Meta:
        model = ProviderBancario
        fields = ["nome", "tipo", "attivo", "note"]
        labels = {
            "nome": "Nome provider",
            "tipo": "Tipo di provider",
            "attivo": "Attivo",
            "note": "Note",
        }
        widgets = {
            "note": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["note"].required = False


# =========================================================================
#  Conti bancari
# =========================================================================


class ContoBancarioForm(forms.ModelForm):
    class Meta:
        model = ContoBancario
        fields = [
            "nome_conto",
            "banca",
            "iban",
            "bic",
            "intestatario",
            "valuta",
            "provider",
            "connessione",
            "attivo",
            "note",
        ]
        labels = {
            "nome_conto": "Nome conto",
            "banca": "Banca",
            "iban": "IBAN",
            "bic": "BIC",
            "intestatario": "Intestatario",
            "valuta": "Valuta",
            "provider": "Provider",
            "connessione": "Connessione bancaria",
            "attivo": "Attivo",
            "note": "Note",
        }
        widgets = {
            "note": forms.Textarea(attrs={"rows": 3}),
            "iban": forms.TextInput(attrs={"placeholder": "IT00 X0000 0000 0000000000000"}),
            "bic": forms.TextInput(attrs={"placeholder": "ABCDITMMXXX"}),
            "valuta": forms.TextInput(attrs={"placeholder": "EUR"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["banca"].required = False
        self.fields["iban"].required = False
        self.fields["bic"].required = False
        self.fields["intestatario"].required = False
        self.fields["connessione"].required = False
        self.fields["note"].required = False

        self.fields["provider"].queryset = ProviderBancario.objects.filter(attivo=True).order_by("nome")
        self.fields["connessione"].queryset = ConnessioneBancaria.objects.select_related("provider").order_by(
            "provider__nome", "etichetta"
        )
        self.fields["connessione"].empty_label = "--- nessuna ---"


# =========================================================================
#  Movimenti finanziari (manuali)
# =========================================================================


class MovimentoFinanziarioForm(forms.ModelForm):
    """
    Form usato per l'inserimento/modifica manuale di movimenti.
    L'origine viene forzata a `manuale` in fase di salvataggio quando il
    movimento viene creato (i movimenti bancari arrivano da flussi dedicati).
    """

    class Meta:
        model = MovimentoFinanziario
        fields = [
            "conto",
            "data_contabile",
            "data_valuta",
            "importo",
            "valuta",
            "descrizione",
            "controparte",
            "iban_controparte",
            "categoria",
            "incide_su_saldo_banca",
            "note",
        ]
        labels = {
            "conto": "Conto",
            "data_contabile": "Data contabile",
            "data_valuta": "Data valuta",
            "importo": "Importo (negativo per uscite)",
            "valuta": "Valuta",
            "descrizione": "Descrizione",
            "controparte": "Controparte",
            "iban_controparte": "IBAN controparte",
            "categoria": "Categoria",
            "incide_su_saldo_banca": "Incide sul saldo del conto",
            "note": "Note",
        }
        widgets = {
            "data_contabile": forms.DateInput(attrs={"placeholder": "gg/mm/aaaa"}),
            "data_valuta": forms.DateInput(attrs={"placeholder": "gg/mm/aaaa"}),
            "descrizione": forms.Textarea(attrs={"rows": 2}),
            "note": forms.Textarea(attrs={"rows": 2}),
            "valuta": forms.TextInput(attrs={"placeholder": "EUR"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["conto"].required = False
        self.fields["data_valuta"].required = False
        self.fields["descrizione"].required = False
        self.fields["controparte"].required = False
        self.fields["iban_controparte"].required = False
        self.fields["categoria"].required = False
        self.fields["note"].required = False

        self.fields["conto"].queryset = ContoBancario.objects.filter(attivo=True).order_by("nome_conto")
        self.fields["conto"].empty_label = "--- nessuno (movimento gestionale) ---"
        self.fields["categoria"].queryset = CategoriaFinanziaria.objects.filter(attiva=True).order_by(
            "parent__nome", "nome"
        )
        self.fields["categoria"].empty_label = "--- da categorizzare ---"
        self.fields["categoria"].help_text = (
            "Se lasciata vuota, il sistema prova ad assegnarla automaticamente tramite le regole attive."
        )
        self.fields["incide_su_saldo_banca"].help_text = (
            "Attiva per movimenti di cassa reali (es. cassa contanti tracciata in un conto interno). "
            "Lascia disattivo per voci puramente gestionali di previsione o controllo."
        )

    def clean(self):
        cleaned_data = super().clean()
        incide = cleaned_data.get("incide_su_saldo_banca")
        conto = cleaned_data.get("conto")
        if incide and not conto:
            self.add_error(
                "conto",
                "Per un movimento che incide sul saldo e' necessario specificare il conto.",
            )
        return cleaned_data


# =========================================================================
#  Regole di categorizzazione
# =========================================================================


class RegolaCategorizzazioneForm(forms.ModelForm):
    class Meta:
        model = RegolaCategorizzazione
        fields = [
            "nome",
            "priorita",
            "condizione_tipo",
            "pattern",
            "importo_min",
            "importo_max",
            "segno_filtro",
            "categoria_da_assegnare",
            "attiva",
            "note",
        ]
        labels = {
            "nome": "Nome regola",
            "priorita": "Priorita'",
            "condizione_tipo": "Condizione principale",
            "pattern": "Valore da confrontare",
            "importo_min": "Importo minimo",
            "importo_max": "Importo massimo",
            "segno_filtro": "Solo movimenti",
            "categoria_da_assegnare": "Categoria da assegnare",
            "attiva": "Attiva",
            "note": "Note",
        }
        widgets = {
            "note": forms.Textarea(attrs={"rows": 3}),
            "pattern": forms.TextInput(attrs={"placeholder": "es. ENEL, oppure IT60X0542811101000000123456"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["pattern"].required = False
        self.fields["importo_min"].required = False
        self.fields["importo_max"].required = False
        self.fields["segno_filtro"].required = False
        self.fields["note"].required = False

        self.fields["categoria_da_assegnare"].queryset = (
            CategoriaFinanziaria.objects.filter(attiva=True).order_by("parent__nome", "nome")
        )
        self.fields["priorita"].help_text = (
            "A parita' di match si applica la regola con priorita' numerica piu' bassa."
        )


# =========================================================================
#  Import estratto conto (file)
# =========================================================================


FORMATO_IMPORT_CHOICES = [
    ("camt053", "CAMT.053 (ISO 20022 XML)"),
    ("csv", "CSV (mappatura colonne personalizzabile)"),
]


class ImportEstrattoContoForm(forms.Form):
    """
    Form di upload del file di estratto conto. Le opzioni CSV sono utilizzate
    solo se ``formato == csv``: vengono ignorate per gli import CAMT.053.

    Le colonne CSV possono essere indicate tramite indice 0-based
    (es. ``0``, ``2``, ``5``) oppure tramite il nome dell'intestazione
    quando il file ha la prima riga di header.
    """

    conto = forms.ModelChoiceField(
        queryset=ContoBancario.objects.none(),
        label="Conto bancario",
    )
    formato = forms.ChoiceField(
        choices=FORMATO_IMPORT_CHOICES,
        label="Formato file",
    )
    file = forms.FileField(label="File da importare")

    # Parametri CSV (opzionali - ignorati se formato != csv)
    csv_delimiter = forms.CharField(
        required=False,
        max_length=1,
        label="Separatore CSV",
        help_text="Lascia vuoto per autodetect. Es. ';', ',', o tab.",
    )
    csv_encoding = forms.CharField(
        required=False,
        max_length=32,
        initial="utf-8-sig",
        label="Encoding",
    )
    csv_ha_intestazione = forms.BooleanField(
        required=False,
        initial=True,
        label="Prima riga con intestazione",
    )
    csv_formato_data = forms.CharField(
        required=False,
        max_length=32,
        initial="%d/%m/%Y",
        label="Formato data",
        help_text="Sintassi strftime. Es. %d/%m/%Y, %Y-%m-%d.",
    )
    csv_sep_decimale = forms.CharField(
        required=False,
        max_length=1,
        initial=",",
        label="Separatore decimali",
    )
    csv_sep_migliaia = forms.CharField(
        required=False,
        max_length=1,
        initial=".",
        label="Separatore migliaia",
    )

    csv_col_data_contabile = forms.CharField(
        required=False, label="Colonna 'Data contabile'",
        help_text="Indice (0,1,2...) oppure nome intestazione.",
    )
    csv_col_data_valuta = forms.CharField(required=False, label="Colonna 'Data valuta'")
    csv_col_importo = forms.CharField(
        required=False, label="Colonna 'Importo' (firmato)",
    )
    csv_col_entrate = forms.CharField(required=False, label="Colonna 'Entrate / Avere'")
    csv_col_uscite = forms.CharField(required=False, label="Colonna 'Uscite / Dare'")
    csv_col_valuta = forms.CharField(required=False, label="Colonna 'Valuta'")
    csv_col_descrizione = forms.CharField(required=False, label="Colonna 'Descrizione'")
    csv_col_controparte = forms.CharField(required=False, label="Colonna 'Controparte'")
    csv_col_iban_controparte = forms.CharField(required=False, label="Colonna 'IBAN controparte'")
    csv_col_transaction_id = forms.CharField(required=False, label="Colonna 'ID transazione'")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["conto"].queryset = ContoBancario.objects.filter(attivo=True).order_by(
            "nome_conto"
        )

    def clean_csv_delimiter(self):
        valore = self.cleaned_data.get("csv_delimiter") or ""
        if valore.lower() in {"\\t", "tab"}:
            return "\t"
        return valore

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("formato") != "csv":
            return cleaned

        data_col = cleaned.get("csv_col_data_contabile")
        importo_col = cleaned.get("csv_col_importo")
        entrate_col = cleaned.get("csv_col_entrate")
        uscite_col = cleaned.get("csv_col_uscite")

        if not data_col:
            self.add_error(
                "csv_col_data_contabile",
                "La colonna della data contabile e' obbligatoria per i file CSV.",
            )

        if not importo_col and not (entrate_col and uscite_col):
            self.add_error(
                "csv_col_importo",
                "Specifica la colonna 'Importo' firmato oppure entrambe 'Entrate' e 'Uscite'.",
            )

        return cleaned

    @staticmethod
    def parse_column_ref(valore: str):
        """Converte la stringa inserita dall'utente in int (indice) o str (nome)."""
        if valore is None:
            return None
        pulito = valore.strip()
        if not pulito:
            return None
        try:
            return int(pulito)
        except ValueError:
            return pulito


# =========================================================================
#  Provider PSD2 (configurazione credenziali)
# =========================================================================


class ProviderPsd2ConfigForm(forms.Form):
    """
    Configura le credenziali di un provider PSD2 (es. GoCardless BAD, TrueLayer).
    I secret vengono cifrati prima di essere salvati nel JSONField
    ``ProviderBancario.configurazione``.

    Convenzione sui nomi dei campi (neutri rispetto al provider):
    - ``secret_id``      = Secret ID (GoCardless) / Client ID (TrueLayer)
    - ``secret_key``     = Secret Key (GoCardless) / Client Secret (TrueLayer)
    - ``environment``    = sandbox/live per provider che lo richiedono
    - ``base_url``       = endpoint API (utile per GoCardless o fork custom)
    """

    ENVIRONMENT_CHOICES = [
        ("", "--- default ---"),
        ("sandbox", "Sandbox (test)"),
        ("live", "Produzione"),
    ]

    secret_id = forms.CharField(
        max_length=200,
        label="Secret ID / Client ID / App-id",
        help_text=(
            "Credenziale 'pubblica' fornita dal provider. "
            "GoCardless BAD: 'Secret ID'. TrueLayer: 'Client ID'. Salt Edge: 'App-id'."
        ),
    )
    secret_key = forms.CharField(
        max_length=400,
        widget=forms.PasswordInput(render_value=False),
        label="Secret Key / Client Secret / Secret",
        help_text=(
            "Verra' cifrata prima di essere salvata. Lascia vuoto per non modificarla. "
            "GoCardless BAD: 'Secret Key'. TrueLayer: 'Client Secret'. Salt Edge: 'Secret'."
        ),
        required=False,
    )
    environment = forms.ChoiceField(
        required=False,
        choices=ENVIRONMENT_CHOICES,
        label="Ambiente",
        help_text="Solo per provider che distinguono sandbox / live (es. TrueLayer).",
    )
    base_url = forms.URLField(
        required=False,
        label="Base URL API",
        help_text="Facoltativo. Default dipendente dal provider.",
    )
    redirect_uri = forms.URLField(
        required=False,
        label="Redirect URI (OAuth2)",
        help_text=(
            "Solo per provider OAuth2 (es. TrueLayer). Se specificato, questo "
            "valore viene usato come 'redirect_uri' nelle chiamate al provider "
            "e deve essere registrato ESATTAMENTE nella console dello "
            "sviluppatore del provider. Lascia vuoto per calcolarlo "
            "automaticamente dall'host della richiesta."
        ),
    )
    providers_default = forms.CharField(
        required=False,
        max_length=500,
        label="Providers TrueLayer (space-separated)",
        help_text=(
            "Facoltativo. Lista di 'providers' TrueLayer (separati da spazio) "
            "da proporre nel selettore OAuth2 (es. 'uk-ob-all uk-oauth-all "
            "it-ob-all'). Se vuoto, Arboris omette il parametro e TrueLayer "
            "usa la lista 'Allowed providers' dell'app sulla Console, "
            "dove si possono abilitare retail, business e corporate "
            "separatamente per ogni paese."
        ),
    )
    country_default = forms.CharField(
        required=False,
        max_length=2,
        label="Paese di default (ISO 3166-1 alfa-2)",
        help_text="Usato come default quando si cerca un istituto bancario. Es. IT.",
    )
    include_fake_providers = forms.BooleanField(
        required=False,
        label="Includi provider di test",
        help_text=(
            "Salt Edge: attiva per vedere nel widget anche le 'fake banks' "
            "(utili in ambiente Pending/Test). Lascia disattivo in produzione."
        ),
    )
    locale = forms.CharField(
        required=False,
        max_length=5,
        label="Lingua widget (Salt Edge)",
        help_text=(
            "Codice ISO 639-1 della lingua usata nel widget Salt Edge "
            "(es. 'it', 'en'). Default: 'it'."
        ),
    )
    PSU_TYPE_CHOICES = [
        ("", "--- default: personal ---"),
        ("personal", "Personal (retail)"),
        ("business", "Business (corporate)"),
    ]
    psu_type = forms.ChoiceField(
        required=False,
        choices=PSU_TYPE_CHOICES,
        label="Tipo utente (Enable Banking)",
        help_text=(
            "Solo Enable Banking. Seleziona se la connessione e' per utenza retail o "
            "corporate. Influenza i filtri sugli ASPSP che supportano solo uno dei due."
        ),
    )
    private_key_pem = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 8, "style": "font-family: monospace;"}),
        label="Private key RSA PEM (Salt Edge)",
        help_text=(
            "Solo Salt Edge. Incolla qui il contenuto completo del file .pem "
            "della private key (incluso '-----BEGIN PRIVATE KEY-----' / "
            "'-----END PRIVATE KEY-----'). Verra' cifrata prima di essere "
            "salvata. La corrispondente public key deve essere caricata nel "
            "dashboard Salt Edge &rarr; Keys. Obbligatoria per app in stato "
            "Live e spesso necessaria anche su Pending/Test per l'endpoint "
            "POST /connections/connect (altrimenti il WAF risponde 403). "
            "Lascia vuoto per non modificare la chiave gia' salvata."
        ),
    )
    private_key_passphrase = forms.CharField(
        required=False,
        widget=forms.PasswordInput(render_value=False),
        max_length=200,
        label="Passphrase private key (Salt Edge)",
        help_text=(
            "Solo Salt Edge. Se la private key PEM e' cifrata con passphrase "
            "(es. PKCS#8 protetta) inseriscila qui. Lascia vuoto se la chiave "
            "non ha passphrase o per non modificarla."
        ),
    )


class PianificazioneSincronizzazioneForm(forms.ModelForm):
    """Configurazione dello scheduler PSD2 (singleton)."""

    class Meta:
        model = PianificazioneSincronizzazione
        fields = [
            "attivo",
            "intervallo_ore",
            "sync_saldo",
            "sync_movimenti",
            "giorni_storico",
        ]
        labels = {
            "attivo": "Pianificazione attiva",
            "intervallo_ore": "Intervallo (ore)",
            "sync_saldo": "Sincronizza saldo",
            "sync_movimenti": "Sincronizza movimenti",
            "giorni_storico": "Giorni di storico da richiedere",
        }

    def clean_intervallo_ore(self):
        valore = self.cleaned_data.get("intervallo_ore") or 0
        if valore < 1:
            raise forms.ValidationError("L'intervallo minimo e' 1 ora.")
        if valore > 24 * 30:
            raise forms.ValidationError("L'intervallo massimo supportato e' 720 ore (30 giorni).")
        return valore


class NuovaConnessioneBancariaForm(forms.Form):
    """Form per avviare un nuovo consenso PSD2 verso una banca specifica."""

    etichetta = forms.CharField(
        max_length=150,
        label="Etichetta della connessione",
        help_text="Nome interno usato per riconoscerla (es. 'Banca Sella - Conto operativo').",
    )
    institution_id = forms.CharField(
        max_length=512,
        required=False,
        label="Identificativo istituto",
        help_text=(
            "Id fornito dalla lista banche del provider (es. 'SELLA_IT'). "
            "Lascia vuoto per provider OAuth2 come TrueLayer: verrai reindirizzato "
            "alla loro UI dove potrai scegliere la banca."
        ),
    )
    access_valid_for_days = forms.IntegerField(
        min_value=1,
        max_value=180,
        initial=90,
        label="Durata consenso (giorni)",
    )
    max_historical_days = forms.IntegerField(
        min_value=1,
        max_value=730,
        initial=90,
        label="Storico movimenti (giorni)",
    )

    def __init__(self, *args, provider: Optional[ProviderBancario] = None, **kwargs) -> None:
        self._provider = provider
        super().__init__(*args, **kwargs)
        if provider is not None:
            from .providers.registry import is_enablebanking_adapter, is_oauth_adapter

            if is_oauth_adapter(provider):
                self.fields["institution_id"].required = False
            else:
                self.fields["institution_id"].required = True
            if is_enablebanking_adapter(provider):
                self.fields["institution_id"].help_text = (
                    "Obbligatorio. Scegli la banca dal menu sotto (valore NomeIstituto|IT richiesto dall'API)."
                )

    def clean_institution_id(self) -> str:
        valore = (self.cleaned_data.get("institution_id") or "").strip()
        p = self._provider
        if p is not None:
            from .providers.registry import is_enablebanking_adapter, is_oauth_adapter

            if is_oauth_adapter(p):
                return valore
            if not valore:
                raise forms.ValidationError("Seleziona o inserisci l'istituto bancario.")
            if is_enablebanking_adapter(p) and "|" not in valore:
                raise forms.ValidationError(
                    "Per Enable Banking serve l'identificativo nel formato NomeBanca|IT "
                    "(selezionalo dal menu a tendina se la lista e' stata caricata)."
                )
        return valore
