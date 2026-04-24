from django.urls import path
from . import views
from sistema.permissions import authenticated_user_required, module_edit_permission_required, module_permission_required


app_auth = authenticated_user_required
anagrafica_view = module_permission_required("anagrafica")
anagrafica_manage = module_permission_required("anagrafica", level="manage")
anagrafica_edit = module_edit_permission_required("anagrafica")

urlpatterns = [
    path("", app_auth(views.home), name="home"),
    #URLS DEGLI INDIRIZZI
    path("indirizzi/", anagrafica_view(views.lista_indirizzi), name="lista_indirizzi"),
    path("indirizzi/nuovo/", anagrafica_manage(views.crea_indirizzo), name="crea_indirizzo"),
    path("indirizzi/<int:pk>/modifica/", anagrafica_edit(views.modifica_indirizzo), name="modifica_indirizzo"),
    path("indirizzi/<int:pk>/elimina/", anagrafica_manage(views.elimina_indirizzo), name="elimina_indirizzo"),

    #URLS DELLE FAMIGLIE
    path("famiglie/", anagrafica_view(views.lista_famiglie), name="lista_famiglie"),
    path("famiglie/nuovo/", anagrafica_manage(views.crea_famiglia), name="crea_famiglia"),
    path("famiglie/<int:pk>/modifica/", anagrafica_edit(views.modifica_famiglia), name="modifica_famiglia"),
    path("famiglie/<int:pk>/stampa/", anagrafica_view(views.stampa_famiglia), name="stampa_famiglia"),
    path("famiglie/<int:pk>/elimina/", anagrafica_manage(views.elimina_famiglia), name="elimina_famiglia"),

    #URLS DEGLI STATI RELAZIONE FAMIGLIA
    path("stati-relazione-famiglia/nuovo/", anagrafica_manage(views.crea_stato_relazione_famiglia), name="crea_stato_relazione_famiglia"),
    path("stati-relazione-famiglia/<int:pk>/modifica/", anagrafica_edit(views.modifica_stato_relazione_famiglia), name="modifica_stato_relazione_famiglia"),
    path("stati-relazione-famiglia/<int:pk>/elimina/", anagrafica_manage(views.elimina_stato_relazione_famiglia), name="elimina_stato_relazione_famiglia"),

    #URLS DELLE RELAZIONI FAMILIARI
    path("relazioni-familiari/nuovo/", anagrafica_manage(views.crea_relazione_familiare), name="crea_relazione_familiare"),
    path("relazioni-familiari/<int:pk>/modifica/", anagrafica_edit(views.modifica_relazione_familiare), name="modifica_relazione_familiare"),
    path("relazioni-familiari/<int:pk>/elimina/", anagrafica_manage(views.elimina_relazione_familiare), name="elimina_relazione_familiare"),

    #URLS DEI DOCUMENTI
    path("tipi-documento/nuovo/", anagrafica_manage(views.crea_tipo_documento), name="crea_tipo_documento"),
    path("tipi-documento/<int:pk>/modifica/", anagrafica_edit(views.modifica_tipo_documento), name="modifica_tipo_documento"),
    path("tipi-documento/<int:pk>/elimina/", anagrafica_manage(views.elimina_tipo_documento), name="elimina_tipo_documento"),

    #URLS DEGLI STUDENTI
    path("studenti/", anagrafica_view(views.lista_studenti), name="lista_studenti"),
    path("studenti/nuovo/", anagrafica_manage(views.crea_studente), name="crea_studente"),
    path("studenti/<int:pk>/modifica/", anagrafica_edit(views.modifica_studente), name="modifica_studente"),
    path("studenti/<int:pk>/elimina/", anagrafica_manage(views.elimina_studente), name="elimina_studente"),

    #URLS DEI FAMILIARI
    path("familiari/", anagrafica_view(views.lista_familiari), name="lista_familiari"),
    path("familiari/nuovo/", anagrafica_manage(views.crea_familiare), name="crea_familiare"),
    path("familiari/<int:pk>/modifica/", anagrafica_edit(views.modifica_familiare), name="modifica_familiare"),
    path("familiari/<int:pk>/elimina/", anagrafica_manage(views.elimina_familiare), name="elimina_familiare"),

    #URSL PER LE AJAX
    path("ajax/cerca-citta/", anagrafica_view(views.ajax_cerca_citta), name="ajax_cerca_citta"),
]
