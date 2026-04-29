from django.urls import path

from . import views
from sistema.permissions import authenticated_user_required


scuola_auth = authenticated_user_required
urlpatterns = [
    path("scuola/anni-scolastici/", scuola_auth(views.lista_anni_scolastici), name="lista_anni_scolastici"),
    path("scuola/anni-scolastici/nuovo/", scuola_auth(views.crea_anno_scolastico), name="crea_anno_scolastico"),
    path("scuola/anni-scolastici/<int:pk>/modifica/", scuola_auth(views.modifica_anno_scolastico), name="modifica_anno_scolastico"),
    path("scuola/anni-scolastici/<int:pk>/elimina/", scuola_auth(views.elimina_anno_scolastico), name="elimina_anno_scolastico"),
    path("scuola/classi/", scuola_auth(views.lista_classi), name="lista_classi"),
    path("scuola/classi/nuova/", scuola_auth(views.crea_classe), name="crea_classe"),
    path("scuola/classi/<int:pk>/modifica/", scuola_auth(views.modifica_classe), name="modifica_classe"),
    path("scuola/classi/<int:pk>/elimina/", scuola_auth(views.elimina_classe), name="elimina_classe"),
    path("scuola/gruppi-classe/", scuola_auth(views.lista_gruppi_classe), name="lista_gruppi_classe"),
    path("scuola/gruppi-classe/nuovo/", scuola_auth(views.crea_gruppo_classe), name="crea_gruppo_classe"),
    path("scuola/gruppi-classe/<int:pk>/modifica/", scuola_auth(views.modifica_gruppo_classe), name="modifica_gruppo_classe"),
    path("scuola/gruppi-classe/<int:pk>/elimina/", scuola_auth(views.elimina_gruppo_classe), name="elimina_gruppo_classe"),
]
