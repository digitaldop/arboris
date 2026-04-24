# Generated manually on 2026-04-22

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("calendario", "0005_rename_ripeti_ogni_settimane_and_extend_recurrence"),
    ]

    operations = [
        migrations.AlterField(
            model_name="eventocalendario",
            name="ripetizione",
            field=models.CharField(
                choices=[
                    ("nessuna", "Non si ripete"),
                    ("giornaliera", "Giornaliera"),
                    ("giorni_feriali", "Giorni feriali"),
                    ("settimanale", "Settimanale"),
                    ("mensile", "Mensile"),
                    ("annuale", "Annuale"),
                ],
                default="nessuna",
                max_length=20,
            ),
        ),
    ]
