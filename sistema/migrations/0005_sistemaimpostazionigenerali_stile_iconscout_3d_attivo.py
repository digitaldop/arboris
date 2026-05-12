from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("sistema", "0004_sistemaimpostazionigenerali_stile_streamline_attivo"),
    ]

    operations = [
        migrations.AddField(
            model_name="sistemaimpostazionigenerali",
            name="stile_iconscout_3d_attivo",
            field=models.BooleanField(
                default=False,
                help_text=(
                    "Quando attivo usa icone emozionali in stile 3D per dashboard, riepiloghi e intestazioni. "
                    "Se attivo insieme allo Streamline, lo stile 3D ha priorita sulle icone principali."
                ),
            ),
        ),
    ]
