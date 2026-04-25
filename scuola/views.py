from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .forms import AnnoScolasticoForm, ClasseForm
from .models import AnnoScolastico, Classe


def is_popup_request(request):
    return request.GET.get("popup") == "1" or request.POST.get("popup") == "1"


def popup_select_response(request, field_name, object_id, object_label):
    return render(
        request,
        "popup/popup_close_select.html",
        {
            "action": "select",
            "field_name": field_name,
            "object_id": object_id,
            "object_label": object_label,
            "target_input_name": request.GET.get("target_input_name") or request.POST.get("target_input_name", ""),
        },
    )


def popup_delete_response(request, field_name, object_id):
    return render(
        request,
        "popup/popup_close_select.html",
        {
            "action": "delete",
            "field_name": field_name,
            "object_id": object_id,
            "target_input_name": request.GET.get("target_input_name") or request.POST.get("target_input_name", ""),
        },
    )


def lista_anni_scolastici(request):
    today = timezone.localdate()
    anni_qs = AnnoScolastico.objects.all()
    anni_correnti_e_futuri = anni_qs.filter(data_fine__gte=today).order_by("data_inizio", "id")
    anni_passati = anni_qs.filter(data_fine__lt=today).order_by("-data_inizio", "-id")
    return render(
        request,
        "scuola/anni_scolastici/anno_scolastico_list.html",
        {
            "anni_correnti_e_futuri": anni_correnti_e_futuri,
            "anni_passati": anni_passati,
        },
    )


def crea_anno_scolastico(request):
    popup = is_popup_request(request)

    if request.method == "POST":
        form = AnnoScolasticoForm(request.POST)
        if form.is_valid():
            anno = form.save()

            if popup:
                return popup_select_response(request, "anno_scolastico", anno.pk, str(anno))

            messages.success(request, "Anno scolastico creato correttamente.")
            return redirect("lista_anni_scolastici")
    else:
        form = AnnoScolasticoForm()

    return render(
        request,
        "scuola/anni_scolastici/anno_scolastico_form.html",
        {"form": form, "anno": None, "popup": popup},
    )


def modifica_anno_scolastico(request, pk):
    anno = get_object_or_404(AnnoScolastico, pk=pk)
    popup = is_popup_request(request)

    if request.method == "POST":
        form = AnnoScolasticoForm(request.POST, instance=anno)
        if form.is_valid():
            anno = form.save()

            if popup:
                return popup_select_response(request, "anno_scolastico", anno.pk, str(anno))

            messages.success(request, "Anno scolastico aggiornato correttamente.")
            return redirect("lista_anni_scolastici")
    else:
        form = AnnoScolasticoForm(instance=anno)

    return render(
        request,
        "scuola/anni_scolastici/anno_scolastico_form.html",
        {"form": form, "anno": anno, "popup": popup},
    )


def elimina_anno_scolastico(request, pk):
    anno = get_object_or_404(AnnoScolastico, pk=pk)
    popup = is_popup_request(request)

    if request.method == "POST":
        object_id = anno.pk
        anno.delete()

        if popup:
            return popup_delete_response(request, "anno_scolastico", object_id)

        messages.success(request, "Anno scolastico eliminato correttamente.")
        return redirect("lista_anni_scolastici")

    return render(
        request,
        "scuola/anni_scolastici/anno_scolastico_confirm_delete.html",
        {
            "anno": anno,
            "count_classi": anno.classi.count(),
            "popup": popup,
        },
    )


def lista_classi(request):
    classi = Classe.objects.select_related("anno_scolastico").all()
    return render(request, "scuola/classi/classe_list.html", {"classi": classi})


def crea_classe(request):
    popup = is_popup_request(request)

    if request.method == "POST":
        form = ClasseForm(request.POST)
        if form.is_valid():
            classe = form.save()

            if popup:
                return popup_select_response(request, "classe", classe.pk, str(classe))

            messages.success(request, "Classe creata correttamente.")
            return redirect("lista_classi")
    else:
        form = ClasseForm()

    return render(
        request,
        "scuola/classi/classe_form.html",
        {"form": form, "classe": None, "popup": popup},
    )


def modifica_classe(request, pk):
    classe = get_object_or_404(Classe, pk=pk)
    popup = is_popup_request(request)

    if request.method == "POST":
        form = ClasseForm(request.POST, instance=classe)
        if form.is_valid():
            classe = form.save()

            if popup:
                return popup_select_response(request, "classe", classe.pk, str(classe))

            messages.success(request, "Classe aggiornata correttamente.")
            return redirect("lista_classi")
    else:
        form = ClasseForm(instance=classe)

    return render(
        request,
        "scuola/classi/classe_form.html",
        {"form": form, "classe": classe, "popup": popup},
    )


def elimina_classe(request, pk):
    classe = get_object_or_404(Classe, pk=pk)
    popup = is_popup_request(request)

    if request.method == "POST":
        object_id = classe.pk
        classe.delete()

        if popup:
            return popup_delete_response(request, "classe", object_id)

        messages.success(request, "Classe eliminata correttamente.")
        return redirect("lista_classi")

    return render(
        request,
        "scuola/classi/classe_confirm_delete.html",
        {"classe": classe, "popup": popup},
    )
