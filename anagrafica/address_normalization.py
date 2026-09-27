"""Conservative address identity, version 1 (also used by migration 0009).

Do not change v1 semantics: introduce a new version and a data migration instead.
Territory IDs and complete house numbers are part of the identity. Unknown cities
or missing house numbers cannot establish a certain physical address.
"""
import hashlib
import json
import re
import unicodedata


def normalize_text(value):
    text = unicodedata.normalize("NFKC", str(value or "")).casefold()
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", text)).strip()


def normalize_house_number(value):
    text = unicodedata.normalize("NFKC", str(value or "")).strip().upper()
    text = re.sub(r"^(?:N(?:UMERO)?\.?|N°|Nº)\s*(?=\d)", "", text)
    text = re.sub(r"\s*/\s*", "/", text)
    text = re.sub(r"^(\d+)\s+([A-Z])$", r"\1/\2", text)
    text = re.sub(r"^(\d+)([A-Z])$", r"\1/\2", text)
    return re.sub(r"\s+", " ", text).strip(" ,")


def normalize_address(via, numero_civico=""):
    street = unicodedata.normalize("NFKC", str(via or "")).strip()
    number = normalize_house_number(numero_civico)
    # Only split a trailing explicit civic; retain street dates/names such as
    # 'Via 25 Aprile' and 'Strada Provinciale 25' when no civic is supplied.
    suffix = re.search(r"(?:\s*,\s*|\s+)(?:n(?:umero)?\.?\s*)?(\d+\s*(?:/\s*[A-Za-z]|[A-Za-z])?)$", street, re.I)
    if suffix:
        candidate = normalize_house_number(suffix.group(1))
        if number == candidate or (not number and not re.search(r"\b(?:provinciale|statale|regionale|sp)\b", street, re.I)):
            number = candidate
            street = street[:suffix.start()].rstrip(" ,")
    return normalize_text(street), number


def address_identity(via, numero_civico, citta_id, cap="", provincia_id=None, regione_id=None):
    street, number = normalize_address(via, numero_civico)
    if not street or not number or not citta_id:
        return street, number, None
    payload = ["v1", street, number, int(citta_id), str(cap or "").strip(), provincia_id, regione_id]
    key = hashlib.sha256(json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()
    return street, number, key
