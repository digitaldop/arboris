from django.contrib import messages
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, Prefetch, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from scuola.models import AnnoScolastico
from sistema.models import LivelloPermesso
from sistema.permissions import user_has_module_permission

from .forms import (
    AttivitaFamigliaInteressataForm,
    FamigliaInteressataForm,
    MinoreInteressatoFormSet,
    ReferenteFamigliaInteressataFormSet,
)
from .models import (
    AttivitaFamigliaInteressata,
    FamigliaInteressata,
    FonteContattoFamigliaInteressata,
    PrioritaFamigliaInteressata,
    StatoAttivitaFamigliaInteressata,
    StatoFamigliaInteressata,
)


FAMIGLIE_INTERESSATE_PER_PAGE = 20


def is_popup_request(request):
    return request.GET.get("popup") == "1" or request.POST.get("popup") == "1"


def popup_response(request, message):
    return render(request, "popup/popup_close.html", {"message": message})


def get_popup_context(request, extra=None):
    popup = is_popup_request(request)
    context = {
        "popup": popup,
        "base_template": "popup_base.html" if popup else "base.html",
        "can_manage_famiglie_interessate": user_has_module_permission(
            request.user,
            "famiglie_interessate",
            LivelloPermesso.GESTIONE,
        ),
    }
    if extra:
        context.update(extra)
    return context


def filtered_famiglie_interessate_queryset(request):
    q = (request.GET.get("q") or "").strip()
    stato = (request.GET.get("stato") or "").strip()
    priorita = (request.GET.get("priorita") or "").strip()
    fonte = (request.GET.get("fonte") or "").strip()
    anno = (request.GET.get("anno") or "").strip()
    followup = (request.GET.get("followup") or "").strip()

    pending_activities = AttivitaFamigliaInteressata.objects.filter(
        stato=StatoAttivitaFamigliaInteressata.PROGRAMMATA,
        data_programmata__isnull=False,
    ).order_by("data_programmata", "id")

    queryset = (
        FamigliaInteressata.objects.select_related("anno_scolastico_interesse", "convertita_in_famiglia")
        .annotate(
            count_referenti=Count("referenti", distinct=True),
            count_minori=Count("minori", distinct=True),
            count_attivita=Count("attivita", distinct=True),
        )
        .prefetch_related(Prefetch("attivita", queryset=pending_activities, to_attr="attivita_programmate"))
    )

    if q:
        queryset = queryset.filter(
            Q(nome__icontains=q)
            | Q(referente_principale__icontains=q)
            | Q(telefono__icontains=q)
            | Q(email__icontains=q)
            | Q(note__icontains=q)
            | Q(referenti__nome__icontains=q)
            | Q(referenti__telefono__icontains=q)
            | Q(referenti__email__icontains=q)
            | Q(minori__nome__icontains=q)
            | Q(minori__cognome__icontains=q)
        ).distinct()

    if stato in {value for value, _label in StatoFamigliaInteressata.choices}:
        queryset = queryset.filter(stato=stato)
    if priorita in {value for value, _label in PrioritaFamigliaInteressata.choices}:
        queryset = queryset.filter(priorita=priorita)
    if fonte in {value for value, _label in FonteContattoFamigliaInteressata.choices}:
        queryset = queryset.filter(fonte_contatto=fonte)
    if anno.isdigit():
        queryset = queryset.filter(anno_scolastico_interesse_id=int(anno))

    today_start = timezone.localtime().replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = today_start.replace(hour=23, minute=59, second=59)
    if followup == "scaduti":
        queryset = queryset.filter(
            attivita__stato=StatoAttivitaFamigliaInteressata.PROGRAMMATA,
            attivita__data_programmata__lt=today_start,
        ).distinct()
    elif followup == "oggi":
        queryset = queryset.filter(
            attivita__stato=StatoAttivitaFamigliaInteressata.PROGRAMMATA,
            attivita__data_programmata__range=(today_start, today_end),
        ).distinct()
    elif followup == "programmati":
        queryset = queryset.filter(
            attivita__stato=StatoAttivitaFamigliaInteressata.PROGRAMMATA,
            attivita__data_programmata__isnull=False,
        ).distinct()

    return queryset.order_by("-data_aggiornamento", "-id")


def lista_famiglie_interessate(request):
    queryset = filtered_famiglie_interessate_queryset(request)
    paginator = Paginator(queryset, FAMIGLIE_INTERESSATE_PER_PAGE)
    page_obj = paginator.get_page(request.GET.get("page"))
    famiglie = list(page_obj.object_list)

    for famiglia in famiglie:
        famiglia.prossima_attivita = famiglia.attivita_programmate[0] if famiglia.attivita_programmate else None

    base_queryset = FamigliaInteressata.objects.all()
    now = timezone.now()
    riepilogo_attivita = AttivitaFamigliaInteressata.objects.aggregate(
        count_programmate=Count("id", filter=Q(stato=StatoAttivitaFamigliaInteressata.PROGRAMMATA)),
        count_scadute=Count(
            "id",
            filter=Q(stato=StatoAttivitaFamigliaInteressata.PROGRAMMATA, data_programmata__lt=now),
        ),
    )

    querystring = request.GET.copy()
    querystring.pop("page", None)

    return render(
        request,
        "famiglie_interessate/famiglia_list.html",
        {
            "famiglie": famiglie,
            "page_obj": page_obj,
            "famiglie_querystring": querystring.urlencode(),
            "count_totale": base_queryset.count(),
            "count_in_lavorazione": base_queryset.exclude(
                stato__in=[
                    StatoFamigliaInteressata.CONVERTITA,
                    StatoFamigliaInteressata.ARCHIVIATA,
                    StatoFamigliaInteressata.NON_INTERESSATA,
                ]
            ).count(),
            "count_convertite": base_queryset.filter(stato=StatoFamigliaInteressata.CONVERTITA).count(),
            "count_followup_scaduti": riepilogo_attivita["count_scadute"] or 0,
            "count_followup_programmati": riepilogo_attivita["count_programmate"] or 0,
            "q": (request.GET.get("q") or "").strip(),
            "stato": (request.GET.get("stato") or "").strip(),
            "priorita": (request.GET.get("priorita") or "").strip(),
            "fonte": (request.GET.get("fonte") or "").strip(),
            "anno": (request.GET.get("anno") or "").strip(),
            "followup": (request.GET.get("followup") or "").strip(),
            "stati": StatoFamigliaInteressata.choices,
            "priorita_choices": PrioritaFamigliaInteressata.choices,
            "fonti": FonteContattoFamigliaInteressata.choices,
            "anni_scolastici": AnnoScolastico.objects.order_by("-data_inizio", "-id"),
        },
    )


def build_famiglia_form_context(request, famiglia, form, referenti_formset, minori_formset, *, is_new=False):
    attivita = []
    if famiglia and famiglia.pk:
        attivita = list(
            famiglia.attivita.select_related("assegnata_a", "creata_da").order_by(
                "-data_programmata",
                "-data_creazione",
                "-id",
            )
        )

    return get_popup_context(
        request,
        {
            "famiglia": famiglia,
            "form": form,
            "referenti_formset": referenti_formset,
            "minori_formset": minori_formset,
            "attivita": attivita,
            "is_new": is_new,
            "has_form_errors": bool(
                form.errors
                or referenti_formset.total_error_count()
                or minori_formset.total_error_count()
            ),
        },
    )


def crea_famiglia_interessata(request):
    if request.method == "POST":
        form = FamigliaInteressataForm(request.POST)
        referenti_formset = ReferenteFamigliaInteressataFormSet(request.POST, prefix="referenti")
        minori_formset = MinoreInteressatoFormSet(request.POST, prefix="minori")

        if form.is_valid() and referenti_formset.is_valid() and minori_formset.is_valid():
            with transaction.atomic():
                famiglia = form.save(commit=False)
                famiglia.creata_da = request.user
                famiglia.aggiornata_da = request.user
                famiglia.save()
                referenti_formset.instance = famiglia
                minori_formset.instance = famiglia
                referenti_formset.save()
                minori_formset.save()
            messages.success(request, "Famiglia interessata creata correttamente.")
            if is_popup_request(request):
                return popup_response(request, "Famiglia interessata creata correttamente.")
            return redirect("modifica_famiglia_interessata", pk=famiglia.pk)
    else:
        form = FamigliaInteressataForm()
        referenti_formset = ReferenteFamigliaInteressataFormSet(prefix="referenti")
        minori_formset = MinoreInteressatoFormSet(prefix="minori")

    return render(
        request,
        "famiglie_interessate/famiglia_form.html",
        build_famiglia_form_context(request, None, form, referenti_formset, minori_formset, is_new=True),
    )


def modifica_famiglia_interessata(request, pk):
    famiglia = get_object_or_404(
        FamigliaInteressata.objects.select_related(
            "anno_scolastico_interesse",
            "convertita_in_famiglia",
            "creata_da",
            "aggiornata_da",
        ),
        pk=pk,
    )

    if request.method == "POST":
        form = FamigliaInteressataForm(request.POST, instance=famiglia)
        referenti_formset = ReferenteFamigliaInteressataFormSet(
            request.POST,
            instance=famiglia,
            prefix="referenti",
        )
        minori_formset = MinoreInteressatoFormSet(
            request.POST,
            instance=famiglia,
            prefix="minori",
        )
        if form.is_valid() and referenti_formset.is_valid() and minori_formset.is_valid():
            with transaction.atomic():
                famiglia = form.save(commit=False)
                famiglia.aggiornata_da = request.user
                famiglia.save()
                referenti_formset.save()
                minori_formset.save()
            messages.success(request, "Famiglia interessata aggiornata correttamente.")
            if is_popup_request(request):
                return popup_response(request, "Famiglia interessata aggiornata correttamente.")
            return redirect("modifica_famiglia_interessata", pk=famiglia.pk)
    else:
        form = FamigliaInteressataForm(instance=famiglia)
        referenti_formset = ReferenteFamigliaInteressataFormSet(instance=famiglia, prefix="referenti")
        minori_formset = MinoreInteressatoFormSet(instance=famiglia, prefix="minori")

    return render(
        request,
        "famiglie_interessate/famiglia_form.html",
        build_famiglia_form_context(request, famiglia, form, referenti_formset, minori_formset),
    )


def crea_attivita_famiglia_interessata(request, pk):
    famiglia = get_object_or_404(FamigliaInteressata, pk=pk)

    initial = {}
    if request.GET.get("followup") == "1":
        initial["tipo"] = "follow_up"
        initial["stato"] = StatoAttivitaFamigliaInteressata.PROGRAMMATA
        initial["calendarizza"] = True

    if request.method == "POST":
        form = AttivitaFamigliaInteressataForm(request.POST)
        if form.is_valid():
            attivita = form.save(commit=False)
            attivita.famiglia = famiglia
            attivita.creata_da = request.user
            attivita.save()
            messages.success(request, "Attivita salvata correttamente.")
            if is_popup_request(request):
                return popup_response(request, "Attivita salvata correttamente.")
            return redirect("modifica_famiglia_interessata", pk=famiglia.pk)
    else:
        form = AttivitaFamigliaInteressataForm(initial=initial)

    return render(
        request,
        "famiglie_interessate/attivita_form.html",
        get_popup_context(
            request,
            {
                "form": form,
                "famiglia": famiglia,
                "attivita": None,
                "is_new": True,
            },
        ),
    )


def modifica_attivita_famiglia_interessata(request, pk):
    attivita = get_object_or_404(
        AttivitaFamigliaInteressata.objects.select_related("famiglia", "assegnata_a"),
        pk=pk,
    )
    famiglia = attivita.famiglia

    if request.method == "POST":
        form = AttivitaFamigliaInteressataForm(request.POST, instance=attivita)
        if form.is_valid():
            form.save()
            messages.success(request, "Attivita aggiornata correttamente.")
            if is_popup_request(request):
                return popup_response(request, "Attivita aggiornata correttamente.")
            return redirect("modifica_famiglia_interessata", pk=famiglia.pk)
    else:
        form = AttivitaFamigliaInteressataForm(instance=attivita)

    return render(
        request,
        "famiglie_interessate/attivita_form.html",
        get_popup_context(
            request,
            {
                "form": form,
                "famiglia": famiglia,
                "attivita": attivita,
                "is_new": False,
                "return_url": reverse("modifica_famiglia_interessata", kwargs={"pk": famiglia.pk}),
            },
        ),
    )
