from __future__ import annotations

from dataclasses import dataclass

from django.apps import apps
from django.core.exceptions import FieldDoesNotExist
from django.db import models


@dataclass(frozen=True)
class ActiveToggleConfig:
    model_label: str
    field_name: str
    module_name: str
    active_label: str = ""
    inactive_label: str = ""
    reload_on_success: bool = False

    @property
    def model_label_lower(self):
        return self.model_label.lower()


ACTIVE_TOGGLE_REGISTRY = {
    # Anagrafica
    "anagrafica.regione": ActiveToggleConfig("anagrafica.Regione", "attiva", "anagrafica"),
    "anagrafica.provincia": ActiveToggleConfig("anagrafica.Provincia", "attiva", "anagrafica"),
    "anagrafica.citta": ActiveToggleConfig("anagrafica.Citta", "attiva", "anagrafica"),
    "anagrafica.nazione": ActiveToggleConfig("anagrafica.Nazione", "attiva", "anagrafica"),
    "anagrafica.cap": ActiveToggleConfig("anagrafica.CAP", "attivo", "anagrafica"),
    "anagrafica.statorelazionefamiglia": ActiveToggleConfig(
        "anagrafica.StatoRelazioneFamiglia",
        "attivo",
        "anagrafica",
    ),
    "anagrafica.famiglia": ActiveToggleConfig("anagrafica.Famiglia", "attiva", "anagrafica"),
    "anagrafica.familiare": ActiveToggleConfig("anagrafica.Familiare", "attivo", "anagrafica"),
    "anagrafica.studente": ActiveToggleConfig("anagrafica.Studente", "attivo", "anagrafica"),
    "anagrafica.tipodocumento": ActiveToggleConfig("anagrafica.TipoDocumento", "attivo", "anagrafica"),
    # Scuola
    "scuola.annoscolastico": ActiveToggleConfig("scuola.AnnoScolastico", "attivo", "sistema"),
    "scuola.classe": ActiveToggleConfig("scuola.Classe", "attiva", "sistema"),
    "scuola.gruppoclasse": ActiveToggleConfig("scuola.GruppoClasse", "attivo", "sistema"),
    # Calendario
    "calendario.categoriacalendario": ActiveToggleConfig("calendario.CategoriaCalendario", "attiva", "calendario"),
    "calendario.eventocalendario": ActiveToggleConfig("calendario.EventoCalendario", "attivo", "calendario"),
    # Economia e fondo
    "economia.metodopagamento": ActiveToggleConfig("economia.MetodoPagamento", "attivo", "economia"),
    "economia.tipomovimentocredito": ActiveToggleConfig("economia.TipoMovimentoCredito", "attivo", "economia"),
    "economia.statoiscrizione": ActiveToggleConfig("economia.StatoIscrizione", "attiva", "economia"),
    "economia.condizioneiscrizione": ActiveToggleConfig("economia.CondizioneIscrizione", "attiva", "economia"),
    "economia.tariffacondizioneiscrizione": ActiveToggleConfig(
        "economia.TariffaCondizioneIscrizione",
        "attiva",
        "economia",
    ),
    "economia.agevolazione": ActiveToggleConfig("economia.Agevolazione", "attiva", "economia"),
    "economia.iscrizione": ActiveToggleConfig("economia.Iscrizione", "attiva", "economia"),
    "fondo_accantonamento.pianoaccantonamento": ActiveToggleConfig(
        "fondo_accantonamento.PianoAccantonamento",
        "attivo",
        "economia",
    ),
    "fondo_accantonamento.regolascontoagevolazione": ActiveToggleConfig(
        "fondo_accantonamento.RegolaScontoAgevolazione",
        "attiva",
        "economia",
    ),
    # Servizi extra
    "servizi_extra.servizioextra": ActiveToggleConfig("servizi_extra.ServizioExtra", "attiva", "servizi_extra"),
    "servizi_extra.tariffaservizioextra": ActiveToggleConfig(
        "servizi_extra.TariffaServizioExtra",
        "attiva",
        "servizi_extra",
    ),
    "servizi_extra.iscrizioneservizioextra": ActiveToggleConfig(
        "servizi_extra.IscrizioneServizioExtra",
        "attiva",
        "servizi_extra",
    ),
    # Gestione finanziaria
    "gestione_finanziaria.categoriafinanziaria": ActiveToggleConfig(
        "gestione_finanziaria.CategoriaFinanziaria",
        "attiva",
        "gestione_finanziaria",
    ),
    "gestione_finanziaria.fornitore": ActiveToggleConfig(
        "gestione_finanziaria.Fornitore",
        "attivo",
        "gestione_finanziaria",
    ),
    "gestione_finanziaria.vocebudgetricorrente": ActiveToggleConfig(
        "gestione_finanziaria.VoceBudgetRicorrente",
        "attiva",
        "gestione_finanziaria",
        reload_on_success=True,
    ),
    "gestione_finanziaria.providerbancario": ActiveToggleConfig(
        "gestione_finanziaria.ProviderBancario",
        "attivo",
        "gestione_finanziaria",
    ),
    "gestione_finanziaria.contobancario": ActiveToggleConfig(
        "gestione_finanziaria.ContoBancario",
        "attivo",
        "gestione_finanziaria",
    ),
    "gestione_finanziaria.regolacategorizzazione": ActiveToggleConfig(
        "gestione_finanziaria.RegolaCategorizzazione",
        "attiva",
        "gestione_finanziaria",
    ),
    "gestione_finanziaria.pianificazionesincronizzazione": ActiveToggleConfig(
        "gestione_finanziaria.PianificazioneSincronizzazione",
        "attivo",
        "gestione_finanziaria",
    ),
    "gestione_finanziaria.fattureincloudconnessione": ActiveToggleConfig(
        "gestione_finanziaria.FattureInCloudConnessione",
        "attiva",
        "gestione_finanziaria",
    ),
    # Dipendenti e collaboratori
    "gestione_amministrativa.tipocontrattodipendente": ActiveToggleConfig(
        "gestione_amministrativa.TipoContrattoDipendente",
        "attivo",
        "gestione_amministrativa",
    ),
    "gestione_amministrativa.contrattodipendente": ActiveToggleConfig(
        "gestione_amministrativa.ContrattoDipendente",
        "attivo",
        "gestione_amministrativa",
    ),
    "gestione_amministrativa.simulazionecostodipendente": ActiveToggleConfig(
        "gestione_amministrativa.SimulazioneCostoDipendente",
        "attiva",
        "gestione_amministrativa",
    ),
    "gestione_amministrativa.parametrocalcolostipendio": ActiveToggleConfig(
        "gestione_amministrativa.ParametroCalcoloStipendio",
        "attivo",
        "gestione_amministrativa",
    ),
    # Sistema
    "sistema.sistemaruolopermessi": ActiveToggleConfig(
        "sistema.SistemaRuoloPermessi",
        "attivo",
        "sistema",
    ),
}


def get_active_toggle_config(model_label, field_name=None):
    normalized_label = (model_label or "").lower()
    config = ACTIVE_TOGGLE_REGISTRY.get(normalized_label)
    if not config:
        return None
    if field_name and field_name != config.field_name:
        return None
    return config


def get_active_toggle_config_for_object(obj, field_name=None):
    if obj is None:
        return None
    return get_active_toggle_config(obj._meta.label_lower, field_name=field_name)


def get_active_toggle_model(config):
    try:
        return apps.get_model(config.model_label)
    except (LookupError, ValueError):
        return None


def active_toggle_labels(field_name, active_label="", inactive_label=""):
    if active_label and inactive_label:
        return active_label, inactive_label
    if field_name == "attiva":
        return active_label or "Attiva", inactive_label or "Non attiva"
    return active_label or "Attivo", inactive_label or "Non attivo"


def validate_active_toggle_config(config):
    model_cls = get_active_toggle_model(config)
    if model_cls is None:
        return False
    try:
        field = model_cls._meta.get_field(config.field_name)
    except FieldDoesNotExist:
        return False
    return isinstance(field, models.BooleanField)
