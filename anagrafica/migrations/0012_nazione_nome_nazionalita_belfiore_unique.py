from django.db import migrations, models


def seed_nome_nazionalita(apps, schema_editor):
    Nazione = apps.get_model("anagrafica", "Nazione")
    defaults = {
        "Italia": "Italiana",
        "Francia": "Francese",
    }
    for nome, nazionalita in defaults.items():
        Nazione.objects.filter(nome__iexact=nome).update(nome_nazionalita=nazionalita)


class Migration(migrations.Migration):

    dependencies = [
        ("anagrafica", "0011_nazione_familiare_luogo_nascita_custom_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="nazione",
            name="nome_nazionalita",
            field=models.CharField(blank=True, max_length=120),
        ),
        migrations.AlterField(
            model_name="nazione",
            name="nome",
            field=models.CharField(db_index=True, max_length=120),
        ),
        migrations.AddConstraint(
            model_name="nazione",
            constraint=models.UniqueConstraint(
                condition=~models.Q(codice_belfiore=""),
                fields=("codice_belfiore",),
                name="unique_nazione_codice_belfiore_non_vuoto",
            ),
        ),
        migrations.RunPython(seed_nome_nazionalita, migrations.RunPython.noop),
    ]
