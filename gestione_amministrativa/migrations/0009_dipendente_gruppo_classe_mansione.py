from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("gestione_amministrativa", "0008_dipendente_profili_anagrafici"),
        ("scuola", "0006_alter_classe_options_alter_gruppoclasse_options_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="dipendente",
            name="gruppo_classe_principale",
            field=models.ForeignKey(
                blank=True,
                help_text="Gruppo classe o pluriclasse di riferimento per gli educatori.",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="educatori_principali",
                to="scuola.gruppoclasse",
            ),
        ),
        migrations.AddField(
            model_name="dipendente",
            name="mansione",
            field=models.CharField(blank=True, max_length=160),
        ),
    ]
