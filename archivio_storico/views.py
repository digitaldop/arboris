from django.contrib import messages
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from archivio_storico.models import ArchivioAnnoScolastico, TipoSnapshotStorico
from archivio_storico.services import (
    anno_scolastico_archiviabile,
    archivia_anno_scolastico,
    get_archiviazione_preview,
)
from scuola.models import AnnoScolastico


def lista_archivio_storico(request):
    archivi = (
        ArchivioAnnoScolastico.objects.select_related("anno_scolastico", "archiviato_da")
        .all()
    )
    anni = (
        AnnoScolastico.objects.filter(attivo=True)
        .select_related("archivio_storico")
        .order_by("-data_inizio", "-id")
    )
    anni_archiviabili = []
    anni_non_archiviabili = []

    for anno in anni:
        can_archive, motivi = anno_scolastico_archiviabile(anno)
        item = {"anno": anno, "motivi": motivi}
        if can_archive:
            anni_archiviabili.append(item)
        else:
            anni_non_archiviabili.append(item)

    return render(
        request,
        "archivio_storico/archivio_list.html",
        {
            "archivi": archivi,
            "anni_archiviabili": anni_archiviabili,
            "anni_non_archiviabili": anni_non_archiviabili,
        },
    )


def anteprima_archiviazione_anno(request, anno_pk):
    anno = get_object_or_404(AnnoScolastico, pk=anno_pk)
    can_archive, motivi = anno_scolastico_archiviabile(anno)
    preview = get_archiviazione_preview(anno)

    return render(
        request,
        "archivio_storico/archivio_preview.html",
        {
            "anno": anno,
            "can_archive": can_archive,
            "motivi_blocco": motivi,
            "preview": preview,
        },
    )


@require_POST
def archivia_anno(request, anno_pk):
    anno = get_object_or_404(AnnoScolastico, pk=anno_pk)
    conferma_check = request.POST.get("conferma_archiviazione") == "1"
    conferma_testo = (request.POST.get("conferma_testo") or "").strip().upper()

    if not conferma_check or conferma_testo != "ARCHIVIA":
        messages.error(
            request,
            'Per archiviare l\'anno scolastico devi spuntare la conferma e scrivere "ARCHIVIA".',
        )
        return redirect("anteprima_archiviazione_anno", anno_pk=anno.pk)

    try:
        archivio = archivia_anno_scolastico(
            anno,
            user=request.user,
            note=request.POST.get("note", ""),
        )
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
        return redirect("anteprima_archiviazione_anno", anno_pk=anno.pk)

    messages.success(request, f"Anno scolastico {anno} archiviato correttamente.")
    return redirect("dettaglio_archivio_storico", pk=archivio.pk)


def dettaglio_archivio_storico(request, pk):
    archivio = get_object_or_404(
        ArchivioAnnoScolastico.objects.select_related("anno_scolastico", "archiviato_da"),
        pk=pk,
    )
    snapshots = list(archivio.snapshot.all())
    sections = []

    for tipo, label in TipoSnapshotStorico.choices:
        records = [snapshot for snapshot in snapshots if snapshot.tipo == tipo]
        if records:
            sections.append(
                {
                    "tipo": tipo,
                    "label": label,
                    "records": records,
                    "count": len(records),
                }
            )

    return render(
        request,
        "archivio_storico/archivio_detail.html",
        {
            "archivio": archivio,
            "sections": sections,
            "back_url": reverse("lista_archivio_storico"),
        },
    )
