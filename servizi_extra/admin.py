from django.contrib import admin

from servizi_extra.models import (
    ServizioExtra,
    TariffaServizioExtra,
    TariffaServizioExtraRata,
    IscrizioneServizioExtra,
    RataServizioExtra,
)


class TariffaServizioExtraRataInline(admin.TabularInline):
    model = TariffaServizioExtraRata
    extra = 0
    fields = ("numero_rata", "descrizione", "importo", "data_scadenza")


@admin.register(ServizioExtra)
class ServizioExtraAdmin(admin.ModelAdmin):
    list_display = ("nome_servizio", "anno_scolastico", "ordine", "attiva")
    list_filter = ("anno_scolastico", "attiva")
    search_fields = ("nome_servizio", "descrizione", "note")


@admin.register(TariffaServizioExtra)
class TariffaServizioExtraAdmin(admin.ModelAdmin):
    list_display = ("nome_tariffa", "servizio", "rateizzata", "attiva")
    list_filter = ("servizio__anno_scolastico", "rateizzata", "attiva")
    search_fields = ("nome_tariffa", "servizio__nome_servizio", "note")
    inlines = [TariffaServizioExtraRataInline]


@admin.register(IscrizioneServizioExtra)
class IscrizioneServizioExtraAdmin(admin.ModelAdmin):
    list_display = ("studente", "servizio", "tariffa", "data_iscrizione", "attiva")
    list_filter = ("servizio__anno_scolastico", "servizio", "attiva")
    search_fields = ("studente__cognome", "studente__nome", "servizio__nome_servizio", "tariffa__nome_tariffa")


@admin.register(RataServizioExtra)
class RataServizioExtraAdmin(admin.ModelAdmin):
    list_display = ("iscrizione", "numero_rata", "data_scadenza", "importo_dovuto", "pagata", "importo_pagato")
    list_filter = ("pagata", "iscrizione__servizio__anno_scolastico", "iscrizione__servizio")
    search_fields = ("iscrizione__studente__cognome", "iscrizione__studente__nome", "descrizione", "metodo_pagamento")

