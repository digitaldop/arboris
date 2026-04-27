from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("osservazioni", "0001_initial"),
    ]

    operations = [
        migrations.AlterField(
            model_name="osservazionestudente",
            name="titolo",
            field=models.CharField(blank=True, max_length=255, null=True, verbose_name="Titolo"),
        ),
    ]
