from django.urls import path
from django.views.generic import RedirectView

from sistema.permissions import module_edit_permission_required, module_permission_required

from . import views


calendario_view = module_permission_required("calendario")
calendario_manage = module_permission_required("calendario", level="manage")
calendario_edit = module_edit_permission_required("calendario")


urlpatterns = [
    path("calendario/agenda/", calendario_view(views.calendario_agenda), name="calendario_agenda"),
    path("calendario/", calendario_view(views.lista_eventi_calendario), name="lista_eventi_calendario"),
    path("calendario/categorie/", calendario_view(views.lista_categorie_calendario), name="lista_categorie_calendario"),
    path("calendario/categorie/nuova/", calendario_manage(views.crea_categoria_calendario), name="crea_categoria_calendario"),
    path(
        "calendario/categorie/<int:pk>/",
        calendario_edit(views.modifica_categoria_calendario),
        name="modifica_categoria_calendario",
    ),
    path(
        "calendario/categorie/<int:pk>/elimina/",
        calendario_manage(views.elimina_categoria_calendario),
        name="elimina_categoria_calendario",
    ),
    path("calendario/nuovo/", calendario_manage(views.crea_evento_calendario), name="crea_evento_calendario"),
    path(
        "calendario/nuovo-rapido/",
        calendario_manage(views.crea_evento_calendario_rapido),
        name="crea_evento_calendario_rapido",
    ),
    path("calendario/<int:pk>/modifica/", calendario_edit(views.modifica_evento_calendario), name="modifica_evento_calendario"),
    path("calendario/<int:pk>/elimina/", calendario_manage(views.elimina_evento_calendario), name="elimina_evento_calendario"),
    path("scuola/calendario/agenda/", RedirectView.as_view(pattern_name="calendario_agenda", permanent=False)),
    path("scuola/calendario/", RedirectView.as_view(pattern_name="lista_eventi_calendario", permanent=False)),
    path("scuola/calendario/categorie/", RedirectView.as_view(pattern_name="lista_categorie_calendario", permanent=False)),
    path("scuola/calendario/categorie/nuova/", RedirectView.as_view(pattern_name="crea_categoria_calendario", permanent=False)),
    path("scuola/calendario/nuovo/", RedirectView.as_view(pattern_name="crea_evento_calendario", permanent=False)),
    path("scuola/calendario/<int:pk>/modifica/", RedirectView.as_view(pattern_name="modifica_evento_calendario", permanent=False)),
    path("scuola/calendario/<int:pk>/elimina/", RedirectView.as_view(pattern_name="elimina_evento_calendario", permanent=False)),
]
