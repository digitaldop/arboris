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


def _is_zero_value(value):
    if value in forms.Field.empty_values:
        return False

    raw_value = str(value).strip().replace(" ", "")
    if "," in raw_value:
        raw_value = raw_value.replace(".", "").replace(",", ".")

    try:
        return Decimal(raw_value) == Decimal("0.00")
    except (InvalidOperation, TypeError, ValueError):
        return False


class CurrencyTextInput(forms.TextInput):
    def format_value(self, value):
        if self.attrs.get("data-zero-as-placeholder") == "1" and _is_zero_value(value):
            return ""
        return super().format_value(value)


def apply_eur_currency_widget(field, *, placeholder="0,00", compact=True, zero_as_placeholder=None):
    field.localize = True
    field.to_python = lambda value, _field=field: italian_decimal_to_python(_field, value)
    if zero_as_placeholder is None:
        zero_as_placeholder = True
    if zero_as_placeholder and _is_zero_value(field.initial):
        field.initial = ""
    field.widget = CurrencyTextInput(attrs=dict(field.widget.attrs))
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
            "data-zero-as-placeholder": "1" if zero_as_placeholder else "0",
            "placeholder": placeholder,
        }
    )
