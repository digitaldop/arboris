from django.contrib import admin

from .models import (
    SistemaOperazioneCronologia,
    SistemaBackupDatabaseConfigurazione,
    SistemaDatabaseBackup,
    Scuola,
    ScuolaSocial,
    ScuolaTelefono,
    ScuolaEmail,
    SistemaImpostazioniGenerali,
    SistemaUtentePermessi,
)


class ScuolaSocialInline(admin.TabularInline):
    model = ScuolaSocial
    extra = 0
    fields = ("nome_social", "link", "ordine")


class ScuolaTelefonoInline(admin.TabularInline):
    model = ScuolaTelefono
    extra = 0
    fields = ("descrizione", "telefono", "ordine")


class ScuolaEmailInline(admin.TabularInline):
    model = ScuolaEmail
    extra = 0
    fields = ("descrizione", "email", "ordine")


@admin.register(Scuola)
class ScuolaAdmin(admin.ModelAdmin):
    list_display = (
        "nome_scuola",
        "ragione_sociale",
        "codice_fiscale",
        "partita_iva",
    )
    search_fields = ("nome_scuola", "ragione_sociale", "codice_fiscale", "partita_iva")
    inlines = [ScuolaSocialInline, ScuolaTelefonoInline, ScuolaEmailInline]
    autocomplete_fields = ("indirizzo_sede_legale", "indirizzo_operativo")


@admin.register(SistemaUtentePermessi)
class SistemaUtentePermessiAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "ruolo",
        "controllo_completo",
        "permesso_anagrafica",
        "permesso_economia",
        "permesso_sistema",
        "permesso_calendario",
        "permesso_gestione_finanziaria",
        "permesso_gestione_amministrativa",
        "permesso_servizi_extra",
    )
    search_fields = ("user__username", "user__email", "user__first_name", "user__last_name")


@admin.register(SistemaImpostazioniGenerali)
class SistemaImpostazioniGeneraliAdmin(admin.ModelAdmin):
    list_display = (
        "terminologia_studente",
        "mostra_dashboard_prossimo_anno_scolastico",
        "font_principale",
        "font_titoli",
        "data_aggiornamento",
    )


@admin.register(SistemaBackupDatabaseConfigurazione)
class SistemaBackupDatabaseConfigurazioneAdmin(admin.ModelAdmin):
    list_display = (
        "frequenza_backup_automatico",
        "ultimo_backup_automatico_at",
        "backup_automatico_in_corso",
        "data_aggiornamento",
    )


@admin.register(SistemaDatabaseBackup)
class SistemaDatabaseBackupAdmin(admin.ModelAdmin):
    list_display = (
        "nome_file",
        "tipo_backup",
        "dimensione_file_bytes",
        "creato_da",
        "data_creazione",
    )
    search_fields = ("nome_file", "note", "creato_da__username", "creato_da__email")


@admin.register(SistemaOperazioneCronologia)
class SistemaOperazioneCronologiaAdmin(admin.ModelAdmin):
    list_display = (
        "data_operazione",
        "azione",
        "modulo",
        "utente_label",
        "model_verbose_name",
        "oggetto_label",
    )
    list_filter = ("azione", "modulo", "data_operazione")
    search_fields = (
        "utente_label",
        "descrizione",
        "model_verbose_name",
        "oggetto_label",
    )
    readonly_fields = (
        "azione",
        "modulo",
        "utente",
        "utente_label",
        "app_label",
        "model_name",
        "model_verbose_name",
        "oggetto_id",
        "oggetto_label",
        "descrizione",
        "campi_coinvolti",
        "data_operazione",
    )

    def has_add_permission(self, request):
        return False

    def has_view_permission(self, request, obj=None):
        return True

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
