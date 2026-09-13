import os
import sys
from pathlib import Path
from wsgiref.simple_server import make_server

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))
os.environ['DJANGO_SETTINGS_MODULE'] = 'arboris.settings'
os.environ['ARBORIS_BACKGROUND_SCHEDULER_ENABLED'] = '0'

import django
from django.conf import settings

settings.DATABASES = {'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': ':memory:'}}
settings.ALLOWED_HOSTS = ['127.0.0.1', 'localhost']
settings.DEBUG = True
settings.STORAGES['staticfiles']['BACKEND'] = 'django.contrib.staticfiles.storage.StaticFilesStorage'
django.setup()

from django.core.management import call_command
from django.contrib.auth.models import User
from django.contrib.staticfiles.handlers import StaticFilesHandler
from django.core.wsgi import get_wsgi_application
from anagrafica.models import Familiare, RelazioneFamiliare, Studente, StudenteFamiliare

call_command('migrate', verbosity=0)
User.objects.create_superuser(username='professione-demo', password='Local-demo-2026!')
relazione = RelazioneFamiliare.objects.create(relazione='Genitore', ordine=1)
familiare = Familiare.objects.create(nome='Ada', cognome='Esempio', relazione_familiare=relazione, professione='Architetta')
studente = Studente.objects.create(nome='Luca', cognome='Esempio')
StudenteFamiliare.objects.create(studente=studente, familiare=familiare, relazione_familiare=relazione)
print('PROFESSIONE QA READY http://127.0.0.1:8785/login/', flush=True)
with make_server('127.0.0.1', 8785, StaticFilesHandler(get_wsgi_application())) as server:
    server.timeout = 1
    while not (root / '.tmp' / 'professione_preview.stop').exists():
        server.handle_request()
