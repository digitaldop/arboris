from django.db import migrations


PERMISSION_FIELDS = (
    "permesso_anagrafica",
    "permesso_famiglie_interessate",
    "permesso_economia",
    "permesso_sistema",
    "permesso_calendario",
    "permesso_gestione_finanziaria",
    "permesso_gestione_amministrativa",
    "permesso_servizi_extra",
)


DEFAULT_ROLES = (
    {
        "key": "amministratore",
        "name": "Amministratore",
        "color": "#417690",
        "amministratore_operativo": True,
        "accesso_backup_database": True,
        "controllo_completo": True,
        "permissions": {field: "manage" for field in PERMISSION_FIELDS},
    },
    {
        "key": "segreteria_amministrativa",
        "name": "Segreteria Amministrativa",
        "color": "#2f855a",
        "amministratore_operativo": False,
        "accesso_backup_database": False,
        "controllo_completo": False,
        "permissions": {
            "permesso_anagrafica": "manage",
            "permesso_famiglie_interessate": "manage",
            "permesso_economia": "manage",
            "permesso_sistema": "view",
            "permesso_calendario": "manage",
            "permesso_gestione_finanziaria": "manage",
            "permesso_gestione_amministrativa": "view",
            "permesso_servizi_extra": "manage",
        },
    },
    {
        "key": "segreteria_didattica",
        "name": "Segreteria Didattica",
        "color": "#7c3aed",
        "amministratore_operativo": False,
        "accesso_backup_database": False,
        "controllo_completo": False,
        "permissions": {
            "permesso_anagrafica": "manage",
            "permesso_famiglie_interessate": "manage",
            "permesso_economia": "view",
            "permesso_sistema": "none",
            "permesso_calendario": "manage",
            "permesso_gestione_finanziaria": "none",
            "permesso_gestione_amministrativa": "none",
            "permesso_servizi_extra": "manage",
        },
    },
    {
        "key": "insegnante",
        "name": "Insegnante",
        "color": "#b7791f",
        "amministratore_operativo": False,
        "accesso_backup_database": False,
        "controllo_completo": False,
        "permissions": {
            "permesso_anagrafica": "view",
            "permesso_famiglie_interessate": "none",
            "permesso_economia": "none",
            "permesso_sistema": "none",
            "permesso_calendario": "view",
            "permesso_gestione_finanziaria": "none",
            "permesso_gestione_amministrativa": "none",
            "permesso_servizi_extra": "view",
        },
    },
    {
        "key": "membro_cda",
        "name": "Membro del CDA",
        "color": "#0f766e",
        "amministratore_operativo": False,
        "accesso_backup_database": False,
        "controllo_completo": False,
        "permissions": {
            "permesso_anagrafica": "view",
            "permesso_famiglie_interessate": "view",
            "permesso_economia": "view",
            "permesso_sistema": "view",
            "permesso_calendario": "view",
            "permesso_gestione_finanziaria": "view",
            "permesso_gestione_amministrativa": "view",
            "permesso_servizi_extra": "view",
        },
    },
    {
        "key": "visualizzatore",
        "name": "Visualizzatore",
        "color": "#64748b",
        "amministratore_operativo": False,
        "accesso_backup_database": False,
        "controllo_completo": False,
        "permissions": {
            "permesso_anagrafica": "view",
            "permesso_famiglie_interessate": "view",
            "permesso_economia": "view",
            "permesso_sistema": "none",
            "permesso_calendario": "view",
            "permesso_gestione_finanziaria": "view",
            "permesso_gestione_amministrativa": "none",
            "permesso_servizi_extra": "view",
        },
    },
)


def seed_default_roles(apps, schema_editor):
    db_alias = schema_editor.connection.alias
    SistemaRuoloPermessi = apps.get_model("sistema", "SistemaRuoloPermessi")

    for config in DEFAULT_ROLES:
        defaults = {
            "nome": config["name"],
            "descrizione": "Ruolo predefinito creato automaticamente dal sistema.",
            "colore_principale": config["color"],
            "attivo": True,
            "amministratore_operativo": config["amministratore_operativo"],
            "accesso_backup_database": config["accesso_backup_database"],
            "controllo_completo": config["controllo_completo"],
        }
        defaults.update(config["permissions"])
        SistemaRuoloPermessi.objects.using(db_alias).update_or_create(
            chiave_legacy=config["key"],
            defaults=defaults,
        )


class Migration(migrations.Migration):

    dependencies = [
        ("sistema", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(seed_default_roles, migrations.RunPython.noop),
    ]
