from django import forms
from django.db.models import Q

from anagrafica.forms import make_searchable_select, html5_date_input
from anagrafica.models import Citta, Indirizzo

from .models import (
    BustaPagaDipendente,
    ContrattoDipendente,
    Dipendente,
    ParametroCalcoloStipendio,
    TipoContrattoDipendente,
)


class CittaCodiceCatastaleSelect(forms.Select):
    def create_option(self, name, value, label, selected, index, subindex=None, attrs=None):
        option = super().create_option(name, value, label, selected, index, subindex=subindex, attrs=attrs)
        if value and hasattr(value, "instance"):
            option["attrs"]["data-codice-catastale"] = value.instance.codice_catastale or ""
        return option


def tipo_contratto_queryset(selected_id=None):
    qs_filter = Q(attivo=True)
    if selected_id:
        qs_filter |= Q(pk=selected_id)
    return TipoContrattoDipendente.objects.filter(qs_filter).order_by("ordine", "nome")


def parametro_calcolo_queryset(selected_id=None):
    qs_filter = Q(attivo=True)
    if selected_id:
        qs_filter |= Q(pk=selected_id)
    return ParametroCalcoloStipendio.objects.filter(qs_filter).order_by("-valido_dal", "nome")


class DipendenteForm(forms.ModelForm):
    contratto = forms.ModelChoiceField(
        queryset=ContrattoDipendente.objects.none(),
        required=False,
        label="Contratto",
    )
    luogo_nascita = forms.ModelChoiceField(
        queryset=Citta.objects.none(),
        required=False,
        label="Luogo di nascita",
        widget=CittaCodiceCatastaleSelect(),
    )

    class Meta:
        model = Dipendente
        fields = [
            "nome",
            "cognome",
            "data_nascita",
            "luogo_nascita",
            "nazionalita",
            "sesso",
            "codice_fiscale",
            "indirizzo",
            "telefono",
            "email",
            "iban",
            "codice_dipendente",
            "stato",
            "data_assunzione",
            "data_cessazione",
            "note",
        ]
        labels = {
            "codice_dipendente": "Matricola / codice interno",
            "nome": "Nome",
            "cognome": "Cognome",
            "codice_fiscale": "Codice fiscale",
            "data_nascita": "Data nascita",
            "luogo_nascita": "Luogo nascita",
            "nazionalita": "Nazionalita",
            "sesso": "Sesso",
            "email": "Email",
            "telefono": "Telefono",
            "indirizzo": "Indirizzo",
            "iban": "IBAN",
            "stato": "Stato",
            "data_assunzione": "Data assunzione",
            "data_cessazione": "Data cessazione",
            "note": "Note",
        }
        widgets = {
            "data_nascita": html5_date_input(),
            "data_assunzione": html5_date_input(),
            "data_cessazione": html5_date_input(),
            "note": forms.Textarea(attrs={"rows": 4}),
            "iban": forms.TextInput(attrs={"placeholder": "IT00X0000000000000000000000"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        optional_fields = [
            "codice_dipendente",
            "codice_fiscale",
            "data_nascita",
            "luogo_nascita",
            "nazionalita",
            "sesso",
            "email",
            "telefono",
            "indirizzo",
            "iban",
            "data_assunzione",
            "data_cessazione",
            "note",
        ]
        for field_name in optional_fields:
            self.fields[field_name].required = False

        self.fields["luogo_nascita"].queryset = (
            Citta.objects.filter(attiva=True).select_related("provincia").order_by("nome")
        )
        self.fields["luogo_nascita"].label_from_instance = lambda obj: f"{obj.nome} ({obj.provincia.sigla})"
        make_searchable_select(self.fields["luogo_nascita"], "Cerca una citta...")

        self.fields["indirizzo"].queryset = (
            Indirizzo.objects.select_related("citta", "provincia", "regione").order_by("via", "numero_civico")
        )
        self.fields["indirizzo"].label_from_instance = lambda obj: obj.label_select()
        make_searchable_select(self.fields["indirizzo"], "Cerca un indirizzo...")
        self.fields["indirizzo"].empty_label = "--- nessun indirizzo collegato ---"
        self._setup_contratto_field()
        self.fields["codice_dipendente"].help_text = (
            "Campo opzionale per una matricola interna, un codice consulente paghe o un identificativo usato nei file esterni."
        )
        self.fields["nome"].widget.attrs["data-cf-nome"] = "1"
        self.fields["cognome"].widget.attrs["data-cf-cognome"] = "1"
        self.fields["data_nascita"].widget.attrs["data-cf-data-nascita"] = "1"
        self.fields["sesso"].widget.attrs["data-cf-sesso"] = "1"
        self.fields["luogo_nascita"].widget.attrs["data-cf-luogo-id"] = "1"
        self.fields["codice_fiscale"].widget.attrs["data-cf-output"] = "1"

        if self.is_bound:
            return

        luogo_nascita_value = (getattr(self.instance, "luogo_nascita", "") or "").strip()
        if luogo_nascita_value:
            citta = self._find_citta_from_label(luogo_nascita_value)
            if citta:
                self.initial["luogo_nascita"] = citta.pk
                self.fields["luogo_nascita"].widget.attrs["data-codice-catastale"] = citta.codice_catastale or ""

    def _setup_contratto_field(self):
        contratto_id = self.data.get(self.add_prefix("contratto")) if self.is_bound else self.initial.get("contratto")
        if not contratto_id and getattr(self.instance, "pk", None):
            contratto_corrente = self.instance.contratto_corrente
            if contratto_corrente:
                contratto_id = contratto_corrente.pk
                self.initial["contratto"] = contratto_corrente.pk

        qs_filter = Q(dipendente__isnull=True)
        if getattr(self.instance, "pk", None):
            qs_filter |= Q(dipendente=self.instance)
        if contratto_id:
            qs_filter |= Q(pk=contratto_id)

        self.fields["contratto"].queryset = (
            ContrattoDipendente.objects.select_related("dipendente", "tipo_contratto")
            .filter(qs_filter)
            .order_by("-data_inizio", "-id")
        )
        self.fields["contratto"].label_from_instance = lambda obj: obj.label_select(include_dipendente=False)
        make_searchable_select(self.fields["contratto"], "Cerca un contratto...")
        self.fields["contratto"].empty_label = "--- nessun contratto collegato ---"

    @staticmethod
    def _find_citta_from_label(value):
        value = (value or "").strip()
        if not value:
            return None

        if value.endswith(")") and " (" in value:
            nome, sigla = value.rsplit(" (", 1)
            sigla = sigla.rstrip(")")
            return (
                Citta.objects.filter(nome__iexact=nome.strip(), provincia__sigla__iexact=sigla.strip(), attiva=True)
                .select_related("provincia")
                .first()
            )

        qs = Citta.objects.filter(nome__iexact=value, attiva=True).select_related("provincia")
        return qs.first() if qs.count() == 1 else None

    def save(self, commit=True):
        dipendente = super().save(commit=False)
        citta = self.cleaned_data.get("luogo_nascita")
        dipendente.luogo_nascita = f"{citta.nome} ({citta.provincia.sigla})" if citta else ""
        if commit:
            dipendente.save()
            self.save_m2m()
            contratto = self.cleaned_data.get("contratto")
            if contratto and contratto.dipendente_id != dipendente.pk:
                contratto.dipendente = dipendente
                contratto.save(update_fields=["dipendente"])
        return dipendente

    def clean_contratto(self):
        contratto = self.cleaned_data.get("contratto")
        if not contratto:
            return contratto
        instance_pk = getattr(self.instance, "pk", None)
        if contratto.dipendente_id and contratto.dipendente_id != instance_pk:
            raise forms.ValidationError("Il contratto selezionato appartiene a un altro dipendente.")
        return contratto


class ContrattoDipendenteForm(forms.ModelForm):
    class Meta:
        model = ContrattoDipendente
        fields = [
            "descrizione",
            "tipo_contratto",
            "parametro_calcolo",
            "data_inizio",
            "data_fine",
            "ccnl",
            "livello",
            "qualifica",
            "mansione",
            "regime_orario",
            "ore_settimanali",
            "percentuale_part_time",
            "retribuzione_lorda_mensile",
            "tariffa_oraria",
            "superminimo_mensile",
            "indennita_fisse_mensili",
            "mensilita_annue",
            "valuta",
            "attivo",
            "note",
        ]
        labels = {
            "descrizione": "Descrizione",
            "tipo_contratto": "Tipo contratto",
            "parametro_calcolo": "Parametro di calcolo",
            "data_inizio": "Data inizio",
            "data_fine": "Data fine",
            "ccnl": "CCNL",
            "livello": "Livello",
            "qualifica": "Qualifica",
            "mansione": "Mansione",
            "regime_orario": "Regime orario",
            "ore_settimanali": "Ore settimanali",
            "percentuale_part_time": "Percentuale part-time",
            "retribuzione_lorda_mensile": "Compenso lordo mensile",
            "tariffa_oraria": "Tariffa oraria",
            "superminimo_mensile": "Superminimo mensile",
            "indennita_fisse_mensili": "Indennita fisse mensili",
            "mensilita_annue": "Mensilita annue",
            "valuta": "Valuta",
            "attivo": "Attivo",
            "note": "Note",
        }
        widgets = {
            "data_inizio": forms.DateInput(attrs={"placeholder": "gg/mm/aaaa"}),
            "data_fine": forms.DateInput(attrs={"placeholder": "gg/mm/aaaa"}),
            "note": forms.Textarea(attrs={"rows": 3}),
            "valuta": forms.TextInput(attrs={"placeholder": "EUR"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        tipo_contratto_id = self.data.get(self.add_prefix("tipo_contratto")) if self.is_bound else self.initial.get(
            "tipo_contratto",
            getattr(self.instance, "tipo_contratto_id", None),
        )
        self.fields["tipo_contratto"].queryset = tipo_contratto_queryset(tipo_contratto_id)
        make_searchable_select(self.fields["tipo_contratto"], "Cerca un tipo di contratto...")
        parametro_calcolo_id = (
            self.data.get(self.add_prefix("parametro_calcolo"))
            if self.is_bound
            else self.initial.get(
                "parametro_calcolo",
                getattr(self.instance, "parametro_calcolo_id", None),
            )
        )
        self.fields["parametro_calcolo"].queryset = parametro_calcolo_queryset(parametro_calcolo_id)
        self.fields["parametro_calcolo"].empty_label = "--- parametro automatico per periodo ---"
        make_searchable_select(self.fields["parametro_calcolo"], "Cerca un parametro di calcolo...")
        optional_fields = [
            "descrizione",
            "parametro_calcolo",
            "data_fine",
            "ccnl",
            "livello",
            "qualifica",
            "mansione",
            "note",
        ]
        for field_name in optional_fields:
            self.fields[field_name].required = False


class TipoContrattoDipendenteForm(forms.ModelForm):
    class Meta:
        model = TipoContrattoDipendente
        fields = ["nome", "ordine", "attivo", "note"]
        labels = {
            "nome": "Tipo di contratto",
            "ordine": "Ordine",
            "attivo": "Attivo",
            "note": "Note",
        }
        widgets = {
            "note": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["ordine"].required = False
        self.fields["note"].required = False


class ParametroCalcoloStipendioForm(forms.ModelForm):
    class Meta:
        model = ParametroCalcoloStipendio
        fields = [
            "nome",
            "valido_dal",
            "valido_al",
            "aliquota_contributi_datore",
            "aliquota_contributi_dipendente",
            "aliquota_tfr",
            "aliquota_inail",
            "aliquota_altri_oneri",
            "attivo",
            "note",
        ]
        labels = {
            "nome": "Nome parametro",
            "valido_dal": "Valido dal",
            "valido_al": "Valido al",
            "aliquota_contributi_datore": "Contributi datore (%)",
            "aliquota_contributi_dipendente": "Contributi dipendente (%)",
            "aliquota_tfr": "TFR (%)",
            "aliquota_inail": "INAIL (%)",
            "aliquota_altri_oneri": "Altri oneri (%)",
            "attivo": "Attivo",
            "note": "Note",
        }
        widgets = {
            "valido_dal": forms.DateInput(attrs={"placeholder": "gg/mm/aaaa"}),
            "valido_al": forms.DateInput(attrs={"placeholder": "gg/mm/aaaa"}),
            "note": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["valido_al"].required = False
        self.fields["note"].required = False


class BustaPagaDipendenteForm(forms.ModelForm):
    class Meta:
        model = BustaPagaDipendente
        fields = [
            "dipendente",
            "contratto",
            "anno",
            "mese",
            "stato",
            "valuta",
            "lordo_previsto",
            "contributi_datore_previsti",
            "contributi_dipendente_previsti",
            "rateo_tredicesima_previsto",
            "rateo_tfr_previsto",
            "altri_oneri_previsti",
            "netto_previsto",
            "costo_azienda_previsto",
            "lordo_effettivo",
            "contributi_datore_effettivi",
            "contributi_dipendente_effettivi",
            "rateo_tredicesima_effettivo",
            "rateo_tfr_effettivo",
            "altri_oneri_effettivi",
            "netto_effettivo",
            "costo_azienda_effettivo",
            "file_busta_paga",
            "data_pagamento_effettiva",
            "movimento_pagamento",
            "note_previsione",
            "note_effettivo",
        ]
        labels = {
            "dipendente": "Dipendente",
            "contratto": "Contratto",
            "anno": "Anno",
            "mese": "Mese",
            "stato": "Stato",
            "valuta": "Valuta",
            "lordo_previsto": "Lordo previsto",
            "contributi_datore_previsti": "Contributi datore previsti",
            "contributi_dipendente_previsti": "Contributi dipendente previsti",
            "rateo_tredicesima_previsto": "Rateo tredicesima previsto",
            "rateo_tfr_previsto": "Rateo TFR previsto",
            "altri_oneri_previsti": "Altri oneri previsti",
            "netto_previsto": "Netto previsto",
            "costo_azienda_previsto": "Costo azienda previsto",
            "lordo_effettivo": "Lordo effettivo",
            "contributi_datore_effettivi": "Contributi datore effettivi",
            "contributi_dipendente_effettivi": "Contributi dipendente effettivi",
            "rateo_tredicesima_effettivo": "Rateo tredicesima effettivo",
            "rateo_tfr_effettivo": "Rateo TFR effettivo",
            "altri_oneri_effettivi": "Altri oneri effettivi",
            "netto_effettivo": "Netto effettivo",
            "costo_azienda_effettivo": "Costo azienda effettivo",
            "file_busta_paga": "File busta paga",
            "data_pagamento_effettiva": "Data pagamento effettiva",
            "movimento_pagamento": "Movimento pagamento",
            "note_previsione": "Note previsione",
            "note_effettivo": "Note effettivo",
        }
        widgets = {
            "data_pagamento_effettiva": forms.DateInput(attrs={"placeholder": "gg/mm/aaaa"}),
            "valuta": forms.TextInput(attrs={"placeholder": "EUR"}),
            "note_previsione": forms.Textarea(attrs={"rows": 3}),
            "note_effettivo": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["contratto"].required = False
        self.fields["file_busta_paga"].required = False
        self.fields["data_pagamento_effettiva"].required = False
        self.fields["movimento_pagamento"].required = False
        self.fields["note_previsione"].required = False
        self.fields["note_effettivo"].required = False
        self.fields["dipendente"].queryset = Dipendente.objects.order_by("cognome", "nome")
        self.fields["contratto"].queryset = ContrattoDipendente.objects.select_related(
            "dipendente",
            "tipo_contratto",
            "parametro_calcolo",
        ).order_by(
            "dipendente__cognome",
            "dipendente__nome",
            "-data_inizio",
        )
        self.fields["contratto"].empty_label = "--- nessun contratto collegato ---"
        self.fields["movimento_pagamento"].empty_label = "--- nessun movimento collegato ---"

    def clean(self):
        cleaned_data = super().clean()
        dipendente = cleaned_data.get("dipendente")
        contratto = cleaned_data.get("contratto")
        if dipendente and contratto and contratto.dipendente_id != dipendente.pk:
            self.add_error("contratto", "Il contratto selezionato appartiene a un altro dipendente.")
        return cleaned_data
