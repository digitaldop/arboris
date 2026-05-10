from django.db import migrations
from django.db.models import Max


ADDRESS_LABELS = ["Principale", "Residenza", "Domicilio", "Casa", "Lavoro", "Altro"]
PHONE_LABELS = ["Principale", "Cellulare", "Casa", "Lavoro", "Emergenza", "Altro"]
EMAIL_LABELS = ["Principale", "Personale", "Lavoro", "PEC", "Altro"]


def seed_contact_labels(apps, schema_editor):
    db_alias = schema_editor.connection.alias
    LabelIndirizzo = apps.get_model("anagrafica", "LabelIndirizzo")
    LabelTelefono = apps.get_model("anagrafica", "LabelTelefono")
    LabelEmail = apps.get_model("anagrafica", "LabelEmail")

    for index, nome in enumerate(ADDRESS_LABELS, start=1):
        ensure_label(LabelIndirizzo, db_alias, nome, index)
    for index, nome in enumerate(PHONE_LABELS, start=1):
        ensure_label(LabelTelefono, db_alias, nome, index)
    for index, nome in enumerate(EMAIL_LABELS, start=1):
        ensure_label(LabelEmail, db_alias, nome, index)


def next_order(Model, db_alias):
    max_order = Model.objects.using(db_alias).aggregate(Max("ordine"))["ordine__max"]
    return (max_order or 0) + 1


def ensure_label(Model, db_alias, nome, preferred_order):
    label = Model.objects.using(db_alias).filter(nome=nome).first()
    if label is None:
        Model.objects.using(db_alias).create(
            nome=nome,
            ordine=available_order(Model, db_alias, preferred_order),
            attiva=True,
        )
        return

    update_fields = []
    if not label.attiva:
        label.attiva = True
        update_fields.append("attiva")
    if label.ordine is None:
        label.ordine = next_order(Model, db_alias)
        update_fields.append("ordine")
    if update_fields:
        label.save(update_fields=update_fields)


def available_order(Model, db_alias, preferred_order):
    if preferred_order and not Model.objects.using(db_alias).filter(ordine=preferred_order).exists():
        return preferred_order
    return next_order(Model, db_alias)


def drop_legacy_family_tables(apps, schema_editor):
    del apps
    existing_tables = set(schema_editor.connection.introspection.table_names())
    legacy_tables = [
        "anagrafica_famiglia",
        "anagrafica_statorelazionefamiglia",
    ]
    quoted_tables = [
        schema_editor.quote_name(table)
        for table in legacy_tables
        if table in existing_tables
    ]
    if not quoted_tables:
        return

    if schema_editor.connection.vendor == "postgresql":
        for table in quoted_tables:
            schema_editor.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
        return

    if schema_editor.connection.vendor == "sqlite":
        schema_editor.execute("PRAGMA foreign_keys=OFF")
        try:
            for table in quoted_tables:
                schema_editor.execute(f"DROP TABLE IF EXISTS {table}")
        finally:
            schema_editor.execute("PRAGMA foreign_keys=ON")
        return

    for table in quoted_tables:
        schema_editor.execute(f"DROP TABLE IF EXISTS {table}")


def seed_and_cleanup(apps, schema_editor):
    seed_contact_labels(apps, schema_editor)
    drop_legacy_family_tables(apps, schema_editor)


class Migration(migrations.Migration):

    dependencies = [
        ("anagrafica", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(seed_and_cleanup, migrations.RunPython.noop),
    ]
