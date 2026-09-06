from datetime import datetime, timedelta, timezone as datetime_timezone
from email.utils import format_datetime
from unittest.mock import Mock, patch

import requests
from django.test import SimpleTestCase

from .fatture_in_cloud import (
    FattureInCloudClient, FattureInCloudError, FattureInCloudRateLimited,
    FattureInCloudSyncBudgetExceeded, _document_with_supplier_detail,
)
from .fic_rate_limits import retry_after_seconds
from .models import FattureInCloudConnessione


class FicRateLimitClientTests(SimpleTestCase):
    def client_and_response(self, code=429, retry_after="120"):
        response = requests.Response()
        response.status_code = code
        response._content = b'{"error":{"message":"Too many requests."}}'
        if retry_after is not None:
            response.headers["Retry-After"] = retry_after
        client = FattureInCloudClient(FattureInCloudConnessione(company_id=123))
        client._headers = Mock(return_value={})
        return client, response

    def test_429_raises_typed_error_and_does_not_retry_immediately(self):
        client, response = self.client_and_response()
        with patch("gestione_finanziaria.fatture_in_cloud.requests.request", return_value=response) as request:
            with self.assertRaises(FattureInCloudRateLimited) as caught:
                client.request("GET", "/test")
        self.assertEqual(caught.exception.retry_after, 120)
        request.assert_called_once()

    def test_hourly_quota_403_with_retry_after_is_retryable(self):
        client, response = self.client_and_response(code=403, retry_after="3600")
        with patch("gestione_finanziaria.fatture_in_cloud.requests.request", return_value=response):
            with self.assertRaises(FattureInCloudRateLimited) as caught:
                client.request("GET", "/test")
        self.assertEqual(caught.exception.retry_after, 3600)

    def test_regular_403_stays_a_permission_error(self):
        client, response = self.client_and_response(code=403, retry_after=None)
        with patch("gestione_finanziaria.fatture_in_cloud.requests.request", return_value=response):
            with self.assertRaises(FattureInCloudError) as caught:
                client.request("GET", "/test")
        self.assertNotIsInstance(caught.exception, FattureInCloudRateLimited)
        self.assertIn("403", str(caught.exception))

    def test_retry_after_accepts_seconds_and_http_dates(self):
        now = datetime(2026, 9, 6, 12, tzinfo=datetime_timezone.utc)
        self.assertEqual(retry_after_seconds("120"), 120)
        self.assertEqual(retry_after_seconds("1.1"), 2)
        self.assertEqual(retry_after_seconds(format_datetime(now + timedelta(seconds=90)), now=now), 90)
        for invalid in (None, "", "invalid", "nan", "inf", "1e100"):
            with self.subTest(invalid=invalid):
                self.assertIsNone(retry_after_seconds(invalid))

    def test_supplier_rate_limit_is_not_hidden_as_a_missing_supplier(self):
        client = Mock()
        client.get_supplier.side_effect = FattureInCloudRateLimited(60)
        context = {"cache": {}, "warnings": set()}
        with self.assertRaises(FattureInCloudRateLimited):
            _document_with_supplier_detail(client, {"entity": {"id": 77}}, context)
        self.assertEqual(context["cache"], {})
        self.assertEqual(context["warnings"], set())

    def test_requests_are_spaced_including_first_request_of_chunk(self):
        client, response = self.client_and_response(code=200, retry_after=None)
        client.request_interval_seconds = 1.2
        clock = [0.0]
        times = []
        def sleep(seconds):
            clock[0] += seconds
        def request(*args, **kwargs):
            times.append(clock[0])
            return response
        with patch("gestione_finanziaria.fatture_in_cloud.time.monotonic", side_effect=lambda: clock[0]), \
             patch("gestione_finanziaria.fatture_in_cloud.time.sleep", side_effect=sleep), \
             patch("gestione_finanziaria.fatture_in_cloud.requests.request", side_effect=request):
            client.request("GET", "/one")
            client.request("GET", "/two")
        self.assertEqual(times, [1.2, 2.4])

    def test_budget_expiring_during_pacing_does_not_send_request(self):
        client, response = self.client_and_response(code=200, retry_after=None)
        client.request_interval_seconds = 1.2
        client.before_request = Mock(side_effect=[None, FattureInCloudSyncBudgetExceeded("Tempo massimo")])
        with patch("gestione_finanziaria.fatture_in_cloud.time.sleep"), \
             patch("gestione_finanziaria.fatture_in_cloud.requests.request", return_value=response) as request:
            with self.assertRaises(FattureInCloudSyncBudgetExceeded):
                client.request("GET", "/test")
        request.assert_not_called()
