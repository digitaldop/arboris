from django.urls import path

from archivio_storico import views
from sistema.permissions import module_permission_required


archivio_view = module_permission_required("sistema")
archivio_manage = module_permission_required("sistema", level="manage")

urlpatterns = [
    path("archivio-storico/", archivio_view(views.lista_archivio_storico), name="lista_archivio_storico"),
    path(
        "archivio-storico/anni/<int:anno_pk>/anteprima/",
        archivio_manage(views.anteprima_archiviazione_anno),
        name="anteprima_archiviazione_anno",
    ),
    path(
        "archivio-storico/anni/<int:anno_pk>/archivia/",
        archivio_manage(views.archivia_anno),
        name="archivia_anno_scolastico",
    ),
    path(
        "archivio-storico/<int:pk>/",
        archivio_view(views.dettaglio_archivio_storico),
        name="dettaglio_archivio_storico",
    ),
]
