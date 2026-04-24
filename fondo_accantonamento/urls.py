from django.urls import path

from sistema.permissions import module_edit_permission_required, module_permission_required

from . import views

fondo_view = module_permission_required("economia")
fondo_manage = module_permission_required("economia", level="manage")
fondo_edit = module_edit_permission_required("economia")

urlpatterns = [
    path("economia/fondo-accantonamento/", fondo_view(views.lista_piani), name="fondo_piano_lista"),
    path(
        "economia/fondo-accantonamento/nuovo/",
        fondo_manage(views.nuovo_piano),
        name="fondo_piano_nuovo",
    ),
    path(
        "economia/fondo-accantonamento/<int:pk>/",
        fondo_view(views.dettaglio_piano),
        name="fondo_piano_dettaglio",
    ),
    path(
        "economia/fondo-accantonamento/<int:pk>/modifica/",
        fondo_edit(views.modifica_piano),
        name="fondo_piano_modifica",
    ),
    path(
        "economia/fondo-accantonamento/<int:pk>/elimina/",
        fondo_manage(views.elimina_piano),
        name="fondo_piano_elimina",
    ),
    path(
        "economia/fondo-accantonamento/<int:piano_pk>/versamento/",
        fondo_manage(views.aggiungi_versamento),
        name="fondo_piano_versamento",
    ),
    path(
        "economia/fondo-accantonamento/<int:piano_pk>/prelievo/",
        fondo_manage(views.aggiungi_prelievo),
        name="fondo_piano_prelievo",
    ),
    path(
        "economia/fondo-accantonamento/<int:piano_pk>/genera-scadenze/",
        fondo_manage(views.genera_scadenze),
        name="fondo_piano_genera_scadenze",
    ),
    path(
        "economia/fondo-accantonamento/scadenza/<int:scadenza_pk>/soddisfa/",
        fondo_manage(views.soddisfa_scadenza),
        name="fondo_scadenza_soddisfa",
    ),
]
