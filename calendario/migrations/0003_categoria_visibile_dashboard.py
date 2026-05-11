from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("calendario", "0002_seed_system_categories"),
    ]

    operations = [
        migrations.AddField(
            model_name="categoriacalendario",
            name="visibile_dashboard",
            field=models.BooleanField(
                default=True,
                help_text="Mostra gli eventi di questa categoria nel widget calendario della dashboard.",
            ),
        ),
    ]
