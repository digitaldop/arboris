from django.db import migrations, models
import django.db.models.deletion


def backfill_import_aliases(apps, schema_editor):
    DocumentoFornitore = apps.get_model("gestione_finanziaria", "DocumentoFornitore")
    DocumentoFornitoreImportAlias = apps.get_model("gestione_finanziaria", "DocumentoFornitoreImportAlias")
    for documento in (
        DocumentoFornitore.objects.exclude(external_source="")
        .exclude(external_id="")
        .only("id", "external_source", "external_id")
        .iterator()
    ):
        DocumentoFornitoreImportAlias.objects.get_or_create(
            external_source=documento.external_source,
            external_id=documento.external_id,
            defaults={
                "documento_id": documento.id,
                "ignorato": False,
                "motivo": "backfill_migrazione",
            },
        )


class Migration(migrations.Migration):

    dependencies = [
        ("gestione_finanziaria", "0008_documentofornitore_descrizione_righe_fattura"),
    ]

    operations = [
        migrations.CreateModel(
            name="DocumentoFornitoreImportAlias",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("external_source", models.CharField(db_index=True, max_length=60)),
                ("external_id", models.CharField(db_index=True, max_length=120)),
                ("ignorato", models.BooleanField(db_index=True, default=False)),
                ("motivo", models.CharField(blank=True, max_length=120)),
                ("data_creazione", models.DateTimeField(auto_now_add=True)),
                ("data_aggiornamento", models.DateTimeField(auto_now=True)),
                (
                    "documento",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="import_aliases",
                        to="gestione_finanziaria.documentofornitore",
                    ),
                ),
            ],
            options={
                "verbose_name": "Alias import documento fornitore",
                "verbose_name_plural": "Alias import documenti fornitori",
                "db_table": "gestione_finanziaria_documento_fornitore_import_alias",
                "ordering": ["external_source", "external_id"],
            },
        ),
        migrations.AddConstraint(
            model_name="documentofornitoreimportalias",
            constraint=models.UniqueConstraint(
                fields=("external_source", "external_id"),
                name="gf_doc_forn_import_alias_unique",
            ),
        ),
        migrations.RunPython(backfill_import_aliases, migrations.RunPython.noop),
    ]
