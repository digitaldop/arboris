from django import template

from sistema.rich_notes import render_rich_notes_html

register = template.Library()


@register.filter(name="render_rich_notes")
def render_rich_notes(value):
    return render_rich_notes_html(value)
