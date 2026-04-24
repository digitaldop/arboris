from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("economia", "0005_scambio_retta"),
    ]

    operations = [
        migrations.AddField(
            model_name="movimentocreditoretta",
            name="scambio_retta",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="movimenti_credito_retta",
                to="economia.scambioretta",
            ),
        ),
    ]
