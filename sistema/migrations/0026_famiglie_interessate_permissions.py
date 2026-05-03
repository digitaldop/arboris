# Generated manually for Arboris.

from django.db import migrations, models


def assign_default_interested_family_permissions(apps, _schema_editor):
    SistemaRuoloPermessi = apps.get_model("sistema", "SistemaRuoloPermessi")
    SistemaUtentePermessi = apps.get_model("sistema", "SistemaUtentePermessi")

    manage_roles = {
        "amministratore",
        "segreteria_amministrativa",
        "segreteria_didattica",
    }
    view_roles = {
        "membro_cda",
        "visualizzatore",
    }

    for ruolo in SistemaRuoloPermessi.objects.all():
        if ruolo.controllo_completo or ruolo.chiave_legacy in manage_roles:
            ruolo.permesso_famiglie_interessate = "manage"
        elif ruolo.chiave_legacy in view_roles:
            ruolo.permesso_famiglie_interessate = "view"
        else:
            ruolo.permesso_famiglie_interessate = "none"
        ruolo.save(update_fields=["permesso_famiglie_interessate"])

    for profilo in SistemaUtentePermessi.objects.select_related("ruolo_permessi"):
        if profilo.ruolo_permessi_id:
            profilo.permesso_famiglie_interessate = profilo.ruolo_permessi.permesso_famiglie_interessate
        elif profilo.controllo_completo or profilo.ruolo in manage_roles:
            profilo.permesso_famiglie_interessate = "manage"
        elif profilo.ruolo in view_roles:
            profilo.permesso_famiglie_interessate = "view"
        else:
            profilo.permesso_famiglie_interessate = "none"
        profilo.save(update_fields=["permesso_famiglie_interessate"])


class Migration(migrations.Migration):

    dependencies = [
        ("sistema", "0025_feedbacksegnalazione"),
    ]

    operations = [
        migrations.AddField(
            model_name="sistemaruolopermessi",
            name="permesso_famiglie_interessate",
            field=models.CharField(
                choices=[
                    ("none", "Nessun accesso"),
                    ("view", "Sola visualizzazione"),
                    ("manage", "Anche gestione"),
                ],
                default="none",
                max_length=10,
            ),
        ),
        migrations.AddField(
            model_name="sistemautentepermessi",
            name="permesso_famiglie_interessate",
            field=models.CharField(
                choices=[
                    ("none", "Nessun accesso"),
                    ("view", "Sola visualizzazione"),
                    ("manage", "Anche gestione"),
                ],
                default="none",
                max_length=10,
            ),
        ),
        migrations.RunPython(assign_default_interested_family_permissions, migrations.RunPython.noop),
    ]
