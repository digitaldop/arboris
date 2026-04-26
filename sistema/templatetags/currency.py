from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from django import template
from django.utils import timezone


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


@register.filter
def it_date_with_age(value):
    if not value:
        return "-"

    birth_date = value.date() if isinstance(value, datetime) else value
    if not isinstance(birth_date, date):
        return it_date(value)

    today = timezone.localdate()
    years = today.year - birth_date.year
    if (today.month, today.day) < (birth_date.month, birth_date.day):
        years -= 1
    if years < 0:
        return it_date(value)

    label = "Anno" if years == 1 else "Anni"
    return f"{it_date(value)} ( {years} {label} )"
