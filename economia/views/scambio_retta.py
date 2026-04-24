from urllib.parse import urlencode

from django.conf import settings
from django.contrib import messages
from django.core.exceptions import DisallowedHost
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme

from anagrafica.models import Familiare
from economia.forms import PrestazioneScambioRettaForm, ScambioRettaForm, TariffaScambioRettaForm
from economia.models import (
    MovimentoCreditoRetta,
    PrestazioneScambioRetta,
    ScambioRetta,
    TariffaScambioRetta,
    TipoMovimentoCredito,
)
from economia.scambio_retta_helpers import parse_iso_date
from scuola.models import AnnoScolastico


def build_default_prestazione_return_url(familiare=None):
    if familiare and familiare.pk:
        return f"{reverse('modifica_familiare', kwargs={'pk': familiare.pk})}#scambio-retta-inline"
    return reverse("lista_scambi_retta")


def resolve_safe_return_url(request, default_url):
    candidate = (request.POST.get("return_to") or request.GET.get("return_to") or "").strip()
    try:
        request_host = request.get_host()
    except DisallowedHost:
        request_host = request.META.get("HTTP_HOST", "localhost")

    allowed_hosts = {request_host, "localhost", "127.0.0.1"}
    allowed_hosts.update(host for host in settings.ALLOWED_HOSTS if host and host != "*")

    if candidate and candidate.startswith("/") and url_has_allowed_host_and_scheme(
        candidate,
        allowed_hosts=allowed_hosts,
        require_https=request.is_secure(),
    ):
        return candidate

    return default_url


def get_selected_familiare_for_prestazione_form(form):
    if form.is_bound:
        familiare_id = form.data.get("familiare")
        if familiare_id:
            return Familiare.objects.select_related("famiglia").filter(pk=familiare_id).first()

    if form.instance.pk and form.instance.familiare_id:
        return form.instance.familiare

    initial_familiare_id = form.initial.get("familiare")
    if initial_familiare_id:
        return Familiare.objects.select_related("famiglia").filter(pk=initial_familiare_id).first()

    return None


def get_selected_data_for_prestazione_form(form):
    if form.is_bound:
        return parse_iso_date(form.data.get("data"))

    if form.instance.pk and form.instance.data:
        return form.instance.data

    initial_data = form.initial.get("data")
    if hasattr(initial_data, "isoformat"):
        return initial_data
    return parse_iso_date(initial_data)


def resolve_school_year_preview(date_value):
    if not date_value:
        return None

    return (
        AnnoScolastico.objects.filter(data_inizio__lte=date_value, data_fine__gte=date_value)
        .order_by("-data_inizio", "-id")
        .first()
    )


def build_school_year_payload():
    return list(
        AnnoScolastico.objects.order_by("-data_inizio", "-id").values(
            "id",
            "nome_anno_scolastico",
            "data_inizio",
            "data_fine",
        )
    )


def build_prestazione_template_context(request, form, prestazione=None):
    familiare_preview = get_selected_familiare_for_prestazione_form(form)
    data_preview = get_selected_data_for_prestazione_form(form)
    anno_scolastico_preview = resolve_school_year_preview(data_preview)
    default_return_url = build_default_prestazione_return_url(
        familiare_preview or getattr(prestazione, "familiare", None)
    )
    return_url = resolve_safe_return_url(request, default_return_url)

    return {
        "form": form,
        "prestazione": prestazione,
        "familiare_preview": familiare_preview,
        "famiglia_preview": familiare_preview.famiglia if familiare_preview else None,
        "anno_scolastico_preview": anno_scolastico_preview,
        "return_url": return_url,
        "return_to": return_url,
        "return_query": urlencode({"return_to": return_url}) if return_url else "",
        "school_year_payload": build_school_year_payload(),
        "back_label": "Torna al familiare" if familiare_preview else "Torna a scambio retta",
    }


def lista_tariffe_scambio_retta(request):
    tariffe = TariffaScambioRetta.objects.all()
    return render(request, "economia/scambio_retta/tariffe_scambio_retta_list.html", {"tariffe": tariffe})


def crea_tariffa_scambio_retta(request):
    if request.method == "POST":
        form = TariffaScambioRettaForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Tariffa scambio retta creata correttamente.")
            return redirect("lista_tariffe_scambio_retta")
    else:
        form = TariffaScambioRettaForm()

    return render(
        request,
        "economia/scambio_retta/tariffa_scambio_retta_form.html",
        {"form": form, "tariffa": None},
    )


def modifica_tariffa_scambio_retta(request, pk):
    tariffa = get_object_or_404(TariffaScambioRetta, pk=pk)

    if request.method == "POST":
        form = TariffaScambioRettaForm(request.POST, instance=tariffa)
        if form.is_valid():
            form.save()
            messages.success(request, "Tariffa scambio retta aggiornata correttamente.")
            return redirect("lista_tariffe_scambio_retta")
    else:
        form = TariffaScambioRettaForm(instance=tariffa)

    return render(
        request,
        "economia/scambio_retta/tariffa_scambio_retta_form.html",
        {"form": form, "tariffa": tariffa},
    )


def elimina_tariffa_scambio_retta(request, pk):
    tariffa = get_object_or_404(TariffaScambioRetta, pk=pk)

    if request.method == "POST":
        tariffa.delete()
        messages.success(request, "Tariffa scambio retta eliminata correttamente.")
        return redirect("lista_tariffe_scambio_retta")

    return render(
        request,
        "economia/scambio_retta/tariffa_scambio_retta_confirm_delete.html",
        {"tariffa": tariffa},
    )


def lista_scambi_retta(request):
    scambi = ScambioRetta.objects.select_related(
        "familiare",
        "famiglia",
        "studente",
        "anno_scolastico",
        "tariffa_scambio_retta",
    ).all()
    return render(request, "economia/scambio_retta/scambi_retta_list.html", {"scambi": scambi})


def crea_scambio_retta(request):
    if request.method == "POST":
        form = ScambioRettaForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Scambio retta registrato correttamente.")
            return redirect("lista_scambi_retta")
    else:
        form = ScambioRettaForm()

    return render(
        request,
        "economia/scambio_retta/scambio_retta_form.html",
        {"form": form, "scambio": None},
    )


def modifica_scambio_retta(request, pk):
    scambio = get_object_or_404(ScambioRetta, pk=pk)

    if request.method == "POST":
        form = ScambioRettaForm(request.POST, instance=scambio)
        if form.is_valid():
            form.save()
            messages.success(request, "Scambio retta aggiornato correttamente.")
            return redirect("lista_scambi_retta")
    else:
        form = ScambioRettaForm(instance=scambio)

    return render(
        request,
        "economia/scambio_retta/scambio_retta_form.html",
        {"form": form, "scambio": scambio},
    )


def elimina_scambio_retta(request, pk):
    scambio = get_object_or_404(ScambioRetta, pk=pk)

    if request.method == "POST":
        scambio.delete()
        messages.success(request, "Scambio retta eliminato correttamente.")
        return redirect("lista_scambi_retta")

    return render(
        request,
        "economia/scambio_retta/scambio_retta_confirm_delete.html",
        {"scambio": scambio},
    )


def contabilizza_scambio_retta(request, pk):
    scambio = get_object_or_404(
        ScambioRetta.objects.select_related(
            "familiare",
            "famiglia",
            "studente",
            "anno_scolastico",
            "tariffa_scambio_retta",
        ),
        pk=pk,
    )

    prossima_rata = scambio.get_prossima_rata()

    if request.method == "POST":
        if not scambio.approvata:
            messages.error(request, "Lo scambio retta deve essere approvato prima di poter essere contabilizzato.")
            return redirect("lista_scambi_retta")

        if scambio.contabilizzata:
            messages.warning(request, "Questo scambio retta risulta gia contabilizzato.")
            return redirect("lista_scambi_retta")

        if not prossima_rata:
            messages.error(request, "Non esiste una rata successiva disponibile su cui applicare il credito.")
            return redirect("lista_scambi_retta")

        with transaction.atomic():
            prossima_rata.credito_applicato = (prossima_rata.credito_applicato or 0) + scambio.importo_maturato
            prossima_rata.save()

            tipo_movimento, _ = TipoMovimentoCredito.objects.get_or_create(
                tipo_movimento_credito="Credito scambio retta",
                defaults={
                    "attivo": True,
                    "note": "Creato automaticamente per contabilizzare i crediti derivanti dallo scambio retta.",
                },
            )

            ultimo_saldo = (
                MovimentoCreditoRetta.objects.filter(famiglia=scambio.famiglia)
                .order_by("-data_movimento", "-id")
                .values_list("saldo_progressivo", flat=True)
                .first()
                or 0
            )

            MovimentoCreditoRetta.objects.create(
                famiglia=scambio.famiglia,
                studente=scambio.studente,
                iscrizione=prossima_rata.iscrizione,
                rata_iscrizione=prossima_rata,
                scambio_retta=scambio,
                data_movimento=timezone.localdate(),
                tipo_movimento_credito=tipo_movimento,
                importo=scambio.importo_maturato,
                saldo_progressivo=ultimo_saldo + scambio.importo_maturato,
                descrizione=(
                    f"Credito maturato da scambio retta ({scambio.ore_lavorate} ore) "
                    f"applicato a {prossima_rata.display_label.lower()} di {prossima_rata.iscrizione}"
                ),
            )

            scambio.contabilizzata = True
            scambio.save(update_fields=["contabilizzata"])

        messages.success(request, "Scambio retta contabilizzato e credito applicato alla rata successiva.")
        return redirect(f"{reverse('lista_rate_iscrizione')}?iscrizione={prossima_rata.iscrizione_id}")

    return render(
        request,
        "economia/scambio_retta/scambio_retta_contabilizza.html",
        {
            "scambio": scambio,
            "prossima_rata": prossima_rata,
        },
    )


def crea_prestazione_scambio_retta(request):
    initial = {}
    familiare_id = request.POST.get("familiare") or request.GET.get("familiare")

    if request.method == "POST":
        form = PrestazioneScambioRettaForm(request.POST, familiare_id=familiare_id)
        if form.is_valid():
            prestazione = form.save()
            messages.success(request, "Prestazione scambio retta registrata correttamente.")

            return_url = resolve_safe_return_url(
                request,
                build_default_prestazione_return_url(prestazione.familiare),
            )

            if "_continue" in request.POST:
                redirect_url = reverse("modifica_prestazione_scambio_retta", kwargs={"pk": prestazione.pk})
                if return_url:
                    redirect_url = f"{redirect_url}?{urlencode({'return_to': return_url})}"
                return redirect(redirect_url)

            return redirect(return_url)
    else:
        if familiare_id:
            initial["familiare"] = familiare_id

        data_value = parse_iso_date(request.GET.get("data"))
        if data_value:
            initial["data"] = data_value

        studente_id = request.GET.get("studente")
        if studente_id:
            initial["studente"] = studente_id

        form = PrestazioneScambioRettaForm(initial=initial, familiare_id=familiare_id)

    return render(
        request,
        "economia/scambio_retta/prestazione_scambio_retta_form.html",
        build_prestazione_template_context(request, form, prestazione=None),
    )


def modifica_prestazione_scambio_retta(request, pk):
    prestazione = get_object_or_404(
        PrestazioneScambioRetta.objects.select_related(
            "familiare",
            "famiglia",
            "studente",
            "anno_scolastico",
            "tariffa_scambio_retta",
        ),
        pk=pk,
    )

    if request.method == "POST":
        form = PrestazioneScambioRettaForm(
            request.POST,
            instance=prestazione,
            familiare_id=prestazione.familiare_id,
        )
        if form.is_valid():
            prestazione = form.save()
            messages.success(request, "Prestazione scambio retta aggiornata correttamente.")

            return_url = resolve_safe_return_url(
                request,
                build_default_prestazione_return_url(prestazione.familiare),
            )

            if "_continue" in request.POST:
                redirect_url = reverse("modifica_prestazione_scambio_retta", kwargs={"pk": prestazione.pk})
                if return_url:
                    redirect_url = f"{redirect_url}?{urlencode({'return_to': return_url})}"
                return redirect(redirect_url)

            return redirect(return_url)
    else:
        form = PrestazioneScambioRettaForm(instance=prestazione, familiare_id=prestazione.familiare_id)

    return render(
        request,
        "economia/scambio_retta/prestazione_scambio_retta_form.html",
        build_prestazione_template_context(request, form, prestazione=prestazione),
    )


def elimina_prestazione_scambio_retta(request, pk):
    prestazione = get_object_or_404(
        PrestazioneScambioRetta.objects.select_related("familiare", "studente", "anno_scolastico"),
        pk=pk,
    )
    return_url = resolve_safe_return_url(
        request,
        build_default_prestazione_return_url(prestazione.familiare),
    )

    if request.method == "POST":
        prestazione.delete()
        messages.success(request, "Prestazione scambio retta eliminata correttamente.")
        return redirect(return_url)

    return render(
        request,
        "economia/scambio_retta/prestazione_scambio_retta_confirm_delete.html",
        {
            "prestazione": prestazione,
            "return_url": return_url,
            "return_to": return_url,
            "back_label": "Torna al familiare",
        },
    )
