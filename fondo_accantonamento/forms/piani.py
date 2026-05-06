from __future__ import annotations

from django import forms

from scuola.models import AnnoScolastico

from ..models import MovimentoFondo, PianoAccantonamento, TipoModalitaPiano


class PianoAccantonamentoForm(forms.ModelForm):
    class Meta:
        model = PianoAccantonamento
        fields = [
            "sempre_attivo",
            "anno_scolastico",
            "nome",
            "descrizione",
            "attivo",
            "modalita",
            "percentuale_su_rette",
            "periodicita",
            "data_primo_versamento",
            "importo_versamento_periodico",
            "tipo_deposito",
            "descrizione_deposito",
            "coordinate_riferimento",
        ]
        labels = {
            "sempre_attivo": "Sempre attivo (non legato a un singolo anno)",
            "nome": "Nome piano",
            "descrizione": "Descrizione",
            "attivo": "Attivo",
            "modalita": "Modalita' di versamento",
            "percentuale_su_rette": "Percentuale sulle rette (%)",
            "periodicita": "Periodicita' versamento",
            "data_primo_versamento": "Data primo versamento (periodici)",
            "importo_versamento_periodico": "Importo versamento periodico",
            "tipo_deposito": "Dove sono tenuti i fondi",
            "descrizione_deposito": "Descrizione (banca, cassa, ...)",
            "coordinate_riferimento": "Coordinate / note accesso (sensibili)",
        }
        help_texts = {
            "sempre_attivo": "Se abiliti questa opzione, non selezionare l'anno scolastico: le regole automatiche (percentuale rette, sconti agev., ecc.) si applicano a ogni anno. Utile per un conto/deposito condiviso.",
            "modalita": "Versamenti e prelievi manuali sono sempre possibili; le altre opzioni abilitano percentuale e/o scadenze periodiche.",
            "percentuale_su_rette": "Esempio: 2,50 per il 2,5% trattenuto sulle rette. Modificabile solo con modalita' su percentuale o mista.",
            "data_primo_versamento": "Base per calcolare le scadenze. Modificabile solo con versamenti periodici o mista.",
        }

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.fields["anno_scolastico"].queryset = AnnoScolastico.objects.filter(attivo=True).order_by(
            "-data_inizio"
        )
        self.fields["anno_scolastico"].required = False
        self.fields["sempre_attivo"].required = False
        self.fields["descrizione"].required = False
        self.fields["descrizione"].widget = forms.Textarea(attrs={"rows": 3})
        self.fields["coordinate_riferimento"].widget = forms.Textarea(attrs={"rows": 2})

    def clean(self):
        data = super().clean()
        sempre = data.get("sempre_attivo")
        if sempre:
            data["anno_scolastico"] = None
        elif not data.get("anno_scolastico"):
            self.add_error(
                "anno_scolastico",
                "Seleziona l'anno scolastico oppure abilita Sempre attivo.",
            )
        modalita = (data.get("modalita") or "").strip()
        if modalita == TipoModalitaPiano.PERCENTUALE_RETTE:
            p = data.get("percentuale_su_rette")
            if p is None or p <= 0:
                self.add_error(
                    "percentuale_su_rette",
                    "Indica una percentuale valida (maggiore di zero).",
                )
        if modalita == TipoModalitaPiano.VERSAMENTI_PERIODICI:
            self._valida_parte_periodica(data)
        if modalita == TipoModalitaPiano.MISTO:
            ha_pct = data.get("percentuale_su_rette") and data.get("percentuale_su_rette") > 0
            ha_period = bool(
                data.get("data_primo_versamento")
                and data.get("periodicita")
                and data.get("importo_versamento_periodico")
                and data.get("importo_versamento_periodico") > 0
            )
            if not ha_pct and not ha_period:
                self.add_error(
                    None,
                    "In modalita' Percentuale sulle rette e Versamenti periodici imposta almeno la percentuale oppure i versamenti periodici (date e importi).",
                )
            if ha_pct and (data.get("percentuale_su_rette") or 0) <= 0:
                self.add_error("percentuale_su_rette", "Percentuale non valida.")
            if ha_period:
                self._valida_parte_periodica(data, obbligo_completo=True)
        return data

    def _valida_parte_periodica(self, data, obbligo_completo: bool = True) -> None:
        if not data.get("data_primo_versamento"):
            self.add_error(
                "data_primo_versamento",
                "Obbligatoria per le scadenze periodiche.",
            )
        if not data.get("periodicita"):
            self.add_error("periodicita", "Seleziona la periodicita' dei versamenti.")
        imp = data.get("importo_versamento_periodico")
        if obbligo_completo and (imp is None or imp <= 0):
            self.add_error(
                "importo_versamento_periodico",
                "Indica l'importo per ciascun versamento periodico.",
            )


class VersamentoFondoForm(forms.ModelForm):
    """Solo versamenti in entrata manuali."""

    class Meta:
        model = MovimentoFondo
        fields = ["data", "importo", "note"]
        labels = {
            "data": "Data versamento",
            "importo": "Importo",
            "note": "Note",
        }

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.fields["note"].widget = forms.Textarea(attrs={"rows": 2})


class PrelievoFondoForm(forms.ModelForm):
    """Prelievo dal fondo (manuale)."""

    class Meta:
        model = MovimentoFondo
        fields = ["data", "importo", "richiedente", "motivo", "note"]
        labels = {
            "data": "Data prelievo",
            "importo": "Importo",
            "richiedente": "Prelevato da / approvato da",
            "motivo": "Motivazione",
            "note": "Note aggiuntive",
        }

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.fields["motivo"].widget = forms.Textarea(attrs={"rows": 1})
        self.fields["note"].widget = forms.Textarea(attrs={"rows": 2})

    def clean(self):
        d = super().clean()
        if not (d.get("richiedente") or "").strip():
            self.add_error("richiedente", "Indicare chi ha effettuato o autorizzato il prelievo.")
        return d
