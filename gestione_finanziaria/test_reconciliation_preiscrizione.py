from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from anagrafica.models import Familiare, StudenteFamiliare
from economia.models import RataIscrizione
from .models import RiconciliazioneRataMovimento
from .reconciliation import analyse_request
from .reconciliation_periods import rate_movement_evidence
from .reconciliation_presentation import review_page
from .services import trova_rate_candidate, trova_movimenti_candidati_per_rate
from .test_reconciliation_interface import InterfaceFixtures


class EnrollmentEvidenceTests(SimpleTestCase):
    def evidence(self, description, *, enrollment=True):
        rate = SimpleNamespace(
            tipo_rata="preiscrizione" if enrollment else "mensile",
            anno_riferimento=2026, mese_riferimento=1 if enrollment else 9,
            data_scadenza=None if enrollment else date(2026, 9, 10),
        )
        movement = SimpleNamespace(descrizione=description, data_contabile=date(2026, 9, 15))
        return rate_movement_evidence(rate, movement)

    def test_enrollment_wording_recognized_without_a_due_date(self):
        for description in (
            "Quota iscrizione anno scolastico 2026-2027",
            "Quota di iscrizione", "PREISCRIZIONE", "Pre-iscrizione", "pre iscrizione",
        ):
            with self.subTest(description=description):
                self.assertEqual(self.evidence(description)[0], 100)
                self.assertLess(self.evidence(description, enrollment=False)[0], 75)

    def test_month_does_not_turn_enrollment_into_monthly_tuition(self):
        description = "Preiscrizione settembre 2026"
        self.assertGreater(self.evidence(description)[0], self.evidence(description, enrollment=False)[0])

    def test_mixed_payment_still_allows_monthly_tuition(self):
        for description in ("Preiscrizione e retta settembre 26", "Iscrizione e rata settembre 26"):
            with self.subTest(description=description):
                self.assertEqual(self.evidence(description)[0], 100)
                self.assertEqual(self.evidence(description, enrollment=False)[0], 100)

    def test_unrelated_words_do_not_confirm_enrollment(self):
        for description in ("Retta settembre 26", "Bonifico", "Circoscrizione settembre 26"):
            with self.subTest(description=description):
                self.assertLess(self.evidence(description)[0], 100)
                self.assertGreater(self.evidence(description, enrollment=False)[0], self.evidence(description)[0])


class EnrollmentReconciliationTests(InterfaceFixtures, TestCase):
    def setUp(self):
        super().setUp()
        self.monthly = self.rate()
        self.monthly.importo_dovuto = self.monthly.importo_finale = Decimal("350")
        self.monthly.save()
        for index in range(1, 12):
            offset = 8 + index
            self.next_rate(self.monthly, index + 1, offset % 12 + 1, 2026 + offset // 12, amount=350)
        self.fee = RataIscrizione.objects.create(
            iscrizione=self.monthly.iscrizione, tipo_rata=RataIscrizione.TIPO_PREISCRIZIONE,
            numero_rata=0, mese_riferimento=1, anno_riferimento=2026,
            descrizione="Preiscrizione AS 2026/2027", data_scadenza=None,
            importo_dovuto=300, importo_finale=300,
        )
        relative = Familiare.objects.create(nome="Paola", cognome="Rossi")
        StudenteFamiliare.objects.create(studente=self.monthly.iscrizione.studente, familiare=relative)

    def enrollment_movement(self, amount="300", description=None):
        return self.movement(amount, description or "BON.DA PAOLA ROSSI Quota iscrizione anno scolastico 2026-2027 nome Bianchi Luca")

    def test_manual_page_includes_fee_first_and_all_twelve_monthly_rates(self):
        movement = self.enrollment_movement()
        response = self.client.get(reverse("riconcilia_movimento", args=[movement.pk]))
        self.assertEqual(response.status_code, 200)
        proposals = response.context["proposte_rate"]
        self.assertEqual(len(proposals), 13)
        self.assertEqual(proposals[0].targets, [self.fee])
        self.assertGreater(proposals[0].score, proposals[1].score)
        self.assertContains(response, "Preiscrizione AS 2026/2027")
        self.assertContains(response, f'name="rata_pk" value="{self.fee.pk}"')
        self.assertFalse(RiconciliazioneRataMovimento.objects.exists())

    def test_manual_page_does_not_truncate_when_causale_is_generic(self):
        movement = self.enrollment_movement(description="BON.DA PAOLA ROSSI per Bianchi Luca")
        response = self.client.get(reverse("riconcilia_movimento", args=[movement.pk]))
        targets = [proposal.targets[0].pk for proposal in response.context["proposte_rate"]]
        self.assertEqual(len(targets), 13)
        self.assertIn(self.fee.pk, targets)

    def test_partial_enrollment_payment_is_ranked_before_monthly_rates(self):
        movement = self.enrollment_movement("100", "Acconto preiscrizione Bianchi Luca")
        candidates = trova_rate_candidate(movement)
        self.assertEqual(candidates[0].rata, self.fee)

    def test_fee_alone_does_not_bypass_student_identity(self):
        movement = self.enrollment_movement(description="Quota iscrizione altro nominativo")
        self.assertEqual(trova_rate_candidate(movement), [])

    def test_enrollment_wording_does_not_raise_fuzzy_identity_to_certainty(self):
        movement = self.enrollment_movement(description="Quota iscrizione Luca Bianci")
        candidates = trova_rate_candidate(movement)
        self.assertEqual(candidates[0].rata, self.fee)
        self.assertTrue(candidates[0].richiede_conferma)
        self.assertLessEqual(candidates[0].score, 84)

    def test_assisted_matching_excludes_paid_enrollment(self):
        self.fee.pagata = True
        self.fee.importo_pagato = Decimal("300")
        self.fee.save()
        movement = self.enrollment_movement()
        analyse_request("movimento", movement.pk)
        targets = {row["target_id"] for proposal in self.pending() for row in proposal.allocazioni}
        self.assertNotIn(self.fee.pk, targets)

    def test_reverse_matching_prefers_explicit_enrollment(self):
        enrollment = self.enrollment_movement()
        self.enrollment_movement(description="Retta settembre 26 Bianchi Luca Paola Rossi")
        candidates = trova_movimenti_candidati_per_rate(self.fee, [self.fee])
        self.assertEqual(candidates[0].movimento, enrollment)
        self.assertGreater(candidates[0].score, candidates[1].score)

    def test_assisted_and_stored_proposals_prefer_enrollment(self):
        movement = self.enrollment_movement()
        analyse_request("movimento", movement.pk)
        # Simulate scores saved before recognition of enrollment wording.
        self.pending().update(compatibilita=84)
        _, groups = review_page(self.pending(), 1)
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0]["proposte"][0].allocazioni[0]["target_id"], self.fee.pk)

    def test_confirmation_registers_only_enrollment_fee(self):
        movement = self.enrollment_movement()
        return_url = reverse("lista_movimenti_finanziari")
        response = self.client.post(reverse("riconcilia_movimento", args=[movement.pk]), {
            "azione": "collega", "rata_pk": self.fee.pk, "marca_rata_pagata": "1", "next": return_url,
        })
        self.assertRedirects(response, return_url, fetch_redirect_response=False)
        self.fee.refresh_from_db()
        self.assertTrue(self.fee.pagata)
        self.assertEqual(self.fee.importo_pagato, Decimal("300"))
        self.assertEqual(RiconciliazioneRataMovimento.objects.get().rata_id, self.fee.pk)
        self.assertFalse(RataIscrizione.objects.filter(tipo_rata="mensile", importo_pagato__gt=0).exists())
