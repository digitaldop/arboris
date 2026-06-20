from decimal import Decimal

from django.db import migrations, models
import django.db.models.deletion


def crea_pagamenti_da_collegamenti_esistenti(apps, schema_editor):
    BustaPagaDipendente = apps.get_model("gestione_amministrativa", "BustaPagaDipendente")
    PagamentoBustaPagaDipendente = apps.get_model("gestione_amministrativa", "PagamentoBustaPagaDipendente")

    for busta in BustaPagaDipendente.objects.filter(movimento_pagamento_id__isnull=False):
        importo = busta.netto_effettivo or busta.netto_previsto or Decimal("0.00")
        if importo <= Decimal("0.00"):
            continue
        data_pagamento = busta.data_pagamento_effettiva or busta.data_aggiornamento.date()
        PagamentoBustaPagaDipendente.objects.get_or_create(
            busta_paga_id=busta.pk,
            movimento_id=busta.movimento_pagamento_id,
            defaults={
                "importo": abs(importo),
                "data_pagamento": data_pagamento,
                "note": "Pagamento migrato da collegamento busta paga",
            },
        )


def rimuovi_pagamenti_migrati(apps, schema_editor):
    PagamentoBustaPagaDipendente = apps.get_model("gestione_amministrativa", "PagamentoBustaPagaDipendente")
    PagamentoBustaPagaDipendente.objects.filter(note="Pagamento migrato da collegamento busta paga").delete()


class Migration(migrations.Migration):

    dependencies = [
        ("gestione_amministrativa", "0007_bustapagadipendente_categoria"),
        ("gestione_finanziaria", "0010_documentofornitore_compensazione"),
    ]

    operations = [
        migrations.CreateModel(
            name="PagamentoBustaPagaDipendente",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("importo", models.DecimalField(decimal_places=2, max_digits=12)),
                ("data_pagamento", models.DateField()),
                ("note", models.TextField(blank=True)),
                ("data_creazione", models.DateTimeField(auto_now_add=True)),
                ("data_aggiornamento", models.DateTimeField(auto_now=True)),
                (
                    "busta_paga",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="pagamenti",
                        to="gestione_amministrativa.bustapagadipendente",
                    ),
                ),
                (
                    "movimento",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="pagamenti_buste_paga",
                        to="gestione_finanziaria.movimentofinanziario",
                    ),
                ),
            ],
            options={
                "verbose_name": "Pagamento busta paga",
                "verbose_name_plural": "Pagamenti buste paga",
                "db_table": "gestione_amministrativa_pagamento_busta_paga",
                "ordering": ["-data_pagamento", "-id"],
            },
        ),
        migrations.AddIndex(
            model_name="pagamentobustapagadipendente",
            index=models.Index(fields=["busta_paga", "data_pagamento"], name="ga_pag_busta_data_idx"),
        ),
        migrations.AddIndex(
            model_name="pagamentobustapagadipendente",
            index=models.Index(fields=["movimento"], name="ga_pag_busta_mov_idx"),
        ),
        migrations.AddConstraint(
            model_name="pagamentobustapagadipendente",
            constraint=models.UniqueConstraint(
                condition=models.Q(("movimento__isnull", False)),
                fields=("busta_paga", "movimento"),
                name="ga_pag_busta_unique_movimento",
            ),
        ),
        migrations.AddConstraint(
            model_name="pagamentobustapagadipendente",
            constraint=models.CheckConstraint(
                condition=models.Q(("importo__gt", Decimal("0.00"))),
                name="ga_pag_busta_importo_pos",
            ),
        ),
        migrations.RunPython(crea_pagamenti_da_collegamenti_esistenti, rimuovi_pagamenti_migrati),
    ]
