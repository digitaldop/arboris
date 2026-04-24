from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("anagrafica", "0006_auto_ordini"),
        ("economia", "0001_initial"),
        ("scuola", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="Iscrizione",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("data_preiscrizione", models.DateField(blank=True, null=True)),
                ("data_iscrizione", models.DateField(blank=True, null=True)),
                ("quota_pagante", models.BooleanField(default=True)),
                ("attiva", models.BooleanField(default=True)),
                ("note", models.TextField(blank=True)),
                ("anno_scolastico", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="iscrizioni", to="scuola.annoscolastico")),
                ("classe", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="iscrizioni", to="scuola.classe")),
                ("condizione_iscrizione", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="iscrizioni", to="economia.condizioneiscrizione")),
                ("stato_iscrizione", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="iscrizioni", to="economia.statoiscrizione")),
                ("studente", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="iscrizioni", to="anagrafica.studente")),
                ("tariffa_condizione_iscrizione", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="iscrizioni", to="economia.tariffacondizioneiscrizione")),
            ],
            options={
                "verbose_name": "Iscrizione",
                "verbose_name_plural": "Iscrizioni",
                "db_table": "economia_iscrizione",
                "ordering": ["-anno_scolastico__data_inizio", "studente__cognome", "studente__nome"],
            },
        ),
        migrations.AddConstraint(
            model_name="iscrizione",
            constraint=models.UniqueConstraint(fields=("studente", "anno_scolastico"), name="unique_economia_iscrizione_studente_anno"),
        ),
    ]
