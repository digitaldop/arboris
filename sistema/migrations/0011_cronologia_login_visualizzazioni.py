from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("sistema", "0010_log_operazioni_letture"),
    ]

    operations = [
        migrations.AlterField(
            model_name="sistemaoperazionecronologia",
            name="azione",
            field=models.CharField(
                max_length=20,
                choices=[
                    ("create", "Creazione"),
                    ("update", "Modifica"),
                    ("delete", "Eliminazione"),
                    ("login", "Login"),
                    ("view", "Visualizzazione pagina"),
                ],
            ),
        ),
    ]
