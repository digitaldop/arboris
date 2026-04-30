from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("sistema", "0023_sistemaimpostazionigenerali_gestione_iscrizione_corso_anno_and_more"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="sistemaoperazionecronologia",
            index=models.Index(
                fields=["app_label", "model_name", "oggetto_id", "azione", "data_operazione"],
                name="sistema_ope_obj_audit_idx",
            ),
        ),
    ]
