import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("gestione_amministrativa", "0007_bustapagadipendente_categoria"),
        ("gestione_finanziaria", "0006_documentofornitore_ritenuta_acconto"),
    ]

    operations = [
        migrations.AddField(
            model_name="fornitore",
            name="dipendente_collegato",
            field=models.ForeignKey(
                blank=True,
                help_text="Dipendente, educatore o collaboratore a cui attribuire le fatture di questo fornitore.",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="fornitori_collegati",
                to="gestione_amministrativa.dipendente",
            ),
        ),
    ]
