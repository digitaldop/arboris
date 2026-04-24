from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="AnnoScolastico",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("nome_anno_scolastico", models.CharField(max_length=50, unique=True)),
                ("data_inizio", models.DateField()),
                ("data_fine", models.DateField()),
                ("corrente", models.BooleanField(default=False)),
                ("attivo", models.BooleanField(default=True)),
                ("note", models.TextField(blank=True)),
            ],
            options={
                "verbose_name": "Anno scolastico",
                "verbose_name_plural": "Anni scolastici",
                "db_table": "scuola_anno_scolastico",
                "ordering": ["-data_inizio", "-id"],
            },
        ),
        migrations.CreateModel(
            name="Classe",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("nome_classe", models.CharField(max_length=100)),
                ("sezione_classe", models.CharField(blank=True, max_length=20)),
                ("ordine_classe", models.PositiveIntegerField()),
                ("attiva", models.BooleanField(default=True)),
                ("note", models.TextField(blank=True)),
                ("anno_scolastico", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="classi", to="scuola.annoscolastico")),
            ],
            options={
                "verbose_name": "Classe",
                "verbose_name_plural": "Classi",
                "db_table": "scuola_classe",
                "ordering": ["anno_scolastico__data_inizio", "ordine_classe", "nome_classe", "sezione_classe"],
            },
        ),
        migrations.AddConstraint(
            model_name="classe",
            constraint=models.UniqueConstraint(fields=("anno_scolastico", "nome_classe", "sezione_classe"), name="unique_scuola_classe_per_anno"),
        ),
    ]
