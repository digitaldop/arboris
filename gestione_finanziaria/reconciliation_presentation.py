"""Present alternatives together without splitting cumulative allocations."""
from collections import defaultdict
from datetime import date
from decimal import Decimal

from django.core.paginator import Paginator

from .reconciliation import _nodes


def target_key(rows):
    return tuple(sorted({(row["target_tipo"], row["target_id"]) for row in rows}))


def confidence_label(score):
    if score >= 90:
        return "Molto alta"
    if score >= 75:
        return "Alta"
    if score >= 50:
        return "Media"
    return "Bassa"


def prepare_proposal(record):
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
        record.destinazioni.append({
            **target, "importo_abbinato": amount,
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
    record.option_label = f"{record.compatibilita}/100 · " + " + ".join(option_labels)
    return record


def review_page(records, page_number, per_page=20):
    # Read only allocation identities across the view; fetch snapshots and audit
    # history for the displayed groups. A target's alternatives stay on one page.
    grouped_ids = {}
    for pk, rows in records.order_by("-compatibilita", "-pk").values_list("pk", "allocazioni").iterator(chunk_size=500):
        grouped_ids.setdefault(target_key(rows), []).append(pk)
    page = Paginator(list(grouped_ids.values()), per_page).get_page(page_number)
    ids = [pk for group in page.object_list for pk in group]
    proposals = {
        record.pk: prepare_proposal(record)
        for record in records.filter(pk__in=ids).prefetch_related("decisioni__utente")
    }
    groups = []
    for group_ids in page.object_list:
        options = [proposals[pk] for pk in group_ids if pk in proposals]
        if not options:
            continue
        groups.append({
            "id": options[0].pk, "proposte": options,
            "ids": ",".join(str(option.pk) for option in options),
        })
    return page, groups
