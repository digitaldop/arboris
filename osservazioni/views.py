from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from anagrafica.models import Studente
from economia.models import Iscrizione
from sistema.models import LivelloPermesso, SistemaImpostazioniGenerali
from sistema.permissions import user_has_module_permission, user_is_operational_admin
from sistema.terminology import get_student_terminology

from .forms import OsservazioneStudenteForm
from .models import OsservazioneStudente


def user_can_manage_osservazioni(user):
    return user_has_module_permission(user, "anagrafica", LivelloPermesso.GESTIONE)


def get_osservazioni_policy():
    impostazioni = SistemaImpostazioniGenerali.objects.first()
    return {
        "solo_autori_visualizzazione": bool(
            getattr(impostazioni, "osservazioni_solo_autori_visualizzazione", False)
        ),
        "solo_autori_modifica": bool(getattr(impostazioni, "osservazioni_solo_autori_modifica", True)),
    }


def user_can_change_osservazione(user, osservazione, solo_autori_modifica=None):
    if not user or not user.is_authenticated:
        return False
    if user_is_operational_admin(user):
        return True
    if not user_can_manage_osservazioni(user):
        return False
    if solo_autori_modifica is None:
        solo_autori_modifica = get_osservazioni_policy()["solo_autori_modifica"]
    if not solo_autori_modifica:
        return True
    return osservazione.creato_da_id == user.id


def osservazioni_studente_redirect(studente_pk, ordine):
    return f"{reverse('osservazioni_studente', kwargs={'studente_pk': studente_pk})}?ordine={ordine}"


def normalize_ordine(value):
    return "desc" if value == "desc" else "asc"


def student_general_data_title():
    settings = SistemaImpostazioniGenerali.objects.first()
    terminology = get_student_terminology(getattr(settings, "terminologia_studente", None))
    selected_key = terminology["selected_key"]
    if selected_key == "alunno":
        suffix = "dell'alunno"
    elif selected_key == "bambino":
        suffix = "del bambino"
    else:
        suffix = "dello studente"
    return f"Dati generali {suffix}"


def get_classe_corrente_label(studente):
    iscrizione_corrente = (
        Iscrizione.objects.select_related("classe", "anno_scolastico")
        .filter(studente=studente, classe__isnull=False)
        .order_by("-attiva", "-anno_scolastico__data_inizio", "-pk")
        .first()
    )
    if iscrizione_corrente and iscrizione_corrente.classe:
        return str(iscrizione_corrente.classe)
    return ""


def osservazioni_studente(request, studente_pk):
    studente = get_object_or_404(
        Studente.objects.select_related("famiglia"),
        pk=studente_pk,
    )
    can_manage = user_can_manage_osservazioni(request.user)
    ordine = normalize_ordine(request.GET.get("ordine"))
    osservazioni_policy = get_osservazioni_policy()

    if request.method == "POST":
        if not can_manage:
            messages.error(request, "Non hai i permessi necessari per aggiungere osservazioni.")
            return redirect("osservazioni_studente", studente_pk=studente.pk)

        form = OsservazioneStudenteForm(request.POST)
        if form.is_valid():
            osservazione = form.save(commit=False)
            osservazione.studente = studente
            osservazione.creato_da = request.user
            osservazione.aggiornato_da = request.user
            osservazione.save()
            messages.success(request, "Osservazione aggiunta correttamente.")
            return redirect(osservazioni_studente_redirect(studente.pk, ordine))
    else:
        form = OsservazioneStudenteForm()
    show_create_form = request.method == "POST" and can_manage

    ordering = ["data_inserimento", "id"] if ordine == "asc" else ["-data_inserimento", "-id"]
    osservazioni_qs = studente.osservazioni.select_related("creato_da", "aggiornato_da").order_by(*ordering)
    if osservazioni_policy["solo_autori_visualizzazione"] and not user_is_operational_admin(request.user):
        osservazioni_qs = osservazioni_qs.filter(creato_da=request.user)
    osservazioni = list(osservazioni_qs)
    for osservazione in osservazioni:
        osservazione.can_change_for_current_user = user_can_change_osservazione(
            request.user,
            osservazione,
            osservazioni_policy["solo_autori_modifica"],
        )
    toggle_ordine = "desc" if ordine == "asc" else "asc"
    classe_corrente_label = get_classe_corrente_label(studente)

    return render(
        request,
        "osservazioni/osservazioni_studente.html",
        {
            "studente": studente,
            "osservazioni": osservazioni,
            "form": form,
            "ordine": ordine,
            "toggle_ordine": toggle_ordine,
            "can_manage_osservazioni": can_manage,
            "show_create_form": show_create_form,
            "student_general_data_title": student_general_data_title(),
            "classe_corrente_label": classe_corrente_label,
        },
    )


def modifica_osservazione_studente(request, pk):
    osservazione = get_object_or_404(
        OsservazioneStudente.objects.select_related("studente", "studente__famiglia"),
        pk=pk,
    )
    ordine = normalize_ordine(request.GET.get("ordine"))
    osservazioni_policy = get_osservazioni_policy()
    if not user_can_change_osservazione(request.user, osservazione, osservazioni_policy["solo_autori_modifica"]):
        messages.error(request, "Puoi modificare solo le osservazioni che hai creato.")
        return redirect(osservazioni_studente_redirect(osservazione.studente_id, ordine))

    if request.method == "POST":
        form = OsservazioneStudenteForm(request.POST, instance=osservazione)
        if form.is_valid():
            osservazione = form.save(commit=False)
            osservazione.aggiornato_da = request.user
            osservazione.save()
            messages.success(request, "Osservazione aggiornata correttamente.")
            return redirect(osservazioni_studente_redirect(osservazione.studente_id, ordine))
    else:
        form = OsservazioneStudenteForm(instance=osservazione)

    return render(
        request,
        "osservazioni/osservazione_form.html",
        {
            "form": form,
            "osservazione": osservazione,
            "studente": osservazione.studente,
            "ordine": ordine,
        },
    )


def elimina_osservazione_studente(request, pk):
    osservazione = get_object_or_404(
        OsservazioneStudente.objects.select_related("studente", "creato_da"),
        pk=pk,
    )
    studente = osservazione.studente
    ordine = normalize_ordine(request.GET.get("ordine"))
    osservazioni_policy = get_osservazioni_policy()
    if not user_can_change_osservazione(request.user, osservazione, osservazioni_policy["solo_autori_modifica"]):
        messages.error(request, "Puoi eliminare solo le osservazioni che hai creato.")
        return redirect(osservazioni_studente_redirect(studente.pk, ordine))

    if request.method == "POST":
        osservazione.delete()
        messages.success(request, "Osservazione eliminata correttamente.")
        return redirect(osservazioni_studente_redirect(studente.pk, ordine))

    return render(
        request,
        "osservazioni/osservazione_confirm_delete.html",
        {
            "osservazione": osservazione,
            "studente": studente,
            "ordine": ordine,
        },
    )
