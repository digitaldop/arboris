from django.db import migrations, models
import django.db.models.deletion


def backfill_economia_schema(apps, schema_editor):
    StatoIscrizione = apps.get_model("economia", "StatoIscrizione")
    Iscrizione = apps.get_model("economia", "Iscrizione")

    for index, stato in enumerate(StatoIscrizione.objects.order_by("id"), start=1):
        stato.ordine = index
        stato.save(update_fields=["ordine"])

    for iscrizione in Iscrizione.objects.all():
        iscrizione.non_pagante = not getattr(iscrizione, "quota_pagante", True)
        iscrizione.save(update_fields=["non_pagante"])


class Migration(migrations.Migration):
    dependencies = [
        ("economia", "0002_iscrizione"),
    ]

    operations = [
        migrations.CreateModel(
            name="Agevolazione",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("nome_agevolazione", models.CharField(max_length=150, unique=True)),
                ("importo_annuale_agevolazione", models.DecimalField(decimal_places=2, default=0, max_digits=10)),
                ("attiva", models.BooleanField(default=True)),
            ],
            options={
                "verbose_name": "Agevolazione",
                "verbose_name_plural": "Agevolazioni",
                "db_table": "economia_agevolazione",
                "ordering": ["nome_agevolazione"],
            },
        ),
        migrations.AddField(
            model_name="statoiscrizione",
            name="ordine",
            field=models.PositiveIntegerField(blank=True, default=1),
        ),
        migrations.RenameField(
            model_name="condizioneiscrizione",
            old_name="numero_rate",
            new_name="numero_mensilita_default",
        ),
        migrations.RenameField(
            model_name="condizioneiscrizione",
            old_name="ammette_agevolazioni",
            new_name="riduzione_speciale_ammessa",
        ),
        migrations.RenameField(
            model_name="tariffacondizioneiscrizione",
            old_name="ordine_tariffa",
            new_name="ordine_figlio",
        ),
        migrations.RenameField(
            model_name="tariffacondizioneiscrizione",
            old_name="importo_totale",
            new_name="retta_annuale",
        ),
        migrations.RemoveConstraint(
            model_name="tariffacondizioneiscrizione",
            name="unique_economia_tariffa_condizione_iscrizione",
        ),
        migrations.RemoveField(
            model_name="tariffacondizioneiscrizione",
            name="nome_tariffa",
        ),
        migrations.AddField(
            model_name="tariffacondizioneiscrizione",
            name="preiscrizione",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=10),
        ),
        migrations.AddField(
            model_name="iscrizione",
            name="agevolazione",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="iscrizioni", to="economia.agevolazione"),
        ),
        migrations.AddField(
            model_name="iscrizione",
            name="data_fine_iscrizione",
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="iscrizione",
            name="importo_riduzione_speciale",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=10),
        ),
        migrations.AddField(
            model_name="iscrizione",
            name="non_pagante",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="iscrizione",
            name="note_amministrative",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="iscrizione",
            name="riduzione_speciale",
            field=models.BooleanField(default=False),
        ),
        migrations.RunPython(backfill_economia_schema, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name="iscrizione",
            name="data_preiscrizione",
        ),
        migrations.RemoveField(
            model_name="iscrizione",
            name="quota_pagante",
        ),
        migrations.RemoveField(
            model_name="iscrizione",
            name="tariffa_condizione_iscrizione",
        ),
        migrations.CreateModel(
            name="RataIscrizione",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("numero_rata", models.PositiveIntegerField()),
                ("mese_riferimento", models.PositiveIntegerField()),
                ("anno_riferimento", models.PositiveIntegerField()),
                ("descrizione", models.CharField(blank=True, max_length=255)),
                ("importo_dovuto", models.DecimalField(decimal_places=2, max_digits=10)),
                ("data_scadenza", models.DateField(blank=True, null=True)),
                ("pagata", models.BooleanField(default=False)),
                ("importo_pagato", models.DecimalField(decimal_places=2, default=0, max_digits=10)),
                ("data_pagamento", models.DateField(blank=True, null=True)),
                ("credito_applicato", models.DecimalField(decimal_places=2, default=0, max_digits=10)),
                ("altri_sgravi", models.DecimalField(decimal_places=2, default=0, max_digits=10)),
                ("importo_finale", models.DecimalField(decimal_places=2, default=0, max_digits=10)),
                ("note", models.TextField(blank=True)),
                ("famiglia", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="rate_iscrizione", to="anagrafica.famiglia")),
                ("iscrizione", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="rate", to="economia.iscrizione")),
                ("metodo_pagamento", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="rate_iscrizione", to="economia.metodopagamento")),
            ],
            options={
                "verbose_name": "Rata iscrizione",
                "verbose_name_plural": "Rate iscrizione",
                "db_table": "economia_rata_iscrizione",
                "ordering": ["anno_riferimento", "mese_riferimento", "numero_rata"],
            },
        ),
        migrations.CreateModel(
            name="MovimentoCreditoRetta",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("data_movimento", models.DateField()),
                ("importo", models.DecimalField(decimal_places=2, default=0, max_digits=10)),
                ("saldo_progressivo", models.DecimalField(decimal_places=2, default=0, max_digits=10)),
                ("descrizione", models.TextField(blank=True)),
                ("note", models.TextField(blank=True)),
                ("famiglia", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="movimenti_credito_retta", to="anagrafica.famiglia")),
                ("iscrizione", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="movimenti_credito_retta", to="economia.iscrizione")),
                ("rata_iscrizione", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="movimenti_credito_retta", to="economia.rataiscrizione")),
                ("studente", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="movimenti_credito_retta", to="anagrafica.studente")),
                ("tipo_movimento_credito", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="movimenti_credito_retta", to="economia.tipomovimentocredito")),
            ],
            options={
                "verbose_name": "Movimento credito retta",
                "verbose_name_plural": "Movimenti credito retta",
                "db_table": "economia_movimento_credito_retta",
                "ordering": ["data_movimento", "id"],
            },
        ),
        migrations.AlterField(
            model_name="statoiscrizione",
            name="ordine",
            field=models.PositiveIntegerField(blank=True),
        ),
    ]
