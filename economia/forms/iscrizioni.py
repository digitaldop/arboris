from decimal import Decimal

from django import forms
from django.forms import HiddenInput
from django.db import DatabaseError
from django.utils import timezone
from arboris.form_widgets import apply_eur_currency_widget, italian_decimal_to_python, merge_widget_classes
from scuola.utils import resolve_default_anno_scolastico

from economia.models import (
    MetodoPagamento,
    StatoIscrizione,
    CondizioneIscrizione,
    TariffaCondizioneIscrizione,
    Agevolazione,
    Iscrizione,
    RataIscrizione,
)


class DateInput(forms.DateInput):
    input_type = "date"
    format = "%Y-%m-%d"


class CondizioneIscrizioneSelect(forms.Select):
    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        option = super().create_option(name, value, label, selected, index, subindex=subindex, attrs=attrs)

        if value and hasattr(value, "instance"):
            option["attrs"]["data-riduzione-speciale-ammessa"] = "1" if value.instance.riduzione_speciale_ammessa else "0"

        return option


class StatoIscrizioneForm(forms.ModelForm):
    class Meta:
        model = StatoIscrizione
        fields = ["stato_iscrizione", "ordine", "attiva", "note"]
        widgets = {
            "note": forms.Textarea(attrs={"rows": 4}),
        }


class CondizioneIscrizioneForm(forms.ModelForm):
    class Meta:
        model = CondizioneIscrizione
        fields = [
            "anno_scolastico",
            "nome_condizione_iscrizione",
            "numero_mensilita_default",
            "mese_prima_retta",
            "giorno_scadenza_rate",
            "riduzione_speciale_ammessa",
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

        if not self.instance.pk and not self.is_bound and not self.initial.get("mese_prima_retta"):
            self.initial["mese_prima_retta"] = CondizioneIscrizione.DEFAULT_MESE_PRIMA_RETTA

        self.fields["giorno_scadenza_rate"].required = False
        self.fields["giorno_scadenza_rate"].widget.attrs.update(
            {
                "min": "1",
                "max": "31",
                "inputmode": "numeric",
            }
        )
        self.fields["mese_prima_retta"].label = "Mese prima retta"


class TariffaCondizioneIscrizioneForm(forms.ModelForm):
    class Meta:
        model = TariffaCondizioneIscrizione
        fields = [
            "condizione_iscrizione",
            "ordine_figlio_da",
            "ordine_figlio_a",
            "retta_annuale",
            "preiscrizione",
            "attiva",
            "note",
        ]
        widgets = {
            "note": forms.Textarea(attrs={"rows": 4}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["condizione_iscrizione"].queryset = self.fields["condizione_iscrizione"].queryset.order_by(
            "-anno_scolastico__data_inizio",
            "nome_condizione_iscrizione",
        )
        self.fields["condizione_iscrizione"].empty_label = None
        self.fields["ordine_figlio_da"].label = "Da figlio"
        self.fields["ordine_figlio_a"].label = "A figlio"
        self.fields["ordine_figlio_a"].required = False
        self.fields["ordine_figlio_a"].help_text = "Lascia vuoto per indicare 'e oltre'."
        apply_eur_currency_widget(self.fields["retta_annuale"])
        apply_eur_currency_widget(self.fields["preiscrizione"])

        if not self.instance.pk and not self.is_bound and not self.initial.get("condizione_iscrizione"):
            prima_condizione = self.fields["condizione_iscrizione"].queryset.first()
            if prima_condizione:
                self.initial["condizione_iscrizione"] = prima_condizione.pk


class AgevolazioneForm(forms.ModelForm):
    class Meta:
        model = Agevolazione
        fields = ["nome_agevolazione", "importo_annuale_agevolazione", "attiva"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_eur_currency_widget(self.fields["importo_annuale_agevolazione"])


class IscrizioneForm(forms.ModelForm):
    class Meta:
        model = Iscrizione
        fields = [
            "studente",
            "anno_scolastico",
            "classe",
            "data_iscrizione",
            "data_fine_iscrizione",
            "stato_iscrizione",
            "condizione_iscrizione",
            "agevolazione",
            "riduzione_speciale",
            "importo_riduzione_speciale",
            "non_pagante",
            "modalita_pagamento_retta",
            "sconto_unica_soluzione_tipo",
            "sconto_unica_soluzione_valore",
            "scadenza_pagamento_unica",
            "attiva",
            "note_amministrative",
            "note",
        ]
        widgets = {
            "data_iscrizione": DateInput(),
            "data_fine_iscrizione": DateInput(),
            "condizione_iscrizione": CondizioneIscrizioneSelect(),
            "scadenza_pagamento_unica": DateInput(),
            "note_amministrative": forms.Textarea(attrs={"rows": 3}),
            "note": forms.Textarea(attrs={"rows": 4}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["anno_scolastico"].queryset = self.fields["anno_scolastico"].queryset.order_by("-data_inizio", "-id")
        self.fields["studente"].queryset = self.fields["studente"].queryset.order_by("cognome", "nome")
        self.fields["stato_iscrizione"].queryset = self.fields["stato_iscrizione"].queryset.order_by("ordine", "stato_iscrizione")
        self.fields["anno_scolastico"].empty_label = None
        self.fields["stato_iscrizione"].empty_label = None
        self.fields["condizione_iscrizione"].empty_label = None
        self.fields["importo_riduzione_speciale"].label = "Importo riduzione speciale"
        self.fields["importo_riduzione_speciale"].help_text = "Importo in euro."
        apply_eur_currency_widget(self.fields["importo_riduzione_speciale"])
        self.fields["modalita_pagamento_retta"].label = "Modalita pagamento retta"
        self.fields["sconto_unica_soluzione_tipo"].label = "Sconto unica soluzione"
        self.fields["sconto_unica_soluzione_valore"].label = "Valore sconto"
        self.fields["sconto_unica_soluzione_valore"].help_text = "Inserisci una percentuale o un importo in base al tipo di sconto selezionato."
        self.fields["sconto_unica_soluzione_valore"].required = False
        self.fields["sconto_unica_soluzione_valore"].localize = True
        self.fields["sconto_unica_soluzione_valore"].to_python = (
            lambda value, _field=self.fields["sconto_unica_soluzione_valore"]: italian_decimal_to_python(_field, value)
        )
        self.fields["sconto_unica_soluzione_valore"].widget = forms.TextInput()
        merge_widget_classes(
            self.fields["sconto_unica_soluzione_valore"].widget,
            "currency-field",
            "currency-field-compact",
        )
        self.fields["sconto_unica_soluzione_valore"].widget.attrs.update(
            {
                "autocomplete": "off",
                "inputmode": "decimal",
                "placeholder": "0,00",
            }
        )
        self.fields["scadenza_pagamento_unica"].label = "Scadenza pagamento unico"
        self.fields["scadenza_pagamento_unica"].required = False
        self.fields["agevolazione"].required = False
        try:
            self.fields["agevolazione"].queryset = self.fields["agevolazione"].queryset.filter(attiva=True).order_by("nome_agevolazione")
        except DatabaseError:
            self.fields["agevolazione"].queryset = self.fields["agevolazione"].queryset.none()

        classi_queryset = self.fields["classe"].queryset.none()
        condizioni_queryset = self.fields["condizione_iscrizione"].queryset.none()

        anno_scolastico_id = self.data.get("anno_scolastico") if self.is_bound else getattr(self.instance, "anno_scolastico_id", None)

        if anno_scolastico_id:
            classi_queryset = self.fields["classe"].queryset.filter(anno_scolastico_id=anno_scolastico_id).order_by(
                "ordine_classe",
                "nome_classe",
                "sezione_classe",
            )
            condizioni_queryset = self.fields["condizione_iscrizione"].queryset.filter(
                anno_scolastico_id=anno_scolastico_id
            ).order_by("nome_condizione_iscrizione")

        self.fields["classe"].queryset = classi_queryset
        self.fields["condizione_iscrizione"].queryset = condizioni_queryset

        if not self.instance.pk and not self.is_bound:
            anno_predefinito = resolve_default_anno_scolastico(self.fields["anno_scolastico"].queryset)

            if not self.initial.get("anno_scolastico"):
                if anno_predefinito:
                    self.initial["anno_scolastico"] = anno_predefinito.pk
                    anno_scolastico_id = anno_predefinito.pk
                    self.fields["classe"].queryset = self.fields["classe"].queryset.model.objects.filter(
                        anno_scolastico_id=anno_scolastico_id
                    ).order_by("ordine_classe", "nome_classe", "sezione_classe")
                    self.fields["condizione_iscrizione"].queryset = self.fields["condizione_iscrizione"].queryset.model.objects.filter(
                        anno_scolastico_id=anno_scolastico_id
                    ).order_by("nome_condizione_iscrizione")

            if not self.initial.get("stato_iscrizione"):
                primo_stato = self.fields["stato_iscrizione"].queryset.first()
                if primo_stato:
                    self.initial["stato_iscrizione"] = primo_stato.pk

            if anno_scolastico_id and not self.initial.get("condizione_iscrizione"):
                prima_condizione = self.fields["condizione_iscrizione"].queryset.first()
                if prima_condizione:
                    self.initial["condizione_iscrizione"] = prima_condizione.pk

        if not self.is_bound:
            anno_per_date = self.instance.anno_scolastico if self.instance.pk and self.instance.anno_scolastico_id else None
            if anno_per_date is None and anno_scolastico_id:
                anno_per_date = self.fields["anno_scolastico"].queryset.filter(pk=anno_scolastico_id).first()
            if anno_per_date:
                if not self.initial.get("data_iscrizione") and not getattr(self.instance, "data_iscrizione", None):
                    self.initial["data_iscrizione"] = anno_per_date.data_inizio
                if not self.initial.get("data_fine_iscrizione") and not getattr(self.instance, "data_fine_iscrizione", None):
                    self.initial["data_fine_iscrizione"] = anno_per_date.data_fine

        if not getattr(self.instance, "pk", None):
            self.fields["data_fine_iscrizione"].widget = HiddenInput()

        try:
            from fondo_accantonamento.models import RegolaScontoAgevolazione
        except ImportError:  # pragma: no cover
            RegolaScontoAgevolazione = None
        if RegolaScontoAgevolazione and RegolaScontoAgevolazione.objects.filter(attiva=True).exists():
            f_agev = self.fields.get("agevolazione")
            if f_agev and not f_agev.help_text:
                f_agev.help_text = (
                    "Se in Fondo accantonamento e' attiva una regola per l'agevolazione scelta, "
                    "le uscite SCONTO_RETTA vengono sincronizzate con le rate mensili."
                )

    def clean(self):
        cleaned_data = super().clean()
        anno_scolastico = cleaned_data.get("anno_scolastico")
        if anno_scolastico:
            if not cleaned_data.get("data_iscrizione"):
                cleaned_data["data_iscrizione"] = anno_scolastico.data_inizio
            if not cleaned_data.get("data_fine_iscrizione"):
                cleaned_data["data_fine_iscrizione"] = anno_scolastico.data_fine
        if cleaned_data.get("sconto_unica_soluzione_valore") is None:
            cleaned_data["sconto_unica_soluzione_valore"] = Decimal("0.00")
        return cleaned_data


class RataIscrizionePagamentoForm(forms.ModelForm):
    class Meta:
        model = RataIscrizione
        fields = [
            "data_scadenza",
            "pagata",
            "importo_pagato",
            "data_pagamento",
            "metodo_pagamento",
            "credito_applicato",
            "altri_sgravi",
            "note",
        ]
        widgets = {
            "data_scadenza": DateInput(),
            "data_pagamento": DateInput(),
            "note": forms.Textarea(attrs={"rows": 4}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_eur_currency_widget(self.fields["importo_pagato"])
        apply_eur_currency_widget(self.fields["credito_applicato"])
        apply_eur_currency_widget(self.fields["altri_sgravi"])
        self.fields["metodo_pagamento"].required = False
        self.fields["metodo_pagamento"].queryset = self.fields["metodo_pagamento"].queryset.filter(attivo=True).order_by(
            "metodo_pagamento"
        )

    def clean(self):
        cleaned_data = super().clean()
        if self.instance and self.instance.is_preiscrizione:
            cleaned_data["data_scadenza"] = None

        pagata = cleaned_data.get("pagata")
        importo_pagato = cleaned_data.get("importo_pagato") or Decimal("0.00")
        credito_applicato = cleaned_data.get("credito_applicato") or Decimal("0.00")
        altri_sgravi = cleaned_data.get("altri_sgravi") or Decimal("0.00")
        importo_finale = max((self.instance.importo_dovuto or Decimal("0.00")) - credito_applicato - altri_sgravi, Decimal("0.00"))
        previously_marked_as_paid = bool(
            self.instance.pk
            and (
                self.instance.pagata
                or ((self.instance.importo_pagato or Decimal("0.00")) >= (self.instance.importo_finale or Decimal("0.00")) > 0)
            )
        )

        if pagata and importo_pagato < importo_finale:
            self.add_error(
                "importo_pagato",
                "Per segnare la rata come pagata, l'importo pagato deve coprire almeno l'importo finale.",
            )

        if not pagata:
            if previously_marked_as_paid and importo_finale > 0 and importo_pagato >= importo_finale:
                cleaned_data["importo_pagato"] = Decimal("0.00")
                cleaned_data["data_pagamento"] = None
                cleaned_data["metodo_pagamento"] = None
            elif importo_pagato <= 0:
                cleaned_data["data_pagamento"] = None
                cleaned_data["metodo_pagamento"] = None

        return cleaned_data


class RataIscrizionePagamentoRapidoForm(forms.Form):
    pagamento_integrale = forms.BooleanField(
        required=False,
        initial=True,
        label="E stato pagato l'intero importo",
    )
    importo_pagato_personalizzato = forms.DecimalField(
        required=False,
        max_digits=10,
        decimal_places=2,
        min_value=0,
        label="Importo pagato",
    )
    data_pagamento = forms.DateField(
        widget=DateInput(),
        label="Data del pagamento",
    )
    metodo_pagamento = forms.ModelChoiceField(
        queryset=MetodoPagamento.objects.none(),
        required=False,
        label="Metodo di pagamento",
    )

    def __init__(self, *args, rata=None, initial_metodo_pagamento_id=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.rata = rata
        self.fields["metodo_pagamento"].queryset = MetodoPagamento.objects.filter(attivo=True).order_by("metodo_pagamento")
        self.fields["data_pagamento"].initial = timezone.localdate()
        apply_eur_currency_widget(self.fields["importo_pagato_personalizzato"])

        if initial_metodo_pagamento_id and not self.is_bound:
            self.initial["metodo_pagamento"] = initial_metodo_pagamento_id

    def clean(self):
        cleaned_data = super().clean()
        pagamento_integrale = cleaned_data.get("pagamento_integrale")
        importo_personalizzato = cleaned_data.get("importo_pagato_personalizzato")

        if not pagamento_integrale and importo_personalizzato is None:
            self.add_error("importo_pagato_personalizzato", "Indica l'importo pagato se il pagamento non e integrale.")

        return cleaned_data


class RitiroAnticipatoIscrizioneForm(forms.Form):
    data_ritiro = forms.DateField(
        widget=DateInput(),
        label="Data di ritiro",
    )
    note = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 3}),
        label="Note",
    )

    def __init__(self, *args, iscrizione=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.iscrizione = iscrizione

    def clean_data_ritiro(self):
        data_ritiro = self.cleaned_data["data_ritiro"]

        if not self.iscrizione:
            return data_ritiro

        if self.iscrizione.data_iscrizione and data_ritiro < self.iscrizione.data_iscrizione:
            raise forms.ValidationError("La data di ritiro non puo essere precedente alla data di iscrizione.")

        if self.iscrizione.anno_scolastico_id and data_ritiro > self.iscrizione.anno_scolastico.data_fine:
            raise forms.ValidationError("La data di ritiro non puo superare la fine dell'anno scolastico.")

        return data_ritiro
