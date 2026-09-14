from concurrent.futures import ThreadPoolExecutor
from datetime import date
from decimal import Decimal
from threading import Barrier
from unittest.mock import patch
from types import SimpleNamespace

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import connections, transaction
from django.test import TestCase, TransactionTestCase
from django.urls import reverse

from anagrafica.models import Familiare, Studente, StudenteFamiliare
from economia.models import CondizioneIscrizione, Iscrizione, RataIscrizione, StatoIscrizione
from scuola.models import AnnoScolastico
from sistema.models import SistemaUtentePermessi
from .models import (
    ContoBancario, DecisionePropostaRiconciliazione, DocumentoFornitore, Fornitore, MovimentoFinanziario,
    PagamentoFornitore, PropostaRiconciliazione, RichiestaAnalisiRiconciliazione,
    RiconciliazioneRataMovimento, ScadenzaPagamentoFornitore,
)
from .reconciliation import decide_proposal, pending_count, proposals_for_user
from .reconciliation_queue import enqueue_analysis
from .reconciliation_worker import process_pending_analysis


class ReviewFixtures:
    def setUp(self):
        super().setUp()
        self.user = User.objects.create_superuser(username="review-admin", password="test-password")
        self.client.force_login(self.user)

    def movement(self, amount="100.00", description="Retta Luca Bianchi", **kwargs):
        return MovimentoFinanziario.objects.create(
            data_contabile=date(2026, 9, 10), importo=Decimal(amount),
            descrizione=description, **kwargs,
        )

    def rate(self):
        year = AnnoScolastico.objects.create(nome_anno_scolastico="2026/2027", data_inizio=date(2026, 9, 1), data_fine=date(2027, 8, 31))
        condition = CondizioneIscrizione.objects.create(anno_scolastico=year, nome_condizione_iscrizione="Standard", numero_mensilita_default=10)
        state = StatoIscrizione.objects.create(stato_iscrizione="Attiva")
        student = Studente.objects.create(nome="Luca", cognome="Bianchi")
        enrollment = Iscrizione.objects.create(studente=student, anno_scolastico=year, stato_iscrizione=state, condizione_iscrizione=condition)
        return RataIscrizione.objects.create(
            iscrizione=enrollment, numero_rata=1, mese_riferimento=9, anno_riferimento=2026,
            data_scadenza=date(2026, 9, 10), importo_dovuto=100, importo_finale=100,
        )

    def deadline(self):
        supplier = Fornitore.objects.create(denominazione="Aurora Servizi SRL")
        document = DocumentoFornitore.objects.create(fornitore=supplier, numero_documento="FT-100", data_documento=date(2026, 9, 1), totale=100)
        return ScadenzaPagamentoFornitore.objects.create(documento=document, data_scadenza=date(2026, 9, 10), importo_previsto=100)

    def analyse(self):
        process_pending_analysis(limit=200, max_seconds=60)
        self.assertFalse(RichiestaAnalisiRiconciliazione.objects.exclude(errore="").exists())

    def pending(self, kind="rate"):
        return PropostaRiconciliazione.objects.filter(stato="aperta", ambito=kind)


class ReconciliationReviewTests(ReviewFixtures, TestCase):
    def test_relative_details_survive_json_roundtrip_before_confirmation(self):
        rate = self.rate()
        relative = Familiare.objects.create(nome="Paolo", cognome="Bianchi")
        StudenteFamiliare.objects.create(studente=rate.iscrizione.studente, familiare=relative)
        self.movement()
        self.analyse()
        self.assertTrue(decide_proposal(self.pending().get().pk, "conferma", user=self.user)[0])

    def test_remaining_transfer_is_matched_after_a_partial_reconciliation(self):
        from .services import riconcilia_movimento_con_rate

        rate = self.rate()
        second = RataIscrizione.objects.create(iscrizione=rate.iscrizione, numero_rata=2, mese_riferimento=10, anno_riferimento=2026, data_scadenza=date(2026, 10, 10), importo_dovuto=100, importo_finale=100)
        movement = self.movement("200")
        self.analyse()
        riconcilia_movimento_con_rate(movement, [(rate, Decimal("100"))], utente=self.user)
        self.analyse()
        proposal = self.pending().get()
        self.assertEqual(proposal.allocazioni[0]["target_id"], second.pk)
        self.assertEqual(proposal.allocazioni[0]["importo"], "100.00")
        self.assertTrue(decide_proposal(proposal.pk, "conferma", user=self.user)[0])

    def test_ineligible_movements_cannot_crowd_out_a_bank_match(self):
        bank = self.movement()
        for _ in range(35):
            self.movement(valuta="USD")
        self.analyse()
        self.rate()
        self.analyse()
        self.assertEqual(self.pending().get().allocazioni[0]["movimento_id"], bank.pk)

    def test_cumulative_failure_rolls_back_every_allocation(self):
        from .services import riconcilia_movimento_con_rate

        rate = self.rate()
        self.movement("40")
        self.movement("60")
        self.analyse()
        proposal = next(p for p in self.pending() if len(p.allocazioni) == 2)
        attempts = []

        def fail_second(*args, **kwargs):
            attempts.append(1)
            if len(attempts) == 2:
                raise ValidationError("Failure after the first allocation")
            return riconcilia_movimento_con_rate(*args, **kwargs)

        with patch("gestione_finanziaria.services.riconcilia_movimento_con_rate", side_effect=fail_second):
            with self.assertRaises(ValidationError):
                decide_proposal(proposal.pk, "conferma", user=self.user)
        rate.refresh_from_db()
        self.assertEqual(rate.importo_pagato, Decimal("0"))
        self.assertFalse(RiconciliazioneRataMovimento.objects.exists())
        proposal.refresh_from_db()
        self.assertEqual(proposal.stato, "aperta")

    def test_file_import_and_duplicate_import_only_queue_proposals(self):
        from .importers.base import ParsedMovimento
        from .importers.service import importa_movimenti_da_file

        self.rate()
        conto = ContoBancario.objects.create(nome_conto="Conto import")
        parsed = ParsedMovimento(data_contabile=date(2026, 9, 10), importo=Decimal("100"), descrizione="Retta Luca Bianchi")
        parser = SimpleNamespace(parse=lambda raw: [parsed], nome_formato="test")
        first = importa_movimenti_da_file(parser=parser, raw_bytes=b"test", conto=conto, riconcilia_automaticamente=True)
        duplicate = importa_movimenti_da_file(parser=parser, raw_bytes=b"test", conto=conto)
        self.assertEqual((first.inseriti, first.riconciliati, duplicate.duplicati), (1, 0, 1))
        self.analyse()
        self.assertEqual(self.pending().count(), 1)
        self.assertFalse(RiconciliazioneRataMovimento.objects.exists())

    def test_dispatch_runs_only_after_commit(self):
        with patch("gestione_finanziaria.reconciliation_worker.kick_analysis") as kick:
            with self.captureOnCommitCallbacks(execute=True):
                with transaction.atomic():
                    self.movement()
                    self.assertFalse(kick.called)
            self.assertTrue(kick.called)

    def test_new_movement_generates_proposal_without_payment(self):
        rate = self.rate()
        movement = self.movement()
        self.analyse()
        proposal = self.pending().get()
        self.assertEqual(proposal.allocazioni[0]["movimento_id"], movement.pk)
        self.assertFalse(RiconciliazioneRataMovimento.objects.exists())
        rate.refresh_from_db()
        self.assertFalse(rate.pagata)
        self.assertEqual(pending_count(proposals_for_user(self.user)), 1)

    def test_new_rate_finds_preexisting_movement(self):
        self.movement()
        self.analyse()
        self.assertFalse(self.pending().exists())
        self.rate()
        self.analyse()
        self.assertEqual(self.pending().count(), 1)

    def test_new_supplier_deadline_finds_preexisting_movement(self):
        movement = self.movement("-100", "Bonifico Aurora Servizi SRL")
        self.analyse()
        deadline = self.deadline()
        self.analyse()
        proposal = self.pending("fornitore").get()
        self.assertFalse(PagamentoFornitore.objects.exists())
        self.assertTrue(decide_proposal(proposal.pk, "conferma", user=self.user)[0])
        deadline.refresh_from_db()
        self.assertEqual(deadline.importo_pagato, Decimal("100"))
        self.assertEqual(PagamentoFornitore.objects.count(), 1)
        movement.refresh_from_db()
        self.assertEqual(movement.stato_riconciliazione, "riconciliato")

    def test_new_supplier_movement_finds_preexisting_deadline(self):
        self.deadline()
        self.analyse()
        self.movement("-100", "Bonifico Aurora Servizi SRL")
        self.analyse()
        self.assertEqual(self.pending("fornitore").count(), 1)

    def test_confirmation_is_idempotent_and_audited(self):
        rate = self.rate()
        self.movement()
        self.analyse()
        proposal = self.pending().get()
        self.assertTrue(decide_proposal(proposal.pk, "conferma", user=self.user)[0])
        self.assertFalse(decide_proposal(proposal.pk, "conferma", user=self.user)[0])
        self.assertEqual(RiconciliazioneRataMovimento.objects.count(), 1)
        self.assertEqual(DecisionePropostaRiconciliazione.objects.filter(azione="conferma", utente=self.user).count(), 1)
        rate.refresh_from_db()
        self.assertTrue(rate.pagata)

    def test_rejection_survives_reverse_analysis_and_timestamp_changes(self):
        rate = self.rate()
        movement = self.movement()
        self.analyse()
        proposal = self.pending().get()
        decide_proposal(proposal.pk, "rifiuta", user=self.user)
        movement.save(update_fields=["data_aggiornamento"])
        enqueue_analysis("rata", rate.pk)
        self.analyse()
        self.assertFalse(self.pending().exists())
        self.assertEqual(PropostaRiconciliazione.objects.count(), 1)
        decide_proposal(proposal.pk, "riapri", user=self.user)
        self.assertEqual(self.pending().count(), 1)
        self.assertFalse(RiconciliazioneRataMovimento.objects.exists())

    def test_changed_amount_creates_new_version_after_rejection(self):
        rate = self.rate()
        self.movement()
        self.analyse()
        old = self.pending().get()
        decide_proposal(old.pk, "rifiuta", user=self.user)
        rate.importo_dovuto = 150
        rate.save()
        self.analyse()
        self.assertEqual(self.pending().count(), 1)
        self.assertNotEqual(self.pending().get().pk, old.pk)
        old.refresh_from_db()
        self.assertEqual(old.stato, "rifiutata")

    def test_changed_source_prevents_stale_confirmation(self):
        self.rate()
        movement = self.movement()
        self.analyse()
        proposal = self.pending().get()
        movement.importo = Decimal("50")
        movement.save()
        success, message = decide_proposal(proposal.pk, "conferma", user=self.user)
        self.assertFalse(success)
        self.assertIn("aggiornare", message)
        self.assertFalse(RiconciliazioneRataMovimento.objects.exists())
        proposal.refresh_from_db()
        self.assertEqual(proposal.stato, "superata")

    def test_cumulative_payment_can_cover_two_rates(self):
        rate = self.rate()
        second = RataIscrizione.objects.create(iscrizione=rate.iscrizione, numero_rata=2, mese_riferimento=10, anno_riferimento=2026, data_scadenza=date(2026, 10, 10), importo_dovuto=100, importo_finale=100)
        self.movement("200")
        self.analyse()
        proposal = next(p for p in self.pending() if len(p.allocazioni) == 2)
        self.assertTrue(decide_proposal(proposal.pk, "conferma", user=self.user)[0])
        rate.refresh_from_db()
        second.refresh_from_db()
        self.assertTrue(rate.pagata and second.pagata)

    def test_two_movements_can_cover_one_rate(self):
        self.rate()
        self.movement("40")
        self.movement("60")
        self.analyse()
        proposal = next(p for p in self.pending() if len(p.allocazioni) == 2)
        self.assertTrue(decide_proposal(proposal.pk, "conferma", user=self.user)[0])
        self.assertEqual(RiconciliazioneRataMovimento.objects.count(), 2)

    def test_incompatible_batch_is_rejected_before_any_payment(self):
        self.rate()
        self.movement("40")
        self.movement("60")
        self.analyse()
        proposals = [p for p in self.pending() if len(p.allocazioni) == 1]
        self.assertEqual(pending_count(proposals_for_user(self.user)), 1)
        response = self.client.post(reverse("decidi_proposte_riconciliazione"), {"ambito": "rate", "azione": "conferma", "proposte": [p.pk for p in proposals]})
        self.assertEqual(response.status_code, 302)
        self.assertFalse(RiconciliazioneRataMovimento.objects.exists())

    def test_worker_failure_keeps_retryable_job(self):
        movement = self.movement()
        with patch("gestione_finanziaria.reconciliation.analyse_request", side_effect=RuntimeError("test interruption")):
            process_pending_analysis(limit=1)
        job = RichiestaAnalisiRiconciliazione.objects.get(tipo="movimento", oggetto_id=movement.pk)
        self.assertEqual(job.tentativi, 1)
        self.assertTrue(job.errore)

    def test_rolled_back_import_leaves_no_job(self):
        with self.assertRaises(ValueError):
            with transaction.atomic():
                self.movement()
                raise ValueError("rollback")
        self.assertFalse(RichiestaAnalisiRiconciliazione.objects.exists())

    def test_repeated_updates_coalesce_into_one_job(self):
        movement = self.movement()
        for _ in range(3):
            movement.save()
        self.assertEqual(RichiestaAnalisiRiconciliazione.objects.filter(tipo="movimento").count(), 1)

    def test_review_get_does_not_compute_or_record_reconciliation(self):
        self.rate()
        self.movement()
        self.analyse()
        with patch("gestione_finanziaria.services.proposte_riconciliazione_da_movimento", side_effect=AssertionError("GET must not match")):
            response = self.client.get(reverse("proposte_riconciliazione"), {"popup": "1"})
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, "Conferma abbinamento")
            self.assertContains(response, "Rifiuta")
            self.assertEqual(self.client.get(reverse("stato_proposte_riconciliazione")).json()["count"], 1)
        self.assertFalse(RiconciliazioneRataMovimento.objects.exists())

    def test_permissions_apply_to_count_review_and_decision(self):
        self.deadline()
        self.movement("-100", "Bonifico Aurora Servizi SRL")
        self.analyse()
        proposal = self.pending("fornitore").get()
        user = User.objects.create_user(username="economics-only")
        SistemaUtentePermessi.objects.create(user=user, permesso_economia="manage")
        self.client.force_login(user)
        self.assertEqual(self.client.get(reverse("stato_proposte_riconciliazione")).json()["count"], 0)
        self.assertEqual(self.client.get(reverse("proposte_riconciliazione"), {"ambito": "fornitore"}).status_code, 403)
        self.assertEqual(self.client.post(reverse("decidi_proposte_riconciliazione"), {"ambito": "fornitore", "proposta": proposal.pk, "azione": "conferma"}).status_code, 403)
        self.assertFalse(PagamentoFornitore.objects.exists())

    def test_ignored_and_foreign_currency_movements_are_excluded(self):
        self.rate()
        self.movement(stato_riconciliazione="ignorato")
        self.movement(valuta="USD")
        self.analyse()
        self.assertFalse(self.pending().exists())

    def test_pending_count_is_a_single_database_query(self):
        with self.assertNumQueries(1):
            self.assertEqual(pending_count(PropostaRiconciliazione.objects.all()), 0)


class ReconciliationConcurrencyTests(ReviewFixtures, TransactionTestCase):
    def test_simultaneous_confirmations_create_only_one_payment(self):
        self.deadline()
        self.movement("-100", "Bonifico Aurora Servizi SRL")
        self.analyse()
        proposal = self.pending("fornitore").get()
        barrier = Barrier(2)

        def confirm():
            connections.close_all()
            try:
                user = User.objects.get(pk=self.user.pk)
                barrier.wait(timeout=10)
                return decide_proposal(proposal.pk, "conferma", user=user)[0]
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(confirm) for _ in range(2)]
            outcomes = [f.result(timeout=30) for f in futures]
        self.assertEqual(sorted(outcomes), [False, True])
        self.assertEqual(PagamentoFornitore.objects.count(), 1)
