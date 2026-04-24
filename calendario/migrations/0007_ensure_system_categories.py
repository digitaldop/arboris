from django.db import migrations
from django.db.models import Max


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
)


def ensure_system_categories(apps, schema_editor):
    CategoriaCalendario = apps.get_model("calendario", "CategoriaCalendario")

    next_order = (
        CategoriaCalendario.objects.aggregate(max_ordine=Max("ordine"))["max_ordine"]
        or 0
    ) + 1

    for definition in SYSTEM_CATEGORY_DEFINITIONS:
        categoria = CategoriaCalendario.objects.filter(
            chiave_sistema=definition["key"]
        ).first()

        if not categoria:
            categoria = CategoriaCalendario.objects.filter(
                nome__iexact=definition["name"]
            ).first()

        if categoria:
            categoria.chiave_sistema = definition["key"]
            categoria.attiva = True

            if not categoria.colore:
                categoria.colore = definition["color"]

            if not categoria.ordine:
                categoria.ordine = next_order
                next_order += 1

            categoria.save()
        else:
            CategoriaCalendario.objects.create(
                nome=definition["name"],
                colore=definition["color"],
                chiave_sistema=definition["key"],
                ordine=next_order,
                attiva=True,
            )
            next_order += 1


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("calendario", "0006_extend_recurrence_with_weekdays"),
    ]

    operations = [
        migrations.RunPython(ensure_system_categories, noop_reverse),
    ]