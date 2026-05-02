from django.db import migrations, models
import django.db.models.deletion


def migra_categorie_spesa(apps, schema_editor):
    CategoriaSpesa = apps.get_model("gestione_finanziaria", "CategoriaSpesa")
    CategoriaFinanziaria = apps.get_model("gestione_finanziaria", "CategoriaFinanziaria")
    Fornitore = apps.get_model("gestione_finanziaria", "Fornitore")
    DocumentoFornitore = apps.get_model("gestione_finanziaria", "DocumentoFornitore")

    for categoria_spesa in CategoriaSpesa.objects.all().order_by("ordine", "nome", "id"):
        categoria_finanziaria = (
            CategoriaFinanziaria.objects.filter(
                nome=categoria_spesa.nome,
                parent__isnull=True,
                tipo="spesa",
            )
            .order_by("id")
            .first()
        )
        if categoria_finanziaria is None:
            categoria_finanziaria = CategoriaFinanziaria.objects.create(
                nome=categoria_spesa.nome,
                tipo="spesa",
                parent=None,
                ordine=categoria_spesa.ordine,
                attiva=categoria_spesa.attiva,
                note=categoria_spesa.descrizione,
            )
        else:
            changed = []
            if not categoria_finanziaria.note and categoria_spesa.descrizione:
                categoria_finanziaria.note = categoria_spesa.descrizione
                changed.append("note")
            if categoria_finanziaria.ordine is None and categoria_spesa.ordine is not None:
                categoria_finanziaria.ordine = categoria_spesa.ordine
                changed.append("ordine")
            if changed:
                categoria_finanziaria.save(update_fields=changed)

        Fornitore.objects.filter(categoria_spesa_id=categoria_spesa.pk).update(
            categoria_finanziaria_tmp_id=categoria_finanziaria.pk
        )
        DocumentoFornitore.objects.filter(categoria_spesa_id=categoria_spesa.pk).update(
            categoria_finanziaria_tmp_id=categoria_finanziaria.pk
        )


class Migration(migrations.Migration):
    dependencies = [
        ("gestione_finanziaria", "0020_alter_documentofornitore_external_url"),
    ]

    operations = [
        migrations.AddField(
            model_name="fornitore",
            name="categoria_finanziaria_tmp",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="+",
                to="gestione_finanziaria.categoriafinanziaria",
            ),
        ),
        migrations.AddField(
            model_name="documentofornitore",
            name="categoria_finanziaria_tmp",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="+",
                to="gestione_finanziaria.categoriafinanziaria",
            ),
        ),
        migrations.RunPython(migra_categorie_spesa, migrations.RunPython.noop),
        migrations.RemoveIndex(
            model_name="documentofornitore",
            name="gf_doc_catsp_data_idx",
        ),
        migrations.RemoveField(
            model_name="documentofornitore",
            name="categoria_spesa",
        ),
        migrations.RemoveField(
            model_name="fornitore",
            name="categoria_spesa",
        ),
        migrations.RenameField(
            model_name="documentofornitore",
            old_name="categoria_finanziaria_tmp",
            new_name="categoria_spesa",
        ),
        migrations.RenameField(
            model_name="fornitore",
            old_name="categoria_finanziaria_tmp",
            new_name="categoria_spesa",
        ),
        migrations.AlterField(
            model_name="fornitore",
            name="categoria_spesa",
            field=models.ForeignKey(
                blank=True,
                help_text="Categoria prevalente usata come default sui documenti del fornitore.",
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="fornitori",
                to="gestione_finanziaria.categoriafinanziaria",
            ),
        ),
        migrations.AlterField(
            model_name="documentofornitore",
            name="categoria_spesa",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="documenti_fornitori",
                to="gestione_finanziaria.categoriafinanziaria",
            ),
        ),
        migrations.AddIndex(
            model_name="documentofornitore",
            index=models.Index(fields=["categoria_spesa", "data_documento"], name="gf_doc_catsp_data_idx"),
        ),
        migrations.DeleteModel(
            name="CategoriaSpesa",
        ),
    ]
