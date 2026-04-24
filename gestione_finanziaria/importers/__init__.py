"""
Importatori di estratti conto per il modulo Gestione finanziaria.

Contiene:
- ``base``: tipi comuni (``ParsedMovimento``, ``RisultatoImport``) e interfaccia ``BaseParser``;
- ``camt053``: parser ISO 20022 CAMT.053 (XML);
- ``csv_importer``: parser CSV con mapping colonne configurabile;
- ``service``: orchestratore che persiste i movimenti e gestisce deduplica, regole e log.
"""

from .base import BaseParser, ParsedMovimento, RisultatoImport  # noqa: F401
from .camt053 import (  # noqa: F401
    Camt053Parser,
    SaldoEstrattoCamt,
    estrai_iban_da_camt053,
    estrai_saldo_da_camt053,
)
from .csv_importer import CsvImporter, CsvImporterConfig  # noqa: F401
