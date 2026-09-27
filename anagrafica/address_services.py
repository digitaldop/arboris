"""All application address creation goes through this module."""
from django.core.exceptions import ValidationError
from django.db import transaction

from .address_normalization import address_identity


def prepare_address(address):
    if address.cap_scelto_id:
        if address.citta_id and address.cap_scelto.citta_id != address.citta_id:
            raise ValidationError({"cap_scelto": "Il CAP non appartiene alla città scelta."})
        address.citta = address.cap_scelto.citta
        address.cap = address.cap_scelto.codice
    if address.citta_id:
        address.provincia = address.citta.provincia
        address.regione = address.citta.provincia.regione
    address.via_normalizzata, address.civico_normalizzato, address.chiave_normalizzata = address_identity(
        address.via, address.numero_civico, address.citta_id, address.cap,
        address.provincia_id, address.regione_id,
    )
    return address


def get_or_create_normalized_address(*, using="default", **values):
    from .models import Indirizzo

    address = prepare_address(Indirizzo(**values))
    if not address.via_normalizzata:
        raise ValidationError({"via": "Inserisci la strada."})
    # get_or_create uses a savepoint and retries the indexed lookup after a
    # concurrent insert raises IntegrityError (including on PostgreSQL).
    with transaction.atomic(using=using):
        if address.chiave_normalizzata:
            defaults = {
                field.attname: getattr(address, field.attname)
                for field in Indirizzo._meta.concrete_fields if not field.primary_key
            }
            defaults.pop("chiave_normalizzata")
            return Indirizzo.objects.using(using).get_or_create(
                chiave_normalizzata=address.chiave_normalizzata, defaults=defaults,
            )
        # Incomplete historical/manual records must never be merged by guesswork.
        address.save(using=using)
        return address, True


def address_references(address):
    """Include every real FK, including secondary contacts and school settings."""
    return [
        (relation, relation.related_model._base_manager.filter(**{relation.field.attname: address.pk}))
        for relation in address._meta.related_objects
        if relation.one_to_many or relation.one_to_one
    ]
