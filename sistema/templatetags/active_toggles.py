from django import template
from django.urls import reverse

from sistema.active_toggles import (
    active_toggle_labels,
    get_active_toggle_config_for_object,
    validate_active_toggle_config,
)
from sistema.models import LivelloPermesso
from sistema.permissions import user_has_module_permission


register = template.Library()


@register.inclusion_tag("common/active_toggle.html", takes_context=True)
def active_toggle(context, obj, field=None, reload=False, compact=False):
    request = context.get("request")
    config = get_active_toggle_config_for_object(obj, field_name=field)
    if not obj or not config or not validate_active_toggle_config(config):
        return {"available": False}

    value = bool(getattr(obj, config.field_name))
    active_label, inactive_label = active_toggle_labels(
        config.field_name,
        active_label=config.active_label,
        inactive_label=config.inactive_label,
    )
    can_toggle = bool(
        request
        and getattr(request, "user", None)
        and user_has_module_permission(
            request.user,
            config.module_name,
            level=LivelloPermesso.GESTIONE,
        )
    )

    return {
        "available": True,
        "obj": obj,
        "model_label": obj._meta.label_lower,
        "object_id": obj.pk,
        "field_name": config.field_name,
        "value": value,
        "label": active_label if value else inactive_label,
        "active_label": active_label,
        "inactive_label": inactive_label,
        "can_toggle": can_toggle,
        "toggle_url": reverse("toggle_active_state"),
        "next_url": request.get_full_path() if request else "",
        "csrf_token": context.get("csrf_token", ""),
        "reload_on_success": bool(reload or config.reload_on_success),
        "compact": compact,
    }
