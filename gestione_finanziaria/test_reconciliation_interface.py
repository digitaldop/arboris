from concurrent.futures import ThreadPoolExecutor
from datetime import date
from unittest.mock import patch

from django.db import connections, transaction
from django.test import TestCase, TransactionTestCase
from django.urls import reverse

from economia.models import RataIscrizione
from .models import (
    DecisionePropostaRiconciliazione, PropostaRiconciliazione,
    RiconciliazioneRataMovimento, StatoAnalisiRiconciliazione,
)
from .reconciliation import _describe, _hash, decide_proposal, invalidate_changed
from .reconciliation_presentation import review_page
from .test_reconciliation_review import ReviewFixtures


class InterfaceFixtures(ReviewFixtures):
    def next_rate(self, rate, number=2, month=10, year=2026, amount=100):
        return RataIscrizione.objects.create(
            iscrizione=rate.iscrizione, numero_rata=number, mese_riferimento=month, anno_riferimento=year,
            data_scadenza=date(year, month, 10), importo_dovuto=amount, importo_finale=amount,
        )

    def proposal(self, rate, movement, *, score=90, extra_rows=()):
        rows = [{"movimento_id": movement.pk, "target_tipo": "rata", "target_id": rate.pk, "importo": "100.00"}, *extra_rows]
        snapshot, _ = _describe(rows)
        return PropostaRiconciliazione.objects.create(
            chiave=_hash([rows, snapshot]), abbinamento=_hash(rows), caso="same-case",
            ambito="rate", compatibilita=score, allocazioni=rows, dati_verifica=snapshot,
            motivazioni=["Importo corrispondente", "Nominativo corrispondente"],
        )


class ReconciliationInterfaceTests(InterfaceFixtures, TestCase):
    def test_tuition_alternatives_are_grouped_by_movement_and_sorted_by_score(self):
        rate = self.rate()
        movement = self.movement(description="Retta settembre")
        low = self.proposal(self.next_rate(rate), movement, score=45)
        high = self.proposal(rate, movement, score=96)
        response = self.client.get(reverse("proposte_riconciliazione"), {"popup": "1"})
        self.assertEqual(response.status_code, 200)
        groups = response.context["gruppi"]
        self.assertEqual(len(groups), 1)
        self.assertEqual([p.pk for p in groups[0]["proposte"]], [high.pk, low.pk])
        self.assertContains(response, "data-proposal-choice", count=1)
        self.assertContains(response, "96/100")
        self.assertContains(response, "Bassa · 45/100")
        self.assertContains(response, "review-scale-gradient")
        html = response.content.decode()
        self.assertLess(html.index('class="review-movements"'), html.index('class="review-targets"'))
        self.assertContains(response, "Rata da riconciliare")
        self.assertContains(response, "Settembre 2026")

    def test_pagination_keeps_all_twenty_one_candidates_in_one_row(self):
        rate = self.rate()
        movement = self.movement()
        for index in range(21):
            alternative = self.next_rate(rate, number=index + 2, month=index % 12 + 1, year=2026 + index // 12)
            self.proposal(alternative, movement, score=100 - index)
        page, groups = review_page(self.pending(), 1)
        self.assertEqual(page.paginator.num_pages, 1)
        self.assertEqual(page.paginator.count, 1)
        self.assertEqual(len(groups[0]["proposte"]), 21)

    def test_cumulative_allocations_stay_together_and_do_not_merge_with_single_rate(self):
        rate = self.rate()
        other = RataIscrizione.objects.create(
            iscrizione=rate.iscrizione, numero_rata=2, mese_riferimento=10, anno_riferimento=2026,
            data_scadenza=date(2026, 10, 10), importo_dovuto=100,
        )
        self.proposal(rate, self.movement())
        movement = self.movement("200")
        cumulative = self.proposal(rate, movement, extra_rows=[{
            "movimento_id": movement.pk, "target_tipo": "rata", "target_id": other.pk, "importo": "100.00",
        }])
        page, groups = review_page(self.pending(), 1)
        self.assertEqual(page.paginator.count, 2)
        prepared = next(p for group in groups for p in group["proposte"] if p.pk == cumulative.pk)
        self.assertEqual(len(prepared.destinazioni), 2)
        self.assertEqual(len(prepared.movimenti), 1)
        self.assertEqual(prepared.totale_centesimi, 20000)
        self.assertEqual(prepared.movimenti[0]["residuo_successivo"], 0)

    def test_json_rejects_all_row_alternatives_without_redirect_or_payments(self):
        rate = self.rate()
        proposals = [self.proposal(rate, self.movement()) for _ in range(2)]
        response = self.client.post(reverse("decidi_proposte_riconciliazione"), {
            "azione": "rifiuta", "ambito": "rate", "proposte": [p.pk for p in proposals],
        }, HTTP_ACCEPT="application/json")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(all(item["success"] for item in response.json()["results"]))
        self.assertEqual(self.pending().count(), 0)
        self.assertEqual(DecisionePropostaRiconciliazione.objects.filter(azione="rifiuta", utente=self.user).count(), 2)
        self.assertFalse(RiconciliazioneRataMovimento.objects.exists())

    def test_rejection_retry_is_idempotent_and_does_not_run_matching_or_regroup(self):
        proposal = self.proposal(self.rate(), self.movement())
        with patch("gestione_finanziaria.reconciliation.regroup_cases", side_effect=AssertionError("Must not regroup")):
            with patch("gestione_finanziaria.reconciliation._describe", side_effect=AssertionError("Must not inspect balances")):
                for _ in range(2):
                    self.assertTrue(decide_proposal(proposal.pk, "rifiuta", user=self.user)[0])
        self.assertEqual(DecisionePropostaRiconciliazione.objects.filter(proposta=proposal).count(), 1)

    def test_stale_analysis_does_not_overwrite_a_rejection(self):
        proposal = self.proposal(self.rate(), self.movement())

        def reject_while_describing(*args, **kwargs):
            decide_proposal(proposal.pk, "rifiuta", user=self.user)
            return {}, []

        with patch("gestione_finanziaria.reconciliation._describe", side_effect=reject_while_describing):
            invalidate_changed(PropostaRiconciliazione.objects.filter(pk=proposal.pk))
        proposal.refresh_from_db()
        self.assertEqual(proposal.stato, "rifiutata")

    def test_json_invalid_selection_does_not_reject_valid_records(self):
        proposal = self.proposal(self.rate(), self.movement())
        url = reverse("decidi_proposte_riconciliazione")
        response = self.client.post(url, {"ambito": "rate", "azione": "rifiuta", "proposte": [proposal.pk, "bad"]}, HTTP_ACCEPT="application/json")
        self.assertEqual(response.status_code, 400)
        self.assertTrue(response.json()["errors"])
        self.assertEqual(self.pending().count(), 1)

    def test_json_rejection_still_checks_permissions(self):
        from django.contrib.auth.models import User
        from sistema.models import SistemaUtentePermessi

        proposal = self.proposal(self.rate(), self.movement())
        user = User.objects.create_user(username="review-no-permission")
        SistemaUtentePermessi.objects.create(user=user, permesso_economia="view")
        self.client.force_login(user)
        response = self.client.post(reverse("decidi_proposte_riconciliazione"), {
            "ambito": "rate", "azione": "rifiuta", "proposta": proposal.pk,
        }, HTTP_ACCEPT="application/json")
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.pending().count(), 1)

    def test_plain_form_submission_rejects_a_row_without_javascript(self):
        rate = self.rate()
        first = self.proposal(rate, self.movement())
        second = self.proposal(rate, self.movement())
        response = self.client.post(reverse("decidi_proposte_riconciliazione"), {
            "ambito": "rate", "decisione": f"rifiuta:{first.pk},{second.pk}", "popup": "1",
        })
        self.assertEqual(response.status_code, 302)
        self.assertIn("popup=1", response.url)
        self.assertFalse(self.pending().exists())

    def test_dropdown_selected_confirmation_records_only_that_candidate(self):
        rate = self.rate()
        other = self.next_rate(rate)
        movement = self.movement()
        first = self.proposal(rate, movement)
        second = self.proposal(other, movement)
        response = self.client.post(reverse("decidi_proposte_riconciliazione"), {
            "ambito": "rate", "decisione": f"conferma:{second.pk}", "proposte": [first.pk],
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(RiconciliazioneRataMovimento.objects.get().movimento_id, second.allocazioni[0]["movimento_id"])
        self.assertEqual(RiconciliazioneRataMovimento.objects.get().rata_id, other.pk)
        rate.refresh_from_db()
        self.assertFalse(rate.pagata)

    def test_old_full_score_proposals_preselect_september_before_november(self):
        rate = self.rate()
        movement = self.movement(description="Settembre 26 Luca Bianchi")
        september = self.proposal(rate, movement, score=100)
        november = self.proposal(self.next_rate(rate, 3, 11), movement, score=100)
        response = self.client.get(reverse("proposte_riconciliazione"))
        options = response.context["gruppi"][0]["proposte"]
        self.assertEqual([p.pk for p in options], [september.pk, november.pk])
        self.assertLess(options[1].compatibilita, options[0].compatibilita)
        self.assertEqual(len(response.context["gruppi"]), 1)
        # Presentation must not alter confirmation snapshots or stored history.
        november.refresh_from_db()
        self.assertEqual(november.compatibilita, 100)
        self.assertTrue(decide_proposal(september.pk, "conferma", user=self.user)[0])

    def test_different_movements_have_separate_rows_and_paginate(self):
        rate = self.rate()
        for _ in range(21):
            self.proposal(rate, self.movement())
        page, groups = review_page(self.pending(), 1)
        self.assertEqual(page.paginator.count, 21)
        self.assertEqual(page.paginator.num_pages, 2)
        self.assertEqual(len(groups), 20)

    def test_same_movement_cumulative_option_preserves_all_allocations(self):
        rate = self.rate()
        other = self.next_rate(rate)
        movement = self.movement("200")
        self.proposal(rate, movement)
        cumulative = self.proposal(rate, movement, extra_rows=[{
            "movimento_id": movement.pk, "target_tipo": "rata", "target_id": other.pk, "importo": "100.00",
        }])
        _, groups = review_page(self.pending(), 1)
        self.assertEqual(len(groups), 1)
        prepared = next(p for p in groups[0]["proposte"] if p.pk == cumulative.pk)
        self.assertEqual(len(prepared.destinazioni), 2)
        self.assertEqual(prepared.totale_centesimi, 20000)
        self.assertTrue(decide_proposal(cumulative.pk, "conferma", user=self.user)[0])
        self.assertEqual(RiconciliazioneRataMovimento.objects.count(), 2)

    def test_supplier_alternatives_still_group_by_deadline(self):
        deadline = self.deadline()
        for score in (96, 45):
            movement = self.movement("-100", "Aurora Servizi SRL")
            rows = [{"movimento_id": movement.pk, "target_tipo": "scadenza_fornitore", "target_id": deadline.pk, "importo": "100.00"}]
            snapshot, _ = _describe(rows)
            PropostaRiconciliazione.objects.create(
                chiave=_hash([rows, snapshot]), abbinamento=_hash(rows), caso="supplier",
                ambito="fornitore", compatibilita=score, allocazioni=rows, dati_verifica=snapshot,
            )
        response = self.client.get(reverse("proposte_riconciliazione"), {"ambito": "fornitore"})
        self.assertEqual(len(response.context["gruppi"]), 1)
        self.assertEqual([p.compatibilita for p in response.context["gruppi"][0]["proposte"]], [96, 45])
        html = response.content.decode()
        self.assertLess(html.index('class="review-targets"'), html.index('class="review-movements"'))


class ReconciliationRejectionConcurrencyTests(InterfaceFixtures, TransactionTestCase):
    def test_rejection_finishes_while_worker_holds_global_analysis_lock(self):
        proposal = self.proposal(self.rate(), self.movement())
        StatoAnalisiRiconciliazione.objects.get_or_create(pk=1)

        def reject():
            connections.close_all()
            try:
                return decide_proposal(proposal.pk, "rifiuta", user=self.user)[0]
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=1) as executor:
            with transaction.atomic():
                StatoAnalisiRiconciliazione.objects.select_for_update().get(pk=1)
                self.assertTrue(executor.submit(reject).result(timeout=5))
        self.assertFalse(RiconciliazioneRataMovimento.objects.exists())
