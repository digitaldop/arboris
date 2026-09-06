from datetime import timezone as datetime_timezone
from email.utils import parsedate_to_datetime
from math import ceil, isfinite

from django.utils import timezone
from django.utils.dateparse import parse_datetime


def retry_after_seconds(value, *, now=None):
    """Read Retry-After as seconds or an HTTP date; missing values use backoff."""
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        seconds = float(value)
    except ValueError:
        try:
            when = parsedate_to_datetime(value)
            if when.tzinfo is None:
                when = when.replace(tzinfo=datetime_timezone.utc)
            seconds = (when - (now or timezone.now())).total_seconds()
        except (TypeError, ValueError, OverflowError):
            return None
    if not isfinite(seconds) or seconds > 365 * 24 * 60 * 60:
        return None
    return max(0, ceil(seconds))


def sync_retry_at(progress):
    value = (progress or {}).get("retry_at")
    if not isinstance(value, str):
        return None
    try:
        when = parse_datetime(value)
    except ValueError:
        return None
    if when and timezone.is_naive(when):
        when = timezone.make_aware(when, datetime_timezone.utc)
    return when
