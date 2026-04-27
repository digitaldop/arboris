from django.contrib import admin

from .models import OsservazioneStudente


@admin.register(OsservazioneStudente)
class OsservazioneStudenteAdmin(admin.ModelAdmin):
    list_display = ("studente", "titolo", "data_inserimento", "creato_da", "aggiornato_da")
    list_filter = ("data_inserimento",)
    search_fields = ("studente__nome", "studente__cognome", "titolo", "testo")
    autocomplete_fields = ("studente", "creato_da", "aggiornato_da")
