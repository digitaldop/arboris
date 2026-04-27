from django.urls import path

from sistema.permissions import module_edit_permission_required

from . import views


osservazioni_edit = module_edit_permission_required("anagrafica")

urlpatterns = [
    path(
        "studenti/<int:studente_pk>/osservazioni/",
        osservazioni_edit(views.osservazioni_studente),
        name="osservazioni_studente",
    ),
    path(
        "osservazioni/<int:pk>/modifica/",
        osservazioni_edit(views.modifica_osservazione_studente),
        name="modifica_osservazione_studente",
    ),
    path(
        "osservazioni/<int:pk>/elimina/",
        osservazioni_edit(views.elimina_osservazione_studente),
        name="elimina_osservazione_studente",
    ),
]
