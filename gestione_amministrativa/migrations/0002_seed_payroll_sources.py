from django.db import migrations


OFFICIAL_SOURCE_CATALOG = (
    {
        "codice": "INPS_ALIQUOTE_CONTRIBUTIVE",
        "nome": "Aliquote contributive INPS",
        "ente": "INPS",
        "fonte_url": "https://www.inps.it/",
        "descrizione": "Pagina ufficiale INPS con aliquote e indicazioni contributive.",
    },
    {
        "codice": "INPS_MINIMALI_MASSIMALI",
        "nome": "Minimali e massimali contributivi INPS",
        "ente": "INPS",
        "fonte_url": "https://www.inps.it/",
        "descrizione": "Comunicazioni INPS per minimali, massimali e valori annuali.",
    },
    {
        "codice": "INAIL_AUTOLIQUIDAZIONE",
        "nome": "Autoliquidazione e premi INAIL",
        "ente": "INAIL",
        "fonte_url": "https://www.inail.it/",
        "descrizione": "Pagina ufficiale INAIL per autoliquidazione e premio assicurativo.",
    },
    {
        "codice": "MEF_ADDIZIONALI_COMUNALI",
        "nome": "Addizionali comunali IRPEF",
        "ente": "Dipartimento Finanze",
        "fonte_url": "https://www1.finanze.gov.it/",
        "descrizione": "Archivio ufficiale delle aliquote comunali IRPEF.",
    },
    {
        "codice": "MEF_ADDIZIONALI_REGIONALI",
        "nome": "Addizionali regionali IRPEF",
        "ente": "Dipartimento Finanze",
        "fonte_url": "https://www1.finanze.gov.it/",
        "descrizione": "Archivio ufficiale delle aliquote regionali IRPEF.",
    },
    {
        "codice": "CNEL_CCNL",
        "nome": "Archivio CNEL dei contratti collettivi",
        "ente": "CNEL / Ministero del Lavoro",
        "fonte_url": "https://www.lavoro.gov.it/",
        "descrizione": "Archivio ufficiale dei contratti collettivi nazionali depositati.",
    },
)


def seed_payroll_sources(apps, schema_editor):
    db_alias = schema_editor.connection.alias
    DatoPayrollUfficiale = apps.get_model("gestione_amministrativa", "DatoPayrollUfficiale")

    for source in OFFICIAL_SOURCE_CATALOG:
        DatoPayrollUfficiale.objects.using(db_alias).update_or_create(
            categoria="fonte",
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
                "metadata": {"tipo_record": "catalogo_fonte", "aggiornato_da": "sistema"},
            },
        )


class Migration(migrations.Migration):

    dependencies = [
        ("gestione_amministrativa", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(seed_payroll_sources, migrations.RunPython.noop),
    ]
