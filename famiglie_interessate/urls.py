from django.urls import path

from sistema.permissions import module_edit_permission_required, module_permission_required

from . import views


famiglie_interessate_view = module_permission_required("famiglie_interessate")
famiglie_interessate_manage = module_permission_required("famiglie_interessate", level="manage")
famiglie_interessate_edit = module_edit_permission_required("famiglie_interessate")


urlpatterns = [
    path(
        "famiglie-interessate/",
        famiglie_interessate_view(views.lista_famiglie_interessate),
        name="lista_famiglie_interessate",
    ),
    path(
        "famiglie-interessate/nuova/",
        famiglie_interessate_manage(views.crea_famiglia_interessata),
        name="crea_famiglia_interessata",
    ),
    path(
        "famiglie-interessate/<int:pk>/",
        famiglie_interessate_edit(views.modifica_famiglia_interessata),
        name="modifica_famiglia_interessata",
    ),
    path(
        "famiglie-interessate/<int:pk>/attivita/nuova/",
        famiglie_interessate_manage(views.crea_attivita_famiglia_interessata),
        name="crea_attivita_famiglia_interessata",
    ),
    path(
        "famiglie-interessate/attivita/<int:pk>/",
        famiglie_interessate_edit(views.modifica_attivita_famiglia_interessata),
        name="modifica_attivita_famiglia_interessata",
    ),
]
