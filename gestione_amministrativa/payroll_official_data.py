import csv
import io
from datetime import date
from decimal import Decimal, InvalidOperation

import requests
from django.db import transaction
from django.utils import timezone

from .models import CategoriaDatoPayrollUfficiale, DatoPayrollUfficiale


MEF_ADDIZIONALE_COMUNALE_URL = (
    "https://www1.finanze.gov.it/finanze2/dipartimentopolitichefiscali/"
    "fiscalitalocale/nuova_addcomirpef/download/download.php?anno={anno}"
)
MEF_ADDIZIONALE_REGIONALE_URL = (
    "https://www1.finanze.gov.it/finanze2/dipartimentopolitichefiscali/"
    "fiscalitalocale/addregirpef/download/download.php?anno={anno}&tipo=reg"
)


OFFICIAL_SOURCE_CATALOG = [
    {
        "codice": "INPS_ALIQUOTE_CONTRIBUTIVE",
        "nome": "Aliquote contributive INPS",
        "ente": "INPS",
        "fonte_url": "https://www.inps.it/it/it/inps-comunica/diritti-e-obblighi-in-materia-di-sicurezza-sociale-nell-unione-e/per-le-imprese/aliquote-contributive.html",
        "descrizione": "Pagina ufficiale INPS con aliquote e indicazioni contributive per imprese e lavoratori.",
    },
    {
        "codice": "INPS_MINIMALI_MASSIMALI",
        "nome": "Minimali e massimali contributivi INPS",
        "ente": "INPS",
        "fonte_url": "https://www.inps.it/it/it/inps-comunica.html",
        "descrizione": "Comunicazioni e circolari INPS per minimali, massimali e valori contributivi annuali.",
    },
    {
        "codice": "INAIL_AUTOLIQUIDAZIONE",
        "nome": "Autoliquidazione e premi INAIL",
        "ente": "INAIL",
        "fonte_url": "https://www.inail.it/portale/it/attivita/prestazioni/premio-assicurativo/autoliquidazione.html",
        "descrizione": "Pagina ufficiale INAIL per autoliquidazione, premio assicurativo e istruzioni operative.",
    },
    {
        "codice": "MEF_ADDIZIONALI_COMUNALI",
        "nome": "Addizionali comunali IRPEF",
        "ente": "Dipartimento Finanze",
        "fonte_url": "https://www1.finanze.gov.it/finanze2/dipartimentopolitichefiscali/fiscalitalocale/nuova_addcomirpef/download/tabella.htm",
        "descrizione": "Archivio ufficiale delle aliquote comunali IRPEF, con download per anno.",
    },
    {
        "codice": "MEF_ADDIZIONALI_REGIONALI",
        "nome": "Addizionali regionali IRPEF",
        "ente": "Dipartimento Finanze",
        "fonte_url": "https://www1.finanze.gov.it/finanze2/dipartimentopolitichefiscali/fiscalitalocale/addregirpef/download/tabella.htm",
        "descrizione": "Archivio ufficiale delle aliquote regionali IRPEF, con download per anno.",
    },
    {
        "codice": "CNEL_CCNL",
        "nome": "Archivio CNEL dei contratti collettivi",
        "ente": "CNEL / Ministero del Lavoro",
        "fonte_url": "https://www.lavoro.gov.it/temi-e-priorita/rapporti-di-lavoro-e-relazioni-industriali/focus-on/norme-contratti-collettivi/pagine/default",
        "descrizione": "Archivio ufficiale dei contratti collettivi nazionali depositati.",
    },
]


def seed_official_source_catalog():
    created = 0
    updated = 0
    now = timezone.now()
    for source in OFFICIAL_SOURCE_CATALOG:
        _, was_created = DatoPayrollUfficiale.objects.update_or_create(
            categoria=CategoriaDatoPayrollUfficiale.FONTE,
            codice=source["codice"],
            anno=None,
            valido_dal=None,
            defaults={
                "nome": source["nome"],
                "descrizione": source["descrizione"],
                "ente": source["ente"],
                "fonte_url": source["fonte_url"],
                "valore_testo": "Fonte ufficiale",
                "attivo": True,
                "metadata": {"tipo_record": "catalogo_fonte", "aggiornato_da": "sistema", "timestamp": now.isoformat()},
            },
        )
        if was_created:
            created += 1
        else:
            updated += 1
    return {"created": created, "updated": updated}


def _response_text(response):
    response.raise_for_status()
    content_type = response.headers.get("content-type", "")
    encoding = response.encoding or ("utf-8" if "utf-8" in content_type.lower() else "latin-1")
    return response.content.decode(encoding, errors="replace")


def _parse_decimal(value):
    value = (value or "").strip().replace("%", "").replace(" ", "")
    if not value:
        return None

    value = value.replace(".", "").replace(",", ".")
    try:
        return Decimal(value)
    except InvalidOperation:
        return None


def _normalizza_chiave(value):
    return (value or "").strip().upper().replace(" ", "_").replace("-", "_")


def _row_get(row, candidates):
    normalized = {_normalizza_chiave(key): value for key, value in row.items()}
    for candidate in candidates:
        value = normalized.get(_normalizza_chiave(candidate))
        if value not in (None, ""):
            return value
    return ""


def _best_percentage(row):
    preferred_keys = [
        "ALIQUOTA",
        "ALIQUOTA_1",
        "ALIQUOTA1",
        "ALIQUOTA UNICA",
        "ALIQUOTA ORDINARIA",
        "ALIQUOTA COMUNALE",
        "ALIQUOTA REGIONALE",
    ]
    for key in preferred_keys:
        value = _parse_decimal(_row_get(row, [key]))
        if value is not None:
            return value

    for key, raw_value in row.items():
        if "ALIQUOTA" in _normalizza_chiave(key):
            value = _parse_decimal(raw_value)
            if value is not None:
                return value
    return None


def _reader_from_text(text):
    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=";,|\t")
        return csv.DictReader(io.StringIO(text), dialect=dialect)
    except csv.Error:
        return csv.DictReader(io.StringIO(text), delimiter=";")


def _import_mef_csv(text, *, categoria, anno, fonte_url):
    rows = list(_reader_from_text(text))
    created = 0
    updated = 0
    skipped = 0
    ente = "Dipartimento Finanze"
    defaults_common = {
        "anno": anno,
        "ente": ente,
        "fonte_url": fonte_url,
        "attivo": True,
    }

    with transaction.atomic():
        for index, row in enumerate(rows, start=1):
            codice = _row_get(
                row,
                [
                    "CODICE",
                    "CODICE CATASTALE",
                    "CODICE BELFIORE",
                    "CODICE COMUNE",
                    "CODICE REGIONE",
                    "CODICE_REGIONE",
                ],
            )
            nome = _row_get(row, ["COMUNE", "DENOMINAZIONE", "REGIONE", "NOME", "ENTE"])
            aliquota = _best_percentage(row)
            if not codice or not nome:
                skipped += 1
                continue

            codice_record = f"{codice.strip()}:{index}" if not aliquota else codice.strip()
            metadata = {
                "record_origine": {key: value for key, value in row.items() if key},
                "importato_da": "MEF CSV",
            }
            _, was_created = DatoPayrollUfficiale.objects.update_or_create(
                categoria=categoria,
                codice=codice_record[:80],
                anno=anno,
                valido_dal=date(anno, 1, 1),
                defaults={
                    **defaults_common,
                    "nome": nome.strip()[:180],
                    "descrizione": "Dato importato automaticamente dal download ufficiale del Dipartimento Finanze.",
                    "valido_al": date(anno, 12, 31),
                    "valore_percentuale": aliquota,
                    "valore_testo": "" if aliquota is not None else "Dato presente nel file ufficiale",
                    "metadata": metadata,
                },
            )
            if was_created:
                created += 1
            else:
                updated += 1

    return {"created": created, "updated": updated, "skipped": skipped}


def sync_mef_addizionali(*, anno=None, timeout=30):
    anno = anno or timezone.localdate().year
    results = {}
    sources = [
        ("comunali", CategoriaDatoPayrollUfficiale.ADDIZIONALE_COMUNALE, MEF_ADDIZIONALE_COMUNALE_URL.format(anno=anno)),
        ("regionali", CategoriaDatoPayrollUfficiale.ADDIZIONALE_REGIONALE, MEF_ADDIZIONALE_REGIONALE_URL.format(anno=anno)),
    ]
    for key, categoria, url in sources:
        response = requests.get(url, timeout=timeout)
        text = _response_text(response)
        results[key] = _import_mef_csv(text, categoria=categoria, anno=anno, fonte_url=url)
    return results


def sync_payroll_official_data(*, anno=None, include_downloads=True, timeout=30):
    stats = {"catalogo_fonti": seed_official_source_catalog()}
    if include_downloads:
        stats["mef_addizionali"] = sync_mef_addizionali(anno=anno, timeout=timeout)
    return stats
