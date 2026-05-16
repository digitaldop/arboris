from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("gestione_finanziaria", "0003_pianoratealespesa_spesaoperativa_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="contobancario",
            name="external_account_hash",
            field=models.CharField(
                blank=True,
                db_index=True,
                help_text=(
                    "Identificativo stabile lato provider, se disponibile. Per Enable Banking "
                    "corrisponde a identification_hash e aiuta a riconoscere lo stesso conto "
                    "fra sessioni diverse."
                ),
                max_length=512,
            ),
        ),
        migrations.AddField(
            model_name="contobancario",
            name="external_account_type",
            field=models.CharField(
                blank=True,
                help_text="Tipo conto lato provider (es. Enable Banking cash_account_type: CACC, CARD, SVGS).",
                max_length=40,
            ),
        ),
        migrations.AddField(
            model_name="contobancario",
            name="external_account_product",
            field=models.CharField(
                blank=True,
                help_text="Prodotto/dettaglio conto restituito dal provider PSD2, se disponibile.",
                max_length=200,
            ),
        ),
    ]
