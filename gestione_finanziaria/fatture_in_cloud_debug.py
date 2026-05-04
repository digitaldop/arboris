import json
import re
import zipfile
from io import BytesIO
from pathlib import PurePosixPath
from urllib.parse import unquote, urlparse
from xml.etree import ElementTree

import requests

from .fatture_in_cloud import (
    _as_dict,
    _api_timeout,
    _dict_value,
    _e_invoice_header,
    _entity_from_document,
    _normalize_entity,
    _supplier_payment_data_from_document,
)


SUPPLIER_FIELDS = (
    "name",
    "first_name",
    "last_name",
    "vat_number",
    "tax_code",
    "address_street",
    "address_postal_code",
    "address_city",
    "address_province",
    "email",
    "certified_email",
    "phone",
    "ei_code",
    "bank_iban",
    "bank_name",
)

XML_MARKERS = ("FatturaElettronica", "CedentePrestatore", "DatiAnagrafici")
MAX_ATTACHMENT_BYTES = 4 * 1024 * 1024
XML_IN_BINARY_RE = re.compile(
    rb'(?:<\?xml[^>]*>\s*)?<(?:[A-Za-z0-9_]+:)?FatturaElettronica\b.*?</(?:[A-Za-z0-9_]+:)?FatturaElettronica>',
    re.DOTALL,
)


def _redacted_value(value, *, depth, max_depth, max_list_items):
    if isinstance(value, dict):
        if depth >= max_depth:
            return {"__type": "dict", "__keys": sorted(str(key) for key in value.keys())}
        return {
            str(key): _redacted_value(item, depth=depth + 1, max_depth=max_depth, max_list_items=max_list_items)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return {
            "__type": "list",
            "__len": len(value),
            "__items": [
                _redacted_value(item, depth=depth + 1, max_depth=max_depth, max_list_items=max_list_items)
                for item in value[:max_list_items]
            ],
        }
    if isinstance(value, str):
        return {"__type": "str", "__len": len(value)}
    if value is None:
        return None
    if isinstance(value, bool):
        return {"__type": "bool"}
    if isinstance(value, (int, float)):
        return {"__type": "number"}
    return {"__type": type(value).__name__}


def _top_keys(value):
    value = _as_dict(value)
    return sorted(str(key) for key in value.keys())


def _presence_map(data, fields):
    data = _as_dict(data)
    return {field: bool(data.get(field)) for field in fields}


def _e_invoice_supplier_candidate(payload):
    e_invoice = _as_dict(payload.get("e_invoice"))
    header = _e_invoice_header(e_invoice)
    return _normalize_entity(
        _dict_value(header, "CedentePrestatore", "cedente_prestatore", "cedentePrestatore")
    )


def _find_xml_markers(value, *, path="$", matches=None, max_matches=20):
    if matches is None:
        matches = []
    if len(matches) >= max_matches:
        return matches
    if isinstance(value, dict):
        for key, item in value.items():
            _find_xml_markers(item, path=f"{path}.{key}", matches=matches, max_matches=max_matches)
            if len(matches) >= max_matches:
                break
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _find_xml_markers(item, path=f"{path}[{index}]", matches=matches, max_matches=max_matches)
            if len(matches) >= max_matches:
                break
    elif isinstance(value, str) and any(marker in value for marker in XML_MARKERS):
        matches.append({"path": path, "string_length": len(value)})
    return matches


def _extension_from_name(value):
    if not value:
        return ""
    parsed = urlparse(str(value))
    path = parsed.path or str(value)
    suffixes = PurePosixPath(unquote(path)).suffixes
    return "".join(suffixes[-2:]).lower() if suffixes[-2:] == [".xml", ".p7m"] else (suffixes[-1].lower() if suffixes else "")


def _attachment_metadata(payload):
    metadata = []
    if payload.get("attachment_url"):
        metadata.append(
            {
                "source": "attachment_url",
                "url_present": True,
                "filename_extension": _extension_from_name(payload.get("filename") or payload.get("attachment_url")),
            }
        )
    for index, attachment in enumerate(payload.get("other_attachments") or []):
        if not isinstance(attachment, dict):
            continue
        metadata.append(
            {
                "source": f"other_attachments[{index}]",
                "url_present": bool(
                    attachment.get("url")
                    or attachment.get("download_url")
                    or attachment.get("attachment_url")
                    or attachment.get("downloadUrl")
                ),
                "filename_extension": _extension_from_name(attachment.get("filename")),
                "sub_type_present": bool(attachment.get("sub_type") or attachment.get("subType")),
                "status_present": bool(attachment.get("status")),
            }
        )
    return metadata


def _local_name(tag):
    return str(tag).split("}", 1)[-1].split(":", 1)[-1]


def _find_first(element, name):
    if element is None:
        return None
    for node in element.iter():
        if _local_name(node.tag) == name:
            return node
    return None


def _text_for(element, *path):
    current = element
    for name in path:
        current = _find_first(current, name)
        if current is None:
            return ""
    return (current.text or "").strip()


def _supplier_from_e_invoice_xml(xml_text):
    try:
        root = ElementTree.fromstring(xml_text.encode("utf-8"))
    except (ElementTree.ParseError, UnicodeEncodeError):
        return {}
    cedente = _find_first(root, "CedentePrestatore")
    if cedente is None:
        return {}
    dati = _find_first(cedente, "DatiAnagrafici")
    anagrafica = _find_first(dati, "Anagrafica")
    id_fiscale_iva = _find_first(dati, "IdFiscaleIVA")
    sede = _find_first(cedente, "Sede")
    contatti = _find_first(cedente, "Contatti")
    return {
        "name": _text_for(anagrafica, "Denominazione"),
        "first_name": _text_for(anagrafica, "Nome"),
        "last_name": _text_for(anagrafica, "Cognome"),
        "vat_number": _text_for(id_fiscale_iva, "IdCodice"),
        "tax_code": _text_for(dati, "CodiceFiscale"),
        "address_street": _text_for(sede, "Indirizzo"),
        "address_postal_code": _text_for(sede, "CAP"),
        "address_city": _text_for(sede, "Comune"),
        "address_province": _text_for(sede, "Provincia"),
        "email": _text_for(contatti, "Email"),
        "phone": _text_for(contatti, "Telefono"),
    }


def _decode_xml_bytes(data):
    for encoding in ("utf-8-sig", "utf-8", "iso-8859-1"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return ""


def _xml_text_from_bytes(data):
    if not data:
        return "", ""
    stripped = data.lstrip()
    if stripped.startswith(b"<"):
        text = _decode_xml_bytes(stripped)
        return text, "direct_xml" if "FatturaElettronica" in text else "xml_like"

    match = XML_IN_BINARY_RE.search(data)
    if match:
        return _decode_xml_bytes(match.group(0)), "embedded_xml"

    if zipfile.is_zipfile(BytesIO(data)):
        try:
            with zipfile.ZipFile(BytesIO(data)) as archive:
                for name in archive.namelist():
                    if not name.lower().endswith(".xml"):
                        continue
                    xml_data = archive.read(name)[:MAX_ATTACHMENT_BYTES]
                    text = _decode_xml_bytes(xml_data)
                    if "FatturaElettronica" in text:
                        return text, "zip_xml"
        except (OSError, zipfile.BadZipFile, RuntimeError):
            return "", "zip_unreadable"
        return "", "zip_without_invoice_xml"

    return "", ""


def _content_kind(data, content_type):
    content_type = (content_type or "").lower()
    stripped = data.lstrip()
    if "pdf" in content_type or stripped.startswith(b"%PDF"):
        return "pdf"
    if zipfile.is_zipfile(BytesIO(data)):
        return "zip"
    if stripped.startswith(b"<"):
        return "xml_like"
    if XML_IN_BINARY_RE.search(data):
        return "binary_with_embedded_xml"
    if data.startswith(b"0\x82") or data.startswith(b"0\x80"):
        return "binary_p7m_like"
    return "binary"


def _download_bytes(url):
    parsed = urlparse(url or "")
    if parsed.scheme not in {"http", "https"}:
        return None, {"download_status": "invalid_url"}
    try:
        response = requests.get(url, stream=True, timeout=_api_timeout())
    except requests.RequestException as exc:
        return None, {"download_status": "request_error", "error_type": type(exc).__name__}

    info = {
        "download_status": "ok" if response.status_code < 400 else "http_error",
        "http_status": response.status_code,
        "content_type": response.headers.get("Content-Type", ""),
        "content_length_header_present": bool(response.headers.get("Content-Length")),
    }
    if response.status_code >= 400:
        return None, info

    chunks = []
    total = 0
    truncated = False
    for chunk in response.iter_content(chunk_size=65536):
        if not chunk:
            continue
        total += len(chunk)
        if total > MAX_ATTACHMENT_BYTES:
            remaining = MAX_ATTACHMENT_BYTES - sum(len(item) for item in chunks)
            if remaining > 0:
                chunks.append(chunk[:remaining])
            truncated = True
            break
        chunks.append(chunk)
    data = b"".join(chunks)
    info["downloaded_bytes"] = len(data)
    info["truncated"] = truncated
    return data, info


def _attachment_url_from_payload(payload):
    return payload.get("attachment_url") or ""


def attachment_debug_report(payload):
    url = _attachment_url_from_payload(payload)
    report = {
        "attachment_url_present": bool(url),
        "attachments_metadata": _attachment_metadata(payload),
    }
    if not url:
        return report

    data, download_info = _download_bytes(url)
    report.update(download_info)
    if data is None:
        return report

    content_type = download_info.get("content_type", "")
    xml_text, xml_source = _xml_text_from_bytes(data)
    supplier_from_xml = _supplier_from_e_invoice_xml(xml_text) if xml_text else {}
    report.update(
        {
            "content_kind": _content_kind(data, content_type),
            "xml_detected": bool(xml_text),
            "xml_source": xml_source,
            "cedente_prestatore_detected": bool(supplier_from_xml),
            "attachment_supplier_fields_present": _presence_map(supplier_from_xml, SUPPLIER_FIELDS),
        }
    )
    return report


def payload_debug_report(payload, *, source, document_id, max_depth=5, max_list_items=2, include_attachment=False):
    entity = _as_dict(payload.get("entity") or payload.get("supplier"))
    e_invoice = payload.get("e_invoice")
    extra_data = payload.get("extra_data")
    entity_supplier = _normalize_entity(entity)
    e_invoice_supplier = _e_invoice_supplier_candidate(payload)
    normalized_supplier = _entity_from_document(payload)
    supplier_payment_data = _supplier_payment_data_from_document(payload)
    report = {
        "source": source,
        "document_id": str(document_id),
        "top_level_keys": _top_keys(payload),
        "entity_top_keys": _top_keys(entity),
        "e_invoice_type": type(e_invoice).__name__,
        "e_invoice_top_keys": _top_keys(e_invoice),
        "extra_data_type": type(extra_data).__name__,
        "extra_data_top_keys": _top_keys(extra_data),
        "entity_supplier_fields_present": _presence_map(entity_supplier, SUPPLIER_FIELDS),
        "e_invoice_supplier_fields_present": _presence_map(e_invoice_supplier, SUPPLIER_FIELDS),
        "normalized_supplier_fields_present": _presence_map(normalized_supplier, SUPPLIER_FIELDS),
        "supplier_payment_fields_present": _presence_map(supplier_payment_data, ("bank_iban", "bank_name")),
        "xml_marker_paths": _find_xml_markers(payload),
        "redacted_payload_structure": _redacted_value(
            payload,
            depth=0,
            max_depth=max_depth,
            max_list_items=max_list_items,
        ),
    }
    if include_attachment:
        report["attachment_analysis"] = attachment_debug_report(payload)
    else:
        report["attachments_metadata"] = _attachment_metadata(payload)
    return report


def payload_debug_report_json(payload, *, source, document_id, max_depth=5, max_list_items=2, include_attachment=False):
    report = payload_debug_report(
        payload,
        source=source,
        document_id=document_id,
        max_depth=max_depth,
        max_list_items=max_list_items,
        include_attachment=include_attachment,
    )
    return json.dumps(report, ensure_ascii=False, indent=2)
