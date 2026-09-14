import os
import sys
import ast
import subprocess
from pathlib import Path

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root))
os.environ['DJANGO_SETTINGS_MODULE'] = 'arboris.settings'
from django.conf import settings
settings.DATABASES['default']['TEST'] = {'NAME': 'test_arboris_payroll_matrix_20260914'}
settings.PASSWORD_HASHERS = ['django.contrib.auth.hashers.MD5PasswordHasher']
import django
django.setup()
baseline = '--baseline' in sys.argv
if baseline:
    from gestione_amministrativa import models
    source = subprocess.check_output(['git', 'show', 'HEAD:gestione_amministrativa/models.py'], text=True, encoding='utf-8')
    model_node = next(node for node in ast.parse(source).body if isinstance(node, ast.ClassDef) and node.name == 'BustaPagaDipendente')
    property_node = next(node for node in model_node.body if isinstance(node, ast.FunctionDef) and node.name == 'importo_pagato_riconciliato')
    namespace = dict(vars(models))
    exec(compile(ast.Module(body=[property_node], type_ignores=[]), '<baseline-model-property>', 'exec'), namespace)
    models.BustaPagaDipendente.importo_pagato_riconciliato = namespace['importo_pagato_riconciliato']
from django.test.runner import DiscoverRunner
runner = DiscoverRunner(interactive=False, verbosity=1)
labels = ['gestione_amministrativa.tests.SimulazioneCostoDipendenteTests.test_riconciliazione_busta_paga_accetta_movimento_non_capiente_come_parziale'] if baseline else ['gestione_amministrativa']
sys.exit(bool(runner.run_tests(labels)))
