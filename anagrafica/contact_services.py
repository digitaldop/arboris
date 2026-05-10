import re
from collections import defaultdict

from django.contrib.contenttypes.models import ContentType
from django.db.models import Q

from .models import (
    AnagraficaEmail,
    AnagraficaIndirizzo,
    AnagraficaTelefono,
    Familiare,
    Indirizzo,
    LabelEmail,
    LabelIndirizzo,
    LabelTelefono,
    Studente,
    StudenteFamiliare,
)


DEFAULT_ADDRESS_LABELS = ["Principale", "Residenza", "Domicilio", "Casa", "Lavoro", "Altro"]
DEFAULT_PHONE_LABELS = ["Principale", "Cellulare", "Casa", "Lavoro", "Emergenza", "Altro"]
DEFAULT_EMAIL_LABELS = ["Principale", "Personale", "Lavoro", "PEC", "Altro"]


def normalize_address_part(value):
    value = (value or "").strip().lower()
    value = re.sub(r"[^\w\s]", " ", value)
    value = re.sub(r"\s+", " ", value).strip()
    replacements = {
        "v ": "via ",
        "v. ": "via ",
        "p zza ": "piazza ",
        "p.zza ": "piazza ",
        "str ": "strada ",
    }
    for old, new in replacements.items():
        value = value.replace(old, new)
    return value


def ensure_default_contact_labels():
    labels = {}
    for index, label in enumerate(DEFAULT_ADDRESS_LABELS, start=1):
        labels.setdefault("indirizzi", {})[label] = LabelIndirizzo.objects.get_or_create(
            nome=label,
            defaults={"ordine": index, "attiva": True},
        )[0]
    for index, label in enumerate(DEFAULT_PHONE_LABELS, start=1):
        labels.setdefault("telefoni", {})[label] = LabelTelefono.objects.get_or_create(
            nome=label,
            defaults={"ordine": index, "attiva": True},
        )[0]
    for index, label in enumerate(DEFAULT_EMAIL_LABELS, start=1):
        labels.setdefault("email", {})[label] = LabelEmail.objects.get_or_create(
            nome=label,
            defaults={"ordine": index, "attiva": True},
        )[0]
    return labels


def sync_principal_contacts(instance, *, indirizzo=None, telefono=None, email=None):
    if not getattr(instance, "pk", None):
        return

    labels = ensure_default_contact_labels()
    content_type = ContentType.objects.get_for_model(instance, for_concrete_model=False)

    if indirizzo:
        AnagraficaIndirizzo.objects.update_or_create(
            content_type=content_type,
            object_id=instance.pk,
            principale=True,
            defaults={
                "indirizzo": indirizzo,
                "label": labels["indirizzi"]["Principale"],
                "ordine": 1,
            },
        )

    if telefono is not None:
        telefono = (telefono or "").strip()
        if telefono:
            AnagraficaTelefono.objects.update_or_create(
                content_type=content_type,
                object_id=instance.pk,
                principale=True,
                defaults={
                    "numero": telefono,
                    "label": labels["telefoni"]["Principale"],
                    "ordine": 1,
                },
            )
        else:
            AnagraficaTelefono.objects.filter(
                content_type=content_type,
                object_id=instance.pk,
                principale=True,
            ).delete()

    if email is not None:
        email = (email or "").strip().lower()
        if email:
            AnagraficaEmail.objects.update_or_create(
                content_type=content_type,
                object_id=instance.pk,
                principale=True,
                defaults={
                    "email": email,
                    "label": labels["email"]["Principale"],
                    "ordine": 1,
                },
            )
        else:
            AnagraficaEmail.objects.filter(
                content_type=content_type,
                object_id=instance.pk,
                principale=True,
            ).delete()


def _owner_content_type(instance):
    if not getattr(instance, "pk", None):
        return None
    return ContentType.objects.get_for_model(instance, for_concrete_model=False)


def _ensure_single_principal_link(model_cls, content_type, object_id):
    links = list(
        model_cls.objects.filter(content_type=content_type, object_id=object_id)
        .order_by("-principale", "ordine", "id")
    )
    if not links:
        return None

    principal = links[0]
    if not principal.principale:
        model_cls.objects.filter(pk=principal.pk).update(principale=True)
        principal.principale = True

    model_cls.objects.filter(
        content_type=content_type,
        object_id=object_id,
        principale=True,
    ).exclude(pk=principal.pk).update(principale=False)
    return principal


def sync_legacy_contact_fields_from_links(instance):
    """
    Keep the old single-value fields aligned with the selected primary links.

    The multi-contact tables are the new source of truth when the user edits
    them, but several old list/detail pages still read the legacy fields.
    """
    content_type = _owner_content_type(instance)
    if content_type is None:
        return instance

    update_fields = []
    address_link = _ensure_single_principal_link(AnagraficaIndirizzo, content_type, instance.pk)
    phone_link = _ensure_single_principal_link(AnagraficaTelefono, content_type, instance.pk)
    email_link = _ensure_single_principal_link(AnagraficaEmail, content_type, instance.pk)

    if address_link and hasattr(instance, "indirizzo_id") and instance.indirizzo_id != address_link.indirizzo_id:
        instance.indirizzo = address_link.indirizzo
        update_fields.append("indirizzo")
    elif not address_link and hasattr(instance, "indirizzo_id") and instance.indirizzo_id:
        instance.indirizzo = None
        update_fields.append("indirizzo")

    if phone_link and hasattr(instance, "telefono") and instance.telefono != phone_link.numero:
        instance.telefono = phone_link.numero
        update_fields.append("telefono")
    elif not phone_link and hasattr(instance, "telefono") and instance.telefono:
        instance.telefono = ""
        update_fields.append("telefono")

    if email_link and hasattr(instance, "email") and instance.email != email_link.email:
        instance.email = email_link.email
        update_fields.append("email")
    elif not email_link and hasattr(instance, "email") and instance.email:
        instance.email = ""
        update_fields.append("email")

    if update_fields:
        instance.save(update_fields=update_fields)

    return instance


def _student_family_relation_defaults(studente, familiare):
    return {
        "relazione_familiare_id": familiare.relazione_familiare_id,
        "referente_principale": familiare.referente_principale,
        "convivente": familiare.convivente,
        "attivo": familiare.attivo and studente.attivo,
    }


def _relation_has_defaults(relation, defaults):
    return (
        relation.relazione_familiare_id == defaults["relazione_familiare_id"]
        and relation.referente_principale == defaults["referente_principale"]
        and relation.convivente == defaults["convivente"]
        and relation.attivo == defaults["attivo"]
    )


def _sync_family_relation_pair(studente, familiare, *, dry_run=False, update_existing=True):
    defaults = _student_family_relation_defaults(studente, familiare)
    relation = StudenteFamiliare.objects.filter(studente=studente, familiare=familiare).first()

    if relation:
        if not update_existing or _relation_has_defaults(relation, defaults):
            return "unchanged"
        if dry_run:
            return "updated"
        relation.relazione_familiare_id = defaults["relazione_familiare_id"]
        relation.referente_principale = defaults["referente_principale"]
        relation.convivente = defaults["convivente"]
        relation.attivo = defaults["attivo"]
        relation.save(
            update_fields=[
                "relazione_familiare",
                "referente_principale",
                "convivente",
                "attivo",
                "data_aggiornamento",
            ]
        )
        return "updated"

    if dry_run:
        return "created"
    StudenteFamiliare.objects.create(
        studente=studente,
        familiare=familiare,
        **defaults,
    )
    return "created"


def sync_studente_familiare_from_family(studente):
    return


def sync_familiare_studenti_from_family(familiare):
    return


def sync_all_student_family_relations(*, dry_run=False, update_existing=True):
    return {
        "studenti": 0,
        "famiglie": 0,
        "familiari": 0,
        "relazioni_esaminate": 0,
        "created": 0,
        "updated": 0,
        "unchanged": 0,
    }


def _set_studente_familiare_relation(studente, familiare, *, attivo=True):
    return StudenteFamiliare.objects.update_or_create(
        studente=studente,
        familiare=familiare,
        defaults={
            "relazione_familiare_id": familiare.relazione_familiare_id,
            "referente_principale": familiare.referente_principale,
            "convivente": familiare.convivente,
            "attivo": attivo and familiare.attivo and studente.attivo,
        },
    )[0]


def set_studente_familiari(studente, familiari):
    if not getattr(studente, "pk", None):
        return

    selected_ids = set()
    for familiare in familiari:
        if not getattr(familiare, "pk", None):
            continue
        selected_ids.add(familiare.pk)
        _set_studente_familiare_relation(studente, familiare)

    StudenteFamiliare.objects.filter(studente=studente).exclude(familiare_id__in=selected_ids).update(attivo=False)


def set_familiare_studenti(familiare, studenti):
    if not getattr(familiare, "pk", None):
        return

    selected_ids = set()
    for studente in studenti:
        if not getattr(studente, "pk", None):
            continue
        selected_ids.add(studente.pk)
        _set_studente_familiare_relation(studente, familiare)

    StudenteFamiliare.objects.filter(familiare=familiare).exclude(studente_id__in=selected_ids).update(attivo=False)


def _owner_label(obj):
    if not obj:
        return ""
    if hasattr(obj, "nome_completo"):
        label = obj.nome_completo
    else:
        label = str(obj)
    return label.strip()


def _address_owner_payload(indirizzo):
    owners = []
    seen = set()

    for link in (
        AnagraficaIndirizzo.objects.filter(indirizzo=indirizzo)
        .select_related("content_type", "label")
        .order_by("content_type__model", "object_id")
    ):
        key = (link.content_type_id, link.object_id)
        if key in seen:
            continue
        seen.add(key)
        owner = link.content_object
        owners.append(
            {
                "tipo": link.content_type.name.title(),
                "nome": _owner_label(owner),
                "label": link.label.nome,
                "principale": link.principale,
            }
        )

    legacy_sources = [
        ("Familiare", Familiare.objects.filter(indirizzo=indirizzo)),
        ("Studente", Studente.objects.filter(indirizzo=indirizzo)),
    ]
    for tipo, queryset in legacy_sources:
        for obj in queryset[:10]:
            key = (tipo, obj.pk)
            if key in seen:
                continue
            seen.add(key)
            owners.append({"tipo": tipo, "nome": _owner_label(obj), "label": "Legacy", "principale": False})

    return owners


def address_duplicate_candidates(*, via, numero_civico="", cap="", citta_id=None, exclude_id=None, limit=8):
    via_norm = normalize_address_part(via)
    numero_norm = normalize_address_part(numero_civico)
    cap = (cap or "").strip()
    try:
        citta_id = int(citta_id) if citta_id else None
    except (TypeError, ValueError):
        citta_id = None
    if not via_norm:
        return []

    words = [word for word in via_norm.split() if len(word) >= 3]
    queryset = Indirizzo.objects.select_related("citta", "provincia", "regione")
    if exclude_id:
        queryset = queryset.exclude(pk=exclude_id)
    if citta_id:
        queryset = queryset.filter(citta_id=citta_id)
    if words:
        query = Q()
        for word in words[:3]:
            query |= Q(via__icontains=word)
        queryset = queryset.filter(query)
    elif cap:
        queryset = queryset.filter(cap=cap)

    candidates = []
    for indirizzo in queryset[:80]:
        existing_via = normalize_address_part(indirizzo.via)
        existing_numero = normalize_address_part(indirizzo.numero_civico)
        score = 0
        if existing_via == via_norm:
            score += 70
        elif existing_via in via_norm or via_norm in existing_via:
            score += 45
        else:
            score += sum(8 for word in words if word in existing_via)
        if citta_id and indirizzo.citta_id == citta_id:
            score += 20
        if cap and indirizzo.cap == cap:
            score += 10
        if numero_norm and existing_numero == numero_norm:
            score += 15
        elif not numero_norm or not existing_numero:
            score += 5

        if score < 45:
            continue

        candidates.append(
            {
                "id": indirizzo.pk,
                "label": indirizzo.label_full(),
                "score": min(score, 100),
                "owners": _address_owner_payload(indirizzo),
            }
        )

    candidates.sort(key=lambda item: item["score"], reverse=True)
    return candidates[:limit]
