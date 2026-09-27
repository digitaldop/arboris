from arboris.settings import *
DATABASES = {"default": {"ENGINE": "django.db.backends.postgresql", "NAME": "arboris_dev", "USER": "postgres", "PASSWORD": "postgres", "HOST": "localhost", "PORT": "5432", "TEST": {"NAME": "test_arboris_address_revision"}}}
