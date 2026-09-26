from decimal import Decimal

from django.test import TestCase, TransactionTestCase
from django.urls import reverse

from anagrafica.models import Studente
from economia.models import Iscrizione, RataIscrizione
from .models import RiconciliazioneRataMovimento, StatoRiconciliazione
from .services import importo_movimento_disponibile, riconcilia_movimento_con_rate
from .test_reconciliation_interface import InterfaceFixtures


class MixedTuitionPaymentTests(InterfaceFixtures, TestCase):
    def setUp(self):
        super().setUp()
        self.tuition = self.rate()
        self.tuition.importo_dovuto = Decimal("350.00")
        self.tuition.save()
        self.transfer = self.movement("425", "Retta settembre 2026 e servizio aggiuntivo Luca Bianchi")
        self.url = reverse("riconcilia_movimento", args=[self.transfer.pk])

    def test_manual_page_shows_all_open_tuition_even_below_transfer_amount(self):
        expected_ids = {self.tuition.pk}
        for index in range(12):
            rate = self.next_rate(self.tuition, index + 2, index % 12 + 1, 2027, amount=350)
            expected_ids.add(rate.pk)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        proposals = response.context["proposte_rate"]
        self.assertEqual({p.targets[0].pk for p in proposals}, expected_ids)
        self.assertEqual(proposals[0].targets, [self.tuition])
        self.assertEqual(proposals[0].importo_totale, Decimal("350.00"))
        self.assertContains(response, f'name="rata_pk" value="{self.tuition.pk}"')
        self.assertFalse(RiconciliazioneRataMovimento.objects.exists())

    def test_partial_tuition_uses_only_its_remaining_balance(self):
        self.tuition.importo_pagato = Decimal("200.00")
        self.tuition.save()
        response = self.client.get(self.url)
        proposals = response.context["proposte_rate"]
        self.assertEqual(len(proposals), 1)
        self.assertEqual(proposals[0].importo_totale, Decimal("150.00"))

    def test_paid_and_unrelated_tuition_are_excluded(self):
        paid = self.next_rate(self.tuition, amount=425)
        paid.pagata = True
        paid.importo_pagato = Decimal("425.00")
        paid.save()
        original = self.tuition.iscrizione
        unrelated = Iscrizione.objects.create(
            studente=Studente.objects.create(nome="Anna", cognome="Verdi"),
            anno_scolastico=original.anno_scolastico,
            stato_iscrizione=original.stato_iscrizione,
            condizione_iscrizione=original.condizione_iscrizione,
        )
        RataIscrizione.objects.create(
            iscrizione=unrelated, numero_rata=1, mese_riferimento=9, anno_riferimento=2026,
            data_scadenza=self.tuition.data_scadenza, importo_dovuto=425,
        )
        response = self.client.get(self.url)
        self.assertEqual([p.targets[0].pk for p in response.context["proposte_rate"]], [self.tuition.pk])

    def test_tuition_word_without_matching_identity_does_not_suggest_students(self):
        self.transfer.descrizione = "Retta settembre e servizio aggiuntivo"
        self.transfer.save()
        self.assertEqual(self.client.get(self.url).context["proposte_rate"], [])

    def test_confirmation_settles_tuition_and_preserves_extra_balance(self):
        response = self.client.post(self.url, {
            "azione": "collega", "rata_pk": self.tuition.pk, "marca_rata_pagata": "1",
        })
        self.assertEqual(response.status_code, 302)
        self.tuition.refresh_from_db()
        self.transfer.refresh_from_db()
        self.assertTrue(self.tuition.pagata)
        self.assertEqual(self.tuition.importo_pagato, Decimal("350.00"))
        self.assertEqual(RiconciliazioneRataMovimento.objects.get().importo, Decimal("350.00"))
        self.assertEqual(importo_movimento_disponibile(self.transfer), Decimal("75.00"))
        self.assertEqual(self.transfer.stato_riconciliazione, StatoRiconciliazione.NON_RICONCILIATO)
        self.assertIsNone(self.transfer.rata_iscrizione_id)
        self.assertEqual(self.client.get(self.url).context["proposte_rate"], [])

    def test_remaining_transfer_amount_determines_candidate_ranking(self):
        self.next_rate(self.tuition, 2, 9, amount=425)
        matching_balance = self.next_rate(self.tuition, 3, 9, amount=75)
        riconcilia_movimento_con_rate(self.transfer, [(self.tuition, Decimal("350.00"))])
        response = self.client.get(self.url)
        proposals = response.context["proposte_rate"]
        self.assertEqual(proposals[0].targets, [matching_balance])
        self.assertTrue(all(p.importo_totale == Decimal("75.00") for p in proposals))

    def test_fully_allocated_transfer_has_no_further_candidates(self):
        self.tuition.importo_dovuto = Decimal("425.00")
        self.tuition.save()
        self.next_rate(self.tuition, amount=425)
        riconcilia_movimento_con_rate(self.transfer, [(self.tuition, Decimal("425.00"))])
        response = self.client.get(self.url)
        self.assertEqual(response.context["proposte_rate"], [])
        self.assertEqual(response.context["proposte_rate_cumulative"], [])


class ExtraServiceFixtures(InterfaceFixtures):
    def setUp(self):
        super().setUp()
        self.tuition = self.rate()
        self.tuition.importo_dovuto = Decimal("350.00")
        self.tuition.save()
        self.transfer = self.movement("425", "Retta settembre 2026 e doposcuola Luca Bianchi")
        self.url = reverse("riconcilia_movimento", args=[self.transfer.pk])
        self.extra = self.extra_rate()

    def extra_rate(self, *, student=None, name="Doposcuola", amount="75"):
        from servizi_extra.models import IscrizioneServizioExtra, RataServizioExtra, ServizioExtra, TariffaServizioExtra

        service = ServizioExtra.objects.create(anno_scolastico=self.tuition.iscrizione.anno_scolastico, nome_servizio=name)
        tariff = TariffaServizioExtra.objects.create(servizio=service, nome_tariffa="Standard")
        enrollment = IscrizioneServizioExtra.objects.create(
            servizio=service, tariffa=tariff, studente=student or self.tuition.iscrizione.studente,
        )
        return RataServizioExtra.objects.create(
            iscrizione=enrollment, numero_rata=1, importo_dovuto=Decimal(amount),
            descrizione="Quota settembre", data_scadenza=self.transfer.data_contabile,
        )

    def submit(self, *, tuition=True, amount="75,00", extra=None):
        extra = extra or self.extra
        return self.client.post(self.url, {
            "azione": "collega", "rata_pk": self.tuition.pk if tuition else "",
            "servizio_extra_ids": [extra.pk], f"importo_servizio_extra_{extra.pk}": amount,
            "marca_rata_pagata": "1",
            "residuo_movimento_atteso": str(importo_movimento_disponibile(self.transfer)),
        })


class ExtraServiceReconciliationTests(ExtraServiceFixtures, TestCase):
    def test_page_shows_tuition_and_only_unpaid_services_of_recognized_student(self):
        paid = self.extra_rate(name="Mensa")
        paid.pagata = True
        paid.importo_pagato = Decimal("75")
        paid.save()
        self.extra_rate(name="Trasporto", student=Studente.objects.create(nome="Anna", cognome="Verdi"))
        response = self.client.get(self.url)
        self.assertEqual(response.context["numero_candidati"], 2)
        self.assertEqual([c.rata for c in response.context["candidati_servizi_extra"]], [self.extra])
        self.assertContains(response, "Doposcuola")
        self.assertContains(response, f'name="servizio_extra_ids" value="{self.extra.pk}"')
        self.assertContains(response, "Collega quote selezionate")

    def test_mixed_payment_settles_both_and_retry_does_not_duplicate(self):
        from .models import RiconciliazioneServizioExtraMovimento

        self.assertEqual(self.submit().status_code, 302)
        self.transfer.refresh_from_db()
        self.extra.refresh_from_db()
        self.tuition.refresh_from_db()
        self.assertTrue(self.extra.pagata)
        self.assertTrue(self.tuition.pagata)
        self.assertEqual(self.extra.importo_pagato, Decimal("75"))
        self.assertEqual(self.extra.data_pagamento, self.transfer.data_contabile)
        self.assertEqual(self.transfer.stato_riconciliazione, StatoRiconciliazione.RICONCILIATO)
        self.assertEqual(importo_movimento_disponibile(self.transfer), 0)
        self.assertIsNone(self.transfer.rata_iscrizione_id)
        link = RiconciliazioneServizioExtraMovimento.objects.get()
        self.assertEqual(link.creato_da, self.user)
        self.assertEqual(link.importo, Decimal("75"))
        self.assertEqual(self.submit().status_code, 200)
        self.assertEqual(RiconciliazioneServizioExtraMovimento.objects.get().importo, Decimal("75"))
        self.assertEqual(RiconciliazioneRataMovimento.objects.get().importo, Decimal("350"))

    def test_extra_can_be_linked_after_tuition_using_remaining_balance(self):
        riconcilia_movimento_con_rate(self.transfer, [(self.tuition, Decimal("350"))])
        response = self.client.get(self.url)
        self.assertEqual(response.context["proposte_rate"], [])
        self.assertEqual(response.context["candidati_servizi_extra"][0].importo_proposto, Decimal("75"))
        self.assertEqual(self.submit(tuition=False).status_code, 302)
        self.transfer.refresh_from_db()
        self.assertEqual(importo_movimento_disponibile(self.transfer), 0)

    def test_partial_extra_payment_preserves_both_balances_and_matching_cache(self):
        from .services import _movimenti_per_matching, stato_riconciliazione_movimento_display
        from .models import MovimentoFinanziario

        self.assertEqual(self.submit(tuition=False, amount="25").status_code, 302)
        self.extra.refresh_from_db()
        self.assertEqual(self.extra.importo_pagato, Decimal("25"))
        self.assertFalse(self.extra.pagata)
        movement = next(_movimenti_per_matching(MovimentoFinanziario.objects.filter(pk=self.transfer.pk)))
        self.assertEqual(importo_movimento_disponibile(movement), Decimal("400"))
        self.assertIn("Parzial", stato_riconciliazione_movimento_display(movement))
        response = self.client.get(self.url)
        self.assertEqual(response.context["candidati_servizi_extra"][0].importo_proposto, Decimal("50"))

    def test_multiple_services_can_share_a_transfer(self):
        from .models import RiconciliazioneServizioExtraMovimento

        second = self.extra_rate(name="Mensa", amount="40")
        response = self.client.post(self.url, {
            "azione": "collega", "marca_rata_pagata": "1", "servizio_extra_ids": [self.extra.pk, second.pk],
            "residuo_movimento_atteso": "425",
            f"importo_servizio_extra_{self.extra.pk}": "75", f"importo_servizio_extra_{second.pk}": "40",
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(RiconciliazioneServizioExtraMovimento.objects.count(), 2)
        self.assertEqual(importo_movimento_disponibile(self.transfer), Decimal("310"))

    def test_excess_or_invalid_amount_never_registers_even_the_tuition(self):
        from .models import RiconciliazioneServizioExtraMovimento

        for value in ("75,01", "76", "426", "0", "-1", "NaN", "Infinity", "12,345", "", "invalid"):
            with self.subTest(value=value):
                self.assertEqual(self.submit(amount=value).status_code, 200)
                self.assertFalse(RiconciliazioneRataMovimento.objects.exists())
                self.assertFalse(RiconciliazioneServizioExtraMovimento.objects.exists())
                self.tuition.refresh_from_db()
                self.assertEqual(self.tuition.importo_pagato, 0)

    def test_matching_tuition_does_not_authorize_an_unrelated_service(self):
        from .models import RiconciliazioneServizioExtraMovimento

        unrelated = self.extra_rate(name="Altro", student=Studente.objects.create(nome="Anna", cognome="Verdi"))
        self.assertEqual(self.submit(extra=unrelated).status_code, 200)
        self.assertFalse(RiconciliazioneRataMovimento.objects.exists())
        self.assertFalse(RiconciliazioneServizioExtraMovimento.objects.exists())

    def test_repeated_partial_submission_does_not_register_twice(self):
        data = {
            "azione": "collega", "marca_rata_pagata": "1", "servizio_extra_ids": [self.extra.pk],
            f"importo_servizio_extra_{self.extra.pk}": "25", "residuo_movimento_atteso": "425",
        }
        self.assertEqual(self.client.post(self.url, data).status_code, 302)
        response = self.client.post(self.url, data)
        self.assertContains(response, "Il residuo del movimento è cambiato")
        self.extra.refresh_from_db()
        self.assertEqual(self.extra.importo_pagato, Decimal("25"))
        self.assertEqual(importo_movimento_disponibile(self.transfer), Decimal("400"))

    def test_cancellation_from_both_pages_restores_all_balances(self):
        from .models import RiconciliazioneServizioExtraMovimento

        for url in (self.url, reverse("annulla_riconciliazione_movimento", args=[self.transfer.pk])):
            with self.subTest(url=url):
                self.assertEqual(self.submit().status_code, 302)
                self.assertEqual(self.client.post(url, {"azione": "annulla"}).status_code, 302)
                self.tuition.refresh_from_db()
                self.extra.refresh_from_db()
                self.transfer.refresh_from_db()
                self.assertEqual(self.tuition.importo_pagato, 0)
                self.assertEqual(self.extra.importo_pagato, 0)
                self.assertFalse(self.extra.pagata)
                self.assertIsNone(self.extra.data_pagamento)
                self.assertFalse(RiconciliazioneServizioExtraMovimento.objects.exists())
                self.assertEqual(importo_movimento_disponibile(self.transfer), Decimal("425"))

    def test_extra_only_cancellation_preserves_prior_manual_payment(self):
        self.extra.importo_pagato = Decimal("20")
        self.extra.save()
        self.assertEqual(self.submit(tuition=False, amount="55").status_code, 302)
        undo_url = reverse("annulla_riconciliazione_movimento", args=[self.transfer.pk])
        self.assertContains(self.client.get(undo_url), "Doposcuola")
        self.assertEqual(self.client.post(undo_url).status_code, 302)
        self.extra.refresh_from_db()
        self.assertEqual(self.extra.importo_pagato, Decimal("20"))
        self.assertFalse(self.extra.pagata)

    def test_reconciled_extra_payment_fields_cannot_be_edited_directly(self):
        from servizi_extra.forms import RataServizioExtraPagamentoForm

        self.assertEqual(self.submit(tuition=False, amount="25").status_code, 302)
        self.extra.refresh_from_db()
        form = RataServizioExtraPagamentoForm(instance=self.extra)
        self.assertTrue(form.fields["importo_pagato"].disabled)
        self.assertTrue(form.fields["pagata"].disabled)

    def test_extra_reconciliation_requires_financial_management_permission(self):
        from django.contrib.auth.models import User
        from sistema.models import SistemaUtentePermessi

        user = User.objects.create_user(username="extra-read-only")
        SistemaUtentePermessi.objects.create(user=user, permesso_gestione_finanziaria="view")
        self.client.force_login(user)
        self.assertRedirects(self.submit(), reverse("home"), fetch_redirect_response=False)
        self.assertFalse(RiconciliazioneRataMovimento.objects.exists())
        self.assertFalse(self.transfer.riconciliazioni_servizi_extra.exists())


class ExtraServiceConcurrencyTests(ExtraServiceFixtures, TransactionTestCase):
    def test_concurrent_allocations_cannot_spend_the_same_balance_twice(self):
        from concurrent.futures import ThreadPoolExecutor
        from threading import Barrier
        from django.core.exceptions import ValidationError
        from django.db import connections
        from .models import MovimentoFinanziario, RiconciliazioneServizioExtraMovimento, StatoAnalisiRiconciliazione
        from servizi_extra.models import RataServizioExtra

        self.transfer.importo = Decimal("75")
        self.transfer.save()
        second = self.extra_rate(name="Mensa")
        StatoAnalisiRiconciliazione.objects.get_or_create(pk=1)
        barrier = Barrier(2)

        def reconcile(extra_id):
            try:
                movement = MovimentoFinanziario.objects.get(pk=self.transfer.pk)
                extra = RataServizioExtra.objects.get(pk=extra_id)
                barrier.wait(timeout=10)
                riconcilia_movimento_con_rate(movement, [], allocazioni_servizi_extra=[(extra, Decimal("75"))])
                return True
            except ValidationError:
                return False
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(reconcile, [self.extra.pk, second.pk]))
        self.assertEqual(sorted(results), [False, True])
        self.assertEqual(RiconciliazioneServizioExtraMovimento.objects.count(), 1)
        self.transfer.refresh_from_db()
        self.assertEqual(importo_movimento_disponibile(self.transfer), 0)
