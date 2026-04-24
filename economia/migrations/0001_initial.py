from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("scuola", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="MetodoPagamento",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("metodo_pagamento", models.CharField(max_length=100, unique=True)),
                ("attivo", models.BooleanField(default=True)),
                ("note", models.TextField(blank=True)),
            ],
            options={
                "verbose_name": "Metodo pagamento",
                "verbose_name_plural": "Metodi pagamento",
                "db_table": "economia_metodo_pagamento",
                "ordering": ["metodo_pagamento"],
            },
        ),
        migrations.CreateModel(
            name="TipoMovimentoCredito",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("tipo_movimento_credito", models.CharField(max_length=100, unique=True)),
                ("attivo", models.BooleanField(default=True)),
                ("note", models.TextField(blank=True)),
            ],
            options={
                "verbose_name": "Tipo movimento credito",
                "verbose_name_plural": "Tipi movimento credito",
                "db_table": "economia_tipo_movimento_credito",
                "ordering": ["tipo_movimento_credito"],
            },
        ),
        migrations.CreateModel(
            name="StatoIscrizione",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("stato_iscrizione", models.CharField(max_length=100, unique=True)),
                ("attivo", models.BooleanField(default=True)),
                ("note", models.TextField(blank=True)),
            ],
            options={
                "verbose_name": "Stato iscrizione",
                "verbose_name_plural": "Stati iscrizione",
                "db_table": "economia_stato_iscrizione",
                "ordering": ["stato_iscrizione"],
            },
        ),
        migrations.CreateModel(
            name="CondizioneIscrizione",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("nome_condizione_iscrizione", models.CharField(max_length=150)),
                ("numero_rate", models.PositiveIntegerField()),
                ("ammette_agevolazioni", models.BooleanField(default=False)),
                ("attiva", models.BooleanField(default=True)),
                ("note", models.TextField(blank=True)),
                ("anno_scolastico", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="condizioni_iscrizione", to="scuola.annoscolastico")),
            ],
            options={
                "verbose_name": "Condizione iscrizione",
                "verbose_name_plural": "Condizioni iscrizione",
                "db_table": "economia_condizione_iscrizione",
                "ordering": ["anno_scolastico__data_inizio", "nome_condizione_iscrizione"],
            },
        ),
        migrations.CreateModel(
            name="TariffaCondizioneIscrizione",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("nome_tariffa", models.CharField(max_length=150)),
                ("ordine_tariffa", models.PositiveIntegerField(default=1)),
                ("importo_totale", models.DecimalField(decimal_places=2, max_digits=10)),
                ("attiva", models.BooleanField(default=True)),
                ("note", models.TextField(blank=True)),
                ("condizione_iscrizione", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="tariffe", to="economia.condizioneiscrizione")),
            ],
            options={
                "verbose_name": "Tariffa condizione iscrizione",
                "verbose_name_plural": "Tariffe condizione iscrizione",
                "db_table": "economia_tariffa_condizione_iscrizione",
                "ordering": ["condizione_iscrizione", "ordine_tariffa", "nome_tariffa"],
            },
        ),
        migrations.AddConstraint(
            model_name="condizioneiscrizione",
            constraint=models.UniqueConstraint(fields=("anno_scolastico", "nome_condizione_iscrizione"), name="unique_economia_condizione_iscrizione_per_anno"),
        ),
        migrations.AddConstraint(
            model_name="tariffacondizioneiscrizione",
            constraint=models.UniqueConstraint(fields=("condizione_iscrizione", "nome_tariffa"), name="unique_economia_tariffa_condizione_iscrizione"),
        ),
    ]
