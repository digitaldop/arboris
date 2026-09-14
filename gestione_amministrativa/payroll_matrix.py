"""Payment overview for existing payslips, grouped by employee and month."""

from decimal import Decimal

from .models import StatoBustaPaga


ZERO = Decimal("0.00")
PAYMENT_FILTERS = (
    ("", "Tutti i pagamenti"),
    ("da_pagare", "Da pagare (anche parziali)"),
    ("pagata", "Pagate"),
    ("parziale", "Parzialmente pagate"),
    ("da_definire", "Importo da definire"),
)
AMOUNT_KEYS = ("dovuto", "pagato", "residuo", "eccedenza")


def _totals():
    return dict.fromkeys(AMOUNT_KEYS, ZERO)


def _payment_cell(busta):
    pagamenti = list(busta.pagamenti.all())
    dovuto = busta.importo_netto_riepilogo
    # Preserve the legacy full-payment markers, but never let them override
    # explicit partial allocations or count a cumulative bank transfer twice.
    pagato = sum((pagamento.importo for pagamento in pagamenti), ZERO)
    pagamento_segnato = bool(busta.movimento_pagamento_id or busta.data_pagamento_effettiva)
    if not pagato and pagamento_segnato:
        pagato = dovuto
    residuo = max(dovuto - pagato, ZERO)
    if (dovuto > ZERO and pagato >= dovuto) or (dovuto <= ZERO and pagamento_segnato):
        stato, label = "pagata", "Pagata"
    elif dovuto <= ZERO:
        stato, label = "da_definire", "Importo da definire"
    elif pagato > ZERO:
        stato, label = "parziale", "Parziale"
    else:
        stato, label = "non_pagata", "Da pagare"

    date_pagamenti = [pagamento.data_pagamento for pagamento in pagamenti]
    if not date_pagamenti:
        if busta.data_pagamento_effettiva:
            date_pagamenti.append(busta.data_pagamento_effettiva)
        elif busta.movimento_pagamento_id:
            date_pagamenti.append(busta.movimento_pagamento.data_contabile)

    return {
        "busta": busta,
        "dovuto": dovuto,
        "pagato": pagato,
        "residuo": residuo,
        "eccedenza": max(pagato - dovuto, ZERO),
        "stato": stato,
        "stato_label": label,
        "data_pagamento": max(date_pagamenti) if date_pagamenti else None,
        "prevista": not busta.netto_effettivo and bool(busta.netto_previsto),
        "bozza": busta.stato == StatoBustaPaga.BOZZA,
    }


def build_payroll_matrix(buste, mesi, stato_pagamento=""):
    """The caller supplies one year, related employees and prefetched payments."""
    colonne = [{"mese": mese, "label": label, **_totals()} for mese, label in mesi]
    colonne_per_mese = {colonna["mese"]: colonna for colonna in colonne}
    righe = {}
    totali = {
        **_totals(), "totale": 0, "pagate": 0, "parziali": 0,
        "da_pagare": 0, "da_definire": 0, "previste": 0, "residuo_previsto": ZERO,
    }
    for busta in buste:
        if busta.mese not in colonne_per_mese:
            continue
        cella = _payment_cell(busta)
        corrisponde = (
            not stato_pagamento
            or cella["stato"] == stato_pagamento
            or (stato_pagamento == "da_pagare" and cella["residuo"] > ZERO)
        )
        riga = righe.setdefault(busta.dipendente_id, {
            "dipendente": busta.dipendente, "celle_per_mese": {},
            "totale": 0, **_totals(),
        })
        riga["celle_per_mese"][busta.mese] = cella if corrisponde else {"esclusa": True}
        if not corrisponde:
            continue
        riga["totale"] += 1
        totali["totale"] += 1
        totali["pagate"] += cella["stato"] == "pagata"
        totali["parziali"] += cella["stato"] == "parziale"
        totali["da_pagare"] += cella["residuo"] > ZERO
        totali["da_definire"] += cella["stato"] == "da_definire"
        if cella["prevista"]:
            totali["previste"] += 1
            totali["residuo_previsto"] += cella["residuo"]
        for key in AMOUNT_KEYS:
            riga[key] += cella[key]
            colonne_per_mese[busta.mese][key] += cella[key]
            totali[key] += cella[key]

    righe_visibili = []
    for riga in sorted(righe.values(), key=lambda item: (
        item["dipendente"].cognome.casefold(), item["dipendente"].nome.casefold(),
        item["dipendente"].pk,
    )):
        if not riga["totale"]:
            continue
        celle_per_mese = riga.pop("celle_per_mese")
        riga["celle"] = [celle_per_mese.get(colonna["mese"]) for colonna in colonne]
        righe_visibili.append(riga)
    return {"righe": righe_visibili, "colonne": colonne, "totali": totali,
            "num_colonne": len(colonne) + 2}
