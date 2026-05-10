from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("anagrafica", "0012_nazione_nome_nazionalita_belfiore_unique"),
        ("gestione_amministrativa", "0007_dato_payroll_ufficiale"),
        ("scuola", "0006_alter_classe_options_alter_gruppoclasse_options_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="dipendente",
            name="ruolo_anagrafico",
            field=models.CharField(
                choices=[
                    ("dipendente", "Dipendente"),
                    ("educatore", "Educatore"),
                    ("educatore_dipendente", "Educatore e dipendente"),
                ],
                db_index=True,
                default="dipendente",
                max_length=30,
            ),
        ),
        migrations.AddField(
            model_name="dipendente",
            name="familiare_collegato",
            field=models.OneToOneField(
                blank=True,
                help_text="Collega un familiare esistente quando la stessa persona e anche dipendente o educatore.",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="profilo_lavorativo",
                to="anagrafica.familiare",
            ),
        ),
        migrations.AddField(
            model_name="dipendente",
            name="classe_principale",
            field=models.ForeignKey(
                blank=True,
                help_text="Classe di riferimento per gli educatori.",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="educatori_principali",
                to="scuola.classe",
            ),
        ),
    ]
