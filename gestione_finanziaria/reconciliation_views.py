from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Max
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST

from .models import PropostaRiconciliazione, RichiestaAnalisiRiconciliazione
from .reconciliation import allowed_scopes, decide_proposal, pending_count, proposals_for_user, _nodes
from .reconciliation_presentation import review_page


def _scope(request):
    scopes = allowed_scopes(request.user)
    if not scopes:
        raise PermissionDenied
    scope = request.GET.get("ambito") or request.POST.get("ambito") or scopes[0]
    if scope not in scopes:
        raise PermissionDenied
    return scopes, scope


@login_required
@require_GET
@never_cache
def status(request):
    _scope(request)
    records = proposals_for_user(request.user)
    queue = RichiestaAnalisiRiconciliazione.objects
    return JsonResponse({
        "count": pending_count(records),
        "revision": records.aggregate(revision=Max("data_aggiornamento"))["revision"],
        "analisi_in_corso": queue.exists(),
        "analisi_rinviata": queue.exclude(errore="").exists(),
    })


@login_required
@require_GET
@never_cache
def review(request):
    scopes, scope = _scope(request)
    state = request.GET.get("stato", PropostaRiconciliazione.Stato.APERTA)
    if state not in PropostaRiconciliazione.Stato.values:
        state = PropostaRiconciliazione.Stato.APERTA
    records = proposals_for_user(request.user).filter(ambito=scope, stato=state)
    page, groups = review_page(records, request.GET.get("pagina"))
    popup = request.GET.get("popup") == "1"
    return render(request, "gestione_finanziaria/proposte_riconciliazione.html", {
        "base_template": "popup_base.html" if popup else "base.html",
        "popup": popup, "ambito": scope, "stato": state, "stati": PropostaRiconciliazione.Stato.choices,
        "gruppi": groups, "pagina": page,
        "tabs": [(kind, "Rette" if kind == "rate" else "Fornitori") for kind in scopes],
        "totale_casi": pending_count(proposals_for_user(request.user)),
        "current_module_view_only": False, "can_manage_current_module": True,
        "analysis_pending": RichiestaAnalisiRiconciliazione.objects.exists(),
        "analysis_error": RichiestaAnalisiRiconciliazione.objects.exclude(errore="").exists(),
    })


@login_required
@require_POST
def decide(request):
    _, scope = _scope(request)
    action = request.POST.get("azione")
    json_request = "application/json" in request.headers.get("Accept", "")
    raw_ids = request.POST.getlist("proposte")
    single = request.POST.get("proposta")
    if single:
        raw_ids = [single]
    decision = request.POST.get("decisione", "")
    if decision:
        action, _, selection = decision.partition(":")
        raw_ids = selection.split(",")
    results = []
    try:
        ids = list(dict.fromkeys(int(pk) for pk in raw_ids))
        if not ids or len(ids) > (400 if action == "rifiuta" else 40) or action not in {"conferma", "rifiuta", "riapri"}:
            raise ValidationError("Seleziona le proposte da gestire.")
        records = list(proposals_for_user(request.user).filter(pk__in=ids, ambito=scope))
        if len(records) != len(ids):
            raise PermissionDenied
        if action == "conferma":
            seen = set()
            for record in records:
                nodes = _nodes(record.allocazioni)
                if seen.intersection(nodes):
                    raise ValidationError("Le proposte selezionate contengono alternative. Scegli un solo abbinamento per gli stessi movimenti o scadenze.")
                seen.update(nodes)
        successes, errors = 0, []
        for record in records:
            try:
                success, message = decide_proposal(record.pk, action, user=request.user)
                results.append({"id": record.pk, "success": success, "message": message})
                successes += int(success)
                if not success:
                    errors.append(message)
            except ValidationError as exc:
                errors.extend(exc.messages)
                results.append({"id": record.pk, "success": False, "message": " ".join(exc.messages)})
        if json_request:
            return JsonResponse({"results": results, "errors": list(dict.fromkeys(errors))})
        if successes:
            verb = {"conferma": "confermate", "rifiuta": "rifiutate", "riapri": "riaperte"}[action]
            messages.success(request, f"1 proposta {verb[:-1]}a." if successes == 1 else f"{successes} proposte {verb}.")
        for error in dict.fromkeys(errors):
            messages.warning(request, error)
    except (ValueError, ValidationError) as exc:
        error = " ".join(exc.messages) if isinstance(exc, ValidationError) else "Selezione non valida."
        if json_request:
            return JsonResponse({"results": [], "errors": [error]}, status=400)
        messages.error(request, error)
    url = reverse("proposte_riconciliazione") + f"?ambito={scope}"
    if request.POST.get("popup") == "1":
        url += "&popup=1"
    return redirect(url)
