import os
import sys
from pathlib import Path
from decimal import Decimal
from datetime import date
from time import sleep
from wsgiref.simple_server import make_server, WSGIServer
from socketserver import ThreadingMixIn

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))
sys.argv = ['manage.py', 'test']
os.environ['DJANGO_SETTINGS_MODULE'] = 'arboris.settings'
from django.conf import settings
settings.DATABASES['default']['TEST'] = {'NAME': 'test_arboris_review_browser_20260914'}
settings.DEBUG = True
settings.ALLOWED_HOSTS = ['127.0.0.1', 'localhost']
settings.SESSION_COOKIE_SECURE = False
settings.CSRF_COOKIE_SECURE = False
settings.SECURE_SSL_REDIRECT = False
settings.PASSWORD_HASHERS = ['django.contrib.auth.hashers.MD5PasswordHasher']
import django
django.setup()
from django.test.runner import DiscoverRunner
from django.test import Client
from django.db import connections
from django.contrib.staticfiles.handlers import StaticFilesHandler
from django.core.wsgi import get_wsgi_application
from django.urls import reverse
from gestione_finanziaria.test_reconciliation_interface import ReconciliationInterfaceTests
from gestione_finanziaria.models import PropostaRiconciliazione, RichiestaAnalisiRiconciliazione
from gestione_finanziaria.reconciliation import _describe, _hash
from economia.models import RataIscrizione

runner = DiscoverRunner(interactive=False, verbosity=0)
old_config = runner.setup_databases()
try:
    assert connections['default'].settings_dict['NAME'] == 'test_arboris_review_browser_20260914'
    fixture = ReconciliationInterfaceTests()
    fixture.client = Client()
    fixture.setUp()
    fixture.user.set_password('Preview-review-2026!')
    fixture.user.save()
    rate = fixture.rate()
    fixture.proposal(rate, fixture.movement(controparte='Paolo Bianchi', description='Retta settembre Luca Bianchi'), score=96)
    fixture.proposal(rate, fixture.movement(controparte='Mario Bianchi', description='Bonifico quota scuola'), score=62)
    for number, score in [(2, 78), (3, 42)]:
        another = RataIscrizione.objects.create(iscrizione=rate.iscrizione, numero_rata=number, mese_riferimento=number + 8, anno_riferimento=2026, data_scadenza=date(2026, number + 8, 10), importo_dovuto=100)
        fixture.proposal(another, fixture.movement(controparte='Famiglia Bianchi', description='Pagamento quota scolastica'), score=score)
    deadline = fixture.deadline()
    for score in [98, 56]:
        movement = fixture.movement('-100', 'Saldo fattura FT-100 Aurora', controparte='Aurora Servizi SRL')
        rows = [{'movimento_id': movement.pk, 'target_tipo': 'scadenza_fornitore', 'target_id': deadline.pk, 'importo': '100.00'}]
        snapshot, _ = _describe(rows)
        PropostaRiconciliazione.objects.create(chiave=_hash([rows, snapshot]), abbinamento=_hash(rows), caso='supplier-preview', ambito='fornitore', compatibilita=score, allocazioni=rows, dati_verifica=snapshot, motivazioni=['Importo corrispondente', 'Riferimento fattura presente nella causale'])
    RichiestaAnalisiRiconciliazione.objects.all().delete()
    connections.close_all()
    app = StaticFilesHandler(get_wsgi_application())
    decision_path = reverse('decidi_proposte_riconciliazione')
    def preview_app(environ, start_response):
        if environ.get('PATH_INFO') == decision_path and environ.get('REQUEST_METHOD') == 'POST':
            sleep(4)
            if (root / '.tmp' / 'review-simulate-error').exists():
                start_response('503 Service Unavailable', [('Content-Type', 'text/plain')])
                return [b'Preview simulated connection failure']
        return app(environ, start_response)
    class ThreadingServer(ThreadingMixIn, WSGIServer):
        daemon_threads = True
    print('REVIEW PREVIEW http://127.0.0.1:8799' + reverse('proposte_riconciliazione') + '?popup=1', flush=True)
    with make_server('127.0.0.1', 8799, preview_app, server_class=ThreadingServer) as server:
        server.serve_forever()
finally:
    connections.close_all()
    runner.teardown_databases(old_config)
