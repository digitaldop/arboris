from __future__ import annotations

import re
from decimal import Decimal
from typing import Optional

from django import forms
from django.forms import inlineformset_factory

from arboris.form_widgets import apply_eur_currency_widget
from .security import cifra_testo

from .models import (
    CategoriaFinanziaria,
    ConnessioneBancaria,
    ContoBancario,
    DocumentoFornitore,
    FattureInCloudConnessione,
    Fornitore,
    MetodoPagamentoFornitore,
    MovimentoFinanziario,
    PagamentoFornitore,
    PianificazioneSincronizzazione,
    ProviderBancario,
    RegolaCategorizzazione,
    SaldoConto,
    ScadenzaPagamentoFornitore,
    StatoScadenzaFornitore,
    TipoCategoriaFinanziaria,
    VoceBudgetRicorrente,
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

MOVIMENTI_FORNITORE_CHOICES_LIMIT = 120


def make_searchable_select(field, placeholder):
    field.widget.attrs.update(
        {
            "data-searchable-select": "1",
            "data-searchable-placeholder": placeholder,
        }
    )


def categorie_spesa_queryset():
    return CategoriaFinanziaria.objects.filter(tipo=TipoCategoriaFinanziaria.SPESA, attiva=True).order_by(
        "parent__nome",
        "ordine",
        "nome",
    )


def movimenti_fornitore_recenti_ids(limit=MOVIMENTI_FORNITORE_CHOICES_LIMIT):
    return list(
        MovimentoFinanziario.objects.order_by("-data_contabile", "-id").values_list("pk", flat=True)[:limit]
    )


def movimenti_fornitore_queryset(choice_ids=None, selected_id=None):
    ids = set(choice_ids or [])
    if selected_id:
        ids.add(selected_id)

    if not ids:
        return MovimentoFinanziario.objects.none()

    return (
        MovimentoFinanziario.objects.filter(pk__in=ids)
        .only("id", "data_contabile", "importo", "descrizione")
        .order_by("-data_contabile", "-id")
    )


class CategoriaFinanziariaForm(forms.ModelForm):
    HEX_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")
    ICON_CHOICES = [
        {"value": "banknote", "label": "Banconota", "symbol": "€"},
        {"value": "receipt", "label": "Ricevuta", "symbol": "▤"},
        {"value": "wallet", "label": "Portafoglio", "symbol": "◧"},
        {"value": "credit-card", "label": "Carta", "symbol": "▭"},
        {"value": "bank", "label": "Banca", "symbol": "⌂"},
        {"value": "cart", "label": "Acquisti", "symbol": "▣"},
        {"value": "home", "label": "Casa", "symbol": "⌂"},
        {"value": "school", "label": "Scuola", "symbol": "▦"},
        {"value": "book", "label": "Didattica", "symbol": "▥"},
        {"value": "users", "label": "Persone", "symbol": "●●"},
        {"value": "heart", "label": "Cura", "symbol": "♡"},
        {"value": "bolt", "label": "Energia", "symbol": "⚡"},
        {"value": "droplet", "label": "Acqua", "symbol": "◌"},
        {"value": "wifi", "label": "Connettivita", "symbol": "⌁"},
        {"value": "tool", "label": "Manutenzione", "symbol": "⚙"},
        {"value": "briefcase", "label": "Servizi", "symbol": "▣"},
        {"value": "calendar", "label": "Periodo", "symbol": "◷"},
        {"value": "transfer", "label": "Trasferimento", "symbol": "⇄"},
    ]

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
            "colore": forms.TextInput(
                attrs={
                    "placeholder": "#336699",
                    "class": "category-color-code-input",
                    "autocomplete": "off",
                }
            ),
            "icona": forms.HiddenInput(),
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

    @property
    def color_picker_value(self):
        if self.is_bound:
            value = self.data.get(self.add_prefix("colore"), "")
        else:
            value = self.initial.get("colore") or getattr(self.instance, "colore", "")
        value = (value or "").strip()
        if value and not value.startswith("#"):
            value = f"#{value}"
        if self.HEX_COLOR_RE.match(value):
            return value
        return "#3b6f87"

    def clean_colore(self):
        value = (self.cleaned_data.get("colore") or "").strip()
        if not value:
            return ""
        if not value.startswith("#"):
            value = f"#{value}"
        if not self.HEX_COLOR_RE.match(value):
            raise forms.ValidationError("Inserisci un colore in formato esadecimale, ad esempio #336699.")
        return value.upper()


# =========================================================================
#  Budgeting
# =========================================================================


class VoceBudgetRicorrenteForm(forms.ModelForm):
    class Meta:
        model = VoceBudgetRicorrente
        fields = [
            "nome",
            "tipo",
            "categoria",
            "fornitore",
            "importo",
            "frequenza",
            "data_inizio",
            "data_fine",
            "giorno_previsto",
            "attiva",
            "note",
        ]
        labels = {
            "nome": "Nome voce",
            "tipo": "Tipo",
            "categoria": "Categoria",
            "fornitore": "Fornitore",
            "importo": "Importo previsto",
            "frequenza": "Frequenza",
            "data_inizio": "Data inizio",
            "data_fine": "Data fine",
            "giorno_previsto": "Giorno previsto",
            "attiva": "Attiva",
            "note": "Note",
        }
        widgets = {
            "data_inizio": forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"}),
            "data_fine": forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"}),
            "note": forms.Textarea(attrs={"rows": 4}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["categoria"].queryset = CategoriaFinanziaria.objects.filter(attiva=True).order_by(
            "tipo",
            "parent__nome",
            "ordine",
            "nome",
        )
        self.fields["fornitore"].queryset = Fornitore.objects.filter(attivo=True).order_by("denominazione")
        for field_name in ("categoria", "fornitore", "data_fine", "note"):
            self.fields[field_name].required = False
        for field_name in ("data_inizio", "data_fine"):
            self.fields[field_name].input_formats = ["%Y-%m-%d"]
        apply_eur_currency_widget(self.fields["importo"])
        make_searchable_select(self.fields["categoria"], "Cerca una categoria...")
        make_searchable_select(self.fields["fornitore"], "Cerca un fornitore...")

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.mese_previsto = None
        if commit:
            instance.save()
            self.save_m2m()
        return instance


# =========================================================================
#  Categorie spesa, fornitori e documenti passivi
# =========================================================================


class CategoriaSpesaForm(forms.ModelForm):
    descrizione = forms.CharField(
        label="Descrizione",
        required=False,
        widget=forms.Textarea(attrs={"rows": 3}),
    )

    class Meta:
        model = CategoriaFinanziaria
        fields = ["nome", "parent", "descrizione", "ordine", "attiva"]
        labels = {
            "nome": "Nome categoria",
            "parent": "Categoria padre",
            "descrizione": "Descrizione",
            "ordine": "Ordine",
            "attiva": "Attiva",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        parent_queryset = CategoriaFinanziaria.objects.filter(tipo=TipoCategoriaFinanziaria.SPESA).order_by(
            "parent__nome",
            "ordine",
            "nome",
        )
        if self.instance and self.instance.pk:
            parent_queryset = parent_queryset.exclude(pk=self.instance.pk)
        self.fields["parent"].queryset = parent_queryset
        self.fields["parent"].required = False
        self.fields["parent"].empty_label = "--- nessuna (categoria radice) ---"
        self.fields["ordine"].required = False
        if self.instance and self.instance.pk and not self.is_bound:
            self.fields["descrizione"].initial = self.instance.note

    def save(self, commit=True):
        categoria = super().save(commit=False)
        categoria.tipo = TipoCategoriaFinanziaria.SPESA
        categoria.note = self.cleaned_data.get("descrizione") or ""
        if commit:
            categoria.save()
            self.save_m2m()
        return categoria


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
        self.fields["categoria_spesa"].queryset = categorie_spesa_queryset()
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
            "tipo_documento": "Tipo fattura",
            "numero_documento": "Numero fattura",
            "data_documento": "Data fattura",
            "data_ricezione": "Data ricezione",
            "anno_competenza": "Anno competenza",
            "mese_competenza": "Mese competenza",
            "descrizione": "Descrizione",
            "imponibile": "Imponibile",
            "aliquota_iva": "Aliquota IVA %",
            "iva": "IVA",
            "totale": "Totale fattura",
            "stato": "Stato",
            "allegato": "Allegato",
            "note": "Note",
        }
        widgets = {
            "data_documento": forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"}),
            "data_ricezione": forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"}),
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
        self.fields["categoria_spesa"].queryset = categorie_spesa_queryset()
        self.fields["categoria_spesa"].empty_label = "--- usa categoria del fornitore ---"
        self.fields["mese_competenza"].choices = MESE_COMPETENZA_CHOICES
        for field_name in ("data_documento", "data_ricezione"):
            self.fields[field_name].input_formats = ["%Y-%m-%d"]
        for field_name in ("imponibile", "iva", "totale"):
            apply_eur_currency_widget(self.fields[field_name], compact=False)

    def clean(self):
        cleaned = super().clean()
        imponibile = cleaned.get("imponibile")
        aliquota_iva = cleaned.get("aliquota_iva") or Decimal("0.00")
        iva = cleaned.get("iva")
        totale = cleaned.get("totale")

        if imponibile in (None, "") and totale in (None, ""):
            self.add_error("imponibile", "Inserisci l'imponibile oppure il totale fattura.")
            self.add_error("totale", "Inserisci il totale fattura oppure l'imponibile.")
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
            "data_scadenza": forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"}),
            "data_pagamento": forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"}),
            "note": forms.TextInput(attrs={"placeholder": "Nota breve"}),
        }

    def __init__(self, *args, **kwargs):
        movimento_choices_ids = kwargs.pop("movimento_choices_ids", None)
        super().__init__(*args, **kwargs)
        optional_fields = ["data_pagamento", "conto_bancario", "movimento_finanziario", "note"]
        for field_name in optional_fields:
            self.fields[field_name].required = False
        for field_name in ("data_scadenza", "data_pagamento"):
            self.fields[field_name].input_formats = ["%Y-%m-%d"]
        self.fields["conto_bancario"].queryset = ContoBancario.objects.filter(attivo=True).order_by("nome_conto")
        self.fields["conto_bancario"].empty_label = "--- nessuno ---"
        if movimento_choices_ids is None:
            self.fields["movimento_finanziario"].queryset = MovimentoFinanziario.objects.order_by("-data_contabile", "-id")
        else:
            self.fields["movimento_finanziario"].queryset = movimenti_fornitore_queryset(
                movimento_choices_ids,
                selected_id=getattr(self.instance, "movimento_finanziario_id", None),
            )
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
    extra=0,
    can_delete=True,
)

ScadenzaPagamentoFornitoreCreateFormSet = inlineformset_factory(
    DocumentoFornitore,
    ScadenzaPagamentoFornitore,
    form=ScadenzaPagamentoFornitoreForm,
    extra=1,
    can_delete=True,
)


class PagamentoFornitoreForm(forms.ModelForm):
    class Meta:
        model = PagamentoFornitore
        fields = [
            "scadenza",
            "movimento_finanziario",
            "data_pagamento",
            "importo",
            "metodo",
            "conto_bancario",
            "note",
        ]
        labels = {
            "scadenza": "Scadenza",
            "movimento_finanziario": "Movimento bancario",
            "data_pagamento": "Data pagamento",
            "importo": "Importo",
            "metodo": "Metodo",
            "conto_bancario": "Conto",
            "note": "Note",
        }
        widgets = {
            "data_pagamento": forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"}),
            "note": forms.TextInput(attrs={"placeholder": "Nota breve"}),
        }

    def __init__(self, *args, **kwargs):
        movimento = kwargs.pop("movimento", None)
        super().__init__(*args, **kwargs)
        self.fields["scadenza"].queryset = (
            ScadenzaPagamentoFornitore.objects.select_related("documento", "documento__fornitore")
            .exclude(stato=StatoScadenzaFornitore.ANNULLATA)
            .order_by("data_scadenza", "id")
        )
        self.fields["movimento_finanziario"].queryset = MovimentoFinanziario.objects.order_by("-data_contabile", "-id")
        self.fields["data_pagamento"].input_formats = ["%Y-%m-%d"]
        self.fields["movimento_finanziario"].required = False
        self.fields["conto_bancario"].queryset = ContoBancario.objects.filter(attivo=True).order_by("nome_conto")
        self.fields["conto_bancario"].required = False
        self.fields["note"].required = False
        apply_eur_currency_widget(self.fields["importo"])
        make_searchable_select(self.fields["scadenza"], "Cerca una scadenza fornitore...")
        make_searchable_select(self.fields["movimento_finanziario"], "Cerca un movimento...")
        make_searchable_select(self.fields["conto_bancario"], "Cerca un conto...")
        if movimento is not None:
            self.fields["movimento_finanziario"].initial = movimento
            self.fields["metodo"].initial = MetodoPagamentoFornitore.BANCA
            if movimento.conto_id:
                self.fields["conto_bancario"].initial = movimento.conto
            if movimento.data_contabile:
                self.fields["data_pagamento"].initial = movimento.data_contabile

    def clean_importo(self):
        importo = self.cleaned_data.get("importo") or Decimal("0.00")
        if importo <= Decimal("0.00"):
            raise forms.ValidationError("L'importo deve essere maggiore di zero.")
        return importo


class FattureInCloudConnessioneForm(forms.ModelForm):
    client_secret = forms.CharField(
        label="Client secret",
        required=False,
        widget=forms.PasswordInput(render_value=False),
        help_text="Lascia vuoto per mantenere il valore gia salvato.",
    )
    access_token = forms.CharField(
        label="Access token manuale",
        required=False,
        widget=forms.PasswordInput(render_value=False),
        help_text="Utile per un primo collegamento manuale o per test privati.",
    )
    refresh_token = forms.CharField(
        label="Refresh token",
        required=False,
        widget=forms.PasswordInput(render_value=False),
        help_text="Lascia vuoto se usi un token manuale senza scadenza.",
    )

    class Meta:
        model = FattureInCloudConnessione
        fields = [
            "nome",
            "company_id",
            "client_id",
            "redirect_uri",
            "base_url",
            "attiva",
            "sincronizza_documenti_registrati",
            "sincronizza_documenti_da_registrare",
            "sync_automatico",
            "intervallo_sync_ore",
        ]
        labels = {
            "nome": "Nome connessione",
            "company_id": "Company ID",
            "client_id": "Client ID",
            "redirect_uri": "Redirect URI OAuth",
            "base_url": "Base URL API",
            "attiva": "Connessione attiva",
            "sincronizza_documenti_registrati": "Importa spese registrate",
            "sincronizza_documenti_da_registrare": "Importa fatture da registrare",
            "sync_automatico": "Sincronizzazione automatica",
            "intervallo_sync_ore": "Intervallo automatico (ore)",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name in ("company_id", "client_id", "redirect_uri"):
            self.fields[field_name].required = False
        if self.instance and self.instance.pk:
            if self.instance.client_secret_cifrato:
                self.fields["client_secret"].help_text = "Secret gia salvato. Compila solo per sostituirlo."
            if self.instance.access_token_cifrato:
                self.fields["access_token"].help_text = "Token gia salvato. Compila solo per sostituirlo."

    def save(self, commit=True):
        instance = super().save(commit=False)
        client_secret = self.cleaned_data.get("client_secret") or ""
        access_token = self.cleaned_data.get("access_token") or ""
        refresh_token = self.cleaned_data.get("refresh_token") or ""
        if client_secret:
            instance.client_secret_cifrato = cifra_testo(client_secret)
        if access_token:
            instance.access_token_cifrato = cifra_testo(access_token)
        if refresh_token:
            instance.refresh_token_cifrato = cifra_testo(refresh_token)
        if instance.access_token_cifrato and instance.company_id:
            instance.stato = "attiva"
        if commit:
            instance.save()
        return instance


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
            "tipo_conto",
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
            "tipo_conto": "Tipo conto",
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
        self.fields["tipo_conto"].required = True
        self.fields["banca"].required = False
        self.fields["iban"].required = False
        self.fields["bic"].required = False
        self.fields["intestatario"].required = False
        self.fields["provider"].required = False
        self.fields["connessione"].required = False
        self.fields["note"].required = False

        self.fields["provider"].queryset = ProviderBancario.objects.filter(attivo=True).order_by("nome")
        self.fields["provider"].empty_label = "--- nessuno ---"
        self.fields["connessione"].queryset = ConnessioneBancaria.objects.select_related("provider").order_by(
            "provider__nome", "etichetta"
        )
        self.fields["connessione"].empty_label = "--- nessuna ---"


# =========================================================================
#  Saldi conti
# =========================================================================


class SaldoContoForm(forms.ModelForm):
    class Meta:
        model = SaldoConto
        fields = [
            "conto",
            "data_riferimento",
            "saldo_contabile",
            "saldo_disponibile",
            "valuta",
            "fonte",
            "note",
        ]
        labels = {
            "conto": "Conto",
            "data_riferimento": "Data riferimento",
            "saldo_contabile": "Saldo contabile",
            "saldo_disponibile": "Saldo disponibile",
            "valuta": "Valuta",
            "fonte": "Fonte",
            "note": "Note",
        }
        widgets = {
            "data_riferimento": forms.DateTimeInput(
                attrs={"type": "datetime-local"},
                format="%Y-%m-%dT%H:%M",
            ),
            "valuta": forms.TextInput(attrs={"placeholder": "EUR"}),
            "note": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["conto"].queryset = ContoBancario.objects.filter(attivo=True).order_by("nome_conto")
        self.fields["saldo_disponibile"].required = False
        self.fields["note"].required = False
        self.fields["data_riferimento"].input_formats = ["%Y-%m-%dT%H:%M", "%d/%m/%Y %H:%M", "%d/%m/%Y"]
        for field_name in ("saldo_contabile", "saldo_disponibile"):
            apply_eur_currency_widget(self.fields[field_name], compact=False)


class ImportSaldiContoCsvForm(forms.Form):
    file = forms.FileField(
        label="File CSV",
        help_text=(
            "Colonne riconosciute: conto_id oppure nome_conto/conto, data_riferimento oppure data, "
            "saldo_contabile oppure saldo, saldo_disponibile e valuta opzionali."
        ),
    )


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
            "canale",
            "data_contabile",
            "data_valuta",
            "importo",
            "valuta",
            "descrizione",
            "controparte",
            "iban_controparte",
            "categoria",
            "incide_su_saldo_banca",
            "sostenuta_da_terzi",
            "rimborsabile",
            "sostenitore",
            "note",
        ]
        labels = {
            "conto": "Conto",
            "canale": "Canale",
            "data_contabile": "Data contabile",
            "data_valuta": "Data valuta",
            "importo": "Importo (negativo per uscite)",
            "valuta": "Valuta",
            "descrizione": "Descrizione",
            "controparte": "Controparte",
            "iban_controparte": "IBAN controparte",
            "categoria": "Categoria",
            "incide_su_saldo_banca": "Incide sul saldo del conto",
            "sostenuta_da_terzi": "Sostenuta da terzi",
            "rimborsabile": "Da rimborsare",
            "sostenitore": "Sostenitore",
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
        self.fields["sostenitore"].required = False
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
        self.fields["sostenuta_da_terzi"].help_text = (
            "Usa questa opzione per spese pagate da soci/genitori senza uscita dal conto della scuola."
        )

    def clean(self):
        cleaned_data = super().clean()
        incide = cleaned_data.get("incide_su_saldo_banca")
        conto = cleaned_data.get("conto")
        canale = cleaned_data.get("canale")
        sostenuta_da_terzi = cleaned_data.get("sostenuta_da_terzi")
        if canale == "personale":
            cleaned_data["sostenuta_da_terzi"] = True
            sostenuta_da_terzi = True
        if sostenuta_da_terzi and incide:
            self.add_error(
                "incide_su_saldo_banca",
                "Una spesa sostenuta da terzi non deve incidere sul saldo del conto della scuola.",
            )
        if incide and not conto:
            self.add_error(
                "conto",
                "Per un movimento che incide sul saldo e' necessario specificare il conto.",
            )
        return cleaned_data


class PuliziaMovimentiFinanziariForm(forms.Form):
    AMBITO_TUTTI = "tutti"
    AMBITO_AUTOMATICI = "automatici"
    AMBITO_MANUALI = "manuali"

    AMBITO_CHOICES = [
        (AMBITO_TUTTI, "Tutti i movimenti"),
        (AMBITO_AUTOMATICI, "Solo import automatici (file/PSD2)"),
        (AMBITO_MANUALI, "Solo inserimenti manuali"),
    ]

    ambito = forms.ChoiceField(
        choices=AMBITO_CHOICES,
        label="Movimenti da eliminare",
        initial=AMBITO_AUTOMATICI,
        help_text=(
            "Gli import automatici includono i movimenti importati da file estratto conto "
            "e quelli sincronizzati tramite provider bancario/PSD2."
        ),
    )
    conferma = forms.CharField(
        label='Conferma digitando "ELIMINA"',
        required=True,
        max_length=20,
    )

    def clean_conferma(self):
        value = (self.cleaned_data.get("conferma") or "").strip().upper()
        if value != "ELIMINA":
            raise forms.ValidationError('Per confermare devi digitare esattamente "ELIMINA".')
        return value


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
            "pattern": "Condizioni testo",
            "importo_min": "Importo minimo",
            "importo_max": "Importo massimo",
            "segno_filtro": "Solo movimenti",
            "categoria_da_assegnare": "Categoria da assegnare",
            "attiva": "Attiva",
            "note": "Note",
        }
        widgets = {
            "note": forms.Textarea(attrs={"rows": 3}),
            "pattern": forms.Textarea(
                attrs={
                    "rows": 4,
                    "placeholder": "es. COMM.SU BONIFICI | COMMISSIONI oppure quota + maggio | iscrizione",
                }
            ),
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
        self.fields["pattern"].help_text = (
            "Per le condizioni testuali puoi usare | oppure una nuova riga come OR; "
            "usa + per richiedere piu' parole insieme. Esempio: quota + maggio | iscrizione."
        )


# =========================================================================
#  Import estratto conto (file)
# =========================================================================


FORMATO_IMPORT_CHOICES = [
    ("auto", "Rilevamento automatico"),
    ("camt053", "CAMT.053 (ISO 20022 XML)"),
    ("csv", "CSV con mappatura manuale"),
    ("excel", "Excel XLS/XLSX con mappatura manuale"),
]


class ImportEstrattoContoForm(forms.Form):
    """
    Form di upload del file di estratto conto. Le opzioni tabellari sono
    utilizzate per CSV/Excel: vengono ignorate per gli import CAMT.053.

    Le colonne CSV/Excel possono essere indicate tramite indice 0-based
    (es. ``0``, ``2``, ``5``) oppure tramite il nome dell'intestazione
    quando il file ha la prima riga di header.
    """

    conto = forms.ModelChoiceField(
        queryset=ContoBancario.objects.none(),
        label="Conto bancario",
        required=False,
        help_text="Se possibile viene rilevato automaticamente dal file. In caso contrario selezionalo in anteprima.",
    )
    formato = forms.ChoiceField(
        choices=FORMATO_IMPORT_CHOICES,
        label="Formato file",
        initial="auto",
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
        make_searchable_select(self.fields["conto"], "Cerca un conto...")
        self.fields["file"].widget.attrs.update(
            {"accept": ".xml,.camt,.camt053,.csv,.xls,.xlsx,.xlsm"}
        )

    def clean_csv_delimiter(self):
        valore = self.cleaned_data.get("csv_delimiter") or ""
        if valore.lower() in {"\\t", "tab"}:
            return "\t"
        return valore

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("formato") not in {"csv", "excel"}:
            return cleaned

        data_col = cleaned.get("csv_col_data_contabile")
        importo_col = cleaned.get("csv_col_importo")
        entrate_col = cleaned.get("csv_col_entrate")
        uscite_col = cleaned.get("csv_col_uscite")

        if not data_col:
            self.add_error(
                "csv_col_data_contabile",
                "La colonna della data contabile e' obbligatoria per i file CSV/Excel.",
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
