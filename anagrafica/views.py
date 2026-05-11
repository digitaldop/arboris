import mimetypes
import unicodedata
from collections import Counter, defaultdict
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP

from django.conf import settings
from django.contrib import messages
from django.db import transaction
from django.db.models import Case, Count, Exists, IntegerField, OuterRef, Prefetch, Q, Sum, Value, When
from django.forms import modelform_factory
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme

from .forms import (
    anagrafica_contact_formsets_are_valid,
    anagrafica_contact_formsets_have_errors,
    build_anagrafica_contact_formsets,
    IndirizzoForm,
    FamigliaForm,
    FamiliareDirectStudentiForm,
    FamiliareFormSet,
    LogicalFamiliareFormSet,
    LogicalStudenteFormSet,
    StudenteFormSet,
    DocumentoFamiliareFormSet,
    StudenteDirectFamiliariForm,
    StudenteStandaloneForm,
    DocumentoStudenteFormSet,
    FamiliareForm,
    IscrizioneStudenteFormSet,
    save_anagrafica_contact_formsets,
    split_classe_principale_reference,
)
from .models import (
    Citta,
    Nazione,
    Indirizzo,
    LabelEmail,
    LabelIndirizzo,
    LabelTelefono,
    RelazioneFamiliare,
    TipoDocumento,
    Studente,
    StudenteFamiliare,
    Documento,
    Familiare,
)
from calendario.data import build_dashboard_calendar_data
from economia.models import Iscrizione, PrestazioneScambioRetta, RataIscrizione, TariffaCondizioneIscrizione
from economia.scambio_retta_helpers import build_familiare_scambio_retta_inline_context
from gestione_finanziaria.services import build_home_financial_dashboard_data
from gestione_amministrativa.models import Dipendente, RuoloAnagraficoDipendente, StatoDipendente
from scuola.models import AnnoScolastico, Classe
from scuola.utils import resolve_default_anno_scolastico
from sistema.inline_context import famiglia_inline_head, studente_inline_head
from sistema.models import (
    AzioneOperazioneCronologia,
    LivelloPermesso,
    Scuola,
    SistemaImpostazioniGenerali,
    SistemaOperazioneCronologia,
)
from sistema.permissions import user_has_module_permission
from sistema.terminology import get_educator_terminology, get_student_terminology

from .contact_services import address_duplicate_candidates, set_familiare_studenti, set_studente_familiari
from .family_logic import (
    build_logical_family_snapshot,
    build_logical_family_snapshot_from_ids,
    family_document_queryset,
    iter_logical_family_snapshots,
    logical_family_detail_url,
    logical_family_matches,
    logical_family_summary_for_person,
    resolve_logical_family_snapshot,
)
from .storage_utils import DOCUMENT_STORAGE_ERROR_TYPES, build_document_storage_error_message
from .utils import citta_choice_label

MONTH_LABELS = {
    1: "Gennaio",
    2: "Febbraio",
    3: "Marzo",
    4: "Aprile",
    5: "Maggio",
    6: "Giugno",
    7: "Luglio",
    8: "Agosto",
    9: "Settembre",
    10: "Ottobre",
    11: "Novembre",
    12: "Dicembre",
}

ANAGRAFICA_DOCUMENT_QUERY_TARGETS = {
    "familiari": "Familiari",
    "studenti": "Studenti",
    "famiglie": "Famiglie",
}

ANAGRAFICA_DOCUMENT_QUERY_PRESETS = [
    {
        "key": "familiari_senza_documento_identita",
        "title": "Familiari senza documento di identita",
        "target": "familiari",
        "aliases": ["documento identita", "documento d identita", "carta identita", "identita"],
    },
    {
        "key": "studenti_senza_contratto",
        "title": "Studenti senza contratto",
        "target": "studenti",
        "aliases": ["contratto", "scheda contratto"],
    },
    {
        "key": "studenti_senza_carta_identita",
        "title": "Studenti senza carta di identita",
        "target": "studenti",
        "aliases": ["carta identita", "documento identita", "documento d identita", "identita"],
    },
]


def normalize_query_text(value):
    normalized = unicodedata.normalize("NFKD", value or "")
    without_accents = "".join(char for char in normalized if not unicodedata.combining(char))
    return " ".join(without_accents.lower().replace("'", " ").split())


def find_tipo_documento_by_aliases(tipi_documento, aliases):
    normalized_aliases = [normalize_query_text(alias) for alias in aliases]
    for tipo_documento in tipi_documento:
        normalized_name = normalize_query_text(tipo_documento.tipo_documento)
        if any(alias and alias in normalized_name for alias in normalized_aliases):
            return tipo_documento
    return None


def resolve_current_school_year():
    anno_corrente = resolve_default_anno_scolastico()
    if anno_corrente:
        return anno_corrente, anno_corrente.nome_anno_scolastico

    oggi = timezone.localdate()
    anno_inizio = oggi.year if oggi.month >= 9 else oggi.year - 1
    anno_fine = anno_inizio + 1
    return None, f"{anno_inizio}/{anno_fine}"


def build_school_year_status(anno_scolastico):
    if not anno_scolastico:
        return {"label": "Non configurato", "tone": "muted"}

    oggi = timezone.localdate()
    if anno_scolastico.data_inizio and anno_scolastico.data_fine:
        if anno_scolastico.data_inizio <= oggi <= anno_scolastico.data_fine:
            return {"label": "Corrente", "tone": "success"}
        if anno_scolastico.data_inizio > oggi:
            return {"label": "Prossimo", "tone": "upcoming"}
        if anno_scolastico.data_fine < oggi:
            return {"label": "Concluso", "tone": "past"}

    if not anno_scolastico.attivo:
        return {"label": "Non attivo", "tone": "muted"}
    return {"label": "Da verificare", "tone": "muted"}


def apri_documento(request, pk):
    documento = get_object_or_404(
        Documento.objects.select_related("tipo_documento", "familiare", "studente"),
        pk=pk,
    )

    if not documento.file:
        raise Http404("Il documento non ha alcun file associato.")

    try:
        file_handle = documento.file.open("rb")
    except FileNotFoundError as exc:
        raise Http404("Il file del documento non e disponibile sul server.") from exc
    except DOCUMENT_STORAGE_ERROR_TYPES as exc:
        raise Http404(build_document_storage_error_message(exc)) from exc

    filename = documento.filename or f"documento-{documento.pk}"
    content_type, _encoding = mimetypes.guess_type(filename)
    response = FileResponse(file_handle, content_type=content_type or "application/octet-stream")
    response["Content-Disposition"] = f'inline; filename="{filename}"'
    return response


def elimina_documento(request, pk):
    documento = get_object_or_404(
        Documento.objects.select_related("tipo_documento", "familiare", "studente"),
        pk=pk,
    )
    popup = is_popup_request(request)
    return_url = resolve_document_return_url(request, documento)

    if request.method == "POST":
        documento.delete()

        if popup:
            return popup_response(request, "Documento eliminato correttamente.")

        messages.success(request, "Documento eliminato correttamente.")
        return redirect(return_url)

    return render(
        request,
        "anagrafica/documenti/documento_confirm_delete.html",
        {
            "documento": documento,
            "documento_label": build_document_display_label(documento),
            "documento_owner_label": build_document_owner_label(documento),
            "popup": popup,
            "return_url": return_url,
        },
    )


def build_document_owner_redirect_url(documento):
    if documento.familiare_id:
        return reverse("modifica_familiare", kwargs={"pk": documento.familiare_id})
    if documento.studente_id:
        return build_studente_redirect_url(documento.studente_id, "documenti")
    return reverse("lista_famiglie")


def resolve_document_return_url(request, documento):
    candidate = (request.GET.get("return_to") or request.POST.get("return_to") or "").strip()
    if candidate and url_has_allowed_host_and_scheme(candidate, allowed_hosts={request.get_host()}):
        return candidate
    return build_document_owner_redirect_url(documento)


def build_document_owner_label(documento):
    if documento.familiare_id:
        return f"Familiare {documento.familiare}"
    if documento.studente_id:
        return f"Studente {documento.studente}"
    return ""


def build_document_display_label(documento):
    return documento.descrizione or documento.filename or str(documento.tipo_documento)


def resolve_next_school_year(anno_corrente):
    if not anno_corrente:
        return None

    return (
        AnnoScolastico.objects.filter(data_inizio__gt=anno_corrente.data_inizio)
        .order_by("data_inizio", "id")
        .first()
    )


def resolve_inline_target(request, allowed_targets):
    edit_scope = request.POST.get("_edit_scope") or "full"
    inline_target = (request.POST.get("_inline_target") or "").strip()

    if edit_scope != "inline" or inline_target not in allowed_targets:
        return edit_scope, None

    return edit_scope, inline_target


def resolve_active_inline_tab(request, allowed_targets, default_target):
    if request.method == "POST":
        candidate = (request.POST.get("_inline_target") or "").strip()
    else:
        candidate = (request.GET.get("tab") or "").strip()

    if candidate in allowed_targets:
        return candidate

    return default_target


def build_famiglia_redirect_url(pk, active_inline_tab=None):
    url = reverse("lista_famiglie")
    if active_inline_tab and active_inline_tab != "studenti":
        return f"{url}?tab={active_inline_tab}"
    return url


def build_famiglia_logica_redirect_url(logical_key, active_inline_tab=None):
    if not logical_key:
        return reverse("lista_famiglie")

    url = reverse("modifica_famiglia_logica", kwargs={"key": logical_key})
    if active_inline_tab and active_inline_tab != "studenti":
        return f"{url}?tab={active_inline_tab}"
    return url


def build_famiglia_logica_form(logical_snapshot):
    initial = {
        "cognome_famiglia": logical_snapshot.cognome_famiglia,
        "indirizzo_principale": (
            logical_snapshot.indirizzo_principale.label_select()
            if logical_snapshot.indirizzo_principale
            else ""
        ),
        "attiva": True,
        "note": "",
    }
    return FamigliaForm(initial=initial)


def refresh_logical_family_snapshot(logical_snapshot):
    legacy_famiglia = logical_snapshot.legacy_family
    if legacy_famiglia and hasattr(legacy_famiglia, "_logical_family_snapshot"):
        delattr(legacy_famiglia, "_logical_family_snapshot")

    refreshed = resolve_logical_family_snapshot(logical_snapshot.logical_key)
    if refreshed:
        return refreshed

    if legacy_famiglia:
        return build_logical_family_snapshot(legacy_famiglia)

    return build_logical_family_snapshot_from_ids(
        logical_snapshot.student_ids,
        logical_snapshot.familiare_ids,
    )


def build_familiare_redirect_url(pk, active_inline_tab=None, default_tab="studenti"):
    url = reverse("modifica_familiare", kwargs={"pk": pk})
    if active_inline_tab and active_inline_tab != default_tab:
        return f"{url}?tab={active_inline_tab}"
    return url


def build_studente_redirect_url(pk, active_inline_tab=None):
    url = reverse("modifica_studente", kwargs={"pk": pk})
    if active_inline_tab and active_inline_tab != "iscrizioni":
        return f"{url}?tab={active_inline_tab}"
    return url


def pick_audit_entry(entries, action, reverse=False):
    action_entries = [entry for entry in entries if entry.azione == action]
    if reverse:
        action_entries = list(reversed(action_entries))

    user_entry = next((entry for entry in action_entries if entry.utente_id), None)
    if user_entry:
        return user_entry

    labeled_entry = next(
        (
            entry for entry in action_entries
            if entry.utente_label and entry.utente_label.casefold() != "sistema"
        ),
        None,
    )
    return labeled_entry or (action_entries[0] if action_entries else None)


def famiglia_audit_labels(famiglia):
    if not famiglia or not famiglia.pk:
        return "-", "-"

    entries = list(SistemaOperazioneCronologia.objects.select_related(
        "utente",
        "utente__profilo_permessi",
        "utente__profilo_permessi__ruolo_permessi",
    ).filter(
        app_label="anagrafica",
        model_name="famiglia",
        oggetto_id=str(famiglia.pk),
    ).order_by("data_operazione", "id"))
    created_entry = pick_audit_entry(
        entries,
        AzioneOperazioneCronologia.CREAZIONE,
    )
    updated_entry = pick_audit_entry(
        entries,
        AzioneOperazioneCronologia.MODIFICA,
        reverse=True,
    ) or created_entry

    return audit_user_label_with_role(created_entry), audit_user_label_with_role(updated_entry)


def studente_audit_labels(studente):
    if not studente or not studente.pk:
        return {
            "created_data": None,
            "created_label": "-",
            "updated_data": None,
            "updated_label": "-",
        }

    entries = list(SistemaOperazioneCronologia.objects.select_related(
        "utente",
        "utente__profilo_permessi",
        "utente__profilo_permessi__ruolo_permessi",
    ).filter(
        app_label="anagrafica",
        model_name="studente",
        oggetto_id=str(studente.pk),
    ).order_by("data_operazione", "id"))
    created_entry = pick_audit_entry(
        entries,
        AzioneOperazioneCronologia.CREAZIONE,
    )
    updated_entry = pick_audit_entry(
        entries,
        AzioneOperazioneCronologia.MODIFICA,
        reverse=True,
    ) or created_entry

    return {
        "created_data": created_entry.data_operazione if created_entry else None,
        "created_label": audit_user_label_with_role(created_entry),
        "updated_data": updated_entry.data_operazione if updated_entry else None,
        "updated_label": audit_user_label_with_role(updated_entry),
    }


def familiare_audit_labels(familiare):
    if not familiare or not familiare.pk:
        return {
            "created_data": None,
            "created_label": "-",
            "updated_data": None,
            "updated_label": "-",
        }

    entries = list(SistemaOperazioneCronologia.objects.select_related(
        "utente",
        "utente__profilo_permessi",
        "utente__profilo_permessi__ruolo_permessi",
    ).filter(
        app_label="anagrafica",
        model_name="familiare",
        oggetto_id=str(familiare.pk),
    ).order_by("data_operazione", "id"))
    created_entry = pick_audit_entry(
        entries,
        AzioneOperazioneCronologia.CREAZIONE,
    )
    updated_entry = pick_audit_entry(
        entries,
        AzioneOperazioneCronologia.MODIFICA,
        reverse=True,
    ) or created_entry

    return {
        "created_data": created_entry.data_operazione if created_entry else None,
        "created_label": audit_user_label_with_role(created_entry),
        "updated_data": updated_entry.data_operazione if updated_entry else None,
        "updated_label": audit_user_label_with_role(updated_entry),
    }


def famiglia_activity_entries(famiglia, limit=5):
    if not famiglia:
        return []

    snapshot = build_logical_family_snapshot(famiglia)
    if not snapshot.student_ids and not snapshot.familiare_ids:
        return []
    filters = Q()

    familiari_ids = [str(pk) for pk in snapshot.familiare_ids]
    if familiari_ids:
        filters |= Q(model_name="familiare", oggetto_id__in=familiari_ids)

    studenti_ids = [str(pk) for pk in snapshot.student_ids]
    if studenti_ids:
        filters |= Q(model_name="studente", oggetto_id__in=studenti_ids)

    documenti_ids = [
        str(pk)
        for pk in family_document_queryset(snapshot).values_list("pk", flat=True)
    ]
    if documenti_ids:
        filters |= Q(model_name="documento", oggetto_id__in=documenti_ids)

    if not filters:
        return []

    return list(
        SistemaOperazioneCronologia.objects.select_related(
            "utente",
            "utente__profilo_permessi",
            "utente__profilo_permessi__ruolo_permessi",
        )
        .filter(app_label="anagrafica")
        .filter(filters)
        .order_by("-data_operazione", "-id")[:limit]
    )


def studente_activity_entries(studente, iscrizione_ids=None, documenti_ids=None, limit=5):
    if not studente or not studente.pk:
        return []

    filters = Q(app_label="anagrafica", model_name="studente", oggetto_id=str(studente.pk))

    documenti_ids = [str(pk) for pk in (documenti_ids or []) if pk]
    if documenti_ids:
        filters |= Q(app_label="anagrafica", model_name="documento", oggetto_id__in=documenti_ids)

    iscrizione_ids = [str(pk) for pk in (iscrizione_ids or []) if pk]
    if iscrizione_ids:
        filters |= Q(app_label="economia", model_name="iscrizione", oggetto_id__in=iscrizione_ids)

    return list(
        SistemaOperazioneCronologia.objects.select_related(
            "utente",
            "utente__profilo_permessi",
            "utente__profilo_permessi__ruolo_permessi",
        )
        .filter(filters)
        .order_by("-data_operazione", "-id")[:limit]
    )


def familiare_activity_entries(familiare, documenti_ids=None, limit=5):
    if not familiare or not familiare.pk:
        return []

    filters = Q(app_label="anagrafica", model_name="familiare", oggetto_id=str(familiare.pk))

    documenti_ids = [str(pk) for pk in (documenti_ids or []) if pk]
    if documenti_ids:
        filters |= Q(app_label="anagrafica", model_name="documento", oggetto_id__in=documenti_ids)

    return list(
        SistemaOperazioneCronologia.objects.select_related(
            "utente",
            "utente__profilo_permessi",
            "utente__profilo_permessi__ruolo_permessi",
        )
        .filter(filters)
        .order_by("-data_operazione", "-id")[:limit]
    )


def audit_user_label_with_role(entry):
    if not entry:
        return "-"

    label = entry.utente_display
    ruolo_label = ""
    user = entry.utente
    if user:
        profilo = getattr(user, "profilo_permessi", None)
        if profilo:
            ruolo_label = getattr(profilo, "ruolo_display", "") or ""
        if not ruolo_label and user.is_superuser:
            ruolo_label = "Superuser"

    return f"{label} ({ruolo_label})" if ruolo_label else label


def last_update_audit_label(instance):
    entry = last_update_audit_entry(instance)
    return audit_user_label_with_role(entry)


def last_update_audit_entry(instance):
    if not instance or not instance.pk:
        return None

    entries = SistemaOperazioneCronologia.objects.select_related(
        "utente",
        "utente__profilo_permessi",
        "utente__profilo_permessi__ruolo_permessi",
    ).filter(
        app_label=instance._meta.app_label,
        model_name=instance._meta.model_name,
        oggetto_id=str(instance.pk),
    )
    entry = (
        entries
        .filter(azione=AzioneOperazioneCronologia.MODIFICA)
        .order_by("-data_operazione", "-id")
        .first()
    ) or (
        entries
        .filter(azione=AzioneOperazioneCronologia.CREAZIONE)
        .order_by("-data_operazione", "-id")
        .first()
    )

    return entry


def last_update_audit_info(instance):
    entry = last_update_audit_entry(instance)
    return {
        "data": entry.data_operazione if entry else None,
        "utente_label": audit_user_label_with_role(entry),
    }


def famiglia_familiari_inline_queryset(famiglia=None):
    if not famiglia:
        return Familiare.objects.none()

    snapshot = famiglia if hasattr(famiglia, "familiare_ids") else build_logical_family_snapshot(famiglia)
    return (
        Familiare.objects.filter(pk__in=snapshot.familiare_ids)
        .select_related(
            "relazione_familiare",
            "indirizzo__citta__provincia",
            "indirizzo__provincia",
            "luogo_nascita__provincia",
            "nazione_nascita",
            "nazionalita",
        )
        .order_by("cognome", "nome")
    )


def famiglia_studenti_inline_queryset(famiglia=None):
    if not famiglia:
        return Studente.objects.none()

    snapshot = famiglia if hasattr(famiglia, "student_ids") else build_logical_family_snapshot(famiglia)
    return (
        annotate_studenti_current_iscrizione_status(Studente.objects.filter(pk__in=snapshot.student_ids))
        .annotate(
            data_nascita_vuota=Case(
                When(data_nascita__isnull=True, then=Value(1)),
                default=Value(0),
                output_field=IntegerField(),
            )
        )
        .select_related(
            "indirizzo__citta__provincia",
            "indirizzo__provincia",
            "luogo_nascita__provincia",
            "nazione_nascita",
            "nazionalita",
        )
        .order_by("data_nascita_vuota", "data_nascita", "cognome", "nome", "id")
    )


def annotate_studenti_current_iscrizione_status(queryset, today=None):
    today = today or timezone.localdate()
    iscrizione_corrente = Iscrizione.objects.filter(
        studente=OuterRef("pk"),
        attiva=True,
        anno_scolastico__data_inizio__lte=today,
        anno_scolastico__data_fine__gte=today,
    )
    return queryset.annotate(
        ha_iscrizione_attiva_corrente=Exists(iscrizione_corrente),
    )


def _school_year_label(anno_scolastico):
    if not anno_scolastico:
        return ""
    return anno_scolastico.nome_anno_scolastico or str(anno_scolastico)


def _is_current_school_year(anno_scolastico, today):
    return bool(
        anno_scolastico
        and anno_scolastico.data_inizio
        and anno_scolastico.data_fine
        and anno_scolastico.data_inizio <= today <= anno_scolastico.data_fine
    )


def _is_future_school_year(anno_scolastico, today):
    return bool(anno_scolastico and anno_scolastico.data_inizio and anno_scolastico.data_inizio > today)


def current_iscrizione_class_display(iscrizione):
    classe_label = str(iscrizione.classe) if iscrizione and iscrizione.classe_id else ""
    if iscrizione and iscrizione.gruppo_classe_id:
        gruppo_label = iscrizione.gruppo_classe.nome_gruppo_classe if iscrizione.gruppo_classe else ""
        if gruppo_label and classe_label:
            return "Pluriclasse", f"{gruppo_label} ({classe_label})"
        if gruppo_label:
            return "Pluriclasse", gruppo_label
    if classe_label:
        return "Classe", classe_label
    return "", ""


def decorate_studenti_formset_current_enrollment_labels(studenti_formset, today=None):
    if studenti_formset is None:
        return

    student_instances = [form.instance for form in studenti_formset.forms if form.instance.pk]
    decorate_studenti_current_enrollment_labels(student_instances, today=today)


def decorate_studenti_current_enrollment_labels(student_instances, today=None):
    if not student_instances:
        return

    today = today or timezone.localdate()
    for studente in student_instances:
        studente.classe_corrente_famiglia_tipo = ""
        studente.classe_corrente_famiglia_label = ""
        studente.ha_iscrizione_attiva_corrente = False
        studente.iscrizione_status_badges = []

    student_ids = [studente.pk for studente in student_instances]
    if not student_ids:
        return

    iscrizioni_attive = (
        Iscrizione.objects
        .filter(
            studente_id__in=student_ids,
            attiva=True,
        )
        .filter(
            Q(anno_scolastico__data_inizio__lte=today, anno_scolastico__data_fine__gte=today)
            | Q(anno_scolastico__data_inizio__gt=today)
        )
        .select_related("anno_scolastico", "classe", "gruppo_classe")
        .order_by("studente_id", "anno_scolastico__data_inizio", "id")
    )

    student_map = {studente.pk: studente for studente in student_instances}
    labels_by_student = {}
    badges_seen = defaultdict(set)
    for iscrizione in iscrizioni_attive:
        studente = student_map.get(iscrizione.studente_id)
        if studente is None:
            continue

        anno = iscrizione.anno_scolastico
        anno_label = _school_year_label(anno)
        if _is_current_school_year(anno, today):
            studente.ha_iscrizione_attiva_corrente = True
            tipo, label = current_iscrizione_class_display(iscrizione)
            if label and iscrizione.studente_id not in labels_by_student:
                labels_by_student[iscrizione.studente_id] = (tipo, label)
            badge = {
                "label": f"ISCRITTO {anno_label}" if anno_label else "ISCRITTO",
                "css_class": "status-chip-success",
                "title": "Iscrizione attiva per l'anno scolastico corrente",
            }
        elif _is_future_school_year(anno, today):
            badge = {
                "label": f"PREISCRITTO {anno_label}" if anno_label else "PREISCRITTO",
                "css_class": "status-chip-warning",
                "title": "Preiscrizione attiva per un anno scolastico futuro",
            }
        else:
            continue

        badge_key = (badge["label"], badge["css_class"])
        if badge_key in badges_seen[iscrizione.studente_id]:
            continue
        badges_seen[iscrizione.studente_id].add(badge_key)
        studente.iscrizione_status_badges.append(badge)

    for studente in student_instances:
        tipo, label = labels_by_student.get(studente.pk, ("", ""))
        studente.classe_corrente_famiglia_tipo = tipo
        studente.classe_corrente_famiglia_label = label


def active_student_relative_prefetch(to_attr="relazioni_familiari_attive_prefetch"):
    return Prefetch(
        "relazioni_familiari",
        queryset=(
            StudenteFamiliare.objects.filter(attivo=True)
            .select_related(
                "familiare",
                "familiare__relazione_familiare",
                "familiare__persona",
                "familiare__persona__indirizzo",
                "familiare__persona__indirizzo__citta",
            )
            .order_by("familiare__persona__cognome", "familiare__persona__nome", "familiare_id")
        ),
        to_attr=to_attr,
    )


def active_relative_student_prefetch(to_attr="relazioni_studenti_attive_prefetch"):
    return Prefetch(
        "relazioni_studenti",
        queryset=(
            StudenteFamiliare.objects.filter(attivo=True)
            .select_related(
                "studente",
                "studente__indirizzo",
                "studente__indirizzo__citta",
                "studente__indirizzo__provincia",
                "studente__luogo_nascita",
                "studente__luogo_nascita__provincia",
            )
            .order_by("studente__cognome", "studente__nome", "studente_id")
        ),
        to_attr=to_attr,
    )


def _person_name(person):
    return " ".join(part for part in [getattr(person, "nome", ""), getattr(person, "cognome", "")] if part).strip()


def _join_limited_labels(labels, limit=2):
    values = [label for label in labels if label]
    if not values:
        return ""
    visible = values[:limit]
    suffix = f" +{len(values) - limit}" if len(values) > limit else ""
    return ", ".join(visible) + suffix


def decorate_studenti_direct_relation_labels(studenti):
    for studente in studenti or []:
        relazioni = getattr(studente, "relazioni_familiari_attive_prefetch", None)
        if relazioni is None:
            relazioni = list(
                studente.relazioni_familiari.filter(attivo=True)
                .select_related(
                    "familiare",
                    "familiare__relazione_familiare",
                    "familiare__persona",
                    "familiare__persona__indirizzo",
                    "familiare__persona__indirizzo__citta",
                )
                .order_by("familiare__persona__cognome", "familiare__persona__nome", "familiare_id")
            )

        labels = []
        for relazione in relazioni:
            familiare = relazione.familiare
            nome = _person_name(familiare)
            if relazione.relazione_familiare_id:
                nome = f"{nome} ({relazione.relazione_familiare})"
            labels.append(nome)

        studente.familiari_collegati_lista_label = _join_limited_labels(labels)
        studente.familiari_collegati_lista_context = ""


def decorate_familiari_direct_relation_labels(familiari):
    for familiare in familiari or []:
        relazioni = getattr(familiare, "relazioni_studenti_attive_prefetch", None)
        if relazioni is None:
            relazioni = list(
                familiare.relazioni_studenti.filter(attivo=True)
                .select_related(
                    "studente",
                    "studente__luogo_nascita",
                    "studente__luogo_nascita__provincia",
                )
                .order_by("studente__cognome", "studente__nome", "studente_id")
            )

        labels = [_person_name(relazione.studente) for relazione in relazioni]
        familiare.studenti_collegati_lista_label = _join_limited_labels(labels)
        familiare.studenti_collegati_lista_context = ""


def direct_student_peers_for_relations(studente, relazioni_familiari):
    familiare_ids = [relazione.familiare_id for relazione in relazioni_familiari if relazione.familiare_id]
    if not familiare_ids:
        return []

    relazioni = (
        StudenteFamiliare.objects.filter(
            attivo=True,
            familiare_id__in=familiare_ids,
        )
        .exclude(studente=studente)
        .select_related(
            "studente",
            "studente__indirizzo",
            "studente__indirizzo__citta",
            "studente__indirizzo__provincia",
            "studente__luogo_nascita",
            "studente__luogo_nascita__provincia",
        )
        .order_by("studente__cognome", "studente__nome", "studente_id")
    )

    studenti = []
    seen = set()
    for relazione in relazioni:
        if relazione.studente_id in seen:
            continue
        seen.add(relazione.studente_id)
        studenti.append(relazione.studente)
    return studenti


def direct_relative_peers_for_student_relations(familiare, relazioni_studenti):
    studente_ids = [relazione.studente_id for relazione in relazioni_studenti if relazione.studente_id]
    if not studente_ids:
        return []

    relazioni = (
        StudenteFamiliare.objects.filter(
            attivo=True,
            studente_id__in=studente_ids,
        )
        .exclude(familiare=familiare)
        .select_related(
            "familiare",
            "familiare__relazione_familiare",
            "familiare__persona",
            "familiare__persona__indirizzo",
            "familiare__persona__indirizzo__citta",
        )
        .order_by("familiare__persona__cognome", "familiare__persona__nome", "familiare_id")
    )

    familiari = []
    seen = set()
    for relazione in relazioni:
        if relazione.familiare_id in seen:
            continue
        seen.add(relazione.familiare_id)
        familiari.append(relazione.familiare)
    return familiari


def build_related_address_suggestions(people):
    addresses = {}
    counts = Counter()
    sources = defaultdict(list)

    for person, person_type in people or []:
        if not person:
            continue
        address = getattr(person, "indirizzo_effettivo", None)
        if not address or not getattr(address, "pk", None):
            continue
        address_id = str(address.pk)
        addresses[address_id] = address
        counts[address_id] += 1
        person_label = _person_name(person)
        if person_type and person_label:
            sources[address_id].append(f"{person_type}: {person_label}")
        elif person_label:
            sources[address_id].append(person_label)

    suggestions = []
    for address_id, address in addresses.items():
        source_labels = sources[address_id]
        suggestions.append(
            {
                "id": address_id,
                "label": address.label_select(),
                "label_full": address.label_full(),
                "count": counts[address_id],
                "sources": source_labels[:4],
                "sources_label": _join_limited_labels(source_labels, limit=3),
            }
        )

    return sorted(suggestions, key=lambda item: (-item["count"], item["label"].casefold(), item["id"]))


def build_familiare_address_suggestions(familiare, relazioni_studenti, parenti_collegati):
    people = []
    for relazione in relazioni_studenti or []:
        people.append((getattr(relazione, "studente", None), "Studente"))
    for parente in parenti_collegati or []:
        if not familiare or getattr(parente, "pk", None) != getattr(familiare, "pk", None):
            people.append((parente, "Familiare"))
    return build_related_address_suggestions(people)


def build_studente_address_suggestions(studente, relazioni_familiari, studenti_collegati):
    people = []
    for relazione in relazioni_familiari or []:
        people.append((getattr(relazione, "familiare", None), "Familiare"))
    for studente_collegato in studenti_collegati or []:
        if not studente or getattr(studente_collegato, "pk", None) != getattr(studente, "pk", None):
            people.append((studente_collegato, "Studente"))
    return build_related_address_suggestions(people)


def ordered_queryset_from_ids(model, ids, *, select_related_fields=()):
    ordered_ids = []
    seen = set()
    for item_id in ids or []:
        if not item_id or item_id in seen:
            continue
        seen.add(item_id)
        ordered_ids.append(item_id)

    if not ordered_ids:
        return model.objects.none()

    preserved_order = Case(
        *[When(pk=item_id, then=index) for index, item_id in enumerate(ordered_ids)],
        output_field=IntegerField(),
    )
    queryset = model.objects.filter(pk__in=ordered_ids)
    if select_related_fields:
        queryset = queryset.select_related(*select_related_fields)
    return queryset.order_by(preserved_order)


def ensure_direct_student_family_relation(studente, familiare):
    if not getattr(studente, "pk", None) or not getattr(familiare, "pk", None):
        return

    StudenteFamiliare.objects.update_or_create(
        studente=studente,
        familiare=familiare,
        defaults={
            "relazione_familiare_id": familiare.relazione_familiare_id,
            "referente_principale": familiare.referente_principale,
            "convivente": familiare.convivente,
            "attivo": bool(studente.attivo),
        },
    )


def build_familiari_formset(*, data=None, instance=None, prefix="familiari", logical=False, queryset=None):
    if logical:
        kwargs = {
            "prefix": prefix,
            "queryset": queryset if queryset is not None else famiglia_familiari_inline_queryset(instance),
        }
        if data is not None:
            kwargs["data"] = data
        return LogicalFamiliareFormSet(**kwargs)

    kwargs = {
        "prefix": prefix,
        "queryset": queryset if queryset is not None else famiglia_familiari_inline_queryset(instance),
    }
    if data is not None:
        kwargs["data"] = data
    if instance is not None:
        kwargs["instance"] = instance
    return FamiliareFormSet(**kwargs)


def build_studenti_formset(*, data=None, instance=None, prefix="studenti", logical=False, queryset=None):
    if logical:
        kwargs = {
            "prefix": prefix,
            "queryset": queryset if queryset is not None else famiglia_studenti_inline_queryset(instance),
        }
        if data is not None:
            kwargs["data"] = data
        return LogicalStudenteFormSet(**kwargs)

    kwargs = {
        "prefix": prefix,
        "queryset": queryset if queryset is not None else famiglia_studenti_inline_queryset(instance),
    }
    if data is not None:
        kwargs["data"] = data
    if instance is not None:
        kwargs["instance"] = instance
    return StudenteFormSet(**kwargs)


def studente_iscrizioni_inline_queryset(studente=None):
    if not studente:
        return Iscrizione.objects.none()

    ordered_rate_queryset = (
        RataIscrizione.objects.select_related("metodo_pagamento")
        .order_by(
            "anno_riferimento",
            "mese_riferimento",
            "numero_rata",
            "id",
        )
    )
    tariffa_queryset = TariffaCondizioneIscrizione.objects.filter(attiva=True).order_by(
        "ordine_figlio_da",
        "ordine_figlio_a",
        "id",
    )

    return (
        Iscrizione.objects.filter(studente=studente)
        .select_related(
            "anno_scolastico",
            "classe",
            "gruppo_classe",
            "stato_iscrizione",
            "condizione_iscrizione",
            "agevolazione",
        )
        .prefetch_related(
            Prefetch("rate", queryset=ordered_rate_queryset),
            Prefetch("condizione_iscrizione__tariffe", queryset=tariffa_queryset),
        )
        .order_by("-anno_scolastico__data_inizio", "-id")
    )


STUDENTE_RATE_SYNC_ALL_CHANGED_FIELDS = {"data_nascita"}


def student_form_changes_require_full_rate_sync(form):
    return bool(STUDENTE_RATE_SYNC_ALL_CHANGED_FIELDS.intersection(getattr(form, "changed_data", [])))


def sync_studente_iscrizioni_rate_schedules(studente, *, iscrizioni=None, sync_all=False):
    queryset = studente_iscrizioni_inline_queryset(studente)

    if not sync_all:
        iscrizione_ids = [item.pk for item in (iscrizioni or []) if getattr(item, "pk", None)]
        if not iscrizione_ids:
            return 0
        queryset = queryset.filter(pk__in=iscrizione_ids)

    missing_rate_count = 0
    for iscrizione in queryset:
        if (
            not getattr(iscrizione, "anno_scolastico_id", None)
            or not getattr(iscrizione, "condizione_iscrizione_id", None)
            or not getattr(iscrizione, "stato_iscrizione_id", None)
        ):
            continue

        esito_rate = iscrizione.sync_rate_schedule()
        if esito_rate == "missing":
            missing_rate_count += 1

    return missing_rate_count


def studente_documenti_inline_queryset(studente=None):
    if not studente:
        return Documento.objects.none()

    return (
        Documento.objects.filter(studente=studente)
        .select_related("tipo_documento")
        .order_by("-data_caricamento", "-id")
    )


def build_iscrizioni_studente_formset(*, data=None, instance=None, prefix="iscrizioni", queryset=None):
    kwargs = {
        "prefix": prefix,
        "queryset": queryset if queryset is not None else studente_iscrizioni_inline_queryset(instance),
    }
    if data is not None:
        kwargs["data"] = data
    if instance is not None:
        kwargs["instance"] = instance
    return IscrizioneStudenteFormSet(**kwargs)


def build_documenti_studente_formset(*, data=None, files=None, instance=None, prefix="documenti", queryset=None):
    kwargs = {
        "prefix": prefix,
        "queryset": queryset if queryset is not None else studente_documenti_inline_queryset(instance),
    }
    if data is not None:
        kwargs["data"] = data
    if files is not None:
        kwargs["files"] = files
    if instance is not None:
        kwargs["instance"] = instance
    return DocumentoStudenteFormSet(**kwargs)


def build_studente_document_counts(studente, today):
    counts = studente.documenti.aggregate(
        totale=Count("id"),
        in_scadenza=Count(
            "id",
            filter=Q(
                scadenza__isnull=False,
                scadenza__gte=today,
                scadenza__lte=today + timedelta(days=30),
            ),
        ),
        scaduti=Count(
            "id",
            filter=Q(
                scadenza__isnull=False,
                scadenza__lt=today,
            ),
        ),
    )
    return {
        "count_documenti": counts["totale"] or 0,
        "count_documenti_in_scadenza": counts["in_scadenza"] or 0,
        "count_documenti_scaduti": counts["scaduti"] or 0,
    }


def count_studente_rate_scadute_from_overview(rate_overview, today):
    count = 0

    for item in rate_overview or []:
        for month in item.get("months", []):
            importo_finale = month.get("importo_finale") or Decimal("0.00")
            importo_pagato = month.get("importo_pagato") or Decimal("0.00")
            if (
                month.get("data_scadenza")
                and month["data_scadenza"] < today
                and importo_finale > 0
                and not month.get("pagata")
                and importo_pagato < importo_finale
            ):
                count += 1

    return count


def should_prefer_initial_famiglia_tab(request, allowed_targets):
    if request.method == "POST":
        return True

    requested_tab = (request.GET.get("tab") or "").strip()
    return requested_tab in allowed_targets


def build_school_year_months(anno_scolastico):
    if not anno_scolastico or not anno_scolastico.data_inizio or not anno_scolastico.data_fine:
        return []

    current_month = anno_scolastico.data_inizio.replace(day=1)
    end_month = anno_scolastico.data_fine.replace(day=1)
    months = []

    while current_month <= end_month:
        months.append(
            {
                "year": current_month.year,
                "month": current_month.month,
                "label": f"{MONTH_LABELS.get(current_month.month, current_month.month)} {current_month.year}",
            }
        )

        if current_month.month == 12:
            current_month = date(current_month.year + 1, 1, 1)
        else:
            current_month = date(current_month.year, current_month.month + 1, 1)

    return months


def build_iscrizione_dashboard_rate_rows(iscrizione):
    rate_iscrizione = sorted(
        iscrizione.rate.all(),
        key=lambda rata: (
            rata.anno_riferimento,
            rata.mese_riferimento,
            rata.numero_rata,
            rata.id,
        ),
    )

    if rate_iscrizione:
        rate_rows = [
            {
                "year": rata.anno_riferimento,
                "month": rata.mese_riferimento,
                "tipo_rata": rata.tipo_rata or RataIscrizione.TIPO_MENSILE,
                "numero_rata": rata.numero_rata,
                "importo_finale": rata.importo_finale or Decimal("0.00"),
                "importo_incassato": rata.importo_pagato or Decimal("0.00"),
            }
            for rata in rate_iscrizione
        ]
    else:
        rate_rows = [
            {
                "year": item["anno_riferimento"],
                "month": item["mese_riferimento"],
                "tipo_rata": item.get("tipo_rata", RataIscrizione.TIPO_MENSILE),
                "numero_rata": item["numero_rata"],
                "importo_finale": item["importo_finale"] or Decimal("0.00"),
                "importo_incassato": Decimal("0.00"),
            }
            for item in iscrizione.build_rate_plan()
        ]

    tariffa = iscrizione.get_tariffa_applicabile() if not iscrizione.non_pagante else None
    totale_lordo_annuo = tariffa.retta_annuale if tariffa else Decimal("0.00")
    importo_preiscrizione = iscrizione.get_importo_preiscrizione_dovuto()
    piano_lordo_mensile = iscrizione.build_rate_mensili_entries_for_importo(totale_lordo_annuo)
    importi_lordi_per_numero_rata = {
        item["numero_rata"]: item["importo_dovuto"]
        for item in piano_lordo_mensile
    }
    totale_lordo_periodo = sum(importi_lordi_per_numero_rata.values(), Decimal("0.00"))

    dashboard_rows = []
    for index, rate_row in enumerate(rate_rows):
        importo_finale = rate_row["importo_finale"] or Decimal("0.00")
        importo_incassato = rate_row["importo_incassato"] or Decimal("0.00")
        if rate_row["tipo_rata"] == RataIscrizione.TIPO_PREISCRIZIONE:
            importo_totale = importo_preiscrizione
        elif rate_row["tipo_rata"] == RataIscrizione.TIPO_UNICA_SOLUZIONE:
            importo_totale = totale_lordo_periodo
        else:
            importo_totale = importi_lordi_per_numero_rata.get(rate_row["numero_rata"], Decimal("0.00"))
        dashboard_rows.append(
            {
                "year": rate_row["year"],
                "month": rate_row["month"],
                "tipo_rata": rate_row["tipo_rata"],
                "importo_totale": importo_totale,
                "importo_incassato": importo_incassato,
                "importo_rimanente": max(importo_finale - importo_incassato, Decimal("0.00")),
            }
        )

    return dashboard_rows


def build_studente_projected_rate_plan(iscrizione, tariffa, importo_preiscrizione):
    return iscrizione.build_rate_plan()


def build_rate_month_payment_status(*, importo_finale, importo_pagato, pagata=False, is_projected=False):
    if is_projected:
        return {
            "payment_status": "projected",
            "status_class": "is-projected",
            "status_label": "Prevista",
        }

    finale = importo_finale or Decimal("0.00")
    pagato = importo_pagato or Decimal("0.00")

    if pagata or (finale > 0 and pagato >= finale):
        return {
            "payment_status": "paid",
            "status_class": "is-paid",
            "status_label": "Pagata",
        }

    if pagato > 0:
        return {
            "payment_status": "partial",
            "status_class": "is-partial",
            "status_label": "Pagata parzialmente",
        }

    if finale > 0:
        return {
            "payment_status": "unpaid",
            "status_class": "is-unpaid",
            "status_label": "Da pagare",
        }

    return {
        "payment_status": "not_due",
        "status_class": "is-not-due",
        "status_label": "Non dovuta",
    }


def build_famiglia_rette_mensili_year_summary(famiglia, anno_scolastico, iscrizioni, *, today=None, index=0):
    today = today or timezone.localdate()
    has_studenti = bool(build_logical_family_snapshot(famiglia).student_ids)
    rows = []
    totale_mensile = Decimal("0.00")
    totale_pagato = Decimal("0.00")
    totale_residuo = Decimal("0.00")
    anno_label = anno_scolastico.nome_anno_scolastico if anno_scolastico else ""

    for iscrizione in iscrizioni:
        riepilogo = iscrizione.get_riepilogo_economico()
        rate_rows = build_iscrizione_dashboard_rate_rows(iscrizione)
        importo_pagato = sum(
            ((row["importo_incassato"] or Decimal("0.00")) for row in rate_rows),
            Decimal("0.00"),
        )
        importo_residuo = sum(
            ((row["importo_rimanente"] or Decimal("0.00")) for row in rate_rows),
            Decimal("0.00"),
        )
        importo_totale = importo_pagato + importo_residuo
        progresso = (
            int(((importo_pagato / importo_totale) * Decimal("100")).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
            if importo_totale > 0
            else 0
        )
        classe_tipo, classe_label = current_iscrizione_class_display(iscrizione)

        if iscrizione.non_pagante:
            importo_rata = Decimal("0.00")
            importo_caption = "Non pagante"
            importo_meta = "Nessuna retta mensile"
        elif riepilogo["pagamento_unica_soluzione"]:
            importo_rata = riepilogo["rata_unica"] or Decimal("0.00")
            importo_caption = "Unica soluzione"
            importo_meta = (
                f"Scadenza {riepilogo['scadenza_pagamento_unica'].strftime('%d/%m/%Y')}"
                if riepilogo.get("scadenza_pagamento_unica")
                else "Pagamento annuale"
            )
        else:
            importo_rata = riepilogo["rata_standard"] or Decimal("0.00")
            importo_caption = f"{riepilogo['numero_mensilita']} rate mensili"
            importo_meta = (
                f"Ultima rata {riepilogo['rata_finale']}"
                if riepilogo["ultima_rata_diversa"]
                else "Importo ricorrente"
            )
            totale_mensile += importo_rata

        totale_pagato += importo_pagato
        totale_residuo += importo_residuo
        rows.append(
            {
                "studente": iscrizione.studente,
                "iscrizione": iscrizione,
                "classe_tipo": classe_tipo,
                "classe_label": classe_label,
                "importo_rata": importo_rata,
                "importo_caption": importo_caption,
                "importo_meta": importo_meta,
                "pagato": importo_pagato,
                "residuo": importo_residuo,
                "progresso": min(max(progresso, 0), 100),
                "pagamento_unica_soluzione": riepilogo["pagamento_unica_soluzione"],
                "non_pagante": iscrizione.non_pagante,
            }
        )

    anno_key = f"anno-{anno_scolastico.pk}" if anno_scolastico else f"anno-empty-{index}"
    is_current = bool(
        anno_scolastico
        and anno_scolastico.data_inizio
        and anno_scolastico.data_fine
        and anno_scolastico.data_inizio <= today <= anno_scolastico.data_fine
    )

    return {
        "anno": anno_scolastico,
        "anno_id": anno_scolastico.pk if anno_scolastico else None,
        "key": anno_key,
        "panel_id": f"family-rate-year-panel-{anno_scolastico.pk if anno_scolastico else index}",
        "anno_label": anno_label,
        "is_current": is_current,
        "empty_message": (
            "Nessuna iscrizione attiva per l'anno corrente."
            if is_current
            else "Nessuna iscrizione attiva per l'anno selezionato."
        ) if has_studenti else "Nessuno studente inserito.",
        "rows": rows,
        "totale_mensile": totale_mensile,
        "totale_pagato": totale_pagato,
        "totale_residuo": totale_residuo,
        "has_studenti": has_studenti,
    }


def build_famiglia_rette_mensili_summary(famiglia, today=None):
    today = today or timezone.localdate()
    anno_predefinito = resolve_default_anno_scolastico(today=today)
    snapshot = build_logical_family_snapshot(famiglia)
    iscrizioni = list(
        Iscrizione.objects.filter(
            studente_id__in=snapshot.student_ids,
            attiva=True,
        )
        .select_related(
            "studente",
            "anno_scolastico",
            "stato_iscrizione",
            "condizione_iscrizione",
            "classe",
            "gruppo_classe",
            "agevolazione",
        )
        .prefetch_related("rate", "condizione_iscrizione__tariffe")
        .order_by(
            "anno_scolastico__data_inizio",
            "anno_scolastico_id",
            "studente__data_nascita",
            "studente__cognome",
            "studente__nome",
            "studente_id",
            "-data_iscrizione",
            "-id",
        )
    )

    iscrizioni_per_anno = defaultdict(list)
    anni_per_id = {}

    if anno_predefinito:
        anni_per_id[anno_predefinito.pk] = anno_predefinito

    for iscrizione in iscrizioni:
        if not iscrizione.anno_scolastico_id:
            continue

        anno = iscrizione.anno_scolastico
        include_anno = (
            not anno_predefinito
            or anno.pk == anno_predefinito.pk
            or (anno.data_fine and anno.data_fine >= today)
        )
        if not include_anno:
            continue

        anni_per_id[anno.pk] = anno
        iscrizioni_per_anno[anno.pk].append(iscrizione)

    anni = sorted(
        anni_per_id.values(),
        key=lambda anno: (
            0 if anno_predefinito and anno.pk == anno_predefinito.pk else 1,
            anno.data_inizio or date.max,
            anno.pk,
        ),
    )

    year_summaries = [
        build_famiglia_rette_mensili_year_summary(
            famiglia,
            anno,
            iscrizioni_per_anno.get(anno.pk, []),
            today=today,
            index=index,
        )
        for index, anno in enumerate(anni)
    ]

    for index, summary in enumerate(year_summaries):
        summary["is_default"] = index == 0

    default_summary = year_summaries[0] if year_summaries else {
        "anno_label": "",
        "rows": [],
        "totale_mensile": Decimal("0.00"),
        "totale_pagato": Decimal("0.00"),
        "totale_residuo": Decimal("0.00"),
        "has_studenti": bool(snapshot.student_ids),
    }

    return {
        **default_summary,
        "years": year_summaries,
        "has_year_switch": len(year_summaries) > 1,
    }


def build_economia_dashboard_data(anno_corrente):
    default_data = {
        "configured_year": bool(anno_corrente),
        "count_studenti_iscritti": 0,
        "count_studenti_paganti": 0,
        "count_studenti_non_paganti": 0,
        "count_studenti_riduzione_speciale": 0,
        "totale_rette_annuo": Decimal("0.00"),
        "totale_rette_incassato": Decimal("0.00"),
        "totale_rette_rimanenti": Decimal("0.00"),
        "totale_preiscrizioni": Decimal("0.00"),
        "totale_preiscrizioni_incassato": Decimal("0.00"),
        "totale_preiscrizioni_rimanenti": Decimal("0.00"),
        "media_mensile_rette": Decimal("0.00"),
        "totale_riduzioni_speciali": Decimal("0.00"),
        "totale_scambi_retta": Decimal("0.00"),
        "agevolazioni": [],
        "riepilogo_preiscrizioni": {
            "label": "Preiscrizioni",
            "importo_totale": Decimal("0.00"),
            "importo_incassato": Decimal("0.00"),
            "importo_rimanente": Decimal("0.00"),
        },
        "riepilogo_mensile": [],
    }

    if not anno_corrente:
        return default_data

    school_year_months = build_school_year_months(anno_corrente)
    school_year_keys = {(item["year"], item["month"]) for item in school_year_months}

    iscrizioni_anno_corrente = list(
        Iscrizione.objects.filter(
            anno_scolastico=anno_corrente,
            attiva=True,
        )
        .select_related(
            "studente",
            "agevolazione",
            "condizione_iscrizione",
        )
        .prefetch_related("rate")
        .order_by("studente__cognome", "studente__nome", "id")
    )

    monthly_total_map = defaultdict(lambda: Decimal("0.00"))
    monthly_paid_map = defaultdict(lambda: Decimal("0.00"))
    monthly_remaining_map = defaultdict(lambda: Decimal("0.00"))
    agevolazioni_map = {}

    count_studenti_paganti = 0
    count_studenti_non_paganti = 0
    count_studenti_riduzione_speciale = 0
    totale_rette_annuo = Decimal("0.00")
    totale_rette_incassato = Decimal("0.00")
    totale_rette_rimanenti = Decimal("0.00")
    totale_preiscrizioni = Decimal("0.00")
    totale_preiscrizioni_incassato = Decimal("0.00")
    totale_preiscrizioni_rimanenti = Decimal("0.00")
    totale_riduzioni_speciali = Decimal("0.00")
    totale_scambi_retta = (
        PrestazioneScambioRetta.objects.filter(
            anno_scolastico=anno_corrente,
            familiare__abilitato_scambio_retta=True,
        ).aggregate(total=Sum("importo_maturato"))["total"]
        or Decimal("0.00")
    )

    for iscrizione in iscrizioni_anno_corrente:
        if iscrizione.non_pagante:
            count_studenti_non_paganti += 1
        else:
            count_studenti_paganti += 1

        importo_riduzione = iscrizione.get_importo_riduzione_applicata()
        if importo_riduzione > 0:
            count_studenti_riduzione_speciale += 1
            totale_riduzioni_speciali += importo_riduzione

        if iscrizione.agevolazione_id:
            agevolazione_data = agevolazioni_map.setdefault(
                iscrizione.agevolazione_id,
                {
                    "nome_agevolazione": str(iscrizione.agevolazione),
                    "count_studenti": 0,
                    "studenti": [],
                    "totale_importo": Decimal("0.00"),
                },
            )
            agevolazione_data["count_studenti"] += 1
            agevolazione_data["studenti"].append(str(iscrizione.studente))
            agevolazione_data["totale_importo"] += iscrizione.get_importo_agevolazione_applicata()

        rate_rows = build_iscrizione_dashboard_rate_rows(iscrizione)
        for rate_row in rate_rows:
            if rate_row["tipo_rata"] == RataIscrizione.TIPO_PREISCRIZIONE:
                totale_preiscrizioni += rate_row["importo_totale"]
                totale_preiscrizioni_incassato += rate_row["importo_incassato"]
                totale_preiscrizioni_rimanenti += rate_row["importo_rimanente"]
                continue

            totale_rette_annuo += rate_row["importo_totale"]
            totale_rette_incassato += rate_row["importo_incassato"]
            totale_rette_rimanenti += rate_row["importo_rimanente"]

            month_key = (rate_row["year"], rate_row["month"])
            if month_key not in school_year_keys:
                continue

            monthly_total_map[month_key] += rate_row["importo_totale"]
            monthly_paid_map[month_key] += rate_row["importo_incassato"]
            monthly_remaining_map[month_key] += rate_row["importo_rimanente"]

    riepilogo_mensile = [
        {
            "label": item["label"],
            "importo_totale": monthly_total_map[(item["year"], item["month"])],
            "importo_incassato": monthly_paid_map[(item["year"], item["month"])],
            "importo_rimanente": monthly_remaining_map[(item["year"], item["month"])],
        }
        for item in school_year_months
    ]

    total_months = len(riepilogo_mensile)
    media_mensile_rette = (
        (totale_rette_annuo / total_months).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        if total_months
        else Decimal("0.00")
    )

    agevolazioni = sorted(
        [
            {
                "nome_agevolazione": item["nome_agevolazione"],
                "count_studenti": item["count_studenti"],
                "studenti_label": (
                    "1 Studente"
                    if item["count_studenti"] == 1
                    else f"{item['count_studenti']} Studenti"
                ),
                "studenti_names": ", ".join(item["studenti"]),
                "totale_importo": item["totale_importo"],
            }
            for item in agevolazioni_map.values()
            if item["count_studenti"] > 0
        ],
        key=lambda item: item["nome_agevolazione"].lower(),
    )

    return {
        "configured_year": True,
        "count_studenti_iscritti": len(iscrizioni_anno_corrente),
        "count_studenti_paganti": count_studenti_paganti,
        "count_studenti_non_paganti": count_studenti_non_paganti,
        "count_studenti_riduzione_speciale": count_studenti_riduzione_speciale,
        "totale_rette_annuo": totale_rette_annuo,
        "totale_rette_incassato": totale_rette_incassato,
        "totale_rette_rimanenti": totale_rette_rimanenti,
        "totale_preiscrizioni": totale_preiscrizioni,
        "totale_preiscrizioni_incassato": totale_preiscrizioni_incassato,
        "totale_preiscrizioni_rimanenti": totale_preiscrizioni_rimanenti,
        "media_mensile_rette": media_mensile_rette,
        "totale_riduzioni_speciali": totale_riduzioni_speciali,
        "totale_scambi_retta": totale_scambi_retta,
        "agevolazioni": agevolazioni,
        "riepilogo_preiscrizioni": {
            "label": "Preiscrizioni",
            "importo_totale": totale_preiscrizioni,
            "importo_incassato": totale_preiscrizioni_incassato,
            "importo_rimanente": totale_preiscrizioni_rimanenti,
        },
        "riepilogo_mensile": riepilogo_mensile,
    }


def build_studente_rate_overview(studente, iscrizioni=None):
    overview = []

    iscrizioni = list(iscrizioni) if iscrizioni is not None else list(studente_iscrizioni_inline_queryset(studente))
    ordine_figlio_mappa = {}

    anni_scolastici_ids = {
        iscrizione.anno_scolastico_id
        for iscrizione in iscrizioni
        if iscrizione.anno_scolastico_id
    }
    if anni_scolastici_ids and getattr(studente, "pk", None):
        familiari_ids = list(
            StudenteFamiliare.objects.filter(studente=studente, attivo=True)
            .values_list("familiare_id", flat=True)
        )
        studenti_ids = {studente.pk}
        if familiari_ids:
            studenti_ids.update(
                StudenteFamiliare.objects.filter(familiare_id__in=familiari_ids, attivo=True)
                .values_list("studente_id", flat=True)
            )
        iscrizioni_famiglia = (
            Iscrizione.objects.filter(
                studente_id__in=studenti_ids,
                anno_scolastico_id__in=anni_scolastici_ids,
            )
            .select_related("studente")
            .order_by(
                "anno_scolastico_id",
                "studente__data_nascita",
                "studente__cognome",
                "studente__nome",
                "studente_id",
                "id",
            )
        )

        progressivi_per_anno = defaultdict(int)
        for iscrizione_famiglia in iscrizioni_famiglia:
            progressivi_per_anno[iscrizione_famiglia.anno_scolastico_id] += 1
            ordine_figlio_mappa[iscrizione_famiglia.pk] = progressivi_per_anno[iscrizione_famiglia.anno_scolastico_id]

    for iscrizione in iscrizioni:
        if (
            not getattr(iscrizione, "anno_scolastico_id", None)
            or not getattr(iscrizione, "stato_iscrizione_id", None)
            or not getattr(iscrizione, "condizione_iscrizione_id", None)
        ):
            continue

        ordine_figlio = ordine_figlio_mappa.get(iscrizione.pk)
        tariffe_condizione = list(iscrizione.condizione_iscrizione.tariffe.all())
        tariffa = None
        if not iscrizione.non_pagante and ordine_figlio is not None:
            tariffa = next(
                (
                    item for item in tariffe_condizione
                    if item.ordine_figlio_da <= ordine_figlio
                    and (item.ordine_figlio_a is None or item.ordine_figlio_a >= ordine_figlio)
                ),
                None,
            )

        if ordine_figlio is not None:
            iscrizione._ordine_figlio_cache = ordine_figlio
        iscrizione._tariffa_applicabile_cache = tariffa

        rate = list(iscrizione.rate.all())
        importo_preiscrizione = Decimal("0.00") if iscrizione.non_pagante or not tariffa else (tariffa.preiscrizione or Decimal("0.00"))

        if rate:
            months = [
                {
                    "label": rata.display_period_label,
                    "display_label": rata.display_label,
                    "is_preiscrizione": rata.is_preiscrizione,
                    "is_unica_soluzione": rata.is_unica_soluzione,
                    "numero_rata": rata.numero_rata,
                    "importo_dovuto": rata.importo_dovuto,
                    "importo_finale": rata.importo_finale,
                    "importo_pagato": rata.importo_pagato,
                    "pagata": rata.pagata,
                    "data_scadenza": rata.data_scadenza,
                    "data_pagamento": rata.data_pagamento,
                    "credito_applicato": rata.credito_applicato,
                    "altri_sgravi": rata.altri_sgravi,
                    "metodo_pagamento": rata.metodo_pagamento,
                    "rata_pk": rata.pk,
                    "is_projected": False,
                    **build_rate_month_payment_status(
                        importo_finale=rata.importo_finale,
                        importo_pagato=rata.importo_pagato,
                        pagata=rata.pagata,
                    ),
                }
                for rata in rate
            ]
        else:
            piano = build_studente_projected_rate_plan(
                iscrizione,
                tariffa=tariffa,
                importo_preiscrizione=importo_preiscrizione,
            )
            months = [
                {
                    "label": (
                        item["descrizione"]
                        if item.get("tipo_rata") in {RataIscrizione.TIPO_PREISCRIZIONE, RataIscrizione.TIPO_UNICA_SOLUZIONE}
                        else f"{MONTH_LABELS.get(item['mese_riferimento'], item['mese_riferimento'])} {item['anno_riferimento']}"
                    ),
                    "display_label": (
                        item["descrizione"]
                        if item.get("tipo_rata") in {RataIscrizione.TIPO_PREISCRIZIONE, RataIscrizione.TIPO_UNICA_SOLUZIONE}
                        else f"Rata {item['numero_rata']}"
                    ),
                    "is_preiscrizione": item.get("tipo_rata") == RataIscrizione.TIPO_PREISCRIZIONE,
                    "is_unica_soluzione": item.get("tipo_rata") == RataIscrizione.TIPO_UNICA_SOLUZIONE,
                    "numero_rata": item["numero_rata"],
                    "importo_dovuto": item["importo_dovuto"],
                    "importo_finale": item["importo_finale"],
                    "importo_pagato": None,
                    "pagata": False,
                    "data_scadenza": item["data_scadenza"],
                    "data_pagamento": None,
                    "credito_applicato": item["credito_applicato"],
                    "altri_sgravi": item["altri_sgravi"],
                    "metodo_pagamento": None,
                    "rata_pk": None,
                    "is_projected": True,
                    **build_rate_month_payment_status(
                        importo_finale=item["importo_finale"],
                        importo_pagato=None,
                        pagata=False,
                        is_projected=True,
                    ),
                }
                for item in piano
            ]

        monthly_months = [
            month
            for month in months
            if not month["is_preiscrizione"] and not month.get("is_unica_soluzione")
        ]
        single_payment_month = next((month for month in months if month.get("is_unica_soluzione")), None)
        is_pagamento_unica_soluzione = iscrizione.is_pagamento_unica_soluzione
        numero_mensilita = 1 if is_pagamento_unica_soluzione else max(
            iscrizione.condizione_iscrizione.numero_mensilita_default or 0,
            1,
        )
        rata_standard = single_payment_month["importo_dovuto"] if single_payment_month else (
            monthly_months[0]["importo_dovuto"] if monthly_months else None
        )
        totale_dovuto = sum(
            (
                (
                    month["importo_finale"]
                    if month.get("importo_finale") is not None
                    else month.get("importo_dovuto")
                ) or Decimal("0.00")
                for month in months
            ),
            Decimal("0.00"),
        )
        totale_dovuto_senza_preiscrizione = sum(
            (
                (
                    month["importo_finale"]
                    if month.get("importo_finale") is not None
                    else month.get("importo_dovuto")
                ) or Decimal("0.00")
                for month in months
                if not month["is_preiscrizione"]
            ),
            Decimal("0.00"),
        )
        totale_pagato = sum(
            ((month.get("importo_pagato") or Decimal("0.00")) for month in months),
            Decimal("0.00"),
        )
        totale_residuo = max(totale_dovuto - totale_pagato, Decimal("0.00"))
        progresso = (
            int(((totale_pagato / totale_dovuto) * Decimal("100")).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
            if totale_dovuto > 0
            else 0
        )
        classe_tipo, classe_label = current_iscrizione_class_display(iscrizione)
        anno_scolastico = iscrizione.anno_scolastico
        is_current = bool(
            anno_scolastico
            and anno_scolastico.data_inizio
            and anno_scolastico.data_fine
            and anno_scolastico.data_inizio <= timezone.localdate() <= anno_scolastico.data_fine
        )
        if iscrizione.non_pagante:
            importo_caption = "Non pagante"
            importo_meta = "Nessuna retta dovuta"
        elif is_pagamento_unica_soluzione:
            importo_caption = "Unica soluzione"
            importo_meta = "Pagamento annuale"
        else:
            importo_caption = f"{numero_mensilita} rate mensili"
            importo_meta = "Importo ricorrente"

        overview.append(
            {
                "iscrizione": iscrizione,
                "anno_label": iscrizione.anno_scolastico.nome_anno_scolastico,
                "classe_tipo": classe_tipo,
                "classe_label": classe_label,
                "stato_label": str(iscrizione.stato_iscrizione),
                "condizione_label": iscrizione.condizione_iscrizione.nome_condizione_iscrizione,
                "has_tariffa": bool(tariffa),
                "retta_annuale_base": tariffa.retta_annuale if tariffa else None,
                "preiscrizione": importo_preiscrizione,
                "numero_mensilita": numero_mensilita,
                "rata_standard": rata_standard,
                "pagamento_unica_soluzione": is_pagamento_unica_soluzione,
                "modalita_pagamento_label": iscrizione.get_modalita_pagamento_retta_display(),
                "sconto_unica_soluzione": iscrizione.get_importo_sconto_unica_soluzione_applicato(),
                "agevolazione_label": str(iscrizione.agevolazione) if iscrizione.agevolazione_id else "",
                "riduzione_retta_speciale": (
                    iscrizione.importo_riduzione_speciale
                    if iscrizione.riduzione_speciale and iscrizione.importo_riduzione_speciale
                    else None
                ),
                "totale_dovuto": totale_dovuto,
                "totale_dovuto_senza_preiscrizione": totale_dovuto_senza_preiscrizione,
                "totale_pagato": totale_pagato,
                "totale_residuo": totale_residuo,
                "progresso": min(max(progresso, 0), 100),
                "importo_caption": importo_caption,
                "importo_meta": importo_meta,
                "is_current": is_current,
                "months": months,
                "month_rows": build_balanced_rate_rows(months),
                "has_projected_plan": bool(months) and all(month["is_projected"] for month in months),
            }
        )

    if any(item["is_current"] for item in overview):
        overview.sort(
            key=lambda item: (
                0 if item["is_current"] else 1,
                item["iscrizione"].anno_scolastico.data_inizio or date.max,
                item["iscrizione"].pk,
            )
        )

    return overview


def build_balanced_rate_rows(months, max_single_row=6):
    months = list(months or [])

    if not months:
        return []

    if len(months) <= max_single_row:
        return [months]

    split_index = (len(months) + 1) // 2
    return [months[:split_index], months[split_index:]]


def build_dashboard_school_year_statistics(anno_scolastico):
    data = {
        "anno_scolastico": anno_scolastico,
        "anno_label": anno_scolastico.nome_anno_scolastico if anno_scolastico else "",
        "count_studenti_iscritti": 0,
        "count_famiglie_iscritte": 0,
        "composizione_classi": [],
    }

    if not anno_scolastico:
        return data

    iscrizioni_anno = Iscrizione.objects.filter(
        anno_scolastico=anno_scolastico,
        attiva=True,
    )

    data["count_studenti_iscritti"] = iscrizioni_anno.values("studente_id").distinct().count()
    studenti_iscritti_ids = set(iscrizioni_anno.values_list("studente_id", flat=True).distinct())
    data["count_famiglie_iscritte"] = sum(
        1
        for snapshot in iter_logical_family_snapshots()
        if studenti_iscritti_ids.intersection(snapshot.student_ids)
    )

    classi_anno = (
        Classe.objects.filter(attiva=True)
        .annotate(
            count_studenti=Count(
                "iscrizioni__studente",
                filter=Q(iscrizioni__anno_scolastico=anno_scolastico, iscrizioni__attiva=True),
                distinct=True,
            )
        )
        .order_by("ordine_classe", "nome_classe", "sezione_classe", "id")
    )

    data["composizione_classi"] = [
        {
            "nome_classe": str(classe),
            "count_studenti": classe.count_studenti,
            "studenti_label": (
                "Nessun Studente"
                if classe.count_studenti == 0
                else f"{classe.count_studenti} Studente" if classe.count_studenti == 1 else f"{classe.count_studenti} Studenti"
            ),
        }
        for classe in classi_anno
    ]

    return data


def home(request):
    anno_corrente, anno_scolastico_corrente = resolve_current_school_year()
    impostazioni_generali = SistemaImpostazioniGenerali.objects.first()
    can_view_gestione_finanziaria = user_has_module_permission(
        request.user,
        "gestione_finanziaria",
        LivelloPermesso.VISUALIZZAZIONE,
    )
    mostra_dashboard_prossimo_anno = bool(
        impostazioni_generali and impostazioni_generali.mostra_dashboard_prossimo_anno_scolastico
    )

    dashboard_corrente = build_dashboard_school_year_statistics(anno_corrente)
    prossimo_anno_scolastico = resolve_next_school_year(anno_corrente) if mostra_dashboard_prossimo_anno else None
    dashboard_prossimo_anno = (
        build_dashboard_school_year_statistics(prossimo_anno_scolastico)
        if prossimo_anno_scolastico
        else build_dashboard_school_year_statistics(None)
    )

    economia_dashboard = build_economia_dashboard_data(anno_corrente)
    economia_dashboard_prossimo_anno = (
        build_economia_dashboard_data(prossimo_anno_scolastico)
        if prossimo_anno_scolastico
        else build_economia_dashboard_data(None)
    )
    calendario_dashboard = build_dashboard_calendar_data(user=request.user)
    gestione_finanziaria_dashboard = (
        build_home_financial_dashboard_data()
        if can_view_gestione_finanziaria
        else None
    )

    context = {
        "anno_scolastico_corrente": anno_scolastico_corrente,
        "anno_scolastico_corrente_obj": anno_corrente,
        "anno_scolastico_corrente_status": build_school_year_status(anno_corrente),
        "count_famiglie_iscritte": dashboard_corrente["count_famiglie_iscritte"],
        "count_studenti_iscritti": dashboard_corrente["count_studenti_iscritti"],
        "composizione_classi": dashboard_corrente["composizione_classi"],
        "economia_dashboard": economia_dashboard,
        "mostra_dashboard_prossimo_anno": mostra_dashboard_prossimo_anno and bool(prossimo_anno_scolastico),
        "dashboard_prossimo_anno": dashboard_prossimo_anno,
        "economia_dashboard_prossimo_anno": economia_dashboard_prossimo_anno,
        "calendario_dashboard": calendario_dashboard,
        "gestione_finanziaria_dashboard": gestione_finanziaria_dashboard,
    }

    return render(request, "home.html", context)

#Funzione per l'helper dei pop up di creazione/modifica rapida
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


def popup_response(request, message="Operazione completata."):
    return render(request, "popup/popup_close.html", {"message": message})
#Fine helper pop up


def get_indirizzo_usage(indirizzo):
    studenti = [
        f"{cognome} {nome}".strip()
        for cognome, nome in indirizzo.studenti.order_by("cognome", "nome").values_list("cognome", "nome")
    ]
    familiari = [
        f"{cognome} {nome}".strip()
        for cognome, nome in indirizzo.persone.filter(profilo_familiare__isnull=False)
        .order_by("cognome", "nome")
        .values_list("cognome", "nome")
    ]
    scuole_legali = list(
        indirizzo.scuole_sede_legale.order_by("nome_scuola").values_list("nome_scuola", flat=True)
    )
    scuole_operative = list(
        indirizzo.scuole_sede_operativa.order_by("nome_scuola").values_list("nome_scuola", flat=True)
    )
    scuole = list(dict.fromkeys(scuole_legali + scuole_operative))

    return {
        "famiglie": [],
        "studenti": studenti,
        "familiari": familiari,
        "scuole": scuole,
        "totale": len(studenti) + len(familiari) + len(scuole),
    }


def get_famiglia_delete_impact(famiglia):
    return {
        "familiari": [],
        "studenti": [],
        "documenti_famiglia": [],
        "documenti_familiari": [],
        "documenti_studenti": [],
        "totale_documenti": 0,
        "indirizzi_da_eliminare": [],
        "indirizzi_condivisi": [],
    }


def get_record_documents_impact(record):
    documenti = list(record.documenti.select_related("tipo_documento").order_by("-data_caricamento", "-id"))
    return {
        "documenti": documenti,
        "totale_documenti": len(documenti),
    }

#INIZIO VIEWS DEGLI INDIRIZZI
def lista_indirizzi(request):
    indirizzi = (
        Indirizzo.objects
        .select_related("citta", "provincia", "regione", "cap_scelto")
        .order_by("via", "numero_civico")
    )

    evidenzia_id = request.GET.get("highlight")

    return render(
        request,
        "anagrafica/indirizzi/indirizzo_list.html",
        {
            "indirizzi": indirizzi,
            "evidenzia_id": evidenzia_id,
        },
    )


def _indirizzo_duplicate_candidates_from_form(form, exclude_id=None):
    cap_obj = form.cleaned_data.get("cap_scelto")
    return address_duplicate_candidates(
        via=form.cleaned_data.get("via", ""),
        numero_civico=form.cleaned_data.get("numero_civico", ""),
        cap=getattr(cap_obj, "codice", ""),
        citta_id=getattr(form.cleaned_data.get("citta"), "pk", None),
        exclude_id=exclude_id,
    )


def _existing_indirizzo_response(request, indirizzo, popup):
    if popup:
        return popup_select_response(
            request,
            field_name="indirizzo_principale",
            object_id=indirizzo.pk,
            object_label=indirizzo.label_select(),
        )
    messages.info(request, "E' stato selezionato l'indirizzo gia presente in archivio.")
    return redirect(f"{reverse('lista_indirizzi')}?highlight={indirizzo.pk}")


def crea_indirizzo(request):
    popup = is_popup_request(request)
    duplicate_candidates = []

    if request.method == "POST":
        existing_id = request.POST.get("use_existing_address")
        if existing_id:
            indirizzo_esistente = get_object_or_404(Indirizzo, pk=existing_id)
            return _existing_indirizzo_response(request, indirizzo_esistente, popup)

        form = IndirizzoForm(request.POST)
        if form.is_valid():
            if request.POST.get("force_new_address") != "1":
                duplicate_candidates = _indirizzo_duplicate_candidates_from_form(form)
                if duplicate_candidates:
                    template_name = (
                        "anagrafica/indirizzi/indirizzo_popup_form.html"
                        if popup
                        else "anagrafica/indirizzi/indirizzo_form.html"
                    )
                    return render(
                        request,
                        template_name,
                        {
                            "form": form,
                            "popup": popup,
                            "duplicate_candidates": duplicate_candidates,
                        },
                    )
            indirizzo = form.save()

            if popup:
                return popup_select_response(
                    request,
                    field_name="indirizzo_principale",
                    object_id=indirizzo.pk,
                    object_label=indirizzo.label_select(),
                )

            messages.success(request, "Indirizzo creato correttamente.")
            return redirect(f"{reverse('lista_indirizzi')}?highlight={indirizzo.pk}")
    else:
        form = IndirizzoForm()

    template_name = "anagrafica/indirizzi/indirizzo_popup_form.html" if popup else "anagrafica/indirizzi/indirizzo_form.html"

    return render(
        request,
        template_name,
        {
            "form": form,
            "popup": popup,
            "duplicate_candidates": duplicate_candidates,
        },
    )


def modifica_indirizzo(request, pk):
    indirizzo = get_object_or_404(Indirizzo, pk=pk)
    popup = is_popup_request(request)
    duplicate_candidates = []

    if request.method == "POST":
        existing_id = request.POST.get("use_existing_address")
        if existing_id:
            indirizzo_esistente = get_object_or_404(Indirizzo, pk=existing_id)
            return _existing_indirizzo_response(request, indirizzo_esistente, popup)

        form = IndirizzoForm(request.POST, instance=indirizzo)
        if form.is_valid():
            if request.POST.get("force_new_address") != "1":
                duplicate_candidates = _indirizzo_duplicate_candidates_from_form(form, exclude_id=indirizzo.pk)
                if duplicate_candidates:
                    template_name = (
                        "anagrafica/indirizzi/indirizzo_popup_form.html"
                        if popup
                        else "anagrafica/indirizzi/indirizzo_form.html"
                    )
                    return render(
                        request,
                        template_name,
                        {
                            "form": form,
                            "indirizzo": indirizzo,
                            "popup": popup,
                            "duplicate_candidates": duplicate_candidates,
                        },
                    )
            indirizzo = form.save()

            if popup:
                return popup_select_response(
                    request,
                    field_name="indirizzo_principale",
                    object_id=indirizzo.pk,
                    object_label=indirizzo.label_select(),
                )

            messages.success(request, "Modifiche salvate correttamente.")
            return redirect(f"{reverse('lista_indirizzi')}?highlight={indirizzo.pk}")
    else:
        form = IndirizzoForm(instance=indirizzo)

    template_name = "anagrafica/indirizzi/indirizzo_popup_form.html" if popup else "anagrafica/indirizzi/indirizzo_form.html"

    return render(
        request,
        template_name,
        {
            "form": form,
            "indirizzo": indirizzo,
            "popup": popup,
            "duplicate_candidates": duplicate_candidates,
        },
    )


def elimina_indirizzo(request, pk):
    indirizzo = get_object_or_404(Indirizzo, pk=pk)
    popup = is_popup_request(request)

    object_id = indirizzo.pk
    usage = get_indirizzo_usage(indirizzo)

    if request.method == "POST":
        indirizzo.delete()

        if popup:
            return popup_delete_response(
                request,
                field_name="indirizzo_principale",
                object_id=object_id,
            )

        messages.success(request, "Indirizzo eliminato correttamente.")
        return redirect("lista_indirizzi")

    template_name = "anagrafica/indirizzi/indirizzo_popup_delete.html" if popup else "anagrafica/indirizzi/indirizzo_conferma_elimina.html"

    return render(
        request,
        template_name,
        {
            "indirizzo": indirizzo,
            "popup": popup,
            "usage": usage,
        },
    )


CONTACT_LABEL_CONFIG = {
    "indirizzo": {
        "model": LabelIndirizzo,
        "field_name": "label_indirizzo",
        "titolo_nuovo": "Nuova etichetta indirizzo",
        "titolo_modifica": "Modifica etichetta indirizzo",
        "titolo_elimina": "Elimina etichetta indirizzo",
        "descrizione": "Definisci le etichette usate per distinguere residenza, domicilio e altri indirizzi.",
    },
    "telefono": {
        "model": LabelTelefono,
        "field_name": "label_telefono",
        "titolo_nuovo": "Nuova etichetta telefono",
        "titolo_modifica": "Modifica etichetta telefono",
        "titolo_elimina": "Elimina etichetta telefono",
        "descrizione": "Definisci le etichette usate per distinguere cellulare, casa, lavoro o emergenza.",
    },
    "email": {
        "model": LabelEmail,
        "field_name": "label_email",
        "titolo_nuovo": "Nuova etichetta email",
        "titolo_modifica": "Modifica etichetta email",
        "titolo_elimina": "Elimina etichetta email",
        "descrizione": "Definisci le etichette usate per distinguere email principale, personale, lavoro o PEC.",
    },
}


def _contact_label_config(kind):
    config = CONTACT_LABEL_CONFIG.get(kind)
    if not config:
        raise Http404("Tipo etichetta non valido.")
    return config


def crea_label_contatto(request, kind):
    popup = is_popup_request(request)
    config = _contact_label_config(kind)
    LabelForm = modelform_factory(config["model"], fields=["nome", "ordine", "attiva", "note"])

    if request.method == "POST":
        form = LabelForm(request.POST)
        if form.is_valid():
            obj = form.save()
            if popup:
                return popup_select_response(
                    request,
                    field_name=request.GET.get("target_input_name") or request.POST.get("target_input_name") or config["field_name"],
                    object_id=obj.pk,
                    object_label=str(obj),
                )
            messages.success(request, "Etichetta creata correttamente.")
            return redirect("home")
    else:
        form = LabelForm()

    form.fields["nome"].widget.attrs.setdefault("placeholder", "Es. Principale, Casa, Lavoro...")
    form.fields["ordine"].widget.attrs.setdefault("min", "1")
    form.fields["note"].widget.attrs.update({"rows": "4", "placeholder": "Nota opzionale..."})

    return render(
        request,
        "anagrafica/configurazioni/label_contatto_popup_form.html"
        if popup
        else "anagrafica/configurazioni/label_contatto_form.html",
        {
            "form": form,
            "titolo": config["titolo_nuovo"],
            "descrizione": config["descrizione"],
            "popup": popup,
            "kind": kind,
        },
    )


def modifica_label_contatto(request, kind, pk):
    popup = is_popup_request(request)
    config = _contact_label_config(kind)
    obj = get_object_or_404(config["model"], pk=pk)
    LabelForm = modelform_factory(config["model"], fields=["nome", "ordine", "attiva", "note"])

    if request.method == "POST":
        form = LabelForm(request.POST, instance=obj)
        if form.is_valid():
            obj = form.save()
            if popup:
                return popup_select_response(
                    request,
                    field_name=request.GET.get("target_input_name") or request.POST.get("target_input_name") or config["field_name"],
                    object_id=obj.pk,
                    object_label=str(obj),
                )
            messages.success(request, "Etichetta modificata correttamente.")
            return redirect("home")
    else:
        form = LabelForm(instance=obj)

    form.fields["nome"].widget.attrs.setdefault("placeholder", "Es. Principale, Casa, Lavoro...")
    form.fields["ordine"].widget.attrs.setdefault("min", "1")
    form.fields["note"].widget.attrs.update({"rows": "4", "placeholder": "Nota opzionale..."})

    return render(
        request,
        "anagrafica/configurazioni/label_contatto_popup_form.html"
        if popup
        else "anagrafica/configurazioni/label_contatto_form.html",
        {
            "form": form,
            "titolo": config["titolo_modifica"],
            "descrizione": config["descrizione"],
            "popup": popup,
            "kind": kind,
        },
    )


def elimina_label_contatto(request, kind, pk):
    popup = is_popup_request(request)
    config = _contact_label_config(kind)
    obj = get_object_or_404(config["model"], pk=pk)
    object_id = obj.pk

    if request.method == "POST":
        obj.delete()
        if popup:
            return popup_delete_response(
                request,
                field_name=request.GET.get("target_input_name") or request.POST.get("target_input_name") or config["field_name"],
                object_id=object_id,
            )
        messages.success(request, "Etichetta eliminata correttamente.")
        return redirect("home")

    return render(
        request,
        "anagrafica/configurazioni/label_contatto_popup_delete.html"
        if popup
        else "anagrafica/configurazioni/label_contatto_delete.html",
        {
            "oggetto": obj,
            "titolo": config["titolo_elimina"],
            "descrizione": config["descrizione"],
            "popup": popup,
            "kind": kind,
        },
    )


def ajax_cerca_citta(request):
    citta_id = (request.GET.get("id") or "").strip()
    q = request.GET.get("q", "").strip()
    include_nazioni = (request.GET.get("include_nazioni") or "").strip() == "1"
    italia_nazionalita_id = None
    if include_nazioni:
        italia_nazionalita_id = (
            Nazione.objects
            .filter(attiva=True, nome__iexact="Italia")
            .exclude(nome_nazionalita="")
            .order_by("ordine", "id")
            .values_list("pk", flat=True)
            .first()
        )

    qs = (
        Citta.objects
        .filter(attiva=True)
        .select_related("provincia", "provincia__regione")
    )

    if citta_id:
        try:
            qs = qs.filter(pk=int(citta_id))
        except (TypeError, ValueError):
            return JsonResponse({"results": []})
    elif q:
        qs = (
            qs.filter(nome__icontains=q)
            .annotate(
                search_rank=Case(
                    When(nome__iexact=q, then=Value(0)),
                    When(nome__istartswith=q, then=Value(1)),
                    default=Value(2),
                    output_field=IntegerField(),
                )
            )
            .order_by("search_rank", "nome", "provincia__sigla")
        )
    else:
        qs = qs.order_by("nome", "provincia__sigla")

    qs = qs[:20]

    results = []
    for c in qs:
        caps = list(
            c.cap_list.filter(attivo=True)
            .order_by("codice")
            .values("id", "codice")
        )

        prov = getattr(c, "provincia", None)
        results.append({
            "type": "citta",
            "id": c.id,
            "nome": c.nome,
            "label": citta_choice_label(c),
            "codice_catastale": c.codice_catastale,
            "provincia_nome": getattr(prov, "nome", "") if prov is not None else "",
            "provincia_sigla": getattr(prov, "sigla", "") if prov is not None else "",
            "regione_nome": prov.regione.nome if prov and prov.regione else "",
            "nazionalita_id": italia_nazionalita_id or "",
            "nazionalita_label": "Italiana" if italia_nazionalita_id else "",
            "caps": caps,
        })

    if include_nazioni and not citta_id and q:
        nazioni_qs = (
            Nazione.objects
            .filter(attiva=True, nome__icontains=q)
            .annotate(
                search_rank=Case(
                    When(nome__iexact=q, then=Value(0)),
                    When(nome__istartswith=q, then=Value(1)),
                    default=Value(2),
                    output_field=IntegerField(),
                )
            )
            .order_by("search_rank", "nome")[:10]
        )
        for nazione in nazioni_qs:
            nazionalita = None
            if nazione.nome_nazionalita:
                nazionalita = (
                    Nazione.objects
                    .filter(attiva=True, nome_nazionalita__iexact=nazione.nome_nazionalita)
                    .exclude(nome_nazionalita="")
                    .order_by("nome_nazionalita", "ordine", "id")
                    .first()
                )
            has_same_name = Nazione.objects.filter(
                attiva=True,
                nome__iexact=nazione.nome,
            ).exclude(pk=nazione.pk).exists()
            label = str(nazione)
            if has_same_name and nazione.codice_belfiore:
                label = f"{nazione} ({nazione.codice_belfiore})"
            results.append({
                "type": "nazione",
                "id": nazione.id,
                "nome": str(nazione),
                "label": label,
                "codice_catastale": nazione.codice_belfiore,
                "nazionalita_id": nazionalita.pk if nazionalita else "",
                "nazionalita_label": nazionalita.label_nazionalita if nazionalita else "",
                "provincia_nome": "",
                "provincia_sigla": "",
                "regione_nome": "",
                "caps": [],
            })

    return JsonResponse({"results": results})


def ajax_indirizzi_duplicati(request):
    results = address_duplicate_candidates(
        via=request.GET.get("via", ""),
        numero_civico=request.GET.get("numero_civico", ""),
        cap=request.GET.get("cap", ""),
        citta_id=request.GET.get("citta") or request.GET.get("citta_id"),
        exclude_id=request.GET.get("exclude_id"),
    )
    return JsonResponse({"results": results})

#FINE VIEWS DEGLI INDIRIZZI


def anagrafica_document_missing_queryset(target, tipo_documento):
    documento_filter = Documento.objects.filter(tipo_documento=tipo_documento)

    if target == "familiari":
        return (
            Familiare.objects.annotate(
                has_required_document=Exists(documento_filter.filter(familiare=OuterRef("pk")))
            )
            .filter(has_required_document=False)
            .select_related(
                "relazione_familiare",
                "indirizzo__citta__provincia",
            )
            .prefetch_related("relazioni_studenti__studente")
            .order_by("cognome", "nome", "id")
        )

    if target == "studenti":
        return (
            Studente.objects.annotate(
                has_required_document=Exists(documento_filter.filter(studente=OuterRef("pk")))
            )
            .filter(has_required_document=False)
            .select_related(
                "indirizzo__citta__provincia",
            )
            .prefetch_related("relazioni_familiari__familiare")
            .order_by("cognome", "nome", "id")
        )

    if target == "famiglie":
        return [
            snapshot
            for snapshot in iter_logical_family_snapshots()
            if not family_document_queryset(snapshot).filter(tipo_documento=tipo_documento).exists()
        ]

    return []


def build_person_family_context(record):
    return logical_family_summary_for_person(record)["context"]


def _person_label(person):
    return " ".join(
        part for part in [getattr(person, "nome", ""), getattr(person, "cognome", "")] if part
    ).strip()


def _join_limited_person_labels(people, limit=2):
    labels = [_person_label(person) for person in people if person]
    labels = [label for label in labels if label]
    if not labels:
        return ""

    visible = labels[:limit]
    remaining = len(labels) - len(visible)
    suffix = f" +{remaining}" if remaining > 0 else ""
    return f"{', '.join(visible)}{suffix}"


def build_person_family_display(record, *, key_prefix, referenti=None):
    if not getattr(record, "pk", None):
        return {"label": "", "context": "", "referenti": "", "url": ""}

    family_name = (
        getattr(record, "cognome", "")
        or "logica"
    )
    label = f"Famiglia {family_name}"
    return {
        "label": label,
        "context": f"Famiglia: {family_name}",
        "referenti": _join_limited_person_labels(referenti or []),
        "url": reverse("modifica_famiglia_logica", kwargs={"key": f"{key_prefix}-{record.pk}"}),
    }


def build_anagrafica_query_rows(target, records):
    rows = []
    for record in records:
        if target == "familiari":
            details = []
            if record.relazione_familiare_id:
                details.append(str(record.relazione_familiare))
            if record.email:
                details.append(record.email)
            if record.formatted_telefono:
                details.append(record.formatted_telefono)
            rows.append(
                {
                    "label": str(record),
                    "context": build_person_family_context(record),
                    "details": " | ".join(details),
                    "url": reverse("modifica_familiare", kwargs={"pk": record.pk}),
                }
            )
        elif target == "studenti":
            details = []
            if record.codice_fiscale:
                details.append(f"CF: {record.codice_fiscale}")
            if record.data_nascita:
                details.append(f"Nato/a il {record.data_nascita:%d/%m/%Y}")
            rows.append(
                {
                    "label": str(record),
                    "context": build_person_family_context(record),
                    "details": " | ".join(details),
                    "url": reverse("modifica_studente", kwargs={"pk": record.pk}),
                }
            )
        elif target == "famiglie":
            details = []
            if record.indirizzo_principale:
                details.append(record.indirizzo_principale.label_full())
            rows.append(
                {
                    "label": record.cognome_famiglia,
                    "context": record.label_contesto_anagrafica(),
                    "details": " | ".join(details),
                    "url": logical_family_detail_url(record),
                }
            )
    return rows


def ricerche_anagrafica(request):
    query_key = (request.GET.get("query") or "").strip()
    target = (request.GET.get("target") or "").strip()
    tipo_documento_id = (request.GET.get("tipo_documento") or "").strip()
    tipi_documento = list(TipoDocumento.objects.filter(attivo=True).order_by("ordine", "tipo_documento"))
    base_url = reverse("ricerche_anagrafica")

    preset_cards = []
    for preset in ANAGRAFICA_DOCUMENT_QUERY_PRESETS:
        tipo_documento = find_tipo_documento_by_aliases(tipi_documento, preset["aliases"])
        url = ""
        if tipo_documento:
            url = (
                f"{base_url}?query=documenti_mancanti"
                f"&target={preset['target']}"
                f"&tipo_documento={tipo_documento.pk}"
            )
        preset_cards.append({**preset, "tipo_documento": tipo_documento, "url": url})

    selected_tipo_documento = None
    if tipo_documento_id.isdigit():
        selected_tipo_documento = next(
            (tipo for tipo in tipi_documento if tipo.pk == int(tipo_documento_id)),
            None,
        )

    rows = []
    result_title = ""
    result_message = ""
    if query_key == "documenti_mancanti":
        target_label = ANAGRAFICA_DOCUMENT_QUERY_TARGETS.get(target)
        if not target_label:
            result_message = "Seleziona un gruppo valido tra studenti, familiari e famiglie."
        elif not selected_tipo_documento:
            result_message = "Seleziona il tipo documento da verificare."
        else:
            records = anagrafica_document_missing_queryset(target, selected_tipo_documento)
            rows = build_anagrafica_query_rows(target, records)
            result_title = f"{target_label} senza {selected_tipo_documento.tipo_documento}"

    return render(
        request,
        "anagrafica/ricerche_anagrafica.html",
        {
            "query_key": query_key,
            "target": target,
            "tipo_documento_id": tipo_documento_id,
            "tipi_documento": tipi_documento,
            "target_choices": ANAGRAFICA_DOCUMENT_QUERY_TARGETS.items(),
            "preset_cards": preset_cards,
            "rows": rows,
            "result_title": result_title,
            "result_message": result_message,
        },
    )


#INIZIO VIEWS DELLE FAMIGLIE
def lista_famiglie(request):
    q = request.GET.get("q", "").strip()

    famiglie = list(iter_logical_family_snapshots())
    if q:
        famiglie = [
            famiglia
            for famiglia in famiglie
            if logical_family_matches(famiglia, q)
        ]

    evidenzia_id = request.GET.get("highlight")

    return render(
        request,
        "anagrafica/famiglie/famiglia_list.html",
        {
            "famiglie": famiglie,
            "evidenzia_id": evidenzia_id,
            "q": q,
        },
    )


def crea_famiglia(request):
    popup = is_popup_request(request)
    message = (
        "La creazione di famiglie come entita autonoma e stata disattivata: "
        "collega direttamente studenti, genitori e tutori dalle rispettive schede."
    )

    if popup:
        return popup_response(request, message)

    messages.info(request, message)
    return redirect("lista_famiglie")


def modifica_famiglia_logica(request, key):
    logical_snapshot = resolve_logical_family_snapshot(key)
    if logical_snapshot is None:
        raise Http404("Famiglia non trovata.")
    return _render_famiglia_logica(request, logical_snapshot)


def _render_famiglia_logica(request, logical_snapshot):
    allowed_inline_targets = {"familiari", "studenti", "documenti"}
    famiglia = logical_snapshot
    redirect_key = logical_snapshot.logical_key
    edit_scope = "full" if request.GET.get("edit") == "1" else "view"
    inline_target = "studenti"
    active_inline_tab = "studenti"
    prefer_initial_active_tab = False
    familiari_formset = None
    studenti_formset = None

    if request.method == "POST" and request.POST.get("_note_popup") == "1":
        messages.info(
            request,
            "Le note della famiglia ora sono ricavate dalle note di studenti e familiari collegati.",
        )
        return redirect(build_famiglia_logica_redirect_url(redirect_key, "studenti"))

    if request.method == "POST":
        active_inline_tab = resolve_active_inline_tab(request, allowed_inline_targets, "studenti")
        prefer_initial_active_tab = should_prefer_initial_famiglia_tab(request, allowed_inline_targets)
        edit_scope, inline_target = resolve_inline_target(
            request,
            allowed_inline_targets,
        )
        form = build_famiglia_logica_form(logical_snapshot)
        familiari_formset = (
            build_familiari_formset(data=request.POST, instance=logical_snapshot, prefix="familiari", logical=True)
            if inline_target == "familiari"
            else None
        )
        studenti_formset = (
            build_studenti_formset(data=request.POST, instance=logical_snapshot, prefix="studenti", logical=True)
            if inline_target == "studenti"
            else None
        )

        form_is_valid = True
        familiari_is_valid = familiari_formset.is_valid() if inline_target == "familiari" else True
        studenti_is_valid = studenti_formset.is_valid() if inline_target == "studenti" else True
        documenti_is_valid = True

        if form_is_valid and familiari_is_valid and studenti_is_valid and documenti_is_valid:
            try:
                with transaction.atomic():
                    if inline_target == "familiari":
                        familiari = familiari_formset.save()
                        for familiare in getattr(familiari_formset, "new_objects", []):
                            set_familiare_studenti(familiare, logical_snapshot.studenti)
                        if familiari:
                            logical_snapshot = refresh_logical_family_snapshot(logical_snapshot)
                            redirect_key = logical_snapshot.logical_key
                    if inline_target == "studenti":
                        studenti = studenti_formset.save()
                        for studente in getattr(studenti_formset, "new_objects", []):
                            set_studente_familiari(studente, logical_snapshot.familiari)
                        if studenti:
                            logical_snapshot = refresh_logical_family_snapshot(logical_snapshot)
                            redirect_key = logical_snapshot.logical_key
                    if inline_target == "documenti":
                        messages.info(
                            request,
                            "I documenti vanno gestiti dalla scheda del singolo studente o familiare.",
                        )
            except DOCUMENT_STORAGE_ERROR_TYPES as exc:
                messages.error(request, build_document_storage_error_message(exc))
            else:
                if "_continue" in request.POST:
                    messages.success(request, "Modifiche salvate correttamente.")
                    return redirect(build_famiglia_logica_redirect_url(redirect_key, active_inline_tab))

                if "_addanother" in request.POST:
                    messages.success(request, "Modifiche salvate correttamente.")
                    return redirect(build_famiglia_logica_redirect_url(redirect_key, active_inline_tab))

                messages.success(request, "Modifiche salvate correttamente.")
                return redirect(build_famiglia_logica_redirect_url(redirect_key, active_inline_tab))

        if familiari_formset is None:
            familiari_formset = build_familiari_formset(instance=logical_snapshot, prefix="familiari", logical=True)
        if studenti_formset is None:
            studenti_formset = build_studenti_formset(instance=logical_snapshot, prefix="studenti", logical=True)
    else:
        active_inline_tab = resolve_active_inline_tab(request, allowed_inline_targets, "studenti")
        prefer_initial_active_tab = should_prefer_initial_famiglia_tab(request, allowed_inline_targets)
        form = build_famiglia_logica_form(logical_snapshot)
        familiari_formset = build_familiari_formset(instance=logical_snapshot, prefix="familiari", logical=True)
        studenti_formset = build_studenti_formset(instance=logical_snapshot, prefix="studenti", logical=True)

    today = timezone.localdate()

    documenti_familiari = list(
        Documento.objects
        .filter(familiare_id__in=logical_snapshot.familiare_ids)
        .select_related("familiare", "familiare__persona", "tipo_documento")
        .order_by("familiare__persona__cognome", "familiare__persona__nome", "-data_caricamento", "-id")
    )

    documenti_studenti = list(
        Documento.objects
        .filter(studente_id__in=logical_snapshot.student_ids)
        .select_related("studente", "tipo_documento")
        .order_by("studente__cognome", "studente__nome", "-data_caricamento", "-id")
    )
    count_documenti_familiari = len(documenti_familiari)
    count_documenti_studenti = len(documenti_studenti)
    documenti_logici_qs = family_document_queryset(logical_snapshot)
    famiglia_documenti_counts = documenti_logici_qs.aggregate(
        totale=Count("id"),
        in_scadenza=Count(
            "id",
            filter=Q(
                scadenza__isnull=False,
                scadenza__gte=today,
                scadenza__lte=today + timedelta(days=30),
            ),
        ),
        scaduti=Count(
            "id",
            filter=Q(
                scadenza__isnull=False,
                scadenza__lt=today,
            ),
        ),
    )
    count_documenti_totali = (
        famiglia_documenti_counts["totale"] or 0
    )
    decorate_studenti_formset_current_enrollment_labels(studenti_formset, today)

    ctx = {
        "form": form,
        "famiglia": famiglia,
        "famiglia_logical_key": logical_snapshot.logical_key,
        "familiari_formset": familiari_formset,
        "studenti_formset": studenti_formset,
        "count_familiari": len(logical_snapshot.familiari),
        "count_studenti": len(logical_snapshot.studenti),
        "count_documenti": count_documenti_totali,
        "count_documenti_in_scadenza": famiglia_documenti_counts["in_scadenza"] or 0,
        "count_documenti_scaduti": famiglia_documenti_counts["scaduti"] or 0,
        "documenti_familiari": documenti_familiari,
        "documenti_studenti": documenti_studenti,
        "count_documenti_familiari": count_documenti_familiari,
        "count_documenti_studenti": count_documenti_studenti,
        "famiglia_note_entries": logical_snapshot.note_entries,
        "famiglia_activity_entries": famiglia_activity_entries(logical_snapshot),
        "famiglia_rette_summary": build_famiglia_rette_mensili_summary(logical_snapshot, today),
        "edit_scope": edit_scope,
        "inline_target": inline_target,
        "active_inline_tab": active_inline_tab,
        "prefer_initial_active_tab": prefer_initial_active_tab,
        "has_form_errors": bool(form.errors or familiari_formset.total_error_count() or studenti_formset.total_error_count()),
    }
    ctx.update(
        famiglia_inline_head(
            active_inline_tab=active_inline_tab,
            count_familiari=ctx["count_familiari"],
            count_studenti=ctx["count_studenti"],
            count_documenti=ctx["count_documenti"],
            related_famiglia_studenti_doc_count=count_documenti_familiari + count_documenti_studenti,
        )
    )
    return render(request, "anagrafica/famiglie/famiglia_form.html", ctx)


def stampa_famiglia_logica(request, key):
    logical_snapshot = resolve_logical_family_snapshot(key)
    if logical_snapshot is None:
        raise Http404("Famiglia non trovata.")
    return render_famiglia_print(request, logical_snapshot)


def render_famiglia_print(request, logical_snapshot):
    return render(
        request,
        "anagrafica/famiglie/famiglia_print.html",
        {
            "famiglia": logical_snapshot,
            "familiari": logical_snapshot.familiari,
            "studenti": logical_snapshot.studenti,
            "print_date": timezone.localdate(),
        },
    )

#FINE VIEWS DELLE FAMIGLIE

#INIZIO VIEWS PER I FAMILIARI

#Views per le relazioni familiari
def crea_relazione_familiare(request):
    popup = is_popup_request(request)

    RelazioneFamiliareForm = modelform_factory(
        RelazioneFamiliare,
        fields=["relazione", "ordine", "note"],
    )

    if request.method == "POST":
        form = RelazioneFamiliareForm(request.POST)
        if form.is_valid():
            obj = form.save()

            if popup:
                return popup_select_response(
                    request,
                    field_name="relazione_familiare",
                    object_id=obj.pk,
                    object_label=str(obj),
                )

            messages.success(request, "Relazione familiare creata correttamente.")
            return redirect("lista_famiglie")
    else:
        form = RelazioneFamiliareForm()

    form.fields["relazione"].widget.attrs.setdefault("placeholder", "Es. Padre, Madre, Tutore...")
    form.fields["ordine"].widget.attrs.setdefault("min", "1")
    form.fields["note"].widget.attrs.update(
        {
            "placeholder": "Aggiungi una nota (opzionale)...",
            "rows": "6",
            "data-rich-notes": "1",
        }
    )

    return render(
        request,
        "anagrafica/configurazioni/relazione_familiare_popup_form.html" if popup else "anagrafica/configurazioni/relazione_familiare_form.html",
        {
            "form": form,
            "titolo": "Nuova parentela",
            "popup": popup,
        },
    )


def modifica_relazione_familiare(request, pk):
    relazione = get_object_or_404(RelazioneFamiliare, pk=pk)
    popup = is_popup_request(request)

    RelazioneFamiliareForm = modelform_factory(
        RelazioneFamiliare,
        fields=["relazione", "ordine", "note"],
    )

    if request.method == "POST":
        form = RelazioneFamiliareForm(request.POST, instance=relazione)
        if form.is_valid():
            obj = form.save()

            if popup:
                return popup_select_response(
                    request,
                    field_name="relazione_familiare",
                    object_id=obj.pk,
                    object_label=str(obj),
                )

            messages.success(request, "Relazione familiare modificata correttamente.")
            return redirect("lista_famiglie")
    else:
        form = RelazioneFamiliareForm(instance=relazione)

    form.fields["relazione"].widget.attrs.setdefault("placeholder", "Es. Padre, Madre, Tutore...")
    form.fields["ordine"].widget.attrs.setdefault("min", "1")
    form.fields["note"].widget.attrs.update(
        {
            "placeholder": "Aggiungi una nota (opzionale)...",
            "rows": "6",
            "data-rich-notes": "1",
        }
    )

    return render(
        request,
        "anagrafica/configurazioni/relazione_familiare_popup_form.html" if popup else "anagrafica/configurazioni/relazione_familiare_form.html",
        {
            "form": form,
            "titolo": "Modifica parentela",
            "popup": popup,
        },
    )


def elimina_relazione_familiare(request, pk):
    relazione = get_object_or_404(RelazioneFamiliare, pk=pk)
    popup = is_popup_request(request)

    object_id = relazione.pk

    if request.method == "POST":
        relazione.delete()

        if popup:
            return popup_delete_response(
                request,
                field_name="relazione_familiare",
                object_id=object_id,
            )

        messages.success(request, "Relazione familiare eliminata correttamente.")
        return redirect("lista_famiglie")

    return render(
        request,
        "anagrafica/configurazioni/relazione_familiare_popup_delete.html" if popup else "anagrafica/configurazioni/relazione_familiare_delete.html",
        {
            "oggetto": relazione,
            "titolo": "Elimina parentela",
            "popup": popup,
        },
    )


#Views per i familiari veri e propri
def lista_familiari(request):
    q = request.GET.get("q", "").strip()

    familiari = (
        Familiare.objects
        .select_related(
            "relazione_familiare",
            "indirizzo",
            "indirizzo__citta",
            "luogo_nascita",
            "luogo_nascita__provincia",
            "nazione_nascita",
            "nazionalita",
        )
        .prefetch_related(active_relative_student_prefetch())
        .order_by("cognome", "nome")
    )

    if q:
        familiari = familiari.filter(
            Q(nome__icontains=q) |
            Q(cognome__icontains=q) |
            Q(email__icontains=q) |
            Q(telefono__icontains=q) |
            Q(codice_fiscale__icontains=q) |
            Q(luogo_nascita__nome__icontains=q) |
            Q(luogo_nascita__provincia__sigla__icontains=q) |
            Q(nazione_nascita__nome__icontains=q) |
            Q(luogo_nascita_custom__icontains=q) |
            Q(relazioni_studenti__attivo=True, relazioni_studenti__studente__nome__icontains=q) |
            Q(relazioni_studenti__attivo=True, relazioni_studenti__studente__cognome__icontains=q) |
            Q(relazioni_studenti__attivo=True, relazioni_studenti__studente__codice_fiscale__icontains=q) |
            Q(relazione_familiare__relazione__icontains=q)
        ).distinct()

    evidenzia_id = request.GET.get("highlight")
    familiari = list(familiari)
    decorate_familiari_direct_relation_labels(familiari)

    return render(
        request,
        "anagrafica/familiari/familiari_lista.html",
        {
            "familiari": familiari,
            "q": q,
            "evidenzia_id": evidenzia_id,
        },
    )


def get_familiare_profilo_lavorativo(familiare):
    if not familiare or not getattr(familiare, "pk", None):
        return None
    if not getattr(familiare, "persona_id", None):
        return None
    return Dipendente.objects.filter(persona_collegata=familiare.persona).first()


def familiare_to_dipendente_payload(familiare):
    return {
        "stato": StatoDipendente.ATTIVO if familiare.attivo else StatoDipendente.SOSPESO,
    }


def sync_familiare_profilo_lavorativo(familiare, cleaned_data):
    if "profilo_dipendente_attivo" not in cleaned_data and "profilo_educatore_attivo" not in cleaned_data:
        return get_familiare_profilo_lavorativo(familiare), False

    profilo = get_familiare_profilo_lavorativo(familiare)
    abilita_dipendente = bool(cleaned_data.get("profilo_dipendente_attivo"))
    abilita_educatore = bool(cleaned_data.get("profilo_educatore_attivo"))
    if abilita_dipendente and abilita_educatore:
        abilita_dipendente = False

    if not abilita_dipendente and not abilita_educatore:
        if not profilo:
            return None, False

        has_relazioni = profilo.contratti.exists() or profilo.buste_paga.exists() or profilo.documenti.exists()
        if has_relazioni:
            return profilo, True

        profilo.delete()
        return None, False

    if abilita_educatore:
        ruolo = RuoloAnagraficoDipendente.EDUCATORE
    else:
        ruolo = RuoloAnagraficoDipendente.DIPENDENTE

    payload = familiare_to_dipendente_payload(familiare)
    if not profilo and getattr(familiare, "persona_id", None):
        profilo = (
            Dipendente.objects.filter(persona_collegata=familiare.persona)
            .first()
        )

    if not profilo:
        profilo = Dipendente(persona_collegata=familiare.persona)

    for field_name, value in payload.items():
        setattr(profilo, field_name, value)
    profilo.ruolo_aziendale = ruolo
    profilo.persona_collegata = familiare.persona
    classe_id, gruppo_id = split_classe_principale_reference(cleaned_data.get("classe_principale_educatore"))
    profilo.classe_principale_id = classe_id if abilita_educatore else None
    profilo.gruppo_classe_principale_id = gruppo_id if abilita_educatore else None
    profilo.mansione = (cleaned_data.get("profilo_mansione") or "").strip() if abilita_dipendente else ""
    profilo.iban = (cleaned_data.get("profilo_iban") or "").replace(" ", "").upper().strip()
    profilo.stato = cleaned_data.get("profilo_stato") or profilo.stato or StatoDipendente.ATTIVO
    profilo.save()
    return profilo, False


def studenti_classe_principale_educatore(profilo):
    if not profilo or not profilo.is_educatore:
        return []

    if not profilo.classe_principale_id and not getattr(profilo, "gruppo_classe_principale_id", None):
        return []

    anno = resolve_default_anno_scolastico()
    iscrizioni = (
        Iscrizione.objects.select_related("studente")
        .filter(attiva=True)
        .order_by("studente__cognome", "studente__nome", "-id")
    )
    if getattr(profilo, "gruppo_classe_principale_id", None):
        iscrizioni = iscrizioni.filter(gruppo_classe_id=profilo.gruppo_classe_principale_id)
    else:
        iscrizioni = iscrizioni.filter(classe_id=profilo.classe_principale_id)
    if anno:
        iscrizioni = iscrizioni.filter(anno_scolastico=anno)

    studenti = []
    seen = set()
    for iscrizione in iscrizioni[:80]:
        studente = iscrizione.studente
        if studente.pk in seen:
            continue
        seen.add(studente.pk)
        studenti.append(studente)
    return studenti


def build_familiare_lavoro_context(familiare):
    profilo = get_familiare_profilo_lavorativo(familiare)
    if not profilo:
        return {
            "profilo_lavorativo": None,
            "profilo_contratto_corrente": None,
            "profilo_contratti": [],
            "profilo_buste_paga": [],
            "profilo_documenti": [],
            "profilo_studenti_classe": [],
        }

    contratto_corrente = profilo.contratto_corrente

    return {
        "profilo_lavorativo": profilo,
        "profilo_contratto_corrente": contratto_corrente,
        "profilo_contratti": profilo.contratti.select_related("tipo_contratto").order_by("-data_inizio", "-id")[:8],
        "profilo_buste_paga": (
            profilo.buste_paga.select_related("contratto", "contratto__tipo_contratto")
            .prefetch_related("documenti")
            .order_by("-anno", "-mese", "-id")[:8]
        ),
        "profilo_documenti": profilo.documenti.order_by("-data_documento", "-id")[:6],
        "profilo_studenti_classe": studenti_classe_principale_educatore(profilo),
    }


def crea_familiare(request):
    allowed_inline_targets = {"studenti", "parenti", "documenti"}
    edit_scope = "full"
    inline_target = "studenti"
    active_inline_tab = "studenti"
    studenti_formset = None
    parenti_formset = None
    documenti_formset = None
    contact_formsets = None
    initial = {}
    profilo_lavorativo_iniziale = (request.GET.get("profilo_lavorativo") or "").strip().lower()
    create_profile_context = {}
    if profilo_lavorativo_iniziale in {"dipendente", "educatore"}:
        initial["profilo_dipendente_attivo"] = profilo_lavorativo_iniziale == "dipendente"
        initial["profilo_educatore_attivo"] = profilo_lavorativo_iniziale == "educatore"
        if profilo_lavorativo_iniziale == "educatore":
            create_profile_context = {
                "create_profile_scope": "educatori",
                "create_profile_title": f"Nuovo {get_educator_terminology()['selected_singular_lower']}",
                "create_profile_status": get_educator_terminology()["selected_singular"],
                "create_profile_list_label": get_educator_terminology()["selected_plural"],
                "create_profile_list_url": "lista_educatori",
                "create_profile_save_label": f"Salva {get_educator_terminology()['selected_singular_lower']}",
                "create_profile_cancel_url": "lista_educatori",
            }
        else:
            create_profile_context = {
                "create_profile_scope": "dipendenti",
                "create_profile_title": "Nuovo dipendente",
                "create_profile_status": "Dipendente",
                "create_profile_list_label": "Dipendenti",
                "create_profile_list_url": "lista_dipendenti",
                "create_profile_save_label": "Salva dipendente",
                "create_profile_cancel_url": "lista_dipendenti",
            }
    studente_collegato_id = (request.GET.get("studente") or "").strip()
    if studente_collegato_id.isdigit():
        studente_collegato = (
            Studente.objects.filter(pk=int(studente_collegato_id), attivo=True).first()
        )
        if studente_collegato:
            initial["studenti_collegati"] = [studente_collegato.pk]

    if request.method == "POST":
        active_inline_tab = resolve_active_inline_tab(request, allowed_inline_targets, "studenti")
        edit_scope, inline_target = resolve_inline_target(
            request,
            allowed_inline_targets,
        )
        form = FamiliareForm(
            request.POST,
            enable_work_profile_fields=True,
            enable_direct_relations_field=True,
        )
        contact_formsets = build_anagrafica_contact_formsets(data=request.POST)
        studenti_formset = (
            build_studenti_formset(data=request.POST, prefix="studenti")
            if inline_target in (None, "studenti")
            else None
        )
        parenti_formset = (
            build_familiari_formset(data=request.POST, prefix="parenti")
            if inline_target in (None, "parenti")
            else None
        )
        documenti_formset = (
            DocumentoFamiliareFormSet(
                request.POST,
                request.FILES,
                prefix="documenti",
            )
            if inline_target in (None, "documenti")
            else None
        )

        form_is_valid = form.is_valid()
        studenti_is_valid = studenti_formset.is_valid() if inline_target in (None, "studenti") else True
        parenti_is_valid = parenti_formset.is_valid() if inline_target in (None, "parenti") else True
        documenti_is_valid = documenti_formset.is_valid() if inline_target in (None, "documenti") else True
        contatti_is_valid = anagrafica_contact_formsets_are_valid(contact_formsets)

        if form_is_valid and studenti_is_valid and parenti_is_valid and documenti_is_valid and contatti_is_valid:
            try:
                with transaction.atomic():
                    familiare = form.save()
                    _, profilo_rimosso_bloccato = sync_familiare_profilo_lavorativo(familiare, form.cleaned_data)
                    save_anagrafica_contact_formsets(familiare, contact_formsets)

                    if inline_target in (None, "studenti"):
                        studenti_creati = studenti_formset.save()
                        if studenti_creati:
                            set_familiare_studenti(familiare, studenti_creati)

                    if inline_target in (None, "parenti"):
                        parenti_formset.save()

                    if inline_target in (None, "documenti"):
                        documenti_formset.instance = familiare
                        documenti_formset.save()
            except DOCUMENT_STORAGE_ERROR_TYPES as exc:
                messages.error(request, build_document_storage_error_message(exc))
            else:
                created_label = create_profile_context.get("create_profile_status") or "Familiare"
                if profilo_rimosso_bloccato:
                    messages.warning(
                        request,
                        "Il profilo lavorativo e' rimasto attivo perche' contiene contratti, buste paga o documenti collegati.",
                    )
                if "_continue" in request.POST:
                    messages.success(request, f"{created_label} creato correttamente.")
                    if create_profile_context.get("create_profile_list_url"):
                        profilo_creato = get_familiare_profilo_lavorativo(familiare)
                        highlight_id = profilo_creato.pk if profilo_creato else familiare.pk
                        return redirect(
                            f"{reverse(create_profile_context['create_profile_list_url'])}?highlight={highlight_id}"
                        )
                    return redirect(f"{reverse('lista_familiari')}?highlight={familiare.pk}")

                if "_addanother" in request.POST:
                    messages.success(request, f"{created_label} creato correttamente. Puoi inserirne un altro.")
                    if profilo_lavorativo_iniziale in {"dipendente", "educatore"}:
                        return redirect(f"{reverse('crea_familiare')}?profilo_lavorativo={profilo_lavorativo_iniziale}")
                    return redirect("crea_familiare")

                messages.success(request, f"{created_label} creato correttamente. Ora puoi continuare a inserire i dati.")
                default_target = "studenti"
                target = active_inline_tab if active_inline_tab in allowed_inline_targets else default_target
                return redirect(build_familiare_redirect_url(familiare.pk, target, default_target))

        if studenti_formset is None:
            studenti_formset = build_studenti_formset(prefix="studenti")
        if parenti_formset is None:
            parenti_formset = build_familiari_formset(prefix="parenti")
        if documenti_formset is None:
            documenti_formset = DocumentoFamiliareFormSet(prefix="documenti")
    else:
        active_inline_tab = resolve_active_inline_tab(request, allowed_inline_targets, "studenti")
        form = FamiliareForm(
            initial=initial,
            enable_work_profile_fields=True,
            enable_direct_relations_field=True,
        )
        contact_formsets = build_anagrafica_contact_formsets()
        studenti_formset = build_studenti_formset(prefix="studenti")
        parenti_formset = build_familiari_formset(prefix="parenti")
        documenti_formset = DocumentoFamiliareFormSet(prefix="documenti")

    today = timezone.localdate()
    decorate_studenti_formset_current_enrollment_labels(studenti_formset, today)
    has_form_errors = bool(
        form.errors
        or studenti_formset.total_error_count()
        or parenti_formset.total_error_count()
        or documenti_formset.total_error_count()
        or anagrafica_contact_formsets_have_errors(contact_formsets)
    )

    return render(
        request,
        "anagrafica/familiari/familiari_form.html",
        {
            "form": form,
            "documenti_formset": documenti_formset,
            "studenti_formset": studenti_formset,
            "parenti_formset": parenti_formset,
            **contact_formsets,
            "studenti_famiglia": None,
            "count_studenti": 0,
            "count_parenti": 0,
            "studenti_collegati_diretti": [],
            "parenti_collegati_diretti": [],
            "familiare_indirizzi_correlati": [],
            "studente_inline_defaults": None,
            "count_documenti": 0,
            "count_documenti_in_scadenza": 0,
            "count_documenti_scaduti": 0,
            "scambio_retta_inline_context": {"enabled": False, "sections": []},
            "scambio_retta_return_to": "",
            "edit_scope": edit_scope,
            "inline_target": active_inline_tab,
            "has_form_errors": has_form_errors,
            **create_profile_context,
            **build_familiare_lavoro_context(None),
            "familiare_inline_tabs": [
                {
                    "tab_id": "tab-studenti",
                    "label": get_student_terminology()["selected_plural"],
                    "base_label": get_student_terminology()["selected_plural"],
                    "count": 0,
                    "is_active": active_inline_tab == "studenti",
                },
                {
                    "tab_id": "tab-parenti",
                    "label": "Familiari",
                    "base_label": "Familiari",
                    "count": 0,
                    "is_active": active_inline_tab == "parenti",
                },
                {
                    "tab_id": "tab-documenti",
                    "label": "Documenti",
                    "base_label": "Documenti",
                    "count": 0,
                    "is_active": active_inline_tab == "documenti",
                },
            ],
            "familiare_inline_edit_label": "Modifica",
        },
    )


def modifica_familiare(request, pk):
    familiare = get_object_or_404(
        Familiare.objects.select_related(
            "relazione_familiare",
            "indirizzo",
            "luogo_nascita",
            "luogo_nascita__provincia",
            "nazione_nascita",
            "nazionalita",
        )
        .prefetch_related(active_relative_student_prefetch()),
        pk=pk,
    )
    today = timezone.localdate()
    edit_scope = "full" if request.GET.get("edit") == "1" else "view"

    studenti_formset = None
    parenti_formset = None
    studenti_diretti_form = None
    contact_formsets = None

    relazioni_studenti_prefetch = getattr(familiare, "relazioni_studenti_attive_prefetch", None)
    if relazioni_studenti_prefetch is None:
        studenti_collegati_diretti = list(
            familiare.relazioni_studenti.filter(attivo=True)
            .select_related(
                "studente",
                "studente__luogo_nascita",
                "studente__luogo_nascita__provincia",
            )
            .order_by("studente__cognome", "studente__nome", "studente_id")
        )
    else:
        studenti_collegati_diretti = list(relazioni_studenti_prefetch)
    decorate_studenti_current_enrollment_labels(
        [relazione.studente for relazione in studenti_collegati_diretti if getattr(relazione, "studente", None)],
        today,
    )
    parenti_collegati_diretti = direct_relative_peers_for_student_relations(familiare, studenti_collegati_diretti)
    studenti_formset_queryset = ordered_queryset_from_ids(
        Studente,
        [relazione.studente_id for relazione in studenti_collegati_diretti],
        select_related_fields=("luogo_nascita", "luogo_nascita__provincia"),
    )
    parenti_formset_queryset = ordered_queryset_from_ids(
        Familiare,
        [parente.pk for parente in parenti_collegati_diretti],
        select_related_fields=("relazione_familiare", "persona", "persona__indirizzo", "persona__indirizzo__citta"),
    )

    if request.method == "POST" and request.POST.get("_note_popup") == "1":
        note_active_tab = (request.POST.get("_note_active_tab") or "studenti").strip()
        if note_active_tab.startswith("tab-"):
            note_active_tab = note_active_tab[4:]
        allowed_note_tabs = ["studenti", "parenti", "documenti"]
        default_note_tab = "studenti"
        if note_active_tab not in allowed_note_tabs:
            note_active_tab = default_note_tab

        nuova_nota = request.POST.get("note", "")
        if familiare.note != nuova_nota:
            familiare.note = nuova_nota
            familiare.save()
            messages.success(request, "Note aggiornate correttamente.")
        else:
            messages.info(request, "Nessuna modifica alle note.")
        return redirect(build_familiare_redirect_url(familiare.pk, note_active_tab, default_note_tab))

    def famiglia_for_studenti_inline(current_edit_scope=None):
        return None

    if request.method == "POST":
        edit_scope = (request.POST.get("_edit_scope") or "full").strip()
        if edit_scope == "view":
            return redirect(request.get_full_path())

        inline_editing = edit_scope == "inline"
        inline_target = (request.POST.get("_inline_target") or "").strip()
        card_inline_submit = (request.POST.get("_card_inline_submit") or "").strip()
        famiglia_for_studenti = famiglia_for_studenti_inline(edit_scope)
        form = (
            FamiliareForm(
                instance=familiare,
                enable_work_profile_fields=True,
                enable_direct_relations_field=True,
            )
            if inline_editing
            else FamiliareForm(
                request.POST,
                instance=familiare,
                enable_work_profile_fields=True,
                enable_direct_relations_field=True,
            )
        )
        contact_formsets = build_anagrafica_contact_formsets(
            data=request.POST if not inline_editing else None,
            instance=familiare,
        )
        if inline_editing and inline_target == "documenti":
            documenti_formset = DocumentoFamiliareFormSet(
                request.POST,
                request.FILES,
                instance=familiare,
                prefix="documenti",
            )
        else:
            documenti_formset = DocumentoFamiliareFormSet(instance=familiare, prefix="documenti")
        studenti_formset = build_studenti_formset(
            data=request.POST if inline_editing and inline_target == "studenti" and card_inline_submit == "studenti" else None,
            prefix="studenti",
            queryset=studenti_formset_queryset,
        )
        parenti_formset = build_familiari_formset(
            data=request.POST if inline_editing and inline_target == "parenti" else None,
            prefix="parenti",
            queryset=parenti_formset_queryset,
        )
        studenti_diretti_form = FamiliareDirectStudentiForm(
            request.POST if inline_editing and inline_target == "studenti" else None,
            familiare=familiare,
        )
        studenti_ok = True
        if inline_editing and inline_target == "studenti":
            if card_inline_submit == "studenti" and studenti_formset is not None:
                studenti_ok = studenti_formset.is_valid()
            else:
                studenti_ok = studenti_diretti_form.is_valid()
        parenti_ok = parenti_formset.is_valid() if inline_editing and inline_target == "parenti" and parenti_formset is not None else True
        form_ok = True if inline_editing else form.is_valid()
        documenti_ok = documenti_formset.is_valid() if inline_editing and inline_target == "documenti" else True
        contatti_ok = True if inline_editing else anagrafica_contact_formsets_are_valid(contact_formsets)

        if form_ok and documenti_ok and studenti_ok and parenti_ok and contatti_ok:
            try:
                with transaction.atomic():
                    profilo_rimosso_bloccato = False
                    if not inline_editing:
                        familiare = form.save()
                        _, profilo_rimosso_bloccato = sync_familiare_profilo_lavorativo(familiare, form.cleaned_data)
                        save_anagrafica_contact_formsets(familiare, contact_formsets)
                    if inline_editing and inline_target == "documenti":
                        documenti_formset.save()
                    if inline_editing and inline_target == "studenti" and card_inline_submit == "studenti" and studenti_formset is not None:
                        studenti_formset.save()
                        for studente_salvato in getattr(studenti_formset, "new_objects", []):
                            ensure_direct_student_family_relation(studente_salvato, familiare)
                    if inline_editing and inline_target == "studenti" and card_inline_submit != "studenti":
                        studenti_diretti_form.save()
                    if inline_editing and inline_target == "parenti" and parenti_formset is not None:
                        parenti_formset.save()
                        studenti_base = [relazione.studente for relazione in studenti_collegati_diretti if getattr(relazione, "studente", None)]
                        for parente_salvato in getattr(parenti_formset, "new_objects", []):
                            for studente_base in studenti_base:
                                ensure_direct_student_family_relation(studente_base, parente_salvato)
            except DOCUMENT_STORAGE_ERROR_TYPES as exc:
                messages.error(request, build_document_storage_error_message(exc))
            else:
                if profilo_rimosso_bloccato:
                    messages.warning(
                        request,
                        "Il profilo lavorativo e' rimasto attivo perche' contiene contratti, buste paga o documenti collegati.",
                    )
                if "_continue" in request.POST:
                    messages.success(request, "Modifiche salvate correttamente.")
                    target = (request.POST.get("_inline_target") or "").strip()
                    allowed_targets = ["documenti"]
                    if studenti_formset is not None or studenti_diretti_form is not None:
                        allowed_targets.insert(0, "studenti")
                    if parenti_formset is not None:
                        insert_at = 1 if "studenti" in allowed_targets else 0
                        allowed_targets.insert(insert_at, "parenti")
                    default_target = "studenti" if "studenti" in allowed_targets else "documenti"
                    if target not in allowed_targets:
                        target = default_target
                    return redirect(build_familiare_redirect_url(familiare.pk, target, default_target))

                if "_addanother" in request.POST:
                    messages.success(request, "Modifiche salvate correttamente. Puoi inserire un nuovo familiare.")
                    return redirect("crea_familiare")

                messages.success(request, "Modifiche salvate correttamente.")
                target = (request.POST.get("_inline_target") or "").strip()
                allowed_targets = ["documenti"]
                if studenti_formset is not None or studenti_diretti_form is not None:
                    allowed_targets.insert(0, "studenti")
                if parenti_formset is not None:
                    insert_at = 1 if "studenti" in allowed_targets else 0
                    allowed_targets.insert(insert_at, "parenti")
                default_target = "studenti" if "studenti" in allowed_targets else "documenti"
                if target not in allowed_targets:
                    target = default_target
                return redirect(build_familiare_redirect_url(familiare.pk, target, default_target))
    else:
        famiglia_for_studenti = famiglia_for_studenti_inline(edit_scope)
        form = FamiliareForm(
            instance=familiare,
            enable_work_profile_fields=True,
            enable_direct_relations_field=True,
        )
        contact_formsets = build_anagrafica_contact_formsets(instance=familiare)
        studenti_diretti_form = FamiliareDirectStudentiForm(familiare=familiare)
        studenti_formset = build_studenti_formset(
            prefix="studenti",
            queryset=studenti_formset_queryset,
        )
        parenti_formset = build_familiari_formset(
            prefix="parenti",
            queryset=parenti_formset_queryset,
        )
        documenti_formset = DocumentoFamiliareFormSet(instance=familiare, prefix="documenti")

    usa_studenti_diretti = bool(studenti_collegati_diretti)
    usa_parenti_diretti = bool(parenti_collegati_diretti)
    count_studenti = len(studenti_collegati_diretti)
    count_parenti = len(parenti_collegati_diretti)
    studente_inline_defaults = None
    scambio_retta_inline_context = build_familiare_scambio_retta_inline_context(familiare, request.GET)
    scambio_retta_return_to = f"{request.get_full_path()}#scambio-retta-inline"
    allowed_inline_targets = ["documenti"]
    if studenti_formset is not None or usa_studenti_diretti or studenti_diretti_form is not None:
        allowed_inline_targets.insert(0, "studenti")
    if parenti_formset is not None or usa_parenti_diretti:
        insert_at = 1 if "studenti" in allowed_inline_targets else 0
        allowed_inline_targets.insert(insert_at, "parenti")
    default_inline_target = "studenti" if "studenti" in allowed_inline_targets else "documenti"
    inline_target = resolve_active_inline_tab(request, allowed_inline_targets, default_inline_target)
    familiare_inline_tabs = []
    familiare_inline_edit_label = "Modifica Documenti"
    if studenti_formset is not None or usa_studenti_diretti or studenti_diretti_form is not None:
        familiare_inline_tabs.append({
            "tab_id": "tab-studenti",
            "label": "Figli e Figlie",
            "base_label": "Figli e Figlie",
            "count": count_studenti,
            "is_active": inline_target == "studenti",
        })
        if inline_target == "studenti":
            familiare_inline_edit_label = "Modifica Figli e Figlie"
    if parenti_formset is not None or usa_parenti_diretti:
        familiare_inline_tabs.append({
            "tab_id": "tab-parenti",
            "label": "Parenti",
            "base_label": "Parenti",
            "count": count_parenti,
            "is_active": inline_target == "parenti",
        })
        if inline_target == "parenti":
            familiare_inline_edit_label = (
                "Modifica Parenti"
                if parenti_formset is not None
                else "Modifica dalla scheda"
            )
    familiare_inline_tabs.append({
        "tab_id": "tab-documenti",
        "label": "Documenti",
        "base_label": "Documenti",
        "count": familiare.documenti.count(),
        "is_active": inline_target == "documenti",
    })
    familiare_famiglia_logica = build_person_family_display(
        familiare,
        key_prefix="f",
        referenti=[familiare] if familiare.referente_principale else [],
    )
    decorate_studenti_formset_current_enrollment_labels(studenti_formset, today)
    familiare_audit_info = familiare_audit_labels(familiare)
    documenti_ids = list(familiare.documenti.values_list("pk", flat=True))
    familiare_indirizzi_correlati = build_familiare_address_suggestions(
        familiare,
        studenti_collegati_diretti,
        parenti_collegati_diretti,
    )
    return render(
        request,
        "anagrafica/familiari/familiari_form.html",
        {
            "form": form,
            "familiare": familiare,
            "documenti_formset": documenti_formset,
            "studenti_formset": studenti_formset,
            "studenti_diretti_form": studenti_diretti_form,
            "parenti_formset": parenti_formset,
            **contact_formsets,
            "studenti_famiglia": famiglia_for_studenti,
            "familiare_famiglia_logica": familiare_famiglia_logica,
            "count_studenti": count_studenti,
            "count_parenti": count_parenti,
            "studenti_collegati_diretti": studenti_collegati_diretti,
            "parenti_collegati_diretti": parenti_collegati_diretti,
            "familiare_indirizzi_correlati": familiare_indirizzi_correlati,
            "usa_studenti_diretti": usa_studenti_diretti,
            "usa_parenti_diretti": usa_parenti_diretti,
            "usa_studenti_diretti_cards": usa_studenti_diretti and studenti_formset is None,
            "usa_parenti_diretti_cards": usa_parenti_diretti and parenti_formset is None,
            "studente_inline_defaults": studente_inline_defaults,
            "count_documenti": familiare.documenti.count(),
            "count_documenti_in_scadenza": familiare.documenti.filter(
                scadenza__isnull=False,
                scadenza__gte=today,
                scadenza__lte=today + timedelta(days=30),
            ).count(),
            "count_documenti_scaduti": familiare.documenti.filter(
                scadenza__isnull=False,
                scadenza__lt=today,
            ).count(),
            "scambio_retta_inline_context": scambio_retta_inline_context,
            "scambio_retta_return_to": scambio_retta_return_to,
            "edit_scope": edit_scope,
            "inline_target": inline_target,
            "familiare_inline_tabs": familiare_inline_tabs,
            "familiare_inline_edit_label": familiare_inline_edit_label,
            "familiare_inline_can_edit": (
                (inline_target == "studenti" and (studenti_formset is not None or studenti_diretti_form is not None))
                or (inline_target == "parenti" and parenti_formset is not None)
                or inline_target == "documenti"
            ),
            "familiare_creazione_data": familiare_audit_info["created_data"],
            "familiare_creato_da_label": familiare_audit_info["created_label"],
            "familiare_ultima_modifica_data": familiare_audit_info["updated_data"],
            "familiare_aggiornato_da_label": familiare_audit_info["updated_label"],
            "familiare_activity_entries": familiare_activity_entries(familiare, documenti_ids=documenti_ids),
            "has_form_errors": bool(
                form.errors
                or documenti_formset.total_error_count()
                or (studenti_formset.total_error_count() if studenti_formset is not None else 0)
                or (parenti_formset.total_error_count() if parenti_formset is not None else 0)
                or anagrafica_contact_formsets_have_errors(contact_formsets)
            ),
            **build_familiare_lavoro_context(familiare),
        },
    )


def elimina_familiare(request, pk):
    familiare = get_object_or_404(Familiare, pk=pk)
    impact = get_record_documents_impact(familiare)
    popup = is_popup_request(request)

    if request.method == "POST":
        object_id = familiare.pk
        familiare.delete()

        if popup:
            return popup_delete_response(request, "familiare", object_id)

        messages.success(request, "Familiare eliminato correttamente.")
        return redirect("lista_familiari")

    template_name = "anagrafica/familiari/familiare_popup_delete.html" if popup else "anagrafica/familiari/familiari_conferma_elimina.html"

    return render(
        request,
        template_name,
        {
            "familiare": familiare,
            "impact": impact,
            "popup": popup,
        },
    )

#FINE VIEWS PER I FAMILIARI

#VIEWS PER I DOCUMENTI ALLEGATI

def crea_tipo_documento(request):
    popup = is_popup_request(request)

    TipoDocumentoForm = modelform_factory(
        TipoDocumento,
        fields=["tipo_documento", "ordine", "attivo", "note"],
    )

    if request.method == "POST":
        form = TipoDocumentoForm(request.POST)
        if form.is_valid():
            obj = form.save()

            if popup:
                return popup_select_response(
                    request,
                    field_name="tipo_documento",
                    object_id=obj.pk,
                    object_label=str(obj),
                )

            messages.success(request, "Tipo documento creato correttamente.")
            return redirect("lista_famiglie")
    else:
        form = TipoDocumentoForm()

    return render(
        request,
        "anagrafica/configurazioni/tipo_documento_popup_form.html" if popup else "anagrafica/configurazioni/tipo_documento_form.html",
        {
            "form": form,
            "titolo": "Nuovo tipo documento",
            "popup": popup,
        },
    )


def modifica_tipo_documento(request, pk):
    tipo = get_object_or_404(TipoDocumento, pk=pk)
    popup = is_popup_request(request)

    TipoDocumentoForm = modelform_factory(
        TipoDocumento,
        fields=["tipo_documento", "ordine", "attivo", "note"],
    )

    if request.method == "POST":
        form = TipoDocumentoForm(request.POST, instance=tipo)
        if form.is_valid():
            obj = form.save()

            if popup:
                return popup_select_response(
                    request,
                    field_name="tipo_documento",
                    object_id=obj.pk,
                    object_label=str(obj),
                )

            messages.success(request, "Tipo documento modificato correttamente.")
            return redirect("lista_famiglie")
    else:
        form = TipoDocumentoForm(instance=tipo)

    return render(
        request,
        "anagrafica/configurazioni/tipo_documento_popup_form.html" if popup else "anagrafica/configurazioni/tipo_documento_form.html",
        {
            "form": form,
            "titolo": "Modifica tipo documento",
            "popup": popup,
        },
    )


def elimina_tipo_documento(request, pk):
    tipo = get_object_or_404(TipoDocumento, pk=pk)
    popup = is_popup_request(request)

    object_id = tipo.pk

    if request.method == "POST":
        tipo.delete()

        if popup:
            return popup_delete_response(
                request,
                field_name="tipo_documento",
                object_id=object_id,
            )

        messages.success(request, "Tipo documento eliminato correttamente.")
        return redirect("lista_famiglie")

    return render(
        request,
        "anagrafica/configurazioni/tipo_documento_popup_delete.html" if popup else "anagrafica/configurazioni/tipo_documento_delete.html",
        {
            "oggetto": tipo,
            "titolo": "Elimina tipo documento",
            "popup": popup,
        },
    )

#FINE VIEWS PER I DOCUMENTI ALLEGATI

#INIZIO VIEWS PER GLI STUDENTI

def lista_studenti(request):
    q = request.GET.get("q", "").strip()

    studenti = (
        annotate_studenti_current_iscrizione_status(Studente.objects.all())
        .select_related(
            "indirizzo",
            "indirizzo__citta",
            "indirizzo__provincia",
            "indirizzo__regione",
            "indirizzo__cap_scelto",
            "luogo_nascita",
            "luogo_nascita__provincia",
            "nazione_nascita",
            "nazionalita",
        )
        .prefetch_related(active_student_relative_prefetch())
        .order_by("cognome", "nome")
    )

    if q:
        studenti = studenti.filter(
            Q(cognome__icontains=q) |
            Q(nome__icontains=q) |
            Q(codice_fiscale__icontains=q) |
            Q(luogo_nascita__nome__icontains=q) |
            Q(luogo_nascita__provincia__sigla__icontains=q) |
            Q(nazione_nascita__nome__icontains=q) |
            Q(luogo_nascita_custom__icontains=q) |
            Q(relazioni_familiari__attivo=True, relazioni_familiari__familiare__persona__nome__icontains=q) |
            Q(relazioni_familiari__attivo=True, relazioni_familiari__familiare__persona__cognome__icontains=q) |
            Q(relazioni_familiari__attivo=True, relazioni_familiari__familiare__persona__email__icontains=q) |
            Q(relazioni_familiari__attivo=True, relazioni_familiari__familiare__persona__telefono__icontains=q)
        ).distinct()

    studenti = list(studenti)
    decorate_studenti_current_enrollment_labels(studenti)
    decorate_studenti_direct_relation_labels(studenti)
    evidenzia_id = request.GET.get("highlight")

    return render(
        request,
        "anagrafica/studenti/studente_list.html",
        {
            "studenti": studenti,
            "q": q,
            "evidenzia_id": evidenzia_id,
        },
    )


def crea_studente(request):
    popup = is_popup_request(request)
    initial = {}
    familiare_collegato_id = (request.GET.get("familiare") or "").strip()
    if familiare_collegato_id.isdigit():
        familiare_collegato = (
            Familiare.objects.filter(pk=int(familiare_collegato_id), attivo=True).first()
        )
        if familiare_collegato:
            initial["familiari_collegati"] = [familiare_collegato.pk]

    if popup:
        if request.method == "POST":
            form = StudenteStandaloneForm(request.POST)
            if form.is_valid():
                studente = form.save()
                return popup_select_response(request, "studente", studente.pk, str(studente))
        else:
            form = StudenteStandaloneForm(initial=initial)

        return render(
            request,
            "anagrafica/studenti/studente_popup_form.html",
            {
                "form": form,
                "studente": None,
                "popup": popup,
            },
        )

    allowed_inline_targets = {"iscrizioni", "parenti", "documenti"}
    edit_scope = "full"
    inline_target = "iscrizioni"
    active_inline_tab = "iscrizioni"
    prefer_initial_active_tab = False
    iscrizioni_formset = None
    parenti_formset = None
    documenti_formset = None
    contact_formsets = {}

    if request.method == "POST":
        active_inline_tab = resolve_active_inline_tab(request, allowed_inline_targets, "iscrizioni")
        prefer_initial_active_tab = should_prefer_initial_famiglia_tab(request, allowed_inline_targets)
        edit_scope, inline_target = resolve_inline_target(
            request,
            allowed_inline_targets,
        )
        form = StudenteStandaloneForm(request.POST)
        iscrizioni_formset = (
            build_iscrizioni_studente_formset(data=request.POST, prefix="iscrizioni")
            if inline_target in (None, "iscrizioni")
            else None
        )
        parenti_formset = (
            build_familiari_formset(data=request.POST, prefix="parenti")
            if inline_target in (None, "parenti")
            else None
        )
        documenti_formset = (
            build_documenti_studente_formset(data=request.POST, files=request.FILES, prefix="documenti")
            if inline_target in (None, "documenti")
            else None
        )

        form_is_valid = form.is_valid()
        iscrizioni_is_valid = iscrizioni_formset.is_valid() if inline_target in (None, "iscrizioni") else True
        parenti_is_valid = parenti_formset.is_valid() if inline_target in (None, "parenti") else True
        documenti_is_valid = documenti_formset.is_valid() if inline_target in (None, "documenti") else True
        contatti_is_valid = True

        if form_is_valid and iscrizioni_is_valid and parenti_is_valid and documenti_is_valid and contatti_is_valid:
            missing_rate_count = 0
            try:
                with transaction.atomic():
                    studente = form.save()

                    if inline_target in (None, "iscrizioni"):
                        iscrizioni_formset.instance = studente
                        iscrizioni_salvate = iscrizioni_formset.save()
                        missing_rate_count = sync_studente_iscrizioni_rate_schedules(
                            studente,
                            iscrizioni=iscrizioni_salvate,
                        )

                    if inline_target in (None, "parenti"):
                        parenti_formset.save()

                    if inline_target in (None, "documenti"):
                        documenti_formset.instance = studente
                        documenti_formset.save()
            except DOCUMENT_STORAGE_ERROR_TYPES as exc:
                messages.error(request, build_document_storage_error_message(exc))
            else:
                if missing_rate_count:
                    messages.warning(
                        request,
                        "Una o piu iscrizioni sono state salvate senza generare il piano rate: verifica la tariffa attiva della condizione selezionata.",
                    )

                if "_continue" in request.POST:
                    messages.success(request, "Studente creato correttamente.")
                    return redirect(f"{reverse('lista_studenti')}?highlight={studente.pk}")

                if "_addanother" in request.POST:
                    messages.success(request, "Studente creato correttamente. Puoi inserirne un altro.")
                    return redirect("crea_studente")

                messages.success(request, "Studente creato correttamente. Ora puoi continuare a inserire i dati.")
                return redirect(build_studente_redirect_url(studente.pk, active_inline_tab))

        if iscrizioni_formset is None:
            iscrizioni_formset = build_iscrizioni_studente_formset(prefix="iscrizioni")
        if parenti_formset is None:
            parenti_formset = build_familiari_formset(prefix="parenti")
        if documenti_formset is None:
            documenti_formset = build_documenti_studente_formset(prefix="documenti")
    else:
        active_inline_tab = resolve_active_inline_tab(request, allowed_inline_targets, "iscrizioni")
        prefer_initial_active_tab = should_prefer_initial_famiglia_tab(request, allowed_inline_targets)
        form = StudenteStandaloneForm(initial=initial)
        iscrizioni_formset = build_iscrizioni_studente_formset(prefix="iscrizioni")
        parenti_formset = build_familiari_formset(prefix="parenti")
        documenti_formset = build_documenti_studente_formset(prefix="documenti")

    ctx = {
        "form": form,
        "iscrizioni_formset": iscrizioni_formset,
        "documenti_formset": documenti_formset,
        "parenti_formset": parenti_formset,
        **contact_formsets,
        "classe_corrente_label": "",
        "classe_corrente_tipo": "",
        "edit_scope": edit_scope,
        "inline_target": active_inline_tab,
        "active_inline_tab": active_inline_tab,
        "prefer_initial_active_tab": prefer_initial_active_tab,
        "show_inline_iscrizioni_editor": edit_scope == "inline" and inline_target == "iscrizioni",
        "count_iscrizioni": 0,
        "count_documenti": 0,
        "count_parenti": 0,
        "count_genitori_tutori": 0,
        "count_fratelli_sorelle": 0,
        "familiari_collegati_diretti": [],
        "studenti_parenti_diretti": [],
        "studente_indirizzi_correlati": [],
        "parenti_famiglia": [],
        "studenti_parenti_famiglia": [],
        "count_documenti_in_scadenza": 0,
        "count_documenti_scaduti": 0,
        "count_rate_scadute": 0,
        "rate_overview": [],
        "iscrizione_corrente": None,
        "studente_activity_entries": [],
        "has_form_errors": bool(
            form.errors
            or iscrizioni_formset.total_error_count()
            or parenti_formset.total_error_count()
            or documenti_formset.total_error_count()
        ),
    }
    ctx.update(
        studente_inline_head(
            inline_target=active_inline_tab,
            count_iscrizioni=ctx["count_iscrizioni"],
            count_documenti=ctx["count_documenti"],
            count_parenti=0,
            count_fratelli_sorelle=0,
        )
    )
    return render(request, "anagrafica/studenti/studente_form.html", ctx)


def modifica_studente(request, pk):
    studente = get_object_or_404(
        Studente.objects.select_related(
            "indirizzo",
            "indirizzo__provincia",
            "indirizzo__regione",
            "indirizzo__citta__provincia",
            "luogo_nascita",
            "luogo_nascita__provincia",
        ).prefetch_related(
            active_student_relative_prefetch()
        ),
        pk=pk,
    )
    today = timezone.localdate()
    popup = is_popup_request(request)
    edit_scope = "full" if request.GET.get("edit") == "1" else "view"
    inline_target = "iscrizioni"
    allowed_display_targets = {"iscrizioni", "parenti", "fratelli", "documenti"}
    allowed_edit_targets = {"iscrizioni", "parenti", "documenti"}
    active_inline_tab = resolve_active_inline_tab(request, allowed_display_targets, "iscrizioni")
    prefer_initial_active_tab = should_prefer_initial_famiglia_tab(request, allowed_display_targets)
    familiari_diretti_form = None
    contact_formsets = None

    if popup:
        if request.method == "POST":
            form = StudenteStandaloneForm(request.POST, instance=studente)
            if form.is_valid():
                studente = form.save()
                return popup_select_response(request, "studente", studente.pk, str(studente))
        else:
            form = StudenteStandaloneForm(instance=studente)

        return render(
            request,
            "anagrafica/studenti/studente_popup_form.html",
            {
                "form": form,
                "studente": studente,
                "popup": popup,
            },
        )

    iscrizioni_queryset = studente_iscrizioni_inline_queryset(studente)
    documenti_queryset = studente_documenti_inline_queryset(studente)
    famiglia_for_parenti = None
    relazioni_familiari_prefetch = getattr(studente, "relazioni_familiari_attive_prefetch", None)
    if relazioni_familiari_prefetch is None:
        familiari_collegati_diretti = list(
            studente.relazioni_familiari.filter(attivo=True)
            .select_related(
                "familiare",
                "familiare__relazione_familiare",
                "familiare__persona",
                "familiare__persona__indirizzo",
                "familiare__persona__indirizzo__citta",
            )
            .order_by("familiare__persona__cognome", "familiare__persona__nome", "familiare_id")
        )
    else:
        familiari_collegati_diretti = list(relazioni_familiari_prefetch)
    studenti_parenti_diretti = direct_student_peers_for_relations(studente, familiari_collegati_diretti)
    parenti_formset_queryset = ordered_queryset_from_ids(
        Familiare,
        [relazione.familiare_id for relazione in familiari_collegati_diretti],
        select_related_fields=("relazione_familiare", "persona", "persona__indirizzo", "persona__indirizzo__citta"),
    )

    if request.method == "POST":
        if request.POST.get("_note_popup") == "1":
            nuova_nota = request.POST.get("note", "")
            if studente.note != nuova_nota:
                studente.note = nuova_nota
                studente.save(update_fields=["note"])
                messages.success(request, "Note dello studente aggiornate correttamente.")

            note_active_tab = (request.POST.get("_note_active_tab") or "iscrizioni").strip()
            if note_active_tab not in allowed_display_targets:
                note_active_tab = "iscrizioni"
            return redirect(build_studente_redirect_url(studente.pk, note_active_tab))

        edit_scope, inline_target = resolve_inline_target(
            request,
            allowed_edit_targets,
        )
        inline_editing = edit_scope == "inline"
        card_inline_submit = (request.POST.get("_card_inline_submit") or "").strip()
        if inline_target in allowed_edit_targets:
            active_inline_tab = inline_target
        form = (
            StudenteStandaloneForm(instance=studente)
            if inline_editing
            else StudenteStandaloneForm(request.POST, instance=studente)
        )
        contact_formsets = {}
        familiari_diretti_form = StudenteDirectFamiliariForm(
            request.POST if inline_editing and inline_target == "parenti" else None,
            studente=studente,
        )
        iscrizioni_formset = (
            build_iscrizioni_studente_formset(
                data=request.POST,
                instance=studente,
                prefix="iscrizioni",
                queryset=iscrizioni_queryset,
            )
            if inline_target == "iscrizioni"
            else None
        )
        documenti_formset = (
            build_documenti_studente_formset(
                data=request.POST,
                files=request.FILES,
                instance=studente,
                prefix="documenti",
                queryset=documenti_queryset,
            )
            if inline_target == "documenti"
            else None
        )
        parenti_formset = build_familiari_formset(
            data=request.POST if inline_target == "parenti" and card_inline_submit == "parenti" else None,
            instance=famiglia_for_parenti,
            prefix="parenti",
            queryset=parenti_formset_queryset,
        )

        form_is_valid = True if inline_editing else form.is_valid()
        iscrizioni_is_valid = iscrizioni_formset.is_valid() if inline_target == "iscrizioni" else True
        documenti_is_valid = documenti_formset.is_valid() if inline_target == "documenti" else True
        contatti_is_valid = True
        parenti_is_valid = True
        if inline_target == "parenti":
            if card_inline_submit == "parenti" and parenti_formset is not None:
                parenti_is_valid = parenti_formset.is_valid()
            else:
                parenti_is_valid = familiari_diretti_form.is_valid()

        if form_is_valid and iscrizioni_is_valid and documenti_is_valid and parenti_is_valid and contatti_is_valid:
            missing_rate_count = 0
            try:
                with transaction.atomic():
                    if not inline_editing:
                        studente = form.save()
                    if inline_target == "iscrizioni":
                        iscrizioni_salvate = iscrizioni_formset.save()
                        missing_rate_count = sync_studente_iscrizioni_rate_schedules(
                            studente,
                            iscrizioni=iscrizioni_salvate,
                            sync_all=student_form_changes_require_full_rate_sync(form),
                        )

                    if inline_target == "documenti":
                        documenti_formset.save()

                    if inline_target == "parenti" and card_inline_submit == "parenti" and parenti_formset is not None:
                        parenti_formset.save()
                        for parente_salvato in getattr(parenti_formset, "new_objects", []):
                            ensure_direct_student_family_relation(studente, parente_salvato)

                    if inline_target == "parenti" and card_inline_submit != "parenti":
                        familiari_diretti_form.save()
            except DOCUMENT_STORAGE_ERROR_TYPES as exc:
                messages.error(request, build_document_storage_error_message(exc))
            else:
                if missing_rate_count:
                    messages.warning(
                        request,
                        "Una o piu iscrizioni sono state salvate senza generare il piano rate: verifica la tariffa attiva della condizione selezionata.",
                    )

                if "_continue" in request.POST:
                    messages.success(request, "Modifiche salvate correttamente.")
                    return redirect(build_studente_redirect_url(studente.pk, active_inline_tab))

                if "_addanother" in request.POST:
                    messages.success(request, "Modifiche salvate correttamente. Puoi inserire un nuovo studente.")
                    return redirect("crea_studente")

                messages.success(request, "Modifiche salvate correttamente.")
                return redirect(build_studente_redirect_url(studente.pk, active_inline_tab))

        if iscrizioni_formset is None:
            iscrizioni_formset = build_iscrizioni_studente_formset(
                instance=studente,
                prefix="iscrizioni",
                queryset=iscrizioni_queryset,
            )
        if documenti_formset is None:
            documenti_formset = build_documenti_studente_formset(
                instance=studente,
                prefix="documenti",
                queryset=documenti_queryset,
            )
    else:
        form = StudenteStandaloneForm(instance=studente)
        contact_formsets = {}
        familiari_diretti_form = StudenteDirectFamiliariForm(studente=studente)
        iscrizioni_formset = build_iscrizioni_studente_formset(
            instance=studente,
            prefix="iscrizioni",
            queryset=iscrizioni_queryset,
        )
        documenti_formset = build_documenti_studente_formset(
            instance=studente,
            prefix="documenti",
            queryset=documenti_queryset,
        )
        parenti_formset = build_familiari_formset(
            instance=famiglia_for_parenti,
            prefix="parenti",
            queryset=parenti_formset_queryset,
        )

    iscrizioni_correnti_list = list(iscrizioni_queryset)
    iscrizione_corrente = (
        next(
            (
                item for item in sorted(
                    (iscrizione for iscrizione in iscrizioni_correnti_list if iscrizione.classe_id or iscrizione.gruppo_classe_id),
                    key=lambda iscrizione: (
                        0 if iscrizione.attiva else 1,
                        -(iscrizione.anno_scolastico.data_inizio.toordinal() if iscrizione.anno_scolastico and iscrizione.anno_scolastico.data_inizio else 0),
                        -iscrizione.pk,
                    ),
                )
            ),
            None,
        )
    )
    classe_corrente_tipo, classe_corrente_label = current_iscrizione_class_display(iscrizione_corrente)
    document_counts = build_studente_document_counts(studente, today)
    studente_activity = studente_activity_entries(
        studente,
        iscrizione_ids=[item.pk for item in iscrizioni_correnti_list],
    )
    studente_audit_info = studente_audit_labels(studente)
    parenti_famiglia = []
    studenti_parenti_famiglia = []
    count_parenti_legacy = 0
    decorate_studenti_current_enrollment_labels(studenti_parenti_diretti, today=today)
    usa_parenti_diretti = bool(familiari_collegati_diretti)
    usa_fratelli_diretti = bool(studenti_parenti_diretti)
    count_genitori_tutori = len(familiari_collegati_diretti) if usa_parenti_diretti else count_parenti_legacy
    count_fratelli_sorelle = (
        len(studenti_parenti_diretti)
        if usa_fratelli_diretti
        else len(studenti_parenti_famiglia)
    )
    count_parenti = count_genitori_tutori
    rate_overview = build_studente_rate_overview(studente, iscrizioni_correnti_list)
    student_family_referenti = [
        relazione.familiare
        for relazione in familiari_collegati_diretti
        if getattr(relazione, "familiare", None)
    ]
    studente_famiglia_logica = build_person_family_display(
        studente,
        key_prefix="s",
        referenti=student_family_referenti,
    )
    studente_indirizzi_correlati = build_studente_address_suggestions(
        studente,
        familiari_collegati_diretti,
        studenti_parenti_diretti,
    )

    ctx = {
        "form": form,
        "studente": studente,
        "studente_famiglia_logica": studente_famiglia_logica,
        **contact_formsets,
        "parenti_famiglia": parenti_famiglia,
        "studenti_parenti_famiglia": studenti_parenti_famiglia,
        "studenti_parenti_diretti": studenti_parenti_diretti,
        "familiari_collegati_diretti": familiari_collegati_diretti,
        "studente_indirizzi_correlati": studente_indirizzi_correlati,
        "familiari_diretti_form": familiari_diretti_form,
        "usa_parenti_diretti": usa_parenti_diretti,
        "usa_parenti_diretti_cards": usa_parenti_diretti and parenti_formset is None,
        "usa_fratelli_diretti": usa_fratelli_diretti,
        "count_parenti": count_parenti,
        "count_genitori_tutori": count_genitori_tutori,
        "count_fratelli_sorelle": count_fratelli_sorelle,
        "iscrizioni_formset": iscrizioni_formset,
        "documenti_formset": documenti_formset,
        "parenti_formset": parenti_formset,
        "classe_corrente_label": classe_corrente_label,
        "classe_corrente_tipo": classe_corrente_tipo,
        "edit_scope": edit_scope,
        "inline_target": active_inline_tab,
        "prefer_initial_active_tab": prefer_initial_active_tab,
        "show_inline_iscrizioni_editor": edit_scope == "inline" and inline_target == "iscrizioni",
        "count_iscrizioni": len(iscrizioni_correnti_list),
        "count_documenti": document_counts["count_documenti"],
        "count_documenti_in_scadenza": document_counts["count_documenti_in_scadenza"],
        "count_documenti_scaduti": document_counts["count_documenti_scaduti"],
        "count_rate_scadute": count_studente_rate_scadute_from_overview(rate_overview, today),
        "rate_overview": rate_overview,
        "iscrizione_corrente": iscrizione_corrente,
        "studente_activity_entries": studente_activity,
        "studente_creazione_data": studente_audit_info["created_data"],
        "studente_creato_da_label": studente_audit_info["created_label"],
        "studente_ultima_modifica_data": studente_audit_info["updated_data"],
        "studente_aggiornato_da_label": studente_audit_info["updated_label"],
        "has_form_errors": bool(
            form.errors
            or iscrizioni_formset.total_error_count()
            or documenti_formset.total_error_count()
            or (parenti_formset.total_error_count() if parenti_formset is not None else 0)
        ),
    }
    ctx.update(
        studente_inline_head(
            inline_target=active_inline_tab,
            count_iscrizioni=ctx["count_iscrizioni"],
            count_documenti=ctx["count_documenti"],
            count_parenti=count_parenti,
            count_fratelli_sorelle=count_fratelli_sorelle,
        )
    )
    return render(request, "anagrafica/studenti/studente_form.html", ctx)


def get_studente_print_osservazioni(request, studente):
    try:
        from osservazioni.views import get_osservazioni_policy, user_can_manage_osservazioni
        from sistema.permissions import user_is_operational_admin
    except ImportError:
        return [], False

    if not user_can_manage_osservazioni(request.user):
        return [], False

    osservazioni_policy = get_osservazioni_policy()
    osservazioni_qs = studente.osservazioni.select_related("creato_da", "aggiornato_da").order_by(
        "data_inserimento",
        "id",
    )
    if osservazioni_policy["solo_autori_visualizzazione"] and not user_is_operational_admin(request.user):
        osservazioni_qs = osservazioni_qs.filter(creato_da=request.user)

    return list(osservazioni_qs), True


def get_studente_print_payload(request, studente, *, include_rate=False, include_osservazioni=False):
    anno_corrente = resolve_default_anno_scolastico(AnnoScolastico.objects.filter(attivo=True))
    iscrizioni_correnti = []
    rate_overview = []

    if include_rate and anno_corrente:
        iscrizioni_correnti = list(
            studente_iscrizioni_inline_queryset(studente).filter(anno_scolastico=anno_corrente)
        )
        rate_overview = build_studente_rate_overview(studente, iscrizioni_correnti)

    osservazioni = []
    can_print_osservazioni = False
    if include_osservazioni:
        osservazioni, can_print_osservazioni = get_studente_print_osservazioni(request, studente)
    else:
        _, can_print_osservazioni = get_studente_print_osservazioni(request, studente)

    classe_corrente_label = ""
    iscrizione_corrente = next((item for item in iscrizioni_correnti if item.classe_id or item.gruppo_classe_id), None)
    if iscrizione_corrente and iscrizione_corrente.classe:
        classe_corrente_label = str(iscrizione_corrente.classe)
    elif iscrizione_corrente and iscrizione_corrente.gruppo_classe_id:
        classe_corrente_label = iscrizione_corrente.gruppo_classe.nome_gruppo_classe
    elif anno_corrente:
        iscrizione_corrente = (
            studente.iscrizioni.select_related("classe", "gruppo_classe", "anno_scolastico")
            .filter(anno_scolastico=anno_corrente)
            .filter(Q(classe__isnull=False) | Q(gruppo_classe__isnull=False))
            .order_by("-attiva", "-pk")
            .first()
        )
        if iscrizione_corrente and iscrizione_corrente.classe:
            classe_corrente_label = str(iscrizione_corrente.classe)
        elif iscrizione_corrente and iscrizione_corrente.gruppo_classe_id:
            classe_corrente_label = iscrizione_corrente.gruppo_classe.nome_gruppo_classe

    return {
        "anno_corrente": anno_corrente,
        "classe_corrente_label": classe_corrente_label,
        "studente_famiglia_logica": build_person_family_display(studente, key_prefix="s"),
        "rate_overview": rate_overview,
        "osservazioni": osservazioni,
        "can_print_osservazioni": can_print_osservazioni,
    }


def stampa_studente_opzioni(request, pk):
    studente = get_object_or_404(
        Studente.objects.all(),
        pk=pk,
    )
    _, can_print_osservazioni = get_studente_print_osservazioni(request, studente)
    anno_corrente = resolve_default_anno_scolastico(AnnoScolastico.objects.filter(attivo=True))

    return render(
        request,
        "anagrafica/studenti/studente_print_options.html",
        {
            "studente": studente,
            "anno_corrente": anno_corrente,
            "can_print_osservazioni": can_print_osservazioni,
        },
    )


def stampa_studente(request, pk):
    studente = get_object_or_404(
        Studente.objects.select_related(
            "indirizzo",
            "indirizzo__citta",
            "luogo_nascita",
            "luogo_nascita__provincia",
            "nazione_nascita",
            "nazionalita",
        ),
        pk=pk,
    )

    include_dati_generali = request.GET.get("dati_generali") == "1"
    include_rate = request.GET.get("piano_rate") == "1"
    include_osservazioni = request.GET.get("osservazioni") == "1"
    if not any([include_dati_generali, include_rate, include_osservazioni]):
        include_dati_generali = True

    payload = get_studente_print_payload(
        request,
        studente,
        include_rate=include_rate,
        include_osservazioni=include_osservazioni,
    )

    return render(
        request,
        "anagrafica/studenti/studente_print.html",
        {
            "studente": studente,
            "print_date": timezone.localdate(),
            "include_dati_generali": include_dati_generali,
            "include_rate": include_rate,
            "include_osservazioni": include_osservazioni and payload["can_print_osservazioni"],
            **payload,
        },
    )


def elimina_studente(request, pk):
    studente = get_object_or_404(Studente, pk=pk)
    impact = get_record_documents_impact(studente)
    popup = is_popup_request(request)

    if request.method == "POST":
        object_id = studente.pk
        studente.delete()

        if popup:
            return popup_delete_response(request, "studente", object_id)

        messages.success(request, "Studente eliminato correttamente.")
        return redirect("lista_studenti")

    template_name = "anagrafica/studenti/studente_popup_delete.html" if popup else "anagrafica/studenti/studente_conferma_elimina.html"

    return render(
        request,
        template_name,
        {
            "studente": studente,
            "impact": impact,
            "popup": popup,
        },
    )

#FINE VIEWS PER GLI STUDENTI
