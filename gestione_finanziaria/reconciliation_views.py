from datetime import date
from decimal import Decimal
from itertools import groupby

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db.models import Max
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST

from .models import PropostaRiconciliazione, RichiestaAnalisiRiconciliazione
from .reconciliation import allowed_scopes, decide_proposal, pending_count, proposals_for_user, _nodes


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
    records = proposals_for_user(request.user).filter(ambito=scope, stato=state).prefetch_related("decisioni__utente").order_by("caso", "-compatibilita", "-pk")
    page = Paginator(records, 20).get_page(request.GET.get("pagina"))
    for record in page.object_list:
        record.righe = []
        record.totale = sum((Decimal(row["importo"]) for row in record.allocazioni), Decimal("0"))
        record.totale_centesimi = int(record.totale * 100)
        for row in record.allocazioni:
            movement = record.dati_verifica["movimenti"][str(row["movimento_id"])]
            target = record.dati_verifica["destinazioni"][f"{row['target_tipo']}:{row['target_id']}"]
            record.righe.append({
                **row, "movimento": movement, "destinazione": target,
                "data_movimento": date.fromisoformat(movement["data"]) if movement["data"] else None,
                "data_scadenza": date.fromisoformat(target["data"]) if target["data"] else None,
                "residuo_movimento": Decimal(movement["disponibile"]) - sum(
                    Decimal(other["importo"]) for other in record.allocazioni if other["movimento_id"] == row["movimento_id"]
                ),
                "residuo": Decimal(target["residuo"]) - sum(
                    Decimal(other["importo"]) for other in record.allocazioni
                    if other["target_tipo"] == row["target_tipo"] and other["target_id"] == row["target_id"]
                ),
            })
        record.conflict_nodes = ",".join(sorted(_nodes(record.allocazioni)))
    groups = [list(items) for _, items in groupby(page.object_list, key=lambda p: p.caso)]
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
    raw_ids = request.POST.getlist("proposte")
    single = request.POST.get("proposta")
    if single:
        raw_ids = [single]
    try:
        ids = list(dict.fromkeys(int(pk) for pk in raw_ids))
        if not ids or len(ids) > 40 or action not in {"conferma", "rifiuta", "riapri"}:
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
                successes += int(success)
                if not success:
                    errors.append(message)
            except ValidationError as exc:
                errors.extend(exc.messages)
        if successes:
            verb = {"conferma": "confermate", "rifiuta": "rifiutate", "riapri": "riaperte"}[action]
            messages.success(request, f"1 proposta {verb[:-1]}a." if successes == 1 else f"{successes} proposte {verb}.")
        for error in dict.fromkeys(errors):
            messages.warning(request, error)
    except (ValueError, ValidationError) as exc:
        messages.error(request, " ".join(exc.messages) if isinstance(exc, ValidationError) else "Selezione non valida.")
    url = reverse("proposte_riconciliazione") + f"?ambito={scope}"
    if request.POST.get("popup") == "1":
        url += "&popup=1"
    return redirect(url)
