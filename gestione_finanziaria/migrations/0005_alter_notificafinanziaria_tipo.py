from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("gestione_finanziaria", "0004_conto_bancario_provider_account_metadata"),
    ]

    operations = [
        migrations.AlterField(
            model_name="notificafinanziaria",
            name="tipo",
            field=models.CharField(
                choices=[
                    ("fattura_ricevuta", "Fattura ricevuta"),
                    ("movimento_bancario", "Movimento bancario"),
                    ("scadenza_prossima", "Scadenza prossima"),
                    ("scadenza_insoluta", "Scadenza insoluta"),
                    ("riconciliazione", "Riconciliazione"),
                    ("integrazione", "Integrazione"),
                ],
                default="integrazione",
                max_length=30,
            ),
        ),
    ]
