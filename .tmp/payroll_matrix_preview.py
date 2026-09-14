import os
import sys
from datetime import date
from pathlib import Path
from wsgiref.simple_server import make_server

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))
os.environ['DJANGO_SETTINGS_MODULE'] = 'arboris.settings'
from django.conf import settings
settings.DATABASES['default']['TEST'] = {'NAME': 'test_arboris_payroll_preview_20260914'}
settings.DEBUG = True
settings.ALLOWED_HOSTS = ['127.0.0.1', 'localhost']
settings.SESSION_COOKIE_SECURE = False
settings.CSRF_COOKIE_SECURE = False
settings.SECURE_SSL_REDIRECT = False
settings.PASSWORD_HASHERS = ['django.contrib.auth.hashers.MD5PasswordHasher']
settings.TEMPLATES[0]['APP_DIRS'] = False
settings.TEMPLATES[0]['OPTIONS']['loaders'] = ['django.template.loaders.filesystem.Loader', 'django.template.loaders.app_directories.Loader']
import django
django.setup()
from django.test.runner import DiscoverRunner
from django.contrib.auth.models import User
from django.contrib.staticfiles.handlers import StaticFilesHandler
from django.core.wsgi import get_wsgi_application
from django.db import connections
from gestione_amministrativa.models import BustaPagaDipendente, Dipendente, PagamentoBustaPagaDipendente, StatoBustaPaga
from sistema.models import SistemaUtentePermessi, LivelloPermesso

runner = DiscoverRunner(interactive=False, verbosity=0)
old_config = runner.setup_databases()
try:
    assert connections['default'].settings_dict['NAME'] == 'test_arboris_payroll_preview_20260914'
    user = User.objects.create_user('anteprima-matrice', password='Anteprima-buste-2026!')
    SistemaUtentePermessi.objects.create(user=user, permesso_gestione_amministrativa=LivelloPermesso.GESTIONE, permesso_anagrafica=LivelloPermesso.GESTIONE)
    for index, (nome, cognome) in enumerate([('Luca', 'Bianchi'), ('Elena', 'Conti'), ('Marco', 'Ferri'), ('Anna', 'Rossi')]):
        employee = Dipendente.objects.create(nome=nome, cognome=cognome)
        for month in [1, 2, 3, 4, 5, 6, 7, 8, 9, 13]:
            if index == 2 and month < 4:
                continue
            net = 1200 + index * 135 + month * 3
            forecast = month in [9, 13]
            bill = BustaPagaDipendente.objects.create(dipendente=employee, anno=2026, mese=month,
                stato=StatoBustaPaga.PREVISTA if forecast else StatoBustaPaga.EFFETTIVA,
                netto_effettivo=0 if forecast else net, netto_previsto=net if forecast else 0)
            if month <= 6:
                PagamentoBustaPagaDipendente.objects.create(busta_paga=bill, importo=net if month < 5 or index == 0 else 500, data_pagamento=date(2026, month, 28))
    connections.close_all()
    with make_server('127.0.0.1', 8875, StaticFilesHandler(get_wsgi_application())) as server:
        print('Payroll preview ready: http://127.0.0.1:8875', flush=True)
        server.timeout = 1
        while not (root / '.tmp' / 'payroll-preview-stop').exists():
            server.handle_request()
finally:
    runner.teardown_databases(old_config)
