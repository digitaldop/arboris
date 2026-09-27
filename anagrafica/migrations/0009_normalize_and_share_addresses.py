from collections import Counter, defaultdict

from django.db import migrations, models

from anagrafica.address_normalization import address_identity


def consolidate_addresses(apps, schema_editor):
    alias = schema_editor.connection.alias
    Address = apps.get_model("anagrafica", "Indirizzo")
    Archive = apps.get_model("anagrafica", "IndirizzoArchivioMigrazione")
    references = [
        (model, field)
        for model in apps.get_models()
        for field in model._meta.local_fields
        if field.is_relation and field.remote_field.model == Address
    ]
    if schema_editor.connection.vendor == "postgresql":
        tables = {Address._meta.db_table} | {model._meta.db_table for model, _ in references}
        schema_editor.execute("LOCK TABLE " + ", ".join(schema_editor.quote_name(t) for t in sorted(tables)) + " IN SHARE ROW EXCLUSIVE MODE")
    canonical = {}
    for address in Address.objects.using(alias).select_related("citta__provincia", "cap_scelto").order_by("pk").iterator():
        street, number, key = address_identity(address.via, address.numero_civico, address.citta_id, address.cap, address.provincia_id, address.regione_id)
        # Keep conflicting legacy territory data exactly as it was. It needs a
        # human decision, not an inferred correction during deployment.
        if address.citta_id and (
            address.provincia_id != address.citta.provincia_id or
            address.regione_id != address.citta.provincia.regione_id or
            (address.cap_scelto_id and (address.cap_scelto.citta_id != address.citta_id or address.cap_scelto.codice != address.cap))
        ):
            key = None
        if key and key in canonical:
            target = canonical[key]
            original = {field.attname: getattr(address, field.attname) for field in Address._meta.concrete_fields}
            for field in ("latitudine", "longitudine"):
                if original[field] is not None:
                    original[field] = str(original[field])
            links = []
            for model, field in references:
                records = model.objects.using(alias).filter(**{field.attname: address.pk})
                ids = list(records.values_list("pk", flat=True))
                if ids:
                    links.append({"model": model._meta.label_lower, "field": field.attname, "ids": ids})
                    records.update(**{field.attname: target})
            Archive.objects.using(alias).update_or_create(originale_id=address.pk, defaults={"canonico_id": target, "dati": original, "relazioni": links})
            if any(model.objects.using(alias).filter(**{field.attname: address.pk}).exists() for model, field in references):
                raise RuntimeError("Un indirizzo duplicato conserva relazioni: migrazione annullata.")
            # No cascades are allowed: only this now-unreferenced duplicate row.
            with schema_editor.connection.cursor() as cursor:
                cursor.execute(f"DELETE FROM {schema_editor.quote_name(Address._meta.db_table)} WHERE id = %s", [address.pk])
        else:
            Address.objects.using(alias).filter(pk=address.pk).update(via_normalizzata=street, civico_normalizzato=number, chiave_normalizzata=key)
            if key:
                canonical[key] = address.pk


def seed_family_settings(apps, schema_editor):
    alias = schema_editor.connection.alias
    Student = apps.get_model("anagrafica", "Studente")
    Relative = apps.get_model("anagrafica", "Familiare")
    Link = apps.get_model("anagrafica", "StudenteFamiliare")
    Residence = apps.get_model("anagrafica", "ResidenzaFamiglia")
    Contact = apps.get_model("anagrafica", "AnagraficaIndirizzo")
    ContentType = apps.get_model("contenttypes", "ContentType")
    nodes = {}
    for student in Student.objects.using(alias).all():
        nodes[("studente", student.pk)] = (student.indirizzo_id, student.residenza_famiglia_id, None)
    for relative in Relative.objects.using(alias).select_related("persona").all():
        nodes[("familiare", relative.pk)] = (relative.persona.indirizzo_id, relative.residenza_famiglia_id, relative.persona_id)
    types = dict(ContentType.objects.using(alias).filter(app_label="anagrafica").values_list("id", "model"))
    principal = {}
    for contact in Contact.objects.using(alias).order_by("-principale", "ordine", "pk"):
        principal.setdefault((types.get(contact.content_type_id), contact.object_id), contact.indirizzo_id)
    graph = defaultdict(set)
    for student_id, relative_id in Link.objects.using(alias).filter(attivo=True).values_list("studente_id", "familiare_id"):
        a, b = ("studente", student_id), ("familiare", relative_id)
        graph[a].add(b)
        graph[b].add(a)
    seen = set()
    for node in nodes:
        if node in seen:
            continue
        pending, component = [node], set()
        while pending:
            item = pending.pop()
            if item in component:
                continue
            component.add(item)
            pending.extend(graph[item] - component)
        seen.update(component)
        # Idempotence: existing settings are never re-derived or overwritten.
        if any(nodes[item][1] for item in component):
            continue
        addresses = []
        for item in component:
            own, _, person_id = nodes[item]
            selected = principal.get(("persona", person_id)) if person_id else None
            selected = selected or principal.get(item) or own
            if selected:
                addresses.append(selected)
        counts = Counter(addresses)
        main = sorted(counts, key=lambda pk: (-counts[pk], pk))[0] if counts else None
        residence = Residence.objects.using(alias).create(indirizzo_principale_id=main)
        Student.objects.using(alias).filter(pk__in=[pk for kind, pk in component if kind == "studente"]).update(residenza_famiglia_id=residence.pk)
        Relative.objects.using(alias).filter(pk__in=[pk for kind, pk in component if kind == "familiare"]).update(residenza_famiglia_id=residence.pk)


class Migration(migrations.Migration):
    dependencies = [
        ("anagrafica", "0008_shared_addresses"),
        ("sistema", "0013_sistemaruolopermessi_permessi_pagine"),
        ("gestione_amministrativa", "0010_alter_bustapagadipendente_mese"),
    ]
    operations = [
        migrations.RunPython(consolidate_addresses),
        migrations.AddConstraint(model_name="indirizzo", constraint=models.UniqueConstraint(fields=["chiave_normalizzata"], name="unique_indirizzo_normalizzato")),
        migrations.RunPython(seed_family_settings),
    ]
