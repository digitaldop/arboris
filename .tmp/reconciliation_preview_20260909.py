import os
import sys
from pathlib import Path
from datetime import date
from decimal import Decimal
from wsgiref.simple_server import make_server

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ['DJANGO_SETTINGS_MODULE'] = 'arboris.settings'
os.environ['ARBORIS_BACKGROUND_SCHEDULER_ENABLED'] = '0'
import django
from django.conf import settings
settings.DATABASES['default']['TEST'] = {'NAME': 'test_arboris_matching_ui_20260909'}
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
from django.test.runner import DiscoverRunner
from django.urls import reverse
from sistema.audit import audit_logging_disabled
from gestione_finanziaria.test_matching_approssimato import RetteMatchingApprossimatoTests, FornitoriMatchingApprossimatoTests
from gestione_finanziaria.models import MovimentoFinanziario

runner = DiscoverRunner(interactive=False, verbosity=0)
old_config = runner.setup_databases()
try:
    assert connection.settings_dict['NAME'] == 'test_arboris_matching_ui_20260909'
    with audit_logging_disabled():
        User.objects.create_superuser(username='matching-collaudo', password='Local-only-Matching-2026')
        RetteMatchingApprossimatoTests.setUpTestData()
        test = RetteMatchingApprossimatoTests()
        rata, movimento = test.caso()
        MovimentoFinanziario.objects.create(data_contabile=rata.data_scadenza, importo=100, descrizione='Retta LUCE SOPHIA NERI')
        MovimentoFinanziario.objects.create(data_contabile=date(2026, 8, 15), importo=45, descrizione='Acconto LUCE SOPHI A')
        scadenza, uscita = FornitoriMatchingApprossimatoTests().caso()
        MovimentoFinanziario.objects.create(data_contabile=scadenza.data_scadenza, importo=-500, controparte='Artan Gjata', descrizione='Saldo fattura')
    for name, pk in [('riconcilia_rata_iscrizione', rata.pk), ('riconcilia_movimento', movimento.pk), ('registra_pagamento_scadenza_fornitore', scadenza.pk), ('riconcilia_movimento', uscita.pk)]:
        print('PREVIEW http://127.0.0.1:8785' + reverse(name, args=[pk]), flush=True)
    with make_server('127.0.0.1', 8785, StaticFilesHandler(get_wsgi_application())) as server:
        server.serve_forever()
finally:
    runner.teardown_databases(old_config)
