import base64
import binascii
import json
import logging
import re
from pathlib import Path

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login as auth_login
from django.contrib.auth import logout as auth_logout
from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.mail import send_mail
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.http import FileResponse, HttpResponseBadRequest, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from .inline_context import scuola_inline_head
from .forms import (
    ArborisAuthenticationForm,
    FeedbackSegnalazioneForm,
    SistemaBackupDatabaseConfigurazioneForm,
    SistemaBackupDatabaseRestoreConfirmForm,
    SistemaBackupDatabaseUploadForm,
    SistemaImpostazioniGeneraliForm,
    ScuolaForm,
    ScuolaSocialFormSet,
    ScuolaTelefonoFormSet,
    ScuolaEmailFormSet,
    SistemaRuoloPermessiForm,
    SistemaUtenteForm,
)
from .database_backups import (
    DatabaseBackupError,
    cancel_or_delete_restore_job,
    create_database_backup,
    create_restore_job_from_backup_record,
    create_restore_job_from_local_file,
    create_restore_job_from_upload,
    delete_pending_restore_upload,
    get_pending_restore_root,
    get_backup_configuration,
    restore_file_reference_exists,
)
from .restore_scheduler import schedule_restore_job
from .models import (
    AzioneOperazioneCronologia,
    FeedbackSegnalazione,
    LivelloPermesso,
    MODULE_TOGGLE_DEFINITIONS,
    ModuloOperazioneCronologia,
    Scuola,
    SistemaDatabaseBackup,
    SistemaDatabaseRestoreJob,
    SistemaImpostazioniGenerali,
    SistemaOperazioneCronologia,
    SistemaRuoloPermessi,
    SistemaUtentePermessi,
    StatoFeedbackSegnalazione,
    StatoRipristinoDatabase,
    TipoFeedbackSegnalazione,
)
from anagrafica.dati_base_import import (
    default_gi_file_path,
    default_nazioni_belfiore_file_path,
    run_import_dati_base,
    run_import_nazioni_belfiore,
)

from .active_toggles import get_active_toggle_config, get_active_toggle_model
from .audit_retention import cleanup_cronologia_operazioni
from .permissions import (
    authenticated_user_required,
    get_user_permission_profile,
    operational_admin_required,
    user_has_module_permission,
)


PENDING_RESTORE_SESSION_KEY = "sistema_database_backup_pending_restore"
PENDING_RESTORE_JOB_SESSION_KEY = "sistema_db_restore_job_id"
RESTORE_CHUNKED_UPLOAD_ID_RE = re.compile(r"^[A-Za-z0-9_-]{8,80}$")
RESTORE_CHUNK_MAX_BYTES = 768 * 1024
CRONOLOGIA_RESULT_LIMIT = 250
FEEDBACK_PER_PAGE = 20
GLOBAL_SEARCH_MIN_QUERY_LENGTH = 2
GLOBAL_SEARCH_MAX_RESULTS = 12
logger = logging.getLogger(__name__)


def parse_toggle_bool(value):
    return str(value or "").strip().lower() in {"1", "true", "on", "yes", "si"}


def json_or_redirect(request, payload, *, status=200, fallback_url=None, message_level=None):
    if request.POST.get("ajax") == "1" or request.headers.get("x-requested-with") == "XMLHttpRequest":
        return JsonResponse(payload, status=status)

    if message_level and payload.get("message"):
        getattr(messages, message_level)(request, payload["message"])

    redirect_url = fallback_url or request.POST.get("next") or ""
    if not redirect_url or not url_has_allowed_host_and_scheme(
        redirect_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        redirect_url = "home"
    return redirect(redirect_url)


def compact_join(parts, separator=" - "):
    return separator.join(str(part).strip() for part in parts if str(part or "").strip())


def search_result(category, title, url, *, subtitle="", module="", icon="search"):
    return {
        "category": category,
        "title": title,
        "subtitle": subtitle,
        "url": url,
        "module": module,
        "icon": icon,
    }


def append_limited_results(results, items, remaining):
    if remaining <= 0:
        return
    results.extend(items[:remaining])


@authenticated_user_required
@require_POST
def toggle_active_state(request):
    model_label = request.POST.get("model")
    object_id = request.POST.get("pk")
    field_name = request.POST.get("field")
    config = get_active_toggle_config(model_label, field_name=field_name)
    if not config:
        return HttpResponseBadRequest("Toggle non configurato.")

    if not user_has_module_permission(
        request.user,
        config.module_name,
        level=LivelloPermesso.GESTIONE,
    ):
        raise PermissionDenied("Non hai i permessi necessari per modificare questo stato.")

    model_cls = get_active_toggle_model(config)
    if model_cls is None:
        return HttpResponseBadRequest("Modello non disponibile.")

    obj = get_object_or_404(model_cls, pk=object_id)
    previous_value = bool(getattr(obj, config.field_name))
    new_value = parse_toggle_bool(request.POST.get("value"))
    setattr(obj, config.field_name, new_value)

    try:
        obj.clean()
        update_fields = [config.field_name]
        if any(field.name == "data_aggiornamento" for field in obj._meta.fields):
            update_fields.append("data_aggiornamento")
        obj.save(update_fields=update_fields)
    except ValidationError as exc:
        setattr(obj, config.field_name, previous_value)
        message = "; ".join(exc.messages) if hasattr(exc, "messages") else str(exc)
        return json_or_redirect(
            request,
            {"ok": False, "value": previous_value, "message": message},
            status=400,
            message_level="error",
        )

    label = "attivo" if new_value else "non attivo"
    message = f"Stato aggiornato: {obj} e' ora {label}."
    return json_or_redirect(
        request,
        {"ok": True, "value": new_value, "message": message},
        message_level="success",
    )


def build_anagrafica_global_search_results(query, remaining):
    from anagrafica.family_logic import (
        iter_logical_family_snapshots,
        logical_family_detail_url,
        logical_family_matches,
        logical_family_summary_for_person,
    )
    from anagrafica.models import Documento, Familiare, Studente

    results = []
    terms = [term for term in query.split() if term]

    famiglie = []
    for snapshot in iter_logical_family_snapshots():
        if logical_family_matches(snapshot, query) or any(
            logical_family_matches(snapshot, term) for term in terms
        ):
            famiglie.append(snapshot)
        if len(famiglie) >= 4:
            break

    results.extend(
        search_result(
            "Famiglia",
            famiglia.cognome_famiglia,
            logical_family_detail_url(famiglia),
            subtitle=compact_join(
                [
                    famiglia.indirizzo_principale.label_full() if famiglia.indirizzo_principale else "",
                    famiglia.label_contesto_anagrafica(),
                ]
            ),
            module="Anagrafica",
            icon="family",
        )
        for famiglia in famiglie
    )

    person_filter = Q(nome__icontains=query) | Q(cognome__icontains=query) | Q(codice_fiscale__icontains=query)
    if len(terms) >= 2:
        first, second = terms[0], terms[1]
        person_filter |= (Q(nome__icontains=first) & Q(cognome__icontains=second))
        person_filter |= (Q(cognome__icontains=first) & Q(nome__icontains=second))

    studenti = (
        Studente.objects.filter(
            person_filter
            | Q(relazioni_familiari__attivo=True, relazioni_familiari__familiare__persona__nome__icontains=query)
            | Q(relazioni_familiari__attivo=True, relazioni_familiari__familiare__persona__cognome__icontains=query)
        )
        .distinct()
        .order_by("cognome", "nome", "id")[:4]
    )
    results.extend(
        search_result(
            "Studente",
            str(studente),
            reverse("modifica_studente", kwargs={"pk": studente.pk}),
            subtitle=logical_family_summary_for_person(studente)["context"],
            module="Anagrafica",
            icon="student",
        )
        for studente in studenti
    )

    familiari = (
        Familiare.objects.filter(
            person_filter
            | Q(email__icontains=query)
            | Q(telefono__icontains=query)
            | Q(relazioni_studenti__attivo=True, relazioni_studenti__studente__nome__icontains=query)
            | Q(relazioni_studenti__attivo=True, relazioni_studenti__studente__cognome__icontains=query)
        )
        .select_related("persona", "relazione_familiare")
        .distinct()
        .order_by("cognome", "nome", "id")[:3]
    )
    results.extend(
        search_result(
            "Familiare",
            str(familiare),
            reverse("modifica_familiare", kwargs={"pk": familiare.pk}),
            subtitle=compact_join([familiare.relazione_familiare, logical_family_summary_for_person(familiare)["label"]]),
            module="Anagrafica",
            icon="user",
        )
        for familiare in familiari
    )

    documenti = (
        Documento.objects.filter(
            Q(tipo_documento__tipo_documento__icontains=query)
            | Q(descrizione__icontains=query)
            | Q(file__icontains=query)
            | Q(familiare__persona__nome__icontains=query)
            | Q(familiare__persona__cognome__icontains=query)
            | Q(studente__nome__icontains=query)
            | Q(studente__cognome__icontains=query)
        )
        .select_related("tipo_documento", "familiare__persona", "studente")
        .order_by("-data_caricamento", "-id")[:3]
    )
    for documento in documenti:
        owner_label = ""
        owner_url = documento.download_url
        if documento.familiare_id:
            owner_label = f"Familiare {documento.familiare}"
            owner_url = reverse("modifica_familiare", kwargs={"pk": documento.familiare_id})
        elif documento.studente_id:
            owner_label = f"Studente {documento.studente}"
            owner_url = reverse("modifica_studente", kwargs={"pk": documento.studente_id})
        results.append(
            search_result(
                "Documento",
                str(documento),
                owner_url,
                subtitle=compact_join([owner_label, documento.scadenza.strftime("%d/%m/%Y") if documento.scadenza else ""]),
                module="Anagrafica",
                icon="file-text",
            )
        )

    return results[:remaining]


def build_interested_families_global_search_results(query, remaining):
    from famiglie_interessate.models import FamigliaInteressata

    famiglie = (
        FamigliaInteressata.objects.filter(
            Q(nome__icontains=query)
            | Q(referente_principale__icontains=query)
            | Q(telefono__icontains=query)
            | Q(email__icontains=query)
            | Q(minori__nome__icontains=query)
            | Q(minori__cognome__icontains=query)
        )
        .distinct()
        .order_by("-data_aggiornamento", "-id")[:remaining]
    )
    return [
        search_result(
            "Famiglia interessata",
            famiglia.nome_display,
            reverse("modifica_famiglia_interessata", kwargs={"pk": famiglia.pk}),
            subtitle=compact_join([famiglia.get_stato_display(), famiglia.contatto_display]),
            module="Famiglie interessate",
            icon="family",
        )
        for famiglia in famiglie
    ]


def build_calendar_global_search_results(query, remaining):
    from calendario.models import EventoCalendario

    eventi = (
        EventoCalendario.objects.filter(
            Q(titolo__icontains=query)
            | Q(tipologia__icontains=query)
            | Q(luogo__icontains=query)
            | Q(descrizione__icontains=query)
            | Q(categoria_evento__nome__icontains=query)
        )
        .select_related("categoria_evento")
        .order_by("data_inizio", "ora_inizio", "titolo")[:remaining]
    )
    return [
        search_result(
            "Evento calendario",
            evento.titolo,
            reverse("modifica_evento_calendario", kwargs={"pk": evento.pk}),
            subtitle=compact_join([evento.categoria_evento.nome, evento.data_inizio.strftime("%d/%m/%Y"), evento.luogo]),
            module="Calendario",
            icon="calendar",
        )
        for evento in eventi
    ]


def build_financial_global_search_results(query, remaining):
    from gestione_finanziaria.models import DocumentoFornitore, Fornitore, MovimentoFinanziario

    results = []
    fornitori = (
        Fornitore.objects.filter(
            Q(denominazione__icontains=query)
            | Q(codice_fiscale__icontains=query)
            | Q(partita_iva__icontains=query)
            | Q(email__icontains=query)
            | Q(telefono__icontains=query)
            | Q(referente__icontains=query)
        )
        .select_related("categoria_spesa")
        .order_by("denominazione", "id")[:4]
    )
    results.extend(
        search_result(
            "Fornitore",
            fornitore.denominazione,
            reverse("modifica_fornitore", kwargs={"pk": fornitore.pk}),
            subtitle=compact_join([getattr(fornitore.categoria_spesa, "nome", ""), fornitore.email or fornitore.telefono]),
            module="Gestione finanziaria",
            icon="building",
        )
        for fornitore in fornitori
    )

    documenti = (
        DocumentoFornitore.objects.filter(
            Q(numero_documento__icontains=query)
            | Q(descrizione__icontains=query)
            | Q(fornitore__denominazione__icontains=query)
            | Q(external_id__icontains=query)
            | Q(note__icontains=query)
        )
        .select_related("fornitore", "categoria_spesa")
        .order_by("-data_documento", "-id")[:4]
    )
    results.extend(
        search_result(
            "Fattura fornitore",
            compact_join([documento.get_tipo_documento_display(), documento.numero_documento]),
            reverse("modifica_documento_fornitore", kwargs={"pk": documento.pk}),
            subtitle=compact_join([
                documento.fornitore.denominazione,
                documento.data_documento.strftime("%d/%m/%Y"),
                f"EUR {documento.totale}",
            ]),
            module="Gestione finanziaria",
            icon="file-text",
        )
        for documento in documenti
    )

    movimenti = (
        MovimentoFinanziario.objects.filter(
            Q(descrizione__icontains=query)
            | Q(note__icontains=query)
            | Q(conto__nome_conto__icontains=query)
            | Q(categoria__nome__icontains=query)
        )
        .select_related("conto", "categoria")
        .order_by("-data_contabile", "-id")[:3]
    )
    results.extend(
        search_result(
            "Movimento bancario",
            movimento.descrizione or f"Movimento {movimento.pk}",
            reverse("modifica_movimento_finanziario", kwargs={"pk": movimento.pk}),
            subtitle=compact_join([
                movimento.data_contabile.strftime("%d/%m/%Y") if movimento.data_contabile else "",
                getattr(movimento.conto, "nome_conto", ""),
                f"EUR {movimento.importo}",
            ]),
            module="Gestione finanziaria",
            icon="wallet",
        )
        for movimento in movimenti
    )

    return results[:remaining]


def build_global_search_results(user, query, limit=GLOBAL_SEARCH_MAX_RESULTS):
    results = []
    query = (query or "").strip()
    if len(query) < GLOBAL_SEARCH_MIN_QUERY_LENGTH:
        return results

    search_plan = (
        ("anagrafica", build_anagrafica_global_search_results),
        ("famiglie_interessate", build_interested_families_global_search_results),
        ("calendario", build_calendar_global_search_results),
        ("gestione_finanziaria", build_financial_global_search_results),
    )

    for module_name, builder in search_plan:
        remaining = limit - len(results)
        if remaining <= 0:
            break
        if not user_has_module_permission(user, module_name, LivelloPermesso.VISUALIZZAZIONE):
            continue
        append_limited_results(results, builder(query, remaining), remaining)

    return results[:limit]


@authenticated_user_required
def ricerca_globale_sistema(request):
    query = (request.GET.get("q") or "").strip()
    results = build_global_search_results(request.user, query)
    return JsonResponse(
        {
            "ok": True,
            "query": query,
            "min_length": GLOBAL_SEARCH_MIN_QUERY_LENGTH,
            "count": len(results),
            "results": results,
        }
    )


def sync_user_profiles_for_role(ruolo):
    SistemaUtentePermessi.objects.filter(ruolo_permessi=ruolo).update(
        ruolo=ruolo.chiave_legacy or "",
        controllo_completo=ruolo.controllo_completo,
        permesso_anagrafica=ruolo.permesso_anagrafica,
        permesso_famiglie_interessate=ruolo.permesso_famiglie_interessate,
        permesso_economia=ruolo.permesso_economia,
        permesso_sistema=ruolo.permesso_sistema,
        permesso_calendario=ruolo.permesso_calendario,
        permesso_gestione_finanziaria=ruolo.permesso_gestione_finanziaria,
        permesso_gestione_amministrativa=ruolo.permesso_gestione_amministrativa,
        permesso_servizi_extra=ruolo.permesso_servizi_extra,
    )


def resolve_safe_next_url(request, fallback_url_name="home"):
    next_url = (
        request.POST.get("next")
        or request.GET.get("next")
        or ""
    ).strip()
    if next_url and url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
        return next_url
    return reverse(fallback_url_name)


def feedback_user_label(user):
    if not user or not user.is_authenticated:
        return ""
    return user.get_full_name().strip() or user.email or user.username


def feedback_user_role_label(user):
    if not user or not user.is_authenticated:
        return ""
    profilo = get_user_permission_profile(user)
    if profilo and profilo.ruolo_display:
        return profilo.ruolo_display
    if user.is_superuser:
        return "Superuser"
    if user.is_staff:
        return "Staff tecnico"
    return "Utente"


def feedback_client_ip(request):
    forwarded_for = (request.META.get("HTTP_X_FORWARDED_FOR") or "").split(",")[0].strip()
    return forwarded_for or request.META.get("REMOTE_ADDR") or None


def feedback_email_subject(feedback):
    tipo_label = "Bug" if feedback.tipo == TipoFeedbackSegnalazione.BUG else "Funzione"
    pagina = feedback.pagina_titolo or feedback.pagina_path or "Pagina non specificata"
    return f"[Arboris Beta][{tipo_label}] {pagina[:110]}"


def feedback_email_body(feedback):
    return "\n".join(
        [
            "Nuova segnalazione beta Arboris",
            "",
            f"Tipo: {feedback.get_tipo_display()}",
            f"Data invio: {timezone.localtime(feedback.data_creazione):%d/%m/%Y %H:%M:%S}",
            "",
            "Utente",
            f"- Nome: {feedback.utente_nome or '-'}",
            f"- Email: {feedback.utente_email or '-'}",
            f"- Ruolo: {feedback.utente_ruolo or '-'}",
            f"- ID utente: {feedback.utente_id or '-'}",
            f"- IP: {feedback.ip_address or '-'}",
            "",
            "Punto del software",
            f"- Titolo pagina: {feedback.pagina_titolo or '-'}",
            f"- URL: {feedback.pagina_url or '-'}",
            f"- Path: {feedback.pagina_path or '-'}",
            f"- Breadcrumb: {feedback.breadcrumb or '-'}",
            f"- Referer: {feedback.referer or '-'}",
            f"- Browser: {feedback.user_agent or '-'}",
            "",
            "Messaggio",
            feedback.messaggio,
        ]
    )


def invia_email_feedback(feedback):
    recipient = (
        getattr(settings, "BETA_FEEDBACK_RECIPIENT_EMAIL", "")
        or "gliptica.software@gmail.com"
    ).strip()
    feedback.email_destinatario = recipient
    feedback.save(update_fields=["email_destinatario", "data_aggiornamento"])

    try:
        send_mail(
            feedback_email_subject(feedback),
            feedback_email_body(feedback),
            getattr(settings, "DEFAULT_FROM_EMAIL", "webmaster@localhost"),
            [recipient],
            fail_silently=False,
        )
    except Exception as exc:  # noqa: BLE001 - il feedback non deve andare perso se l'e-mail fallisce.
        feedback.email_errore = str(exc)
        feedback.save(update_fields=["email_errore", "data_aggiornamento"])
        return False

    feedback.email_inviata_at = timezone.now()
    feedback.email_errore = ""
    feedback.save(update_fields=["email_inviata_at", "email_errore", "data_aggiornamento"])
    return True


@authenticated_user_required
@require_POST
def crea_feedback_beta(request):
    form = FeedbackSegnalazioneForm(request.POST)
    if not form.is_valid():
        return JsonResponse(
            {
                "ok": False,
                "errors": form.errors.get_json_data(),
                "message": "Controlla il messaggio e riprova.",
            },
            status=400,
        )

    feedback = form.save(commit=False)
    feedback.utente = request.user
    feedback.utente_nome = feedback_user_label(request.user)
    feedback.utente_email = request.user.email or request.user.username
    feedback.utente_ruolo = feedback_user_role_label(request.user)
    feedback.user_agent = request.META.get("HTTP_USER_AGENT", "")
    feedback.referer = request.META.get("HTTP_REFERER", "")
    feedback.ip_address = feedback_client_ip(request)
    feedback.email_destinatario = (
        getattr(settings, "BETA_FEEDBACK_RECIPIENT_EMAIL", "")
        or "gliptica.software@gmail.com"
    ).strip()
    feedback.save()
    email_sent = invia_email_feedback(feedback)

    return JsonResponse(
        {
            "ok": True,
            "email_sent": email_sent,
            "message": "Segnalazione inviata. Grazie!",
        }
    )


def login_view(request):
    if getattr(request.user, "is_authenticated", False):
        return redirect(resolve_safe_next_url(request))

    form = ArborisAuthenticationForm(request, data=request.POST or None)
    next_url = resolve_safe_next_url(request)

    if request.method == "POST" and form.is_valid():
        auth_login(request, form.get_user())
        if form.cleaned_data.get("remember_me"):
            request.session.set_expiry(None)
        else:
            request.session.set_expiry(0)
        messages.success(request, "Accesso eseguito correttamente.")
        return redirect(next_url)

    response = render(
        request,
        "sistema/login.html",
        {
            "form": form,
            "next_url": next_url,
        },
    )
    response["Cache-Control"] = "no-store"
    return response


def logout_view(request):
    if getattr(request.user, "is_authenticated", False):
        auth_logout(request)
        messages.info(request, "Hai effettuato il logout.")
    return redirect("login")


def resolve_inline_target(request, allowed_targets):
    edit_scope = request.POST.get("_edit_scope") or "full"
    inline_target = (request.POST.get("_inline_target") or "").strip()

    if edit_scope != "inline" or inline_target not in allowed_targets:
        return edit_scope, None

    return edit_scope, inline_target


def scuola_sistema(request):
    scuola = Scuola.objects.first()
    edit_scope = "view" if scuola else "full"
    inline_target = "telefoni"

    if request.method == "POST":
        edit_scope, inline_target = resolve_inline_target(
            request,
            {"socials", "telefoni", "email"},
        )
        form = ScuolaForm(request.POST, instance=scuola)
        socials_formset = (
            ScuolaSocialFormSet(request.POST, instance=scuola, prefix="socials")
            if inline_target in (None, "socials")
            else ScuolaSocialFormSet(instance=scuola, prefix="socials")
        )
        telefoni_formset = (
            ScuolaTelefonoFormSet(request.POST, instance=scuola, prefix="telefoni")
            if inline_target in (None, "telefoni")
            else ScuolaTelefonoFormSet(instance=scuola, prefix="telefoni")
        )
        email_formset = (
            ScuolaEmailFormSet(request.POST, instance=scuola, prefix="email")
            if inline_target in (None, "email")
            else ScuolaEmailFormSet(instance=scuola, prefix="email")
        )

        form_is_valid = form.is_valid()
        socials_is_valid = socials_formset.is_valid() if inline_target in (None, "socials") else True
        telefoni_is_valid = telefoni_formset.is_valid() if inline_target in (None, "telefoni") else True
        email_is_valid = email_formset.is_valid() if inline_target in (None, "email") else True

        if form_is_valid and socials_is_valid and telefoni_is_valid and email_is_valid:
            scuola = form.save()
            if inline_target in (None, "socials"):
                socials_formset.instance = scuola
                socials_formset.save()
            if inline_target in (None, "telefoni"):
                telefoni_formset.instance = scuola
                telefoni_formset.save()
            if inline_target in (None, "email"):
                email_formset.instance = scuola
                email_formset.save()
            messages.success(request, "Dati della scuola salvati correttamente.")
            return redirect("scuola_sistema")
    else:
        form = ScuolaForm(instance=scuola)
        socials_formset = ScuolaSocialFormSet(instance=scuola, prefix="socials")
        telefoni_formset = ScuolaTelefonoFormSet(instance=scuola, prefix="telefoni")
        email_formset = ScuolaEmailFormSet(instance=scuola, prefix="email")

    ctx = {
        "form": form,
        "scuola": scuola,
        "socials_formset": socials_formset,
        "telefoni_formset": telefoni_formset,
        "email_formset": email_formset,
        "edit_scope": edit_scope,
        "inline_target": inline_target,
        "count_socials": scuola.socials.count() if scuola else 0,
        "count_telefoni": scuola.telefoni.count() if scuola else 0,
        "count_email": scuola.email.count() if scuola else 0,
    }
    ctx.update(
        scuola_inline_head(
            inline_target=inline_target,
            count_telefoni=ctx["count_telefoni"],
            count_email=ctx["count_email"],
            count_socials=ctx["count_socials"],
        )
    )
    return render(request, "sistema/scuola_form.html", ctx)


def impostazioni_generali_sistema(request):
    impostazioni = SistemaImpostazioniGenerali.objects.first()
    impostazioni_display = impostazioni or SistemaImpostazioniGenerali()

    if request.method == "POST":
        form = SistemaImpostazioniGeneraliForm(request.POST, instance=impostazioni)
        if form.is_valid():
            impostazioni = form.save()
            impostazioni_display = impostazioni
            cleanup_stats = cleanup_cronologia_operazioni(impostazioni=impostazioni, force=True)
            messages.success(request, "Impostazioni generali salvate correttamente.")
            if cleanup_stats.get("deleted_count"):
                extra_note = (
                    " La pulizia proseguira automaticamente al prossimo accesso utile."
                    if cleanup_stats.get("truncated")
                    else ""
                )
                messages.info(
                    request,
                    f"Cronologia operazioni ripulita: {cleanup_stats['deleted_count']} operazioni rimosse."
                    f"{extra_note}",
                )
            return redirect("impostazioni_generali_sistema")
    else:
        form = SistemaImpostazioniGeneraliForm(instance=impostazioni)

    p = default_gi_file_path()
    nazioni_path = default_nazioni_belfiore_file_path()
    moduli_configurabili = []
    for definition in MODULE_TOGGLE_DEFINITIONS:
        field = form[definition["field"]]
        enabled = bool(getattr(impostazioni_display, definition["field"], True))
        moduli_configurabili.append(
            {
                **definition,
                "field": field,
                "enabled": enabled,
            }
        )

    return render(
        request,
        "sistema/impostazioni_generali_form.html",
        {
            "form": form,
            "impostazioni": impostazioni_display,
            "moduli_configurabili": moduli_configurabili,
            "moduli_attivi_count": sum(1 for modulo in moduli_configurabili if modulo["enabled"]),
            "moduli_totali_count": len(moduli_configurabili),
            "dati_base_file_ready": p.is_file(),
            "dati_base_file_path": str(p),
            "nazioni_belfiore_file_ready": nazioni_path.is_file(),
            "nazioni_belfiore_file_path": str(nazioni_path),
        },
    )


def importa_dati_base_anagrafica(request):
    """
    Avvia l'import di regioni, province, città e CAP da import/gi_comuni_cap.xlsx (stesso meccanismo di `import_dati_base`).
    Protetto a livello Sistema: solo chi ha permesso di gestione sul modulo.
    """
    if request.method != "POST":
        return redirect("impostazioni_generali_sistema")
    p = default_gi_file_path()
    if not p.is_file():
        messages.error(
            request,
            f"File assente sul server: {p}. Carica o committa il file nella cartella import del progetto e ridistribuisci.",
        )
        return redirect("impostazioni_generali_sistema")
    try:
        stats = run_import_dati_base(file_path=p)
    except ValidationError as e:
        messages.error(request, " ".join(e.messages) if e.messages else str(e))
        return redirect("impostazioni_generali_sistema")
    except Exception as e:  # noqa: BLE001 — logica operativa: mostra errore generico
        messages.error(request, f"Errore durante l'import: {e}")
        return redirect("impostazioni_generali_sistema")
    messages.success(
        request,
        (
            f"Import dati base eseguito. File: {stats.get('file', p)}. "
            f"Nuove regioni: {stats['regioni_creati']}, nuove province: {stats['province_creati']}, "
            f"elaborazione città (righe): {stats['citta_righe']}, CAP creati: {stats['cap_creati']}, "
            f"CAP non importati (città mancante): {stats['cap_saltati']}, "
            f"durata: {stats.get('durata_secondi', 0)} secondi."
        ),
    )
    return redirect("impostazioni_generali_sistema")


def importa_nazioni_belfiore_anagrafica(request):
    """
    Avvia l'import di nazioni, nazionalitÃ  e codici Belfiore esteri da import/nazioni_belfiore.csv.
    Protetto a livello Sistema: solo chi ha permesso di gestione sul modulo.
    """
    if request.method != "POST":
        return redirect("impostazioni_generali_sistema")
    p = default_nazioni_belfiore_file_path()
    if not p.is_file():
        messages.error(
            request,
            f"File assente sul server: {p}. Carica o committa il file nella cartella import del progetto e ridistribuisci.",
        )
        return redirect("impostazioni_generali_sistema")
    try:
        stats = run_import_nazioni_belfiore(file_path=p)
    except ValidationError as e:
        messages.error(request, " ".join(e.messages) if e.messages else str(e))
        return redirect("impostazioni_generali_sistema")
    except Exception as e:  # noqa: BLE001 - logica operativa: mostra errore generico
        messages.error(request, f"Errore durante l'import nazioni: {e}")
        return redirect("impostazioni_generali_sistema")
    messages.success(
        request,
        (
            f"Import nazioni eseguito. File: {stats.get('file', p)}. "
            f"Righe elaborate: {stats['righe']}, nuove nazioni: {stats['nazioni_create']}, "
            f"nazioni aggiornate: {stats['nazioni_aggiornate']}, invariate: {stats['nazioni_invariate']}, "
            f"durata: {stats.get('durata_secondi', 0)} secondi."
        ),
    )
    return redirect("impostazioni_generali_sistema")


def get_pending_restore_metadata(request):
    """Job in attesa di conferma ripristino (file già caricato, non ancora in coda)."""
    job_id = request.session.get(PENDING_RESTORE_JOB_SESSION_KEY)
    if job_id:
        try:
            job = SistemaDatabaseRestoreJob.objects.get(
                pk=job_id,
                stato=StatoRipristinoDatabase.IN_ATTESA_CONFERMA,
            )
        except SistemaDatabaseRestoreJob.DoesNotExist:
            request.session.pop(PENDING_RESTORE_JOB_SESSION_KEY, None)
            request.session.modified = True
        else:
            if not restore_file_reference_exists(job.percorso_file):
                cancel_or_delete_restore_job(job)
                request.session.pop(PENDING_RESTORE_JOB_SESSION_KEY, None)
                request.session.modified = True
            else:
                return job

    # Sessione legacy (dict con path): non più supportata
    legacy = request.session.pop(PENDING_RESTORE_SESSION_KEY, None)
    if legacy:
        request.session.modified = True
        delete_pending_restore_upload(legacy)
    return None


def clear_pending_restore_metadata(request):
    job_id = request.session.pop(PENDING_RESTORE_JOB_SESSION_KEY, None)
    request.session.modified = True
    if job_id:
        try:
            job = SistemaDatabaseRestoreJob.objects.get(
                pk=job_id,
                stato=StatoRipristinoDatabase.IN_ATTESA_CONFERMA,
            )
            cancel_or_delete_restore_job(job)
        except SistemaDatabaseRestoreJob.DoesNotExist:
            pass


def parse_restore_chunk_payload(request):
    try:
        return json.loads(request.body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None


def validate_restore_file_name(file_name):
    safe_name = Path(str(file_name or "")).name
    lower_name = safe_name.lower()
    if not safe_name or not (lower_name.endswith(".sql") or lower_name.endswith(".sql.gz")):
        return ""
    return safe_name


def handle_restore_chunk_upload(request):
    payload = parse_restore_chunk_payload(request)
    if not payload or payload.get("action") != "upload_restore_file_chunk":
        return JsonResponse({"ok": False, "message": "Richiesta upload non valida."}, status=400)

    upload_id = str(payload.get("upload_id") or "").strip()
    if not RESTORE_CHUNKED_UPLOAD_ID_RE.match(upload_id):
        return JsonResponse({"ok": False, "message": "Sessione upload non valida."}, status=400)

    file_name = validate_restore_file_name(payload.get("file_name"))
    if not file_name:
        return JsonResponse(
            {"ok": False, "message": "Carica un file di backup PostgreSQL in formato .sql o .sql.gz."},
            status=400,
        )

    try:
        chunk_index = int(payload.get("chunk_index"))
        total_chunks = int(payload.get("total_chunks"))
        file_size = int(payload.get("file_size") or 0)
    except (TypeError, ValueError):
        return JsonResponse({"ok": False, "message": "Indice blocco upload non valido."}, status=400)

    if total_chunks <= 0 or chunk_index < 0 or chunk_index >= total_chunks or file_size <= 0:
        return JsonResponse({"ok": False, "message": "Metadati upload non validi."}, status=400)

    try:
        chunk_bytes = base64.b64decode(payload.get("data") or "", validate=True)
    except (binascii.Error, ValueError):
        return JsonResponse({"ok": False, "message": "Blocco upload non leggibile."}, status=400)

    if not chunk_bytes:
        return JsonResponse({"ok": False, "message": "Blocco upload vuoto."}, status=400)
    if len(chunk_bytes) > RESTORE_CHUNK_MAX_BYTES:
        return JsonResponse({"ok": False, "message": "Blocco upload troppo grande."}, status=400)

    upload_path = get_pending_restore_root() / f"chunked_{upload_id}.part"
    try:
        if chunk_index == 0:
            clear_pending_restore_metadata(request)
            upload_path.write_bytes(chunk_bytes)
        else:
            if not upload_path.exists():
                return JsonResponse({"ok": False, "message": "Sessione upload scaduta. Riprova."}, status=410)
            with upload_path.open("ab") as destination:
                destination.write(chunk_bytes)

        uploaded_size = upload_path.stat().st_size
        if chunk_index + 1 < total_chunks:
            return JsonResponse(
                {
                    "ok": True,
                    "complete": False,
                    "uploaded_chunks": chunk_index + 1,
                    "total_chunks": total_chunks,
                    "uploaded_size": uploaded_size,
                }
            )

        if uploaded_size != file_size:
            upload_path.unlink(missing_ok=True)
            return JsonResponse(
                {"ok": False, "message": "Il file ricomposto non coincide con la dimensione attesa. Riprova."},
                status=400,
            )

        job = create_restore_job_from_local_file(
            upload_path,
            file_name,
            triggered_by=request.user,
        )
        upload_path.unlink(missing_ok=True)
    except DatabaseBackupError as exc:
        upload_path.unlink(missing_ok=True)
        return JsonResponse({"ok": False, "message": str(exc)}, status=400)
    except OSError as exc:
        upload_path.unlink(missing_ok=True)
        return JsonResponse({"ok": False, "message": f"Impossibile completare l'upload: {exc}"}, status=500)
    except Exception as exc:
        upload_path.unlink(missing_ok=True)
        logger.exception("Errore durante l'upload a blocchi del ripristino database.")
        return JsonResponse({"ok": False, "message": f"Upload non completato: {exc}"}, status=500)

    request.session[PENDING_RESTORE_JOB_SESSION_KEY] = job.pk
    request.session.modified = True
    return JsonResponse(
        {
            "ok": True,
            "complete": True,
            "message": "File di backup caricato nello storage protetto.",
            "redirect": reverse("backup_database_sistema"),
        }
    )


def backup_database_sistema(request):
    configurazione = get_backup_configuration()
    pending_restore = get_pending_restore_metadata(request)
    configurazione_form = SistemaBackupDatabaseConfigurazioneForm(instance=configurazione)
    upload_form = SistemaBackupDatabaseUploadForm()
    confirm_form = SistemaBackupDatabaseRestoreConfirmForm()

    if request.method == "POST":
        if request.content_type.startswith("application/json"):
            return handle_restore_chunk_upload(request)

        action = (request.POST.get("action") or "").strip()

        if action == "save_backup_settings":
            configurazione_form = SistemaBackupDatabaseConfigurazioneForm(request.POST, instance=configurazione)
            if configurazione_form.is_valid():
                configurazione = configurazione_form.save()
                messages.success(request, "Impostazioni backup salvate correttamente.")
                return redirect("backup_database_sistema")

        elif action == "create_manual_backup":
            try:
                backup = create_database_backup(
                    triggered_by=request.user,
                    note="Backup creato manualmente dalla pagina Sistema > Backup Database.",
                )
            except DatabaseBackupError as exc:
                messages.error(request, f"Backup non creato: {exc}")
            else:
                messages.success(request, f"Backup creato correttamente: {backup.nome_file}.")
            return redirect("backup_database_sistema")

        elif action == "upload_restore_file":
            upload_form = SistemaBackupDatabaseUploadForm(request.POST, request.FILES)
            if upload_form.is_valid():
                clear_pending_restore_metadata(request)
                job = create_restore_job_from_upload(
                    upload_form.cleaned_data["file_backup"],
                    triggered_by=request.user,
                )
                request.session[PENDING_RESTORE_JOB_SESSION_KEY] = job.pk
                request.session.modified = True
                pending_restore = job
                confirm_form = SistemaBackupDatabaseRestoreConfirmForm()
                messages.warning(
                    request,
                    "File di backup caricato nello storage protetto. Completa il secondo controllo per mettere in coda il ripristino in background.",
                )

        elif action == "prepare_restore_backup":
            backup_id = request.POST.get("backup_id")
            backup_record = get_object_or_404(SistemaDatabaseBackup, pk=backup_id)
            clear_pending_restore_metadata(request)
            job = create_restore_job_from_backup_record(
                backup_record,
                triggered_by=request.user,
            )
            request.session[PENDING_RESTORE_JOB_SESSION_KEY] = job.pk
            request.session.modified = True
            pending_restore = job
            confirm_form = SistemaBackupDatabaseRestoreConfirmForm()
            messages.warning(
                request,
                f"Backup {backup_record.nome_file} selezionato. Completa il secondo controllo per avviare il ripristino in background.",
            )

        elif action == "cancel_restore":
            clear_pending_restore_metadata(request)
            messages.info(request, "Ripristino annullato.")
            return redirect("backup_database_sistema")

        elif action == "confirm_restore":
            job_in_attesa = get_pending_restore_metadata(request)
            if not job_in_attesa:
                messages.error(request, "Carica prima un file di backup da ripristinare.")
                return redirect("backup_database_sistema")

            confirm_form = SistemaBackupDatabaseRestoreConfirmForm(request.POST)
            if confirm_form.is_valid():
                job = job_in_attesa
                job.stato = StatoRipristinoDatabase.IN_CODA
                job.save(update_fields=["stato"])
                request.session.pop(PENDING_RESTORE_JOB_SESSION_KEY, None)
                request.session.modified = True
                try:
                    schedule_restore_job(job.pk)
                except Exception as exc:  # noqa: BLE001
                    job.stato = StatoRipristinoDatabase.IN_ATTESA_CONFERMA
                    job.save(update_fields=["stato"])
                    request.session[PENDING_RESTORE_JOB_SESSION_KEY] = job.pk
                    request.session.modified = True
                    messages.error(request, f"Impossibile avviare il ripristino: {exc}")
                else:
                    messages.success(
                        request,
                        "Ripristino messo in coda. L'elaborazione avviene in background: aggiorna la pagina per lo stato o attendi la fine del processo (può richiedere diversi minuti).",
                    )
                return redirect("backup_database_sistema")
            pending_restore = job_in_attesa

    backup_records = list(SistemaDatabaseBackup.objects.select_related("creato_da").order_by("-data_creazione", "-id")[:10])
    ultimo_backup = backup_records[0] if backup_records else None
    recent_restore_jobs = list(SistemaDatabaseRestoreJob.objects.select_related("creato_da", "backup_sicurezza").order_by(
        "-data_creazione", "-id"
    )[:20])
    backup_stats = {
        "backup_conservati": len(backup_records),
        "ripristini_recenti": len(recent_restore_jobs),
        "ripristini_attivi": sum(
            1
            for job in recent_restore_jobs
            if job.stato
            in {
                StatoRipristinoDatabase.IN_ATTESA_CONFERMA,
                StatoRipristinoDatabase.IN_CODA,
                StatoRipristinoDatabase.IN_CORSO,
            }
        ),
        "ultimo_backup_dimensione": ultimo_backup.dimensione_label if ultimo_backup else "-",
        "ultimo_backup_data": ultimo_backup.data_creazione if ultimo_backup else None,
    }

    return render(
        request,
        "sistema/backup_database_form.html",
        {
            "configurazione": configurazione,
            "configurazione_form": configurazione_form,
            "upload_form": upload_form,
            "confirm_form": confirm_form,
            "pending_restore": pending_restore,
            "backup_records": backup_records,
            "ultimo_backup": ultimo_backup,
            "recent_restore_jobs": recent_restore_jobs,
            "backup_stats": backup_stats,
        },
    )


def scarica_backup_database(request, pk):
    backup = get_object_or_404(SistemaDatabaseBackup, pk=pk)
    file_handle = backup.file_backup.open("rb")
    return FileResponse(file_handle, as_attachment=True, filename=backup.nome_file or Path(backup.file_backup.name).name)


@operational_admin_required
def cronologia_operazioni_sistema(request):
    q = (request.GET.get("q") or "").strip()
    azione = (request.GET.get("azione") or "").strip()
    modulo = (request.GET.get("modulo") or "").strip()

    action_values = {value for value, _label in AzioneOperazioneCronologia.choices}
    module_values = {value for value, _label in ModuloOperazioneCronologia.choices}

    if azione not in action_values:
        azione = ""

    if modulo not in module_values:
        modulo = ""

    operazioni_qs = SistemaOperazioneCronologia.objects.select_related("utente").order_by("-data_operazione", "-id")

    if q:
        operazioni_qs = operazioni_qs.filter(
            Q(descrizione__icontains=q)
            | Q(oggetto_label__icontains=q)
            | Q(model_verbose_name__icontains=q)
            | Q(utente_label__icontains=q)
        )

    if azione:
        operazioni_qs = operazioni_qs.filter(azione=azione)

    if modulo:
        operazioni_qs = operazioni_qs.filter(modulo=modulo)

    totale_operazioni = operazioni_qs.count()
    operazioni = list(operazioni_qs[:CRONOLOGIA_RESULT_LIMIT])
    riepilogo = operazioni_qs.aggregate(
        count_creazioni=Count("id", filter=Q(azione=AzioneOperazioneCronologia.CREAZIONE)),
        count_modifiche=Count("id", filter=Q(azione=AzioneOperazioneCronologia.MODIFICA)),
        count_eliminazioni=Count("id", filter=Q(azione=AzioneOperazioneCronologia.ELIMINAZIONE)),
    )

    return render(
        request,
        "sistema/cronologia_operazioni_list.html",
        {
            "operazioni": operazioni,
            "totale_operazioni": totale_operazioni,
            "azione": azione,
            "modulo": modulo,
            "q": q,
            "azioni_disponibili": AzioneOperazioneCronologia.choices,
            "moduli_disponibili": ModuloOperazioneCronologia.choices,
            "count_creazioni": riepilogo["count_creazioni"] or 0,
            "count_modifiche": riepilogo["count_modifiche"] or 0,
            "count_eliminazioni": riepilogo["count_eliminazioni"] or 0,
            "is_truncated": totale_operazioni > len(operazioni),
            "result_limit": CRONOLOGIA_RESULT_LIMIT,
        },
    )


@operational_admin_required
def lista_feedback_segnalazioni(request):
    q = (request.GET.get("q") or "").strip()
    tipo = (request.GET.get("tipo") or "").strip()
    stato = (request.GET.get("stato") or "").strip()
    email_status = (request.GET.get("email_status") or "").strip()

    tipo_values = {value for value, _label in TipoFeedbackSegnalazione.choices}
    stato_values = {value for value, _label in StatoFeedbackSegnalazione.choices}

    if tipo not in tipo_values:
        tipo = ""
    if stato not in stato_values:
        stato = ""
    if email_status not in {"sent", "error", "pending"}:
        email_status = ""

    feedback_qs = FeedbackSegnalazione.objects.select_related("utente").order_by("-data_creazione", "-id")

    if q:
        feedback_qs = feedback_qs.filter(
            Q(messaggio__icontains=q)
            | Q(utente_nome__icontains=q)
            | Q(utente_email__icontains=q)
            | Q(pagina_titolo__icontains=q)
            | Q(pagina_path__icontains=q)
        )
    if tipo:
        feedback_qs = feedback_qs.filter(tipo=tipo)
    if stato:
        feedback_qs = feedback_qs.filter(stato=stato)
    if email_status == "sent":
        feedback_qs = feedback_qs.filter(email_inviata_at__isnull=False)
    elif email_status == "error":
        feedback_qs = feedback_qs.filter(email_inviata_at__isnull=True).exclude(email_errore="")
    elif email_status == "pending":
        feedback_qs = feedback_qs.filter(email_inviata_at__isnull=True, email_errore="")

    riepilogo = feedback_qs.aggregate(
        count_bug=Count("id", filter=Q(tipo=TipoFeedbackSegnalazione.BUG)),
        count_funzioni=Count("id", filter=Q(tipo=TipoFeedbackSegnalazione.FUNZIONE)),
        count_email_errori=Count("id", filter=Q(email_inviata_at__isnull=True) & ~Q(email_errore="")),
    )

    querystring = request.GET.copy()
    querystring.pop("page", None)
    paginator = Paginator(feedback_qs, FEEDBACK_PER_PAGE)
    page_obj = paginator.get_page(request.GET.get("page"))

    return render(
        request,
        "sistema/feedback_segnalazioni_list.html",
        {
            "feedback_page_obj": page_obj,
            "feedback_list": page_obj.object_list,
            "q": q,
            "tipo": tipo,
            "stato": stato,
            "email_status": email_status,
            "tipi_feedback": TipoFeedbackSegnalazione.choices,
            "stati_feedback": StatoFeedbackSegnalazione.choices,
            "count_totale": paginator.count,
            "count_bug": riepilogo["count_bug"] or 0,
            "count_funzioni": riepilogo["count_funzioni"] or 0,
            "count_email_errori": riepilogo["count_email_errori"] or 0,
            "feedback_querystring": querystring.urlencode(),
        },
    )


def lista_utenti(request):
    utenti = list(
        User.objects.select_related("profilo_permessi__ruolo_permessi").order_by("last_name", "first_name", "email")
    )

    for utente in utenti:
        profilo, _ = SistemaUtentePermessi.objects.get_or_create(user=utente)
        utente.profilo_permessi_safe = profilo
        utente.gestibile_da_request = request.user.is_superuser or not utente.is_superuser
        utente.eliminabile_da_request = utente.gestibile_da_request and utente.pk != request.user.pk

    utenti_stats = {
        "totale": len(utenti),
        "attivi": sum(1 for utente in utenti if utente.is_active),
        "ruoli_assegnati": len(
            {
                utente.profilo_permessi_safe.ruolo_permessi_id
                for utente in utenti
                if utente.profilo_permessi_safe.ruolo_permessi_id
            }
        ),
        "controllo_completo": sum(
            1 for utente in utenti if utente.profilo_permessi_safe.controllo_completo_effettivo
        ),
    }

    return render(
        request,
        "sistema/utenti_list.html",
        {
            "utenti": utenti,
            "utenti_stats": utenti_stats,
        },
    )


def lista_ruoli_utenti(request):
    ruoli = list(SistemaRuoloPermessi.objects.annotate(count_utenti=Count("utenti")).order_by("nome"))
    role_stats = {
        "totale": len(ruoli),
        "attivi": sum(1 for ruolo in ruoli if ruolo.attivo),
        "controllo_completo": sum(1 for ruolo in ruoli if ruolo.controllo_completo),
        "utenti_collegati": sum(ruolo.count_utenti for ruolo in ruoli),
    }

    return render(
        request,
        "sistema/ruoli_list.html",
        {
            "ruoli": ruoli,
            "role_stats": role_stats,
        },
    )


def sistema_is_popup_request(request):
    return request.GET.get("popup") == "1" or request.POST.get("popup") == "1"


def sistema_popup_response(request, message="Operazione completata."):
    return render(request, "popup/popup_close.html", {"message": message})


def sistema_popup_select_response(request, field_name, object_id, object_label):
    return render(
        request,
        "popup/popup_close_select.html",
        {
            "action": "select",
            "field_name": field_name,
            "object_id": object_id,
            "object_label": object_label,
            "target_input_name": request.GET.get("target_input_name")
            or request.POST.get("target_input_name", ""),
        },
    )


def sistema_popup_delete_response(request, field_name, object_id):
    return render(
        request,
        "popup/popup_close_select.html",
        {
            "action": "delete",
            "field_name": field_name,
            "object_id": object_id,
            "object_label": "",
            "target_input_name": request.GET.get("target_input_name")
            or request.POST.get("target_input_name", ""),
        },
    )


def sistema_ruolo_form_context(request, form, ruolo_obj=None, is_new=False):
    module_permission_fields = [
        {"field": form["permesso_anagrafica"], "icon": "family", "tone": "blue"},
        {"field": form["permesso_famiglie_interessate"], "icon": "family-heart", "tone": "green"},
        {"field": form["permesso_economia"], "icon": "coins", "tone": "amber"},
        {"field": form["permesso_gestione_finanziaria"], "icon": "finance", "tone": "blue"},
        {"field": form["permesso_sistema"], "icon": "settings", "tone": "purple"},
        {"field": form["permesso_calendario"], "icon": "calendar", "tone": "green"},
        {"field": form["permesso_gestione_amministrativa"], "icon": "briefcase", "tone": "amber"},
        {"field": form["permesso_servizi_extra"], "icon": "list", "tone": "purple"},
    ]
    special_permission_fields = [
        {"field": form["controllo_completo"], "icon": "shield", "tone": "red"},
        {"field": form["amministratore_operativo"], "icon": "settings", "tone": "blue"},
        {"field": form["accesso_backup_database"], "icon": "archive", "tone": "amber"},
    ]
    context = {
        "form": form,
        "ruolo_obj": ruolo_obj,
        "is_new": is_new,
        "popup": sistema_is_popup_request(request),
        "module_permission_fields": module_permission_fields,
        "special_permission_fields": special_permission_fields,
    }
    if ruolo_obj:
        context["count_utenti"] = ruolo_obj.utenti.count()
    return context


def sistema_utente_form_context(request, form, utente_obj=None, is_new=False):
    profilo = getattr(utente_obj, "profilo_permessi", None) if utente_obj else None
    role_summary = []
    if profilo and profilo.ruolo_permessi_id:
        role_summary = [
            ("Ruolo", profilo.ruolo_display),
            ("Controllo completo", "Si" if profilo.controllo_completo_effettivo else "No"),
            ("Anagrafica", profilo.permesso_anagrafica_effettivo_display),
            ("Famiglie interessate", profilo.permesso_famiglie_interessate_effettivo_display),
            ("Rette scolastiche", profilo.permesso_economia_effettivo_display),
            ("Gestione finanziaria", profilo.permesso_gestione_finanziaria_effettivo_display),
            ("Sistema", profilo.permesso_sistema_effettivo_display),
            ("Calendario", profilo.permesso_calendario_effettivo_display),
        ]
    return {
        "form": form,
        "utente_obj": utente_obj,
        "is_new": is_new,
        "popup": sistema_is_popup_request(request),
        "role_summary": role_summary,
    }


def crea_ruolo_utente(request):
    popup = sistema_is_popup_request(request)
    if request.method == "POST":
        form = SistemaRuoloPermessiForm(request.POST)
        if form.is_valid():
            ruolo = form.save()
            sync_user_profiles_for_role(ruolo)
            messages.success(request, f"Ruolo {ruolo.nome} creato correttamente.")
            if popup:
                return sistema_popup_select_response(request, "ruolo_permessi", ruolo.pk, ruolo.nome)
            return redirect("modifica_ruolo_utente", pk=ruolo.pk)
    else:
        form = SistemaRuoloPermessiForm()

    return render(
        request,
        "sistema/ruolo_form.html",
        sistema_ruolo_form_context(request, form, ruolo_obj=None, is_new=True),
    )


def modifica_ruolo_utente(request, pk):
    ruolo = get_object_or_404(SistemaRuoloPermessi, pk=pk)
    popup = sistema_is_popup_request(request)

    if request.method == "POST":
        form = SistemaRuoloPermessiForm(request.POST, instance=ruolo)
        if form.is_valid():
            ruolo = form.save()
            sync_user_profiles_for_role(ruolo)
            messages.success(request, f"Ruolo {ruolo.nome} aggiornato correttamente.")
            if popup:
                return sistema_popup_select_response(request, "ruolo_permessi", ruolo.pk, ruolo.nome)
            return redirect("modifica_ruolo_utente", pk=ruolo.pk)
    else:
        form = SistemaRuoloPermessiForm(instance=ruolo)

    return render(
        request,
        "sistema/ruolo_form.html",
        sistema_ruolo_form_context(request, form, ruolo_obj=ruolo, is_new=False),
    )


def elimina_ruolo_utente(request, pk):
    ruolo = get_object_or_404(SistemaRuoloPermessi, pk=pk)
    popup = sistema_is_popup_request(request)
    count_utenti = ruolo.utenti.count()
    can_delete = count_utenti == 0

    if request.method == "POST":
        if not can_delete:
            messages.error(request, "Non puoi eliminare un ruolo collegato a uno o piu utenti.")
        else:
            ruolo_id = ruolo.pk
            nome = ruolo.nome
            ruolo.delete()
            messages.success(request, f"Ruolo {nome} eliminato correttamente.")
            if popup:
                return sistema_popup_delete_response(request, "ruolo_permessi", ruolo_id)
            return redirect("lista_ruoli_utenti")

    return render(
        request,
        "sistema/ruolo_confirm_delete.html",
        {
            "ruolo_obj": ruolo,
            "popup": popup,
            "count_utenti": count_utenti,
            "can_delete": can_delete,
        },
    )


def crea_utente(request):
    popup = sistema_is_popup_request(request)
    if request.method == "POST":
        form = SistemaUtenteForm(request.POST)
        if form.is_valid():
            utente = form.save()
            messages.success(request, f"Utente {utente.get_full_name() or utente.email} creato correttamente.")
            if popup:
                return sistema_popup_response(request, f"Utente {utente.get_full_name() or utente.email} creato correttamente.")
            return redirect("modifica_utente", pk=utente.pk)
    else:
        form = SistemaUtenteForm()

    return render(
        request,
        "sistema/utente_form.html",
        sistema_utente_form_context(request, form, utente_obj=None, is_new=True),
    )


def modifica_utente(request, pk):
    utente = get_object_or_404(User.objects.select_related("profilo_permessi__ruolo_permessi"), pk=pk)
    popup = sistema_is_popup_request(request)

    if utente.is_superuser and not request.user.is_superuser:
        messages.error(request, "Solo un superuser puo modificare un altro superuser.")
        if popup:
            return sistema_popup_response(request, "Solo un superuser puo modificare un altro superuser.")
        return redirect("lista_utenti")

    if request.method == "POST":
        form = SistemaUtenteForm(request.POST, instance=utente)
        if form.is_valid():
            utente = form.save()
            messages.success(request, f"Utente {utente.get_full_name() or utente.email} aggiornato correttamente.")
            if popup:
                return sistema_popup_response(request, f"Utente {utente.get_full_name() or utente.email} aggiornato correttamente.")
            return redirect("modifica_utente", pk=utente.pk)
    else:
        form = SistemaUtenteForm(instance=utente)

    return render(
        request,
        "sistema/utente_form.html",
        sistema_utente_form_context(request, form, utente_obj=utente, is_new=False),
    )


def elimina_utente(request, pk):
    utente = get_object_or_404(User.objects.select_related("profilo_permessi__ruolo_permessi"), pk=pk)
    popup = sistema_is_popup_request(request)

    if utente.pk == request.user.pk:
        messages.error(request, "Non puoi eliminare l'account con cui hai effettuato l'accesso.")
        if popup:
            return render(
                request,
                "sistema/utente_confirm_delete.html",
                {
                    "utente_obj": utente,
                    "popup": popup,
                    "can_delete": False,
                    "delete_block_reason": "Non puoi eliminare l'account con cui hai effettuato l'accesso.",
                },
            )
        return redirect("modifica_utente", pk=utente.pk)

    if utente.is_superuser and not request.user.is_superuser:
        messages.error(request, "Solo un superuser puo eliminare un altro superuser.")
        if popup:
            return render(
                request,
                "sistema/utente_confirm_delete.html",
                {
                    "utente_obj": utente,
                    "popup": popup,
                    "can_delete": False,
                    "delete_block_reason": "Solo un superuser puo eliminare un altro superuser.",
                },
            )
        return redirect("modifica_utente", pk=utente.pk)

    if request.method == "POST":
        user_label = utente.get_full_name() or utente.email or utente.username
        utente.delete()
        messages.success(request, f"Utente {user_label} eliminato correttamente.")
        if popup:
            return sistema_popup_response(request, f"Utente {user_label} eliminato correttamente.")
        return redirect("lista_utenti")

    return render(
        request,
        "sistema/utente_confirm_delete.html",
        {
            "utente_obj": utente,
            "popup": popup,
            "can_delete": True,
            "delete_block_reason": "",
        },
    )


def informativa_privacy(request):
    """Pagina statica informativa sul trattamento dei dati personali (template generico)."""
    return render(request, "sistema/informativa_privacy.html")


def termini_e_condizioni(request):
    """Pagina statica termini e condizioni d'uso del software (template generico)."""
    return render(request, "sistema/termini_condizioni.html")
