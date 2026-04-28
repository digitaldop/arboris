from django.contrib import admin

from .models import AnnoScolastico, Classe


@admin.register(AnnoScolastico)
class AnnoScolasticoAdmin(admin.ModelAdmin):
    list_display = ("nome_anno_scolastico", "data_inizio", "data_fine", "corrente_calcolato", "attivo")
    list_filter = ("attivo",)
    search_fields = ("nome_anno_scolastico",)

    @admin.display(boolean=True, description="Corrente")
    def corrente_calcolato(self, obj):
        return obj.is_corrente


@admin.register(Classe)
class ClasseAdmin(admin.ModelAdmin):
    list_display = ("nome_classe", "sezione_classe", "ordine_classe", "anno_scolastico", "attiva")
    list_filter = ("anno_scolastico", "attiva")
    search_fields = ("nome_classe", "sezione_classe")
