"""Menu LOG amministrativo: operazioni degli utenti e letture per account."""

from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Exists, Max, OuterRef, Q
from django.http import JsonResponse
from django.middleware.csrf import get_token
from django.shortcuts import get_object_or_404, redirect
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST

from .models import SistemaLogLettura, SistemaLogStatoLettura, SistemaOperazioneCronologia
from .permissions import operational_admin_required, user_has_page_permission


def operazioni_utente():
    return SistemaOperazioneCronologia.objects.filter(
        Q(utente__isnull=False) | ~Q(utente_label=""),
    ).exclude(app_label="gestione_finanziaria", model_name="notificafinanziarialettura")


def nuove_operazioni(user):
    if not user_has_page_permission(user, "sistema_cronologia_operazioni"):
        raise PermissionDenied
    stato = SistemaLogStatoLettura.objects.filter(user=user).first()
    if stato is None:
        # Il registro preesistente resta nella cronologia, senza creare un arretrato.
        ultimo_id = SistemaOperazioneCronologia.objects.aggregate(ultimo=Max("pk"))["ultimo"] or 0
        stato, _ = SistemaLogStatoLettura.objects.get_or_create(user=user, defaults={"storico_fino_id": ultimo_id})
    letture = SistemaLogLettura.objects.filter(user=user, operazione_id=OuterRef("pk"))
    # Il menu rapido riguarda gli altri account; la cronologia resta completa.
    return operazioni_utente().exclude(utente=user).filter(pk__gt=stato.storico_fino_id).annotate(letta=Exists(letture))


def riepilogo_log(user):
    non_lette = nuove_operazioni(user).filter(letta=False)
    return {
        "log_operazioni_non_lette": non_lette.count(),
        "log_operazioni_recenti": list(non_lette.select_related("utente").order_by("-data_operazione", "-id")[:5]),
    }


def _return_url(request):
    url = request.POST.get("next") or request.GET.get("next") or reverse("cronologia_operazioni_sistema")
    if not url_has_allowed_host_and_scheme(url, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
        return reverse("cronologia_operazioni_sistema")
    return url


def _risposta(request, ids=()):
    dati = riepilogo_log(request.user)
    html = render_to_string("sistema/log_header.html", {
        **dati, "log_next_url": _return_url(request), "csrf_token": get_token(request),
    })
    return JsonResponse({"success": True, "non_lette": dati["log_operazioni_non_lette"], "html": html, "lette_ids": list(ids)})


@operational_admin_required
@never_cache
@require_GET
def stato_log_operazioni(request):
    return _risposta(request)


@operational_admin_required
@never_cache
@require_POST
def segna_log_operazione_letta(request, pk):
    operazione = get_object_or_404(nuove_operazioni(request.user), pk=pk)
    SistemaLogLettura.objects.get_or_create(user=request.user, operazione=operazione)
    if request.headers.get("Accept") == "application/json":
        return _risposta(request, [pk])
    return redirect(_return_url(request))


@operational_admin_required
@never_cache
@require_POST
def segna_tutti_log_operazioni_letti(request):
    with transaction.atomic():
        ids = list(nuove_operazioni(request.user).filter(letta=False).values_list("pk", flat=True))
        SistemaLogLettura.objects.bulk_create(
            [SistemaLogLettura(user=request.user, operazione_id=pk) for pk in ids],
            ignore_conflicts=True, batch_size=500,
        )
    if request.headers.get("Accept") == "application/json":
        return _risposta(request, ids)
    return redirect(_return_url(request))
