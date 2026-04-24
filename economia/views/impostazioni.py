from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render

from economia.forms import MetodoPagamentoForm
from economia.models import MetodoPagamento
from economia.views.iscrizioni import (
    is_popup_request,
    popup_delete_response,
    popup_select_response,
)


def crea_metodo_pagamento(request):
    popup = is_popup_request(request)

    if request.method == "POST":
        form = MetodoPagamentoForm(request.POST)
        if form.is_valid():
            metodo = form.save()

            if popup:
                return popup_select_response(request, "metodo_pagamento", metodo.pk, str(metodo))

            messages.success(request, "Metodo di pagamento creato correttamente.")
            return redirect("home")
    else:
        form = MetodoPagamentoForm()

    return render(
        request,
        "economia/impostazioni/metodo_pagamento_form.html",
        {"form": form, "metodo": None, "popup": popup},
    )


def modifica_metodo_pagamento(request, pk):
    metodo = get_object_or_404(MetodoPagamento, pk=pk)
    popup = is_popup_request(request)

    if request.method == "POST":
        form = MetodoPagamentoForm(request.POST, instance=metodo)
        if form.is_valid():
            metodo = form.save()

            if popup:
                return popup_select_response(request, "metodo_pagamento", metodo.pk, str(metodo))

            messages.success(request, "Metodo di pagamento aggiornato correttamente.")
            return redirect("home")
    else:
        form = MetodoPagamentoForm(instance=metodo)

    return render(
        request,
        "economia/impostazioni/metodo_pagamento_form.html",
        {"form": form, "metodo": metodo, "popup": popup},
    )


def elimina_metodo_pagamento(request, pk):
    metodo = get_object_or_404(MetodoPagamento, pk=pk)
    popup = is_popup_request(request)

    if request.method == "POST":
        object_id = metodo.pk
        metodo.delete()

        if popup:
            return popup_delete_response(request, "metodo_pagamento", object_id)

        messages.success(request, "Metodo di pagamento eliminato correttamente.")
        return redirect("home")

    return render(
        request,
        "economia/impostazioni/metodo_pagamento_confirm_delete.html",
        {"metodo": metodo, "popup": popup},
    )
