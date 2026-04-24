from decimal import Decimal, InvalidOperation

from django import template


register = template.Library()


@register.filter
def euro(value):
    if value in (None, ""):
        return "-"

    try:
        amount = Decimal(value)
    except (InvalidOperation, TypeError, ValueError):
        return value

    negative = amount < 0
    amount = abs(amount)
    formatted = f"{amount:,.2f}"
    formatted = formatted.replace(",", "X").replace(".", ",").replace("X", ".")

    if negative:
        formatted = f"-{formatted}"

    return formatted


@register.filter
def si_no(value):
    return "Sì" if bool(value) else "No"


@register.filter
def it_date(value):
    if not value:
        return "-"

    try:
        return value.strftime("%d / %m / %Y")
    except Exception:
        return value
