from decimal import Decimal

from django import forms
from django.forms import inlineformset_factory
from django.utils import timezone

from servizi_extra.models import (
    ServizioExtra,
    TariffaServizioExtra,
    TariffaServizioExtraRata,
    IscrizioneServizioExtra,
    RataServizioExtra,
)


class DateInput(forms.DateInput):
    input_type = "date"


class TariffaServizioExtraSelect(forms.Select):
    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        option = super().create_option(name, value, label, selected, index, subindex=subindex, attrs=attrs)

        if value and hasattr(value, "instance"):
            option["attrs"]["data-servizio-id"] = str(value.instance.servizio_id or "")

        return option


class ServizioExtraForm(forms.ModelForm):
    class Meta:
        model = ServizioExtra
        fields = ["anno_scolastico", "nome_servizio", "ordine", "descrizione", "attiva", "note"]
        widgets = {
            "descrizione": forms.Textarea(attrs={"rows": 3}),
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


class TariffaServizioExtraForm(forms.ModelForm):
    class Meta:
        model = TariffaServizioExtra
        fields = ["servizio", "nome_tariffa", "rateizzata", "attiva", "note"]
        widgets = {
            "note": forms.Textarea(attrs={"rows": 4}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["servizio"].queryset = self.fields["servizio"].queryset.select_related("anno_scolastico").order_by(
            "-anno_scolastico__data_inizio",
            "nome_servizio",
        )
        self.fields["servizio"].empty_label = None
        self.fields["rateizzata"].help_text = "Attiva la modalita rateizzata per definire piu scadenze nella stessa tariffa."

        if not self.instance.pk and not self.is_bound and not self.initial.get("servizio"):
            primo_servizio = self.fields["servizio"].queryset.first()
            if primo_servizio:
                self.initial["servizio"] = primo_servizio.pk


class TariffaServizioExtraRataForm(forms.ModelForm):
    class Meta:
        model = TariffaServizioExtraRata
        fields = ["numero_rata", "descrizione", "importo", "data_scadenza"]
        widgets = {
            "data_scadenza": DateInput(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["descrizione"].required = False
        self.fields["descrizione"].help_text = "Lascia vuoto per usare automaticamente 'Rata N'."
        self.fields["importo"].widget.attrs.update(
            {
                "autocomplete": "off",
                "inputmode": "decimal",
                "data-currency": "EUR",
                "placeholder": "0,00",
            }
        )


class BaseTariffaServizioExtraRataFormSet(forms.BaseInlineFormSet):
    def clean(self):
        super().clean()

        if any(form.errors for form in self.forms):
            return

        rateizzata = str(self.data.get("rateizzata") or "").lower() in {"1", "true", "on"}
        active_rows = []
        numeri_rate = set()

        for form in self.forms:
            cleaned_data = getattr(form, "cleaned_data", None) or {}
            if cleaned_data.get("DELETE"):
                continue

            numero_rata = cleaned_data.get("numero_rata")
            descrizione = cleaned_data.get("descrizione")
            importo = cleaned_data.get("importo")
            data_scadenza = cleaned_data.get("data_scadenza")

            if not any([numero_rata, descrizione, importo, data_scadenza]):
                continue

            if numero_rata in numeri_rate:
                raise forms.ValidationError("Il numero rata deve essere univoco all'interno della stessa tariffa.")

            numeri_rate.add(numero_rata)
            active_rows.append(cleaned_data)

        if not active_rows:
            raise forms.ValidationError("Inserisci almeno una rata per la tariffa.")

        if not rateizzata and len(active_rows) != 1:
            raise forms.ValidationError("Se la tariffa non e rateizzata devi inserire una sola rata.")


TariffaServizioExtraRataFormSet = inlineformset_factory(
    TariffaServizioExtra,
    TariffaServizioExtraRata,
    form=TariffaServizioExtraRataForm,
    formset=BaseTariffaServizioExtraRataFormSet,
    extra=1,
    can_delete=True,
)


class IscrizioneServizioExtraForm(forms.ModelForm):
    class Meta:
        model = IscrizioneServizioExtra
        fields = [
            "studente",
            "servizio",
            "tariffa",
            "data_iscrizione",
            "data_fine_iscrizione",
            "attiva",
            "note_amministrative",
            "note",
        ]
        widgets = {
            "tariffa": TariffaServizioExtraSelect(),
            "data_iscrizione": DateInput(),
            "data_fine_iscrizione": DateInput(),
            "note_amministrative": forms.Textarea(attrs={"rows": 3}),
            "note": forms.Textarea(attrs={"rows": 4}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["studente"].queryset = self.fields["studente"].queryset.order_by("cognome", "nome")
        self.fields["servizio"].queryset = self.fields["servizio"].queryset.select_related("anno_scolastico").order_by(
            "-anno_scolastico__data_inizio",
            "nome_servizio",
        )

        service_id = self.data.get("servizio") if self.is_bound else getattr(self.instance, "servizio_id", None)

        if not service_id and not self.is_bound and not self.instance.pk:
            primo_servizio = self.fields["servizio"].queryset.first()
            if primo_servizio:
                service_id = primo_servizio.pk
                self.initial["servizio"] = primo_servizio.pk

        tariffa_queryset = TariffaServizioExtra.objects.none()
        if service_id:
            tariffa_queryset = TariffaServizioExtra.objects.filter(servizio_id=service_id).order_by("nome_tariffa")

        self.fields["tariffa"].queryset = tariffa_queryset
        self.fields["servizio"].empty_label = None
        self.fields["tariffa"].empty_label = None

        if not self.instance.pk and not self.is_bound:
            if not self.initial.get("tariffa"):
                prima_tariffa = tariffa_queryset.first()
                if prima_tariffa:
                    self.initial["tariffa"] = prima_tariffa.pk
            if not self.initial.get("data_iscrizione"):
                self.initial["data_iscrizione"] = timezone.localdate()


class RataServizioExtraPagamentoForm(forms.ModelForm):
    class Meta:
        model = RataServizioExtra
        fields = [
            "data_scadenza",
            "pagata",
            "importo_pagato",
            "data_pagamento",
            "metodo_pagamento",
            "note",
        ]
        widgets = {
            "data_scadenza": DateInput(),
            "data_pagamento": DateInput(),
            "note": forms.Textarea(attrs={"rows": 4}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["importo_pagato"].widget = forms.TextInput()
        self.fields["importo_pagato"].widget.attrs.update(
            {
                "autocomplete": "off",
                "inputmode": "decimal",
                "data-currency": "EUR",
                "placeholder": "0,00",
            }
        )
        self.fields["metodo_pagamento"].required = False
        self.fields["metodo_pagamento"].widget.attrs.update({"placeholder": "Contanti, bonifico, POS..."})

    def clean(self):
        cleaned_data = super().clean()
        pagata = cleaned_data.get("pagata")
        importo_pagato = cleaned_data.get("importo_pagato") or Decimal("0.00")
        importo_finale = self.instance.importo_finale or Decimal("0.00")
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
                cleaned_data["metodo_pagamento"] = ""
            elif importo_pagato <= 0:
                cleaned_data["data_pagamento"] = None
                cleaned_data["metodo_pagamento"] = ""

        return cleaned_data

