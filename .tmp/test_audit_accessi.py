import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ["DJANGO_SETTINGS_MODULE"] = "arboris.settings"
os.environ["ARBORIS_BACKGROUND_SCHEDULER_ENABLED"] = "0"

from django.conf import settings
from django.core.management import execute_from_command_line

settings.DATABASES["default"]["TEST"] = {"NAME": "test_arboris_audit_accessi_20260913"}
settings.PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
execute_from_command_line(["manage.py", "test", *sys.argv[1:], "--noinput"])
