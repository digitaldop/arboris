from django.urls import path

from . import views
from sistema.permissions import module_edit_permission_required, module_permission_required


scuola_view = module_permission_required("sistema")
scuola_manage = module_permission_required("sistema", level="manage")
scuola_edit = module_edit_permission_required("sistema")
urlpatterns = [
    path("scuola/anni-scolastici/", scuola_view(views.lista_anni_scolastici), name="lista_anni_scolastici"),
    path("scuola/anni-scolastici/nuovo/", scuola_manage(views.crea_anno_scolastico), name="crea_anno_scolastico"),
    path("scuola/anni-scolastici/<int:pk>/modifica/", scuola_edit(views.modifica_anno_scolastico), name="modifica_anno_scolastico"),
    path("scuola/anni-scolastici/<int:pk>/elimina/", scuola_manage(views.elimina_anno_scolastico), name="elimina_anno_scolastico"),
    path("scuola/classi/", scuola_view(views.lista_classi), name="lista_classi"),
    path("scuola/classi/nuova/", scuola_manage(views.crea_classe), name="crea_classe"),
    path("scuola/classi/<int:pk>/modifica/", scuola_edit(views.modifica_classe), name="modifica_classe"),
    path("scuola/classi/<int:pk>/elimina/", scuola_manage(views.elimina_classe), name="elimina_classe"),
    path("scuola/gruppi-classe/", scuola_view(views.lista_gruppi_classe), name="lista_gruppi_classe"),
    path("scuola/gruppi-classe/nuovo/", scuola_manage(views.crea_gruppo_classe), name="crea_gruppo_classe"),
    path("scuola/gruppi-classe/<int:pk>/modifica/", scuola_edit(views.modifica_gruppo_classe), name="modifica_gruppo_classe"),
    path("scuola/gruppi-classe/<int:pk>/elimina/", scuola_manage(views.elimina_gruppo_classe), name="elimina_gruppo_classe"),
]
