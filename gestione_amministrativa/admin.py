from django.contrib import admin

from .models import (
    BustaPagaDipendente,
    ContrattoDipendente,
    Dipendente,
    DocumentoDipendente,
    ParametroCalcoloStipendio,
    SimulazioneCostoDipendente,
    TipoContrattoDipendente,
    VoceBustaPaga,
)


class ContrattoDipendenteInline(admin.TabularInline):
    model = ContrattoDipendente
    extra = 0
    autocomplete_fields = ("tipo_contratto",)
    fields = (
        "tipo_contratto",
        "parametro_calcolo",
        "data_inizio",
        "data_fine",
        "livello",
        "mansione",
        "retribuzione_lorda_mensile",
        "tariffa_oraria",
        "mensilita_annue",
        "attivo",
    )


class SimulazioneCostoDipendenteInline(admin.TabularInline):
    model = SimulazioneCostoDipendente
    extra = 0
    fields = (
        "titolo",
        "valido_dal",
        "valido_al",
        "netto_mensile",
        "lordo_mensile",
        "costo_azienda_mensile",
        "attiva",
    )


@admin.register(Dipendente)
class DipendenteAdmin(admin.ModelAdmin):
    list_display = (
        "cognome",
        "nome",
        "codice_dipendente",
        "codice_fiscale",
        "sesso",
        "stato",
        "data_assunzione",
        "data_cessazione",
    )
    list_filter = ("stato",)
    search_fields = ("nome", "cognome", "codice_dipendente", "codice_fiscale", "email")
    autocomplete_fields = ("indirizzo",)
    inlines = [ContrattoDipendenteInline]


@admin.register(TipoContrattoDipendente)
class TipoContrattoDipendenteAdmin(admin.ModelAdmin):
    list_display = ("nome", "ordine", "attivo")
    list_filter = ("attivo",)
    search_fields = ("nome",)


@admin.register(ContrattoDipendente)
class ContrattoDipendenteAdmin(admin.ModelAdmin):
    list_display = (
        "dipendente",
        "tipo_contratto",
        "data_inizio",
        "data_fine",
        "livello",
        "retribuzione_lorda_mensile",
        "tariffa_oraria",
        "mensilita_annue",
        "attivo",
    )
    list_filter = ("tipo_contratto", "regime_orario", "attivo")
    search_fields = ("dipendente__nome", "dipendente__cognome", "ccnl", "livello", "mansione")
    autocomplete_fields = ("dipendente", "tipo_contratto", "parametro_calcolo")
    date_hierarchy = "data_inizio"
    inlines = [SimulazioneCostoDipendenteInline]


@admin.register(SimulazioneCostoDipendente)
class SimulazioneCostoDipendenteAdmin(admin.ModelAdmin):
    list_display = (
        "contratto",
        "valido_dal",
        "valido_al",
        "netto_mensile",
        "lordo_mensile",
        "costo_azienda_mensile",
        "attiva",
    )
    list_filter = ("attiva", "valido_dal")
    search_fields = (
        "titolo",
        "contratto__dipendente__nome",
        "contratto__dipendente__cognome",
        "contratto__dipendente__codice_fiscale",
        "livello",
        "qualifica",
    )
    autocomplete_fields = ("contratto",)
    date_hierarchy = "valido_dal"


@admin.register(ParametroCalcoloStipendio)
class ParametroCalcoloStipendioAdmin(admin.ModelAdmin):
    list_display = (
        "nome",
        "valido_dal",
        "valido_al",
        "aliquota_contributi_datore",
        "aliquota_contributi_dipendente",
        "aliquota_tfr",
        "attivo",
    )
    list_filter = ("attivo",)
    search_fields = ("nome",)


class VoceBustaPagaInline(admin.TabularInline):
    model = VoceBustaPaga
    extra = 0
    fields = ("scenario", "tipo_voce", "codice", "descrizione", "importo", "ordine")


@admin.register(BustaPagaDipendente)
class BustaPagaDipendenteAdmin(admin.ModelAdmin):
    list_display = (
        "dipendente",
        "anno",
        "mese",
        "stato",
        "lordo_previsto",
        "lordo_effettivo",
        "costo_azienda_previsto",
        "costo_azienda_effettivo",
    )
    list_filter = ("stato", "anno", "mese")
    search_fields = ("dipendente__nome", "dipendente__cognome", "dipendente__codice_fiscale")
    autocomplete_fields = ("dipendente", "contratto", "movimento_pagamento")
    inlines = [VoceBustaPagaInline]


@admin.register(VoceBustaPaga)
class VoceBustaPagaAdmin(admin.ModelAdmin):
    list_display = ("busta_paga", "scenario", "tipo_voce", "codice", "descrizione", "importo")
    list_filter = ("scenario", "tipo_voce")
    search_fields = ("descrizione", "codice", "busta_paga__dipendente__nome", "busta_paga__dipendente__cognome")
    autocomplete_fields = ("busta_paga",)


@admin.register(DocumentoDipendente)
class DocumentoDipendenteAdmin(admin.ModelAdmin):
    list_display = ("dipendente", "tipo_documento", "titolo", "data_documento", "data_creazione")
    list_filter = ("tipo_documento",)
    search_fields = ("dipendente__nome", "dipendente__cognome", "titolo")
    autocomplete_fields = ("dipendente", "busta_paga")
