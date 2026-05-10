from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("sistema", "0029_sistemaimpostazionigenerali_cronologia_retention_mesi"),
    ]

    operations = [
        migrations.AddField(
            model_name="sistemaimpostazionigenerali",
            name="gestione_dipendenti_dettagliata_attiva",
            field=models.BooleanField(
                default=False,
                help_text=(
                    "Se attiva mostra parametri payroll, simulazioni costo dettagliate e campi contrattuali tecnici. "
                    "Se disattiva mantiene una gestione semplificata con dipendenti, contratti e buste paga."
                ),
            ),
        ),
    ]
