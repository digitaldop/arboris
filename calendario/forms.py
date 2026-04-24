from datetime import datetime, timedelta

from django import forms
from django.db.models import Q

from .models import CategoriaCalendario, EventoCalendario


class DateInput(forms.DateInput):
    input_type = "date"


class TimeInput(forms.TimeInput):
    input_type = "time"


class ColorInput(forms.TextInput):
    input_type = "color"


class CategoriaCalendarioForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk and self.instance.is_system_category:
            self.fields["attiva"].disabled = True

    class Meta:
        model = CategoriaCalendario
        fields = ["nome", "colore", "ordine", "attiva"]
        widgets = {
            "colore": ColorInput(),
        }
        labels = {
            "nome": "Nome categoria",
            "colore": "Colore etichetta",
        }


class EventoCalendarioForm(forms.ModelForm):
    durata_minuti = forms.IntegerField(
        label="Durata (minuti)",
        required=False,
        min_value=15,
        max_value=1440,
        help_text="Se la compili, il sistema ricalcola automaticamente l'orario di fine.",
    )

    class Meta:
        model = EventoCalendario
        fields = [
            "titolo",
            "categoria_evento",
            "tipologia",
            "data_inizio",
            "data_fine",
            "ora_inizio",
            "ora_fine",
            "intera_giornata",
            "ripetizione",
            "ripeti_ogni_intervallo",
            "ripetizione_numero_occorrenze",
            "ripetizione_fino_al",
            "luogo",
            "descrizione",
            "visibile",
            "attivo",
        ]
        labels = {
            "categoria_evento": "Categoria",
            "tipologia": "Tipologia / tag",
            "ripeti_ogni_intervallo": "Ripeti ogni",
            "ripetizione_numero_occorrenze": "Numero occorrenze",
            "ripetizione_fino_al": "Ripeti fino al",
        }
        widgets = {
            "data_inizio": DateInput(),
            "data_fine": DateInput(),
            "ora_inizio": TimeInput(),
            "ora_fine": TimeInput(),
            "ripetizione_fino_al": DateInput(),
            "descrizione": forms.Textarea(attrs={"rows": 5}),
        }
        help_texts = {
            "data_fine": "Per eventi che durano piu giorni puoi estendere liberamente la data finale.",
            "ripeti_ogni_intervallo": "Usa 1 per ogni ciclo, oppure un numero maggiore per saltare giorni, settimane, mesi o anni.",
            "ripetizione_numero_occorrenze": "Compila solo questo oppure la data finale della serie. La prima occorrenza conta.",
            "ripetizione_fino_al": "Compila solo questa oppure il numero occorrenze.",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        categorie_attive = CategoriaCalendario.objects.filter(attiva=True)
        if self.instance and self.instance.pk and self.instance.categoria_evento_id:
            categorie_attive = CategoriaCalendario.objects.filter(
                Q(attiva=True) | Q(pk=self.instance.categoria_evento_id)
            )
        self.fields["categoria_evento"].queryset = categorie_attive.order_by("ordine", "nome")
        self.fields["tipologia"].required = False
        self.fields["ripeti_ogni_intervallo"].required = False
        self.fields["ripetizione_numero_occorrenze"].required = False
        self.fields["ripetizione_fino_al"].required = False
        self.fields["ripeti_ogni_intervallo"].initial = self.instance.ripeti_ogni_intervallo if self.instance and self.instance.pk else 1

        if self.instance and self.instance.pk and self.instance.durata_minuti:
            self.fields["durata_minuti"].initial = self.instance.durata_minuti

        self._sync_recurrence_interval_label(
            self.data.get(self.add_prefix("ripetizione")) if self.is_bound else getattr(self.instance, "ripetizione", None)
        )

    def _sync_recurrence_interval_label(self, recurrence_value):
        unit_map = {
            EventoCalendario.RIPETIZIONE_GIORNALIERA: "giorni",
            EventoCalendario.RIPETIZIONE_GIORNI_FERIALI: "giorni feriali",
            EventoCalendario.RIPETIZIONE_SETTIMANALE: "settimane",
            EventoCalendario.RIPETIZIONE_MENSILE: "mesi",
            EventoCalendario.RIPETIZIONE_ANNUALE: "anni",
        }
        unit_label = unit_map.get(recurrence_value, "intervalli")
        self.fields["ripeti_ogni_intervallo"].label = f"Ripeti ogni ({unit_label})"

    def clean(self):
        cleaned_data = super().clean()

        intera_giornata = cleaned_data.get("intera_giornata")
        data_inizio = cleaned_data.get("data_inizio")
        data_fine = cleaned_data.get("data_fine")
        ora_inizio = cleaned_data.get("ora_inizio")
        durata_minuti = cleaned_data.get("durata_minuti")
        ripetizione = cleaned_data.get("ripetizione") or EventoCalendario.RIPETIZIONE_NESSUNA
        intervallo = cleaned_data.get("ripeti_ogni_intervallo")
        numero_occorrenze = cleaned_data.get("ripetizione_numero_occorrenze")
        fine_serie = cleaned_data.get("ripetizione_fino_al")

        if data_inizio and not data_fine:
            cleaned_data["data_fine"] = data_inizio
            data_fine = data_inizio

        if intera_giornata:
            cleaned_data["ora_inizio"] = None
            cleaned_data["ora_fine"] = None
        else:
            if durata_minuti:
                if not data_inizio or not ora_inizio:
                    self.add_error(
                        "durata_minuti",
                        "Per usare la durata devi indicare almeno data e ora di inizio.",
                    )
                    return cleaned_data

                fine_dt = datetime.combine(data_inizio, ora_inizio) + timedelta(minutes=durata_minuti)
                cleaned_data["data_fine"] = fine_dt.date()
                cleaned_data["ora_fine"] = fine_dt.time().replace(microsecond=0)

        if ripetizione == EventoCalendario.RIPETIZIONE_NESSUNA:
            cleaned_data["ripeti_ogni_intervallo"] = 1
            cleaned_data["ripetizione_numero_occorrenze"] = None
            cleaned_data["ripetizione_fino_al"] = None
            return cleaned_data

        if ripetizione not in {
            EventoCalendario.RIPETIZIONE_GIORNALIERA,
            EventoCalendario.RIPETIZIONE_GIORNI_FERIALI,
            EventoCalendario.RIPETIZIONE_SETTIMANALE,
            EventoCalendario.RIPETIZIONE_MENSILE,
            EventoCalendario.RIPETIZIONE_ANNUALE,
        }:
            self.add_error("ripetizione", "La ripetizione selezionata non e supportata.")
            return cleaned_data

        if ripetizione == EventoCalendario.RIPETIZIONE_GIORNI_FERIALI:
            cleaned_data["ripeti_ogni_intervallo"] = 1
        elif not intervallo:
            cleaned_data["ripeti_ogni_intervallo"] = 1

        if bool(numero_occorrenze) == bool(fine_serie):
            error_message = "Indica solo uno tra numero occorrenze e data finale della serie."
            self.add_error("ripetizione_numero_occorrenze", error_message)
            self.add_error("ripetizione_fino_al", error_message)

        if numero_occorrenze and numero_occorrenze < 2:
            self.add_error("ripetizione_numero_occorrenze", "Inserisci almeno 2 occorrenze totali.")

        if fine_serie and data_inizio and fine_serie < data_inizio:
            self.add_error("ripetizione_fino_al", "La data finale della serie deve essere uguale o successiva alla data iniziale.")

        return cleaned_data


class EventoCalendarioQuickCreateForm(forms.ModelForm):
    durata_minuti = forms.IntegerField(
        required=False,
        min_value=15,
        max_value=1440,
        initial=60,
    )

    class Meta:
        model = EventoCalendario
        fields = [
            "titolo",
            "categoria_evento",
            "data_inizio",
            "data_fine",
            "ora_inizio",
            "intera_giornata",
            "luogo",
            "descrizione",
            "visibile",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["categoria_evento"].queryset = CategoriaCalendario.objects.filter(attiva=True).order_by(
            "ordine",
            "nome",
        )
        self.fields["visibile"].initial = True
        self.fields["intera_giornata"].initial = True

    def clean(self):
        cleaned_data = super().clean()

        intera_giornata = cleaned_data.get("intera_giornata")
        data_inizio = cleaned_data.get("data_inizio")
        data_fine = cleaned_data.get("data_fine") or data_inizio
        ora_inizio = cleaned_data.get("ora_inizio")
        durata_minuti = cleaned_data.get("durata_minuti") or 60

        cleaned_data["data_fine"] = data_fine

        if data_fine and data_inizio and data_fine < data_inizio:
            self.add_error("data_fine", "La data di fine non puo essere precedente alla data iniziale.")
            return cleaned_data

        if intera_giornata:
            cleaned_data["ora_inizio"] = None
            cleaned_data["ora_fine"] = None
            return cleaned_data

        if not ora_inizio:
            self.add_error("ora_inizio", "Inserisci un orario di inizio.")
            return cleaned_data

        if not data_inizio:
            self.add_error("data_inizio", "Inserisci la data dell'evento.")
            return cleaned_data

        fine_dt = datetime.combine(data_inizio, ora_inizio) + timedelta(minutes=durata_minuti)
        cleaned_data["data_fine"] = fine_dt.date()
        cleaned_data["ora_fine"] = fine_dt.time().replace(microsecond=0)

        return cleaned_data

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.data_fine = self.cleaned_data["data_fine"]
        instance.ora_fine = self.cleaned_data.get("ora_fine")
        instance.attivo = True

        if self.cleaned_data.get("intera_giornata"):
            instance.ora_inizio = None
            instance.ora_fine = None

        if commit:
            instance.save()
        return instance
