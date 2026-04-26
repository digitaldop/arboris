from django.contrib import messages
from django.contrib.auth import login as auth_login
from django.contrib.auth import logout as auth_logout
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db.models import Count, Q
from django.http import FileResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from pathlib import Path

from .inline_context import scuola_inline_head
from .forms import (
    ArborisAuthenticationForm,
    SistemaBackupDatabaseConfigurazioneForm,
    SistemaBackupDatabaseRestoreConfirmForm,
    SistemaBackupDatabaseUploadForm,
    SistemaImpostazioniGeneraliForm,
    ScuolaForm,
    ScuolaSocialFormSet,
    ScuolaTelefonoFormSet,
    ScuolaEmailFormSet,
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
    ModuloOperazioneCronologia,
    Scuola,
    SistemaDatabaseBackup,
    SistemaDatabaseRestoreJob,
    SistemaImpostazioniGenerali,
    SistemaOperazioneCronologia,
    SistemaUtentePermessi,
    StatoRipristinoDatabase,
)
from anagrafica.dati_base_import import default_gi_file_path, run_import_dati_base

from .permissions import operational_admin_required


PENDING_RESTORE_SESSION_KEY = "sistema_database_backup_pending_restore"
PENDING_RESTORE_JOB_SESSION_KEY = "sistema_db_restore_job_id"
CRONOLOGIA_RESULT_LIMIT = 250


def resolve_safe_next_url(request, fallback_url_name="home"):
    next_url = (
        request.POST.get("next")
        or request.GET.get("next")
        or ""
    ).strip()
    if next_url and url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
        return next_url
    return reverse(fallback_url_name)


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
    return render(
        request,
        "sistema/impostazioni_generali_form.html",
        {
            "form": form,
            "impostazioni": impostazioni_display,
            "dati_base_file_ready": p.is_file(),
            "dati_base_file_path": str(p),
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


def lista_utenti(request):
    utenti = list(
        User.objects.order_by("last_name", "first_name", "email")
    )

    for utente in utenti:
        profilo, _ = SistemaUtentePermessi.objects.get_or_create(user=utente)
        utente.profilo_permessi_safe = profilo

    return render(
        request,
        "sistema/utenti_list.html",
        {
            "utenti": utenti,
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
    utente = get_object_or_404(User.objects.all(), pk=pk)

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


def informativa_privacy(request):
    """Pagina statica informativa sul trattamento dei dati personali (template generico)."""
    return render(request, "sistema/informativa_privacy.html")


def termini_e_condizioni(request):
    """Pagina statica termini e condizioni d'uso del software (template generico)."""
    return render(request, "sistema/termini_condizioni.html")
