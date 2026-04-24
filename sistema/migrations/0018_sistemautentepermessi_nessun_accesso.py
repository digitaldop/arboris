from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("sistema", "0017_sistemadatabaserestorejob"),
    ]

    operations = [
        migrations.AlterField(
            model_name="sistemautentepermessi",
            name="permesso_anagrafica",
            field=models.CharField(
                choices=[
                    ("none", "Nessun accesso"),
                    ("view", "Sola visualizzazione"),
                    ("manage", "Anche gestione"),
                ],
                default="none",
                max_length=10,
            ),
        ),
        migrations.AlterField(
            model_name="sistemautentepermessi",
            name="permesso_calendario",
            field=models.CharField(
                choices=[
                    ("none", "Nessun accesso"),
                    ("view", "Sola visualizzazione"),
                    ("manage", "Anche gestione"),
                ],
                default="none",
                max_length=10,
            ),
        ),
        migrations.AlterField(
            model_name="sistemautentepermessi",
            name="permesso_economia",
            field=models.CharField(
                choices=[
                    ("none", "Nessun accesso"),
                    ("view", "Sola visualizzazione"),
                    ("manage", "Anche gestione"),
                ],
                default="none",
                max_length=10,
            ),
        ),
        migrations.AlterField(
            model_name="sistemautentepermessi",
            name="permesso_gestione_amministrativa",
            field=models.CharField(
                choices=[
                    ("none", "Nessun accesso"),
                    ("view", "Sola visualizzazione"),
                    ("manage", "Anche gestione"),
                ],
                default="none",
                max_length=10,
            ),
        ),
        migrations.AlterField(
            model_name="sistemautentepermessi",
            name="permesso_gestione_finanziaria",
            field=models.CharField(
                choices=[
                    ("none", "Nessun accesso"),
                    ("view", "Sola visualizzazione"),
                    ("manage", "Anche gestione"),
                ],
                default="none",
                max_length=10,
            ),
        ),
        migrations.AlterField(
            model_name="sistemautentepermessi",
            name="permesso_servizi_extra",
            field=models.CharField(
                choices=[
                    ("none", "Nessun accesso"),
                    ("view", "Sola visualizzazione"),
                    ("manage", "Anche gestione"),
                ],
                default="none",
                max_length=10,
            ),
        ),
        migrations.AlterField(
            model_name="sistemautentepermessi",
            name="permesso_sistema",
            field=models.CharField(
                choices=[
                    ("none", "Nessun accesso"),
                    ("view", "Sola visualizzazione"),
                    ("manage", "Anche gestione"),
                ],
                default="none",
                max_length=10,
            ),
        ),
    ]
