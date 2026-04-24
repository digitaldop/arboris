from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("sistema", "0012_sistemaimpostazionigenerali_font_principale_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="SistemaOperazioneCronologia",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("azione", models.CharField(choices=[("create", "Creazione"), ("update", "Modifica"), ("delete", "Eliminazione")], max_length=20)),
                ("modulo", models.CharField(choices=[("anagrafica", "Anagrafica"), ("economia", "Economia"), ("scuola", "Scuola"), ("calendario", "Calendario"), ("sistema", "Sistema")], default="sistema", max_length=20)),
                ("utente_label", models.CharField(blank=True, max_length=255)),
                ("app_label", models.CharField(max_length=60)),
                ("model_name", models.CharField(max_length=80)),
                ("model_verbose_name", models.CharField(max_length=120)),
                ("oggetto_id", models.CharField(blank=True, max_length=64)),
                ("oggetto_label", models.CharField(blank=True, max_length=255)),
                ("descrizione", models.TextField()),
                ("campi_coinvolti", models.JSONField(blank=True, default=list)),
                ("data_operazione", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("utente", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="operazioni_cronologia", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "verbose_name": "Operazione cronologia",
                "verbose_name_plural": "Cronologia operazioni",
                "db_table": "sistema_operazione_cronologia",
                "ordering": ["-data_operazione", "-id"],
            },
        ),
        migrations.AddIndex(
            model_name="sistemaoperazionecronologia",
            index=models.Index(fields=["azione"], name="sistema_ope_azione_aecbff_idx"),
        ),
        migrations.AddIndex(
            model_name="sistemaoperazionecronologia",
            index=models.Index(fields=["modulo"], name="sistema_ope_modulo_642ec3_idx"),
        ),
    ]
