from datetime import date
from decimal import Decimal
from unittest.mock import patch

from django.core.cache import cache
from django.db import connection
from django.test import RequestFactory, TestCase
from django.test.utils import CaptureQueriesContext

from anagrafica.family_logic import (
    build_logical_family_snapshot_from_ids,
    count_logical_families_for_students,
    iter_logical_family_snapshots,
)
from anagrafica.models import Familiare, RelazioneFamiliare, Studente, StudenteFamiliare
from anagrafica.views import build_economia_dashboard_data
from economia.models import CondizioneIscrizione, Iscrizione, StatoIscrizione, TariffaCondizioneIscrizione
from economia.read_optimizations import prepare_iscrizioni_for_display
from economia.views.iscrizioni import lista_iscrizioni
from scuola.models import AnnoScolastico
from sistema.audit import audit_logging_disabled


class PageLoadingPerformanceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        with audit_logging_disabled():
            cls.relationship = RelazioneFamiliare.objects.create(relazione="Genitore", ordine=1)
            cls.year = AnnoScolastico.objects.create(
                nome_anno_scolastico="2026/2027", data_inizio=date(2026, 9, 1), data_fine=date(2027, 6, 30),
            )
            cls.status = StatoIscrizione.objects.create(stato_iscrizione="Iscritto", ordine=1)
            cls.condition = CondizioneIscrizione.objects.create(
                anno_scolastico=cls.year, nome_condizione_iscrizione="Standard", numero_mensilita_default=10,
            )
            cls.tariff = TariffaCondizioneIscrizione.objects.create(
                condizione_iscrizione=cls.condition, ordine_figlio_da=1, retta_annuale=Decimal("3000"),
                preiscrizione=Decimal("100"),
            )

    def add_family(self, number):
        with audit_logging_disabled():
            student = Studente.objects.create(
                nome=f"Studente {number}", cognome=f"Famiglia {number}", data_nascita=date(2018, 1, 1),
            )
            relative = Familiare.objects.create(
                nome=f"Genitore {number}", cognome=f"Famiglia {number}", relazione_familiare=self.relationship,
            )
            StudenteFamiliare.objects.create(studente=student, familiare=relative, attivo=True)
            enrollment = Iscrizione.objects.create(
                studente=student, anno_scolastico=self.year, stato_iscrizione=self.status,
                condizione_iscrizione=self.condition, data_iscrizione=date(2026, 9, 1),
            )
        return student, relative, enrollment

    def test_family_queries_do_not_grow_with_number_of_families(self):
        self.add_family(0)
        iter_logical_family_snapshots()  # Warm ContentType's process-local cache.
        with CaptureQueriesContext(connection) as small:
            iter_logical_family_snapshots()
        for number in range(1, 12):
            self.add_family(number)
        with CaptureQueriesContext(connection) as large:
            snapshots = iter_logical_family_snapshots()
        self.assertEqual(len(snapshots), 12)
        self.assertEqual(len(large), len(small), f"1 family: {len(small)} queries; 12 families: {len(large)}")
        self.assertLessEqual(len(large), 6)

    def test_batched_families_match_individual_snapshots_and_transitive_count(self):
        student_a, relative_a, _ = self.add_family(0)
        student_b, relative_b, _ = self.add_family(1)
        student_c, _, _ = self.add_family(2)
        StudenteFamiliare.objects.create(studente=student_b, familiare=relative_a, attivo=True)
        StudenteFamiliare.objects.create(studente=student_c, familiare=relative_b, attivo=False)
        for snapshot in iter_logical_family_snapshots():
            self.assertEqual(snapshot, build_logical_family_snapshot_from_ids(snapshot.student_ids, snapshot.familiare_ids))
        with self.assertNumQueries(1):
            self.assertEqual(count_logical_families_for_students({student_a.pk, student_b.pk, student_c.pk}), 2)
        with self.assertNumQueries(0):
            self.assertEqual(count_logical_families_for_students(set()), 0)

    def test_economy_dashboard_query_budget_and_totals(self):
        self.add_family(0)
        cache.clear()
        with CaptureQueriesContext(connection) as small:
            first = build_economia_dashboard_data(self.year)
        for number in range(1, 12):
            self.add_family(number)
        with CaptureQueriesContext(connection) as large:
            result = build_economia_dashboard_data(self.year)
        self.assertLessEqual(len(large), len(small), f"1 enrollment: {len(small)} queries; 12: {len(large)}")
        self.assertLessEqual(len(large), 8)
        self.assertEqual(result["totale_rette_annuo"], first["totale_rette_annuo"] * 12)
        self.assertEqual(result["totale_rette_annuo"], Decimal("36000"))
        self.assertEqual(result["totale_preiscrizioni"], Decimal("1200"))

    def test_batch_tariffs_preserve_direct_kinship_order_and_inactive_enrollments(self):
        student_a, relative_a, enrollment_a = self.add_family(0)
        student_b, relative_b, enrollment_b = self.add_family(1)
        student_c, _, enrollment_c = self.add_family(2)
        StudenteFamiliare.objects.create(studente=student_b, familiare=relative_a, attivo=True)
        StudenteFamiliare.objects.create(studente=student_c, familiare=relative_b, attivo=True)
        Iscrizione.objects.filter(pk=enrollment_a.pk).update(attiva=False)
        Studente.objects.filter(pk=student_c.pk).update(attivo=False, data_nascita=None)
        self.tariff.ordine_figlio_a = 1
        self.tariff.save()
        TariffaCondizioneIscrizione.objects.create(
            condizione_iscrizione=self.condition, ordine_figlio_da=2, retta_annuale=Decimal("2400"),
        )
        queryset = Iscrizione.objects.select_related("condizione_iscrizione", "studente", "anno_scolastico")
        expected = {item.pk: (item.get_ordine_figlio(), item.get_tariffa_applicabile().pk) for item in queryset}
        enrollments = list(queryset.all())
        prepare_iscrizioni_for_display(enrollments)
        with self.assertNumQueries(0):
            actual = {item.pk: (item.get_ordine_figlio(), item.get_tariffa_applicabile().pk) for item in enrollments}
        self.assertEqual(actual, expected)

    def test_enrollment_list_counts_rates_in_one_query(self):
        for number in range(3):
            self.add_family(number)
        request = RequestFactory().get("/iscrizioni/")
        with patch("economia.views.iscrizioni.render", side_effect=lambda request, template, context: context):
            with self.assertNumQueries(1):
                context = lista_iscrizioni(request)
                self.assertEqual([item.count_rate for item in context["iscrizioni"]], [0, 0, 0])
