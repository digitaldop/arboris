import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("economia", "0006_movimentocreditoretta_scambio_retta"),
    ]

    operations = [
        migrations.AddField(
            model_name="condizioneiscrizione",
            name="giorno_scadenza_rate",
            field=models.PositiveSmallIntegerField(
                blank=True,
                help_text="Giorno del mese usato per calcolare la scadenza di ciascuna rata.",
                null=True,
                validators=[django.core.validators.MinValueValidator(1), django.core.validators.MaxValueValidator(31)],
            ),
        ),
    ]
