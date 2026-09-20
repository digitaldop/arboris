import os
import sys
from datetime import date
from pathlib import Path
from wsgiref.simple_server import make_server

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))
os.environ['DJANGO_SETTINGS_MODULE'] = 'arboris.settings'
from django.conf import settings
settings.DATABASES['default']['TEST'] = {'NAME': 'test_arboris_payroll_period_preview_20260920'}
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
from gestione_amministrativa.models import BustaPagaDipendente, ContrattoDipendente, Dipendente, PagamentoBustaPagaDipendente, StatoBustaPaga
from scuola.models import AnnoScolastico
from sistema.models import SistemaUtentePermessi, LivelloPermesso

runner = DiscoverRunner(interactive=False, verbosity=0)
old_config = runner.setup_databases()
try:
    assert connections['default'].settings_dict['NAME'] == 'test_arboris_payroll_period_preview_20260920'
    user = User.objects.create_user('anteprima-periodi', password='Anteprima-periodi-2026!')
    SistemaUtentePermessi.objects.create(user=user, permesso_gestione_amministrativa=LivelloPermesso.GESTIONE, permesso_anagrafica=LivelloPermesso.GESTIONE)
    for year in [2024, 2025, 2026]:
        AnnoScolastico.objects.create(nome_anno_scolastico=f'{year}/{year+1}', data_inizio=date(year, 9, 1), data_fine=date(year+1, 8, 31), attivo=year == 2026)
    for index, (nome, cognome) in enumerate([('Luca', 'Bianchi'), ('Elena', 'Conti'), ('Anna', 'Rossi')]):
        employee = Dipendente.objects.create(nome=nome, cognome=cognome)
        ContrattoDipendente.objects.create(dipendente=employee, data_inizio=date(2024 - index * 2, 1, 1))
        for year in [2025, 2026]:
            for month in [1, 2, 8, 9, 10, 12, 13]:
                net = 1200 + index * 135 + month * 3
                bill = BustaPagaDipendente.objects.create(dipendente=employee, anno=year, mese=month,
                    stato=StatoBustaPaga.BOZZA if index == 1 else StatoBustaPaga.EFFETTIVA, netto_effettivo=net)
                if month in [1, 2, 9, 10]:
                    PagamentoBustaPagaDipendente.objects.create(busta_paga=bill, importo=net if index == 0 else 500, data_pagamento=date(year, month, 28))
    connections.close_all()
    with make_server('127.0.0.1', 8876, StaticFilesHandler(get_wsgi_application())) as server:
        print('Payroll period preview ready: http://127.0.0.1:8876', flush=True)
        server.timeout = 1
        while not (root / '.tmp' / 'payroll-period-preview-stop').exists():
            server.handle_request()
finally:
    runner.teardown_databases(old_config)
