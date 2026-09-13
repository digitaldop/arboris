import os
import sys
import time
from pathlib import Path
from wsgiref.simple_server import make_server

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ["DJANGO_SETTINGS_MODULE"] = "arboris.settings"
os.environ["ARBORIS_BACKGROUND_SCHEDULER_ENABLED"] = "0"

import django
from django.conf import settings

settings.DATABASES["default"]["TEST"] = {"NAME": "test_arboris_audit_accessi_ui_20260913"}
settings.DEBUG = True
settings.ALLOWED_HOSTS = ["127.0.0.1", "localhost"]
settings.SESSION_COOKIE_SECURE = False
settings.CSRF_COOKIE_SECURE = False
settings.SECURE_SSL_REDIRECT = False
django.setup()

from django.contrib.auth.models import User
from django.contrib.staticfiles.handlers import StaticFilesHandler
from django.core.wsgi import get_wsgi_application
from django.test import Client
from django.test.runner import DiscoverRunner
from sistema.audit import audit_logging_disabled
from sistema.models import SistemaUtentePermessi

runner = DiscoverRunner(interactive=False, verbosity=0)
config = runner.setup_databases()
try:
    with audit_logging_disabled():
        User.objects.create_superuser(username="audit-demo-admin", password="Local-Audit-Demo-2026")
        user = User.objects.create_user(username="mario.rossi", password="Local-Audit-Demo-2026", first_name="Mario", last_name="Rossi")
        SistemaUtentePermessi.objects.create(user=user, permesso_anagrafica="view")
    client = Client(HTTP_HOST="127.0.0.1")
    client.post("/login/", {"username": "mario.rossi", "password": "Local-Audit-Demo-2026"})
    for path in ("/", "/studenti/", "/famiglie/"):
        client.get(path)
    with make_server("127.0.0.1", 8787, StaticFilesHandler(get_wsgi_application())) as server:
        server.timeout = 0.5
        deadline = time.monotonic() + 600
        print("AUDIT PREVIEW READY http://127.0.0.1:8787/login/", flush=True)
        while time.monotonic() < deadline and not Path(".tmp/audit-preview.stop").exists():
            server.handle_request()
finally:
    runner.teardown_databases(config)
