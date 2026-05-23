from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("anagrafica", "0005_alter_familiare_persona"),
    ]

    operations = [
        migrations.AlterField(
            model_name="familiare",
            name="relazione_familiare",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="familiari",
                to="anagrafica.relazionefamiliare",
            ),
        ),
    ]
