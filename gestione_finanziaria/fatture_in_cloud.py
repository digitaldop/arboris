from __future__ import annotations

import time
from datetime import timedelta
from decimal import Decimal, InvalidOperation
from json import JSONDecodeError
from urllib.parse import urlencode

import requests
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime

from .models import (
    EsitoSincronizzazione,
    FattureInCloudConnessione,
    FattureInCloudSyncLog,
    Fornitore,
    OrigineDocumentoFornitore,
    ScadenzaPagamentoFornitore,
    StatoConnessioneFattureInCloud,
    StatoDocumentoFornitore,
    TipoDocumentoFornitore,
    TipoSyncFattureInCloud,
    DocumentoFornitore,
)
from .security import cifra_testo, decifra_testo_safe
from .services import aggiorna_stato_documento_da_scadenze, crea_notifica_finanziaria


FIC_SOURCE = "fatture_in_cloud"
DEFAULT_BASE_URL = "https://api-v2.fattureincloud.it"
AUTHORIZATION_URL = "https://api-v2.fattureincloud.it/oauth/authorize"
TOKEN_URL = "https://api-v2.fattureincloud.it/oauth/token"
RECEIVED_DOCUMENT_TYPES = ("expense", "passive_credit_note")
PENDING_DOCUMENT_TYPES = ("agyo", "mail", "browser")
DEFAULT_SCOPES = "received_documents:r entity.suppliers:r"
DEFAULT_API_CONNECT_TIMEOUT_SECONDS = 3.0
DEFAULT_API_READ_TIMEOUT_SECONDS = 6.0
DEFAULT_SYNC_MAX_SECONDS = 18.0
SUPPLIER_DETAILS_SCOPE_WARNING = (
    "Dati anagrafici completi dei fornitori non disponibili: "
    "ricollega Fatture in Cloud autorizzando anche la lettura dei fornitori."
)


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


def _supplier_name(entity, document_data):
    return (
        entity.get("name")
        or " ".join(part for part in [entity.get("first_name"), entity.get("last_name")] if part)
        or document_data.get("supplier_name")
        or document_data.get("supplierName")
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


def _find_or_create_supplier(entity, document_data):
    name = _supplier_name(entity, document_data)
    vat_number = _clean_identifier(entity.get("vat_number"))
    if vat_number.startswith("IT") and len(vat_number) > 11:
        vat_number = vat_number[2:]
    tax_code = _clean_identifier(entity.get("tax_code"))

    qs = Fornitore.objects.all()
    fornitore = None
    if vat_number:
        fornitore = qs.filter(partita_iva__iexact=vat_number).first()
    if fornitore is None and tax_code:
        fornitore = qs.filter(codice_fiscale__iexact=tax_code).first()
    if fornitore is None:
        fornitore = qs.filter(denominazione__iexact=name).first()

    defaults = {
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
    if fornitore is None:
        return Fornitore.objects.create(denominazione=name, attivo=True, **defaults), True, False

    changed = []
    for field_name, value in defaults.items():
        if value and not getattr(fornitore, field_name):
            setattr(fornitore, field_name, value)
            changed.append(field_name)
    if changed:
        changed.append("data_aggiornamento")
        fornitore.save(update_fields=changed)
    return fornitore, False, bool(changed)


def _document_type(document_data):
    fic_type = (
        document_data.get("document_type")
        or document_data.get("documentType")
        or document_data.get("type")
        or ""
    )
    if "credit" in fic_type:
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


def _paid_amount_from_payments(payments):
    paid = Decimal("0.00")
    for payment in payments or []:
        status = (payment.get("status") or payment.get("payment_status") or "").lower()
        amount = _payment_amount(payment)
        if status in {"paid", "payed", "saldata", "saldate", "paid_in_full"} or payment.get("paid_date"):
            paid += amount
    return paid


def _state_from_document(total, payments):
    paid = _paid_amount_from_payments(payments)
    if total > Decimal("0.00") and paid >= total:
        return StatoDocumentoFornitore.PAGATO
    if paid > Decimal("0.00"):
        return StatoDocumentoFornitore.PARZIALMENTE_PAGATO
    return StatoDocumentoFornitore.DA_PAGARE


def _payment_deadlines(document_data):
    payments = _payment_items(document_data)
    total = _document_total(document_data)
    deadlines = []
    for payment in payments:
        due_date = _as_date(
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
        amount = _payment_amount(payment)
        if amount <= Decimal("0.00") and len(payments) == 1:
            amount = total
        if due_date and amount > Decimal("0.00"):
            deadlines.append(
                {
                    "data_scadenza": due_date,
                    "importo_previsto": amount,
                    "importo_pagato": _as_decimal(payment.get("paid_amount") or payment.get("paidAmount")),
                    "data_pagamento": _as_date(
                        payment.get("paid_date") or payment.get("paidDate") or payment.get("data_pagamento")
                    ),
                }
            )

    if deadlines:
        return deadlines

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
        return [
            {
                "data_scadenza": due_date,
                "importo_previsto": total,
                "importo_pagato": Decimal("0.00"),
                "data_pagamento": None,
            }
        ]
    return []


def _document_date(document_data):
    return (
        _as_date(
            document_data.get("date")
            or document_data.get("emission_date")
            or document_data.get("emssion_date")
            or document_data.get("document_date")
            or document_data.get("documentDate")
        )
        or timezone.localdate()
    )


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


def _sync_document_deadlines(documento, deadlines):
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


def _update_document_fields(documento, document_data, fornitore, pending):
    e_invoice = _as_dict(document_data.get("e_invoice"))
    amounts = _as_dict(document_data.get("amounts"))
    doc_date = _document_date(document_data)
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
    documento.tipo_documento = _document_type(document_data)
    documento.numero_documento = _invoice_number(document_data)
    documento.data_documento = doc_date
    documento.data_ricezione = _as_date(
        document_data.get("received_at")
        or document_data.get("created_at")
        or e_invoice.get("received_at")
    )
    documento.anno_competenza = doc_date.year
    documento.mese_competenza = doc_date.month
    documento.descrizione = (document_data.get("description") or document_data.get("subject") or "")[:255]
    documento.imponibile = amount_net
    documento.iva = amount_vat
    documento.totale = amount_gross
    documento.aliquota_iva = Decimal("0.00")
    if amount_net:
        documento.aliquota_iva = (amount_vat * Decimal("100") / amount_net).quantize(Decimal("0.01"))
    documento.stato = _state_from_document(amount_gross, _payment_items(document_data))
    documento.origine = OrigineDocumentoFornitore.FATTURE_IN_CLOUD
    documento.external_source = FIC_SOURCE
    documento.external_id = str(document_data.get("id") or "")
    documento.external_type = "pending" if pending else (document_data.get("type") or "")
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
def importa_documento_fatture_in_cloud(connessione, document_data, *, pending=False, utente=None):
    if not document_data or not document_data.get("id"):
        raise ValidationError("Documento Fatture in Cloud privo di ID.")

    entity = _enrich_supplier_entity_from_document(_entity_from_document(document_data), document_data)
    fornitore, fornitore_created, fornitore_updated = _find_or_create_supplier(entity, document_data)
    external_id = str(document_data.get("id"))
    documento = DocumentoFornitore.objects.filter(external_source=FIC_SOURCE, external_id=external_id).first()
    created = False
    if documento is None:
        documento = DocumentoFornitore.objects.filter(
            fornitore=fornitore,
            tipo_documento=_document_type(document_data),
            numero_documento=_invoice_number(document_data),
            data_documento=_document_date(document_data),
        ).first()
    if documento is None:
        documento = DocumentoFornitore()
        created = True

    _update_document_fields(documento, document_data, fornitore, pending)
    documento.save()

    scadenze_create = _sync_document_deadlines(documento, _payment_deadlines(document_data))

    aggiorna_stato_documento_da_scadenze(documento)
    _notifica, notifica_created = crea_notifica_finanziaria(
        titolo="Nuova fattura fornitore ricevuta" if created else "Fattura fornitore aggiornata",
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

    def list_received_documents(self, doc_type, *, page=1, per_page=50):
        params = {
            "type": doc_type,
            "page": page,
            "per_page": per_page,
            "sort": "-date,-id",
            "fieldset": "detailed",
        }
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

    def list_pending_received_documents(self, doc_type, *, page=1, per_page=50):
        params = {
            "type": doc_type,
            "page": page,
            "per_page": per_page,
            "sort": "-date,-id",
            "fieldset": "detailed",
        }
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
        return _document_with_supplier_detail(client, summary, supplier_context)
    detail = client.get_pending_received_document(document_id) if pending else client.get_received_document(document_id)
    if not isinstance(detail, dict) or not detail:
        return _document_with_supplier_detail(client, summary, supplier_context)
    return _document_with_supplier_detail(client, {**summary, **detail}, supplier_context)


def _check_sync_budget(start, max_seconds):
    if max_seconds and time.monotonic() - start >= max_seconds:
        raise FattureInCloudSyncBudgetExceeded(
            "Tempo massimo della sincronizzazione raggiunto prima del completamento. "
            "Alcuni documenti potrebbero essere gia stati importati: ripeti la sincronizzazione per continuare."
        )


def _add_import_result_to_stats(stats, result):
    stats["creati"] += 1 if result["created"] else 0
    stats["aggiornati"] += 1 if result["updated"] else 0
    stats["scadenze"] += result["scadenze_create"]
    stats["notifiche"] += 1 if result["notifica_created"] else 0
    stats["fornitori_creati"] += 1 if result["fornitore_created"] else 0
    stats["fornitori_aggiornati"] += 1 if result["fornitore_updated"] else 0


def _sync_summary_label(doc_type, pending):
    prefix = "Da registrare" if pending else "Registrati"
    return f"{prefix} {doc_type}"


def sincronizza_fatture_in_cloud(connessione, *, utente=None, max_seconds=None):
    start = time.monotonic()
    if max_seconds is None:
        max_seconds = _sync_max_seconds()
    stats = {
        "creati": 0,
        "aggiornati": 0,
        "scadenze": 0,
        "notifiche": 0,
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
                    for summary in _iter_paginated(lambda page: client.list_received_documents(doc_type, page=page)):
                        _check_sync_budget(start, max_seconds)
                        try:
                            document = _document_detail_from_summary(
                                client,
                                summary,
                                pending=False,
                                supplier_context=supplier_context,
                            )
                            result = importa_documento_fatture_in_cloud(
                                connessione,
                                document,
                                pending=False,
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

        if connessione.sincronizza_documenti_da_registrare:
            for doc_type in PENDING_DOCUMENT_TYPES:
                label = _sync_summary_label(doc_type, pending=True)
                try:
                    _check_sync_budget(start, max_seconds)
                    documents = _iter_paginated(lambda page: client.list_pending_received_documents(doc_type, page=page))
                    for summary in documents:
                        _check_sync_budget(start, max_seconds)
                        try:
                            document = _document_detail_from_summary(
                                client,
                                summary,
                                pending=True,
                                supplier_context=supplier_context,
                            )
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
                f"Fornitori: {stats['fornitori_creati']} creati, "
                f"{stats['fornitori_aggiornati']} aggiornati."
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
    document = _document_with_supplier_detail(client, document, supplier_context)
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
