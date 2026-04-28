from django.utils import timezone

from .models import AnnoScolastico


def resolve_default_anno_scolastico(queryset=None, *, today=None):
    if queryset is None:
        queryset = AnnoScolastico.objects.all()

    active_queryset = queryset.filter(attivo=True)
    ordered_queryset = active_queryset.order_by("-data_inizio", "-id")
    reference_date = today or timezone.localdate()

    anno_per_data = ordered_queryset.filter(data_inizio__lte=reference_date, data_fine__gte=reference_date).first()
    if anno_per_data:
        return anno_per_data

    return ordered_queryset.first() or queryset.order_by("-data_inizio", "-id").first()
