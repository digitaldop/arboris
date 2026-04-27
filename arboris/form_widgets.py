from django import forms
from django.core.exceptions import ValidationError
from decimal import Decimal, InvalidOperation


def italian_decimal_to_python(field, value):
    if value in field.empty_values:
        return None

    if isinstance(value, Decimal):
        return value

    raw_value = str(value).strip().replace(" ", "")
    if "," in raw_value:
        raw_value = raw_value.replace(".", "").replace(",", ".")

    try:
        value = Decimal(raw_value)
    except (InvalidOperation, TypeError, ValueError):
        raise ValidationError(field.error_messages["invalid"], code="invalid") from None

    if not value.is_finite():
        raise ValidationError(field.error_messages["invalid"], code="invalid")

    return value


def merge_widget_classes(widget, *extra_classes):
    existing_classes = (widget.attrs.get("class") or "").split()
    for css_class in extra_classes:
        if css_class and css_class not in existing_classes:
            existing_classes.append(css_class)
    widget.attrs["class"] = " ".join(existing_classes).strip()


def apply_eur_currency_widget(field, *, placeholder="0,00", compact=True):
    field.localize = True
    field.to_python = lambda value, _field=field: italian_decimal_to_python(_field, value)
    field.widget = forms.TextInput()
    field.widget.is_localized = True
    merge_widget_classes(field.widget, "currency-field", "currency-field-suffix")
    if compact:
        merge_widget_classes(field.widget, "currency-field-compact")

    field.widget.attrs.update(
        {
            "autocomplete": "off",
            "inputmode": "decimal",
            "data-currency": "EUR",
            "data-currency-display": "suffix",
            "placeholder": placeholder,
        }
    )
