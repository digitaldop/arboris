"""Present alternatives together without splitting cumulative allocations."""
from collections import defaultdict
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from django.core.paginator import Paginator
from economia.models import RataIscrizione

from .reconciliation import _nodes
from .reconciliation_periods import MONTHS, rate_movement_evidence


def target_key(rows):
    return tuple(sorted({(row["target_tipo"], row["target_id"]) for row in rows}))


def review_group_key(scope, rows):
    if scope == "rate":
        # Keep cumulative proposals atomic, including those with several credits.
        return scope, tuple(sorted({row["movimento_id"] for row in rows}))
    return scope, target_key(rows)


def confidence_label(score):
    if score >= 90:
        return "Molto alta"
    if score >= 75:
        return "Alta"
    if score >= 50:
        return "Media"
    return "Bassa"


def prepare_proposal(record, rates=None):
    rates = rates or {}
    record.period_rank = (4, 99999)
    if record.ambito == "rate" and len(record.allocazioni) == 1:
        row = record.allocazioni[0]
        rate = rates.get(row["target_id"])
        movement = record.dati_verifica["movimenti"][str(row["movimento_id"])]
        if rate:
            ceiling, record.period_rank, reason = rate_movement_evidence(rate, SimpleNamespace(
                data_contabile=date.fromisoformat(movement["data"]) if movement["data"] else None,
                descrizione=movement["causale"],
            ))
            # Old snapshots remain valid for confirmation; only display ranking
            # is refreshed while the background analysis catches up.
            record.compatibilita = min(record.compatibilita, ceiling)
            record.motivazioni = list(dict.fromkeys([*record.motivazioni, reason]))
    target_totals, movement_totals = defaultdict(Decimal), defaultdict(Decimal)
    for row in record.allocazioni:
        target_totals[f"{row['target_tipo']}:{row['target_id']}"] += Decimal(row["importo"])
        movement_totals[str(row["movimento_id"])] += Decimal(row["importo"])
    record.totale = sum(movement_totals.values(), Decimal("0"))
    record.totale_centesimi = int(record.totale * 100)
    record.conflict_nodes = ",".join(sorted(_nodes(record.allocazioni)))
    record.compatibilita_label = confidence_label(record.compatibilita)
    record.destinazioni, record.movimenti = [], []
    for key, amount in target_totals.items():
        target = record.dati_verifica["destinazioni"][key]
        rate = rates.get(int(key.split(":")[1])) if key.startswith("rata:") else None
        period = ""
        if rate and rate.tipo_rata == "mensile" and 1 <= rate.mese_riferimento <= 12:
            period = f"{MONTHS[rate.mese_riferimento - 1]} {rate.anno_riferimento}"
        record.destinazioni.append({
            **target, "importo_abbinato": amount, "periodo": period,
            "data_scadenza": date.fromisoformat(target["data"]) if target["data"] else None,
            "residuo_successivo": Decimal(target["residuo"]) - amount,
        })
    option_labels = []
    for key, amount in movement_totals.items():
        movement = record.dati_verifica["movimenti"][key]
        movement_date = date.fromisoformat(movement["data"]) if movement["data"] else None
        record.movimenti.append({
            **movement, "id": key, "importo_abbinato": amount, "data_movimento": movement_date,
            "residuo_successivo": Decimal(movement["disponibile"]) - amount,
        })
        formatted_amount = f"{Decimal(movement['importo']):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        label = " · ".join(filter(None, [
            movement_date.strftime("%d/%m/%Y") if movement_date else "",
            movement["controparte"] or movement["causale"][:65] or movement["conto"],
            f"€ {formatted_amount}", f"#{key}",
        ]))
        option_labels.append(label)
    if record.ambito == "rate":
        option_labels = [" · ".join(filter(None, [
            target["intestatario"], target["riferimento"], target["periodo"] or target.get("anno"),
            "scad. " + target["data_scadenza"].strftime("%d/%m/%Y") if target["data_scadenza"] else "",
            "da saldare € " + f"{Decimal(target['residuo']):.2f}".replace(".", ","),
        ])) for target in record.destinazioni]
    record.option_label = f"{record.compatibilita}/100 · " + " + ".join(option_labels)
    return record


def review_page(records, page_number, per_page=20):
    # Read only allocation identities across the view; fetch snapshots and audit
    # history for the displayed groups. Alternatives stay on the same page.
    grouped_ids = {}
    for pk, scope, rows in records.order_by("-compatibilita", "-pk").values_list("pk", "ambito", "allocazioni").iterator(chunk_size=500):
        grouped_ids.setdefault(review_group_key(scope, rows), []).append(pk)
    page = Paginator(list(grouped_ids.values()), per_page).get_page(page_number)
    ids = [pk for group in page.object_list for pk in group]
    page_records = list(records.filter(pk__in=ids).prefetch_related("decisioni__utente"))
    rate_ids = {row["target_id"] for record in page_records for row in record.allocazioni if row["target_tipo"] == "rata"}
    rates = RataIscrizione.objects.filter(pk__in=rate_ids).only(
        "pk", "tipo_rata", "anno_riferimento", "mese_riferimento", "data_scadenza",
    ).in_bulk()
    proposals = {record.pk: prepare_proposal(record, rates) for record in page_records}
    groups = []
    for group_ids in page.object_list:
        options = [proposals[pk] for pk in group_ids if pk in proposals]
        if not options:
            continue
        if options[0].ambito == "rate":
            options.sort(key=lambda option: (-option.compatibilita, option.period_rank, option.pk))
        groups.append({
            "id": options[0].pk, "proposte": options,
            "ids": ",".join(str(option.pk) for option in options),
        })
    return page, groups
