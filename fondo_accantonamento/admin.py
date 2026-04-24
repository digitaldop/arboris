from django.contrib import admin

from .models import (
    MovimentoFondo,
    PianoAccantonamento,
    RegolaScontoAgevolazione,
    ScadenzaVersamento,
)


@admin.register(PianoAccantonamento)
class PianoAccantonamentoAdmin(admin.ModelAdmin):
    list_display = ("nome", "sempre_attivo", "anno_scolastico", "modalita", "attivo")
    list_filter = ("sempre_attivo", "attivo", "modalita", "anno_scolastico")
    search_fields = ("nome", "descrizione")


@admin.register(MovimentoFondo)
class MovimentoFondoAdmin(admin.ModelAdmin):
    list_display = ("piano", "tipo", "data", "importo")
    list_filter = ("tipo",)
    raw_id_fields = ("piano", "rata_iscrizione", "scadenza_versamento")


@admin.register(ScadenzaVersamento)
class ScadenzaVersamentoAdmin(admin.ModelAdmin):
    list_display = ("piano", "data_scadenza", "importo_previsto", "stato")
    list_filter = ("stato",)
    raw_id_fields = ("piano", "movimento_versamento")


@admin.register(RegolaScontoAgevolazione)
class RegolaScontoAgevolazioneAdmin(admin.ModelAdmin):
    list_display = ("agevolazione", "piano", "numero_mensilita", "attiva")
    list_filter = ("attiva", "piano__anno_scolastico")
    raw_id_fields = ("agevolazione", "piano")
