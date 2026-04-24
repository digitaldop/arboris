import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("sistema", "0016_sistemautentepermessi_permesso_gestione_amministrativa_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="SistemaDatabaseRestoreJob",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("stato", models.CharField(
                    choices=[
                        ("in_attesa_conferma", "In attesa di conferma"),
                        ("in_coda", "In coda"),
                        ("in_corso", "In corso"),
                        ("completato", "Completato"),
                        ("errore", "Errore"),
                        ("annullato", "Annullato"),
                    ],
                    default="in_attesa_conferma",
                    max_length=32,
                )),
                ("percorso_file", models.TextField(help_text="Percorso assoluto del file in attesa o appena usato per il restore.")),
                ("nome_file_originale", models.CharField(max_length=400)),
                ("dimensione_file_bytes", models.BigIntegerField(default=0)),
                ("data_creazione", models.DateTimeField(auto_now_add=True)),
                ("data_avvio_ripristino", models.DateTimeField(blank=True, null=True)),
                ("data_completamento", models.DateTimeField(blank=True, null=True)),
                ("messaggio_errore", models.TextField(blank=True)),
                ("celery_task_id", models.CharField(blank=True, max_length=120)),
                ("backup_sicurezza", models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name="ripristino_job_collegato",
                    to="sistema.sistemandatabasebackup",
                )),
                ("creato_da", models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name="ripristini_database",
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                "verbose_name": "Job ripristino database",
                "verbose_name_plural": "Job ripristino database",
                "db_table": "sistema_database_restore_job",
                "ordering": ["-data_creazione", "-id"],
            },
        ),
    ]
