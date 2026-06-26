from __future__ import annotations

import hashlib
import time
import re
import unicodedata
from datetime import timedelta
from decimal import Decimal, InvalidOperation
from json import JSONDecodeError
from pathlib import PurePosixPath
from urllib.parse import unquote, urlencode, urlparse

import requests
from django.conf import settings
from django.core.files.base import ContentFile
from django.core.exceptions import ValidationError
from django.db import transaction
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime
from django.utils.text import get_valid_filename

from .models import (
    EsitoSincronizzazione,
    FattureInCloudConnessione,
    FattureInCloudSyncLog,
    Fornitore,
    OrigineDocumentoFornitore,
    ScadenzaPagamentoFornitore,
    StatoConnessioneFattureInCloud,
    StatoDocumentoFornitore,
    StatoScadenzaFornitore,
    TipoDocumentoFornitore,
    TipoSyncFattureInCloud,
    DocumentoFornitore,
    DocumentoFornitoreImportAlias,
)
from .security import cifra_testo, decifra_testo_safe
from .services import (
    aggiorna_stato_documento_da_scadenze,
    crea_notifica_finanziaria,
    riconcilia_movimento_con_scadenza_fornitore,
    trova_movimenti_candidati_per_scadenza_fornitore,
)
from .fatture_in_cloud_xml import (
    content_kind,
    document_data_from_e_invoice_xml,
    download_bytes,
    extension_from_name,
    supplier_from_e_invoice_xml,
    xml_text_from_bytes,
)


FIC_SOURCE = "fatture_in_cloud"
DEFAULT_BASE_URL = "https://api-v2.fattureincloud.it"
AUTHORIZATION_URL = "https://api-v2.fattureincloud.it/oauth/authorize"
TOKEN_URL = "https://api-v2.fattureincloud.it/oauth/token"
RECEIVED_DOCUMENT_TYPES = ("expense", "passive_credit_note")
PENDING_DOCUMENT_TYPES = ("agyo", "mail", "browser")
FIC_CREDIT_NOTE_TYPES = {
    "credit",
    "credit_note",
    "passive_credit_note",
    "nota_credito",
    "nota di credito",
    "td04",
    "td08",
}
DEFAULT_SCOPES = "received_documents:r entity.suppliers:r"
DEFAULT_API_CONNECT_TIMEOUT_SECONDS = 3.0
DEFAULT_API_READ_TIMEOUT_SECONDS = 6.0
DEFAULT_SYNC_MAX_SECONDS = 18.0
DEFAULT_ATTACHMENT_MAX_BYTES = 20 * 1024 * 1024
SUPPLIER_DETAILS_SCOPE_WARNING = (
    "Dati anagrafici completi dei fornitori non disponibili: "
    "ricollega Fatture in Cloud autorizzando anche la lettura dei fornitori."
)
FIC_AUTO_MATCH_MIN_SCORE = 85
PAYMENT_PAID_STATUSES = {
    "paid",
    "payed",
    "paid_in_full",
    "pagata",
    "pagato",
    "saldata",
    "saldato",
    "saldate",
    "saldati",
    "settled",
    "completed",
    "complete",
}
PAYMENT_PARTIAL_STATUSES = {
    "partially_paid",
    "partial",
    "partially_payed",
    "parzialmente_pagata",
    "parzialmente_pagato",
    "pagata_parzialmente",
    "pagato_parzialmente",
}
SUPPLIER_LEGAL_SUFFIXES = {
    "SRL",
    "SPA",
    "SAPA",
    "SAS",
    "SNC",
    "SS",
    "COOP",
    "COOPERATIVA",
    "SCARL",
    "IMPRESA",
    "INDIVIDUALE",
    "DITTA",
}
SUPPLIER_PLACEHOLDER_NAME_KEYS = {
    "FORNITORE NON IDENTIFICATO",
    "FATTURA DA REGISTRARE",
    "DOCUMENTO DA REGISTRARE",
}


class FattureInCloudError(Exception):
    pass


class FattureInCloudSyncBudgetExceeded(FattureInCloudError):
    pass


def _positive_float_setting(name, default):
    value = getattr(settings, name, default)
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _api_timeout():
    connect_timeout = _positive_float_setting(
        "FATTURE_IN_CLOUD_API_CONNECT_TIMEOUT_SECONDS",
        DEFAULT_API_CONNECT_TIMEOUT_SECONDS,
    )
    read_timeout = _positive_float_setting(
        "FATTURE_IN_CLOUD_API_READ_TIMEOUT_SECONDS",
        DEFAULT_API_READ_TIMEOUT_SECONDS,
    )
    return (max(connect_timeout, 0.1), max(read_timeout, 0.1))


def _sync_max_seconds():
    value = _positive_float_setting("FATTURE_IN_CLOUD_SYNC_MAX_SECONDS", DEFAULT_SYNC_MAX_SECONDS)
    return value if value > 0 else None


def _attachment_max_bytes():
    value = getattr(settings, "FATTURE_IN_CLOUD_ATTACHMENT_MAX_BYTES", DEFAULT_ATTACHMENT_MAX_BYTES)
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = DEFAULT_ATTACHMENT_MAX_BYTES
    return max(parsed, 1024)


def oauth_env_configured():
    return bool(
        getattr(settings, "FATTURE_IN_CLOUD_OAUTH_CLIENT_ID", "")
        and getattr(settings, "FATTURE_IN_CLOUD_OAUTH_CLIENT_SECRET", "")
    )


def configured_oauth_client_id(connessione: FattureInCloudConnessione | None = None):
    if connessione and connessione.client_id:
        return connessione.client_id.strip()
    return (getattr(settings, "FATTURE_IN_CLOUD_OAUTH_CLIENT_ID", "") or "").strip()


def configured_oauth_client_secret(connessione: FattureInCloudConnessione | None = None):
    if connessione and connessione.client_secret_cifrato:
        secret = decifra_testo_safe(connessione.client_secret_cifrato)
        if secret:
            return secret
    return (getattr(settings, "FATTURE_IN_CLOUD_OAUTH_CLIENT_SECRET", "") or "").strip()


def has_oauth_credentials(connessione: FattureInCloudConnessione | None = None):
    return bool(configured_oauth_client_id(connessione) and configured_oauth_client_secret(connessione))


def configured_oauth_redirect_uri():
    return (getattr(settings, "FATTURE_IN_CLOUD_OAUTH_REDIRECT_URI", "") or "").strip()


def _as_decimal(value) -> Decimal:
    if value in (None, ""):
        return Decimal("0.00")
    try:
        return Decimal(str(value)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        return Decimal("0.00")


def _as_date(value):
    if not value:
        return None
    if hasattr(value, "date") and not isinstance(value, str):
        return value.date() if hasattr(value, "hour") else value
    parsed = parse_date(str(value)[:10])
    if parsed:
        return parsed
    parsed_dt = parse_datetime(str(value))
    if parsed_dt:
        return parsed_dt.date()
    return None


def _as_datetime(value):
    if not value:
        return None
    parsed = parse_datetime(str(value))
    if parsed and timezone.is_naive(parsed):
        return timezone.make_aware(parsed)
    return parsed


def _clean_identifier(value):
    return "".join(ch for ch in (value or "").upper().strip() if ch.isalnum())


def _clean_vat_identifier(value):
    identifier = _clean_identifier(value)
    if identifier.startswith("IT") and len(identifier) > 11:
        identifier = identifier[2:]
    return identifier


def _normalizza_testo_match(value):
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = re.sub(r"[^A-Za-z0-9]+", " ", text).upper()
    return re.sub(r"\s+", " ", text).strip()


def _normalizza_nome_fornitore_match(value):
    text = _normalizza_testo_match(value)
    if not text:
        return ""
    legal_forms = (
        (r"\bS R L\b", "SRL"),
        (r"\bS P A\b", "SPA"),
        (r"\bS A P A\b", "SAPA"),
        (r"\bS A S\b", "SAS"),
        (r"\bS N C\b", "SNC"),
        (r"\bS C A R L\b", "SCARL"),
    )
    for pattern, replacement in legal_forms:
        text = re.sub(pattern, replacement, text)
    tokens = [token for token in text.split() if token not in SUPPLIER_LEGAL_SUFFIXES]
    return " ".join(tokens) or text


def _normalizza_numero_documento_match(value):
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = re.sub(r"[^A-Za-z0-9]+", "", text).upper()
    if text.isdigit():
        return text.lstrip("0") or "0"
    return text


def _same_money(first, second):
    return _as_decimal(first) == _as_decimal(second)


def _as_dict(value):
    return value if isinstance(value, dict) else {}


def _as_list(value):
    if not value:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _first_present(*values):
    for value in values:
        if value not in (None, ""):
            return value
    return ""


def _nested_dict(data, *keys):
    current = _as_dict(data)
    for key in keys:
        current = _as_dict(current.get(key))
        if not current:
            return {}
    return current


def _dict_value(data, *keys):
    data = _as_dict(data)
    if not data:
        return None
    for key in keys:
        if key in data:
            return data.get(key)

    lowered = {str(key).lower(): value for key, value in data.items()}
    for key in keys:
        value = lowered.get(str(key).lower())
        if value is not None:
            return value
    return None


def _normalizza_spazi(value):
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _unique_text_values(values, *, limit=None):
    seen = set()
    result = []
    for value in values:
        text = _normalizza_spazi(value)
        if not text:
            continue
        normalized = text.casefold()
        if normalized in seen:
            continue
        seen.add(normalized)
        result.append(text)
        if limit and len(result) >= limit:
            break
    return result


def _e_invoice_header(e_invoice):
    return _as_dict(
        _dict_value(
            e_invoice,
            "FatturaElettronicaHeader",
            "fattura_elettronica_header",
            "fatturaElettronicaHeader",
            "header",
        )
    )


def _e_invoice_bodies(e_invoice):
    body = _dict_value(
        e_invoice,
        "FatturaElettronicaBody",
        "fattura_elettronica_body",
        "fatturaElettronicaBody",
        "body",
    )
    return [_as_dict(item) for item in _as_list(body) if isinstance(item, dict)]


def _document_general_data(e_invoice):
    candidates = [
        _nested_dict(e_invoice, "dati_generali", "dati_generali_documento"),
        _nested_dict(e_invoice, "DatiGenerali", "DatiGeneraliDocumento"),
    ]
    for body in _e_invoice_bodies(e_invoice):
        candidates.extend(
            [
                _nested_dict(body, "dati_generali", "dati_generali_documento"),
                _nested_dict(body, "DatiGenerali", "DatiGeneraliDocumento"),
            ]
        )
    for candidate in candidates:
        if candidate:
            return candidate
    return {}


def _limit_model_field(model, field_name, value):
    if value in (None, ""):
        return ""
    field = model._meta.get_field(field_name)
    max_length = getattr(field, "max_length", None)
    value = str(value)
    return value[:max_length] if max_length else value


def _attachment_url_from_item(item):
    item = _as_dict(item)
    return (
        item.get("url")
        or item.get("download_url")
        or item.get("attachment_url")
        or item.get("downloadUrl")
        or ""
    )


def _primary_attachment_source(document_data):
    url = document_data.get("attachment_url") or document_data.get("attachment_preview_url") or ""
    if url:
        return {
            "url": url,
            "filename": (
                document_data.get("filename")
                or document_data.get("attachment_filename")
                or document_data.get("attachment_name")
                or ""
            ),
            "source": "attachment_url" if document_data.get("attachment_url") else "attachment_preview_url",
        }

    for index, attachment in enumerate(document_data.get("other_attachments") or []):
        url = _attachment_url_from_item(attachment)
        if url:
            return {
                "url": url,
                "filename": attachment.get("filename") or attachment.get("name") or "",
                "source": f"other_attachments[{index}]",
            }
    return {}


def _extension_from_content(data, content_type):
    kind = content_kind(data or b"", content_type or "")
    if kind == "pdf":
        return ".pdf"
    if kind == "xml_like" or kind == "binary_with_embedded_xml":
        return ".xml"
    if kind == "zip":
        return ".zip"
    if kind == "binary_p7m_like":
        return ".p7m"
    content_type = (content_type or "").lower()
    if "pdf" in content_type:
        return ".pdf"
    if "xml" in content_type:
        return ".xml"
    if "zip" in content_type:
        return ".zip"
    if "pkcs7" in content_type or "p7m" in content_type:
        return ".p7m"
    return ".bin"


def _attachment_filename(documento, document_data, attachment_source, data, download_info):
    raw_name = (
        attachment_source.get("filename")
        or document_data.get("filename")
        or PurePosixPath(unquote(urlparse(attachment_source.get("url") or "").path)).name
    )
    ext = extension_from_name(raw_name) or extension_from_name(attachment_source.get("url"))
    if not ext:
        ext = _extension_from_content(data, download_info.get("content_type", ""))

    numero = re.sub(r"[^A-Za-z0-9._-]+", "_", documento.numero_documento or "")
    external_id = re.sub(r"[^A-Za-z0-9._-]+", "_", documento.external_id or str(document_data.get("id") or ""))
    base = numero or external_id or "documento"
    filename = get_valid_filename(f"FIC_{external_id}_{base}{ext}")
    return filename[:180]


def _external_payload_with_attachment_result(documento, attachment_result):
    payload = dict(documento.external_payload or {})
    payload["_arboris_attachment_import"] = attachment_result
    documento.external_payload = payload


def _salva_allegato_fatture_in_cloud(documento, document_data):
    if documento.allegato:
        return {"saved": False, "skipped": "already_present"}

    attachment_source = _primary_attachment_source(document_data)
    if not attachment_source:
        return {"saved": False, "skipped": "missing_url"}

    data, download_info = download_bytes(
        attachment_source["url"],
        timeout=_api_timeout(),
        max_bytes=_attachment_max_bytes(),
    )
    if data is None:
        return {
            "saved": False,
            "source": attachment_source.get("source", ""),
            "download": download_info,
            "error": "download_failed",
        }
    if download_info.get("truncated"):
        return {
            "saved": False,
            "source": attachment_source.get("source", ""),
            "download": download_info,
            "error": "attachment_too_large",
        }

    filename = _attachment_filename(documento, document_data, attachment_source, data, download_info)
    documento.allegato.save(filename, ContentFile(data), save=False)
    return {
        "saved": True,
        "source": attachment_source.get("source", ""),
        "filename": filename,
        "storage_name": documento.allegato.name,
        "download": download_info,
    }


def _response_json(response, error_prefix):
    try:
        return response.json()
    except (ValueError, JSONDecodeError) as exc:
        raise FattureInCloudError(f"{error_prefix}: risposta non valida da Fatture in Cloud.") from exc


def _normalize_entity(entity):
    entity = _as_dict(entity)
    if not entity:
        return {}

    dati_anagrafici = _as_dict(
        _dict_value(entity, "dati_anagrafici", "DatiAnagrafici", "datiAnagrafici")
    )
    anagrafica = _as_dict(_dict_value(dati_anagrafici, "anagrafica", "Anagrafica"))
    id_fiscale_iva = _as_dict(
        _dict_value(dati_anagrafici, "id_fiscale_iva", "IdFiscaleIVA", "idFiscaleIva")
    )
    sede = _as_dict(_dict_value(entity, "sede", "Sede", "address", "Address"))
    contatti = _as_dict(_dict_value(entity, "contatti", "Contatti", "contacts", "Contacts"))

    normalized = dict(entity)
    normalized["name"] = _first_present(
        entity.get("name"),
        entity.get("denominazione"),
        entity.get("Denominazione"),
        anagrafica.get("denominazione"),
        anagrafica.get("Denominazione"),
        entity.get("business_name"),
    )
    normalized["first_name"] = _first_present(
        entity.get("first_name"),
        entity.get("nome"),
        entity.get("Nome"),
        anagrafica.get("nome"),
        anagrafica.get("Nome"),
    )
    normalized["last_name"] = _first_present(
        entity.get("last_name"),
        entity.get("cognome"),
        entity.get("Cognome"),
        anagrafica.get("cognome"),
        anagrafica.get("Cognome"),
    )
    normalized["vat_number"] = _first_present(
        entity.get("vat_number"),
        entity.get("vatNumber"),
        entity.get("partita_iva"),
        entity.get("partitaIva"),
        id_fiscale_iva.get("id_codice"),
        id_fiscale_iva.get("IdCodice"),
    )
    normalized["tax_code"] = _first_present(
        entity.get("tax_code"),
        entity.get("taxCode"),
        entity.get("codice_fiscale"),
        entity.get("CodiceFiscale"),
        dati_anagrafici.get("codice_fiscale"),
        dati_anagrafici.get("CodiceFiscale"),
    )
    normalized["address_street"] = _first_present(
        entity.get("address_street"),
        entity.get("address"),
        sede.get("indirizzo"),
        sede.get("Indirizzo"),
    )
    normalized["address_postal_code"] = _first_present(
        entity.get("address_postal_code"),
        entity.get("postal_code"),
        sede.get("cap"),
        sede.get("CAP"),
    )
    normalized["address_city"] = _first_present(entity.get("address_city"), sede.get("comune"), sede.get("Comune"))
    normalized["address_province"] = _first_present(
        entity.get("address_province"),
        sede.get("provincia"),
        sede.get("Provincia"),
    )
    normalized["email"] = _first_present(entity.get("email"), contatti.get("email"), contatti.get("Email"))
    normalized["certified_email"] = _first_present(
        entity.get("certified_email"),
        entity.get("pec"),
        entity.get("PEC"),
        contatti.get("pec"),
        contatti.get("Pec"),
        contatti.get("PECMail"),
        contatti.get("EmailCertificata"),
    )
    normalized["phone"] = _first_present(
        entity.get("phone"),
        entity.get("telefono"),
        entity.get("Telefono"),
        contatti.get("telefono"),
        contatti.get("Telefono"),
        contatti.get("phone"),
        contatti.get("Phone"),
    )
    normalized["type"] = _first_present(entity.get("type"), entity.get("kind"), entity.get("tipo_soggetto"))
    normalized["ei_code"] = _first_present(
        entity.get("ei_code"),
        entity.get("e_invoice_code"),
        entity.get("codice_sdi"),
        entity.get("codice_destinatario"),
        entity.get("CodiceDestinatario"),
    )
    normalized["bank_iban"] = _first_present(
        entity.get("bank_iban"),
        entity.get("bankIban"),
        entity.get("iban"),
        entity.get("IBAN"),
    )
    normalized["bank_name"] = _first_present(
        entity.get("bank_name"),
        entity.get("bankName"),
        entity.get("banca"),
        entity.get("istituto_bancario"),
    )
    return normalized


def _entity_from_document(document_data):
    e_invoice = _as_dict(document_data.get("e_invoice"))
    header = _e_invoice_header(e_invoice)
    entity = (
        document_data.get("entity")
        or document_data.get("supplier")
        or e_invoice.get("entity")
        or e_invoice.get("supplier")
        or e_invoice.get("cedente_prestatore")
        or e_invoice.get("CedentePrestatore")
        or e_invoice.get("cedentePrestatore")
        or _dict_value(header, "CedentePrestatore", "cedente_prestatore", "cedentePrestatore")
    )
    if not entity:
        entity = {
            "name": _first_present(
                document_data.get("supplier_name"),
                document_data.get("supplierName"),
            ),
            "vat_number": _first_present(
                document_data.get("supplier_vat_number"),
                document_data.get("supplierVatNumber"),
                document_data.get("supplier_vat_code"),
                document_data.get("supplierVatCode"),
            ),
            "tax_code": _first_present(
                document_data.get("supplier_tax_code"),
                document_data.get("supplierTaxCode"),
            ),
        }
    return _normalize_entity(entity)


def _explicit_supplier_name(entity, document_data):
    return (
        entity.get("name")
        or " ".join(part for part in [entity.get("first_name"), entity.get("last_name")] if part)
        or document_data.get("supplier_name")
        or document_data.get("supplierName")
        or ""
    )[:220]


def _supplier_name(entity, document_data):
    return (
        _explicit_supplier_name(entity, document_data)
        or document_data.get("description")
        or document_data.get("subject")
        or "Fornitore non identificato"
    )[:220]


def _supplier_address(entity):
    parts = [
        entity.get("address_street"),
        entity.get("address_postal_code"),
        entity.get("address_city"),
        entity.get("address_province"),
    ]
    return " ".join(part for part in parts if part)[:255]


def _supplier_identity_from_values(vat_number="", tax_code=""):
    return {
        "vat": _clean_vat_identifier(vat_number),
        "tax": _clean_identifier(tax_code),
    }


def _supplier_identity_from_entity(entity):
    return _supplier_identity_from_values(entity.get("vat_number"), entity.get("tax_code"))


def _supplier_identity_from_fornitore(fornitore):
    return _supplier_identity_from_values(fornitore.partita_iva, fornitore.codice_fiscale)


def _supplier_identity_conflicts(fornitore, identity):
    existing = _supplier_identity_from_fornitore(fornitore)
    return bool(
        (identity.get("vat") and existing.get("vat") and identity["vat"] != existing["vat"])
        or (identity.get("tax") and existing.get("tax") and identity["tax"] != existing["tax"])
    )


def _supplier_identity_matches(fornitore, identity):
    existing = _supplier_identity_from_fornitore(fornitore)
    return bool(
        (identity.get("vat") and existing.get("vat") == identity["vat"])
        or (identity.get("tax") and existing.get("tax") == identity["tax"])
    )


def _supplier_name_is_placeholder(value):
    key = _normalizza_nome_fornitore_match(value)
    return bool(
        key in SUPPLIER_PLACEHOLDER_NAME_KEYS
        or key.startswith("FATTURA DA ")
        or key.startswith("DOCUMENTO DA ")
    )


def _should_replace_supplier_after_signature_match(fornitore, entity, document_data):
    new_name = _explicit_supplier_name(entity, document_data)
    new_name_key = _normalizza_nome_fornitore_match(new_name)
    existing_name_key = _normalizza_nome_fornitore_match(fornitore.denominazione)
    if not new_name_key or new_name_key == existing_name_key:
        return False
    if _supplier_name_is_placeholder(new_name):
        return False
    if _supplier_identity_conflicts(fornitore, _supplier_identity_from_entity(entity)):
        return False
    return _supplier_name_is_placeholder(fornitore.denominazione)


def _find_supplier_by_normalized_name(qs, name, identity):
    name_key = _normalizza_nome_fornitore_match(name)
    if not name_key:
        return None

    matches = []
    for candidate in qs.only("id", "denominazione", "partita_iva", "codice_fiscale"):
        if _normalizza_nome_fornitore_match(candidate.denominazione) != name_key:
            continue
        if _supplier_identity_conflicts(candidate, identity):
            continue
        matches.append(candidate)
        if len(matches) > 1:
            return None
    return matches[0] if matches else None


def _supplier_defaults_from_entity(entity):
    vat_number = _clean_vat_identifier(entity.get("vat_number"))
    tax_code = _clean_identifier(entity.get("tax_code"))
    return {
        "tipo_soggetto": "azienda" if (entity.get("type") or "") != "person" else "professionista",
        "partita_iva": vat_number[:11],
        "codice_fiscale": tax_code[:16],
        "indirizzo": _supplier_address(entity),
        "email": (entity.get("email") or "")[:254],
        "pec": (entity.get("certified_email") or "")[:254],
        "telefono": (entity.get("phone") or "")[:40],
        "codice_sdi": _clean_identifier(entity.get("ei_code"))[:7],
        "iban": _clean_identifier(entity.get("bank_iban"))[:34],
        "banca": (entity.get("bank_name") or "")[:160],
    }


def _update_supplier_missing_fields(fornitore, entity):
    changed = []
    for field_name, value in _supplier_defaults_from_entity(entity).items():
        if value and not getattr(fornitore, field_name):
            setattr(fornitore, field_name, value)
            changed.append(field_name)
    if changed:
        changed.append("data_aggiornamento")
        fornitore.save(update_fields=changed)
    return bool(changed)


def _find_or_create_supplier(entity, document_data):
    name = _supplier_name(entity, document_data)
    vat_number = _clean_vat_identifier(entity.get("vat_number"))
    tax_code = _clean_identifier(entity.get("tax_code"))
    identity = _supplier_identity_from_values(vat_number, tax_code)

    qs = Fornitore.objects.all()
    fornitore = None
    if vat_number:
        fornitore = qs.filter(partita_iva__iexact=vat_number).first()
    if fornitore is None and tax_code:
        fornitore = qs.filter(codice_fiscale__iexact=tax_code).first()
    if fornitore is None:
        fornitore = qs.filter(denominazione__iexact=name).first()
    if fornitore is None:
        fornitore = _find_supplier_by_normalized_name(qs, name, identity)

    defaults = _supplier_defaults_from_entity(entity)
    if fornitore is None:
        return Fornitore.objects.create(denominazione=name, attivo=True, **defaults), True, False

    return fornitore, False, _update_supplier_missing_fields(fornitore, entity)


def _raw_document_type_values(document_data, source_doc_type=None):
    e_invoice = _as_dict(document_data.get("e_invoice"))
    dati_generali_documento = _document_general_data(e_invoice)
    return [
        source_doc_type,
        document_data.get("document_type"),
        document_data.get("documentType"),
        document_data.get("type"),
        e_invoice.get("document_type"),
        e_invoice.get("documentType"),
        e_invoice.get("tipo_documento"),
        e_invoice.get("TipoDocumento"),
        dati_generali_documento.get("tipo_documento"),
        dati_generali_documento.get("TipoDocumento"),
    ]


def _is_credit_note_document(document_data, source_doc_type=None):
    for raw_value in _raw_document_type_values(document_data, source_doc_type):
        value = _normalizza_spazi(raw_value).casefold()
        if not value:
            continue
        compact = re.sub(r"[^a-z0-9]+", "_", value).strip("_")
        if value in FIC_CREDIT_NOTE_TYPES or compact in FIC_CREDIT_NOTE_TYPES:
            return True
        if "credit" in value or ("nota" in value and "credito" in value):
            return True
    return False


def _document_type(document_data, source_doc_type=None):
    if _is_credit_note_document(document_data, source_doc_type):
        return TipoDocumentoFornitore.NOTA_CREDITO
    return TipoDocumentoFornitore.FATTURA


def _invoice_number(document_data):
    e_invoice = _as_dict(document_data.get("e_invoice"))
    dati_generali_documento = _document_general_data(e_invoice)
    return (
        document_data.get("invoice_number")
        or document_data.get("invoiceNumber")
        or document_data.get("document_number")
        or document_data.get("documentNumber")
        or document_data.get("number")
        or e_invoice.get("number")
        or e_invoice.get("numero")
        or e_invoice.get("Numero")
        or dati_generali_documento.get("numero")
        or dati_generali_documento.get("Numero")
        or str(document_data.get("id") or "")
    )[:80]


def _document_total(document_data):
    e_invoice = _as_dict(document_data.get("e_invoice"))
    amounts = _as_dict(document_data.get("amounts"))
    dati_generali_documento = _document_general_data(e_invoice)
    return _as_decimal(
        document_data.get("amount_gross")
        or document_data.get("total")
        or document_data.get("amount")
        or amounts.get("gross")
        or amounts.get("amount_gross")
        or amounts.get("total")
        or amounts.get("amount")
        or document_data.get("importo_totale_documento")
        or document_data.get("ImportoTotaleDocumento")
        or e_invoice.get("amount_gross")
        or e_invoice.get("total")
        or e_invoice.get("importo_totale_documento")
        or e_invoice.get("ImportoTotaleDocumento")
        or dati_generali_documento.get("importo_totale_documento")
        or dati_generali_documento.get("ImportoTotaleDocumento")
    )


def _iter_direct_withholding_nodes(document_data):
    e_invoice = _as_dict(document_data.get("e_invoice"))
    amounts = _as_dict(document_data.get("amounts"))
    node = _first_present(
        document_data.get("withholding_tax"),
        document_data.get("withholdingTax"),
        document_data.get("tax_withholding"),
        document_data.get("taxWithholding"),
        document_data.get("ritenuta"),
        document_data.get("ritenuta_acconto"),
        amounts.get("withholding_tax"),
        amounts.get("withholdingTax"),
        amounts.get("ritenuta"),
        amounts.get("ritenuta_acconto"),
        e_invoice.get("withholding_tax"),
        e_invoice.get("withholdingTax"),
        e_invoice.get("ritenuta"),
        e_invoice.get("ritenuta_acconto"),
    )
    if node:
        yield node


def _iter_e_invoice_withholding_nodes(document_data):
    e_invoice = _as_dict(document_data.get("e_invoice"))
    general_sources = [_document_general_data(e_invoice)]
    for body in _e_invoice_bodies(e_invoice):
        general_sources.extend(
            [
                _nested_dict(body, "dati_generali", "dati_generali_documento"),
                _nested_dict(body, "DatiGenerali", "DatiGeneraliDocumento"),
            ]
        )
    seen_sources = set()
    for source in general_sources:
        source_marker = id(source)
        if not source or source_marker in seen_sources:
            continue
        seen_sources.add(source_marker)
        for node in _as_list(_dict_value(source, "dati_ritenuta", "DatiRitenuta", "datiRitenuta")):
            if node:
                yield node


def _withholding_node_amount(node):
    if not isinstance(node, dict):
        return _as_decimal(node)
    return _as_decimal(
        _first_present(
            node.get("amount"),
            node.get("value"),
            node.get("total"),
            node.get("importo"),
            node.get("importo_ritenuta"),
            node.get("ImportoRitenuta"),
            node.get("withholding_amount"),
            node.get("withholdingAmount"),
            node.get("withholding_tax_amount"),
            node.get("withholdingTaxAmount"),
            node.get("ritenuta_acconto"),
            node.get("ritenutaAcconto"),
        )
    )


def _withholding_node_rate(node):
    if not isinstance(node, dict):
        return Decimal("0.00")
    return _as_decimal(
        _first_present(
            node.get("rate"),
            node.get("percentage"),
            node.get("aliquota"),
            node.get("aliquota_ritenuta"),
            node.get("AliquotaRitenuta"),
            node.get("withholding_rate"),
            node.get("withholdingRate"),
            node.get("withholding_tax_rate"),
            node.get("withholdingTaxRate"),
        )
    )


def _withholding_node_taxable(node):
    if not isinstance(node, dict):
        return Decimal("0.00")
    return _as_decimal(
        _first_present(
            node.get("taxable"),
            node.get("taxable_amount"),
            node.get("taxableAmount"),
            node.get("imponibile"),
            node.get("imponibile_ritenuta"),
            node.get("imponibile_ritenuta_acconto"),
            node.get("withholding_taxable"),
            node.get("withholdingTaxable"),
            node.get("withholding_taxable_amount"),
            node.get("withholdingTaxableAmount"),
        )
    )


def _document_withholding(document_data):
    direct = _summarize_withholding_nodes(_iter_direct_withholding_nodes(document_data))
    if direct["ritenuta"] > Decimal("0.00") or direct["imponibile"] > Decimal("0.00"):
        return direct
    return _summarize_withholding_nodes(_iter_e_invoice_withholding_nodes(document_data))


def _summarize_withholding_nodes(nodes):
    total_amount = Decimal("0.00")
    taxable_total = Decimal("0.00")
    first_rate = Decimal("0.00")
    for node in nodes:
        amount = _withholding_node_amount(node)
        taxable = _withholding_node_taxable(node)
        rate = _withholding_node_rate(node)
        if amount <= Decimal("0.00") and taxable <= Decimal("0.00"):
            continue
        total_amount += amount
        taxable_total += taxable
        if first_rate <= Decimal("0.00") and rate > Decimal("0.00"):
            first_rate = rate

    if taxable_total <= Decimal("0.00") and total_amount > Decimal("0.00") and first_rate > Decimal("0.00"):
        taxable_total = (total_amount * Decimal("100") / first_rate).quantize(Decimal("0.01"))

    return {
        "imponibile": taxable_total.quantize(Decimal("0.01")),
        "aliquota": first_rate.quantize(Decimal("0.01")) if first_rate > Decimal("0.00") else Decimal("20.00"),
        "ritenuta": total_amount.quantize(Decimal("0.01")),
    }


def _document_total_to_pay(document_data):
    total = _document_total(document_data)
    withholding = _document_withholding(document_data)["ritenuta"]
    return max(total - withholding, Decimal("0.00"))


def _iter_invoice_line_items(document_data):
    e_invoice = _as_dict(document_data.get("e_invoice"))
    containers = [document_data, e_invoice, *_e_invoice_bodies(e_invoice)]
    goods_keys = (
        "dati_beni_servizi",
        "DatiBeniServizi",
        "datiBeniServizi",
        "goods_services",
        "goodsServices",
    )
    line_keys = (
        "dettaglio_linee",
        "DettaglioLinee",
        "dettaglioLinee",
        "items_list",
        "itemsList",
        "items",
        "lines",
        "rows",
        "details",
    )
    for container in containers:
        if not isinstance(container, dict):
            continue
        for key in line_keys:
            for item in _as_list(container.get(key)):
                if isinstance(item, dict):
                    yield item
        for goods_section in _as_list(_dict_value(container, *goods_keys)):
            goods_section = _as_dict(goods_section)
            if not goods_section:
                continue
            for key in line_keys:
                for item in _as_list(goods_section.get(key)):
                    if isinstance(item, dict):
                        yield item


def _document_line_descriptions(document_data, *, limit=3):
    return _unique_text_values(
        (
            _first_present(
                item.get("description"),
                item.get("descrizione"),
                item.get("Descrizione"),
                item.get("name"),
                item.get("Nome"),
            )
            for item in _iter_invoice_line_items(document_data)
        ),
        limit=limit,
    )


def _document_invoice_line_descriptions(document_data):
    return _unique_text_values(
        [
            *_document_line_descriptions(document_data, limit=20),
            *_as_list(document_data.get("_arboris_line_descriptions")),
            *_as_list(document_data.get("invoice_line_descriptions")),
            *_as_list(document_data.get("line_descriptions")),
        ],
        limit=20,
    )


def _document_invoice_line_description_text(document_data):
    return "\n".join(_document_invoice_line_descriptions(document_data))[:4000]


def _document_causali(document_data):
    e_invoice = _as_dict(document_data.get("e_invoice"))
    general_data_sources = [_document_general_data(e_invoice)]
    for body in _e_invoice_bodies(e_invoice):
        general_data_sources.extend(
            [
                _nested_dict(body, "dati_generali", "dati_generali_documento"),
                _nested_dict(body, "DatiGenerali", "DatiGeneraliDocumento"),
            ]
        )
    values = []
    for data in general_data_sources:
        causale = _dict_value(data, "causale", "Causale", "causali", "Causali")
        values.extend(_as_list(causale))
    return _unique_text_values(values, limit=3)


def _document_description(document_data):
    direct = _first_present(
        document_data.get("description"),
        document_data.get("subject"),
        document_data.get("notes"),
        document_data.get("note"),
    )
    if direct:
        return _normalizza_spazi(direct)[:255]

    line_descriptions = _document_line_descriptions(document_data)
    if line_descriptions:
        return "; ".join(line_descriptions)[:255]

    causali = _document_causali(document_data)
    if causali:
        return "; ".join(causali)[:255]

    e_invoice = _as_dict(document_data.get("e_invoice"))
    fallback = _first_present(
        e_invoice.get("description"),
        e_invoice.get("subject"),
        e_invoice.get("causale"),
        e_invoice.get("Causale"),
    )
    return _normalizza_spazi(fallback)[:255]


def _payment_items(document_data):
    payments = list(_as_list(document_data.get("payments_list") or document_data.get("payments")))
    e_invoice = _as_dict(document_data.get("e_invoice"))
    payments.extend(_as_list(e_invoice.get("payments_list") or e_invoice.get("payments")))

    e_invoice_payment_groups = list(_as_list(
        e_invoice.get("dati_pagamento")
        or e_invoice.get("DatiPagamento")
        or e_invoice.get("datiPagamento")
        or document_data.get("dati_pagamento")
        or document_data.get("DatiPagamento")
    ))
    for body in _e_invoice_bodies(e_invoice):
        payments.extend(_as_list(_dict_value(body, "payments_list", "payments")))
        e_invoice_payment_groups.extend(
            _as_list(_dict_value(body, "dati_pagamento", "DatiPagamento", "datiPagamento"))
        )
    for group in e_invoice_payment_groups:
        group = _as_dict(group)
        details = (
            group.get("dettaglio_pagamento")
            or group.get("DettaglioPagamento")
            or group.get("dettaglioPagamento")
            or group.get("details")
            or group.get("payment_details")
            or group.get("paymentDetails")
        )
        payments.extend(_as_list(details))
    return [payment for payment in payments if isinstance(payment, dict)]


def _supplier_payment_data_from_document(document_data):
    data = {}
    for payment in _payment_items(document_data):
        iban = _first_present(
            payment.get("iban"),
            payment.get("IBAN"),
            payment.get("bank_iban"),
            payment.get("bankIban"),
        )
        bank_name = _first_present(
            payment.get("bank_name"),
            payment.get("bankName"),
            payment.get("banca"),
            payment.get("istituto_finanziario"),
            payment.get("IstitutoFinanziario"),
        )
        if iban and not data.get("bank_iban"):
            data["bank_iban"] = iban
        if bank_name and not data.get("bank_name"):
            data["bank_name"] = bank_name
        if data.get("bank_iban") and data.get("bank_name"):
            break
    return data


def _enrich_supplier_entity_from_document(entity, document_data):
    enriched = dict(entity or {})
    for key, value in _supplier_payment_data_from_document(document_data).items():
        if value and not enriched.get(key):
            enriched[key] = value
    return enriched


def _supplier_entity_id_from_document(document_data):
    entity = _as_dict(document_data.get("entity") or document_data.get("supplier"))
    entity_id = entity.get("id") or entity.get("supplier_id") or entity.get("supplierId")
    return str(entity_id).strip() if entity_id not in (None, "") else ""


def _merge_non_empty(base, extra):
    merged = dict(base or {})
    for key, value in _as_dict(extra).items():
        if value not in (None, ""):
            merged[key] = value
    return merged


def _merge_missing_nested(base, extra):
    merged = dict(base or {})
    for key, value in _as_dict(extra).items():
        current = merged.get(key)
        if isinstance(current, dict) and isinstance(value, dict):
            merged[key] = _merge_missing_nested(current, value)
        elif current in (None, "", [], {}) and value not in (None, "", [], {}):
            merged[key] = value
    return merged


def _supplier_has_import_details(entity):
    normalized = _normalize_entity(entity)
    return any(
        normalized.get(field_name)
        for field_name in (
            "vat_number",
            "tax_code",
            "address_street",
            "email",
            "certified_email",
        )
    )


def _document_with_supplier_detail(client, document_data, supplier_context):
    if not isinstance(document_data, dict):
        return document_data

    entity = _as_dict(document_data.get("entity") or document_data.get("supplier"))
    supplier_id = _supplier_entity_id_from_document(document_data)
    if not supplier_id:
        return document_data
    if supplier_context is not None and supplier_context.get("supplier_detail_disabled"):
        return document_data

    cache = supplier_context.setdefault("cache", {}) if supplier_context is not None else {}
    warnings = supplier_context.setdefault("warnings", set()) if supplier_context is not None else set()
    if supplier_id not in cache:
        try:
            cache[supplier_id] = client.get_supplier(supplier_id)
        except FattureInCloudError as exc:
            cache[supplier_id] = None
            if " 401" in str(exc) or " 403" in str(exc) or "NO_PERMISSION" in str(exc).upper():
                if supplier_context is not None:
                    supplier_context["supplier_detail_disabled"] = True
                warnings.add(SUPPLIER_DETAILS_SCOPE_WARNING)
            else:
                warnings.add("Dati anagrafici completi dei fornitori non recuperati durante la sincronizzazione.")

    supplier_detail = cache.get(supplier_id)
    if not supplier_detail:
        return document_data

    enriched = dict(document_data)
    enriched["entity"] = _merge_non_empty(entity, supplier_detail)
    return enriched


def _attachment_xml_details(document_data, supplier_context):
    if not isinstance(document_data, dict):
        return {}
    if not document_data.get("attachment_url"):
        return {}

    cache = supplier_context.setdefault("attachment_xml_cache", {}) if supplier_context is not None else {}
    cache_key = str(document_data.get("attachment_url") or document_data.get("id") or "")
    if cache_key not in cache:
        data, _download_info = download_bytes(
            document_data.get("attachment_url"),
            timeout=_api_timeout(),
            max_bytes=_attachment_max_bytes(),
        )
        xml_text, _xml_source = xml_text_from_bytes(data or b"")
        cache[cache_key] = {
            "supplier": supplier_from_e_invoice_xml(xml_text) if xml_text else {},
            "document": document_data_from_e_invoice_xml(xml_text) if xml_text else {},
        }
    return cache.get(cache_key) or {}


def _document_with_attachment_supplier_detail(document_data, supplier_context):
    if not isinstance(document_data, dict):
        return document_data
    if not document_data.get("attachment_url"):
        return document_data
    if _supplier_has_import_details(_entity_from_document(document_data)):
        return document_data

    supplier_detail = _attachment_xml_details(document_data, supplier_context).get("supplier")
    if not supplier_detail:
        return document_data

    entity = _as_dict(document_data.get("entity") or document_data.get("supplier"))
    if not entity:
        entity = {
            "name": _first_present(
                document_data.get("supplier_name"),
                document_data.get("supplierName"),
            )
        }
    enriched = dict(document_data)
    enriched["entity"] = _merge_non_empty(entity, supplier_detail)
    return enriched


def _document_with_attachment_invoice_detail(document_data, supplier_context):
    if not isinstance(document_data, dict):
        return document_data
    if not document_data.get("attachment_url"):
        return document_data

    attachment_document = _attachment_xml_details(document_data, supplier_context).get("document")
    if not attachment_document:
        return document_data

    enriched = dict(document_data)
    enriched["e_invoice"] = _merge_missing_nested(
        _as_dict(document_data.get("e_invoice")),
        _as_dict(attachment_document.get("e_invoice")),
    )
    line_descriptions = _unique_text_values(
        [
            *_as_list(document_data.get("_arboris_line_descriptions")),
            *_as_list(attachment_document.get("_arboris_line_descriptions")),
        ],
        limit=20,
    )
    if line_descriptions:
        enriched["_arboris_line_descriptions"] = line_descriptions
    return enriched


def _document_with_external_supplier_details(client, document_data, supplier_context, *, include_attachment=False):
    enriched = _document_with_supplier_detail(client, document_data, supplier_context)
    if include_attachment:
        enriched = _document_with_attachment_invoice_detail(enriched, supplier_context)
        enriched = _document_with_attachment_supplier_detail(enriched, supplier_context)
    return enriched


def _payment_amount(payment):
    amount = payment.get("amount")
    if isinstance(amount, dict):
        amount = (
            amount.get("gross")
            or amount.get("amount_gross")
            or amount.get("total")
            or amount.get("value")
        )
    return _as_decimal(
        amount
        or payment.get("amount_gross")
        or payment.get("paid_amount")
        or payment.get("paidAmount")
        or payment.get("importo")
        or payment.get("importo_pagamento")
        or payment.get("ImportoPagamento")
    )


def _payment_status(payment):
    return _normalizza_spazi(
        _first_present(
            payment.get("status"),
            payment.get("payment_status"),
            payment.get("paymentStatus"),
            payment.get("stato"),
            payment.get("Stato"),
        )
    ).casefold()


def _is_paid_status(status):
    return status in PAYMENT_PAID_STATUSES


def _is_partial_status(status):
    return status in PAYMENT_PARTIAL_STATUSES


def _payment_paid_date(payment):
    return _as_date(
        _first_present(
            payment.get("paid_date"),
            payment.get("paidDate"),
            payment.get("paid_at"),
            payment.get("paidAt"),
            payment.get("payment_date"),
            payment.get("paymentDate"),
            payment.get("data_pagamento"),
            payment.get("DataPagamento"),
            payment.get("data_saldo"),
            payment.get("DataSaldo"),
        )
    )


def _payment_paid_amount(payment):
    explicit = _as_decimal(
        _first_present(
            payment.get("paid_amount"),
            payment.get("paidAmount"),
            payment.get("amount_paid"),
            payment.get("amountPaid"),
            payment.get("paid_total"),
            payment.get("paidTotal"),
            payment.get("importo_pagato"),
            payment.get("ImportoPagato"),
        )
    )
    if explicit > Decimal("0.00"):
        return explicit

    status = _payment_status(payment)
    if _is_paid_status(status) or _payment_paid_date(payment):
        return _payment_amount(payment)
    if _is_partial_status(status):
        return Decimal("0.00")
    return Decimal("0.00")


def _document_payment_status(document_data):
    return _normalizza_spazi(
        _first_present(
            document_data.get("payment_status"),
            document_data.get("paymentStatus"),
            document_data.get("payments_status"),
            document_data.get("paymentsStatus"),
            document_data.get("status"),
            document_data.get("stato"),
        )
    ).casefold()


def _document_paid_date(document_data):
    return _as_date(
        _first_present(
            document_data.get("paid_date"),
            document_data.get("paidDate"),
            document_data.get("paid_at"),
            document_data.get("paidAt"),
            document_data.get("payment_date"),
            document_data.get("paymentDate"),
            document_data.get("data_pagamento"),
            document_data.get("DataPagamento"),
        )
    )


def _document_paid_amount(document_data, total):
    amounts = _as_dict(document_data.get("amounts"))
    explicit = _as_decimal(
        _first_present(
            document_data.get("paid_amount"),
            document_data.get("paidAmount"),
            document_data.get("amount_paid"),
            document_data.get("amountPaid"),
            document_data.get("paid_total"),
            document_data.get("paidTotal"),
            document_data.get("importo_pagato"),
            document_data.get("ImportoPagato"),
            amounts.get("paid"),
            amounts.get("paid_amount"),
            amounts.get("paidAmount"),
        )
    )
    if explicit > Decimal("0.00"):
        return explicit

    due = _as_decimal(
        _first_present(
            document_data.get("amount_due"),
            document_data.get("amountDue"),
            document_data.get("remaining_amount"),
            document_data.get("remainingAmount"),
            document_data.get("residual_amount"),
            document_data.get("residualAmount"),
            amounts.get("due"),
            amounts.get("amount_due"),
            amounts.get("remaining"),
        )
    )
    if total > Decimal("0.00") and due > Decimal("0.00") and due < total:
        return total - due

    status = _document_payment_status(document_data)
    if _is_paid_status(status) or _document_paid_date(document_data):
        return total
    return Decimal("0.00")


def _apply_document_payment_state_to_deadlines(document_data, deadlines):
    if not deadlines:
        return deadlines

    total = sum((deadline["importo_previsto"] for deadline in deadlines), Decimal("0.00"))
    paid_amount = _document_paid_amount(document_data, total)
    paid_date = _document_paid_date(document_data)
    if paid_amount <= Decimal("0.00"):
        return deadlines

    remaining = paid_amount
    for deadline in deadlines:
        if deadline["importo_pagato"] > Decimal("0.00"):
            remaining -= deadline["importo_pagato"]
            continue
        if remaining <= Decimal("0.00"):
            break
        deadline["importo_pagato"] = min(deadline["importo_previsto"], remaining)
        if paid_date and not deadline["data_pagamento"]:
            deadline["data_pagamento"] = paid_date
        remaining -= deadline["importo_pagato"]
    return deadlines


def _deadlines_total(deadlines):
    return sum((_as_decimal(deadline.get("importo_previsto")) for deadline in deadlines), Decimal("0.00"))


def _deduplicate_payment_deadlines(deadlines, *, expected_total=None):
    normalized = [
        {
            "data_scadenza": deadline["data_scadenza"],
            "importo_previsto": _as_decimal(deadline["importo_previsto"]),
            "importo_pagato": _as_decimal(deadline.get("importo_pagato")),
            "data_pagamento": deadline.get("data_pagamento"),
        }
        for deadline in deadlines or []
    ]
    if len(normalized) <= 1:
        return normalized

    expected_total = _as_decimal(expected_total)
    if expected_total > Decimal("0.00") and _deadlines_total(normalized) <= expected_total + Decimal("0.01"):
        return normalized

    deduplicated = []
    by_key = {}
    for deadline in normalized:
        key = (deadline["data_scadenza"], deadline["importo_previsto"])
        existing = by_key.get(key)
        if existing is None:
            by_key[key] = deadline
            deduplicated.append(deadline)
            continue

        if deadline["importo_pagato"] > existing["importo_pagato"]:
            existing["importo_pagato"] = deadline["importo_pagato"]
        if deadline["data_pagamento"] and not existing["data_pagamento"]:
            existing["data_pagamento"] = deadline["data_pagamento"]
    return deduplicated


def _paid_amount_from_payments(payments):
    paid = Decimal("0.00")
    for payment in payments or []:
        paid += _payment_paid_amount(payment)
    return paid


def _state_from_document(total, payments, document_data=None, source_doc_type=None):
    if document_data and _is_credit_note_document(document_data, source_doc_type):
        return StatoDocumentoFornitore.PAGATO

    paid = _paid_amount_from_payments(payments)
    if document_data:
        paid = max(paid, _document_paid_amount(document_data, total))
    if total > Decimal("0.00") and paid >= total:
        return StatoDocumentoFornitore.PAGATO
    if paid > Decimal("0.00"):
        return StatoDocumentoFornitore.PARZIALMENTE_PAGATO
    return StatoDocumentoFornitore.DA_PAGARE


def _payment_due_date(payment):
    return _as_date(
        payment.get("due_date")
        or payment.get("dueDate")
        or payment.get("date")
        or payment.get("expiration_date")
        or payment.get("expirationDate")
        or payment.get("payment_due_date")
        or payment.get("paymentDueDate")
        or payment.get("data_scadenza_pagamento")
        or payment.get("DataScadenzaPagamento")
    )


def _payment_deadlines(document_data, source_doc_type=None):
    if _is_credit_note_document(document_data, source_doc_type):
        return []

    payments = _payment_items(document_data)
    total = _document_total_to_pay(document_data)
    deadlines = []
    for payment in payments:
        due_date = _payment_due_date(payment)
        amount = _payment_amount(payment)
        if amount <= Decimal("0.00") and len(payments) == 1:
            amount = total
        if due_date and amount > Decimal("0.00"):
            deadlines.append(
                {
                    "data_scadenza": due_date,
                    "importo_previsto": amount,
                    "importo_pagato": _payment_paid_amount(payment),
                    "data_pagamento": _payment_paid_date(payment),
                }
            )

    if deadlines:
        deadlines = _deduplicate_payment_deadlines(deadlines, expected_total=total)
        return _apply_document_payment_state_to_deadlines(document_data, deadlines)

    due_date = _as_date(
        document_data.get("next_due_date")
        or document_data.get("nextDueDate")
        or document_data.get("due_date")
        or document_data.get("dueDate")
        or document_data.get("expiration_date")
        or document_data.get("expirationDate")
        or document_data.get("payment_due_date")
        or document_data.get("paymentDueDate")
        or document_data.get("emission_date")
        or document_data.get("emssion_date")
        or document_data.get("date")
    ) or timezone.localdate()
    if total > Decimal("0.00"):
        deadlines = _deduplicate_payment_deadlines(
            [
                {
                    "data_scadenza": due_date,
                    "importo_previsto": total,
                    "importo_pagato": Decimal("0.00"),
                    "data_pagamento": None,
                }
            ],
            expected_total=total,
        )
        return _apply_document_payment_state_to_deadlines(document_data, deadlines)
    return []


def _document_explicit_date(document_data):
    e_invoice = _as_dict(document_data.get("e_invoice"))
    dati_generali_documento = _document_general_data(e_invoice)
    return _as_date(
        _first_present(
            document_data.get("date"),
            document_data.get("emission_date"),
            document_data.get("emssion_date"),
            document_data.get("document_date"),
            document_data.get("documentDate"),
            e_invoice.get("date"),
            e_invoice.get("emission_date"),
            e_invoice.get("emssion_date"),
            e_invoice.get("document_date"),
            e_invoice.get("documentDate"),
            e_invoice.get("data"),
            e_invoice.get("Data"),
            dati_generali_documento.get("data"),
            dati_generali_documento.get("Data"),
            dati_generali_documento.get("data_documento"),
            dati_generali_documento.get("DataDocumento"),
        )
    )


def _document_date(document_data):
    return _document_explicit_date(document_data) or timezone.localdate()


def _document_date_for_sync_filter(document_data):
    return _document_explicit_date(document_data)


def _document_due_date_candidates(document_data):
    values = [
        document_data.get("next_due_date"),
        document_data.get("nextDueDate"),
        document_data.get("due_date"),
        document_data.get("dueDate"),
        document_data.get("expiration_date"),
        document_data.get("expirationDate"),
        document_data.get("payment_due_date"),
        document_data.get("paymentDueDate"),
    ]
    dates = []
    for value in values:
        due_date = _as_date(value)
        if due_date:
            dates.append(due_date)
    for payment in _payment_items(document_data):
        due_date = _payment_due_date(payment)
        if due_date:
            dates.append(due_date)
    return dates


def _document_import_date_candidates(document_data):
    dates = []
    explicit_date = _document_date_for_sync_filter(document_data)
    if explicit_date:
        dates.append(explicit_date)
    dates.extend(_document_due_date_candidates(document_data))

    seen = set()
    unique_dates = []
    for item in dates:
        if item in seen:
            continue
        seen.add(item)
        unique_dates.append(item)
    return unique_dates


def _document_total_for_import_match(document_data):
    amounts = _as_dict(document_data.get("amounts"))
    amount_net = _as_decimal(
        document_data.get("amount_net")
        or amounts.get("net")
        or amounts.get("amount_net")
    )
    amount_vat = _as_decimal(
        document_data.get("amount_vat")
        or amounts.get("vat")
        or amounts.get("amount_vat")
    )
    amount_gross = _document_total(document_data)
    if amount_gross == Decimal("0.00") and amount_net:
        amount_gross = amount_net + amount_vat
    return amount_gross.quantize(Decimal("0.01"))


def _signature_alias_id(parts):
    digest = hashlib.sha256("|".join(str(part) for part in parts).encode("utf-8")).hexdigest()
    return f"signature:{digest}"


def _document_import_signature_alias_ids(document_data, entity, source_doc_type=None):
    date_candidates = _document_import_date_candidates(document_data)
    numero_norm = _normalizza_numero_documento_match(_invoice_number(document_data))
    supplier_name_key = _normalizza_nome_fornitore_match(_supplier_name(entity, document_data))
    identity = _supplier_identity_from_entity(entity)
    description_key = _normalizza_testo_match(_document_description(document_data))
    line_description_key = _normalizza_testo_match(_document_invoice_line_description_text(document_data))
    total = _document_total_for_import_match(document_data)
    if not (date_candidates and numero_norm and total > Decimal("0.00")):
        return []

    doc_type = str(_document_type(document_data, source_doc_type))
    aliases = []

    # Legacy signature kept so old aliases created before this strengthening remain effective.
    explicit_date = _document_date_for_sync_filter(document_data)
    if explicit_date and supplier_name_key:
        aliases.append(
            _signature_alias_id(
                [
                    "signature",
                    doc_type,
                    supplier_name_key,
                    numero_norm,
                    explicit_date.isoformat(),
                    f"{total:.2f}",
                ]
            )
        )

    discriminators = [
        ("supplier", supplier_name_key),
        ("description", description_key),
        ("lines", line_description_key),
    ]
    if identity.get("vat"):
        discriminators.append(("vat", identity["vat"]))
    if identity.get("tax"):
        discriminators.append(("tax", identity["tax"]))

    for kind, discriminator in discriminators:
        if not discriminator:
            continue
        for item_date in date_candidates:
            aliases.append(
                _signature_alias_id(
                    [
                        "signature-v2",
                        kind,
                        doc_type,
                        discriminator,
                        numero_norm,
                        item_date.isoformat(),
                        f"{total:.2f}",
                    ]
                )
            )

    seen = set()
    unique_aliases = []
    for alias_id in aliases:
        if alias_id in seen:
            continue
        seen.add(alias_id)
        unique_aliases.append(alias_id)
    return unique_aliases


def _document_description_matches_import(documento, description_key, line_description_key):
    if not description_key and not line_description_key:
        return True

    existing_keys = {
        _normalizza_testo_match(documento.descrizione),
        _normalizza_testo_match(documento.descrizione_righe_fattura),
    }
    existing_keys.discard("")
    if not existing_keys:
        return True
    return bool(
        (description_key and description_key in existing_keys)
        or (line_description_key and line_description_key in existing_keys)
    )


def _supplier_matches_imported_document(fornitore, identity, supplier_name_key):
    if _supplier_identity_matches(fornitore, identity):
        return True
    if _supplier_identity_conflicts(fornitore, identity):
        return False
    return bool(
        supplier_name_key
        and _normalizza_nome_fornitore_match(fornitore.denominazione) == supplier_name_key
    )


def _document_import_match_key(documento):
    return (
        0 if documento.origine == OrigineDocumentoFornitore.FATTURE_IN_CLOUD else 1,
        0 if documento.external_source == FIC_SOURCE and documento.external_id else 1,
        documento.pk,
    )


def _find_existing_document_by_import_signature(document_data, fornitore, entity, source_doc_type=None):
    date_candidates = _document_import_date_candidates(document_data)
    date_candidate_set = set(date_candidates)
    invoice_number = _invoice_number(document_data)
    numero_norm = _normalizza_numero_documento_match(invoice_number)
    if not numero_norm:
        return None

    doc_type = _document_type(document_data, source_doc_type)
    total = _document_total_for_import_match(document_data)
    identity = _supplier_identity_from_entity(entity)
    supplier_name_key = _normalizza_nome_fornitore_match(_supplier_name(entity, document_data))
    description_key = _normalizza_testo_match(_document_description(document_data))
    line_description_key = _normalizza_testo_match(_document_invoice_line_description_text(document_data))
    has_description_signal = bool(description_key or line_description_key)
    candidates_qs = DocumentoFornitore.objects.select_for_update().select_related("fornitore").filter(
        tipo_documento=doc_type,
    )
    candidate_years = sorted({item.year for item in date_candidates})
    if candidate_years:
        candidates_qs = candidates_qs.filter(data_documento__year__in=candidate_years)
    matches = []

    for documento in candidates_qs.filter(fornitore=fornitore):
        if _normalizza_numero_documento_match(documento.numero_documento) != numero_norm:
            continue
        same_candidate_date = bool(date_candidate_set and documento.data_documento in date_candidate_set)
        same_total = total > Decimal("0.00") and _same_money(documento.totale, total)
        if same_candidate_date or (
            same_total
            and has_description_signal
            and _document_description_matches_import(documento, description_key, line_description_key)
        ):
            matches.append(documento)

    if not matches and total > Decimal("0.00"):
        if not date_candidate_set and not has_description_signal:
            return None
        cross_supplier_qs = candidates_qs
        if date_candidate_set:
            cross_supplier_qs = cross_supplier_qs.filter(data_documento__in=date_candidate_set)
        for documento in cross_supplier_qs:
            if documento.fornitore_id == fornitore.pk:
                continue
            if _normalizza_numero_documento_match(documento.numero_documento) != numero_norm:
                continue
            if not _same_money(documento.totale, total):
                continue
            if _supplier_matches_imported_document(documento.fornitore, identity, supplier_name_key):
                matches.append(documento)
                continue
            if (
                supplier_name_key
                and _normalizza_nome_fornitore_match(documento.fornitore.denominazione) == supplier_name_key
                and _document_description_matches_import(documento, description_key, line_description_key)
            ):
                matches.append(documento)

    if not matches:
        return None
    return sorted(matches, key=_document_import_match_key)[0]


def _clean_external_alias_value(value):
    return str(value or "").strip()


def _fic_import_alias_for_external_id(external_id):
    external_id = _clean_external_alias_value(external_id)
    if not external_id:
        return None
    alias = (
        DocumentoFornitoreImportAlias.objects.select_for_update()
        .filter(external_source=FIC_SOURCE, external_id=external_id)
        .first()
    )
    if alias and alias.documento_id:
        alias.documento = DocumentoFornitore.objects.select_for_update().filter(pk=alias.documento_id).first()
    return alias


def _reserve_fic_import_alias(external_id, *, motivo="import_fatture_in_cloud"):
    external_id = _clean_external_alias_value(external_id)
    if not external_id:
        return None
    alias, _created = DocumentoFornitoreImportAlias.objects.select_for_update().get_or_create(
        external_source=FIC_SOURCE,
        external_id=external_id,
        defaults={
            "documento": None,
            "ignorato": False,
            "motivo": motivo,
        },
    )
    if alias.documento_id:
        alias.documento = DocumentoFornitore.objects.select_for_update().filter(pk=alias.documento_id).first()
    return alias


def _reserve_fic_import_aliases(external_ids, *, motivo="import_fatture_in_cloud"):
    aliases = []
    for external_id in external_ids:
        alias = _reserve_fic_import_alias(external_id, motivo=motivo)
        if alias is not None:
            aliases.append(alias)
    return aliases


def _upsert_document_import_alias(documento, external_source, external_id, *, motivo=""):
    external_source = _clean_external_alias_value(external_source)
    external_id = _clean_external_alias_value(external_id)
    if not external_source or not external_id:
        return None
    alias, _created = DocumentoFornitoreImportAlias.objects.update_or_create(
        external_source=external_source,
        external_id=external_id,
        defaults={
            "documento": documento,
            "ignorato": False,
            "motivo": motivo,
        },
    )
    return alias


def _ignore_document_import_alias(external_source, external_id, *, motivo=""):
    external_source = _clean_external_alias_value(external_source)
    external_id = _clean_external_alias_value(external_id)
    if not external_source or not external_id:
        return None
    alias, _created = DocumentoFornitoreImportAlias.objects.update_or_create(
        external_source=external_source,
        external_id=external_id,
        defaults={
            "documento": None,
            "ignorato": True,
            "motivo": motivo,
        },
    )
    return alias


def registra_alias_import_documento_fornitore(documento, *, motivo="import_fatture_in_cloud"):
    return _upsert_document_import_alias(documento, documento.external_source, documento.external_id, motivo=motivo)


def assorbi_alias_import_documento_fornitore(documento_duplicato, documento_keep, *, motivo="pulizia_duplicati"):
    if not documento_duplicato or not documento_keep or documento_duplicato.pk == documento_keep.pk:
        return 0

    aggiornati = 0
    if documento_duplicato.external_source and documento_duplicato.external_id:
        _upsert_document_import_alias(
            documento_keep,
            documento_duplicato.external_source,
            documento_duplicato.external_id,
            motivo=motivo,
        )
        aggiornati += 1

    aggiornati += DocumentoFornitoreImportAlias.objects.filter(documento=documento_duplicato).update(
        documento=documento_keep,
        ignorato=False,
        motivo=motivo,
        data_aggiornamento=timezone.now(),
    )
    return aggiornati


def ignora_alias_import_documento_fornitore(documento, *, motivo="documento_eliminato"):
    if not documento:
        return 0

    aggiornati = 0
    if documento.external_source and documento.external_id:
        _ignore_document_import_alias(documento.external_source, documento.external_id, motivo=motivo)
        aggiornati += 1

    aggiornati += DocumentoFornitoreImportAlias.objects.filter(documento=documento).update(
        documento=None,
        ignorato=True,
        motivo=motivo,
        data_aggiornamento=timezone.now(),
    )
    return aggiornati


def _skipped_import_result(documento=None, *, reason=""):
    return {
        "documento": documento,
        "created": False,
        "updated": False,
        "skipped": True,
        "skip_reason": reason,
        "fornitore_created": False,
        "fornitore_updated": False,
        "scadenze_create": 0,
        "pagamenti_auto": 0,
        "notifica_created": False,
    }


def _document_is_before_sync_start(document_data, data_inizio):
    if not data_inizio:
        return False
    document_date = _document_date_for_sync_filter(_as_dict(document_data))
    return bool(document_date and document_date < data_inizio)


def _scadenza_modificabile_da_import(scadenza):
    return (
        scadenza.importo_pagato == Decimal("0.00")
        and not scadenza.data_pagamento
        and not scadenza.movimento_finanziario_id
        and not scadenza.pagamenti.exists()
    )


def _create_deadlines(documento, deadlines):
    created = 0
    for deadline in deadlines:
        ScadenzaPagamentoFornitore.objects.create(
            documento=documento,
            data_scadenza=deadline["data_scadenza"],
            importo_previsto=deadline["importo_previsto"],
            importo_pagato=deadline["importo_pagato"],
            data_pagamento=deadline["data_pagamento"],
        )
        created += 1
    return created


def _sync_document_deadlines(documento, deadlines, *, clear_existing=False):
    if clear_existing:
        existing = list(documento.scadenze.order_by("id"))
        if existing and all(_scadenza_modificabile_da_import(scadenza) for scadenza in existing):
            documento.scadenze.all().delete()
        elif existing:
            for scadenza in existing:
                if scadenza.stato != StatoScadenzaFornitore.ANNULLATA:
                    scadenza.stato = StatoScadenzaFornitore.ANNULLATA
                    scadenza.save(update_fields=["stato", "data_aggiornamento"])
        return 0

    deadlines = _deduplicate_payment_deadlines(deadlines, expected_total=documento.totale_da_pagare)
    if not deadlines:
        return 0

    existing = list(documento.scadenze.order_by("id"))
    if not existing:
        return _create_deadlines(documento, deadlines)

    if not all(_scadenza_modificabile_da_import(scadenza) for scadenza in existing):
        return 0

    if len(existing) != len(deadlines):
        documento.scadenze.all().delete()
        return _create_deadlines(documento, deadlines)

    updated = 0
    for scadenza, deadline in zip(existing, deadlines):
        changed = False
        for field_name in ("data_scadenza", "importo_previsto", "importo_pagato", "data_pagamento"):
            value = deadline[field_name]
            if getattr(scadenza, field_name) != value:
                setattr(scadenza, field_name, value)
                changed = True
        if changed:
            scadenza.save()
            updated += 1
    return updated


def _auto_reconcile_imported_supplier_deadlines(documento, *, utente=None):
    pagamenti_creati = 0
    scadenze = documento.scadenze.select_related("documento", "documento__fornitore").order_by("data_scadenza", "id")
    for scadenza in scadenze:
        if scadenza.importo_residuo <= Decimal("0.00"):
            continue
        candidati = trova_movimenti_candidati_per_scadenza_fornitore(scadenza, limite=3)
        if not candidati:
            continue

        top_score = candidati[0].score
        migliori = [candidato for candidato in candidati if candidato.score == top_score]
        if top_score < FIC_AUTO_MATCH_MIN_SCORE or len(migliori) != 1:
            continue

        candidato = migliori[0]
        importo = min(candidato.importo_disponibile, scadenza.importo_residuo)
        if abs(importo - scadenza.importo_residuo) > Decimal("0.01"):
            continue

        try:
            riconcilia_movimento_con_scadenza_fornitore(
                candidato.movimento,
                scadenza,
                importo=importo,
                utente=utente,
                note="Riconciliazione automatica da import Fatture in Cloud",
            )
        except ValidationError:
            continue
        pagamenti_creati += 1
    return pagamenti_creati


def _update_document_fields(documento, document_data, fornitore, pending, *, source_doc_type=None):
    e_invoice = _as_dict(document_data.get("e_invoice"))
    amounts = _as_dict(document_data.get("amounts"))
    doc_date = _document_date(document_data)
    withholding = _document_withholding(document_data)
    amount_net = _as_decimal(
        document_data.get("amount_net")
        or amounts.get("net")
        or amounts.get("amount_net")
    )
    amount_vat = _as_decimal(
        document_data.get("amount_vat")
        or amounts.get("vat")
        or amounts.get("amount_vat")
    )
    amount_gross = _document_total(document_data)
    if amount_gross == Decimal("0.00") and amount_net:
        amount_gross = amount_net + amount_vat

    documento.fornitore = fornitore
    documento.tipo_documento = _document_type(document_data, source_doc_type)
    documento.numero_documento = _invoice_number(document_data)
    documento.data_documento = doc_date
    documento.data_ricezione = _as_date(
        document_data.get("received_at")
        or document_data.get("created_at")
        or e_invoice.get("received_at")
    )
    documento.anno_competenza = doc_date.year
    documento.mese_competenza = doc_date.month
    documento.descrizione = _document_description(document_data)
    descrizione_righe_fattura = _document_invoice_line_description_text(document_data)
    if descrizione_righe_fattura or not documento.descrizione_righe_fattura:
        documento.descrizione_righe_fattura = descrizione_righe_fattura
    documento.imponibile = amount_net
    documento.iva = amount_vat
    documento.totale = amount_gross
    documento.imponibile_ritenuta_acconto = withholding["imponibile"]
    documento.aliquota_ritenuta_acconto = withholding["aliquota"]
    documento.ritenuta_acconto = withholding["ritenuta"]
    documento.aliquota_iva = Decimal("0.00")
    if amount_net:
        documento.aliquota_iva = (amount_vat * Decimal("100") / amount_net).quantize(Decimal("0.01"))
    if documento.stato != StatoDocumentoFornitore.COMPENSATO:
        documento.stato = _state_from_document(
            max(amount_gross - withholding["ritenuta"], Decimal("0.00")),
            _payment_items(document_data),
            document_data,
            source_doc_type,
        )
    documento.origine = OrigineDocumentoFornitore.FATTURE_IN_CLOUD
    documento.external_source = FIC_SOURCE
    documento.external_id = str(document_data.get("id") or "")
    documento.external_type = "pending" if pending else (source_doc_type or document_data.get("type") or "")
    documento.external_url = _limit_model_field(
        DocumentoFornitore,
        "external_url",
        document_data.get("attachment_url") or document_data.get("attachment_preview_url") or "",
    )
    documento.external_payload = document_data
    documento.importato_at = documento.importato_at or timezone.now()
    documento.external_updated_at = _as_datetime(document_data.get("updated_at"))
    return documento


@transaction.atomic
def importa_documento_fatture_in_cloud(connessione, document_data, *, pending=False, utente=None, source_doc_type=None):
    if not document_data or not document_data.get("id"):
        raise ValidationError("Documento Fatture in Cloud privo di ID.")

    external_id = _clean_external_alias_value(document_data.get("id"))
    entity = _enrich_supplier_entity_from_document(_entity_from_document(document_data), document_data)
    signature_alias_ids = _document_import_signature_alias_ids(document_data, entity, source_doc_type)
    import_alias = _reserve_fic_import_alias(external_id, motivo="import_fatture_in_cloud")
    signature_aliases = _reserve_fic_import_aliases(
        signature_alias_ids,
        motivo="firma_import_fatture_in_cloud",
    )
    signature_alias = next(
        (alias for alias in signature_aliases if not alias.ignorato and alias.documento is not None),
        None,
    )
    ignored_signature_alias = next((alias for alias in signature_aliases if alias.ignorato), None)
    if import_alias and import_alias.ignorato:
        return _skipped_import_result(import_alias.documento, reason="alias_ignorato")
    if ignored_signature_alias and signature_alias is None:
        return _skipped_import_result(ignored_signature_alias.documento, reason="firma_import_ignorata")

    documento = None
    documento_da_firma_import = False
    if import_alias and import_alias.documento is not None:
        documento = import_alias.documento
        if not (
            documento.external_source == FIC_SOURCE
            and _clean_external_alias_value(documento.external_id) == external_id
        ):
            return _skipped_import_result(documento, reason="alias_assorbito")
    elif signature_alias:
        documento = signature_alias.documento
        documento_da_firma_import = documento is not None

    if documento_da_firma_import:
        if _should_replace_supplier_after_signature_match(documento.fornitore, entity, document_data):
            fornitore, fornitore_created, fornitore_updated = _find_or_create_supplier(entity, document_data)
        else:
            fornitore = documento.fornitore
            fornitore_created = False
            fornitore_updated = _update_supplier_missing_fields(fornitore, entity)
    else:
        fornitore, fornitore_created, fornitore_updated = _find_or_create_supplier(entity, document_data)
    if documento is None:
        documento = (
            DocumentoFornitore.objects.select_for_update()
            .filter(external_source=FIC_SOURCE, external_id=external_id)
            .first()
        )
    created = False
    if documento is None:
        documento = DocumentoFornitore.objects.select_for_update().filter(
            fornitore=fornitore,
            tipo_documento=_document_type(document_data, source_doc_type),
            numero_documento=_invoice_number(document_data),
            data_documento=_document_date(document_data),
        ).first()
    if documento is None:
        documento = _find_existing_document_by_import_signature(document_data, fornitore, entity, source_doc_type)
    if documento is None:
        documento = DocumentoFornitore()
        created = True

    previous_external_source = documento.external_source if documento.pk else ""
    previous_external_id = documento.external_id if documento.pk else ""
    _update_document_fields(documento, document_data, fornitore, pending, source_doc_type=source_doc_type)
    documento.save()
    registra_alias_import_documento_fornitore(documento, motivo="import_fatture_in_cloud")
    for signature_alias_id in signature_alias_ids:
        _upsert_document_import_alias(documento, FIC_SOURCE, signature_alias_id, motivo="firma_import_fatture_in_cloud")
    if previous_external_source and previous_external_id and (
        previous_external_source != documento.external_source or previous_external_id != documento.external_id
    ):
        _upsert_document_import_alias(
            documento,
            previous_external_source,
            previous_external_id,
            motivo="alias_precedente_import",
        )

    attachment_result = _salva_allegato_fatture_in_cloud(documento, document_data)
    if attachment_result.get("saved") or attachment_result.get("error"):
        _external_payload_with_attachment_result(documento, attachment_result)
        documento.save(update_fields=["allegato", "external_payload", "data_aggiornamento"])

    is_credit_note = documento.tipo_documento == TipoDocumentoFornitore.NOTA_CREDITO
    is_compensated = documento.stato == StatoDocumentoFornitore.COMPENSATO
    if is_compensated:
        scadenze_create = 0
        pagamenti_auto = 0
    else:
        scadenze_create = _sync_document_deadlines(
            documento,
            _payment_deadlines(document_data, source_doc_type),
            clear_existing=is_credit_note,
        )
        pagamenti_auto = 0 if is_credit_note else _auto_reconcile_imported_supplier_deadlines(documento, utente=utente)
        aggiorna_stato_documento_da_scadenze(documento)
    _notifica, notifica_created = crea_notifica_finanziaria(
        titolo="Nuova nota di credito ricevuta" if is_credit_note and created else (
            "Nota di credito aggiornata" if is_credit_note else (
                "Nuova fattura fornitore ricevuta" if created else "Fattura fornitore aggiornata"
            )
        ),
        messaggio=f"{documento.fornitore} - {documento.numero_documento} - EUR {documento.totale}",
        tipo="fattura_ricevuta",
        url=reverse("modifica_documento_fornitore", kwargs={"pk": documento.pk}),
        documento=documento,
        chiave_deduplica=f"fic-document-{external_id}",
        payload={"connessione_id": connessione.pk if connessione else None, "pending": pending},
    )
    return {
        "documento": documento,
        "created": created,
        "updated": not created,
        "fornitore_created": fornitore_created,
        "fornitore_updated": fornitore_updated,
        "scadenze_create": scadenze_create,
        "pagamenti_auto": pagamenti_auto,
        "notifica_created": notifica_created,
    }


class FattureInCloudClient:
    def __init__(self, connessione: FattureInCloudConnessione):
        self.connessione = connessione
        self.base_url = (connessione.base_url or DEFAULT_BASE_URL).rstrip("/")

    @property
    def access_token(self):
        return decifra_testo_safe(self.connessione.access_token_cifrato)

    @property
    def refresh_token(self):
        return decifra_testo_safe(self.connessione.refresh_token_cifrato)

    @property
    def client_id(self):
        return configured_oauth_client_id(self.connessione)

    @property
    def client_secret(self):
        return configured_oauth_client_secret(self.connessione)

    def _headers(self):
        token = self.access_token
        if not token:
            raise FattureInCloudError("Access token Fatture in Cloud non configurato.")
        return {
            "Accept": "application/json",
            "Authorization": f"Bearer {token}",
        }

    def request(self, method, path, *, params=None, json=None, retry_refresh=True):
        url = f"{self.base_url}{path}"
        try:
            response = requests.request(
                method,
                url,
                params=params,
                json=json,
                headers=self._headers(),
                timeout=_api_timeout(),
            )
        except requests.RequestException as exc:
            raise FattureInCloudError(f"Connessione API Fatture in Cloud fallita: {exc}") from exc
        if response.status_code == 401 and retry_refresh and self.refresh_token:
            self.refresh_access_token()
            return self.request(method, path, params=params, json=json, retry_refresh=False)
        if response.status_code >= 400:
            raise FattureInCloudError(f"Errore API Fatture in Cloud {response.status_code}: {response.text[:500]}")
        if not response.content:
            return {}
        return _response_json(response, "Errore API Fatture in Cloud")

    def refresh_access_token(self):
        if not self.client_id or not self.refresh_token:
            raise FattureInCloudError("Refresh token o client ID mancanti.")
        payload = {
            "grant_type": "refresh_token",
            "client_id": self.client_id,
            "refresh_token": self.refresh_token,
        }
        if self.client_secret:
            payload["client_secret"] = self.client_secret
        try:
            response = requests.post(TOKEN_URL, json=payload, timeout=_api_timeout())
        except requests.RequestException as exc:
            raise FattureInCloudError(f"Refresh token fallito: impossibile contattare Fatture in Cloud ({exc}).") from exc
        if response.status_code >= 400:
            raise FattureInCloudError(f"Refresh token fallito: {response.text[:500]}")
        self._store_tokens(_response_json(response, "Refresh token fallito"))

    def exchange_code(self, code, redirect_uri):
        if not self.client_id or not self.client_secret:
            raise FattureInCloudError("Client ID o Client Secret Fatture in Cloud mancanti.")
        payload = {
            "grant_type": "authorization_code",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "redirect_uri": redirect_uri,
            "code": code,
        }
        try:
            response = requests.post(TOKEN_URL, json=payload, timeout=_api_timeout())
        except requests.RequestException as exc:
            raise FattureInCloudError(f"Scambio code fallito: impossibile contattare Fatture in Cloud ({exc}).") from exc
        if response.status_code >= 400:
            raise FattureInCloudError(f"Scambio code fallito: {response.text[:500]}")
        self._store_tokens(_response_json(response, "Scambio code fallito"))

    def _store_tokens(self, payload):
        access_token = payload.get("access_token") or ""
        refresh_token = payload.get("refresh_token") or ""
        expires_in = payload.get("expires_in")
        update_fields = ["data_aggiornamento", "stato"]
        if access_token:
            self.connessione.access_token_cifrato = cifra_testo(access_token)
            update_fields.append("access_token_cifrato")
        if refresh_token:
            self.connessione.refresh_token_cifrato = cifra_testo(refresh_token)
            update_fields.append("refresh_token_cifrato")
        if expires_in:
            try:
                expires_in_seconds = int(expires_in)
            except (TypeError, ValueError):
                expires_in_seconds = 0
            if expires_in_seconds > 0:
                self.connessione.token_scadenza = timezone.now() + timedelta(seconds=expires_in_seconds)
                update_fields.append("token_scadenza")
        self.connessione.stato = StatoConnessioneFattureInCloud.ATTIVA
        self.connessione.save(update_fields=update_fields)

    def list_user_companies(self):
        data = self.request("GET", "/user/companies").get("data", [])
        if isinstance(data, dict):
            companies = data.get("companies") or []
        else:
            companies = data or []
        return [company for company in companies if isinstance(company, dict)]

    def list_received_documents(self, doc_type, *, page=1, per_page=50, data_inizio=None):
        params = {
            "type": doc_type,
            "page": page,
            "per_page": per_page,
            "sort": "-date,-id",
            "fieldset": "detailed",
        }
        if data_inizio:
            params["date_from"] = data_inizio.isoformat()
        return self.request("GET", f"/c/{self.connessione.company_id}/received_documents", params=params)

    def get_received_document(self, document_id):
        return self.request(
            "GET",
            f"/c/{self.connessione.company_id}/received_documents/{document_id}",
            params={"fieldset": "detailed"},
        ).get("data", {})

    def get_supplier(self, supplier_id):
        return self.request(
            "GET",
            f"/c/{self.connessione.company_id}/entities/suppliers/{supplier_id}",
            params={"fieldset": "detailed"},
        ).get("data", {})

    def list_pending_received_documents(self, doc_type, *, page=1, per_page=50, data_inizio=None):
        params = {
            "type": doc_type,
            "page": page,
            "per_page": per_page,
            "sort": "-date,-id",
            "fieldset": "detailed",
        }
        if data_inizio:
            params["date_from"] = data_inizio.isoformat()
        return self.request("GET", f"/c/{self.connessione.company_id}/received_documents/pending", params=params)

    def get_pending_received_document(self, document_id):
        return self.request(
            "GET",
            f"/c/{self.connessione.company_id}/received_documents/pending/{document_id}",
            params={"fieldset": "detailed"},
        ).get("data", {})


def authorization_url(connessione, redirect_uri, state, scopes=DEFAULT_SCOPES):
    client_id = configured_oauth_client_id(connessione)
    if not client_id:
        raise FattureInCloudError("Client ID Fatture in Cloud mancante.")
    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "scope": scopes,
        "state": state,
    }
    return f"{AUTHORIZATION_URL}?{urlencode(params)}"


def _iter_paginated(fetch_page):
    page = 1
    while True:
        payload = fetch_page(page)
        items = payload.get("data") or []
        for item in items:
            yield item
        pagination = payload.get("pagination") or {}
        current = pagination.get("current_page") or page
        last_page = pagination.get("last_page") or current
        if not items or current >= last_page:
            break
        page += 1


def _document_detail_from_summary(client, summary, *, pending, supplier_context=None):
    if not isinstance(summary, dict):
        return summary
    document_id = summary.get("id")
    if not document_id:
        return _document_with_external_supplier_details(
            client,
            summary,
            supplier_context,
            include_attachment=pending,
        )
    detail = client.get_pending_received_document(document_id) if pending else client.get_received_document(document_id)
    if not isinstance(detail, dict) or not detail:
        return _document_with_external_supplier_details(
            client,
            summary,
            supplier_context,
            include_attachment=pending,
        )
    return _document_with_external_supplier_details(
        client,
        {**summary, **detail},
        supplier_context,
        include_attachment=pending,
    )


def _check_sync_budget(start, max_seconds):
    if max_seconds and time.monotonic() - start >= max_seconds:
        raise FattureInCloudSyncBudgetExceeded(
            "Tempo massimo della sincronizzazione raggiunto prima del completamento. "
            "Alcuni documenti potrebbero essere gia stati importati: ripeti la sincronizzazione per continuare."
        )


def _add_import_result_to_stats(stats, result):
    stats["creati"] += 1 if result.get("created") else 0
    stats["aggiornati"] += 1 if result.get("updated") else 0
    stats["ignorati"] += 1 if result.get("skipped") else 0
    stats["scadenze"] += result.get("scadenze_create", 0)
    stats["pagamenti_auto"] += result.get("pagamenti_auto", 0)
    stats["notifiche"] += 1 if result.get("notifica_created") else 0
    stats["fornitori_creati"] += 1 if result.get("fornitore_created") else 0
    stats["fornitori_aggiornati"] += 1 if result.get("fornitore_updated") else 0


def _sync_summary_label(doc_type, pending):
    prefix = "Da registrare" if pending else "Registrati"
    return f"{prefix} {doc_type}"


def sincronizza_fatture_in_cloud(connessione, *, utente=None, max_seconds=None, data_inizio=None):
    start = time.monotonic()
    if max_seconds is None:
        max_seconds = _sync_max_seconds()
    stats = {
        "creati": 0,
        "aggiornati": 0,
        "ignorati": 0,
        "scadenze": 0,
        "notifiche": 0,
        "pagamenti_auto": 0,
        "fornitori_creati": 0,
        "fornitori_aggiornati": 0,
        "messaggi": [],
        "interrotta_per_tempo": False,
    }
    esito = EsitoSincronizzazione.OK
    client = FattureInCloudClient(connessione)
    supplier_context = {"cache": {}, "warnings": set()}

    try:
        if not connessione.company_id:
            raise FattureInCloudError("Company ID non configurato.")

        if connessione.sincronizza_documenti_registrati:
            for doc_type in RECEIVED_DOCUMENT_TYPES:
                label = _sync_summary_label(doc_type, pending=False)
                try:
                    _check_sync_budget(start, max_seconds)
                    for summary in _iter_paginated(
                        lambda page: client.list_received_documents(doc_type, page=page, data_inizio=data_inizio)
                    ):
                        if _document_is_before_sync_start(summary, data_inizio):
                            break
                        _check_sync_budget(start, max_seconds)
                        try:
                            document = _document_detail_from_summary(
                                client,
                                summary,
                                pending=False,
                                supplier_context=supplier_context,
                            )
                            if _document_is_before_sync_start(document, data_inizio):
                                continue
                            result = importa_documento_fatture_in_cloud(
                                connessione,
                                document,
                                pending=False,
                                utente=utente,
                                source_doc_type=doc_type,
                            )
                            _add_import_result_to_stats(stats, result)
                        except FattureInCloudSyncBudgetExceeded:
                            raise
                        except (FattureInCloudError, ValidationError) as exc:
                            esito = EsitoSincronizzazione.PARZIALE
                            stats["messaggi"].append(f"{label}: documento {summary.get('id') or '-'}: {exc}")
                except FattureInCloudSyncBudgetExceeded:
                    raise
                except FattureInCloudError as exc:
                    esito = EsitoSincronizzazione.PARZIALE
                    stats["messaggi"].append(f"{label}: {exc}")

        if connessione.sincronizza_documenti_da_registrare:
            for doc_type in PENDING_DOCUMENT_TYPES:
                label = _sync_summary_label(doc_type, pending=True)
                try:
                    _check_sync_budget(start, max_seconds)
                    documents = _iter_paginated(
                        lambda page: client.list_pending_received_documents(
                            doc_type,
                            page=page,
                            data_inizio=data_inizio,
                        )
                    )
                    for summary in documents:
                        if _document_is_before_sync_start(summary, data_inizio):
                            break
                        _check_sync_budget(start, max_seconds)
                        try:
                            document = _document_detail_from_summary(
                                client,
                                summary,
                                pending=True,
                                supplier_context=supplier_context,
                            )
                            if _document_is_before_sync_start(document, data_inizio):
                                continue
                            result = importa_documento_fatture_in_cloud(
                                connessione,
                                document,
                                pending=True,
                                utente=utente,
                            )
                            _add_import_result_to_stats(stats, result)
                        except FattureInCloudSyncBudgetExceeded:
                            raise
                        except (FattureInCloudError, ValidationError) as exc:
                            esito = EsitoSincronizzazione.PARZIALE
                            stats["messaggi"].append(f"{label}: documento {summary.get('id') or '-'}: {exc}")
                except FattureInCloudSyncBudgetExceeded:
                    raise
                except FattureInCloudError as exc:
                    esito = EsitoSincronizzazione.PARZIALE
                    stats["messaggi"].append(f"{label}: {exc}")

        if supplier_context.get("warnings") and esito == EsitoSincronizzazione.OK:
            esito = EsitoSincronizzazione.PARZIALE

        if not stats["messaggi"]:
            stats["messaggi"].append(
                f"Importati {stats['creati']} nuovi documenti, aggiornati {stats['aggiornati']} documenti. "
                f"Ignorati {stats['ignorati']} documenti gia gestiti. "
                f"Fornitori: {stats['fornitori_creati']} creati, "
                f"{stats['fornitori_aggiornati']} aggiornati. "
                f"Pagamenti riconosciuti: {stats['pagamenti_auto']}."
            )
    except FattureInCloudSyncBudgetExceeded as exc:
        esito = EsitoSincronizzazione.PARZIALE
        stats["interrotta_per_tempo"] = True
        stats["messaggi"].append(str(exc))
    except Exception as exc:
        esito = EsitoSincronizzazione.ERRORE
        stats["messaggi"].append(str(exc))
        crea_notifica_finanziaria(
            titolo="Errore sincronizzazione Fatture in Cloud",
            messaggio=str(exc),
            tipo="integrazione",
            livello="errore",
            richiede_gestione=True,
            chiave_deduplica=f"fic-sync-error-{connessione.pk}-{timezone.localdate().isoformat()}",
        )
    finally:
        for warning in sorted(supplier_context.get("warnings") or []):
            if warning not in stats["messaggi"]:
                stats["messaggi"].append(warning)
        durata_ms = int((time.monotonic() - start) * 1000)
        messaggio = "\n".join(stats["messaggi"])[:4000]
        connessione.ultimo_sync_at = timezone.now()
        connessione.ultimo_esito = esito
        connessione.ultimo_messaggio = messaggio
        connessione.in_corso = False
        connessione.stato = (
            StatoConnessioneFattureInCloud.ATTIVA
            if esito != EsitoSincronizzazione.ERRORE
            else StatoConnessioneFattureInCloud.ERRORE
        )
        connessione.save(
            update_fields=[
                "ultimo_sync_at",
                "ultimo_esito",
                "ultimo_messaggio",
                "in_corso",
                "stato",
                "data_aggiornamento",
            ]
        )
        FattureInCloudSyncLog.objects.create(
            connessione=connessione,
            tipo_operazione=TipoSyncFattureInCloud.COMPLETA,
            esito=esito,
            documenti_creati=stats["creati"],
            documenti_aggiornati=stats["aggiornati"],
            scadenze_create=stats["scadenze"],
            notifiche_create=stats["notifiche"],
            durata_millisecondi=durata_ms,
            messaggio=messaggio,
        )
    stats["esito"] = esito
    if esito == EsitoSincronizzazione.ERRORE:
        raise FattureInCloudError(stats["messaggi"][-1])
    return stats


def importa_documento_da_webhook(connessione, notification_type, document_id, *, utente=None):
    client = FattureInCloudClient(connessione)
    supplier_context = {"cache": {}, "warnings": set()}
    pending = notification_type.endswith("received_documents.e_invoices.receive")
    if pending:
        document = client.get_pending_received_document(document_id)
    else:
        document = client.get_received_document(document_id)
    document = _document_with_external_supplier_details(
        client,
        document,
        supplier_context,
        include_attachment=pending,
    )
    result = importa_documento_fatture_in_cloud(connessione, document, pending=pending, utente=utente)
    FattureInCloudSyncLog.objects.create(
        connessione=connessione,
        tipo_operazione=TipoSyncFattureInCloud.WEBHOOK,
        esito=EsitoSincronizzazione.OK,
        documenti_creati=1 if result["created"] else 0,
        documenti_aggiornati=1 if result["updated"] else 0,
        scadenze_create=result["scadenze_create"],
        notifiche_create=1 if result["notifica_created"] else 0,
        messaggio=f"Webhook {notification_type}: documento {document_id}",
    )
    return result
