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

    seed_label_group(LabelIndirizzo, db_alias, ADDRESS_LABELS)
    seed_label_group(LabelTelefono, db_alias, PHONE_LABELS)
    seed_label_group(LabelEmail, db_alias, EMAIL_LABELS)


def seed_label_group(Model, db_alias, labels):
    existing_by_name = {
        label.nome: label
        for label in Model.objects.using(db_alias).filter(nome__in=labels)
    }
    used_orders = set(
        Model.objects.using(db_alias)
        .exclude(ordine__isnull=True)
        .values_list("ordine", flat=True)
    )

    for preferred_order, nome in enumerate(labels, start=1):
        label = existing_by_name.get(nome)
        if label is None:
            ordine = available_order_from_cache(Model, db_alias, used_orders, preferred_order)
            label = Model.objects.using(db_alias).create(
                nome=nome,
                ordine=ordine,
                attiva=True,
            )
            existing_by_name[nome] = label
            used_orders.add(ordine)
            continue

        update_fields = []
        if not label.attiva:
            label.attiva = True
            update_fields.append("attiva")
        if label.ordine is None:
            label.ordine = available_order_from_cache(Model, db_alias, used_orders, preferred_order)
            update_fields.append("ordine")
            used_orders.add(label.ordine)
        if update_fields:
            label.save(update_fields=update_fields)


def available_order_from_cache(Model, db_alias, used_orders, preferred_order):
    if preferred_order and preferred_order not in used_orders:
        return preferred_order

    max_order = Model.objects.using(db_alias).aggregate(Max("ordine"))["ordine__max"] or 0
    candidate = max(max_order, max(used_orders or {0})) + 1
    while candidate in used_orders:
        candidate += 1
    return candidate


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


class Migration(migrations.Migration):
    atomic = False

    dependencies = [
        ("anagrafica", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(seed_contact_labels, migrations.RunPython.noop, atomic=False),
        migrations.RunPython(drop_legacy_family_tables, migrations.RunPython.noop, atomic=False),
    ]
