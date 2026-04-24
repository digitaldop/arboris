from django.contrib import admin

from .models import CategoriaCalendario, EventoCalendario


@admin.register(CategoriaCalendario)
class CategoriaCalendarioAdmin(admin.ModelAdmin):
    list_display = ("nome", "chiave_sistema", "colore", "ordine", "attiva")
    list_filter = ("attiva", "chiave_sistema")
    search_fields = ("nome", "chiave_sistema")
    ordering = ("ordine", "nome")


@admin.register(EventoCalendario)
class EventoCalendarioAdmin(admin.ModelAdmin):
    list_display = (
        "titolo",
        "categoria_evento",
        "tipologia",
        "data_inizio",
        "data_fine",
        "intera_giornata",
        "ripetizione",
        "attivo",
    )
    list_filter = ("categoria_evento", "intera_giornata", "ripetizione", "attivo", "visibile")
    search_fields = ("titolo", "tipologia", "luogo", "descrizione")
