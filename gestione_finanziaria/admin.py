from django.contrib import admin

from .models import (
    CategoriaFinanziaria,
    ConnessioneBancaria,
    ContoBancario,
    MovimentoFinanziario,
    ProviderBancario,
    RegolaCategorizzazione,
    SaldoConto,
    SincronizzazioneLog,
)


@admin.register(CategoriaFinanziaria)
class CategoriaFinanziariaAdmin(admin.ModelAdmin):
    list_display = ("nome", "tipo", "parent", "ordine", "attiva")
    list_filter = ("tipo", "attiva")
    search_fields = ("nome",)
    autocomplete_fields = ("parent",)


@admin.register(ProviderBancario)
class ProviderBancarioAdmin(admin.ModelAdmin):
    list_display = ("nome", "tipo", "attivo")
    list_filter = ("tipo", "attivo")
    search_fields = ("nome",)


@admin.register(ConnessioneBancaria)
class ConnessioneBancariaAdmin(admin.ModelAdmin):
    list_display = ("etichetta", "provider", "stato", "consenso_scadenza", "ultimo_refresh_at")
    list_filter = ("stato", "provider")
    search_fields = ("etichetta", "external_institution_id", "external_connection_id")
    readonly_fields = ("access_token_cifrato", "refresh_token_cifrato")


@admin.register(ContoBancario)
class ContoBancarioAdmin(admin.ModelAdmin):
    list_display = (
        "nome_conto",
        "banca",
        "iban",
        "provider",
        "connessione",
        "saldo_corrente",
        "saldo_corrente_aggiornato_al",
        "attivo",
    )
    list_filter = ("provider", "attivo")
    search_fields = ("nome_conto", "iban", "intestatario", "banca")


@admin.register(SaldoConto)
class SaldoContoAdmin(admin.ModelAdmin):
    list_display = ("conto", "data_riferimento", "saldo_contabile", "saldo_disponibile", "fonte")
    list_filter = ("fonte", "conto")
    date_hierarchy = "data_riferimento"


@admin.register(RegolaCategorizzazione)
class RegolaCategorizzazioneAdmin(admin.ModelAdmin):
    list_display = (
        "nome",
        "priorita",
        "condizione_tipo",
        "pattern",
        "categoria_da_assegnare",
        "attiva",
        "volte_applicata",
    )
    list_filter = ("attiva", "condizione_tipo")
    search_fields = ("nome", "pattern")
    autocomplete_fields = ("categoria_da_assegnare",)


@admin.register(MovimentoFinanziario)
class MovimentoFinanziarioAdmin(admin.ModelAdmin):
    list_display = (
        "data_contabile",
        "conto",
        "origine",
        "importo",
        "categoria",
        "stato_riconciliazione",
        "controparte",
    )
    list_filter = ("origine", "stato_riconciliazione", "conto", "categoria")
    search_fields = ("descrizione", "controparte", "iban_controparte", "provider_transaction_id")
    date_hierarchy = "data_contabile"
    autocomplete_fields = ("categoria",)
    readonly_fields = ("provider_transaction_id", "hash_deduplica")


@admin.register(SincronizzazioneLog)
class SincronizzazioneLogAdmin(admin.ModelAdmin):
    list_display = (
        "data_operazione",
        "tipo_operazione",
        "esito",
        "conto",
        "connessione",
        "movimenti_inseriti",
        "movimenti_aggiornati",
    )
    list_filter = ("tipo_operazione", "esito")
    date_hierarchy = "data_operazione"
