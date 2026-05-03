from datetime import datetime, timedelta

from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Count
from django.db.models.deletion import ProtectedError
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_time

from anagrafica.models import Documento
from economia.models import RataIscrizione
from gestione_finanziaria.models import ScadenzaPagamentoFornitore

from .data import (
    build_calendar_agenda_bundle,
    build_calendar_list_bundle,
    build_local_calendar_occurrence_record,
    serialize_calendar_entry as serialize_calendar_record,
)
from .forms import CategoriaCalendarioForm, EventoCalendarioForm, EventoCalendarioQuickCreateForm
from .models import (
    CategoriaCalendario,
    EventoCalendario,
    SYSTEM_CATEGORY_DOCUMENTS,
    SYSTEM_CATEGORY_INTERESTED_FAMILIES,
    SYSTEM_CATEGORY_RATE_DUE,
    SYSTEM_CATEGORY_SUPPLIER_DUE,
    ensure_system_calendar_categories,
)


CALENDAR_EVENTS_PER_PAGE = 12


def serialize_calendar_category(categoria, event_count=0):
    return {
        "id": categoria.pk,
        "name": categoria.nome,
        "color": categoria.colore,
        "event_count": event_count,
    }


def parse_bool(value, default=False):
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "si", "s", "yes", "on"}


def is_popup_request(request):
    return request.GET.get("popup") == "1" or request.POST.get("popup") == "1"


def render_popup_close(request, message):
    return render(request, "popup/popup_close.html", {"message": message})


def get_popup_template_context(request, extra=None):
    popup = is_popup_request(request)
    context = {
        "popup": popup,
        "base_template": "popup_base.html" if popup else "base.html",
    }
    if extra:
        context.update(extra)
    return context


def paginate_calendar_records(request, records):
    paginator = Paginator(records, CALENDAR_EVENTS_PER_PAGE)
    return paginator.get_page(request.GET.get("page"))


def build_event_list_context(request, list_bundle, *, prefix=""):
    query_params = request.GET.copy()
    query_params.pop("page", None)
    query_params.pop("popup", None)

    page_obj = paginate_calendar_records(request, list_bundle["records"])
    return {
        f"{prefix}eventi": page_obj.object_list,
        f"{prefix}eventi_page_obj": page_obj,
        f"{prefix}eventi_querystring": query_params.urlencode(),
        f"{prefix}categorie": list_bundle["categories"],
        f"{prefix}categoria": (request.GET.get("categoria") or "").strip(),
        f"{prefix}q": (request.GET.get("q") or "").strip(),
        f"{prefix}count_eventi_totali": list_bundle["count_eventi_totali"],
        f"{prefix}count_eventi_filtrati": page_obj.paginator.count,
        f"{prefix}count_intera_giornata": list_bundle["count_intera_giornata"],
        f"{prefix}count_con_orario": list_bundle["count_con_orario"],
    }


def resolve_calendar_initial_state(request):
    initial_view = (request.GET.get("view") or "month").strip().lower()
    if initial_view not in {"day", "month", "week", "year"}:
        initial_view = "month"

    initial_date = parse_date((request.GET.get("date") or "").strip()) or timezone.localdate()
    return initial_view, initial_date


def build_event_initial_from_request(request):
    initial = {
        "intera_giornata": True,
        "visibile": True,
        "attivo": True,
        "ripetizione": EventoCalendario.RIPETIZIONE_NESSUNA,
    }

    data_inizio = parse_date((request.GET.get("date") or "").strip())
    data_fine = parse_date((request.GET.get("end_date") or "").strip())
    if data_inizio:
        initial["data_inizio"] = data_inizio
        initial["data_fine"] = data_fine or data_inizio

    categoria_evento = (request.GET.get("categoria_evento") or "").strip()
    if categoria_evento.isdigit():
        initial["categoria_evento"] = int(categoria_evento)

    intera_giornata = parse_bool(request.GET.get("all_day"), default=True)
    initial["intera_giornata"] = intera_giornata

    ora_inizio = parse_time((request.GET.get("time") or "").strip())
    if ora_inizio and not intera_giornata:
        initial["ora_inizio"] = ora_inizio

        durata = (request.GET.get("duration") or "").strip()
        durata_minuti = int(durata) if durata.isdigit() else 60
        initial["durata_minuti"] = durata_minuti

        if data_inizio:
            fine_dt = datetime.combine(data_inizio, ora_inizio) + timedelta(minutes=durata_minuti)
            initial["data_fine"] = fine_dt.date()
            initial["ora_fine"] = fine_dt.time().replace(microsecond=0)

    return initial


def calendario_agenda(request):
    initial_view, initial_date = resolve_calendar_initial_state(request)
    agenda_bundle = build_calendar_agenda_bundle(user=request.user)
    list_bundle = build_calendar_list_bundle(
        categoria_filter=(request.GET.get("categoria") or "").strip(),
        query=(request.GET.get("q") or "").strip(),
        user=request.user,
    )
    calendar_records = agenda_bundle["records"]
    categorie = agenda_bundle["categories"]
    counts_by_category = agenda_bundle["counts_by_category"]
    context = {
        "calendar_entries": [serialize_calendar_record(record) for record in calendar_records],
        "calendar_categories": categorie,
        "calendar_categories_payload": [
            serialize_calendar_category(categoria, event_count=counts_by_category.get(categoria.pk, 0))
            for categoria in categorie
            if categoria.attiva
        ],
        "calendar_initial_view": initial_view,
        "calendar_initial_date": initial_date,
        "count_eventi_locali": len(calendar_records),
        "count_categorie": len(categorie),
        "count_intera_giornata": sum(1 for record in calendar_records if record["all_day"]),
        "count_con_orario": sum(1 for record in calendar_records if not record["all_day"]),
    }
    context.update(build_event_list_context(request, list_bundle, prefix="lista_"))

    return render(
        request,
        "calendario/calendario_view.html",
        context,
    )


def lista_eventi_calendario(request):
    categoria = (request.GET.get("categoria") or "").strip()
    q = (request.GET.get("q") or "").strip()
    list_bundle = build_calendar_list_bundle(categoria_filter=categoria, query=q, user=request.user)
    context = build_event_list_context(request, list_bundle)

    return render(
        request,
        "calendario/evento_list.html",
        context,
    )


def lista_categorie_calendario(request):
    system_categories = ensure_system_calendar_categories()
    auto_counts = {}

    if system_categories.get(SYSTEM_CATEGORY_RATE_DUE):
        auto_counts[system_categories[SYSTEM_CATEGORY_RATE_DUE].pk] = RataIscrizione.objects.filter(
            data_scadenza__isnull=False
        ).count()
    if system_categories.get(SYSTEM_CATEGORY_DOCUMENTS):
        auto_counts[system_categories[SYSTEM_CATEGORY_DOCUMENTS].pk] = Documento.objects.filter(
            scadenza__isnull=False
        ).count()
    if system_categories.get(SYSTEM_CATEGORY_SUPPLIER_DUE):
        auto_counts[system_categories[SYSTEM_CATEGORY_SUPPLIER_DUE].pk] = ScadenzaPagamentoFornitore.objects.filter(
            data_scadenza__isnull=False
        ).count()
    if system_categories.get(SYSTEM_CATEGORY_INTERESTED_FAMILIES):
        from famiglie_interessate.models import AttivitaFamigliaInteressata

        auto_counts[system_categories[SYSTEM_CATEGORY_INTERESTED_FAMILIES].pk] = (
            AttivitaFamigliaInteressata.objects.filter(calendarizza=True, data_programmata__isnull=False).count()
        )

    categorie = CategoriaCalendario.objects.annotate(count_eventi=Count("eventi")).order_by("ordine", "nome")
    for categoria in categorie:
        categoria.count_eventi_agenda = categoria.count_eventi + auto_counts.get(categoria.pk, 0)

    return render(
        request,
        "calendario/categoria_list.html",
        get_popup_template_context(request, {
            "categorie": categorie,
            "count_attive": categorie.filter(attiva=True).count(),
            "count_totali": categorie.count(),
        }),
    )


def crea_categoria_calendario(request):
    popup = is_popup_request(request)
    if request.method == "POST":
        form = CategoriaCalendarioForm(request.POST)
        if form.is_valid():
            categoria = form.save()
            messages.success(request, "Categoria calendario creata correttamente.")
            if popup:
                return render_popup_close(request, "Categoria calendario creata correttamente.")
            return redirect("modifica_categoria_calendario", pk=categoria.pk)
    else:
        form = CategoriaCalendarioForm()

    return render(
        request,
        "calendario/categoria_form.html",
        get_popup_template_context(request, {"form": form, "categoria_obj": None}),
    )


def modifica_categoria_calendario(request, pk):
    categoria_obj = get_object_or_404(CategoriaCalendario, pk=pk)
    popup = is_popup_request(request)

    if request.method == "POST":
        form = CategoriaCalendarioForm(request.POST, instance=categoria_obj)
        if form.is_valid():
            categoria_obj = form.save()
            messages.success(request, "Categoria calendario aggiornata correttamente.")
            if popup:
                return render_popup_close(request, "Categoria calendario aggiornata correttamente.")
            return redirect("modifica_categoria_calendario", pk=categoria_obj.pk)
    else:
        form = CategoriaCalendarioForm(instance=categoria_obj)

    return render(
        request,
        "calendario/categoria_form.html",
        get_popup_template_context(request, {"form": form, "categoria_obj": categoria_obj}),
    )


def elimina_categoria_calendario(request, pk):
    categoria_obj = get_object_or_404(CategoriaCalendario, pk=pk)
    popup = is_popup_request(request)

    if categoria_obj.is_system_category:
        messages.error(request, "Questa categoria e di sistema e non puo essere eliminata.")
        if popup:
            return render_popup_close(request, "Questa categoria e di sistema e non puo essere eliminata.")
        return redirect("modifica_categoria_calendario", pk=categoria_obj.pk)

    if request.method == "POST":
        try:
            categoria_obj.delete()
        except ProtectedError:
            messages.error(
                request,
                "Questa categoria e ancora collegata ad almeno un evento. Sposta prima gli eventi su un'altra categoria.",
            )
            if popup:
                return render_popup_close(
                    request,
                    "Questa categoria e ancora collegata ad almeno un evento.",
                )
            return redirect("modifica_categoria_calendario", pk=categoria_obj.pk)

        messages.success(request, "Categoria calendario eliminata correttamente.")
        if popup:
            return render_popup_close(request, "Categoria calendario eliminata correttamente.")
        return redirect("lista_categorie_calendario")

    return render(
        request,
        "calendario/categoria_confirm_delete.html",
        get_popup_template_context(request, {"categoria_obj": categoria_obj}),
    )


def crea_evento_calendario(request):
    popup = is_popup_request(request)
    if request.method == "POST":
        form = EventoCalendarioForm(request.POST)
        if form.is_valid():
            evento = form.save(commit=False)
            if request.user.is_authenticated:
                evento.creato_da = request.user
                evento.aggiornato_da = request.user
            evento.save()
            messages.success(request, "Evento calendario creato correttamente.")
            if popup:
                return render_popup_close(request, "Evento calendario creato correttamente.")
            return redirect("modifica_evento_calendario", pk=evento.pk)
    else:
        form = EventoCalendarioForm(initial=build_event_initial_from_request(request))

    return render(
        request,
        "calendario/evento_form.html",
        get_popup_template_context(request, {"form": form, "evento": None}),
    )


def crea_evento_calendario_rapido(request):
    if request.method != "POST":
        return JsonResponse({"success": False, "errors": ["Metodo non consentito."]}, status=405)

    form = EventoCalendarioQuickCreateForm(request.POST)
    if not form.is_valid():
        serialized_errors = {
            field: [str(error) for error in errors]
            for field, errors in form.errors.items()
        }
        error_messages = []
        for errors in serialized_errors.values():
            error_messages.extend(errors)
        return JsonResponse(
            {
                "success": False,
                "errors": serialized_errors,
                "error_messages": error_messages,
            },
            status=400,
        )

    evento = form.save(commit=False)
    if request.user.is_authenticated:
        evento.creato_da = request.user
        evento.aggiornato_da = request.user
    evento.save()

    return JsonResponse(
        {
            "success": True,
            "message": "Evento creato correttamente.",
            "entry": serialize_calendar_record(
                build_local_calendar_occurrence_record(
                    evento,
                    {
                        "index": 0,
                        "start_date": evento.data_inizio,
                        "end_date": evento.data_fine,
                    },
                )
            ),
            "event_url": reverse("modifica_evento_calendario", kwargs={"pk": evento.pk}),
        }
    )


def modifica_evento_calendario(request, pk):
    evento = get_object_or_404(EventoCalendario.objects.select_related("categoria_evento"), pk=pk)
    popup = is_popup_request(request)

    if request.method == "POST":
        form = EventoCalendarioForm(request.POST, instance=evento)
        if form.is_valid():
            evento = form.save(commit=False)
            if request.user.is_authenticated:
                evento.aggiornato_da = request.user
            evento.save()
            messages.success(request, "Evento calendario aggiornato correttamente.")
            if popup:
                return render_popup_close(request, "Evento calendario aggiornato correttamente.")
            return redirect("modifica_evento_calendario", pk=evento.pk)
    else:
        form = EventoCalendarioForm(instance=evento)

    return render(
        request,
        "calendario/evento_form.html",
        get_popup_template_context(request, {"form": form, "evento": evento}),
    )


def elimina_evento_calendario(request, pk):
    evento = get_object_or_404(EventoCalendario, pk=pk)
    popup = is_popup_request(request)

    if request.method == "POST":
        evento.delete()
        messages.success(request, "Evento calendario eliminato correttamente.")
        if popup:
            return render_popup_close(request, "Evento calendario eliminato correttamente.")
        return redirect("lista_eventi_calendario")

    return render(
        request,
        "calendario/evento_confirm_delete.html",
        get_popup_template_context(request, {"evento": evento}),
    )
