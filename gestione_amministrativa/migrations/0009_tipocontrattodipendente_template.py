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
