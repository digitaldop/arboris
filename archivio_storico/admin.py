from django.contrib import admin

from .models import ArchivioAnnoScolastico, ArchivioSnapshot


@admin.register(ArchivioAnnoScolastico)
class ArchivioAnnoScolasticoAdmin(admin.ModelAdmin):
    list_display = (
        "nome_anno_scolastico",
        "data_inizio",
        "data_fine",
        "data_archiviazione",
        "archiviato_da",
        "totale_snapshot",
    )
    search_fields = ("nome_anno_scolastico",)
    list_filter = ("data_archiviazione",)


@admin.register(ArchivioSnapshot)
class ArchivioSnapshotAdmin(admin.ModelAdmin):
    list_display = ("archivio", "tipo", "titolo", "source_model", "source_pk")
    search_fields = ("titolo", "source_pk")
    list_filter = ("tipo", "source_app_label", "source_model")
