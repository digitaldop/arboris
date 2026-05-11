from django.contrib import admin

from .models import (
    BustaPagaDipendente,
    ContrattoDipendente,
    DatoPayrollUfficiale,
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
        "ruolo_aziendale",
        "codice_fiscale",
        "classe_principale",
        "gruppo_classe_principale",
        "materia",
        "mansione",
        "sesso",
        "stato",
    )
    list_filter = ("ruolo_aziendale", "stato", "classe_principale", "gruppo_classe_principale", "materia")
    search_fields = (
        "persona_collegata__nome",
        "persona_collegata__cognome",
        "persona_collegata__codice_fiscale",
        "persona_collegata__email",
        "materia",
    )
    autocomplete_fields = ("persona_collegata", "classe_principale", "gruppo_classe_principale")
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
    search_fields = (
        "dipendente__persona_collegata__nome",
        "dipendente__persona_collegata__cognome",
        "ccnl",
        "livello",
        "mansione",
    )
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
        "contratto__dipendente__persona_collegata__nome",
        "contratto__dipendente__persona_collegata__cognome",
        "contratto__dipendente__persona_collegata__codice_fiscale",
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


@admin.register(DatoPayrollUfficiale)
class DatoPayrollUfficialeAdmin(admin.ModelAdmin):
    list_display = (
        "nome",
        "categoria",
        "codice",
        "anno",
        "valore_percentuale",
        "valore_importo",
        "ente",
        "attivo",
        "data_rilevazione",
    )
    list_filter = ("categoria", "anno", "attivo", "ente")
    search_fields = ("nome", "codice", "descrizione", "ente")
    readonly_fields = ("data_rilevazione",)


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
    search_fields = (
        "dipendente__persona_collegata__nome",
        "dipendente__persona_collegata__cognome",
        "dipendente__persona_collegata__codice_fiscale",
    )
    autocomplete_fields = ("dipendente", "contratto", "movimento_pagamento")
    inlines = [VoceBustaPagaInline]


@admin.register(VoceBustaPaga)
class VoceBustaPagaAdmin(admin.ModelAdmin):
    list_display = ("busta_paga", "scenario", "tipo_voce", "codice", "descrizione", "importo")
    list_filter = ("scenario", "tipo_voce")
    search_fields = (
        "descrizione",
        "codice",
        "busta_paga__dipendente__persona_collegata__nome",
        "busta_paga__dipendente__persona_collegata__cognome",
    )
    autocomplete_fields = ("busta_paga",)


@admin.register(DocumentoDipendente)
class DocumentoDipendenteAdmin(admin.ModelAdmin):
    list_display = ("dipendente", "tipo_documento", "titolo", "data_documento", "data_creazione")
    list_filter = ("tipo_documento",)
    search_fields = ("dipendente__persona_collegata__nome", "dipendente__persona_collegata__cognome", "titolo")
    autocomplete_fields = ("dipendente", "busta_paga")
