from django.contrib import admin

from .models import (
    AttivitaFamigliaInteressata,
    FamigliaInteressata,
    MinoreInteressato,
    ReferenteFamigliaInteressata,
)


class ReferenteFamigliaInteressataInline(admin.TabularInline):
    model = ReferenteFamigliaInteressata
    extra = 0


class MinoreInteressatoInline(admin.TabularInline):
    model = MinoreInteressato
    extra = 0


class AttivitaFamigliaInteressataInline(admin.TabularInline):
    model = AttivitaFamigliaInteressata
    extra = 0
    fields = ("tipo", "titolo", "stato", "data_programmata", "assegnata_a")


@admin.register(FamigliaInteressata)
class FamigliaInteressataAdmin(admin.ModelAdmin):
    list_display = (
        "nome_display",
        "referente_principale",
        "telefono",
        "email",
        "stato",
        "priorita",
        "data_aggiornamento",
    )
    list_filter = ("stato", "priorita", "fonte_contatto", "anno_scolastico_interesse")
    search_fields = ("nome", "referente_principale", "telefono", "email", "note")
    inlines = [ReferenteFamigliaInteressataInline, MinoreInteressatoInline, AttivitaFamigliaInteressataInline]


@admin.register(AttivitaFamigliaInteressata)
class AttivitaFamigliaInteressataAdmin(admin.ModelAdmin):
    list_display = ("calendar_title", "famiglia", "tipo", "stato", "data_programmata", "assegnata_a")
    list_filter = ("tipo", "stato", "calendarizza", "data_programmata")
    search_fields = ("titolo", "famiglia__nome", "famiglia__referente_principale", "descrizione", "esito")
    autocomplete_fields = ("famiglia", "assegnata_a")
