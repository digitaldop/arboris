from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("sistema", "0005_sistemaimpostazionigenerali_stile_iconscout_3d_attivo"),
    ]

    operations = [
        migrations.AddField(
            model_name="sistemaimpostazionigenerali",
            name="interfaccia_professionale_attiva",
            field=models.BooleanField(
                default=False,
                help_text=(
                    "Quando attiva applica un layout piu SaaS e professionale: sidebar lineare, "
                    "tabelle piu compatte, card meno arrotondate e spaziature piu operative."
                ),
            ),
        ),
    ]
