"""Address settings for Arboris' connected logical families.

Membership remains defined exclusively by active StudenteFamiliare relations.
No document, financial or family identity is moved to this settings model.
"""
from django.db import transaction

from .models import Familiare, ResidenzaFamiglia, Studente


@transaction.atomic
def set_family_address(snapshot, address):
    # Always detach this component from a potentially split former component.
    # Changing its principal address must not move relatives outside this graph.
    residence = ResidenzaFamiglia.objects.create(indirizzo_principale=address)
    Studente.objects.filter(pk__in=snapshot.student_ids).update(residenza_famiglia=residence)
    Familiare.objects.filter(pk__in=snapshot.familiare_ids).update(residenza_famiglia=residence)
    return residence


@transaction.atomic
def connect_family_addresses(relation):
    from .family_logic import _connected_member_ids, _derive_family_address, _load_relatives, _load_students

    students, relatives = _connected_member_ids({relation.studente_id}, {relation.familiare_id})
    # Serialize concurrent changes to this component in a consistent order.
    list(Studente.objects.filter(pk__in=students).order_by("pk").select_for_update())
    list(Familiare.objects.filter(pk__in=relatives).order_by("pk").select_for_update())
    people = _load_students(students) + _load_relatives(relatives)
    settings = {person.residenza_famiglia_id: person.residenza_famiglia for person in people if person.residenza_famiglia_id}
    addresses = {item.indirizzo_principale_id for item in settings.values() if item.indirizzo_principale_id}
    if len(addresses) > 1:
        # A new kinship relation is not proof that two households cohabit.
        # Keep their settings and let the family page resolve explicitly.
        return
    if settings:
        residence = next((item for item in settings.values() if item.indirizzo_principale_id), next(iter(settings.values())))
    else:
        residence = ResidenzaFamiglia.objects.create(indirizzo_principale=_derive_family_address(people, []))
    Studente.objects.filter(pk__in=students).update(residenza_famiglia=residence)
    Familiare.objects.filter(pk__in=relatives).update(residenza_famiglia=residence)
    relation.studente.residenza_famiglia = residence
    relation.familiare.residenza_famiglia = residence


@transaction.atomic
def initialize_family_address(person):
    address_id = getattr(person.indirizzo, "pk", None)
    if not person.residenza_famiglia_id or not address_id:
        return
    residence = ResidenzaFamiglia.objects.filter(pk=person.residenza_famiglia_id, indirizzo_principale__isnull=True).select_for_update().first()
    if residence is None:
        return
    from .family_logic import _connected_member_ids, build_logical_family_snapshot_from_ids
    students, relatives = _connected_member_ids(
        {person.pk} if isinstance(person, Studente) else set(),
        {person.pk} if isinstance(person, Familiare) else set(),
    )
    if residence.studenti.exclude(pk__in=students).exists() or residence.familiari.exclude(pk__in=relatives).exists():
        residence = set_family_address(build_logical_family_snapshot_from_ids(students, relatives), person.indirizzo)
        person.residenza_famiglia = residence
    else:
        ResidenzaFamiglia.objects.filter(pk=residence.pk).update(indirizzo_principale_id=address_id)
