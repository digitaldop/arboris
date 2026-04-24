from django.contrib import messages
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db.models import Count, Q
from django.http import FileResponse, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import get_template
from pathlib import Path

from .forms import (
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
    create_database_backup,
    delete_pending_restore_upload,
    get_backup_configuration,
    restore_database_from_backup_file,
    store_pending_restore_upload,
)
from .models import (
    AzioneOperazioneCronologia,
    ModuloOperazioneCronologia,
    Scuola,
    SistemaDatabaseBackup,
    SistemaImpostazioniGenerali,
    SistemaOperazioneCronologia,
    SistemaUtentePermessi,
)
from anagrafica.dati_base_import import default_gi_file_path, run_import_dati_base

from .permissions import operational_admin_required


PENDING_RESTORE_SESSION_KEY = "sistema_database_backup_pending_restore"
CRONOLOGIA_RESULT_LIMIT = 250


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

    return render(
        request,
        "sistema/scuola_form.html",
        {
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
        },
    )


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
            f"CAP non importati (città mancante): {stats['cap_saltati']}."
        ),
    )
    return redirect("impostazioni_generali_sistema")


def get_pending_restore_metadata(request):
    pending = request.session.get(PENDING_RESTORE_SESSION_KEY)
    if not pending:
        return None

    file_path = pending.get("path", "")
    if not file_path or not Path(file_path).exists():
        request.session.pop(PENDING_RESTORE_SESSION_KEY, None)
        request.session.modified = True
        return None

    return pending


def clear_pending_restore_metadata(request):
    pending = request.session.pop(PENDING_RESTORE_SESSION_KEY, None)
    request.session.modified = True
    delete_pending_restore_upload(pending)


def render_backup_restore_result(context):
    template = get_template("sistema/backup_database_restore_result.html")
    return HttpResponse(template.render(context))


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
                pending_restore = store_pending_restore_upload(upload_form.cleaned_data["file_backup"])
                request.session[PENDING_RESTORE_SESSION_KEY] = pending_restore
                request.session.modified = True
                confirm_form = SistemaBackupDatabaseRestoreConfirmForm()
                messages.warning(
                    request,
                    "File di backup caricato. Completa il secondo controllo per avviare il ripristino.",
                )

        elif action == "cancel_restore":
            clear_pending_restore_metadata(request)
            messages.info(request, "Ripristino annullato.")
            return redirect("backup_database_sistema")

        elif action == "confirm_restore":
            pending_restore = get_pending_restore_metadata(request)
            if not pending_restore:
                messages.error(request, "Carica prima un file di backup da ripristinare.")
                return redirect("backup_database_sistema")

            confirm_form = SistemaBackupDatabaseRestoreConfirmForm(request.POST)
            if confirm_form.is_valid():
                try:
                    safety_backup = restore_database_from_backup_file(
                        pending_restore["path"],
                        original_name=pending_restore.get("original_name", ""),
                        triggered_by=request.user,
                    )
                except DatabaseBackupError as exc:
                    clear_pending_restore_metadata(request)
                    return render_backup_restore_result(
                        {
                            "restore_success": False,
                            "restore_message": str(exc),
                            "uploaded_backup_name": pending_restore.get("original_name") or "backup.sql",
                            "safety_backup_name": exc.safety_backup.nome_file if exc.safety_backup else "",
                        },
                    )

                clear_pending_restore_metadata(request)
                return render_backup_restore_result(
                    {
                        "restore_success": True,
                        "restore_message": "Ripristino completato correttamente.",
                        "uploaded_backup_name": pending_restore.get("original_name") or "backup.sql",
                        "safety_backup_name": safety_backup.nome_file,
                    },
                )

    backup_records = SistemaDatabaseBackup.objects.select_related("creato_da").order_by("-data_creazione", "-id")[:10]
    ultimo_backup = backup_records[0] if backup_records else None

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
