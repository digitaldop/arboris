import re
import zipfile
from io import BytesIO
from pathlib import PurePosixPath
from urllib.parse import unquote, urlparse
from xml.etree import ElementTree

import requests


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


def extension_from_name(value):
    if not value:
        return ""
    parsed = urlparse(str(value))
    path = parsed.path or str(value)
    suffixes = PurePosixPath(unquote(path)).suffixes
    return "".join(suffixes[-2:]).lower() if suffixes[-2:] == [".xml", ".p7m"] else (suffixes[-1].lower() if suffixes else "")


def attachment_metadata(payload):
    metadata = []
    if payload.get("attachment_url"):
        metadata.append(
            {
                "source": "attachment_url",
                "url_present": True,
                "filename_extension": extension_from_name(payload.get("filename") or payload.get("attachment_url")),
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
                "filename_extension": extension_from_name(attachment.get("filename")),
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


def supplier_from_e_invoice_xml(xml_text):
    xml_text = re.sub(r"^\s*<\?xml[^>]*\?>", "", xml_text or "", count=1)
    try:
        root = ElementTree.fromstring(xml_text)
    except ElementTree.ParseError:
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


def decode_xml_bytes(data):
    for encoding in ("utf-8-sig", "utf-8", "iso-8859-1"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return ""


def xml_text_from_bytes(data):
    if not data:
        return "", ""
    stripped = data.lstrip()
    if stripped.startswith(b"<"):
        text = decode_xml_bytes(stripped)
        return text, "direct_xml" if "FatturaElettronica" in text else "xml_like"

    match = XML_IN_BINARY_RE.search(data)
    if match:
        return decode_xml_bytes(match.group(0)), "embedded_xml"

    if zipfile.is_zipfile(BytesIO(data)):
        try:
            with zipfile.ZipFile(BytesIO(data)) as archive:
                for name in archive.namelist():
                    if not name.lower().endswith(".xml"):
                        continue
                    xml_data = archive.read(name)[:MAX_ATTACHMENT_BYTES]
                    text = decode_xml_bytes(xml_data)
                    if "FatturaElettronica" in text:
                        return text, "zip_xml"
        except (OSError, zipfile.BadZipFile, RuntimeError):
            return "", "zip_unreadable"
        return "", "zip_without_invoice_xml"

    return "", ""


def content_kind(data, content_type):
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


def download_bytes(url, *, timeout):
    parsed = urlparse(url or "")
    if parsed.scheme not in {"http", "https"}:
        return None, {"download_status": "invalid_url"}
    try:
        response = requests.get(url, stream=True, timeout=timeout)
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


def attachment_url_from_payload(payload):
    return payload.get("attachment_url") or ""


def supplier_from_attachment_payload(payload, *, timeout):
    url = attachment_url_from_payload(payload)
    if not url:
        return {}
    data, _download_info = download_bytes(url, timeout=timeout)
    if data is None:
        return {}
    xml_text, _xml_source = xml_text_from_bytes(data)
    return supplier_from_e_invoice_xml(xml_text) if xml_text else {}


def attachment_debug_report(payload, *, timeout):
    url = attachment_url_from_payload(payload)
    report = {
        "attachment_url_present": bool(url),
        "attachments_metadata": attachment_metadata(payload),
    }
    if not url:
        return report, {}

    data, download_info = download_bytes(url, timeout=timeout)
    report.update(download_info)
    if data is None:
        return report, {}

    content_type = download_info.get("content_type", "")
    xml_text, xml_source = xml_text_from_bytes(data)
    supplier_from_xml = supplier_from_e_invoice_xml(xml_text) if xml_text else {}
    report.update(
        {
            "content_kind": content_kind(data, content_type),
            "xml_detected": bool(xml_text),
            "xml_source": xml_source,
            "cedente_prestatore_detected": bool(supplier_from_xml),
        }
    )
    return report, supplier_from_xml
