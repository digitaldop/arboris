from django.urls import path

from . import views


urlpatterns = [
    path("scuola/anni-scolastici/", views.lista_anni_scolastici, name="lista_anni_scolastici"),
    path("scuola/anni-scolastici/nuovo/", views.crea_anno_scolastico, name="crea_anno_scolastico"),
    path("scuola/anni-scolastici/<int:pk>/modifica/", views.modifica_anno_scolastico, name="modifica_anno_scolastico"),
    path("scuola/anni-scolastici/<int:pk>/elimina/", views.elimina_anno_scolastico, name="elimina_anno_scolastico"),
    path("scuola/classi/", views.lista_classi, name="lista_classi"),
    path("scuola/classi/nuova/", views.crea_classe, name="crea_classe"),
    path("scuola/classi/<int:pk>/modifica/", views.modifica_classe, name="modifica_classe"),
    path("scuola/classi/<int:pk>/elimina/", views.elimina_classe, name="elimina_classe"),
]
