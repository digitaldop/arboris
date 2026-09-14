"""Suggested allocations and explicit decisions. Analysis never writes payments."""
import hashlib
import json
from copy import copy
from collections import defaultdict
from decimal import Decimal

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from economia.models import RataIscrizione
from sistema.permissions import user_has_module_permission
from . import services
from .models import (
    DecisionePropostaRiconciliazione, Fornitore, MovimentoFinanziario,
    PropostaRiconciliazione, ScadenzaPagamentoFornitore, StatoAnalisiRiconciliazione,
)

S = PropostaRiconciliazione.Stato


def allowed_scopes(user):
    finance = user_has_module_permission(user, "gestione_finanziaria", "manage")
    economics = user_has_module_permission(user, "economia", "manage")
    return (["rate"] if finance or economics else []) + (["fornitore"] if finance else [])


def proposals_for_user(user):
    return PropostaRiconciliazione.objects.filter(ambito__in=allowed_scopes(user))


def pending_count(queryset):
    return queryset.filter(stato=S.APERTA).order_by().values("caso").distinct().count()


def _hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def _money(value):
    return format(Decimal(value or 0), ".2f")


def _day(value):
    return value.isoformat() if value else ""


def _bank_eligible(movement):
    return (
        movement.canale == "banca" and not movement.sostenuta_da_terzi
        and movement.valuta.upper() == "EUR" and bool(movement.importo)
        and movement.stato_riconciliazione != "ignorato"
        and not (movement.rata_iscrizione_id and not movement.riconciliazioni_rate.exists())
    )


def _target_eligible(target, kind):
    if kind == "rata":
        return not target.pagata and services.importo_rata_residuo(target) > 0
    doc = target.documento
    return (
        target.stato not in {"pagata", "annullata"}
        and doc.stato != "compensato" and doc.tipo_documento != "nota_credito"
        and doc.verifica_proforma not in {"da_verificare", "sostituita"}
        and services.importo_scadenza_fornitore_residuo(target) > 0
    )


def _load_objects(rows, *, lock=False):
    movement_ids = {row["movimento_id"] for row in rows}
    rate_ids = {row["target_id"] for row in rows if row["target_tipo"] == "rata"}
    deadline_ids = {row["target_id"] for row in rows if row["target_tipo"] == "scadenza_fornitore"}
    if lock:
        # Same order as supplier payments: suppliers, movements, then targets.
        suppliers = ScadenzaPagamentoFornitore.objects.filter(pk__in=deadline_ids).values("documento__fornitore_id")
        list(Fornitore.objects.select_for_update().filter(pk__in=suppliers).order_by("pk"))
        list(MovimentoFinanziario.objects.select_for_update().filter(pk__in=movement_ids).order_by("pk"))
        list(RataIscrizione.objects.select_for_update().filter(pk__in=rate_ids).order_by("pk"))
        list(ScadenzaPagamentoFornitore.objects.select_for_update().filter(pk__in=deadline_ids).order_by("pk"))
    movements = {m.pk: m for m in services._movimenti_per_matching(
        MovimentoFinanziario.objects.filter(pk__in=movement_ids).select_related("conto"),
    )}
    rates = RataIscrizione.objects.filter(pk__in=rate_ids).select_related(
        "iscrizione__studente", "iscrizione__anno_scolastico",
    ).prefetch_related("iscrizione__studente__relazioni_familiari__familiare__persona").in_bulk()
    deadlines = ScadenzaPagamentoFornitore.objects.filter(pk__in=deadline_ids).select_related("documento__fornitore").in_bulk()
    targets = {("rata", pk): obj for pk, obj in rates.items()}
    targets.update({("scadenza_fornitore", pk): obj for pk, obj in deadlines.items()})
    return movements, targets


def _describe(rows, *, lock=False, objects=None):
    movements, targets = objects if objects is not None else _load_objects(rows, lock=lock)
    snapshot = {"movimenti": {}, "destinazioni": {}}
    move_totals, target_totals = defaultdict(Decimal), defaultdict(Decimal)
    allocations = []
    for row in rows:
        movement = movements.get(row["movimento_id"])
        target_key = (row["target_tipo"], row["target_id"])
        target = targets.get(target_key)
        amount = Decimal(row["importo"])
        if not movement or not target or amount <= 0 or not _bank_eligible(movement) or not _target_eligible(target, target_key[0]):
            raise ValidationError("Proposta da aggiornare: movimento o scadenza non più disponibili.")
        if (movement.importo > 0) != (target_key[0] == "rata"):
            raise ValidationError("Il segno del movimento non è compatibile con la proposta.")
        move_totals[movement.pk] += amount
        target_totals[target_key] += amount
        available = services.importo_movimento_disponibile(movement)
        snapshot["movimenti"][str(movement.pk)] = {
            "conto": str(movement.conto) if movement.conto_id else "Conto non indicato",
            "conto_id": movement.conto_id, "data": _day(movement.data_contabile),
            "importo": _money(movement.importo), "disponibile": _money(available),
            "causale": movement.descrizione, "controparte": movement.controparte,
            "iban": movement.iban_controparte, "valuta": movement.valuta,
        }
        if target_key[0] == "rata":
            student = target.iscrizione.studente
            residual = services.importo_rata_residuo(target)
            info = {
                "intestatario": str(student), "riferimento": target.display_label,
                "codice_fiscale": student.codice_fiscale,
                "iscrizione_id": target.iscrizione_id, "anno": str(target.iscrizione.anno_scolastico),
                "familiari": sorted([str(link.familiare), link.familiare.codice_fiscale] for link in student.relazioni_familiari.all() if link.attivo),
            }
        else:
            residual = services.importo_scadenza_fornitore_residuo(target)
            info = {
                "intestatario": str(target.documento.fornitore),
                "riferimento": target.documento.numero_documento or str(target.documento),
                "documento_id": target.documento_id, "fornitore_id": target.documento.fornitore_id,
                "iban": target.documento.fornitore.iban,
                "totale_documento": _money(target.documento.totale),
            }
        info.update(data=_day(target.data_scadenza), residuo=_money(residual))
        snapshot["destinazioni"][f"{target_key[0]}:{target.pk}"] = info
        if move_totals[movement.pk] > available or target_totals[target_key] > residual:
            raise ValidationError("Proposta da aggiornare: gli importi disponibili sono cambiati.")
        allocations.append((movement, target, target_key[0], amount))
    return snapshot, allocations


def _rows(proposal):
    amounts = defaultdict(Decimal)
    for item in proposal.allocazioni:
        amounts[(item.movimento.pk, item.target_tipo, item.target.pk)] += item.importo
    return [
        {"movimento_id": m, "target_tipo": kind, "target_id": t, "importo": _money(amount)}
        for (m, kind, t), amount in sorted(amounts.items()) if amount > 0
    ]


def _nodes(rows):
    nodes = set()
    for row in rows:
        nodes.add(f"movimento:{row['movimento_id']}")
        nodes.add(f"{row['target_tipo']}:{row['target_id']}")
    return nodes


def regroup_cases():
    records = list(PropostaRiconciliazione.objects.filter(stato=S.APERTA).only("pk", "allocazioni", "caso"))
    parents = {}

    def root(node):
        parents.setdefault(node, node)
        while parents[node] != node:
            parents[node] = parents[parents[node]]
            node = parents[node]
        return node

    for record in records:
        nodes = sorted(_nodes(record.allocazioni))
        for node in nodes[1:]:
            left, right = root(nodes[0]), root(node)
            parents[max(left, right)] = min(left, right)
    changed = []
    for record in records:
        case = root(min(_nodes(record.allocazioni)))
        if record.caso != case:
            record.caso = case
            changed.append(record)
    PropostaRiconciliazione.objects.bulk_update(changed, ["caso"], batch_size=500)


def _affected_query(tipo, pk):
    if tipo == "movimento":
        return Q(allocazioni__contains=[{"movimento_id": pk}])
    kind = "rata" if tipo == "rata" else "scadenza_fornitore"
    return Q(allocazioni__contains=[{"target_tipo": kind, "target_id": pk}])


def invalidate_changed(queryset):
    records = list(queryset.filter(stato=S.APERTA))
    objects = _load_objects([row for record in records for row in record.allocazioni]) if records else None
    for record in records:
        try:
            snapshot, _ = _describe(record.allocazioni, objects=objects)
            valid = snapshot == record.dati_verifica
        except ValidationError:
            valid = False
        if not valid:
            PropostaRiconciliazione.objects.filter(pk=record.pk, stato=S.APERTA).update(stato=S.SUPERATA, data_aggiornamento=timezone.now())


def analyse_request(tipo, pk):
    from .models import RichiestaAnalisiRiconciliazione

    if tipo in {"documento", "fornitore", "iscrizione", "studente", "familiare", "persona"}:
        if tipo in {"iscrizione", "studente", "familiare", "persona"}:
            lookup = {
                "iscrizione": "iscrizione_id", "studente": "iscrizione__studente_id",
                "familiare": "iscrizione__studente__relazioni_familiari__familiare_id",
                "persona": "iscrizione__studente__relazioni_familiari__familiare__persona_id",
            }[tipo]
            children = RataIscrizione.objects.filter(**{lookup: pk}).distinct()
            kind = "rata"
        else:
            children = ScadenzaPagamentoFornitore.objects.filter(**{
                "documento_id" if tipo == "documento" else "documento__fornitore_id": pk,
            })
            kind = "scadenza"
        RichiestaAnalisiRiconciliazione.objects.bulk_create([
            RichiestaAnalisiRiconciliazione(tipo=kind, oggetto_id=child_id)
            for child_id in children.values_list("pk", flat=True)
        ], ignore_conflicts=True, batch_size=500)
        return

    proposals = []
    seen_targets = set()

    def from_target(target, kind):
        key = (kind, target.pk)
        if key in seen_targets or not _target_eligible(target, kind):
            return []
        seen_targets.add(key)
        if kind == "rata":
            return services.proposte_riconciliazione_da_rata(target, [target], bank_only=True)
        return services.proposte_riconciliazione_da_scadenza_fornitore(target, bank_only=True)

    def from_movement(movement):
        if not _bank_eligible(movement):
            return []
        available = services.importo_movimento_disponibile(movement)
        if available <= 0:
            return []
        candidate = copy(movement)
        # Match the remaining credit, not the original transfer amount. This
        # temporary instance is never saved; stored snapshots use fresh rows.
        if movement.importo > 0:
            candidate.importo = available
        candidate._arboris_importo_disponibile_cache = available
        return services.proposte_riconciliazione_da_movimento(candidate)

    if tipo == "movimento":
        movement = MovimentoFinanziario.objects.filter(pk=pk).first()
        if movement:
            proposals.extend(from_movement(movement))
            for proposal in list(proposals):
                for allocation in proposal.allocazioni:
                    proposals.extend(from_target(allocation.target, allocation.target_tipo))
    else:
        model = RataIscrizione if tipo == "rata" else ScadenzaPagamentoFornitore
        target = model.objects.filter(pk=pk).first()
        if target:
            proposals.extend(from_target(target, "rata" if tipo == "rata" else "scadenza_fornitore"))
            movements = {item.movimento.pk: item.movimento for p in proposals for item in p.allocazioni}
            for movement in movements.values():
                proposals.extend(from_movement(movement))

    invalidate_changed(PropostaRiconciliazione.objects.filter(_affected_query(tipo, pk)))
    seen = set()
    prepared = [(proposal, _rows(proposal)) for proposal in proposals]
    objects = _load_objects([row for _, rows in prepared for row in rows]) if prepared else None
    for proposal, rows in prepared:
        if not rows:
            continue
        # Identity survives amount changes; the version key below includes amounts
        # and all material facts. Neither key depends on search direction.
        match = _hash([[row["movimento_id"], row["target_tipo"], row["target_id"]] for row in rows])
        if match in seen:
            continue
        seen.add(match)
        try:
            snapshot, _ = _describe(rows, objects=objects)
        except ValidationError:
            continue
        key = _hash([rows, snapshot])
        reasons = list(proposal.motivazioni)
        if PropostaRiconciliazione.objects.filter(abbinamento=match).exclude(chiave=key).exists():
            reasons.append("Dati aggiornati rispetto a una proposta precedente.")
        PropostaRiconciliazione.objects.filter(abbinamento=match, stato=S.APERTA).exclude(chiave=key).update(stato=S.SUPERATA)
        record, created = PropostaRiconciliazione.objects.get_or_create(
            chiave=key,
            defaults={
                "abbinamento": match, "caso": min(_nodes(rows)), "ambito": proposal.kind,
                "compatibilita": proposal.score_percentuale, "motivazioni": list(dict.fromkeys(reasons)),
                "allocazioni": rows, "dati_verifica": snapshot,
            },
        )
        if not created and record.stato in {S.SUPERATA, S.CONFERMATA}:
            # An annulled payment may make the original allocation available again.
            record.stato = S.APERTA
            record.save(update_fields=["stato", "data_aggiornamento"])
    regroup_cases()


@transaction.atomic
def decide_proposal(pk, action, *, user):
    if action not in {"conferma", "rifiuta", "riapri"}:
        raise ValidationError("Azione non valida.")
    # Rejecting a suggestion does not touch bank balances or run analysis. Only
    # confirmations/reopening need to wait for the matching worker's global lock.
    if action != "rifiuta":
        StatoAnalisiRiconciliazione.objects.get_or_create(pk=1)
        StatoAnalisiRiconciliazione.objects.select_for_update().get(pk=1)
    record = PropostaRiconciliazione.objects.select_for_update().get(pk=pk)
    if record.ambito not in allowed_scopes(user):
        raise PermissionDenied
    if action == "rifiuta" and record.stato == S.RIFIUTATA:
        return True, "Proposta già rifiutata."
    if action == "riapri" and record.stato != S.RIFIUTATA:
        raise ValidationError("La proposta non è rifiutata.")
    if action != "riapri" and record.stato != S.APERTA:
        return False, "Proposta già gestita o da aggiornare. Nessuna nuova registrazione."

    if action in {"conferma", "riapri"}:
        try:
            snapshot, allocations = _describe(record.allocazioni, lock=True)
            if snapshot != record.dati_verifica:
                raise ValidationError("Proposta da aggiornare: i dati sono cambiati dopo l'analisi.")
        except ValidationError as exc:
            record.stato = S.SUPERATA
            record.save(update_fields=["stato", "data_aggiornamento"])
            from .reconciliation_queue import enqueue_analysis

            for row in record.allocazioni:
                enqueue_analysis("movimento", row["movimento_id"])
            regroup_cases()
            return False, " ".join(exc.messages)
        if action == "conferma":
            proposal = services.crea_proposta_riconciliazione(
                kind=record.ambito, direction="review", allocazioni=allocations,
            )
            services.applica_proposta_riconciliazione(proposal, utente=user, note="Proposta confermata dall'utente")
    record.stato = {"conferma": S.CONFERMATA, "rifiuta": S.RIFIUTATA, "riapri": S.APERTA}[action]
    record.save(update_fields=["stato", "data_aggiornamento"])
    DecisionePropostaRiconciliazione.objects.create(proposta=record, azione=action, utente=user)
    if action == "conferma":
        query = Q(pk__in=[])
        for row in record.allocazioni:
            query |= _affected_query("movimento", row["movimento_id"])
            query |= _affected_query("rata" if row["target_tipo"] == "rata" else "scadenza", row["target_id"])
        invalidate_changed(PropostaRiconciliazione.objects.filter(query))
    if action != "rifiuta":
        regroup_cases()
    return True, {"conferma": "Riconciliazione registrata.", "rifiuta": "Proposta rifiutata.", "riapri": "Proposta riaperta."}[action]
