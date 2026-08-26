from decimal import Decimal, ROUND_HALF_UP

from django.db.models import Q

from .models import (
    BustaPagaDipendente,
    ContrattoDipendente,
    Dipendente,
    ParametroCalcoloStipendio,
    ScenarioValorePayroll,
    SimulazioneCostoDipendente,
    StatoBustaPaga,
    TipoVocePayroll,
    VoceBustaPaga,
    busta_paga_data_riferimento,
)


CENT = Decimal("0.01")
ZERO = Decimal("0.00")
ONE_HUNDRED = Decimal("100.00")


def money(value):
    return (value or ZERO).quantize(CENT, rounding=ROUND_HALF_UP)


def percentuale(importo, aliquota):
    return money((importo or ZERO) * (aliquota or ZERO) / ONE_HUNDRED)


def periodo_bounds(anno, mese):
    data_riferimento = busta_paga_data_riferimento(anno, mese)
    return data_riferimento.replace(day=1), data_riferimento


def compensi_lavorativi_dipendente(dipendente, limite=24):
    if not dipendente or not getattr(dipendente, "pk", None):
        return []

    from gestione_finanziaria.models import DocumentoFornitore

    buste = (
        dipendente.buste_paga.select_related("contratto", "contratto__tipo_contratto")
        .prefetch_related("documenti")
        .order_by("-anno", "-mese", "-id")[:limite]
    )
    documenti_fornitore = (
        DocumentoFornitore.objects.select_related("fornitore", "categoria_spesa", "fornitore__categoria_spesa")
        .filter(fornitore__dipendente_collegato=dipendente)
        .order_by("-data_documento", "-id")[:limite]
    )

    compensi = []
    for busta in buste:
        compensi.append(
            {
                "tipo": "busta",
                "oggetto": busta,
                "data": busta_paga_data_riferimento(busta.anno, busta.mese),
                "titolo": busta.periodo_label,
                "stato": busta.get_stato_display(),
                "importo": busta.importo_netto_riepilogo,
                "importo_secondario": busta.costo_azienda_riepilogo if busta.ha_costo_azienda_riepilogo else ZERO,
                "valuta": busta.valuta,
            }
        )

    for documento in documenti_fornitore:
        compensi.append(
            {
                "tipo": "documento_fornitore",
                "oggetto": documento,
                "data": documento.data_documento,
                "titolo": f"{documento.get_tipo_documento_display()} {documento.numero_documento}".strip(),
                "stato": documento.get_stato_display(),
                "importo": documento.totale_da_pagare,
                "importo_secondario": documento.totale,
                "valuta": "EUR",
            }
        )

    return sorted(compensi, key=lambda item: (item["data"], item["titolo"]), reverse=True)[:limite]


def contratto_applicabile(dipendente, anno, mese):
    inizio_periodo, fine_periodo = periodo_bounds(anno, mese)
    return (
        ContrattoDipendente.objects.filter(dipendente=dipendente, attivo=True)
        .filter(data_inizio__lte=fine_periodo)
        .filter(Q(data_fine__isnull=True) | Q(data_fine__gte=inizio_periodo))
        .order_by("-data_inizio", "-id")
        .first()
    )


def parametro_applicabile(anno, mese):
    inizio_periodo, fine_periodo = periodo_bounds(anno, mese)
    return (
        ParametroCalcoloStipendio.objects.filter(attivo=True, valido_dal__lte=fine_periodo)
        .filter(Q(valido_al__isnull=True) | Q(valido_al__gte=inizio_periodo))
        .order_by("-valido_dal", "-id")
        .first()
    )


def simulazione_costo_applicabile(contratto, anno, mese):
    if not contratto:
        return None
    inizio_periodo, fine_periodo = periodo_bounds(anno, mese)
    return (
        SimulazioneCostoDipendente.objects.filter(contratto=contratto, attiva=True)
        .filter(valido_dal__lte=fine_periodo)
        .filter(Q(valido_al__isnull=True) | Q(valido_al__gte=inizio_periodo))
        .order_by("-valido_dal", "-id")
        .first()
    )


def _previsione_da_simulazione(contratto, simulazione):
    return {
        "contratto": contratto,
        "parametro": None,
        "simulazione": simulazione,
        "lordo_previsto": money(simulazione.lordo_mensile),
        "contributi_datore_previsti": money(simulazione.contributi_datore_totali),
        "contributi_dipendente_previsti": money(simulazione.contributi_dipendente_totali),
        "rateo_tredicesima_previsto": money(simulazione.costo_mensilita_aggiuntive),
        "rateo_tfr_previsto": money(simulazione.trattamento_fine_rapporto),
        "altri_oneri_previsti": money(simulazione.altri_oneri_previsti_totali),
        "netto_previsto": money(simulazione.netto_mensile),
        "costo_azienda_previsto": money(simulazione.costo_azienda_mensile),
    }


def calcola_previsione_busta_paga(dipendente, anno, mese, contratto=None, parametro=None):
    contratto = contratto or contratto_applicabile(dipendente, anno, mese)
    if not contratto:
        raise ValueError("Non esiste un contratto attivo applicabile al periodo selezionato.")

    simulazione = simulazione_costo_applicabile(contratto, anno, mese)
    if simulazione:
        return _previsione_da_simulazione(contratto, simulazione)

    parametro = parametro or contratto.parametro_calcolo or parametro_applicabile(anno, mese)

    lordo = money(contratto.retribuzione_lorda_totale_mensile)
    mensilita_extra = max((contratto.mensilita_annue or Decimal("12.00")) - Decimal("12.00"), ZERO)
    rateo_mensilita = money(lordo * mensilita_extra / Decimal("12.00"))

    aliquota_datore = getattr(parametro, "aliquota_contributi_datore", ZERO) if parametro else ZERO
    aliquota_dipendente = getattr(parametro, "aliquota_contributi_dipendente", ZERO) if parametro else ZERO
    aliquota_tfr = getattr(parametro, "aliquota_tfr", ZERO) if parametro else ZERO
    aliquota_inail = getattr(parametro, "aliquota_inail", ZERO) if parametro else ZERO
    aliquota_altri_oneri = getattr(parametro, "aliquota_altri_oneri", ZERO) if parametro else ZERO

    contributi_datore = percentuale(lordo, aliquota_datore)
    contributi_dipendente = percentuale(lordo, aliquota_dipendente)
    rateo_tfr = percentuale(lordo, aliquota_tfr)
    quota_inail = percentuale(lordo, aliquota_inail)
    altri_oneri = percentuale(lordo, aliquota_altri_oneri)
    totale_altri_oneri = money(quota_inail + altri_oneri)
    netto = money(lordo - contributi_dipendente)
    costo_azienda = money(lordo + contributi_datore + rateo_mensilita + rateo_tfr + totale_altri_oneri)

    return {
        "contratto": contratto,
        "parametro": parametro,
        "lordo_previsto": lordo,
        "contributi_datore_previsti": contributi_datore,
        "contributi_dipendente_previsti": contributi_dipendente,
        "rateo_tredicesima_previsto": rateo_mensilita,
        "rateo_tfr_previsto": rateo_tfr,
        "altri_oneri_previsti": totale_altri_oneri,
        "netto_previsto": netto,
        "costo_azienda_previsto": costo_azienda,
    }


def crea_o_aggiorna_previsione_busta_paga(dipendente, anno, mese):
    if not isinstance(dipendente, Dipendente):
        dipendente = Dipendente.objects.get(pk=dipendente)

    previsione = calcola_previsione_busta_paga(dipendente, anno, mese)
    busta, _ = BustaPagaDipendente.objects.get_or_create(
        dipendente=dipendente,
        anno=anno,
        mese=mese,
        defaults={
            "contratto": previsione["contratto"],
            "stato": StatoBustaPaga.PREVISTA,
            "valuta": previsione["contratto"].valuta,
        },
    )
    busta.contratto = previsione["contratto"]
    busta.stato = StatoBustaPaga.EFFETTIVA if busta.ha_effettivo else StatoBustaPaga.PREVISTA
    busta.valuta = previsione["contratto"].valuta
    for field_name, value in previsione.items():
        if field_name in {"contratto", "parametro", "simulazione"}:
            continue
        setattr(busta, field_name, value)
    simulazione = previsione.get("simulazione")
    parametro = previsione.get("parametro")
    if simulazione:
        busta.note_previsione = f"Previsione generata dalla simulazione costo: {simulazione}."
    elif parametro:
        busta.note_previsione = f"Previsione calcolata con parametro: {parametro}."
    busta.save()

    VoceBustaPaga.objects.filter(
        busta_paga=busta,
        scenario=ScenarioValorePayroll.PREVISTO,
        codice__in=[
            "LORDO",
            "CONTR_DAT",
            "CONTR_DIP",
            "RATEO_MENS",
            "RATEO_TFR",
            "ALTRI_ONERI",
            "NETTO_SIM",
            "COSTO_SIM",
        ],
    ).delete()
    voci = [
        ("LORDO", TipoVocePayroll.RETRIBUZIONE, "Retribuzione lorda prevista", previsione["lordo_previsto"], 10),
        ("CONTR_DAT", TipoVocePayroll.CONTRIBUTO_DATORE, "Contributi datore previsti", previsione["contributi_datore_previsti"], 20),
        ("CONTR_DIP", TipoVocePayroll.CONTRIBUTO_DIPENDENTE, "Contributi dipendente previsti", previsione["contributi_dipendente_previsti"], 30),
        ("RATEO_MENS", TipoVocePayroll.TREDICESIMA, "Rateo mensilita aggiuntive previsto", previsione["rateo_tredicesima_previsto"], 40),
        ("RATEO_TFR", TipoVocePayroll.TFR, "Rateo TFR previsto", previsione["rateo_tfr_previsto"], 50),
        ("ALTRI_ONERI", TipoVocePayroll.ONERE, "Altri oneri previsti", previsione["altri_oneri_previsti"], 60),
    ]
    if simulazione:
        voci.extend(
            [
                (
                    "NETTO_SIM",
                    TipoVocePayroll.RETRIBUZIONE,
                    "Retribuzione netta prevista da simulazione",
                    previsione["netto_previsto"],
                    70,
                ),
                (
                    "COSTO_SIM",
                    TipoVocePayroll.ONERE,
                    "Totale costo azienda previsto da simulazione",
                    previsione["costo_azienda_previsto"],
                    80,
                ),
            ]
        )
    VoceBustaPaga.objects.bulk_create(
        [
            VoceBustaPaga(
                busta_paga=busta,
                scenario=ScenarioValorePayroll.PREVISTO,
                codice=codice,
                tipo_voce=tipo_voce,
                descrizione=descrizione,
                importo=money(importo),
                importo_unitario=money(importo),
                ordine=ordine,
            )
            for codice, tipo_voce, descrizione, importo, ordine in voci
        ]
    )
    return busta
