import os
import sys
from pathlib import Path
from wsgiref.simple_server import make_server

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ['DJANGO_SETTINGS_MODULE'] = 'arboris.settings'
os.environ['ARBORIS_BACKGROUND_SCHEDULER_ENABLED'] = '0'

import django
from django.conf import settings

settings.DATABASES['default']['TEST'] = {'NAME': 'test_arboris_log_ui'}
settings.DEBUG = True
settings.ALLOWED_HOSTS = ['127.0.0.1', 'localhost']
settings.SESSION_COOKIE_SECURE = False
settings.CSRF_COOKIE_SECURE = False
settings.SECURE_SSL_REDIRECT = False
django.setup()

from django.contrib.auth.models import User
from django.contrib.staticfiles.handlers import StaticFilesHandler
from django.core.wsgi import get_wsgi_application
from django.db import connection
from django.db.migrations.recorder import MigrationRecorder
from django.test.runner import DiscoverRunner
from gestione_finanziaria.models import NotificaFinanziaria
from sistema.audit import audit_logging_disabled
from sistema.log_notifiche import riepilogo_log
from sistema.models import SistemaOperazioneCronologia, SistemaUtentePermessi

runner = DiscoverRunner(interactive=False, verbosity=0)
with audit_logging_disabled():
    old_config = runner.setup_databases()
try:
    assert connection.settings_dict['NAME'] == 'test_arboris_log_ui'
    assert MigrationRecorder.Migration.objects.filter(app='sistema', name='0010_log_operazioni_letture').exists()
    print('MIGRATION 0010 APPLIED ON ISOLATED TEST DATABASE', flush=True)
    with audit_logging_disabled():
        admin = User.objects.create_superuser(username='log-collaudo', password='Local-only-Log-2026')
        actor = User.objects.create_user(username='operatore-collaudo', first_name='Operatore', last_name='Prova')
        SistemaUtentePermessi.objects.create(user=actor)
    riepilogo_log(admin)
    for index in range(8):
        SistemaOperazioneCronologia.objects.create(
            utente=actor, utente_label='Operatore Prova', azione='update',
            modulo='gestione_finanziaria', app_label='gestione_finanziaria', model_name='fornitore',
            model_verbose_name='fornitore', oggetto_label=f'Fornitore dimostrativo {index + 1}',
            descrizione=f'Aggiornati i dati del fornitore dimostrativo {index + 1}. '
                'La descrizione comprende tutti i dettagli della modifica effettuata dall’operatore, '
                'compreso l’indirizzo amministrativo e il riferimento usato per la riconciliazione dei pagamenti.',
            campi_coinvolti=['denominazione', 'indirizzo'],
        )
    with audit_logging_disabled():
        for index in range(2):
            NotificaFinanziaria.objects.create(titolo=f'Fattura dimostrativa {index + 1}', messaggio='Avviso finanziario per verifica conteggi separati.')
    print('LOG QA READY http://127.0.0.1:8784/login/', flush=True)
    with make_server('127.0.0.1', 8784, StaticFilesHandler(get_wsgi_application())) as server:
        server.serve_forever()
finally:
    runner.teardown_databases(old_config)
