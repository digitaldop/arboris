from address_test_settings import *
DATABASES["default"]["NAME"] = "test_arboris_address_preview"
DATABASES["default"]["TEST"]["NAME"] = "test_arboris_address_preview"
GEOAPIFY_API_KEY = ""
MIDDLEWARE = [m for m in MIDDLEWARE if m not in ("sistema.middleware.DatabaseBackupScheduleMiddleware", "gestione_finanziaria.middleware.SincronizzazionePsd2ScheduleMiddleware")]
