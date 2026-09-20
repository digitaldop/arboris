"""Payment overview for existing payslips, grouped by employee and month."""

from decimal import Decimal

from .models import BUSTA_PAGA_MONTH_CHOICES, StatoBustaPaga


ZERO = Decimal("0.00")
PAYMENT_FILTERS = (
    ("", "Tutti i pagamenti"),
    ("da_pagare", "Da pagare (anche parziali)"),
    ("pagata", "Pagate"),
    ("parziale", "Parzialmente pagate"),
    ("da_definire", "Importo da definire"),
)
AMOUNT_KEYS = ("dovuto", "pagato", "residuo", "eccedenza")


def payroll_periods(data_inizio, data_fine, mese=""):
    """Monthly payroll competences overlapping the selected date range.

    The thirteenth salary belongs to December of its own calendar year.
    """
    labels = dict(BUSTA_PAGA_MONTH_CHOICES)
    periodi = []
    start = data_inizio.year * 12 + data_inizio.month - 1
    end = data_fine.year * 12 + data_fine.month - 1
    for month_index in range(start, end + 1):
        year, month_zero = divmod(month_index, 12)
        month = month_zero + 1
        periodi.append((year, month, labels[month]))
        if month == 12:
            periodi.append((year, 13, labels[13]))
    return [periodo for periodo in periodi if not mese or str(periodo[1]) == mese]


def contract_seniority(contratti, data_riferimento):
    """Count distinct calendar months covered by contracts up to the cutoff."""
    per_dipendente = {}
    for contratto in contratti:
        inizio = contratto["data_inizio"]
        fine = min(contratto["data_fine"] or data_riferimento, data_riferimento)
        if inizio > fine:
            continue
        dato = per_dipendente.setdefault(contratto["dipendente_id"], {
            "data_inizio": inizio, "intervalli": [],
        })
        dato["data_inizio"] = min(dato["data_inizio"], inizio)
        dato["intervalli"].append((inizio.year * 12 + inizio.month, fine.year * 12 + fine.month))

    for dato in per_dipendente.values():
        intervalli = sorted(dato.pop("intervalli"))
        inizio, fine = intervalli[0]
        mesi = 0
        for prossimo_inizio, prossima_fine in intervalli[1:]:
            if prossimo_inizio <= fine + 1:
                fine = max(fine, prossima_fine)
            else:
                mesi += fine - inizio + 1
                inizio, fine = prossimo_inizio, prossima_fine
        dato["mesi"] = mesi + fine - inizio + 1
    return per_dipendente


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


def build_payroll_matrix(buste, periodi, stato_pagamento="", *, ordine="alfabetico", anzianita=None):
    """The caller supplies year/month columns and prefetched payment data."""
    colonne = [{"anno": anno, "mese": mese, "label": label, **_totals()} for anno, mese, label in periodi]
    colonne_per_periodo = {(colonna["anno"], colonna["mese"]): colonna for colonna in colonne}
    anzianita = anzianita or {}
    righe = {}
    totali = {
        **_totals(), "totale": 0, "pagate": 0, "parziali": 0,
        "da_pagare": 0, "da_definire": 0, "previste": 0, "residuo_previsto": ZERO,
    }
    for busta in buste:
        periodo = (busta.anno, busta.mese)
        if periodo not in colonne_per_periodo:
            continue
        cella = _payment_cell(busta)
        corrisponde = (
            not stato_pagamento
            or cella["stato"] == stato_pagamento
            or (stato_pagamento == "da_pagare" and cella["residuo"] > ZERO)
        )
        riga = righe.setdefault(busta.dipendente_id, {
            "dipendente": busta.dipendente, "celle_per_periodo": {},
            "anzianita": anzianita.get(busta.dipendente_id),
            "totale": 0, **_totals(),
        })
        riga["celle_per_periodo"][periodo] = cella if corrisponde else {"esclusa": True}
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
            colonne_per_periodo[periodo][key] += cella[key]
            totali[key] += cella[key]

    righe_visibili = []

    def ordine_riga(item):
        alfabetico = (item["dipendente"].cognome.casefold(), item["dipendente"].nome.casefold(), item["dipendente"].pk)
        if ordine == "anzianita":
            dato = item["anzianita"]
            return (dato is None, -(dato["mesi"] if dato else 0), *alfabetico)
        return alfabetico

    for riga in sorted(righe.values(), key=ordine_riga):
        if not riga["totale"]:
            continue
        celle_per_periodo = riga.pop("celle_per_periodo")
        riga["celle"] = [celle_per_periodo.get((colonna["anno"], colonna["mese"])) for colonna in colonne]
        righe_visibili.append(riga)
    return {"righe": righe_visibili, "colonne": colonne, "totali": totali,
            "num_colonne": len(colonne) + 2}
