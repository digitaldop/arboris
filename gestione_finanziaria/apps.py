from django.apps import AppConfig


class GestioneFinanziariaConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "gestione_finanziaria"
    verbose_name = "Gestione finanziaria"

    def ready(self) -> None:
        from . import signals  # noqa: F401 - registra post_migrate
