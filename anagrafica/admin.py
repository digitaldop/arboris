from django.contrib import admin
from .models import (
    Regione,
    Provincia,
    Citta,
    CAP,
    StatoRelazioneFamiglia,
    RelazioneFamiliare,
    TipoDocumento,
    Famiglia,
    Familiare,
    Studente,
    Indirizzo,
    Documento,
)

################### INIZIO DEFINIZIONE DEGLI INLINE ###################

'''class IndirizzoFamigliaInline(admin.TabularInline):
    model = Indirizzo
    fk_name = "famiglia"
    extra = 0
    fields = ("indirizzo", "cap", "citta", "provincia", "nazione", "note")'''


class DocumentoFamigliaInline(admin.TabularInline):
    model = Documento
    fk_name = "famiglia"
    extra = 0
    fields = ("tipo_documento", "descrizione", "file", "scadenza", "visibile", "note")


class FamiliareInline(admin.TabularInline):
    model = Familiare
    extra = 0
    fields = (
        "cognome",
        "nome",
        "relazione_familiare",
        "telefono",
        "email",
        "convivente",
        "referente_principale",
        "abilitato_scambio_retta",
        "attivo",
    )


class StudenteInline(admin.TabularInline):
    model = Studente
    extra = 0
    fields = (
        "cognome",
        "nome",
        "data_nascita",
        "codice_fiscale",
        "attivo",
    )


'''class IndirizzoFamiliareInline(admin.TabularInline):
    model = Indirizzo
    fk_name = "familiare"
    extra = 0
    fields = ("indirizzo", "cap", "citta", "provincia", "nazione", "note")'''


class DocumentoFamiliareInline(admin.TabularInline):
    model = Documento
    fk_name = "familiare"
    extra = 0
    fields = ("tipo_documento", "descrizione", "file", "scadenza", "visibile", "note")


'''class IndirizzoStudenteInline(admin.TabularInline):
    model = Indirizzo
    fk_name = "studente"
    extra = 0
    fields = ("indirizzo", "cap", "citta", "provincia", "nazione", "note")'''


class DocumentoStudenteInline(admin.TabularInline):
    model = Documento
    fk_name = "studente"
    extra = 0
    fields = ("tipo_documento", "descrizione", "file", "scadenza", "visibile", "note")


################### FINE DEFINIZIONE DEGLI INLINE ###################

#INIZIO ADMIN DEGLI INDIRIZZI
@admin.register(Regione)
class RegioneAdmin(admin.ModelAdmin):
    list_display = ("nome", "ordine", "attiva")
    list_filter = ("attiva",)
    search_fields = ("nome",)
    ordering = ("ordine", "nome")


@admin.register(Provincia)
class ProvinciaAdmin(admin.ModelAdmin):
    list_display = ("sigla", "nome", "regione", "ordine", "attiva")
    list_editable = ("ordine", "attiva")
    search_fields = ("sigla", "nome")
    ordering = ("ordine", "sigla")


@admin.register(Citta)
class CittaAdmin(admin.ModelAdmin):
    list_display = ("nome", "provincia", "codice_catastale", "ordine", "attiva")
    list_filter = ("provincia__regione", "provincia", "attiva")
    search_fields = ("nome", "provincia__nome", "provincia__sigla", "codice_catastale", "codice_istat")
    ordering = ("ordine", "nome")


@admin.register(CAP)
class CAPAdmin(admin.ModelAdmin):
    list_display = ("codice", "citta", "ordine", "attivo")
    list_filter = ("citta__provincia__regione", "citta__provincia", "attivo")
    search_fields = ("codice", "citta__nome", "citta__provincia__sigla")
    ordering = ("ordine", "codice")


#Modulo per gli indirizzi, visualizzabile dalla Home dell'Admin, per poter gestire gli indirizzi in modo centralizzato
@admin.register(Indirizzo)
class IndirizzoAdmin(admin.ModelAdmin):
    list_display = ("via", "numero_civico", "citta", "cap", "provincia", "regione")
    list_filter = ("regione", "provincia")
    search_fields = ("via", "numero_civico", "cap", "citta__nome")
    ordering = ("via", "numero_civico")

#FINE ADMIN DEGLI INDIRIZZI


#INIZIO ADMIN DELLE FAMIGLIE

@admin.register(Famiglia)
class FamigliaAdmin(admin.ModelAdmin):
    list_display = (
        "cognome_famiglia",
        "stato_relazione_famiglia",
        "indirizzo_principale",
        "attiva",
        "data_creazione",
    )
    list_filter = ("stato_relazione_famiglia", "attiva")
    search_fields = ("cognome_famiglia", "note")
    ordering = ("cognome_famiglia",)
    inlines = [
        FamiliareInline,
        StudenteInline,
        DocumentoFamigliaInline,
    ]

    fieldsets = (
        (
            "Dati principali",
            {
                "fields": (
                    "cognome_famiglia",
                    "stato_relazione_famiglia",
                    "indirizzo_principale",
                    "attiva",
                )
            },
        ),
        (
            "Sistema",
            {
                "fields": (
                    "data_creazione",
                    "data_aggiornamento",
                )
            },
        ),
        (
            "Note",
            {
                "fields": ("note",),
                "classes": ("collapse",),
            },
        ),
    )

    readonly_fields = ("data_creazione", "data_aggiornamento")

    autocomplete_fields = ("indirizzo_principale",)


@admin.register(StatoRelazioneFamiglia)
class StatoRelazioneFamigliaAdmin(admin.ModelAdmin):
    list_display = ("stato", "ordine", "attivo")
    list_editable = ("ordine", "attivo")
    search_fields = ("stato",)
    ordering = ("ordine", "stato")

#FINE ADMIN DELLE FAMIGLIE


@admin.register(Familiare)
class FamiliareAdmin(admin.ModelAdmin):
    list_display = (
        "cognome",
        "nome",
        "famiglia",
        "relazione_familiare",
        "telefono",
        "email",
        "indirizzo",
        "referente_principale",
        "abilitato_scambio_retta",
        "attivo",
    )
    list_filter = (
        "relazione_familiare",
        "convivente",
        "referente_principale",
        "abilitato_scambio_retta",
        "attivo",
    )
    search_fields = (
        "cognome",
        "nome",
        "telefono",
        "email",
        "codice_fiscale",
        "luogo_nascita__nome",
        "famiglia__cognome_famiglia",
    )
    ordering = ("cognome", "nome")
    inlines = [DocumentoFamiliareInline]

    fieldsets = (
        (
            "Dati principali",
            {
                "fields": (
                    "famiglia",
                    "relazione_familiare",
                    "cognome",
                    "nome",
                    "attivo",
                )
            },
        ),
        (
            "Contatti",
            {
                "fields": (
                    "telefono",
                    "email",
                    "indirizzo",
                )
            },
        ),
        (
            "Dati anagrafici",
            {
                "fields": (
                    "codice_fiscale",
                    "data_nascita",
                    "sesso",
                    "luogo_nascita",
                )
            },
        ),
        (
            "Ruolo nella famiglia",
            {
                "fields": (
                    "convivente",
                    "referente_principale",
                    "abilitato_scambio_retta",
                )
            },
        ),
        (
            "Note",
            {
                "fields": ("note",),
                "classes": ("collapse",),
            },
        ),
    )

    #Questa funzione serve per visualizzare l'indirizzo effettivo del familiare, che può essere diverso da quello principale della famiglia, direttamente nella lista dei familiari nell'Admin
    @admin.display(description="Indirizzo effettivo")
    def indirizzo_effettivo_admin(self, obj):
        indirizzo = obj.indirizzo_effettivo
        return str(indirizzo) if indirizzo else "-"
    
    autocomplete_fields = ("famiglia", "indirizzo", "luogo_nascita")


@admin.register(Studente)
class StudenteAdmin(admin.ModelAdmin):
    list_display = (
        "cognome",
        "nome",
        "famiglia",
        "indirizzo",
        "data_nascita",
        "attivo",
    )
    list_filter = ("attivo",)
    search_fields = (
        "cognome",
        "nome",
        "codice_fiscale",
        "luogo_nascita__nome",
        "famiglia__cognome_famiglia",
    )
    ordering = ("cognome", "nome")
    inlines = [DocumentoStudenteInline]

    fieldsets = (
        (
            "Dati principali",
            {
                "fields": (
                    "famiglia",
                    "cognome",
                    "nome",
                    "indirizzo",
                    "attivo",
                )
            },
        ),
        (
            "Dati anagrafici",
            {
                "fields": (
                    "data_nascita",
                    "sesso",
                    "luogo_nascita",
                    "codice_fiscale",
                )
            },
        ),
        (
            "Note",
            {
                "fields": ("note",),
                "classes": ("collapse",),
            },
        ),
    )

    #Questa funzione serve per visualizzare l'indirizzo effettivo dello studente, che può essere diverso da quello principale della famiglia, direttamente nella lista degli studenti nell'Admin
    @admin.display(description="Indirizzo effettivo")
    def indirizzo_effettivo_admin(self, obj):
        indirizzo = obj.indirizzo_effettivo
        return str(indirizzo) if indirizzo else "-"
    
    autocomplete_fields = ("famiglia", "indirizzo", "luogo_nascita")

#Visualizzazione del modulo indirizzo dalla Home dell'Admin
'''@admin.register(Indirizzo)
class IndirizzoAdmin(admin.ModelAdmin):
    list_display = ("indirizzo", "cap", "citta", "provincia", "nazione")
    search_fields = ("indirizzo", "cap", "citta", "provincia", "nazione")'''

#Visualizzazione del modulo documento dalla Home dell'Admin
'''@admin.register(Documento)
class DocumentoAdmin(admin.ModelAdmin):
    list_display = (
        "tipo_documento",
        "descrizione",
        "data_caricamento",
        "scadenza",
        "visibile",
    )
    list_filter = ("tipo_documento", "visibile", "data_caricamento")
    search_fields = ("descrizione", "note")
    readonly_fields = ("data_caricamento",)'''








@admin.register(RelazioneFamiliare)
class RelazioneFamiliareAdmin(admin.ModelAdmin):
    list_display = ("relazione", "ordine")
    list_editable = ("ordine",)
    search_fields = ("relazione",)
    ordering = ("ordine", "relazione")


@admin.register(TipoDocumento)
class TipoDocumentoAdmin(admin.ModelAdmin):
    list_display = ("tipo_documento", "ordine", "attivo")
    list_editable = ("ordine", "attivo")
    search_fields = ("tipo_documento",)
    ordering = ("ordine", "tipo_documento")
