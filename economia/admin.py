from django.contrib import admin

from .models import (
    MetodoPagamento,
    TipoMovimentoCredito,
    StatoIscrizione,
    CondizioneIscrizione,
    TariffaCondizioneIscrizione,
    Agevolazione,
    Iscrizione,
    RataIscrizione,
    MovimentoCreditoRetta,
    TariffaScambioRetta,
    ScambioRetta,
    PrestazioneScambioRetta,
)


@admin.register(MetodoPagamento)
class MetodoPagamentoAdmin(admin.ModelAdmin):
    list_display = ("metodo_pagamento", "attivo")
    list_filter = ("attivo",)
    search_fields = ("metodo_pagamento",)


@admin.register(TipoMovimentoCredito)
class TipoMovimentoCreditoAdmin(admin.ModelAdmin):
    list_display = ("tipo_movimento_credito", "attivo")
    list_filter = ("attivo",)
    search_fields = ("tipo_movimento_credito",)


@admin.register(StatoIscrizione)
class StatoIscrizioneAdmin(admin.ModelAdmin):
    list_display = ("stato_iscrizione", "ordine", "attiva")
    list_filter = ("attiva",)
    search_fields = ("stato_iscrizione",)


@admin.register(CondizioneIscrizione)
class CondizioneIscrizioneAdmin(admin.ModelAdmin):
    list_display = (
        "nome_condizione_iscrizione",
        "anno_scolastico",
        "numero_mensilita_default",
        "mese_prima_retta",
        "giorno_scadenza_rate",
        "riduzione_speciale_ammessa",
        "attiva",
    )
    list_filter = ("anno_scolastico", "riduzione_speciale_ammessa", "attiva")
    search_fields = ("nome_condizione_iscrizione",)


@admin.register(TariffaCondizioneIscrizione)
class TariffaCondizioneIscrizioneAdmin(admin.ModelAdmin):
    list_display = ("condizione_iscrizione", "ordine_figlio_da", "ordine_figlio_a", "retta_annuale", "preiscrizione", "attiva")
    list_filter = ("condizione_iscrizione__anno_scolastico", "attiva")
    search_fields = ("condizione_iscrizione__nome_condizione_iscrizione",)


@admin.register(Agevolazione)
class AgevolazioneAdmin(admin.ModelAdmin):
    list_display = ("nome_agevolazione", "importo_annuale_agevolazione", "attiva")
    list_filter = ("attiva",)
    search_fields = ("nome_agevolazione",)


@admin.register(Iscrizione)
class IscrizioneAdmin(admin.ModelAdmin):
    list_display = (
        "studente",
        "anno_scolastico",
        "classe",
        "gruppo_classe",
        "stato_iscrizione",
        "condizione_iscrizione",
        "agevolazione",
        "non_pagante",
        "riduzione_speciale",
        "attiva",
    )
    list_filter = ("anno_scolastico", "classe", "gruppo_classe", "stato_iscrizione", "non_pagante", "riduzione_speciale", "attiva")
    search_fields = ("studente__cognome", "studente__nome")


@admin.register(RataIscrizione)
class RataIscrizioneAdmin(admin.ModelAdmin):
    list_display = ("iscrizione", "tipo_rata", "numero_rata", "mese_riferimento", "anno_riferimento", "importo_dovuto", "pagata")
    list_filter = ("tipo_rata", "pagata", "anno_riferimento", "mese_riferimento")
    search_fields = ("iscrizione__studente__cognome", "iscrizione__studente__nome", "descrizione")


@admin.register(MovimentoCreditoRetta)
class MovimentoCreditoRettaAdmin(admin.ModelAdmin):
    list_display = ("studente", "scambio_retta", "data_movimento", "tipo_movimento_credito", "importo", "saldo_progressivo")
    list_filter = ("tipo_movimento_credito",)
    search_fields = ("studente__cognome", "studente__nome", "descrizione")


@admin.register(TariffaScambioRetta)
class TariffaScambioRettaAdmin(admin.ModelAdmin):
    list_display = ("definizione", "valore_orario")
    search_fields = ("definizione",)


@admin.register(ScambioRetta)
class ScambioRettaAdmin(admin.ModelAdmin):
    list_display = (
        "familiare",
        "studente",
        "anno_scolastico",
        "mese_riferimento",
        "ore_lavorate",
        "importo_maturato",
        "approvata",
        "contabilizzata",
    )
    list_filter = ("anno_scolastico", "mese_riferimento", "approvata", "contabilizzata")
    search_fields = (
        "familiare__cognome",
        "familiare__nome",
        "studente__cognome",
        "studente__nome",
        "descrizione",
    )


@admin.register(PrestazioneScambioRetta)
class PrestazioneScambioRettaAdmin(admin.ModelAdmin):
    list_display = (
        "familiare",
        "studente",
        "anno_scolastico",
        "data",
        "ora_ingresso",
        "ora_uscita",
        "ore_lavorate",
        "importo_maturato",
    )
    list_filter = ("anno_scolastico", "data", "tariffa_scambio_retta")
    search_fields = (
        "familiare__cognome",
        "familiare__nome",
        "studente__cognome",
        "studente__nome",
        "descrizione",
    )
