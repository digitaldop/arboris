import re

from django.utils.html import conditional_escape
from django.utils.safestring import mark_safe


UNDERLINE_PATTERN = re.compile(r"__(.+?)__", re.DOTALL)
BOLD_PATTERN = re.compile(r"\*\*(.+?)\*\*", re.DOTALL)
ITALIC_PATTERN = re.compile(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", re.DOTALL)


def render_rich_notes_html(value):
    text = "" if value is None else str(value)
    if not text.strip():
        return ""

    html = conditional_escape(text)
    html = UNDERLINE_PATTERN.sub(r"<u>\1</u>", html)
    html = BOLD_PATTERN.sub(r"<strong>\1</strong>", html)
    html = ITALIC_PATTERN.sub(r"<em>\1</em>", html)
    html = html.replace("\r\n", "\n").replace("\r", "\n").replace("\n", "<br>")
    return mark_safe(html)
