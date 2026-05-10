from decimal import Decimal

import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("gestione_amministrativa", "0006_simulazionecostodipendente"),
    ]

    operations = [
        migrations.CreateModel(
            name="DatoPayrollUfficiale",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "categoria",
                    models.CharField(
                        choices=[
                            ("fonte", "Fonte informativa"),
                            ("contributi", "Contributi INPS"),
                            ("inail", "INAIL"),
                            ("tfr", "TFR"),
                            ("irpef", "IRPEF"),
                            ("addizionale_regionale", "Addizionale regionale IRPEF"),
                            ("addizionale_comunale", "Addizionale comunale IRPEF"),
                            ("ccnl", "CCNL"),
                            ("altro", "Altro"),
                        ],
                        max_length=40,
                    ),
                ),
                ("codice", models.CharField(max_length=80)),
                ("nome", models.CharField(max_length=180)),
                ("descrizione", models.TextField(blank=True)),
                ("anno", models.PositiveSmallIntegerField(blank=True, db_index=True, null=True)),
                ("valido_dal", models.DateField(blank=True, null=True)),
                ("valido_al", models.DateField(blank=True, null=True)),
                (
                    "valore_percentuale",
                    models.DecimalField(
                        blank=True,
                        decimal_places=4,
                        max_digits=8,
                        null=True,
                        validators=[
                            django.core.validators.MinValueValidator(Decimal("0.00")),
                            django.core.validators.MaxValueValidator(Decimal("1000.00")),
                        ],
                    ),
                ),
                ("valore_importo", models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True)),
                ("valore_testo", models.CharField(blank=True, max_length=255)),
                ("ente", models.CharField(blank=True, max_length=120)),
                ("fonte_url", models.URLField(blank=True, max_length=500)),
                ("data_pubblicazione", models.DateField(blank=True, null=True)),
                ("data_rilevazione", models.DateTimeField(auto_now=True)),
                ("attivo", models.BooleanField(default=True)),
                ("metadata", models.JSONField(blank=True, default=dict)),
            ],
            options={
                "verbose_name": "Dato payroll ufficiale",
                "verbose_name_plural": "Dati payroll ufficiali",
                "db_table": "gestione_amministrativa_dato_payroll_ufficiale",
                "ordering": ["categoria", "-anno", "nome", "codice"],
            },
        ),
        migrations.AddIndex(
            model_name="datopayrollufficiale",
            index=models.Index(fields=["categoria", "anno"], name="ga_payroll_cat_anno_idx"),
        ),
        migrations.AddIndex(
            model_name="datopayrollufficiale",
            index=models.Index(fields=["attivo"], name="ga_payroll_attivo_idx"),
        ),
        migrations.AddConstraint(
            model_name="datopayrollufficiale",
            constraint=models.UniqueConstraint(
                fields=("categoria", "codice", "anno", "valido_dal"),
                name="ga_payroll_dato_unique",
            ),
        ),
    ]
