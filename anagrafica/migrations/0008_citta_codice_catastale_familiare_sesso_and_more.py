from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("anagrafica", "0007_luogo_nascita_fk"),
    ]

    operations = [
        migrations.AddField(
            model_name="citta",
            name="codice_catastale",
            field=models.CharField(blank=True, db_index=True, max_length=4),
        ),
        migrations.AddField(
            model_name="familiare",
            name="sesso",
            field=models.CharField(blank=True, choices=[("M", "Maschio"), ("F", "Femmina")], max_length=1),
        ),
        migrations.AddField(
            model_name="studente",
            name="sesso",
            field=models.CharField(blank=True, choices=[("M", "Maschio"), ("F", "Femmina")], max_length=1),
        ),
    ]
