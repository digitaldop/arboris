from django.urls import path

from economia.views import iscrizioni as iscrizioni_views
from economia.views import impostazioni as impostazioni_views
from economia.views import scambio_retta as scambio_retta_views
from sistema.permissions import module_edit_permission_required, module_permission_required


economia_view = module_permission_required("economia")
economia_manage = module_permission_required("economia", level="manage")
economia_edit = module_edit_permission_required("economia")

urlpatterns = [
    path("economia/stati-iscrizione/", economia_view(iscrizioni_views.lista_stati_iscrizione), name="lista_stati_iscrizione"),
    path("economia/stati-iscrizione/nuovo/", economia_manage(iscrizioni_views.crea_stato_iscrizione), name="crea_stato_iscrizione"),
    path("economia/stati-iscrizione/<int:pk>/modifica/", economia_edit(iscrizioni_views.modifica_stato_iscrizione), name="modifica_stato_iscrizione"),
    path("economia/stati-iscrizione/<int:pk>/elimina/", economia_manage(iscrizioni_views.elimina_stato_iscrizione), name="elimina_stato_iscrizione"),
    path("economia/condizioni-iscrizione/", economia_view(iscrizioni_views.lista_condizioni_iscrizione), name="lista_condizioni_iscrizione"),
    path("economia/condizioni-iscrizione/nuova/", economia_manage(iscrizioni_views.crea_condizione_iscrizione), name="crea_condizione_iscrizione"),
    path("economia/condizioni-iscrizione/<int:pk>/modifica/", economia_edit(iscrizioni_views.modifica_condizione_iscrizione), name="modifica_condizione_iscrizione"),
    path("economia/condizioni-iscrizione/<int:pk>/elimina/", economia_manage(iscrizioni_views.elimina_condizione_iscrizione), name="elimina_condizione_iscrizione"),
    path("economia/tariffe-condizione-iscrizione/", economia_view(iscrizioni_views.lista_tariffe_condizione_iscrizione), name="lista_tariffe_condizione_iscrizione"),
    path("economia/tariffe-condizione-iscrizione/nuova/", economia_manage(iscrizioni_views.crea_tariffa_condizione_iscrizione), name="crea_tariffa_condizione_iscrizione"),
    path("economia/tariffe-condizione-iscrizione/<int:pk>/modifica/", economia_edit(iscrizioni_views.modifica_tariffa_condizione_iscrizione), name="modifica_tariffa_condizione_iscrizione"),
    path("economia/tariffe-condizione-iscrizione/<int:pk>/elimina/", economia_manage(iscrizioni_views.elimina_tariffa_condizione_iscrizione), name="elimina_tariffa_condizione_iscrizione"),
    path("economia/agevolazioni/", economia_view(iscrizioni_views.lista_agevolazioni), name="lista_agevolazioni"),
    path("economia/agevolazioni/nuova/", economia_manage(iscrizioni_views.crea_agevolazione), name="crea_agevolazione"),
    path("economia/agevolazioni/<int:pk>/modifica/", economia_edit(iscrizioni_views.modifica_agevolazione), name="modifica_agevolazione"),
    path("economia/agevolazioni/<int:pk>/elimina/", economia_manage(iscrizioni_views.elimina_agevolazione), name="elimina_agevolazione"),
    path("economia/metodi-pagamento/nuovo/", economia_manage(impostazioni_views.crea_metodo_pagamento), name="crea_metodo_pagamento"),
    path("economia/metodi-pagamento/<int:pk>/modifica/", economia_edit(impostazioni_views.modifica_metodo_pagamento), name="modifica_metodo_pagamento"),
    path("economia/metodi-pagamento/<int:pk>/elimina/", economia_manage(impostazioni_views.elimina_metodo_pagamento), name="elimina_metodo_pagamento"),
    path("economia/iscrizioni/", economia_view(iscrizioni_views.lista_iscrizioni), name="lista_iscrizioni"),
    path("economia/iscrizioni/nuova/", economia_manage(iscrizioni_views.crea_iscrizione), name="crea_iscrizione"),
    path("economia/iscrizioni/<int:pk>/modifica/", economia_edit(iscrizioni_views.modifica_iscrizione), name="modifica_iscrizione"),
    path("economia/iscrizioni/<int:pk>/ricalcola-rate/", economia_manage(iscrizioni_views.ricalcola_rate_iscrizione), name="ricalcola_rate_iscrizione"),
    path("economia/iscrizioni/<int:pk>/rimodula-rate/", economia_manage(iscrizioni_views.rimodula_rate_iscrizione), name="rimodula_rate_iscrizione"),
    path("economia/iscrizioni/<int:pk>/riconcilia-pagamenti/", economia_manage(iscrizioni_views.riconcilia_pagamenti_iscrizione), name="riconcilia_pagamenti_iscrizione"),
    path("economia/rate-iscrizione/ricalcola-anno/", economia_manage(iscrizioni_views.ricalcola_rate_anno_scolastico), name="ricalcola_rate_anno_scolastico"),
    path("economia/rate-iscrizione/riconcilia-pagamenti-anno/", economia_manage(iscrizioni_views.riconcilia_pagamenti_rate_anno_scolastico), name="riconcilia_pagamenti_rate_anno_scolastico"),
    path("economia/iscrizioni/<int:pk>/ritiro-anticipato/", economia_manage(iscrizioni_views.ritiro_anticipato_iscrizione), name="ritiro_anticipato_iscrizione"),
    path("economia/iscrizioni/<int:pk>/elimina/", economia_manage(iscrizioni_views.elimina_iscrizione), name="elimina_iscrizione"),
    path("economia/rate-iscrizione/", economia_view(iscrizioni_views.lista_rate_iscrizione), name="lista_rate_iscrizione"),
    path("economia/rate-iscrizione/<int:pk>/modifica/", economia_edit(iscrizioni_views.modifica_rata_iscrizione), name="modifica_rata_iscrizione"),
    path("economia/rate-iscrizione/<int:pk>/pagamento-rapido/", economia_manage(iscrizioni_views.pagamento_rapido_rata_iscrizione), name="pagamento_rapido_rata_iscrizione"),
    path("economia/rate-iscrizione/<int:pk>/riconcilia/", economia_manage(iscrizioni_views.riconcilia_rata_iscrizione), name="riconcilia_rata_iscrizione"),
    path("economia/verifica-situazione-rette/", economia_view(iscrizioni_views.verifica_situazione_rette), name="verifica_situazione_rette"),
    path("economia/scambio-retta/", economia_view(scambio_retta_views.lista_scambi_retta), name="lista_scambi_retta"),
    path("economia/scambio-retta/nuovo/", economia_manage(scambio_retta_views.crea_scambio_retta), name="crea_scambio_retta"),
    path("economia/scambio-retta/<int:pk>/modifica/", economia_edit(scambio_retta_views.modifica_scambio_retta), name="modifica_scambio_retta"),
    path("economia/scambio-retta/<int:pk>/elimina/", economia_manage(scambio_retta_views.elimina_scambio_retta), name="elimina_scambio_retta"),
    path("economia/scambio-retta/<int:pk>/contabilizza/", economia_manage(scambio_retta_views.contabilizza_scambio_retta), name="contabilizza_scambio_retta"),
    path(
        "economia/scambio-retta/prestazioni/nuova/",
        economia_manage(scambio_retta_views.crea_prestazione_scambio_retta),
        name="crea_prestazione_scambio_retta",
    ),
    path(
        "economia/scambio-retta/prestazioni/<int:pk>/modifica/",
        economia_edit(scambio_retta_views.modifica_prestazione_scambio_retta),
        name="modifica_prestazione_scambio_retta",
    ),
    path(
        "economia/scambio-retta/prestazioni/<int:pk>/elimina/",
        economia_manage(scambio_retta_views.elimina_prestazione_scambio_retta),
        name="elimina_prestazione_scambio_retta",
    ),
    path("economia/tariffe-scambio-retta/", economia_view(scambio_retta_views.lista_tariffe_scambio_retta), name="lista_tariffe_scambio_retta"),
    path("economia/tariffe-scambio-retta/nuova/", economia_manage(scambio_retta_views.crea_tariffa_scambio_retta), name="crea_tariffa_scambio_retta"),
    path("economia/tariffe-scambio-retta/<int:pk>/modifica/", economia_edit(scambio_retta_views.modifica_tariffa_scambio_retta), name="modifica_tariffa_scambio_retta"),
    path("economia/tariffe-scambio-retta/<int:pk>/elimina/", economia_manage(scambio_retta_views.elimina_tariffa_scambio_retta), name="elimina_tariffa_scambio_retta"),
]
