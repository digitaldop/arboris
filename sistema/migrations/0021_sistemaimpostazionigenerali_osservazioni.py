from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("sistema", "0020_sistemaimpostazionigenerali_formato_visualizzazione_telefono"),
    ]

    operations = [
        migrations.AddField(
            model_name="sistemaimpostazionigenerali",
            name="osservazioni_solo_autori_visualizzazione",
            field=models.BooleanField(
                default=False,
                help_text=(
                    "Quando attiva, le osservazioni collegate agli studenti sono visibili solo "
                    "all'autore, salvo amministratori e superuser."
                ),
            ),
        ),
        migrations.AddField(
            model_name="sistemaimpostazionigenerali",
            name="osservazioni_solo_autori_modifica",
            field=models.BooleanField(
                default=True,
                help_text=(
                    "Quando attiva, solo l'autore puo modificare o cancellare le proprie osservazioni, "
                    "salvo amministratori e superuser."
                ),
            ),
        ),
    ]
