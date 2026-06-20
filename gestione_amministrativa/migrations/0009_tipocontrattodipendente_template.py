from decimal import Decimal

import django.core.validators
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("gestione_amministrativa", "0008_pagamentobustapagadipendente"),
    ]

    operations = [
        migrations.AddField(
            model_name="tipocontrattodipendente",
            name="parametro_calcolo",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="tipi_contratto",
                to="gestione_amministrativa.parametrocalcolostipendio",
            ),
        ),
        migrations.AddField(
            model_name="tipocontrattodipendente",
            name="ccnl",
            field=models.CharField(blank=True, max_length=120),
        ),
        migrations.AddField(
            model_name="tipocontrattodipendente",
            name="livello",
            field=models.CharField(blank=True, max_length=60),
        ),
        migrations.AddField(
            model_name="tipocontrattodipendente",
            name="qualifica",
            field=models.CharField(blank=True, max_length=120),
        ),
        migrations.AddField(
            model_name="tipocontrattodipendente",
            name="mansione",
            field=models.CharField(blank=True, max_length=160),
        ),
        migrations.AddField(
            model_name="tipocontrattodipendente",
            name="regime_orario",
            field=models.CharField(
                blank=True,
                choices=[("tempo_pieno", "Tempo pieno"), ("tempo_parziale", "Part-time")],
                default="tempo_pieno",
                max_length=30,
            ),
        ),
        migrations.AddField(
            model_name="tipocontrattodipendente",
            name="ore_settimanali",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                default=Decimal("0.00"),
                max_digits=5,
                validators=[django.core.validators.MinValueValidator(Decimal("0.00"))],
            ),
        ),
        migrations.AddField(
            model_name="tipocontrattodipendente",
            name="percentuale_part_time",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                default=Decimal("100.00"),
                max_digits=5,
                validators=[
                    django.core.validators.MinValueValidator(Decimal("0.00")),
                    django.core.validators.MaxValueValidator(Decimal("100.00")),
                ],
            ),
        ),
        migrations.AddField(
            model_name="tipocontrattodipendente",
            name="retribuzione_lorda_mensile",
            field=models.DecimalField(blank=True, decimal_places=2, default=Decimal("0.00"), max_digits=12),
        ),
        migrations.AddField(
            model_name="tipocontrattodipendente",
            name="tariffa_oraria",
            field=models.DecimalField(blank=True, decimal_places=2, default=Decimal("0.00"), max_digits=12),
        ),
        migrations.AddField(
            model_name="tipocontrattodipendente",
            name="superminimo_mensile",
            field=models.DecimalField(blank=True, decimal_places=2, default=Decimal("0.00"), max_digits=12),
        ),
        migrations.AddField(
            model_name="tipocontrattodipendente",
            name="indennita_fisse_mensili",
            field=models.DecimalField(blank=True, decimal_places=2, default=Decimal("0.00"), max_digits=12),
        ),
        migrations.AddField(
            model_name="tipocontrattodipendente",
            name="mensilita_annue",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                default=Decimal("13.00"),
                max_digits=4,
                validators=[django.core.validators.MinValueValidator(Decimal("1.00"))],
            ),
        ),
        migrations.AddField(
            model_name="tipocontrattodipendente",
            name="costo_azienda_ipotizzato",
            field=models.DecimalField(blank=True, decimal_places=2, default=Decimal("0.00"), max_digits=12),
        ),
        migrations.AddField(
            model_name="tipocontrattodipendente",
            name="lordo_ipotizzato",
            field=models.DecimalField(blank=True, decimal_places=2, default=Decimal("0.00"), max_digits=12),
        ),
        migrations.AddField(
            model_name="tipocontrattodipendente",
            name="netto_ipotizzato",
            field=models.DecimalField(blank=True, decimal_places=2, default=Decimal("0.00"), max_digits=12),
        ),
        migrations.AddField(
            model_name="tipocontrattodipendente",
            name="contributi_mensili_ipotizzati",
            field=models.DecimalField(blank=True, decimal_places=2, default=Decimal("0.00"), max_digits=12),
        ),
        migrations.AddField(
            model_name="tipocontrattodipendente",
            name="valuta",
            field=models.CharField(blank=True, default="EUR", max_length=3),
        ),
    ]
