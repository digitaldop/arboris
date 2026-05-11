from django.urls import path

from . import views
from anagrafica import views as anagrafica_views
from .permissions import database_backup_access_required, module_edit_permission_required, module_permission_required


sistema_view = module_permission_required("sistema")
sistema_manage = module_permission_required("sistema", level="manage")
sistema_edit = module_edit_permission_required("sistema")


urlpatterns = [
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("privacy/", views.informativa_privacy, name="informativa_privacy"),
    path("termini-e-condizioni/", views.termini_e_condizioni, name="termini_condizioni"),
    path("sistema/ricerca-globale/", views.ricerca_globale_sistema, name="ricerca_globale_sistema"),
    path("sistema/toggle-attivo/", views.toggle_active_state, name="toggle_active_state"),
    path("feedback/beta/", views.crea_feedback_beta, name="crea_feedback_beta"),
    path("sistema/scuola/", sistema_edit(views.scuola_sistema), name="scuola_sistema"),
    path("sistema/scuola/indirizzi/nuovo/", sistema_edit(anagrafica_views.crea_indirizzo), name="scuola_crea_indirizzo"),
    path(
        "sistema/scuola/indirizzi/<int:pk>/modifica/",
        sistema_edit(anagrafica_views.modifica_indirizzo),
        name="scuola_modifica_indirizzo",
    ),
    path(
        "sistema/scuola/indirizzi/<int:pk>/elimina/",
        sistema_edit(anagrafica_views.elimina_indirizzo),
        name="scuola_elimina_indirizzo",
    ),
    path(
        "sistema/impostazioni-generali/",
        sistema_edit(views.impostazioni_generali_sistema),
        name="impostazioni_generali_sistema",
    ),
    path(
        "sistema/impostazioni-generali/importa-dati-base/",
        sistema_manage(views.importa_dati_base_anagrafica),
        name="importa_dati_base_anagrafica",
    ),
    path(
        "sistema/impostazioni-generali/importa-nazioni-belfiore/",
        sistema_manage(views.importa_nazioni_belfiore_anagrafica),
        name="importa_nazioni_belfiore_anagrafica",
    ),
    path(
        "sistema/backup-database/",
        database_backup_access_required(views.backup_database_sistema),
        name="backup_database_sistema",
    ),
    path(
        "sistema/backup-database/upload-ripristino/",
        database_backup_access_required(views.upload_restore_chunk_sistema),
        name="backup_database_restore_chunk_upload",
    ),
    path(
        "sistema/backup-database/job-ripristino/<int:pk>/rimuovi/",
        database_backup_access_required(views.rimuovi_job_ripristino_database),
        name="rimuovi_job_ripristino_database",
    ),
    path(
        "sistema/backup-database/<int:pk>/scarica/",
        database_backup_access_required(views.scarica_backup_database),
        name="scarica_backup_database",
    ),
    path(
        "sistema/cronologia-operazioni/",
        views.cronologia_operazioni_sistema,
        name="cronologia_operazioni_sistema",
    ),
    path(
        "sistema/feedback/",
        views.lista_feedback_segnalazioni,
        name="lista_feedback_segnalazioni",
    ),
    path("sistema/utenti/", sistema_view(views.lista_utenti), name="lista_utenti"),
    path("sistema/utenti/ruoli/", sistema_view(views.lista_ruoli_utenti), name="lista_ruoli_utenti"),
    path("sistema/utenti/ruoli/nuovo/", sistema_manage(views.crea_ruolo_utente), name="crea_ruolo_utente"),
    path(
        "sistema/utenti/ruoli/<int:pk>/elimina/",
        sistema_manage(views.elimina_ruolo_utente),
        name="elimina_ruolo_utente",
    ),
    path("sistema/utenti/ruoli/<int:pk>/", sistema_edit(views.modifica_ruolo_utente), name="modifica_ruolo_utente"),
    path("sistema/utenti/nuovo/", sistema_manage(views.crea_utente), name="crea_utente"),
    path("sistema/utenti/<int:pk>/elimina/", sistema_manage(views.elimina_utente), name="elimina_utente"),
    path("sistema/utenti/<int:pk>/", sistema_manage(views.modifica_utente), name="modifica_utente"),
]
