from django.contrib import admin
from .models import (
    Regione,
    Provincia,
    Citta,
    Nazione,
    CAP,
    RelazioneFamiliare,
    Persona,
    TipoDocumento,
    Familiare,
    Studente,
    StudenteFamiliare,
    Indirizzo,
    LabelIndirizzo,
    LabelTelefono,
    LabelEmail,
    AnagraficaIndirizzo,
    AnagraficaTelefono,
    AnagraficaEmail,
    Documento,
)

################### INIZIO DEFINIZIONE DEGLI INLINE ###################

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


class StudenteFamiliareInline(admin.TabularInline):
    model = StudenteFamiliare
    extra = 0
    autocomplete_fields = ("familiare", "relazione_familiare")
    fields = ("familiare", "relazione_familiare", "referente_principale", "convivente", "attivo")


class FamiliareStudenteInline(admin.TabularInline):
    model = StudenteFamiliare
    extra = 0
    autocomplete_fields = ("studente", "relazione_familiare")
    fields = ("studente", "relazione_familiare", "referente_principale", "convivente", "attivo")


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


@admin.register(Nazione)
class NazioneAdmin(admin.ModelAdmin):
    list_display = ("nome", "nome_nazionalita", "codice_iso2", "codice_iso3", "codice_belfiore", "ordine", "attiva")
    list_filter = ("attiva",)
    search_fields = ("nome", "nome_nazionalita", "codice_iso2", "codice_iso3", "codice_belfiore")
    ordering = ("ordine", "nome")


#Modulo per gli indirizzi, visualizzabile dalla Home dell'Admin, per poter gestire gli indirizzi in modo centralizzato
@admin.register(Indirizzo)
class IndirizzoAdmin(admin.ModelAdmin):
    list_display = ("via", "numero_civico", "citta", "cap", "provincia", "regione")
    list_filter = ("regione", "provincia")
    search_fields = ("via", "numero_civico", "cap", "citta__nome")
    ordering = ("via", "numero_civico")


@admin.register(LabelIndirizzo)
class LabelIndirizzoAdmin(admin.ModelAdmin):
    list_display = ("nome", "ordine", "attiva")
    list_editable = ("ordine", "attiva")
    search_fields = ("nome",)
    ordering = ("ordine", "nome")


@admin.register(LabelTelefono)
class LabelTelefonoAdmin(admin.ModelAdmin):
    list_display = ("nome", "ordine", "attiva")
    list_editable = ("ordine", "attiva")
    search_fields = ("nome",)
    ordering = ("ordine", "nome")


@admin.register(LabelEmail)
class LabelEmailAdmin(admin.ModelAdmin):
    list_display = ("nome", "ordine", "attiva")
    list_editable = ("ordine", "attiva")
    search_fields = ("nome",)
    ordering = ("ordine", "nome")


@admin.register(AnagraficaIndirizzo)
class AnagraficaIndirizzoAdmin(admin.ModelAdmin):
    list_display = ("content_object", "label", "indirizzo", "principale", "ordine")
    list_filter = ("label", "principale", "content_type")
    search_fields = ("indirizzo__via", "indirizzo__numero_civico", "indirizzo__citta__nome")
    autocomplete_fields = ("indirizzo", "label")
    ordering = ("content_type", "object_id", "ordine")


@admin.register(AnagraficaTelefono)
class AnagraficaTelefonoAdmin(admin.ModelAdmin):
    list_display = ("content_object", "label", "numero", "principale", "ordine")
    list_filter = ("label", "principale", "content_type")
    search_fields = ("numero",)
    autocomplete_fields = ("label",)
    ordering = ("content_type", "object_id", "ordine")


@admin.register(AnagraficaEmail)
class AnagraficaEmailAdmin(admin.ModelAdmin):
    list_display = ("content_object", "label", "email", "principale", "ordine")
    list_filter = ("label", "principale", "content_type")
    search_fields = ("email",)
    autocomplete_fields = ("label",)
    ordering = ("content_type", "object_id", "ordine")

#FINE ADMIN DEGLI INDIRIZZI


@admin.register(Persona)
class PersonaAdmin(admin.ModelAdmin):
    list_display = ("cognome", "nome", "codice_fiscale", "telefono", "email")
    search_fields = ("cognome", "nome", "codice_fiscale", "telefono", "email")
    ordering = ("cognome", "nome")


@admin.register(Familiare)
class FamiliareAdmin(admin.ModelAdmin):
    list_display = (
        "cognome",
        "nome",
        "relazione_familiare",
        "telefono",
        "email",
        "indirizzo",
        "referente_principale",
        "abilitato_scambio_retta",
    )
    list_filter = (
        "relazione_familiare",
        "convivente",
        "referente_principale",
        "abilitato_scambio_retta",
    )
    search_fields = (
        "persona__cognome",
        "persona__nome",
        "persona__telefono",
        "persona__email",
        "persona__codice_fiscale",
        "persona__luogo_nascita__nome",
        "persona__nazione_nascita__nome",
        "persona__luogo_nascita_custom",
    )
    ordering = ("persona__cognome", "persona__nome")
    inlines = [FamiliareStudenteInline, DocumentoFamiliareInline]

    fieldsets = (
        (
            "Dati principali",
            {
                "fields": (
                    "persona",
                    "relazione_familiare",
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
    )

    #Questa funzione serve per visualizzare l'indirizzo effettivo del familiare, che può essere diverso da quello principale della famiglia, direttamente nella lista dei familiari nell'Admin
    @admin.display(description="Indirizzo effettivo")
    def indirizzo_effettivo_admin(self, obj):
        indirizzo = obj.indirizzo_effettivo
        return str(indirizzo) if indirizzo else "-"
    
    autocomplete_fields = ("persona", "relazione_familiare")


@admin.register(Studente)
class StudenteAdmin(admin.ModelAdmin):
    list_display = (
        "cognome",
        "nome",
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
        "nazione_nascita__nome",
        "luogo_nascita_custom",
    )
    ordering = ("cognome", "nome")
    inlines = [StudenteFamiliareInline, DocumentoStudenteInline]

    fieldsets = (
        (
            "Dati principali",
            {
                "fields": (
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
                    "nazione_nascita",
                    "luogo_nascita_custom",
                    "nazionalita",
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
    
    autocomplete_fields = ("indirizzo", "luogo_nascita", "nazione_nascita", "nazionalita")


@admin.register(StudenteFamiliare)
class StudenteFamiliareAdmin(admin.ModelAdmin):
    list_display = ("studente", "familiare", "relazione_familiare", "referente_principale", "convivente", "attivo")
    list_filter = ("relazione_familiare", "referente_principale", "convivente", "attivo")
    search_fields = (
        "studente__cognome",
        "studente__nome",
        "familiare__persona__cognome",
        "familiare__persona__nome",
    )
    autocomplete_fields = ("studente", "familiare", "relazione_familiare")
    ordering = ("studente__cognome", "studente__nome", "familiare__persona__cognome", "familiare__persona__nome")

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
