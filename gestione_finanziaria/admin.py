from django.contrib import admin

from .models import (
    CategoriaSpesa,
    CategoriaFinanziaria,
    ConnessioneBancaria,
    ContoBancario,
    DocumentoFornitore,
    FattureInCloudConnessione,
    FattureInCloudSyncLog,
    Fornitore,
    MovimentoFinanziario,
    NotificaFinanziaria,
    NotificaFinanziariaLettura,
    PagamentoFornitore,
    ProviderBancario,
    RegolaCategorizzazione,
    SaldoConto,
    ScadenzaPagamentoFornitore,
    SincronizzazioneLog,
)


@admin.register(CategoriaFinanziaria)
class CategoriaFinanziariaAdmin(admin.ModelAdmin):
    list_display = ("nome", "tipo", "parent", "ordine", "attiva")
    list_filter = ("tipo", "attiva")
    search_fields = ("nome",)
    autocomplete_fields = ("parent",)


@admin.register(CategoriaSpesa)
class CategoriaSpesaAdmin(admin.ModelAdmin):
    list_display = ("nome", "ordine", "attiva")
    list_filter = ("attiva",)
    search_fields = ("nome", "descrizione")


@admin.register(Fornitore)
class FornitoreAdmin(admin.ModelAdmin):
    list_display = ("denominazione", "tipo_soggetto", "categoria_spesa", "email", "telefono", "attivo")
    list_filter = ("tipo_soggetto", "categoria_spesa", "attivo")
    search_fields = ("denominazione", "codice_fiscale", "partita_iva", "email", "pec", "referente")
    autocomplete_fields = ("categoria_spesa",)


class ScadenzaPagamentoFornitoreInline(admin.TabularInline):
    model = ScadenzaPagamentoFornitore
    extra = 0
    autocomplete_fields = ("conto_bancario", "movimento_finanziario")


class PagamentoFornitoreInline(admin.TabularInline):
    model = PagamentoFornitore
    extra = 0
    autocomplete_fields = ("movimento_finanziario", "conto_bancario", "creato_da")


@admin.register(DocumentoFornitore)
class DocumentoFornitoreAdmin(admin.ModelAdmin):
    list_display = ("numero_documento", "tipo_documento", "fornitore", "data_documento", "totale", "stato", "origine")
    list_filter = ("tipo_documento", "stato", "categoria_spesa", "origine")
    search_fields = ("numero_documento", "descrizione", "fornitore__denominazione", "external_id")
    date_hierarchy = "data_documento"
    autocomplete_fields = ("fornitore", "categoria_spesa")
    readonly_fields = ("external_payload", "external_source", "external_id", "importato_at", "external_updated_at")
    inlines = [ScadenzaPagamentoFornitoreInline]


@admin.register(ScadenzaPagamentoFornitore)
class ScadenzaPagamentoFornitoreAdmin(admin.ModelAdmin):
    list_display = ("documento", "data_scadenza", "importo_previsto", "importo_pagato", "stato")
    list_filter = ("stato", "data_scadenza")
    search_fields = ("documento__numero_documento", "documento__fornitore__denominazione")
    date_hierarchy = "data_scadenza"
    autocomplete_fields = ("documento", "conto_bancario", "movimento_finanziario")
    inlines = [PagamentoFornitoreInline]


@admin.register(PagamentoFornitore)
class PagamentoFornitoreAdmin(admin.ModelAdmin):
    list_display = ("scadenza", "data_pagamento", "importo", "metodo", "movimento_finanziario")
    list_filter = ("metodo", "data_pagamento")
    search_fields = ("scadenza__documento__numero_documento", "scadenza__documento__fornitore__denominazione")
    date_hierarchy = "data_pagamento"
    autocomplete_fields = ("scadenza", "movimento_finanziario", "conto_bancario", "creato_da")


@admin.register(FattureInCloudConnessione)
class FattureInCloudConnessioneAdmin(admin.ModelAdmin):
    list_display = ("nome", "company_id", "stato", "attiva", "ultimo_sync_at", "ultimo_esito")
    list_filter = ("stato", "attiva")
    search_fields = ("nome", "company_id", "client_id")
    readonly_fields = (
        "client_secret_cifrato",
        "access_token_cifrato",
        "refresh_token_cifrato",
        "oauth_state",
        "webhook_key",
    )


@admin.register(FattureInCloudSyncLog)
class FattureInCloudSyncLogAdmin(admin.ModelAdmin):
    list_display = (
        "data_operazione",
        "connessione",
        "tipo_operazione",
        "esito",
        "documenti_creati",
        "documenti_aggiornati",
        "notifiche_create",
    )
    list_filter = ("tipo_operazione", "esito")
    date_hierarchy = "data_operazione"


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


class NotificaFinanziariaLetturaInline(admin.TabularInline):
    model = NotificaFinanziariaLettura
    extra = 0
    autocomplete_fields = ("user",)


@admin.register(NotificaFinanziaria)
class NotificaFinanziariaAdmin(admin.ModelAdmin):
    list_display = ("titolo", "tipo", "livello", "richiede_gestione", "data_creazione")
    list_filter = ("tipo", "livello", "richiede_gestione")
    search_fields = ("titolo", "messaggio", "chiave_deduplica")
    date_hierarchy = "data_creazione"
    autocomplete_fields = ("documento", "scadenza", "movimento_finanziario")
    inlines = [NotificaFinanziariaLetturaInline]
