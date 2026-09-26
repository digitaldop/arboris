from django.db import migrations, models


def migrate_hidden_pages(apps, schema_editor):
    Role = apps.get_model("sistema", "SistemaRuoloPermessi")
    for role in Role.objects.using(schema_editor.connection.alias).all().iterator():
        role.permessi_pagine = {
            ("gestione_amministrativa_dipendenti" if key == "anagrafica_dipendenti" else key): "none"
            for key in (role.voci_menu_disabilitate or [])
        }
        role.save(update_fields=["permessi_pagine"])


class Migration(migrations.Migration):
    dependencies = [("sistema", "0012_accesso_comunicazioni_famiglie")]
    operations = [
        migrations.AddField(
            model_name="sistemaruolopermessi", name="permessi_pagine",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.RunPython(migrate_hidden_pages, migrations.RunPython.noop),
    ]
