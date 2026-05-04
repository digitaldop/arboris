import json

from .fatture_in_cloud import (
    _as_dict,
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


def payload_debug_report(payload, *, source, document_id, max_depth=5, max_list_items=2):
    entity = _as_dict(payload.get("entity") or payload.get("supplier"))
    e_invoice = payload.get("e_invoice")
    extra_data = payload.get("extra_data")
    entity_supplier = _normalize_entity(entity)
    e_invoice_supplier = _e_invoice_supplier_candidate(payload)
    normalized_supplier = _entity_from_document(payload)
    supplier_payment_data = _supplier_payment_data_from_document(payload)
    return {
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


def payload_debug_report_json(payload, *, source, document_id, max_depth=5, max_list_items=2):
    report = payload_debug_report(
        payload,
        source=source,
        document_id=document_id,
        max_depth=max_depth,
        max_list_items=max_list_items,
    )
    return json.dumps(report, ensure_ascii=False, indent=2)
