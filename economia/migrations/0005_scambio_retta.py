from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("anagrafica", "0006_auto_ordini"),
        ("scuola", "0001_initial"),
        ("economia", "0004_alter_condizioneiscrizione_options_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="TariffaScambioRetta",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("valore_orario", models.DecimalField(decimal_places=2, max_digits=10)),
                ("definizione", models.CharField(blank=True, max_length=150)),
                ("note", models.TextField(blank=True)),
            ],
            options={
                "verbose_name": "Tariffa scambio retta",
                "verbose_name_plural": "Tariffe scambio retta",
                "db_table": "economia_tariffa_scambio_retta",
                "ordering": ["valore_orario", "definizione", "id"],
            },
        ),
        migrations.CreateModel(
            name="ScambioRetta",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("mese_riferimento", models.PositiveSmallIntegerField()),
                ("descrizione", models.TextField(blank=True)),
                ("ore_lavorate", models.DecimalField(decimal_places=2, max_digits=8)),
                ("importo_maturato", models.DecimalField(decimal_places=2, default=0, max_digits=10)),
                ("approvata", models.BooleanField(default=False)),
                ("contabilizzata", models.BooleanField(default=False)),
                ("note", models.TextField(blank=True)),
                ("anno_scolastico", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="scambi_retta", to="scuola.annoscolastico")),
                ("famiglia", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="scambi_retta", to="anagrafica.famiglia")),
                ("familiare", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="scambi_retta", to="anagrafica.familiare")),
                ("studente", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="scambi_retta", to="anagrafica.studente")),
                ("tariffa_scambio_retta", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="scambi_retta", to="economia.tariffascambioretta")),
            ],
            options={
                "verbose_name": "Scambio retta",
                "verbose_name_plural": "Scambi retta",
                "db_table": "economia_scambio_retta",
                "ordering": ["-anno_scolastico__data_inizio", "-mese_riferimento", "famiglia__cognome_famiglia", "studente__cognome"],
            },
        ),
    ]
