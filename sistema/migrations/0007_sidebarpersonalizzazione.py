from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("sistema", "0006_sistemaimpostazionigenerali_interfaccia_professionale_attiva"),
    ]

    operations = [
        migrations.CreateModel(
            name="SidebarPersonalizzazione",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("config", models.JSONField(blank=True, default=dict)),
                ("data_creazione", models.DateTimeField(auto_now_add=True)),
                ("data_aggiornamento", models.DateTimeField(auto_now=True)),
                (
                    "user",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="sidebar_personalizzazione",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "Personalizzazione sidebar",
                "verbose_name_plural": "Personalizzazioni sidebar",
                "db_table": "sistema_sidebar_personalizzazione",
            },
        ),
    ]
