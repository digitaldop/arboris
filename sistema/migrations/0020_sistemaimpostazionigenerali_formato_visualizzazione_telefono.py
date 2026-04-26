from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("sistema", "0019_alter_sistemadatabasebackup_file_backup"),
    ]

    operations = [
        migrations.AddField(
            model_name="sistemaimpostazionigenerali",
            name="formato_visualizzazione_telefono",
            field=models.CharField(
                choices=[
                    ("it_plus_n3_2_2_3", "+ prefisso (se presente) 345 67 89 675"),
                    ("it_plus_n3_3_2_2", "+ prefisso (se presente) 345 678 96 75"),
                    ("it_plus_n10", "+ prefisso (se presente) 3456789675"),
                ],
                default="it_plus_n3_2_2_3",
                help_text="Come mostrare i numeri di telefono in elenchi e schede (in archivio restano senza spazi).",
                max_length=32,
            ),
        ),
    ]
