from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("sistema", "0030_sistemaimpostazionigenerali_gestione_dipendenti_dettagliata_attiva"),
    ]

    operations = [
        migrations.AddField(
            model_name="sistemaimpostazionigenerali",
            name="terminologia_familiare",
            field=models.CharField(
                choices=[
                    ("familiare", "FAMILIARE"),
                    ("genitore", "GENITORE"),
                    ("parente", "PARENTE"),
                ],
                default="familiare",
                help_text="Scegli la dicitura da visualizzare per i familiari nelle interfacce anagrafiche.",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="sistemaimpostazionigenerali",
            name="terminologia_educatore",
            field=models.CharField(
                choices=[
                    ("educatore", "EDUCATORE"),
                    ("maestro", "MAESTRO"),
                    ("insegnante", "INSEGNANTE"),
                ],
                default="educatore",
                help_text="Scegli la dicitura da visualizzare per educatori, maestri o insegnanti.",
                max_length=20,
            ),
        ),
    ]
