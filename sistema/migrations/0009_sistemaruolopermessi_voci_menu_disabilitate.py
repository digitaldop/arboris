from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("sistema", "0008_configurazioneemailsmtp_comunicazionefamiglialog"),
    ]

    operations = [
        migrations.AddField(
            model_name="sistemaruolopermessi",
            name="voci_menu_disabilitate",
            field=models.JSONField(blank=True, default=list),
        ),
    ]
