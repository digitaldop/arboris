from django.urls import path

from . import views
from .permissions import module_edit_permission_required, module_permission_required


sistema_view = module_permission_required("sistema")
sistema_manage = module_permission_required("sistema", level="manage")
sistema_edit = module_edit_permission_required("sistema")


urlpatterns = [
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("privacy/", views.informativa_privacy, name="informativa_privacy"),
    path("termini-e-condizioni/", views.termini_e_condizioni, name="termini_condizioni"),
    path("sistema/scuola/", sistema_edit(views.scuola_sistema), name="scuola_sistema"),
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
        "sistema/backup-database/",
        sistema_manage(views.backup_database_sistema),
        name="backup_database_sistema",
    ),
    path(
        "sistema/backup-database/<int:pk>/scarica/",
        sistema_manage(views.scarica_backup_database),
        name="scarica_backup_database",
    ),
    path(
        "sistema/cronologia-operazioni/",
        views.cronologia_operazioni_sistema,
        name="cronologia_operazioni_sistema",
    ),
    path("sistema/utenti/", sistema_view(views.lista_utenti), name="lista_utenti"),
    path("sistema/utenti/nuovo/", sistema_manage(views.crea_utente), name="crea_utente"),
    path("sistema/utenti/<int:pk>/", sistema_edit(views.modifica_utente), name="modifica_utente"),
]
