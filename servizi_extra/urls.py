from django.urls import path

from servizi_extra.views import servizi as servizi_views
from sistema.permissions import module_edit_permission_required, module_permission_required


servizi_extra_view = module_permission_required("servizi_extra")
servizi_extra_manage = module_permission_required("servizi_extra", level="manage")
servizi_extra_edit = module_edit_permission_required("servizi_extra")


urlpatterns = [
    path("servizi-extra/servizi/", servizi_extra_view(servizi_views.lista_servizi_extra), name="lista_servizi_extra"),
    path(
        "servizi-extra/servizi/<int:pk>/",
        servizi_extra_view(servizi_views.dettaglio_servizio_extra),
        name="dettaglio_servizio_extra",
    ),
    path("servizi-extra/servizi/nuovo/", servizi_extra_manage(servizi_views.crea_servizio_extra), name="crea_servizio_extra"),
    path(
        "servizi-extra/servizi/<int:pk>/modifica/",
        servizi_extra_edit(servizi_views.modifica_servizio_extra),
        name="modifica_servizio_extra",
    ),
    path(
        "servizi-extra/servizi/<int:pk>/elimina/",
        servizi_extra_manage(servizi_views.elimina_servizio_extra),
        name="elimina_servizio_extra",
    ),
    path("servizi-extra/tariffe/", servizi_extra_view(servizi_views.lista_tariffe_servizi_extra), name="lista_tariffe_servizi_extra"),
    path(
        "servizi-extra/tariffe/nuova/",
        servizi_extra_manage(servizi_views.crea_tariffa_servizio_extra),
        name="crea_tariffa_servizio_extra",
    ),
    path(
        "servizi-extra/tariffe/<int:pk>/modifica/",
        servizi_extra_edit(servizi_views.modifica_tariffa_servizio_extra),
        name="modifica_tariffa_servizio_extra",
    ),
    path(
        "servizi-extra/tariffe/<int:pk>/elimina/",
        servizi_extra_manage(servizi_views.elimina_tariffa_servizio_extra),
        name="elimina_tariffa_servizio_extra",
    ),
    path("servizi-extra/iscrizioni/", servizi_extra_view(servizi_views.lista_iscrizioni_servizi_extra), name="lista_iscrizioni_servizi_extra"),
    path(
        "servizi-extra/iscrizioni/nuova/",
        servizi_extra_manage(servizi_views.crea_iscrizione_servizio_extra),
        name="crea_iscrizione_servizio_extra",
    ),
    path(
        "servizi-extra/iscrizioni/<int:pk>/modifica/",
        servizi_extra_edit(servizi_views.modifica_iscrizione_servizio_extra),
        name="modifica_iscrizione_servizio_extra",
    ),
    path(
        "servizi-extra/iscrizioni/<int:pk>/ricalcola-rate/",
        servizi_extra_manage(servizi_views.ricalcola_rate_iscrizione_servizio_extra),
        name="ricalcola_rate_iscrizione_servizio_extra",
    ),
    path(
        "servizi-extra/iscrizioni/<int:pk>/elimina/",
        servizi_extra_manage(servizi_views.elimina_iscrizione_servizio_extra),
        name="elimina_iscrizione_servizio_extra",
    ),
    path("servizi-extra/rate/", servizi_extra_view(servizi_views.lista_rate_servizi_extra), name="lista_rate_servizi_extra"),
    path(
        "servizi-extra/rate/<int:pk>/modifica/",
        servizi_extra_edit(servizi_views.modifica_rata_servizio_extra),
        name="modifica_rata_servizio_extra",
    ),
]
