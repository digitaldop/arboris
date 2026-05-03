# Generated manually for Arboris.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("sistema", "0026_famiglie_interessate_permissions"),
    ]

    operations = [
        migrations.AlterField(
            model_name="sistemaoperazionecronologia",
            name="modulo",
            field=models.CharField(
                choices=[
                    ("anagrafica", "Anagrafica"),
                    ("famiglie_interessate", "Famiglie interessate"),
                    ("economia", "Economia"),
                    ("scuola", "Scuola"),
                    ("calendario", "Calendario"),
                    ("servizi_extra", "Servizi extra"),
                    ("gestione_finanziaria", "Gestione finanziaria"),
                    ("gestione_amministrativa", "Gestione amministrativa"),
                    ("sistema", "Sistema"),
                ],
                default="sistema",
                max_length=30,
            ),
        ),
    ]
