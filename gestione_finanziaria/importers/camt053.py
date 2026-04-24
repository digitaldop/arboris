"""
Parser ISO 20022 CAMT.053 (Bank to Customer Statement).

Supporta le varianti di namespace piu' diffuse (camt.053.001.02/.06/.08).
E' pensato per estratti conto SEPA emessi dalle banche italiane ed europee;
estrae dal messaggio XML le entry (``<Ntry>``) convertendole in
:class:`ParsedMovimento`.

Note implementative:
- usiamo ``xml.etree.ElementTree`` della stdlib per evitare dipendenze esterne;
- il parser localizza i namespace in modo dinamico (non hardcoded) cosi'
  da tollerare piccole differenze di versione;
- per il segno dell'importo si usa ``CdtDbtInd`` (``DBIT`` = uscita,
  ``CRDT`` = entrata). Le entry con stato ``PDNG`` (pending) vengono incluse
  per default (possono poi essere filtrate lato UI in iterazioni successive).
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Iterator, List, Optional, Tuple

from .base import BaseParser, ParsedMovimento


_LOCAL_TAG_RE = re.compile(r"^\{[^}]+\}(?P<name>.+)$")


def _localname(tag: str) -> str:
    match = _LOCAL_TAG_RE.match(tag)
    if match:
        return match.group("name")
    return tag


def _find_child(element: ET.Element, name: str) -> Optional[ET.Element]:
    for child in element:
        if _localname(child.tag) == name:
            return child
    return None


def _find_descendant(element: ET.Element, path: List[str]) -> Optional[ET.Element]:
    current: Optional[ET.Element] = element
    for step in path:
        if current is None:
            return None
        current = _find_child(current, step)
    return current


def _find_all_children(element: ET.Element, name: str) -> List[ET.Element]:
    return [child for child in element if _localname(child.tag) == name]


def _text(element: Optional[ET.Element]) -> str:
    if element is None or element.text is None:
        return ""
    return element.text.strip()


def _parse_date(valore: str) -> Optional[date]:
    if not valore:
        return None
    testo = valore.strip()
    # Tronchiamo eventuale timezone (+02:00 o Z) per semplificare il parsing.
    if len(testo) > 19 and testo[19] in "+-":
        testo = testo[:19]
    elif testo.endswith("Z"):
        testo = testo[:-1]
    for fmt in (
        "%Y-%m-%dT%H:%M:%S.%f",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d",
    ):
        try:
            return datetime.strptime(testo, fmt).date()
        except ValueError:
            continue
    # Ultimo tentativo: prendiamo solo la parte data iniziale.
    if len(testo) >= 10:
        try:
            return datetime.strptime(testo[:10], "%Y-%m-%d").date()
        except ValueError:
            return None
    return None


def _extract_entry_date(entry: ET.Element, tag: str) -> Optional[date]:
    """Recupera una data dall'entry, gestendo sia ``<Dt>`` che ``<DtTm>``."""

    node = _find_child(entry, tag)
    if node is None:
        return None
    for child_name in ("Dt", "DtTm"):
        child = _find_child(node, child_name)
        if child is not None and child.text:
            parsed = _parse_date(child.text)
            if parsed:
                return parsed
    return None


def _extract_descrizione(entry: ET.Element) -> str:
    """
    La descrizione nei messaggi CAMT.053 puo' trovarsi in piu' posti:
    - NtryDtls/TxDtls/RmtInf/Ustrd (remittance info unstructured);
    - AddtlNtryInf a livello di entry.
    Raccogliamo entrambi concatenati per massimizzare il contesto.
    """

    parti: List[str] = []

    add_info = _find_child(entry, "AddtlNtryInf")
    if add_info is not None and add_info.text:
        parti.append(add_info.text.strip())

    for ntry_dtls in _find_all_children(entry, "NtryDtls"):
        for tx_dtls in _find_all_children(ntry_dtls, "TxDtls"):
            rmt_inf = _find_child(tx_dtls, "RmtInf")
            if rmt_inf is None:
                continue
            for ustrd in _find_all_children(rmt_inf, "Ustrd"):
                if ustrd.text:
                    parti.append(ustrd.text.strip())

    testo = " | ".join(parte for parte in parti if parte)
    return testo


def _extract_controparte(entry: ET.Element, cdt_dbt: str) -> tuple[str, str]:
    """Restituisce (nome_controparte, iban_controparte)."""

    nome = ""
    iban = ""

    for ntry_dtls in _find_all_children(entry, "NtryDtls"):
        for tx_dtls in _find_all_children(ntry_dtls, "TxDtls"):
            rltd_pties = _find_child(tx_dtls, "RltdPties")
            if rltd_pties is None:
                continue

            soggetto_tag = "Dbtr" if cdt_dbt == "CRDT" else "Cdtr"
            conto_tag = "DbtrAcct" if cdt_dbt == "CRDT" else "CdtrAcct"

            soggetto = _find_child(rltd_pties, soggetto_tag)
            if soggetto is not None:
                nome_node = _find_child(soggetto, "Nm")
                if nome_node is None:
                    pty = _find_child(soggetto, "Pty")
                    if pty is not None:
                        nome_node = _find_child(pty, "Nm")
                nome = _text(nome_node) or nome

            conto = _find_child(rltd_pties, conto_tag)
            if conto is not None:
                id_node = _find_child(conto, "Id")
                iban_node = _find_child(id_node, "IBAN") if id_node is not None else None
                iban = _text(iban_node) or iban

            if nome or iban:
                return nome, iban

    return nome, iban


def _extract_transaction_id(entry: ET.Element) -> str:
    acct_svcr_ref = _find_child(entry, "AcctSvcrRef")
    if acct_svcr_ref is not None and acct_svcr_ref.text:
        return acct_svcr_ref.text.strip()

    for ntry_dtls in _find_all_children(entry, "NtryDtls"):
        for tx_dtls in _find_all_children(ntry_dtls, "TxDtls"):
            refs = _find_child(tx_dtls, "Refs")
            if refs is not None:
                for candidate in ("AcctSvcrRef", "EndToEndId", "InstrId", "TxId"):
                    node = _find_child(refs, candidate)
                    if node is not None and node.text:
                        return node.text.strip()
    return ""


class Camt053Parser(BaseParser):
    nome_formato = "camt053"

    def parse(self, raw_bytes: bytes) -> Iterator[ParsedMovimento]:
        if not raw_bytes:
            return iter(())

        try:
            root = ET.fromstring(raw_bytes)
        except ET.ParseError as exc:
            raise ValueError(f"XML CAMT.053 non valido: {exc}") from None

        document_children = list(root)
        stmt_root = None
        if _localname(root.tag) == "Document":
            for child in document_children:
                if _localname(child.tag) == "BkToCstmrStmt":
                    stmt_root = child
                    break
        elif _localname(root.tag) == "BkToCstmrStmt":
            stmt_root = root

        if stmt_root is None:
            raise ValueError("Struttura XML non riconosciuta: manca <BkToCstmrStmt>.")

        movimenti: List[ParsedMovimento] = []
        for stmt in _find_all_children(stmt_root, "Stmt"):
            for entry in _find_all_children(stmt, "Ntry"):
                movimento = self._parse_entry(entry)
                if movimento is not None:
                    movimenti.append(movimento)
        return iter(movimenti)

    def _parse_entry(self, entry: ET.Element) -> Optional[ParsedMovimento]:
        amt_node = _find_child(entry, "Amt")
        if amt_node is None or not amt_node.text:
            return None

        importo_abs = Decimal(amt_node.text.strip())
        valuta = amt_node.attrib.get("Ccy", "EUR")

        cdt_dbt = _text(_find_child(entry, "CdtDbtInd")) or "CRDT"
        segno = Decimal("-1") if cdt_dbt == "DBIT" else Decimal("1")
        importo = (importo_abs * segno).quantize(Decimal("0.01"))

        data_contabile = _extract_entry_date(entry, "BookgDt")
        data_valuta = _extract_entry_date(entry, "ValDt")
        if data_contabile is None:
            data_contabile = data_valuta

        if data_contabile is None:
            return None

        descrizione = _extract_descrizione(entry)
        controparte, iban_controparte = _extract_controparte(entry, cdt_dbt)
        tx_id = _extract_transaction_id(entry)

        return ParsedMovimento(
            data_contabile=data_contabile,
            data_valuta=data_valuta,
            importo=importo,
            valuta=valuta,
            descrizione=descrizione,
            controparte=controparte,
            iban_controparte=iban_controparte,
            provider_transaction_id=tx_id,
        ).clean()


# =========================================================================
#  Helper pubblici per metadati dello Stmt (IBAN del conto, saldo CLBD)
# =========================================================================


@dataclass
class SaldoEstrattoCamt:
    importo: Decimal
    data: Optional[date]
    tipo_codice: str  # es. "CLBD", "OPBD", "PRCD"
    valuta: str = "EUR"


def _parse_stmt_root(raw_bytes: bytes) -> Optional[ET.Element]:
    if not raw_bytes:
        return None
    try:
        root = ET.fromstring(raw_bytes)
    except ET.ParseError:
        return None
    if _localname(root.tag) == "Document":
        for child in root:
            if _localname(child.tag) == "BkToCstmrStmt":
                return child
        return None
    if _localname(root.tag) == "BkToCstmrStmt":
        return root
    return None


def estrai_iban_da_camt053(raw_bytes: bytes) -> str:
    """
    Ritorna l'IBAN del conto riferito dal messaggio CAMT.053
    (``Stmt/Acct/Id/IBAN``). Stringa vuota se il file e' invalido o l'IBAN
    non e' presente. L'output e' uppercase e privo di spazi.
    """

    stmt_root = _parse_stmt_root(raw_bytes)
    if stmt_root is None:
        return ""
    for stmt in _find_all_children(stmt_root, "Stmt"):
        acct = _find_child(stmt, "Acct")
        if acct is None:
            continue
        acct_id = _find_child(acct, "Id")
        if acct_id is None:
            continue
        iban_node = _find_child(acct_id, "IBAN")
        iban = _text(iban_node)
        if iban:
            return iban.replace(" ", "").upper()
    return ""


def estrai_saldo_da_camt053(
    raw_bytes: bytes,
    *,
    codice_preferito: str = "CLBD",
) -> Optional[SaldoEstrattoCamt]:
    """
    Estrae dal CAMT.053 il saldo ``<Bal>`` identificato da ``codice_preferito``
    (default ``CLBD`` = Closing Booked, i.e. saldo di fine giornata contabile).

    Se non trova il codice preferito, prova in ordine: ``CLAV`` (Closing
    Available), ``PRCD`` (Previously Closed Booked), ``OPBD`` (Opening Booked).
    Ritorna ``None`` se nessun saldo e' leggibile.
    """

    stmt_root = _parse_stmt_root(raw_bytes)
    if stmt_root is None:
        return None

    fallback_order = [codice_preferito, "CLAV", "PRCD", "OPBD"]
    saldi_per_codice: dict = {}

    for stmt in _find_all_children(stmt_root, "Stmt"):
        for bal in _find_all_children(stmt, "Bal"):
            codice = _estrai_codice_bal(bal)
            saldo = _parse_bal(bal, codice)
            if saldo is not None:
                # Conserviamo l'ultimo saldo con quel codice (se il file
                # contiene piu' Stmt manteniamo il piu' recente nella
                # sequenza XML, che di norma e' l'ultima giornata).
                saldi_per_codice[codice] = saldo

    for codice in fallback_order:
        if codice in saldi_per_codice:
            return saldi_per_codice[codice]
    # Nessun codice noto: ritorniamo il primo disponibile se c'e'.
    if saldi_per_codice:
        return next(iter(saldi_per_codice.values()))
    return None


def _estrai_codice_bal(bal: ET.Element) -> str:
    tp = _find_child(bal, "Tp")
    if tp is None:
        return ""
    cd_or_prtry = _find_child(tp, "CdOrPrtry")
    if cd_or_prtry is None:
        return ""
    cd = _find_child(cd_or_prtry, "Cd")
    if cd is not None and cd.text:
        return cd.text.strip().upper()
    prtry = _find_child(cd_or_prtry, "Prtry")
    if prtry is not None and prtry.text:
        return prtry.text.strip().upper()
    return ""


def _parse_bal(bal: ET.Element, codice: str) -> Optional[SaldoEstrattoCamt]:
    amt_node = _find_child(bal, "Amt")
    if amt_node is None or not amt_node.text:
        return None
    try:
        importo_abs = Decimal(amt_node.text.strip())
    except Exception:
        return None
    valuta = amt_node.attrib.get("Ccy", "EUR")
    cdt_dbt = _text(_find_child(bal, "CdtDbtInd")) or "CRDT"
    segno = Decimal("-1") if cdt_dbt == "DBIT" else Decimal("1")
    importo = (importo_abs * segno).quantize(Decimal("0.01"))
    data_saldo = _extract_entry_date(bal, "Dt")
    return SaldoEstrattoCamt(
        importo=importo,
        data=data_saldo,
        tipo_codice=codice or "",
        valuta=valuta,
    )
