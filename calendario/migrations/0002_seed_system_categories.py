from django.db import migrations


SYSTEM_CATEGORY_DEFINITIONS = (
    {
        "key": "scadenze_rette",
        "name": "Scadenze rette",
        "color": "#be123c",
    },
    {
        "key": "documenti",
        "name": "Documenti",
        "color": "#b45309",
    },
    {
        "key": "scadenze_fornitori",
        "name": "Scadenze fornitori",
        "color": "#0f766e",
    },
    {
        "key": "famiglie_interessate",
        "name": "Famiglie interessate",
        "color": "#417690",
    },
)


def seed_system_categories(apps, schema_editor):
    db_alias = schema_editor.connection.alias
    CategoriaCalendario = apps.get_model("calendario", "CategoriaCalendario")

    for index, definition in enumerate(SYSTEM_CATEGORY_DEFINITIONS, start=1):
        categoria = (
            CategoriaCalendario.objects.using(db_alias)
            .filter(chiave_sistema=definition["key"])
            .first()
        )
        if not categoria:
            categoria = (
                CategoriaCalendario.objects.using(db_alias)
                .filter(nome__iexact=definition["name"])
                .first()
            )

        defaults = {
            "nome": definition["name"],
            "colore": definition["color"],
            "chiave_sistema": definition["key"],
            "ordine": index,
            "attiva": True,
        }
        if categoria:
            for field, value in defaults.items():
                setattr(categoria, field, value)
            categoria.save(using=db_alias)
        else:
            CategoriaCalendario.objects.using(db_alias).create(**defaults)


class Migration(migrations.Migration):

    dependencies = [
        ("calendario", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(seed_system_categories, migrations.RunPython.noop),
    ]
