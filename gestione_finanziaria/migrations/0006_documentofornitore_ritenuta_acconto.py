from decimal import Decimal

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("gestione_finanziaria", "0005_alter_notificafinanziaria_tipo"),
    ]

    operations = [
        migrations.AddField(
            model_name="documentofornitore",
            name="imponibile_ritenuta_acconto",
            field=models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=12),
        ),
        migrations.AddField(
            model_name="documentofornitore",
            name="aliquota_ritenuta_acconto",
            field=models.DecimalField(decimal_places=2, default=Decimal("20.00"), max_digits=5),
        ),
        migrations.AddField(
            model_name="documentofornitore",
            name="ritenuta_acconto",
            field=models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=12),
        ),
    ]
