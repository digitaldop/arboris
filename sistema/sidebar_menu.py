SIDEBAR_MENU_SECTIONS = (
    {
        "key": "calendario",
        "label": "Calendario",
        "children": (
            {"key": "calendario_agenda", "label": "Calendario", "requires": ("can_view_calendario",)},
            {"key": "calendario_eventi", "label": "Eventi", "requires": ("can_view_calendario",)},
            {"key": "calendario_categorie", "label": "Categorie", "requires": ("can_view_calendario",)},
        ),
    },
    {
        "key": "anagrafica",
        "label": "Anagrafiche",
        "children": (
            {"key": "anagrafica_studenti", "label": "Bambini / Studenti", "requires": ("can_view_anagrafica",)},
            {"key": "anagrafica_familiari", "label": "Familiari", "requires": ("can_view_anagrafica",)},
            {"key": "anagrafica_famiglie", "label": "Famiglie", "requires": ("can_view_anagrafica",)},
            {
                "key": "anagrafica_dipendenti",
                "label": "Dipendenti",
                "requires": ("can_view_anagrafica", "can_view_gestione_amministrativa"),
            },
            {
                "key": "anagrafica_fornitori",
                "label": "Rubrica Fornitori",
                "requires": ("can_view_gestione_finanziaria",),
            },
            {"key": "anagrafica_ricerche", "label": "Ricerche", "requires": ("can_view_anagrafica",)},
            {
                "key": "anagrafica_comunicazioni_famiglie",
                "label": "Comunicazioni alle famiglie",
                "requires": ("can_manage_economia",),
            },
            {
                "key": "anagrafica_rette_iscrizioni",
                "label": "Rette e Iscrizioni",
                "children": (
                    {"key": "economia_iscrizioni", "label": "Iscrizioni", "requires": ("can_view_economia",)},
                    {"key": "economia_stati_iscrizione", "label": "Stati iscrizione", "requires": ("can_view_economia",)},
                    {"key": "economia_rate_iscrizione", "label": "Rate iscrizione", "requires": ("can_view_economia",)},
                    {
                        "key": "anagrafica_impostazioni_rette",
                        "label": "Impostazioni Rette",
                        "children": (
                            {
                                "key": "economia_condizioni",
                                "label": "Condizioni economiche",
                                "requires": ("can_view_economia",),
                            },
                            {"key": "economia_tariffe", "label": "Tariffe", "requires": ("can_view_economia",)},
                            {
                                "key": "economia_tariffe_scambio",
                                "label": "Tariffe Scambio Retta",
                                "requires": ("can_view_economia",),
                            },
                            {"key": "economia_agevolazioni", "label": "Agevolazioni", "requires": ("can_view_economia",)},
                        ),
                    },
                ),
            },
        ),
    },
    {
        "key": "gestione_economica",
        "label": "Gestione Economica",
        "children": (
            {
                "key": "gestione_finanziaria_dashboard",
                "label": "Dashboard",
                "requires": ("can_view_gestione_finanziaria",),
            },
            {"key": "economia_panoramica_rette", "label": "Panoramica Rette", "requires": ("can_view_economia",)},
            {
                "key": "gestione_finanziaria_fatture_fornitori_dashboard",
                "label": "Fatture e scadenze",
                "requires": ("can_view_gestione_finanziaria",),
            },
            {
                "key": "gestione_finanziaria_spese_mensili",
                "label": "Spese Mensili",
                "requires": ("can_view_gestione_finanziaria",),
            },
            {"key": "economia_scambi_retta", "label": "Scambi Retta", "requires": ("can_view_economia",)},
            {
                "key": "economia_fondi_accantonamento",
                "label": "Fondi di Accantonamento",
                "requires": ("can_view_economia",),
            },
            {
                "key": "gestione_economica_conti",
                "label": "Conti Correnti",
                "children": (
                    {
                        "key": "gestione_finanziaria_movimenti_bancari",
                        "label": "Movimenti Bancari",
                        "requires": ("can_view_gestione_finanziaria",),
                    },
                    {
                        "key": "gestione_finanziaria_categorie_movimenti",
                        "label": "Categorie movimenti",
                        "requires": ("can_view_gestione_finanziaria",),
                    },
                    {
                        "key": "gestione_finanziaria_riconciliazione",
                        "label": "Riconciliazione",
                        "requires": ("can_view_gestione_finanziaria",),
                    },
                    {
                        "key": "gestione_finanziaria_report_categorie",
                        "label": "Report categorie",
                        "requires": ("can_view_gestione_finanziaria",),
                    },
                    {
                        "key": "gestione_economica_conti_impostazioni",
                        "label": "Impostazioni conti correnti",
                        "children": (
                            {
                                "key": "gestione_finanziaria_conti_bancari",
                                "label": "Conti bancari",
                                "requires": ("can_view_gestione_finanziaria",),
                            },
                            {
                                "key": "gestione_finanziaria_saldi_conti",
                                "label": "Saldi conti",
                                "requires": ("can_view_gestione_finanziaria",),
                            },
                            {
                                "key": "gestione_finanziaria_import_estratto_conto",
                                "label": "Import estratto conto",
                                "requires": ("can_manage_gestione_finanziaria",),
                            },
                            {
                                "key": "gestione_finanziaria_regole_categorizzazione",
                                "label": "Regole categorizzazione",
                                "requires": ("can_view_gestione_finanziaria",),
                            },
                            {
                                "key": "gestione_finanziaria_connessioni_psd2",
                                "label": "Connessioni PSD2",
                                "requires": ("can_view_gestione_finanziaria",),
                            },
                            {
                                "key": "gestione_finanziaria_provider_bancari",
                                "label": "Provider bancari",
                                "requires": ("can_view_gestione_finanziaria",),
                            },
                            {
                                "key": "gestione_finanziaria_pianificazione_sync",
                                "label": "Pianificazione sincronizzazione",
                                "requires": ("can_manage_gestione_finanziaria",),
                            },
                        ),
                    },
                ),
            },
            {
                "key": "gestione_economica_dipendenti_collaboratori",
                "label": "Dipendenti e Collaboratori",
                "children": (
                    {
                        "key": "gestione_amministrativa_dashboard",
                        "label": "Dashboard",
                        "requires": ("can_view_gestione_amministrativa", "gestione_dipendenti_dettagliata_attiva"),
                    },
                    {
                        "key": "gestione_amministrativa_educatori",
                        "label": "Educatori",
                        "requires": ("can_view_gestione_amministrativa",),
                    },
                    {
                        "key": "gestione_amministrativa_dipendenti",
                        "label": "Dipendenti",
                        "requires": ("can_view_gestione_amministrativa",),
                    },
                    {
                        "key": "gestione_amministrativa_contratti",
                        "label": "Contratti",
                        "requires": ("can_view_gestione_amministrativa",),
                    },
                    {
                        "key": "gestione_amministrativa_simulazioni_costo",
                        "label": "Simulazioni costo",
                        "requires": ("can_view_gestione_amministrativa", "gestione_dipendenti_dettagliata_attiva"),
                    },
                    {
                        "key": "gestione_amministrativa_buste_paga",
                        "label": "Buste paga",
                        "requires": ("can_view_gestione_amministrativa",),
                    },
                    {
                        "key": "gestione_amministrativa_parametri_calcolo",
                        "label": "Parametri calcolo",
                        "requires": ("can_view_gestione_amministrativa", "gestione_dipendenti_dettagliata_attiva"),
                    },
                    {
                        "key": "gestione_amministrativa_payroll_ufficiale",
                        "label": "Dati payroll ufficiali",
                        "requires": ("can_view_gestione_amministrativa", "gestione_dipendenti_dettagliata_attiva"),
                    },
                ),
            },
        ),
    },
    {
        "key": "servizi_extra",
        "label": "Servizi extra",
        "children": (
            {"key": "servizi_extra_servizi", "label": "Servizi", "requires": ("can_view_servizi_extra",)},
            {
                "key": "servizi_extra_dettaglio_servizi",
                "label": "Schede servizi",
                "requires": ("can_view_servizi_extra",),
            },
            {
                "key": "servizi_extra_impostazioni",
                "label": "Impostazioni Servizi Extra",
                "children": (
                    {"key": "servizi_extra_tariffe", "label": "Tariffe", "requires": ("can_view_servizi_extra",)},
                    {"key": "servizi_extra_iscrizioni", "label": "Iscrizioni", "requires": ("can_view_servizi_extra",)},
                    {"key": "servizi_extra_rate", "label": "Rate", "requires": ("can_view_servizi_extra",)},
                ),
            },
        ),
    },
    {
        "key": "famiglie_interessate",
        "label": "Famiglie interessate",
        "children": (
            {
                "key": "famiglie_interessate_contatti",
                "label": "Contatti e follow-up",
                "requires": ("can_view_famiglie_interessate",),
            },
        ),
    },
    {
        "key": "archivio_storico",
        "label": "Archivio storico",
        "children": (
            {"key": "archivio_storico_anni", "label": "Anni archiviati", "requires": ("can_view_sistema",)},
        ),
    },
    {
        "key": "parcheggio",
        "label": "Parcheggio",
        "children": (
            {
                "key": "gestione_finanziaria_budgeting",
                "label": "Budgeting",
                "requires": ("can_view_system_tables", "can_manage_gestione_finanziaria"),
            },
            {
                "key": "gestione_finanziaria_documenti_fornitori",
                "label": "Fatture fornitori",
                "requires": ("can_view_system_tables", "can_manage_gestione_finanziaria"),
            },
            {
                "key": "gestione_finanziaria_scadenziario_fornitori",
                "label": "Scadenziario fornitori",
                "requires": ("can_view_system_tables", "can_manage_gestione_finanziaria"),
            },
            {
                "key": "gestione_finanziaria_pagamenti_fornitori",
                "label": "Pagamenti fornitori",
                "requires": ("can_view_system_tables", "can_manage_gestione_finanziaria"),
            },
            {
                "key": "gestione_finanziaria_notifiche",
                "label": "Notifiche",
                "requires": ("can_view_system_tables", "can_manage_gestione_finanziaria"),
            },
        ),
    },
    {
        "key": "sistema",
        "label": "Impostazioni generali",
        "children": (
            {"key": "sistema_impostazioni_generali", "label": "Impostazioni generali", "requires": ("can_view_sistema",)},
            {"key": "sistema_smtp", "label": "Server SMTP email", "requires": ("can_view_sistema", "can_manage_sistema")},
            {"key": "sistema_crediti", "label": "Crediti", "requires": ("can_view_sistema",)},
            {
                "key": "sistema_account",
                "label": "Gestione Account",
                "children": (
                    {"key": "sistema_utenti", "label": "Utenti", "requires": ("can_view_sistema",)},
                    {"key": "sistema_ruoli", "label": "Ruoli", "requires": ("can_view_sistema",)},
                ),
            },
            {
                "key": "sistema_impostazioni_fornitori",
                "label": "Impostazioni Fornitori",
                "children": (
                    {
                        "key": "gestione_finanziaria_fatture_in_cloud",
                        "label": "Fatture in Cloud",
                        "requires": ("can_view_gestione_finanziaria",),
                    },
                    {
                        "key": "gestione_finanziaria_categorie_spesa",
                        "label": "Categorie di spesa",
                        "requires": ("can_view_gestione_finanziaria",),
                    },
                ),
            },
            {
                "key": "sistema_backup_cronologia",
                "label": "Backup e Cronologia",
                "children": (
                    {"key": "sistema_backup_database", "label": "Backup Database", "requires": ("can_access_database_backups",)},
                    {
                        "key": "sistema_cronologia_operazioni",
                        "label": "Cronologia Operazioni",
                        "requires": ("can_view_operation_history",),
                    },
                    {"key": "sistema_feedback_beta", "label": "Feedback beta", "requires": ("can_view_operation_history",)},
                ),
            },
            {
                "key": "sistema_scuola",
                "label": "Impostazioni Scuola",
                "children": (
                    {"key": "sistema_scuola_dati", "label": "Dati Generali Scuola", "requires": ("can_view_sistema", "can_manage_sistema")},
                    {"key": "sistema_anni_scolastici", "label": "Anni scolastici", "requires": ("can_view_sistema",)},
                    {"key": "sistema_classi", "label": "Classi", "requires": ("can_view_sistema",)},
                    {"key": "sistema_pluriclassi", "label": "Pluriclassi", "requires": ("can_view_sistema",)},
                ),
            },
        ),
    },
)


def iter_sidebar_menu_items(nodes=SIDEBAR_MENU_SECTIONS):
    for node in nodes:
        children = node.get("children")
        if children:
            yield from iter_sidebar_menu_items(children)
        else:
            yield node


def iter_sidebar_menu_groups(nodes=SIDEBAR_MENU_SECTIONS):
    for node in nodes:
        children = node.get("children")
        if children:
            yield node
            yield from iter_sidebar_menu_groups(children)


SIDEBAR_MENU_ITEM_CHOICES = tuple(
    (item["key"], item["label"]) for item in iter_sidebar_menu_items()
)
SIDEBAR_MENU_ITEM_KEYS = tuple(key for key, _label in SIDEBAR_MENU_ITEM_CHOICES)
SIDEBAR_MENU_ITEM_KEY_SET = frozenset(SIDEBAR_MENU_ITEM_KEYS)


def normalize_sidebar_menu_disabled_keys(value):
    if not isinstance(value, (list, tuple, set)):
        return []

    normalized = []
    seen = set()
    for raw_key in value:
        key = str(raw_key or "").strip()
        if key in SIDEBAR_MENU_ITEM_KEY_SET and key not in seen:
            normalized.append(key)
            seen.add(key)
    return normalized


def get_role_sidebar_menu_disabled_keys(role):
    if not role:
        return []
    return normalize_sidebar_menu_disabled_keys(
        getattr(role, "voci_menu_disabilitate", [])
    )


def _node_is_visible(node, flags, disabled_keys):
    children = node.get("children")
    if children:
        return any(_node_is_visible(child, flags, disabled_keys) for child in children)
    if node["key"] in disabled_keys:
        return False
    return all(bool(flags.get(flag_name)) for flag_name in node.get("requires", ()))


def build_sidebar_menu_state(disabled_keys, flags):
    disabled_key_set = set(normalize_sidebar_menu_disabled_keys(disabled_keys))
    items = {}
    groups = {}

    def visit(node):
        children = node.get("children")
        if children:
            child_visibility = [visit(child) for child in children]
            visible = any(child_visibility)
            groups[node["key"]] = visible
            return visible

        visible = _node_is_visible(node, flags, disabled_key_set)
        items[node["key"]] = visible
        return visible

    for section in SIDEBAR_MENU_SECTIONS:
        visit(section)

    return {
        "items": items,
        "groups": groups,
    }


def build_sidebar_menu_form_sections(selected_keys):
    selected_key_set = set(selected_keys or ())

    def build_node(node):
        children = node.get("children")
        data = {
            "key": node["key"],
            "label": node["label"],
            "is_group": bool(children),
        }
        if children:
            data["children"] = [build_node(child) for child in children]
        else:
            data["checked"] = node["key"] in selected_key_set
        return data

    return [build_node(section) for section in SIDEBAR_MENU_SECTIONS]
