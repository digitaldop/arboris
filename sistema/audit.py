import json
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import date, datetime, time
from decimal import Decimal


_current_audit_user = ContextVar("current_audit_user", default=None)
_audit_disabled_depth = ContextVar("audit_disabled_depth", default=0)


TRACKED_APP_LABELS = {
    "anagrafica",
    "sistema",
    "scuola",
    "calendario",
    "economia",
    "servizi_extra",
    "gestione_finanziaria",
    "gestione_amministrativa",
}
TRACKED_AUTH_MODELS = {"user"}

EXCLUDED_AUDIT_FIELD_NAMES = {
    "last_login",
    "data_creazione",
    "data_aggiornamento",
    "created_at",
    "updated_at",
    "ultimo_backup_automatico_at",
    "ultimo_errore_backup_automatico",
    "backup_automatico_in_corso",
    "backup_automatico_avviato_at",
}


def normalize_audit_user(user):
    if user is None:
        return None

    if not getattr(user, "is_authenticated", False):
        return None

    return user


def set_current_audit_user(user):
    return _current_audit_user.set(normalize_audit_user(user))


def reset_current_audit_user(token):
    _current_audit_user.reset(token)


def clear_current_audit_user():
    _current_audit_user.set(None)


def get_current_audit_user():
    return normalize_audit_user(_current_audit_user.get())


def is_audit_disabled():
    return _audit_disabled_depth.get() > 0


@contextmanager
def audit_logging_disabled():
    token = _audit_disabled_depth.set(_audit_disabled_depth.get() + 1)
    try:
        yield
    finally:
        _audit_disabled_depth.reset(token)


@contextmanager
def audit_actor(user):
    token = set_current_audit_user(user)
    try:
        yield
    finally:
        reset_current_audit_user(token)


def format_audit_user_label(user):
    user = normalize_audit_user(user)
    if not user:
        return ""

    nome = user.get_full_name().strip()
    return nome or user.email or user.username


def should_track_model(model):
    opts = model._meta

    if opts.abstract or opts.proxy or opts.auto_created:
        return False

    if opts.app_label in TRACKED_APP_LABELS:
        return opts.model_name != "sistemaoperazionecronologia"

    return opts.app_label == "auth" and opts.model_name in TRACKED_AUTH_MODELS


def get_audit_module_for_model(model):
    app_label = model._meta.app_label
    if app_label == "auth":
        return "sistema"
    return app_label


def should_track_field(field):
    if field.primary_key or field.auto_created:
        return False

    if getattr(field, "auto_now", False) or getattr(field, "auto_now_add", False):
        return False

    return field.name not in EXCLUDED_AUDIT_FIELD_NAMES


def normalize_field_value(value):
    if value is None:
        return None

    if hasattr(value, "name"):
        return value.name

    if isinstance(value, (datetime, date, time)):
        return value.isoformat()

    if isinstance(value, Decimal):
        return str(value)

    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)

    if isinstance(value, (bool, int, float, str)):
        return value

    return str(value)


def serialize_instance_for_audit(instance):
    data = {}

    for field in instance._meta.concrete_fields:
        if not should_track_field(field):
            continue

        data[field.name] = normalize_field_value(field.value_from_object(instance))

    return data


def get_changed_field_names(previous_data, current_data):
    changed_names = []

    for field_name, current_value in current_data.items():
        if previous_data.get(field_name) != current_value:
            changed_names.append(field_name)

    return changed_names


def get_field_labels(model, field_names):
    labels = []

    for field_name in field_names:
        try:
            field = model._meta.get_field(field_name)
        except Exception:
            continue

        label = str(getattr(field, "verbose_name", field_name) or field_name).strip()
        labels.append(label[:1].upper() + label[1:] if label else field_name)

    return labels


def get_instance_audit_label(instance):
    try:
        label = str(instance).strip()
    except Exception:
        label = ""

    if label:
        return label[:255]

    verbose_name = str(instance._meta.verbose_name).strip()
    object_id = getattr(instance, "pk", None)
    if object_id is not None:
        return f"{verbose_name} #{object_id}"[:255]

    return verbose_name[:255]
