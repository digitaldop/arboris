from concurrent.futures import ThreadPoolExecutor
from importlib import import_module
from threading import Barrier
from unittest.mock import Mock, patch

import requests
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection, connections, transaction
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase, TransactionTestCase, override_settings
from django.urls import reverse

from .address_autocomplete import reconcile_territory
from .address_normalization import normalize_address
from .address_services import get_or_create_normalized_address
from .family_address_services import set_family_address
from .family_logic import build_logical_family_snapshot_from_ids, resolve_logical_family_snapshot
from .forms import FamiliareForm, IndirizzoForm, StudenteForm
from .models import (AnagraficaIndirizzo, CAP, Citta, Familiare, Indirizzo, IndirizzoArchivioMigrazione,
                     LabelIndirizzo, Provincia, Regione, ResidenzaFamiglia, Studente, StudenteFamiliare)


class TerritoryMixin:
    def make_territory(self):
        self.region = Regione.objects.create(nome="Emilia-Romagna")
        self.province = Provincia.objects.create(nome="Bologna", sigla="BO", regione=self.region)
        self.city = Citta.objects.create(nome="Calderara di Reno", provincia=self.province, codice_istat="037009")
        self.cap = CAP.objects.create(codice="40012", citta=self.city)

    def address(self, via="Via Roma", numero_civico="25"):
        return get_or_create_normalized_address(via=via, numero_civico=numero_civico, citta=self.city, cap_scelto=self.cap)[0]

    def form_data(self, **overrides):
        return {"via": "Via Roma", "numero_civico": "25", "citta": self.city.pk, "cap_scelto": self.cap.pk, **overrides}


class SharedAddressTests(TerritoryMixin, TestCase):
    def setUp(self):
        self.make_territory()

    def test_create_and_reuse_case_punctuation_and_combined_address(self):
        original = self.address()
        for street, number in (("via roma,", "25"), ("VIA ROMA", "n. 25"), ("Via Roma 25", ""), ("Via Roma n. 25", "")):
            self.assertEqual(self.address(street, number).pk, original.pk)
        self.assertEqual(Indirizzo.objects.count(), 1)

    def test_distinct_civics_and_suffix_spacing(self):
        ids = {self.address(numero_civico=n).pk for n in ("25", "25/A", "25/B", "27", "25-27", "25 interno 2")}
        self.assertEqual(len(ids), 6)
        self.assertEqual(self.address(numero_civico="25 / a").pk, self.address(numero_civico="25A").pk)
        self.assertNotEqual(normalize_address("Via 25 Aprile", "25"), normalize_address("Via Aprile", "25"))

    def test_constraint_and_bulk_creation_cannot_duplicate(self):
        self.address()
        with self.assertRaises(IntegrityError), transaction.atomic():
            Indirizzo.objects.create(via="VIA ROMA", numero_civico="25", citta=self.city, cap_scelto=self.cap)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Indirizzo.objects.bulk_create([Indirizzo(via="via roma", numero_civico="25", citta=self.city, cap_scelto=self.cap)])

    def test_shared_address_is_immutable_and_change_reassociates(self):
        original = self.address()
        first = Familiare.objects.create(nome="Anna", cognome="Uno", indirizzo=original)
        other = Familiare.objects.create(nome="Mario", cognome="Due", indirizzo=original)
        form = IndirizzoForm(self.form_data(numero_civico="27"), instance=original)
        self.assertTrue(form.is_valid(), form.errors)
        first.indirizzo = form.save()
        first.save()
        original.refresh_from_db(); other.refresh_from_db()
        self.assertEqual(original.numero_civico, "25")
        self.assertEqual(other.indirizzo.pk, original.pk)
        self.assertNotEqual(first.indirizzo.pk, original.pk)
        original.numero_civico = "99"
        with self.assertRaises(ValidationError):
            original.save()
        with self.assertRaises(ValidationError):
            Indirizzo.objects.filter(pk=original.pk).update(via="changed")

    def test_manual_form_reuses_without_provider(self):
        with patch("anagrafica.address_autocomplete.requests.get") as request:
            form = IndirizzoForm(self.form_data())
            self.assertTrue(form.is_valid(), form.errors)
            first = form.save()
            again = IndirizzoForm(self.form_data(via="VIA ROMA"))
            self.assertTrue(again.is_valid(), again.errors)
            self.assertEqual(first.pk, again.save().pk)
            request.assert_not_called()

    def test_manual_cap_not_in_catalog_and_no_new_territories(self):
        form = IndirizzoForm(self.form_data(cap_scelto="", cap="40013"))
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.save().cap, "40013")
        self.assertEqual(CAP.objects.count(), 1)

    def test_foreign_cap_rejected(self):
        other = Citta.objects.create(nome="Bologna", provincia=self.province)
        cap = CAP.objects.create(codice="40100", citta=other)
        with self.assertRaises(ValidationError):
            get_or_create_normalized_address(via="Via Roma", numero_civico="25", citta=self.city, cap_scelto=cap)

    def test_inherited_address_is_not_copied_into_personal_form_initial(self):
        residence = ResidenzaFamiglia.objects.create(indirizzo_principale=self.address())
        student = Studente.objects.create(nome="Luca", cognome="Uno", residenza_famiglia=residence, usa_indirizzo_famiglia=True)
        form = StudenteForm(instance=student)
        self.assertFalse(form["indirizzo"].value())
        self.assertTrue(form["usa_indirizzo_famiglia"].value())

    def test_family_principal_fallback_and_personal_override(self):
        principal, personal = self.address(), self.address(numero_civico="27")
        student = Studente.objects.create(nome="Luca", cognome="Uno")
        relative = Familiare.objects.create(nome="Anna", cognome="Uno", indirizzo=personal)
        StudenteFamiliare.objects.create(studente=student, familiare=relative)
        snapshot = resolve_logical_family_snapshot(f"s-{student.pk}")
        set_family_address(snapshot, principal)
        student.refresh_from_db(); relative.refresh_from_db()
        self.assertEqual(student.indirizzo_effettivo, principal)
        self.assertEqual(relative.indirizzo_effettivo, personal)
        relative.usa_indirizzo_famiglia = True
        relative.save()
        self.assertEqual(relative.indirizzo_effettivo, principal)
        snapshot = resolve_logical_family_snapshot(f"s-{student.pk}")
        self.assertEqual(snapshot.indirizzo_principale, principal)

    def test_secondary_contact_is_preserved_when_using_family(self):
        from django.contrib.contenttypes.models import ContentType
        residence = ResidenzaFamiglia.objects.create(indirizzo_principale=self.address())
        student = Studente.objects.create(nome="Luca", cognome="Uno", residenza_famiglia=residence, usa_indirizzo_famiglia=True)
        other = self.address(numero_civico="27")
        AnagraficaIndirizzo.objects.create(content_type=ContentType.objects.get_for_model(student), object_id=student.pk, indirizzo=other, principale=True, label=LabelIndirizzo.objects.get_or_create(nome="Principale")[0])
        self.assertEqual(student.indirizzo_effettivo, residence.indirizzo_principale)
        student.usa_indirizzo_famiglia = False
        self.assertEqual(student.indirizzo_effettivo, other)

    def test_persona_primary_contact_follows_familiare_address_change(self):
        from .contact_services import sync_principal_contacts
        old, new = self.address(), self.address(numero_civico="27")
        relative = Familiare.objects.create(nome="Anna", cognome="Uno", indirizzo=old)
        sync_principal_contacts(relative.persona, indirizzo=old)
        form = FamiliareForm({"nome": "Anna", "cognome": "Uno", "indirizzo": new.pk}, instance=relative, require_family_relation=False)
        self.assertTrue(form.is_valid(), form.errors)
        saved = form.save()
        saved.refresh_from_db()
        self.assertEqual(saved.indirizzo_effettivo, new)
        self.assertTrue(Indirizzo.objects.filter(pk=old.pk, numero_civico="25").exists())

    def test_first_address_after_family_split_does_not_move_former_members(self):
        residence = ResidenzaFamiglia.objects.create()
        first = Studente.objects.create(nome="A", cognome="Test", residenza_famiglia=residence)
        former = Studente.objects.create(nome="B", cognome="Test", residenza_famiglia=residence)
        first.indirizzo = self.address()
        first.save()
        former.refresh_from_db()
        self.assertIsNone(former.indirizzo_effettivo)
        self.assertNotEqual(first.residenza_famiglia_id, former.residenza_famiglia_id)

    def test_new_relation_inherits_settings_and_split_change_isolated(self):
        principal = self.address()
        student = Studente.objects.create(nome="Luca", cognome="Uno", indirizzo=principal)
        first = Familiare.objects.create(nome="Anna", cognome="Uno", usa_indirizzo_famiglia=True)
        link = StudenteFamiliare.objects.create(studente=student, familiare=first)
        first.refresh_from_db()
        self.assertEqual(first.indirizzo_effettivo, principal)
        link.attivo = False; link.save()
        set_family_address(resolve_logical_family_snapshot(f"s-{student.pk}"), self.address(numero_civico="27"))
        first.refresh_from_db()
        self.assertEqual(first.indirizzo_effettivo, principal)

    def test_incompatible_households_are_not_merged(self):
        first = ResidenzaFamiglia.objects.create(indirizzo_principale=self.address())
        second = ResidenzaFamiglia.objects.create(indirizzo_principale=self.address(numero_civico="27"))
        student = Studente.objects.create(nome="Luca", cognome="Uno", residenza_famiglia=first)
        relative = Familiare.objects.create(nome="Anna", cognome="Uno", residenza_famiglia=second)
        StudenteFamiliare.objects.create(studente=student, familiare=relative)
        snapshot = resolve_logical_family_snapshot(f"s-{student.pk}")
        self.assertTrue(snapshot.indirizzi_principali_in_conflitto)
        self.assertIsNone(snapshot.indirizzo_principale)


@override_settings(GEOAPIFY_API_KEY="unit-test-secret")
class AutocompleteTests(TerritoryMixin, TestCase):
    def setUp(self):
        self.make_territory()
        cache.clear()
        self.user = get_user_model().objects.create_superuser("address-admin", "", "test")
        self.client.force_login(self.user)
        self.url = reverse("address_autocomplete")
        self.result = {"street": "Via Roma", "housenumber": "25", "postcode": "40012", "city": "Calderara di Reno", "county": "Città metropolitana di Bologna", "county_code": "BO", "state": "Emilia-Romagna", "country_code": "it", "formatted": "Via Roma 25, 40012 Calderara di Reno", "lat": 44.5, "lon": 11.2, "place_id": "provider-id"}

    @patch("anagrafica.address_autocomplete.requests.get")
    def test_valid_response_reconciles_existing_territories_and_caches(self, get):
        get.return_value = Mock(json=lambda: {"results": [self.result]})
        response = self.client.get(self.url, {"q": "Via Roma 25", "citta_id": self.city.pk})
        self.assertEqual(response.status_code, 200)
        row = response.json()["results"][0]
        self.assertEqual(row["citta_id"], self.city.pk)
        self.assertEqual(row["cap_id"], self.cap.pk)
        self.assertNotIn("unit-test-secret", response.content.decode())
        self.client.get(self.url, {"q": "Via Roma 25", "citta_id": self.city.pk})
        self.assertEqual(get.call_count, 1)
        self.assertEqual(get.call_args.kwargs["params"]["filter"], "countrycode:it")
        self.assertIn("Calderara", get.call_args.kwargs["params"]["text"])
        form = IndirizzoForm(self.form_data(geoapify_token=row["token"]))
        self.assertTrue(form.is_valid(), form.errors)
        address = form.save()
        self.assertEqual(str(address.latitudine), "44.5000000")
        self.assertEqual(Citta.objects.count(), 1)
        self.assertEqual(CAP.objects.count(), 1)

    @patch("anagrafica.address_autocomplete.requests.get", side_effect=requests.Timeout)
    def test_unavailable_keeps_local_results_and_manual_form(self, get):
        address = self.address()
        response = self.client.get(self.url, {"q": "Via Roma"})
        self.assertTrue(response.json()["unavailable"])
        self.assertEqual(response.json()["results"][0]["id"], address.pk)
        form = IndirizzoForm(self.form_data(numero_civico="27"))
        self.assertTrue(form.is_valid(), form.errors)
        self.assertNotEqual(form.save().pk, address.pk)

    @patch("anagrafica.address_autocomplete.requests.get")
    def test_auth_input_and_short_queries(self, get):
        self.client.logout()
        self.assertEqual(self.client.get(self.url, {"q": "Via Roma"}).status_code, 302)
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(self.url, {"q": "a"}).json()["results"], [])
        self.assertEqual(self.client.get(self.url, {"q": "x" * 201}).status_code, 400)
        self.assertEqual(self.client.get(self.url, {"q": "Via Roma", "citta_id": "oops"}).status_code, 400)
        get.assert_not_called()

    @patch("anagrafica.address_autocomplete.requests.get")
    def test_malformed_provider_data_and_rate_limit(self, get):
        get.return_value = Mock(json=lambda: {"results": "invalid"})
        self.assertTrue(self.client.get(self.url, {"q": "Via Roma"}).json()["unavailable"])
        cache.set(f"address-autocomplete-rate:{self.user.pk}", 30, 60)
        self.assertEqual(self.client.get(self.url, {"q": "Via Verdi"}).status_code, 429)
        self.assertEqual(get.call_count, 1)

    @patch("anagrafica.address_autocomplete.requests.get")
    def test_manually_changed_selection_does_not_keep_old_coordinates(self, get):
        get.return_value = Mock(json=lambda: {"results": [self.result]})
        token = self.client.get(self.url, {"q": "Via Roma"}).json()["results"][0]["token"]
        form = IndirizzoForm(self.form_data(numero_civico="27", geoapify_token=token))
        self.assertTrue(form.is_valid(), form.errors)
        self.assertIsNone(form.save().latitudine)

    def test_admin_add_reuses_existing_address_and_blocks_direct_edit(self):
        address = self.address()
        response = self.client.post(reverse("admin:anagrafica_indirizzo_add"), self.form_data())
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Indirizzo.objects.count(), 1)
        response = self.client.post(reverse("admin:anagrafica_indirizzo_change", args=[address.pk]), self.form_data(numero_civico="27"))
        self.assertEqual(response.status_code, 403)

    def test_ambiguous_or_conflicting_city_is_not_created_or_guessed(self):
        city, cap = reconcile_territory({**self.result, "city": "Comune di Calderara di Reno"})
        self.assertEqual(city, self.city)
        self.assertEqual(cap, self.cap)
        self.assertEqual(reconcile_territory({**self.result, "city": "Calderara di Rena"}), (None, None))
        self.assertEqual(reconcile_territory({**self.result, "county_code": "MI"}), (None, None))

    def test_edit_view_changes_only_selected_association_and_ignores_force_duplicate(self):
        address = self.address()
        response = self.client.post(reverse("crea_indirizzo"), self.form_data(force_new_address="1"))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Indirizzo.objects.count(), 1)
        response = self.client.post(reverse("modifica_indirizzo", args=[address.pk]), self.form_data(numero_civico="27", popup="1"))
        self.assertEqual(response.status_code, 200)
        address.refresh_from_db()
        self.assertEqual(address.numero_civico, "25")

    def test_delete_rejects_secondary_contact_and_family_references(self):
        address = self.address()
        ResidenzaFamiglia.objects.create(indirizzo_principale=address)
        response = self.client.post(reverse("elimina_indirizzo", args=[address.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Indirizzo.objects.filter(pk=address.pk).exists())

    def test_family_address_page_saves_new_association(self):
        student = Studente.objects.create(nome="Luca", cognome="Uno")
        url = reverse("famiglia_indirizzo", args=[f"s-{student.pk}"])
        self.assertContains(self.client.get(url), "Cerca indirizzo")
        self.assertEqual(self.client.post(url, self.form_data()).status_code, 302)
        student.refresh_from_db()
        self.assertEqual(student.indirizzo_effettivo.numero_civico, "25")


class MigrationAddressTests(TerritoryMixin, TestCase):
    def test_consolidation_preserves_all_relations_and_is_idempotent(self):
        self.make_territory()
        executor = MigrationExecutor(connection)
        apps = executor.loader.project_state([("anagrafica", "0009_normalize_and_share_addresses")]).apps
        Address = apps.get_model("anagrafica", "Indirizzo")
        first = Address.objects.create(via="Via Roma", numero_civico="25", citta_id=self.city.pk, cap_scelto_id=self.cap.pk, cap="40012", provincia_id=self.province.pk, regione_id=self.region.pk)
        duplicate = Address.objects.create(via="VIA ROMA,", numero_civico="n. 25", citta_id=self.city.pk, cap_scelto_id=self.cap.pk, cap="40012", provincia_id=self.province.pk, regione_id=self.region.pk)
        unknown = Address.objects.create(via="Via Roma", numero_civico="25")
        Student = apps.get_model("anagrafica", "Studente")
        student = Student.objects.create(nome="Test", cognome="Test", indirizzo_id=duplicate.pk)
        School = apps.get_model("sistema", "Scuola")
        school = School.objects.create(nome_scuola="Test", indirizzo_sede_legale_id=duplicate.pk)
        Person = apps.get_model("anagrafica", "Persona")
        person = Person.objects.create(nome="Anna", cognome="Test", indirizzo_id=duplicate.pk)
        Contact = apps.get_model("anagrafica", "AnagraficaIndirizzo")
        Type = apps.get_model("contenttypes", "ContentType")
        Label = apps.get_model("anagrafica", "LabelIndirizzo")
        contact = Contact.objects.create(content_type=Type.objects.get_or_create(app_label="anagrafica", model="studente")[0], object_id=student.pk, indirizzo_id=duplicate.pk, label=Label.objects.get_or_create(nome="Principale")[0], principale=True)
        migration = import_module("anagrafica.migrations.0009_normalize_and_share_addresses")
        with connection.schema_editor() as editor:
            migration.consolidate_addresses(apps, editor)
            migration.seed_family_settings(apps, editor)
            migration.consolidate_addresses(apps, editor)
            migration.seed_family_settings(apps, editor)
        student.refresh_from_db(); school.refresh_from_db()
        self.assertEqual(student.indirizzo_id, first.pk)
        self.assertEqual(school.indirizzo_sede_legale_id, first.pk)
        person.refresh_from_db(); contact.refresh_from_db()
        self.assertEqual(person.indirizzo_id, first.pk)
        self.assertEqual(contact.indirizzo_id, first.pk)
        self.assertTrue(Address.objects.filter(pk=unknown.pk).exists())
        self.assertFalse(Address.objects.filter(pk=duplicate.pk).exists())
        archive = IndirizzoArchivioMigrazione.objects.get(originale_id=duplicate.pk)
        self.assertEqual(archive.dati["via"], "VIA ROMA,")
        self.assertEqual(len(archive.relazioni), 4)
        self.assertEqual(ResidenzaFamiglia.objects.count(), 1)


class AddressConcurrencyTests(TerritoryMixin, TransactionTestCase):
    def test_two_connections_create_one_address(self):
        if connection.vendor != "postgresql":
            self.skipTest("PostgreSQL concurrency test")
        self.make_territory()
        barrier = Barrier(2)
        city_id, cap_id = self.city.pk, self.cap.pk

        def create():
            try:
                barrier.wait(timeout=10)
                address, _ = get_or_create_normalized_address(via="Via Roma", numero_civico="25", citta_id=city_id, cap_scelto_id=cap_id)
                return address.pk
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as pool:
            ids = list(pool.map(lambda _: create(), range(2)))
        self.assertEqual(ids[0], ids[1])
        self.assertEqual(Indirizzo.objects.count(), 1)
