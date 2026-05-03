from pathlib import Path

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login as auth_login
from django.contrib.auth import logout as auth_logout
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.http import FileResponse, JsonResponse
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
    create_restore_job_from_upload,
    delete_pending_restore_upload,
    get_backup_configuration,
    restore_file_reference_exists,
)
from .restore_scheduler import schedule_restore_job
from .models import (
    AzioneOperazioneCronologia,
    FeedbackSegnalazione,
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

from .permissions import authenticated_user_required, get_user_permission_profile, operational_admin_required


PENDING_RESTORE_SESSION_KEY = "sistema_database_backup_pending_restore"
PENDING_RESTORE_JOB_SESSION_KEY = "sistema_db_restore_job_id"
CRONOLOGIA_RESULT_LIMIT = 250
FEEDBACK_PER_PAGE = 20


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
            messages.success(request, "Impostazioni generali salvate correttamente.")
            return redirect("impostazioni_generali_sistema")
    else:
        form = SistemaImpostazioniGeneraliForm(instance=impostazioni)

    p = default_gi_file_path()
    nazioni_path = default_nazioni_belfiore_file_path()
    return render(
        request,
        "sistema/impostazioni_generali_form.html",
        {
            "form": form,
            "impostazioni": impostazioni_display,
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


def backup_database_sistema(request):
    configurazione = get_backup_configuration()
    pending_restore = get_pending_restore_metadata(request)
    configurazione_form = SistemaBackupDatabaseConfigurazioneForm(instance=configurazione)
    upload_form = SistemaBackupDatabaseUploadForm()
    confirm_form = SistemaBackupDatabaseRestoreConfirmForm()

    if request.method == "POST":
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

    backup_records = SistemaDatabaseBackup.objects.select_related("creato_da").order_by("-data_creazione", "-id")[:10]
    ultimo_backup = backup_records[0] if backup_records else None
    recent_restore_jobs = SistemaDatabaseRestoreJob.objects.select_related("creato_da", "backup_sicurezza").order_by(
        "-data_creazione", "-id"
    )[:20]

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

    return render(
        request,
        "sistema/utenti_list.html",
        {
            "utenti": utenti,
        },
    )


def lista_ruoli_utenti(request):
    ruoli = SistemaRuoloPermessi.objects.annotate(count_utenti=Count("utenti")).order_by("nome")

    return render(
        request,
        "sistema/ruoli_list.html",
        {
            "ruoli": ruoli,
        },
    )


def crea_ruolo_utente(request):
    if request.method == "POST":
        form = SistemaRuoloPermessiForm(request.POST)
        if form.is_valid():
            ruolo = form.save()
            sync_user_profiles_for_role(ruolo)
            messages.success(request, f"Ruolo {ruolo.nome} creato correttamente.")
            return redirect("modifica_ruolo_utente", pk=ruolo.pk)
    else:
        form = SistemaRuoloPermessiForm()

    return render(
        request,
        "sistema/ruolo_form.html",
        {
            "form": form,
            "ruolo_obj": None,
            "is_new": True,
        },
    )


def modifica_ruolo_utente(request, pk):
    ruolo = get_object_or_404(SistemaRuoloPermessi, pk=pk)

    if request.method == "POST":
        form = SistemaRuoloPermessiForm(request.POST, instance=ruolo)
        if form.is_valid():
            ruolo = form.save()
            sync_user_profiles_for_role(ruolo)
            messages.success(request, f"Ruolo {ruolo.nome} aggiornato correttamente.")
            return redirect("modifica_ruolo_utente", pk=ruolo.pk)
    else:
        form = SistemaRuoloPermessiForm(instance=ruolo)

    return render(
        request,
        "sistema/ruolo_form.html",
        {
            "form": form,
            "ruolo_obj": ruolo,
            "is_new": False,
            "count_utenti": ruolo.utenti.count(),
        },
    )


def crea_utente(request):
    if request.method == "POST":
        form = SistemaUtenteForm(request.POST)
        if form.is_valid():
            utente = form.save()
            messages.success(request, f"Utente {utente.get_full_name() or utente.email} creato correttamente.")
            return redirect("modifica_utente", pk=utente.pk)
    else:
        form = SistemaUtenteForm()

    return render(
        request,
        "sistema/utente_form.html",
        {
            "form": form,
            "utente_obj": None,
            "is_new": True,
        },
    )


def modifica_utente(request, pk):
    utente = get_object_or_404(User.objects.select_related("profilo_permessi__ruolo_permessi"), pk=pk)

    if utente.is_superuser and not request.user.is_superuser:
        messages.error(request, "Solo un superuser puo modificare un altro superuser.")
        return redirect("lista_utenti")

    if request.method == "POST":
        form = SistemaUtenteForm(request.POST, instance=utente)
        if form.is_valid():
            utente = form.save()
            messages.success(request, f"Utente {utente.get_full_name() or utente.email} aggiornato correttamente.")
            return redirect("modifica_utente", pk=utente.pk)
    else:
        form = SistemaUtenteForm(instance=utente)

    return render(
        request,
        "sistema/utente_form.html",
        {
            "form": form,
            "utente_obj": utente,
            "is_new": False,
        },
    )


def elimina_utente(request, pk):
    utente = get_object_or_404(User.objects.select_related("profilo_permessi__ruolo_permessi"), pk=pk)

    if utente.pk == request.user.pk:
        messages.error(request, "Non puoi eliminare l'account con cui hai effettuato l'accesso.")
        return redirect("modifica_utente", pk=utente.pk)

    if utente.is_superuser and not request.user.is_superuser:
        messages.error(request, "Solo un superuser puo eliminare un altro superuser.")
        return redirect("modifica_utente", pk=utente.pk)

    if request.method == "POST":
        user_label = utente.get_full_name() or utente.email or utente.username
        utente.delete()
        messages.success(request, f"Utente {user_label} eliminato correttamente.")
        return redirect("lista_utenti")

    return render(
        request,
        "sistema/utente_confirm_delete.html",
        {
            "utente_obj": utente,
        },
    )


def informativa_privacy(request):
    """Pagina statica informativa sul trattamento dei dati personali (template generico)."""
    return render(request, "sistema/informativa_privacy.html")


def termini_e_condizioni(request):
    """Pagina statica termini e condizioni d'uso del software (template generico)."""
    return render(request, "sistema/termini_condizioni.html")
