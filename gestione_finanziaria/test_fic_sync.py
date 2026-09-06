from datetime import date, timedelta
from unittest.mock import Mock, patch

from django.contrib.auth.models import User
from django.test import SimpleTestCase, TestCase
from django.urls import reverse
from django.utils import timezone

from .fatture_in_cloud import (
    FattureInCloudClient, FattureInCloudError, FattureInCloudSyncBudgetExceeded,
    FattureInCloudSyncInProgress, _iter_paginated, sincronizza_fatture_in_cloud,
)
from .fic_periods import import_start_date
from .forms import FattureInCloudSyncForm
from .models import DocumentoFornitore, FattureInCloudConnessione
from .scheduler import is_fatture_in_cloud_sync_due


class FicImportPeriodTests(SimpleTestCase):
    def test_all_requested_periods_use_calendar_months(self):
        expected = {"1": date(2026, 8, 6), "3": date(2026, 6, 6), "6": date(2026, 3, 6),
                    "9": date(2025, 12, 6), "12": date(2025, 9, 6), "tutte": None}
        for period, start in expected.items():
            with self.subTest(period=period):
                self.assertEqual(import_start_date(period, today=date(2026, 9, 6)), start)

    def test_month_end_and_leap_year(self):
        self.assertEqual(import_start_date("1", today=date(2026, 3, 31)), date(2026, 2, 28))
        self.assertEqual(import_start_date("1", today=date(2024, 3, 31)), date(2024, 2, 29))
        self.assertEqual(import_start_date("12", today=date(2024, 2, 29)), date(2023, 2, 28))

    def test_manual_date_is_required_and_validated(self):
        for value in ("", "invalid", "2999-01-01"):
            with self.subTest(value=value):
                form = FattureInCloudSyncForm({"periodo": "manuale", "data_inizio": value})
                self.assertFalse(form.is_valid())
                self.assertIn("data_inizio", form.errors)

    def test_old_date_only_submission_and_unlimited_submission(self):
        form = FattureInCloudSyncForm({"data_inizio": "2020-01-01"})
        self.assertTrue(form.is_valid())
        self.assertEqual(form.cleaned_data["periodo"], "manuale")
        self.assertEqual(form.cleaned_data["data_inizio"], date(2020, 1, 1))
        form = FattureInCloudSyncForm({})
        self.assertTrue(form.is_valid())
        self.assertIsNone(form.cleaned_data["data_inizio"])

    @patch("gestione_finanziaria.fic_periods.timezone.localdate", return_value=date(2026, 9, 6))
    def test_preset_ignores_stale_manual_input(self, _today):
        form = FattureInCloudSyncForm({"periodo": "3", "data_inizio": "invalid"})
        self.assertTrue(form.is_valid())
        self.assertEqual(form.cleaned_data["data_inizio"], date(2026, 6, 6))
        self.assertFalse(FattureInCloudSyncForm({"periodo": "2"}).is_valid())


class FicPaginationTests(SimpleTestCase):
    def test_official_response_reads_all_150_documents(self):
        def fetch(page):
            return {"data": [{"id": i} for i in range((page - 1) * 50, page * 50)],
                    "current_page": page, "last_page": 3}
        fetch = Mock(side_effect=fetch)
        documents = list(_iter_paginated(fetch))
        self.assertEqual([item["id"] for item in documents], list(range(150)))
        self.assertEqual([call.args[0] for call in fetch.call_args_list], [1, 2, 3])

    def test_nested_pagination_and_numeric_strings(self):
        fetch = Mock(side_effect=lambda page: {
            "data": [{"id": page}], "pagination": {"current_page": str(page), "last_page": "2"},
        })
        self.assertEqual(list(_iter_paginated(fetch)), [{"id": 1}, {"id": 2}])

    def test_next_url_fallback_does_not_follow_arbitrary_urls(self):
        fetch = Mock(side_effect=[
            {"data": [{"id": 1}], "next_page_url": "https://example.invalid/page/2"},
            {"data": [{"id": 2}], "next_page_url": None},
        ])
        self.assertEqual(len(list(_iter_paginated(fetch))), 2)
        self.assertEqual(fetch.call_args.args, (2,))

    def test_empty_page_stops_even_if_more_pages_are_advertised(self):
        fetch = Mock(return_value={"data": [], "current_page": 1, "last_page": 20})
        self.assertEqual(list(_iter_paginated(fetch)), [])
        fetch.assert_called_once_with(1)

    def test_registered_api_uses_document_date_query(self):
        client = FattureInCloudClient(FattureInCloudConnessione(company_id=123))
        with patch.object(client, "request", return_value={}) as request:
            client.list_received_documents("expense", page=2, data_inizio=date(2026, 1, 1))
        self.assertEqual(request.call_args.kwargs["params"]["q"], "date >= '2026-01-01'")
        self.assertEqual(request.call_args.kwargs["params"]["page"], 2)
        self.assertNotIn("date_from", request.call_args.kwargs["params"])


class FicSyncContinuationTests(TestCase):
    def setUp(self):
        self.connessione = FattureInCloudConnessione.objects.create(company_id=123, sincronizza_documenti_da_registrare=False)
        self.user = User.objects.create_superuser(username="fic-sync-test")
        self.client.force_login(self.user)
        self.api = Mock()
        self.documents = [self.document(i, day) for i, day in enumerate(
            ["2026-08-01", "2026-07-01", "2026-06-01", "2020-01-01"], start=1,
        )]
        self.api.list_received_documents.side_effect = self.fetch
        self.api.list_pending_received_documents.return_value = {"data": [], "last_page": 1}
        client_patch = patch("gestione_finanziaria.fatture_in_cloud.FattureInCloudClient", return_value=self.api)
        detail_patch = patch("gestione_finanziaria.fatture_in_cloud._document_detail_from_summary", side_effect=lambda client, summary, **kwargs: summary)
        client_patch.start()
        detail_patch.start()
        self.addCleanup(client_patch.stop)
        self.addCleanup(detail_patch.stop)

    @staticmethod
    def document(pk, day):
        return {"id": pk, "date": day, "type": "expense", "invoice_number": f"TEST-{pk}",
                "entity": {"name": "Fornitore Test"}, "amount_gross": "100.00",
                "payments_list": [{"amount": "100.00", "due_date": day, "status": "not_paid"}]}

    def fetch(self, doc_type, *, page=1, **kwargs):
        if doc_type != "expense":
            return {"data": [], "current_page": page, "last_page": 1}
        return {"data": self.documents[(page - 1) * 2:page * 2], "current_page": page, "last_page": 2}

    def test_imports_unpaid_old_invoices_on_later_pages(self):
        stats = sincronizza_fatture_in_cloud(self.connessione, max_seconds=0)
        self.assertEqual(stats["creati"], 4)
        old = DocumentoFornitore.objects.get(external_id="4")
        self.assertEqual(old.data_documento, date(2020, 1, 1))
        self.assertEqual(old.scadenze.get().importo_pagato, 0)
        self.connessione.refresh_from_db()
        self.assertEqual(self.connessione.sync_progress, {})

    def test_cutoff_is_inclusive_on_second_page(self):
        stats = sincronizza_fatture_in_cloud(self.connessione, max_seconds=0, data_inizio=date(2026, 6, 1))
        self.assertEqual(stats["creati"], 3)
        self.assertTrue(DocumentoFornitore.objects.filter(external_id="3").exists())
        self.assertFalse(DocumentoFornitore.objects.filter(external_id="4").exists())

    def interrupt_after_first_document(self, **kwargs):
        def budget(*args):
            if DocumentoFornitore.objects.count() == 1:
                raise FattureInCloudSyncBudgetExceeded("Tempo massimo")
        with patch("gestione_finanziaria.fatture_in_cloud._check_sync_budget", side_effect=budget):
            stats = sincronizza_fatture_in_cloud(self.connessione, **kwargs)
        self.assertTrue(stats["interrotta_per_tempo"])
        self.connessione.refresh_from_db()
        self.assertEqual(self.connessione.sync_progress["cursor"]["processed_ids"], ["1"])
        self.assertFalse(self.connessione.in_corso)
        return stats

    def test_timeout_resumes_inside_page_without_reimporting_first_document(self):
        self.interrupt_after_first_document()
        stats = sincronizza_fatture_in_cloud(self.connessione, max_seconds=0)
        self.assertEqual(stats["creati"], 3)
        self.assertEqual(stats["aggiornati"], 0)
        self.assertEqual(DocumentoFornitore.objects.count(), 4)

    def test_changed_period_restarts_and_preserves_existing_documents(self):
        self.interrupt_after_first_document()
        stats = sincronizza_fatture_in_cloud(self.connessione, periodo_import="manuale", data_inizio=date(2026, 8, 1), max_seconds=0)
        self.assertEqual(stats["aggiornati"], 1)
        self.assertEqual(stats["creati"], 0)
        self.connessione.refresh_from_db()
        self.assertEqual(self.connessione.periodo_import, "manuale")
        self.assertEqual(self.connessione.data_inizio_import, date(2026, 8, 1))
        self.assertEqual(DocumentoFornitore.objects.count(), 1)

    def test_rolling_cutoff_stays_fixed_when_resumed_on_next_day(self):
        with patch("gestione_finanziaria.fic_periods.timezone.localdate", return_value=date(2026, 9, 1)):
            self.interrupt_after_first_document(periodo_import="3")
        with patch("gestione_finanziaria.fic_periods.timezone.localdate", return_value=date(2026, 9, 2)):
            stats = sincronizza_fatture_in_cloud(self.connessione, max_seconds=0)
        self.assertEqual(stats["creati"], 2)
        self.assertTrue(DocumentoFornitore.objects.filter(external_id="3").exists())
        self.assertEqual(self.api.list_received_documents.call_args.kwargs["data_inizio"], date(2026, 6, 1))

    def test_completed_import_starts_fresh_and_updates_previous_documents(self):
        sincronizza_fatture_in_cloud(self.connessione, max_seconds=0)
        stats = sincronizza_fatture_in_cloud(self.connessione, max_seconds=0)
        self.assertEqual(stats["aggiornati"], 4)
        self.assertEqual(DocumentoFornitore.objects.count(), 4)

    def test_api_page_error_keeps_cursor_for_retry(self):
        original = self.fetch
        def fetch(doc_type, *, page=1, **kwargs):
            if doc_type == "expense" and page == 2:
                raise FattureInCloudError("API non disponibile")
            return original(doc_type, page=page, **kwargs)
        self.api.list_received_documents.side_effect = fetch
        stats = sincronizza_fatture_in_cloud(self.connessione, max_seconds=0)
        self.assertEqual(stats["esito"], "parziale")
        self.connessione.refresh_from_db()
        self.assertEqual(self.connessione.sync_progress["cursor"]["page"], 2)
        self.api.list_received_documents.side_effect = original
        stats = sincronizza_fatture_in_cloud(self.connessione, max_seconds=0)
        self.assertEqual(stats["creati"], 2)
        self.assertEqual(stats["aggiornati"], 0)

    def test_pending_documents_also_read_later_pages(self):
        self.connessione.sincronizza_documenti_registrati = False
        self.connessione.sincronizza_documenti_da_registrare = True
        self.connessione.save()
        self.api.list_pending_received_documents.side_effect = lambda doc_type, **kwargs: self.fetch("expense" if doc_type == "agyo" else doc_type, **kwargs)
        stats = sincronizza_fatture_in_cloud(self.connessione, max_seconds=0)
        self.assertEqual(stats["creati"], 4)

    def test_active_sync_is_not_overwritten(self):
        self.connessione.in_corso = True
        self.connessione.avviato_at = timezone.now()
        self.connessione.save()
        with self.assertRaises(FattureInCloudSyncInProgress):
            sincronizza_fatture_in_cloud(self.connessione, periodo_import="1")
        self.connessione.refresh_from_db()
        self.assertEqual(self.connessione.periodo_import, "tutte")
        self.api.list_received_documents.assert_not_called()

    def test_automatic_import_resumes_before_normal_interval(self):
        self.interrupt_after_first_document()
        self.connessione.sync_automatico = True
        now = self.connessione.ultimo_sync_at + timedelta(minutes=5)
        self.assertTrue(is_fatture_in_cloud_sync_due(self.connessione, now=now))
        self.assertFalse(is_fatture_in_cloud_sync_due(self.connessione, now=now - timedelta(seconds=1)))

    def test_ajax_saves_period_and_reloads_selection(self):
        with patch("gestione_finanziaria.fic_periods.timezone.localdate", return_value=date(2026, 9, 1)):
            response = self.client.post(reverse("sincronizza_fatture_in_cloud", args=[self.connessione.pk]),
                                        {"periodo": "3"}, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["creati"], 3)
        self.connessione.refresh_from_db()
        self.assertEqual(self.connessione.periodo_import, "3")
        response = self.client.get(reverse("modifica_fatture_in_cloud", args=[self.connessione.pk]))
        self.assertEqual(response.context["sync_form"]["periodo"].value(), "3")
        self.assertContains(response, "Data manuale")

    def test_invalid_ajax_date_does_not_start_sync(self):
        response = self.client.post(reverse("sincronizza_fatture_in_cloud", args=[self.connessione.pk]),
                                    {"periodo": "manuale"}, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertEqual(response.status_code, 400)
        self.assertIn("Imposta la data", response.json()["error"])
        self.api.list_received_documents.assert_not_called()
