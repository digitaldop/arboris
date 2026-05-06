from django.db.models.signals import post_delete, post_save, pre_save
from django.db.utils import OperationalError, ProgrammingError
from django.dispatch import receiver

from .audit import (
    audit_logging_disabled,
    format_audit_user_label,
    get_audit_module_for_model,
    get_changed_field_names,
    get_current_audit_user,
    get_field_labels,
    get_instance_audit_label,
    is_audit_disabled,
    serialize_instance_for_audit,
    should_track_model,
)
from .audit_retention import cleanup_cronologia_operazioni
from .models import (
    AzioneOperazioneCronologia,
    SistemaOperazioneCronologia,
)


def build_operation_description(action, model_verbose_name, object_label):
    if action == AzioneOperazioneCronologia.CREAZIONE:
        return f"Creato {model_verbose_name}: {object_label}."
    if action == AzioneOperazioneCronologia.ELIMINAZIONE:
        return f"Eliminato {model_verbose_name}: {object_label}."
    return f"Modificato {model_verbose_name}: {object_label}."


def create_audit_entry(instance, action, changed_field_names=None):
    if is_audit_disabled():
        return

    model = instance.__class__
    current_user = get_current_audit_user()
    model_verbose_name = str(model._meta.verbose_name).strip()
    object_label = get_instance_audit_label(instance)
    changed_field_labels = get_field_labels(model, changed_field_names or [])
    if len(changed_field_labels) > 8:
        overflow_count = len(changed_field_labels) - 8
        changed_field_labels = changed_field_labels[:8] + [f"+{overflow_count} altri campi"]

    try:
        with audit_logging_disabled():
            SistemaOperazioneCronologia.objects.create(
                azione=action,
                modulo=get_audit_module_for_model(model),
                utente=current_user,
                utente_label=format_audit_user_label(current_user),
                app_label=model._meta.app_label,
                model_name=model._meta.model_name,
                model_verbose_name=model_verbose_name[:120],
                oggetto_id="" if getattr(instance, "pk", None) is None else str(instance.pk),
                oggetto_label=object_label,
                descrizione=build_operation_description(action, model_verbose_name, object_label),
                campi_coinvolti=changed_field_labels,
            )
            cleanup_cronologia_operazioni()
    except (OperationalError, ProgrammingError):
        return


@receiver(pre_save, dispatch_uid="sistema_audit_capture_previous_state")
def capture_previous_state(sender, instance, **kwargs):
    if not should_track_model(sender) or is_audit_disabled():
        return

    if not getattr(instance, "pk", None):
        instance._audit_previous_state = {}
        return

    previous_instance = sender._default_manager.filter(pk=instance.pk).first()
    instance._audit_previous_state = (
        serialize_instance_for_audit(previous_instance) if previous_instance else {}
    )


@receiver(post_save, dispatch_uid="sistema_audit_log_save")
def log_saved_instance(sender, instance, created, **kwargs):
    if not should_track_model(sender) or is_audit_disabled():
        return

    current_state = serialize_instance_for_audit(instance)

    if created:
        changed_field_names = [
            field_name for field_name, value in current_state.items()
            if value not in (None, "", "[]", "{}")
        ]
        create_audit_entry(
            instance,
            AzioneOperazioneCronologia.CREAZIONE,
            changed_field_names=changed_field_names,
        )
        return

    previous_state = getattr(instance, "_audit_previous_state", {}) or {}
    changed_field_names = get_changed_field_names(previous_state, current_state)

    if not changed_field_names:
        return

    create_audit_entry(
        instance,
        AzioneOperazioneCronologia.MODIFICA,
        changed_field_names=changed_field_names,
    )


@receiver(post_delete, dispatch_uid="sistema_audit_log_delete")
def log_deleted_instance(sender, instance, **kwargs):
    if not should_track_model(sender) or is_audit_disabled():
        return

    create_audit_entry(
        instance,
        AzioneOperazioneCronologia.ELIMINAZIONE,
        changed_field_names=[],
    )
