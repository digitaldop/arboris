from datetime import date
from decimal import Decimal

from django.test import SimpleTestCase, TestCase

from anagrafica.models import Familiare, StudenteFamiliare
from .models import PropostaRiconciliazione, RiconciliazioneRataMovimento
from .reconciliation import analyse_request, decide_proposal
from .reconciliation_periods import rate_period_evidence
from .reconciliation_presentation import review_page
from .services import trova_rate_candidate, trova_movimenti_candidati_per_rate
from .test_reconciliation_interface import InterfaceFixtures


class PeriodEvidenceTests(SimpleTestCase):
    def evidence(self, year, month, description, movement_date=date(2026, 9, 14), due_date=None):
        return rate_period_evidence(year=year, month=month, due_date=due_date or date(year, month, 10),
                                    movement_date=movement_date, description=description)

    def test_explicit_month_and_year_override_booking_date(self):
        for description in ("Retta Settembre 26", "Retta settembre 2026", "Retta SETTEMBRE del 2026"):
            with self.subTest(description=description):
                self.assertEqual(self.evidence(2026, 9, description, date(2026, 11, 14))[0], 100)
                self.assertLess(self.evidence(2026, 11, description, date(2026, 11, 14))[0], 90)
                self.assertLess(self.evidence(2025, 9, description)[0], 90)

    def test_yearless_arrears_cross_new_year_and_multiple_months(self):
        self.assertEqual(self.evidence(2025, 12, "Retta dicembre", date(2026, 1, 10))[0], 100)
        self.assertEqual(self.evidence(2026, 9, "Settembre e ottobre 2026")[0], 100)
        self.assertEqual(self.evidence(2026, 10, "Settembre e ottobre 2026")[0], 100)

    def test_no_period_uses_reference_month_then_due_date_distance(self):
        september = self.evidence(2026, 9, "Retta alunno")
        november = self.evidence(2026, 11, "Retta alunno")
        self.assertGreater(september[0], november[0])
        self.assertLess(september[1], november[1])
        # The reference month is independent of a postponed due date.
        self.assertEqual(self.evidence(2026, 9, "Settembre 26", due_date=date(2026, 11, 10))[0], 100)

    def test_month_words_are_not_substrings_and_amount_is_not_a_year(self):
        self.assertLess(self.evidence(2026, 11, "Novembretti")[0], 100)
        self.assertEqual(self.evidence(2026, 9, "Retta settembre 350 euro")[0], 100)


class TuitionPeriodMatchingTests(InterfaceFixtures, TestCase):
    def test_named_student_and_parent_do_not_saturate_future_rates(self):
        rate = self.rate()
        other = self.next_rate(rate, 3, 11)
        relative = Familiare.objects.create(nome="Paola", cognome="Rossi")
        StudenteFamiliare.objects.create(studente=rate.iscrizione.studente, familiare=relative)
        movement = self.movement(description="Da Paola Rossi per Settembre 26 Luca Bianchi")
        forward = trova_rate_candidate(movement)
        self.assertEqual([c.rata.pk for c in forward], [rate.pk, other.pk])
        self.assertGreater(forward[0].score_percentuale, forward[1].score_percentuale)
        reverse_september = trova_movimenti_candidati_per_rate(rate, [rate])[0]
        reverse_november = trova_movimenti_candidati_per_rate(other, [other])[0]
        self.assertGreater(reverse_september.score_percentuale, reverse_november.score_percentuale)
        # Analyse from the target first, then from the movement: same selection.
        for kind, pk in (("rata", other.pk), ("movimento", movement.pk)):
            analyse_request(kind, pk)
            _, groups = review_page(self.pending(), 1)
            self.assertEqual(len(groups), 1)
            self.assertEqual(groups[0]["proposte"][0].allocazioni[0]["target_id"], rate.pk)
        self.assertFalse(RiconciliazioneRataMovimento.objects.exists())

    def test_assisted_options_include_all_unpaid_rates_and_smaller_residuals(self):
        rate = self.rate()
        for index in range(15):
            self.next_rate(rate, index + 2, index % 12 + 1, 2027 + index // 12)
        partial = self.next_rate(rate, 30, 9, 2026, amount=60)
        partial.importo_pagato = Decimal("20")
        partial.save()
        paid = self.next_rate(rate, 31, 10, 2026)
        paid.pagata = True
        paid.importo_pagato = 100
        paid.save()
        movement = self.movement(description="Retta settembre 26 Luca Bianchi")
        analyse_request("movimento", movement.pk)
        singles = [p for p in self.pending() if len(p.allocazioni) == 1]
        targets = {p.allocazioni[0]["target_id"]: p.allocazioni[0]["importo"] for p in singles}
        self.assertEqual(len(targets), 17)
        self.assertEqual(targets[partial.pk], "40.00")
        self.assertNotIn(paid.pk, targets)
        _, groups = review_page(self.pending(), 1)
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0]["proposte"][0].allocazioni[0]["target_id"], rate.pk)

    def test_reanalysis_updates_open_scores_but_preserves_rejections(self):
        rate = self.rate()
        other = self.next_rate(rate, 3, 11)
        movement = self.movement(description="Settembre 26 Luca Bianchi")
        analyse_request("movimento", movement.pk)
        old = next(p for p in self.pending() if p.allocazioni[0]["target_id"] == other.pk)
        PropostaRiconciliazione.objects.filter(pk=old.pk).update(compatibilita=100, motivazioni=[])
        analyse_request("movimento", movement.pk)
        old.refresh_from_db()
        self.assertLess(old.compatibilita, 100)
        decide_proposal(old.pk, "rifiuta", user=self.user)
        analyse_request("movimento", movement.pk)
        old.refresh_from_db()
        self.assertEqual(old.stato, "rifiutata")
