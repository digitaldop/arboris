from django.contrib import admin

from .models import (
    FeedbackSegnalazione,
    SistemaOperazioneCronologia,
    SistemaBackupDatabaseConfigurazione,
    SistemaDatabaseBackup,
    SistemaDatabaseRestoreJob,
    Scuola,
    ScuolaSocial,
    ScuolaTelefono,
    ScuolaEmail,
    SistemaImpostazioniGenerali,
    SistemaRuoloPermessi,
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


@admin.register(SistemaRuoloPermessi)
class SistemaRuoloPermessiAdmin(admin.ModelAdmin):
    list_display = (
        "nome",
        "colore_principale",
        "attivo",
        "controllo_completo",
        "amministratore_operativo",
        "accesso_backup_database",
    )
    list_filter = ("attivo", "controllo_completo", "amministratore_operativo", "accesso_backup_database")
    search_fields = ("nome", "descrizione")


@admin.register(SistemaUtentePermessi)
class SistemaUtentePermessiAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "ruolo_permessi",
        "ruolo",
        "controllo_completo",
        "permesso_anagrafica",
        "permesso_famiglie_interessate",
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
        "gestione_iscrizione_corso_anno",
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


@admin.register(SistemaDatabaseRestoreJob)
class SistemaDatabaseRestoreJobAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False

    list_display = (
        "stato",
        "nome_file_originale",
        "creato_da",
        "data_creazione",
        "data_completamento",
    )
    list_filter = ("stato",)
    search_fields = ("nome_file_originale", "celery_task_id", "messaggio_errore")
    readonly_fields = (
        "stato",
        "percorso_file",
        "nome_file_originale",
        "dimensione_file_bytes",
        "creato_da",
        "data_creazione",
        "data_avvio_ripristino",
        "data_completamento",
        "messaggio_errore",
        "backup_sicurezza",
        "celery_task_id",
    )


@admin.register(FeedbackSegnalazione)
class FeedbackSegnalazioneAdmin(admin.ModelAdmin):
    list_display = (
        "data_creazione",
        "tipo",
        "stato",
        "utente_display",
        "pagina_titolo",
        "email_status_label",
    )
    list_filter = ("tipo", "stato", "data_creazione", "email_inviata_at")
    search_fields = ("messaggio", "utente_nome", "utente_email", "pagina_titolo", "pagina_path")
    readonly_fields = (
        "tipo",
        "messaggio",
        "utente",
        "utente_nome",
        "utente_email",
        "utente_ruolo",
        "pagina_url",
        "pagina_path",
        "pagina_titolo",
        "breadcrumb",
        "user_agent",
        "referer",
        "ip_address",
        "email_destinatario",
        "email_inviata_at",
        "email_errore",
        "data_creazione",
        "data_aggiornamento",
    )

    def has_add_permission(self, request):
        return False


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
