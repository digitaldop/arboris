"""Catalogue of main pages and all their detail/action URLs.

URL names are explicit: new endpoints must be assigned here and covered by the
catalogue completeness test. Sidebar keys are shared with sidebar_menu.py.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class PermissionPage:
    key: str
    module: str
    label: str
    views: tuple[str, ...]


PERMISSION_PAGES = (
    PermissionPage('anagrafica_studenti', 'anagrafica', 'Studenti', (
        'lista_studenti',
        'crea_studente',
        'modifica_studente',
        'stampa_studente_opzioni',
        'stampa_studente',
        'elimina_studente',
    )),
    PermissionPage('anagrafica_familiari', 'anagrafica', 'Familiari', (
        'crea_relazione_familiare',
        'modifica_relazione_familiare',
        'elimina_relazione_familiare',
        'lista_familiari',
        'crea_familiare',
        'modifica_familiare',
        'elimina_familiare',
    )),
    PermissionPage('anagrafica_famiglie', 'anagrafica', 'Famiglie', (
        'lista_famiglie',
        'crea_famiglia',
        'modifica_famiglia_logica',
        'stampa_famiglia_logica',
    )),
    PermissionPage('anagrafica_ricerche', 'anagrafica', 'Ricerche', (
        'ricerche_anagrafica',
    )),
    PermissionPage('anagrafica_indirizzi', 'anagrafica', 'Indirizzi e contatti', (
        'lista_indirizzi',
        'crea_indirizzo',
        'modifica_indirizzo',
        'elimina_indirizzo',
        'crea_label_contatto',
        'modifica_label_contatto',
        'elimina_label_contatto',
        'ajax_cerca_citta',
        'ajax_indirizzi_duplicati',
    )),
    PermissionPage('anagrafica_documenti', 'anagrafica', 'Documenti', (
        'crea_tipo_documento',
        'modifica_tipo_documento',
        'elimina_tipo_documento',
        'apri_documento',
        'elimina_documento',
    )),
    PermissionPage('anagrafica_osservazioni', 'anagrafica', 'Osservazioni studenti', (
        'osservazioni_studente',
        'modifica_osservazione_studente',
        'elimina_osservazione_studente',
    )),
    PermissionPage('anagrafica_comunicazioni_famiglie', 'anagrafica', 'Comunicazioni alle famiglie', (
        'comunicazioni_famiglie',
        'storico_comunicazioni_famiglie',
        'dettaglio_comunicazione_famiglia',
    )),
    PermissionPage('famiglie_interessate_contatti', 'famiglie_interessate', 'Contatti e follow-up', (
        'lista_famiglie_interessate',
        'crea_famiglia_interessata',
        'modifica_famiglia_interessata',
        'crea_attivita_famiglia_interessata',
        'modifica_attivita_famiglia_interessata',
    )),
    PermissionPage('economia_panoramica_rette', 'economia', 'Matrice rette / Panoramica rette', (
        'verifica_situazione_rette',
    )),
    PermissionPage('economia_iscrizioni', 'economia', 'Iscrizioni', (
        'lista_iscrizioni',
        'crea_iscrizione',
        'modifica_iscrizione',
        'ricalcola_rate_iscrizione',
        'rimodula_rate_iscrizione',
        'riconcilia_pagamenti_iscrizione',
        'ritiro_anticipato_iscrizione',
        'elimina_iscrizione',
    )),
    PermissionPage('economia_stati_iscrizione', 'economia', 'Stati iscrizione', (
        'lista_stati_iscrizione',
        'crea_stato_iscrizione',
        'modifica_stato_iscrizione',
        'elimina_stato_iscrizione',
    )),
    PermissionPage('economia_rate_iscrizione', 'economia', 'Rate iscrizione', (
        'ricalcola_rate_anno_scolastico',
        'riconcilia_pagamenti_rate_anno_scolastico',
        'lista_rate_iscrizione',
        'modifica_rata_iscrizione',
        'pagamento_rapido_rata_iscrizione',
        'riconcilia_rata_iscrizione',
        'annulla_riconciliazione_rata_iscrizione',
    )),
    PermissionPage('economia_condizioni', 'economia', 'Condizioni economiche', (
        'lista_condizioni_iscrizione',
        'crea_condizione_iscrizione',
        'modifica_condizione_iscrizione',
        'elimina_condizione_iscrizione',
    )),
    PermissionPage('economia_tariffe', 'economia', 'Tariffe', (
        'lista_tariffe_condizione_iscrizione',
        'crea_tariffa_condizione_iscrizione',
        'modifica_tariffa_condizione_iscrizione',
        'elimina_tariffa_condizione_iscrizione',
    )),
    PermissionPage('economia_tariffe_scambio', 'economia', 'Tariffe scambio retta', (
        'lista_tariffe_scambio_retta',
        'crea_tariffa_scambio_retta',
        'modifica_tariffa_scambio_retta',
        'elimina_tariffa_scambio_retta',
    )),
    PermissionPage('economia_agevolazioni', 'economia', 'Agevolazioni', (
        'lista_agevolazioni',
        'crea_agevolazione',
        'modifica_agevolazione',
        'elimina_agevolazione',
    )),
    PermissionPage('economia_scambi_retta', 'economia', 'Scambi retta', (
        'lista_scambi_retta',
        'crea_scambio_retta',
        'modifica_scambio_retta',
        'elimina_scambio_retta',
        'contabilizza_scambio_retta',
        'crea_prestazione_scambio_retta',
        'modifica_prestazione_scambio_retta',
        'elimina_prestazione_scambio_retta',
    )),
    PermissionPage('economia_fondi_accantonamento', 'economia', 'Fondi di accantonamento', (
        'fondo_piano_lista',
        'fondo_piano_nuovo',
        'fondo_piano_dettaglio',
        'fondo_piano_modifica',
        'fondo_piano_elimina',
        'fondo_piano_versamento',
        'fondo_piano_prelievo',
        'fondo_piano_genera_scadenze',
        'fondo_scadenza_soddisfa',
    )),
    PermissionPage('economia_metodi_pagamento', 'economia', 'Metodi di pagamento', (
        'crea_metodo_pagamento',
        'modifica_metodo_pagamento',
        'elimina_metodo_pagamento',
    )),
    PermissionPage('gestione_finanziaria_dashboard', 'gestione_finanziaria', 'Dashboard economica', (
        'dashboard_gestione_finanziaria',
    )),
    PermissionPage('gestione_finanziaria_movimenti_bancari', 'gestione_finanziaria', 'Movimenti bancari', (
        'lista_movimenti_finanziari',
        'crea_movimento_manuale',
        'pulizia_movimenti_finanziari',
        'pulizia_duplicati_movimenti_finanziari',
        'elimina_movimenti_finanziari_multipla',
        'dettaglio_movimento_finanziario',
        'modifica_movimento_finanziario',
        'aggiorna_categoria_movimento',
        'elimina_movimento_finanziario',
        'annulla_riconciliazione_movimento',
    )),
    PermissionPage('gestione_finanziaria_fatture_fornitori_dashboard', 'gestione_finanziaria', 'Fatture e scadenze', (
        'fatture_scadenze_fornitori',
        'scarica_fatture_insolute_fornitori_excel',
    )),
    PermissionPage('gestione_finanziaria_spese_mensili', 'gestione_finanziaria', 'Spese mensili', (
        'spese_mensili_dashboard',
        'crea_spesa_operativa',
        'modifica_spesa_operativa',
        'aggiorna_categoria_spesa_operativa',
        'aggiorna_categoria_documento_fornitore',
        'aggiorna_categoria_busta_paga',
        'crea_piano_rateale_spesa',
    )),
    PermissionPage('anagrafica_fornitori', 'gestione_finanziaria', 'Rubrica fornitori', (
        'lista_fornitori',
        'crea_fornitore',
        'modifica_fornitore',
        'elimina_fornitore',
    )),
    PermissionPage('gestione_finanziaria_categorie_spesa', 'gestione_finanziaria', 'Categorie di spesa', (
        'lista_categorie_spesa',
        'crea_categoria_spesa',
        'modifica_categoria_spesa',
        'elimina_categoria_spesa',
    )),
    PermissionPage('gestione_finanziaria_categorie_movimenti', 'gestione_finanziaria', 'Categorie movimenti', (
        'lista_categorie_finanziarie',
        'crea_categoria_finanziaria',
        'modifica_categoria_finanziaria',
        'trasferisci_categoria_finanziaria',
        'elimina_categoria_finanziaria',
    )),
    PermissionPage('gestione_finanziaria_riconciliazione', 'gestione_finanziaria', 'Riconciliazione', (
        'lista_movimenti_da_riconciliare',
        'riconcilia_movimento',
    )),
    PermissionPage('gestione_finanziaria_report_categorie', 'gestione_finanziaria', 'Report categorie', (
        'report_categorie_mensile',
        'report_categorie_annuale',
    )),
    PermissionPage('gestione_finanziaria_conti_bancari', 'gestione_finanziaria', 'Conti bancari', (
        'lista_conti_bancari',
        'crea_conto_bancario',
        'fondi_conti_bancari',
        'modifica_conto_bancario',
        'aggiorna_nome_conto_bancario',
        'elimina_conto_bancario',
        'ricalcola_saldo_conto_bancario',
        'sincronizza_conto_bancario',
    )),
    PermissionPage('gestione_finanziaria_saldi_conti', 'gestione_finanziaria', 'Saldi conti', (
        'lista_saldi_conti',
        'crea_saldo_conto',
        'import_saldi_conti',
        'scarica_template_saldi_conti_csv',
        'modifica_saldo_conto',
        'elimina_saldo_conto',
    )),
    PermissionPage('gestione_finanziaria_import_estratto_conto', 'gestione_finanziaria', 'Import estratto conto', (
        'import_estratto_conto',
    )),
    PermissionPage('gestione_finanziaria_regole_categorizzazione', 'gestione_finanziaria', 'Regole categorizzazione', (
        'lista_regole_categorizzazione',
        'crea_regola_categorizzazione',
        'modifica_regola_categorizzazione',
        'elimina_regola_categorizzazione',
        'applica_regole_massiva',
    )),
    PermissionPage('gestione_finanziaria_connessioni_psd2', 'gestione_finanziaria', 'Connessioni PSD2', (
        'lista_connessioni_bancarie',
        'nuova_connessione_psd2',
        'rinnova_connessione_psd2',
        'callback_connessione_psd2',
        'callback_oauth_psd2',
        'elimina_connessione_psd2',
    )),
    PermissionPage('gestione_finanziaria_provider_bancari', 'gestione_finanziaria', 'Provider bancari', (
        'lista_provider_bancari',
        'crea_provider_bancario',
        'modifica_provider_bancario',
        'elimina_provider_bancario',
        'configura_provider_psd2',
    )),
    PermissionPage('gestione_finanziaria_pianificazione_sync', 'gestione_finanziaria', 'Pianificazione sincronizzazione', (
        'pianificazione_sincronizzazione',
    )),
    PermissionPage('gestione_finanziaria_fatture_in_cloud', 'gestione_finanziaria', 'Fatture in Cloud', (
        'lista_fatture_in_cloud',
        'crea_fatture_in_cloud',
        'modifica_fatture_in_cloud',
        'elimina_fatture_in_cloud',
        'avvia_oauth_fatture_in_cloud',
        'callback_fatture_in_cloud',
        'sincronizza_fatture_in_cloud',
        'diagnostica_payload_fatture_in_cloud',
    )),
    PermissionPage('gestione_finanziaria_budgeting', 'gestione_finanziaria', 'Budgeting', (
        'budgeting_dashboard',
        'crea_voce_budget',
        'modifica_voce_budget',
        'elimina_voce_budget',
        'toggle_voce_budget',
    )),
    PermissionPage('gestione_finanziaria_documenti_fornitori', 'gestione_finanziaria', 'Fatture fornitori', (
        'lista_documenti_fornitori',
        'crea_documento_fornitore',
        'elimina_documenti_fornitori_multipla',
        'pulizia_duplicati_documenti_fornitori',
        'modifica_documento_fornitore',
        'compensa_documento_fornitore',
        'gestisci_proforma_documento',
        'elimina_documento_fornitore',
    )),
    PermissionPage('gestione_finanziaria_scadenziario_fornitori', 'gestione_finanziaria', 'Scadenziario fornitori', (
        'scadenziario_fornitori',
    )),
    PermissionPage('gestione_finanziaria_pagamenti_fornitori', 'gestione_finanziaria', 'Pagamenti fornitori', (
        'lista_movimenti_da_riconciliare_fornitori',
        'riconcilia_movimento_fornitore',
        'registra_pagamento_scadenza_fornitore',
        'elimina_pagamento_fornitore',
    )),
    PermissionPage('gestione_finanziaria_notifiche', 'gestione_finanziaria', 'Notifiche finanziarie', (
        'lista_notifiche_finanziarie',
        'segna_notifica_finanziaria_letta',
        'stato_notifiche_finanziarie',
        'segna_tutte_notifiche_finanziarie_lette',
    )),
    PermissionPage('gestione_amministrativa_dashboard', 'gestione_amministrativa', 'Dashboard dipendenti', (
        'dashboard_gestione_amministrativa',
    )),
    PermissionPage('gestione_amministrativa_dipendenti', 'gestione_amministrativa', 'Dipendenti', (
        'lista_dipendenti',
        'crea_dipendente',
        'modifica_dipendente',
        'elimina_dipendente',
    )),
    PermissionPage('gestione_amministrativa_educatori', 'gestione_amministrativa', 'Educatori', (
        'lista_educatori',
        'crea_educatore',
        'modifica_educatore',
        'elimina_educatore',
    )),
    PermissionPage('gestione_amministrativa_contratti', 'gestione_amministrativa', 'Contratti', (
        'lista_contratti_dipendenti',
        'crea_contratto_dipendente_generico',
        'crea_tipo_contratto_dipendente',
        'modifica_tipo_contratto_dipendente',
        'elimina_tipo_contratto_dipendente',
        'crea_contratto_dipendente',
        'modifica_contratto_dipendente',
        'elimina_contratto_dipendente',
    )),
    PermissionPage('gestione_amministrativa_simulazioni_costo', 'gestione_amministrativa', 'Simulazioni costo', (
        'lista_simulazioni_costo_dipendenti',
        'crea_simulazione_costo_dipendente',
        'modifica_simulazione_costo_dipendente',
        'elimina_simulazione_costo_dipendente',
    )),
    PermissionPage('gestione_amministrativa_buste_paga', 'gestione_amministrativa', 'Buste paga', (
        'genera_previsione_busta_paga',
        'lista_buste_paga_dipendenti',
        'crea_busta_paga_dipendente',
        'modifica_busta_paga_dipendente',
        'apri_file_busta_paga_dipendente',
        'inserisci_pagamento_busta_paga_dipendente',
        'riconcilia_busta_paga_dipendente',
        'elimina_busta_paga_dipendente',
    )),
    PermissionPage('gestione_amministrativa_parametri_calcolo', 'gestione_amministrativa', 'Parametri calcolo', (
        'lista_parametri_calcolo_stipendi',
        'crea_parametro_calcolo_stipendio',
        'modifica_parametro_calcolo_stipendio',
        'elimina_parametro_calcolo_stipendio',
    )),
    PermissionPage('gestione_amministrativa_payroll_ufficiale', 'gestione_amministrativa', 'Dati payroll ufficiali', (
        'lista_dati_payroll_ufficiali',
    )),
    PermissionPage('calendario_agenda', 'calendario', 'Calendario e agenda', (
        'calendario_agenda',
        'lista_eventi_calendario',
        'crea_evento_calendario',
        'crea_evento_calendario_rapido',
        'modifica_evento_calendario',
        'elimina_evento_calendario',
    )),
    PermissionPage('calendario_categorie', 'calendario', 'Categorie calendario', (
        'lista_categorie_calendario',
        'crea_categoria_calendario',
        'modifica_categoria_calendario',
        'elimina_categoria_calendario',
    )),
    PermissionPage('servizi_extra_servizi', 'servizi_extra', 'Servizi', (
        'lista_servizi_extra',
        'crea_servizio_extra',
        'modifica_servizio_extra',
        'elimina_servizio_extra',
    )),
    PermissionPage('servizi_extra_dettaglio_servizi', 'servizi_extra', 'Schede servizi', (
        'dettaglio_servizio_extra',
    )),
    PermissionPage('servizi_extra_tariffe', 'servizi_extra', 'Tariffe servizi', (
        'lista_tariffe_servizi_extra',
        'crea_tariffa_servizio_extra',
        'modifica_tariffa_servizio_extra',
        'elimina_tariffa_servizio_extra',
    )),
    PermissionPage('servizi_extra_iscrizioni', 'servizi_extra', 'Iscrizioni servizi', (
        'lista_iscrizioni_servizi_extra',
        'crea_iscrizione_servizio_extra',
        'modifica_iscrizione_servizio_extra',
        'ricalcola_rate_iscrizione_servizio_extra',
        'elimina_iscrizione_servizio_extra',
    )),
    PermissionPage('servizi_extra_rate', 'servizi_extra', 'Rate servizi', (
        'lista_rate_servizi_extra',
        'modifica_rata_servizio_extra',
    )),
    PermissionPage('sistema_impostazioni_generali', 'sistema', 'Impostazioni generali', (
        'impostazioni_generali_sistema',
        'importa_dati_base_anagrafica',
        'importa_nazioni_belfiore_anagrafica',
    )),
    PermissionPage('sistema_smtp', 'sistema', 'Server SMTP email', (
        'configurazione_email_smtp',
    )),
    PermissionPage('sistema_utenti', 'sistema', 'Utenti', (
        'lista_utenti',
        'crea_utente',
        'elimina_utente',
        'modifica_utente',
    )),
    PermissionPage('sistema_ruoli', 'sistema', 'Ruoli e permessi', (
        'lista_ruoli_utenti',
        'crea_ruolo_utente',
        'elimina_ruolo_utente',
        'modifica_ruolo_utente',
    )),
    PermissionPage('sistema_scuola_dati', 'sistema', 'Dati generali scuola', (
        'scuola_sistema',
        'scuola_crea_indirizzo',
        'scuola_modifica_indirizzo',
        'scuola_elimina_indirizzo',
    )),
    PermissionPage('sistema_anni_scolastici', 'sistema', 'Anni scolastici', (
        'lista_anni_scolastici',
        'crea_anno_scolastico',
        'modifica_anno_scolastico',
        'elimina_anno_scolastico',
    )),
    PermissionPage('sistema_classi', 'sistema', 'Classi', (
        'lista_classi',
        'crea_classe',
        'modifica_classe',
        'elimina_classe',
    )),
    PermissionPage('sistema_pluriclassi', 'sistema', 'Pluriclassi', (
        'lista_gruppi_classe',
        'crea_gruppo_classe',
        'modifica_gruppo_classe',
        'elimina_gruppo_classe',
    )),
    PermissionPage('sistema_backup_database', 'sistema', 'Backup database', (
        'backup_database_sistema',
        'backup_database_restore_chunk_upload',
        'rimuovi_job_ripristino_database',
        'scarica_backup_database',
    )),
    PermissionPage('sistema_cronologia_operazioni', 'sistema', 'Cronologia operazioni', (
        'cronologia_operazioni_sistema',
        'stato_log_operazioni',
        'segna_log_operazione_letta',
        'segna_tutti_log_operazioni_letti',
    )),
    PermissionPage('sistema_feedback_beta', 'sistema', 'Feedback beta', (
        'lista_feedback_segnalazioni',
    )),
    PermissionPage('sistema_crediti', 'sistema', 'Crediti', (
        'crediti',
    )),
    PermissionPage('archivio_storico_anni', 'sistema', 'Archivio storico', (
        'lista_archivio_storico',
        'anteprima_archiviazione_anno',
        'archivia_anno_scolastico',
        'dettaglio_archivio_storico',
    )),
)

PAGES_BY_KEY = {page.key: page for page in PERMISSION_PAGES}
PAGES_BY_VIEW = {view: page for page in PERMISSION_PAGES for view in page.views}
SIDEBAR_PAGE_ALIASES = {"anagrafica_dipendenti": "gestione_amministrativa_dipendenti"}

# These operations are also exposed by the tuition matrix. Access to them does
# not grant access to the complete enrolments/rates lists.
SHARED_PAGE_VIEWS = {
    view: ("economia_panoramica_rette",) for view in (
        "modifica_rata_iscrizione", "pagamento_rapido_rata_iscrizione",
        "riconcilia_rata_iscrizione", "annulla_riconciliazione_rata_iscrizione",
        "ricalcola_rate_anno_scolastico", "riconcilia_pagamenti_rate_anno_scolastico",
    )
}


def page_for_match(match):
    return PAGES_BY_VIEW.get(getattr(match, "url_name", None))
