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
settings.ALLOWED_HOSTS = ['127.0.0.1', 'localhost', 'testserver']
settings.DEBUG = True
settings.STORAGES['staticfiles']['BACKEND'] = 'django.contrib.staticfiles.storage.StaticFilesStorage'
django.setup()

from django.core.management import call_command
from django.contrib.auth.models import User
from django.contrib.staticfiles.handlers import StaticFilesHandler
from django.core.wsgi import get_wsgi_application
from django.urls import reverse
from anagrafica.models import Familiare, RelazioneFamiliare, Studente, StudenteFamiliare

call_command('migrate', verbosity=0)
User.objects.create_superuser(username='avatar-demo', password='Local-avatar-demo-2026!')
father = RelazioneFamiliare.objects.create(relazione='Padre', ordine=1)
RelazioneFamiliare.objects.create(relazione='Madre', ordine=2)
relative = Familiare.objects.create(nome='Marco', cognome='Esempio', sesso='M', relazione_familiare=father)
student = Studente.objects.create(nome='Luca', cognome='Esempio', sesso='M')
StudenteFamiliare.objects.create(studente=student, familiare=relative, relazione_familiare=father)
print('AVATAR QA READY http://127.0.0.1:8786/login/', flush=True)
for name in ['crea_familiare', 'crea_studente', 'lista_famiglie']:
    print(name, reverse(name), flush=True)
print('familiare', reverse('modifica_familiare', args=[relative.pk]), flush=True)
print('studente', reverse('modifica_studente', args=[student.pk]), flush=True)
with make_server('127.0.0.1', 8786, StaticFilesHandler(get_wsgi_application())) as server:
    server.serve_forever()
