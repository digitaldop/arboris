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
PENDING_DOCUMENT_TYPES = ("expense", "passive_credit_note")
DEFAULT_SCOPES = "received_documents:r"


class FattureInCloudError(Exception):
    pass


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


def _entity_from_document(document_data):
    return (
        document_data.get("entity")
        or document_data.get("supplier")
        or document_data.get("e_invoice", {}).get("supplier")
        or {}
    )


def _supplier_name(entity, document_data):
    return (
        entity.get("name")
        or " ".join(part for part in [entity.get("first_name"), entity.get("last_name")] if part)
        or document_data.get("description")
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
        "codice_sdi": (entity.get("ei_code") or "")[:7],
        "iban": (entity.get("bank_iban") or "")[:34],
        "banca": (entity.get("bank_name") or "")[:160],
        "attivo": True,
    }
    if fornitore is None:
        return Fornitore.objects.create(denominazione=name, **defaults), True

    changed = []
    for field_name, value in defaults.items():
        if value and not getattr(fornitore, field_name):
            setattr(fornitore, field_name, value)
            changed.append(field_name)
    if changed:
        changed.append("data_aggiornamento")
        fornitore.save(update_fields=changed)
    return fornitore, False


def _document_type(document_data):
    fic_type = document_data.get("type") or ""
    if "credit" in fic_type:
        return TipoDocumentoFornitore.NOTA_CREDITO
    return TipoDocumentoFornitore.FATTURA


def _invoice_number(document_data):
    return (
        document_data.get("invoice_number")
        or document_data.get("number")
        or document_data.get("e_invoice", {}).get("number")
        or str(document_data.get("id") or "")
    )[:80]


def _paid_amount_from_payments(payments):
    paid = Decimal("0.00")
    for payment in payments or []:
        status = (payment.get("status") or payment.get("payment_status") or "").lower()
        amount = _as_decimal(payment.get("amount") or payment.get("amount_gross"))
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
    payments = document_data.get("payments_list") or document_data.get("payments") or []
    deadlines = []
    for payment in payments:
        due_date = _as_date(payment.get("due_date") or payment.get("date") or payment.get("expiration_date"))
        amount = _as_decimal(payment.get("amount") or payment.get("amount_gross"))
        if due_date and amount > Decimal("0.00"):
            deadlines.append(
                {
                    "data_scadenza": due_date,
                    "importo_previsto": amount,
                    "importo_pagato": _as_decimal(payment.get("paid_amount")),
                    "data_pagamento": _as_date(payment.get("paid_date")),
                }
            )

    if deadlines:
        return deadlines

    total = _as_decimal(document_data.get("amount_gross") or document_data.get("total"))
    due_date = _as_date(document_data.get("next_due_date") or document_data.get("date")) or timezone.localdate()
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


def _update_document_fields(documento, document_data, fornitore, pending):
    doc_date = _as_date(document_data.get("date")) or timezone.localdate()
    amount_net = _as_decimal(document_data.get("amount_net"))
    amount_vat = _as_decimal(document_data.get("amount_vat"))
    amount_gross = _as_decimal(document_data.get("amount_gross") or document_data.get("total"))
    if amount_gross == Decimal("0.00") and amount_net:
        amount_gross = amount_net + amount_vat

    documento.fornitore = fornitore
    documento.tipo_documento = _document_type(document_data)
    documento.numero_documento = _invoice_number(document_data)
    documento.data_documento = doc_date
    documento.data_ricezione = _as_date(
        document_data.get("received_at")
        or document_data.get("created_at")
        or document_data.get("e_invoice", {}).get("received_at")
    )
    documento.anno_competenza = doc_date.year
    documento.mese_competenza = doc_date.month
    documento.descrizione = (document_data.get("description") or "")[:255]
    documento.imponibile = amount_net
    documento.iva = amount_vat
    documento.totale = amount_gross
    documento.aliquota_iva = Decimal("0.00")
    if amount_net:
        documento.aliquota_iva = (amount_vat * Decimal("100") / amount_net).quantize(Decimal("0.01"))
    documento.stato = _state_from_document(amount_gross, document_data.get("payments_list") or [])
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

    entity = _entity_from_document(document_data)
    fornitore, _fornitore_created = _find_or_create_supplier(entity, document_data)
    external_id = str(document_data.get("id"))
    documento = DocumentoFornitore.objects.filter(external_source=FIC_SOURCE, external_id=external_id).first()
    created = False
    if documento is None:
        documento = DocumentoFornitore.objects.filter(
            fornitore=fornitore,
            tipo_documento=_document_type(document_data),
            numero_documento=_invoice_number(document_data),
            data_documento=_as_date(document_data.get("date")) or timezone.localdate(),
        ).first()
    if documento is None:
        documento = DocumentoFornitore()
        created = True

    _update_document_fields(documento, document_data, fornitore, pending)
    documento.save()

    scadenze_create = 0
    if created or not documento.scadenze.exists():
        for deadline in _payment_deadlines(document_data):
            ScadenzaPagamentoFornitore.objects.create(
                documento=documento,
                data_scadenza=deadline["data_scadenza"],
                importo_previsto=deadline["importo_previsto"],
                importo_pagato=deadline["importo_pagato"],
                data_pagamento=deadline["data_pagamento"],
            )
            scadenze_create += 1

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
                timeout=30,
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
            response = requests.post(TOKEN_URL, json=payload, timeout=30)
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
            response = requests.post(TOKEN_URL, json=payload, timeout=30)
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


def sincronizza_fatture_in_cloud(connessione, *, utente=None):
    start = time.monotonic()
    stats = {
        "creati": 0,
        "aggiornati": 0,
        "scadenze": 0,
        "notifiche": 0,
        "messaggi": [],
    }
    esito = EsitoSincronizzazione.OK
    client = FattureInCloudClient(connessione)

    try:
        if not connessione.company_id:
            raise FattureInCloudError("Company ID non configurato.")

        if connessione.sincronizza_documenti_registrati:
            for doc_type in RECEIVED_DOCUMENT_TYPES:
                for document in _iter_paginated(lambda page: client.list_received_documents(doc_type, page=page)):
                    result = importa_documento_fatture_in_cloud(connessione, document, pending=False, utente=utente)
                    stats["creati"] += 1 if result["created"] else 0
                    stats["aggiornati"] += 1 if result["updated"] else 0
                    stats["scadenze"] += result["scadenze_create"]
                    stats["notifiche"] += 1 if result["notifica_created"] else 0

        if connessione.sincronizza_documenti_da_registrare:
            for doc_type in PENDING_DOCUMENT_TYPES:
                try:
                    documents = _iter_paginated(lambda page: client.list_pending_received_documents(doc_type, page=page))
                    for document in documents:
                        result = importa_documento_fatture_in_cloud(connessione, document, pending=True, utente=utente)
                        stats["creati"] += 1 if result["created"] else 0
                        stats["aggiornati"] += 1 if result["updated"] else 0
                        stats["scadenze"] += result["scadenze_create"]
                        stats["notifiche"] += 1 if result["notifica_created"] else 0
                except FattureInCloudError as exc:
                    esito = EsitoSincronizzazione.PARZIALE
                    stats["messaggi"].append(f"Pending {doc_type}: {exc}")

        if not stats["messaggi"]:
            stats["messaggi"].append(
                f"Importati {stats['creati']} nuovi documenti, aggiornati {stats['aggiornati']} documenti."
            )
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
    if esito == EsitoSincronizzazione.ERRORE:
        raise FattureInCloudError(stats["messaggi"][-1])
    return stats


def importa_documento_da_webhook(connessione, notification_type, document_id, *, utente=None):
    client = FattureInCloudClient(connessione)
    pending = notification_type.endswith("received_documents.e_invoices.receive")
    if pending:
        document = client.get_pending_received_document(document_id)
    else:
        document = client.get_received_document(document_id)
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
