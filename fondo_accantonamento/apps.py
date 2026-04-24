from django.apps import AppConfig


class FondoAccantonamentoConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "fondo_accantonamento"
    verbose_name = "Fondo accantonamento"

    def ready(self):
        # Registra signal per sincronizzazione % rette -> movimenti fondo
        from . import signals  # noqa: F401
