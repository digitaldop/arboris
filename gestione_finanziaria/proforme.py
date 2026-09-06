"""Collegamento pro-forma/fattura senza ricreare pagamenti o movimenti bancari."""

import re
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from .models import (
    CollegamentoProforma, DocumentoFornitore, Fornitore, ScadenzaPagamentoFornitore,
    StatoDocumentoFornitore, StatoScadenzaFornitore, TipoDocumentoFornitore, VerificaProforma,
)

ZERO = Decimal("0.00")
CAMPI_IMPORTI = ("imponibile", "iva", "totale", "aliquota_iva", "imponibile_ritenuta_acconto", "aliquota_ritenuta_acconto", "ritenuta_acconto")


def preserva_importo_collegato(documento, originali=None):
    if originali is None:
        if not documento.proforma_origine_id:
            return {}
        return {campo: getattr(documento, campo) for campo in (*CAMPI_IMPORTI, "fornitore_id", "tipo_documento", "categoria_spesa_id", "anno_competenza", "mese_competenza", "stato")}
    if originali:
        if any(getattr(documento, campo) != originali[campo] for campo in CAMPI_IMPORTI):
            documento.external_payload = dict(documento.external_payload)
            documento.external_payload["_arboris_proforma_variazione"] = {campo: str(getattr(documento, campo)) for campo in CAMPI_IMPORTI}
        for campo, value in originali.items():
            setattr(documento, campo, value)


@transaction.atomic
def conferma_variazione_importi(fattura):
    from .services import aggiorna_stato_documento_da_scadenze

    fattura, _ = _blocca_documenti(fattura)
    variazione = fattura.external_payload.get("_arboris_proforma_variazione")
    if not fattura.proforma_origine_id or not variazione:
        raise ValidationError("Nessuna variazione da confermare.")
    for campo in CAMPI_IMPORTI:
        setattr(fattura, campo, Decimal(variazione[campo]))
    fattura.full_clean()
    _adegua_scadenze(_scadenze(fattura), netto_documento(fattura), fattura)
    fattura.external_payload.pop("_arboris_proforma_variazione")
    fattura.save()
    aggiorna_stato_documento_da_scadenze(fattura)
    return fattura


def netto_documento(documento):
    return max(documento.totale - documento.ritenuta_acconto, ZERO)


def proforme_aperte(fornitore_id):
    return DocumentoFornitore.objects.filter(
        fornitore_id=fornitore_id, tipo_documento=TipoDocumentoFornitore.PROFORMA,
        fattura_definitiva__isnull=True,
    ).exclude(stato__in=[StatoDocumentoFornitore.ANNULLATO, StatoDocumentoFornitore.COMPENSATO])


def _normalizza(value):
    return re.sub(r"\s+", " ", str(value or "")).strip().casefold()


def _riferimenti(payload):
    """Legge esclusivamente riferimenti tipizzati della fattura elettronica."""
    documenti, ordini = [], []

    def visita(value):
        if isinstance(value, list):
            for item in value:
                visita(item)
        elif isinstance(value, dict):
            for key, item in value.items():
                if key in {"DatiFattureCollegate", "DatiOrdineAcquisto"}:
                    for ref in item if isinstance(item, list) else [item]:
                        if isinstance(ref, dict) and ref.get("IdDocumento"):
                            target = documenti if key == "DatiFattureCollegate" else ordini
                            target.append((_normalizza(ref["IdDocumento"]), str(ref.get("Data") or "")[:10]))
                else:
                    visita(item)

    visita(payload)
    return set(documenti), set(ordini)


def candidati_proforma(fattura):
    riferimenti, ordini = _riferimenti(fattura.external_payload)
    testo = _normalizza(f"{fattura.descrizione} {fattura.descrizione_righe_fattura}")
    risultati = []
    for proforma in proforme_aperte(fattura.fornitore_id).exclude(pk=fattura.pk):
        numero = _normalizza(proforma.numero_documento)
        riferimento = any(numero == num and (not data or data == proforma.data_documento.isoformat()) for num, data in riferimenti)
        ordine = bool(proforma.riferimento_ordine) and any(_normalizza(proforma.riferimento_ordine) == num for num, _ in ordini)
        menzione = bool(re.search(r"\bpro[ -]?forma\s*(?:n[.°º]?\s*)?" + re.escape(numero) + r"(?![\w/-])", testo))
        importi_uguali = fattura.totale == proforma.totale and netto_documento(fattura) == netto_documento(proforma)
        if riferimento or ordine or menzione or importi_uguali:
            risultati.append({
                "proforma": proforma,
                # Testo libero e solo importo sono proposte: serve conferma.
                "automatico": (riferimento or ordine) and importi_uguali and len(riferimenti) <= 1 and len(ordini) <= 1,
                "motivo": "Riferimento alla pro-forma" if riferimento or menzione else ("Stesso ordine" if ordine else "Stesso fornitore e importo"),
                "netto": netto_documento(proforma), "pagato": proforma.importo_pagato,
            })
    return risultati


def documento_con_storico_proforma(documento):
    return CollegamentoProforma.objects.filter(Q(fattura=documento) | Q(proforma=documento)).exists()


def documento_bloccato_per_proforma(documento):
    return bool(documento.proforma_origine_id or documento.verifica_proforma in {
        VerificaProforma.DA_VERIFICARE, VerificaProforma.SOSTITUITA,
    })


def _blocca_documenti(fattura, proforma=None):
    # Anche l'import acquisisce questo lock: due fatture dello stesso fornitore
    # non possono aggiudicarsi contemporaneamente la stessa pro-forma.
    Fornitore.objects.select_for_update().get(pk=fattura.fornitore_id)
    ids = [fattura.pk] + ([proforma.pk] if proforma else [])
    docs = {doc.pk: doc for doc in DocumentoFornitore.objects.select_for_update().filter(pk__in=ids).order_by("pk")}
    if any(pk not in docs for pk in ids):
        raise ValidationError("Uno dei documenti non è più disponibile: aggiorna la pagina.")
    return docs[fattura.pk], docs.get(proforma.pk) if proforma else None


def _scadenze(documento):
    return list(documento.scadenze.select_for_update().order_by("data_scadenza", "pk"))


def _ha_pagamenti(scadenze):
    return any(s.importo_pagato or s.data_pagamento or s.movimento_finanziario_id or s.pagamenti.exists() for s in scadenze)


def _adegua_scadenze(scadenze, totale, documento):
    attive = [s for s in scadenze if s.stato != StatoScadenzaFornitore.ANNULLATA]
    if any(s.importo_pagato and s.stato == StatoScadenzaFornitore.ANNULLATA for s in scadenze):
        raise ValidationError("Una scadenza annullata contiene pagamenti: verifica i pagamenti prima del collegamento.")
    pagato = sum((s.importo_pagato for s in attive), ZERO)
    if pagato > totale:
        raise ValidationError("I pagamenti superano il netto del documento: verifica l'eccedenza prima di procedere.")
    if not attive:
        attive = [ScadenzaPagamentoFornitore(documento=documento, data_scadenza=documento.data_documento)]
        scadenze.extend(attive)
    differenza = totale - sum((s.importo_previsto for s in attive), ZERO)
    if differenza >= ZERO:
        attive[-1].importo_previsto += differenza
    else:
        for scadenza in reversed(attive):
            riduzione = min(max(scadenza.importo_previsto - scadenza.importo_pagato, ZERO), -differenza)
            scadenza.importo_previsto -= riduzione
            differenza += riduzione
    for scadenza in scadenze:
        scadenza.documento = documento
        scadenza.save()


@transaction.atomic
def collega_proforma(fattura, proforma, *, utente=None, automatico=False, conferma_differenza=False):
    from .services import aggiorna_stato_documento_da_scadenze

    fattura, proforma = _blocca_documenti(fattura, proforma)
    if fattura.proforma_origine_id == proforma.pk:
        return fattura  # Ripetere la stessa richiesta non modifica scadenze o storico.
    if fattura.pk == proforma.pk or fattura.tipo_documento not in {TipoDocumentoFornitore.FATTURA, TipoDocumentoFornitore.PARCELLA}:
        raise ValidationError("Seleziona una fattura definitiva e una pro-forma distinta.")
    if fattura.fornitore_id != proforma.fornitore_id or not proforme_aperte(fattura.fornitore_id).filter(pk=proforma.pk).exists():
        raise ValidationError("La pro-forma deve essere disponibile e dello stesso fornitore.")
    if fattura.proforma_origine_id or fattura.stato in {StatoDocumentoFornitore.ANNULLATO, StatoDocumentoFornitore.COMPENSATO}:
        raise ValidationError("Questa fattura non è disponibile per il collegamento.")
    uguali = fattura.totale == proforma.totale and netto_documento(fattura) == netto_documento(proforma)
    if not uguali and (automatico or not conferma_differenza):
        raise ValidationError("Gli importi differiscono: conferma il nuovo residuo prima di collegare.")
    scadenze_fattura = _scadenze(fattura)
    if _ha_pagamenti(scadenze_fattura):
        raise ValidationError("La fattura ha già pagamenti: verifica e rimuovi eventuali riconciliazioni duplicate prima di collegarla.")
    scadenze = _scadenze(proforma)
    snapshot = {
        "categoria_spesa_id": fattura.categoria_spesa_id,
        "anno_competenza": fattura.anno_competenza, "mese_competenza": fattura.mese_competenza,
        "scadenze_proforma": [{"id": s.pk, "previsto": str(s.importo_previsto), "scadenza": s.data_scadenza.isoformat()} for s in scadenze],
        "scadenze_fattura": [{"previsto": str(s.importo_previsto), "scadenza": s.data_scadenza.isoformat()} for s in scadenze_fattura],
        "netto_proforma": str(netto_documento(proforma)), "netto_fattura": str(netto_documento(fattura)),
    }
    fattura.scadenze.all().delete()  # Solo scadenze prive di pagamenti, controllate sopra.
    _adegua_scadenze(scadenze, netto_documento(fattura), fattura)
    fattura.proforma_origine = proforma
    fattura.verifica_proforma = VerificaProforma.COLLEGATA
    fattura.categoria_spesa = proforma.categoria_spesa
    fattura.anno_competenza, fattura.mese_competenza = proforma.anno_competenza, proforma.mese_competenza
    fattura.save()
    proforma.verifica_proforma = VerificaProforma.SOSTITUITA
    proforma.save(update_fields=["verifica_proforma", "data_aggiornamento"])
    CollegamentoProforma.objects.create(fattura=fattura, proforma=proforma, automatico=automatico, creato_da=utente, dati_originali=snapshot)
    aggiorna_stato_documento_da_scadenze(fattura)
    return fattura


@transaction.atomic
def annulla_collegamento_proforma(fattura, *, utente=None):
    from .services import aggiorna_stato_documento_da_scadenze

    fattura, _ = _blocca_documenti(fattura)
    if not fattura.proforma_origine_id:
        raise ValidationError("La fattura non ha un collegamento attivo.")
    proforma = DocumentoFornitore.objects.select_for_update().get(pk=fattura.proforma_origine_id)
    storico = fattura.storico_proforma.select_for_update().get(annullato_at__isnull=True)
    scadenze = _scadenze(fattura)
    originali = {row["id"]: row for row in storico.dati_originali["scadenze_proforma"]}
    for scadenza in scadenze:
        if scadenza.pk in originali:
            scadenza.importo_previsto = max(Decimal(originali[scadenza.pk]["previsto"]), scadenza.importo_pagato)
    _adegua_scadenze(scadenze, netto_documento(proforma), proforma)
    fattura.proforma_origine = None
    fattura.verifica_proforma = VerificaProforma.DA_VERIFICARE
    # L'ultimo import resta disponibile per la successiva verifica.
    variazione = fattura.external_payload.pop("_arboris_proforma_variazione", {})
    for campo in CAMPI_IMPORTI:
        if campo in variazione:
            setattr(fattura, campo, Decimal(variazione[campo]))
    for campo in ("categoria_spesa_id", "anno_competenza", "mese_competenza"):
        setattr(fattura, campo, storico.dati_originali.get(campo))
    fattura.stato = StatoDocumentoFornitore.DA_PAGARE
    fattura.save()
    proforma.verifica_proforma = ""
    proforma.save(update_fields=["verifica_proforma", "data_aggiornamento"])
    aggiorna_stato_documento_da_scadenze(proforma)
    storico.annullato_at, storico.annullato_da = timezone.now(), utente
    storico.save(update_fields=["annullato_at", "annullato_da"])
    return fattura


@transaction.atomic
def conferma_fattura_distinta(fattura, *, utente=None):
    from .fatture_in_cloud import _payment_deadlines, _sync_document_deadlines
    from .services import aggiorna_stato_documento_da_scadenze

    fattura, _ = _blocca_documenti(fattura)
    if fattura.proforma_origine_id or fattura.verifica_proforma == VerificaProforma.SOSTITUITA:
        raise ValidationError("Correggi prima il collegamento attivo.")
    if fattura.verifica_proforma != VerificaProforma.DA_VERIFICARE:
        raise ValidationError("La fattura non è in attesa di verifica.")
    fattura.verifica_proforma = VerificaProforma.DISTINTA
    fattura.save(update_fields=["verifica_proforma", "data_aggiornamento"])
    deadlines = _payment_deadlines(fattura.external_payload, fattura.external_type) if fattura.external_source else []
    if deadlines:
        _sync_document_deadlines(fattura, deadlines)
    elif not fattura.scadenze.exists():
        ScadenzaPagamentoFornitore.objects.create(documento=fattura, data_scadenza=fattura.data_documento, importo_previsto=netto_documento(fattura))
    aggiorna_stato_documento_da_scadenze(fattura)
    return fattura


def gestisci_proforma_importata(fattura, *, utente=None):
    """True quando lo scadenziario è già gestito dal flusso pro-forma."""
    if fattura.proforma_origine_id or fattura.verifica_proforma == VerificaProforma.DA_VERIFICARE:
        return True
    if fattura.verifica_proforma == VerificaProforma.DISTINTA or fattura.tipo_documento != TipoDocumentoFornitore.FATTURA:
        return False
    if fattura.stato in {StatoDocumentoFornitore.ANNULLATO, StatoDocumentoFornitore.COMPENSATO}:
        return False
    candidati = candidati_proforma(fattura)
    if not candidati or _ha_pagamenti(_scadenze(fattura)):
        return False
    if len(candidati) == 1 and candidati[0]["automatico"]:
        try:
            collega_proforma(fattura, candidati[0]["proforma"], utente=utente, automatico=True)
            fattura.refresh_from_db()
            return True
        except ValidationError:
            pass  # Una situazione contabile da verificare non interrompe l'import.
    fattura.scadenze.all().delete()
    fattura.verifica_proforma = VerificaProforma.DA_VERIFICARE
    fattura.save(update_fields=["verifica_proforma", "data_aggiornamento"])
    return True
