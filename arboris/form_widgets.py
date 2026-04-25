from django import forms


def merge_widget_classes(widget, *extra_classes):
    existing_classes = (widget.attrs.get("class") or "").split()
    for css_class in extra_classes:
        if css_class and css_class not in existing_classes:
            existing_classes.append(css_class)
    widget.attrs["class"] = " ".join(existing_classes).strip()


def apply_eur_currency_widget(field, *, placeholder="0,00", compact=True):
    field.widget = forms.TextInput()
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
