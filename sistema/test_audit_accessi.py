from unittest.mock import patch

from django.contrib.auth.models import AnonymousUser, User
from django.core.cache import cache
from django.http import HttpResponse, JsonResponse, StreamingHttpResponse
from django.test import RequestFactory, TestCase
from django.urls import resolve, reverse

from .audit import audit_logging_disabled, get_current_audit_user
from .log_notifiche import riepilogo_log
from .middleware import AuditUserMiddleware
from .models import LivelloPermesso, SistemaOperazioneCronologia, SistemaUtentePermessi


class AuditAccessiTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        with audit_logging_disabled():
            cls.user = User.objects.create_user(
                username="accessi-operatore", password="Accessi-tests-2026",
                first_name="Mario", last_name="Rossi",
            )
            SistemaUtentePermessi.objects.create(
                user=cls.user, permesso_anagrafica=LivelloPermesso.VISUALIZZAZIONE,
            )
            cls.admin = User.objects.create_superuser(username="accessi-admin")

    def setUp(self):
        cache.clear()
        with audit_logging_disabled():
            self.client.force_login(self.user)

    def page_request(self, method="GET", **headers):
        request = RequestFactory().generic(method, "/studenti/42/modifica/?q=riservato&token=segreto", **headers)
        request.user = self.user
        request.resolver_match = resolve(request.path_info)
        return request

    def page_response(self, **kwargs):
        return HttpResponse("<!DOCTYPE html><html><head><title>Scheda</title></head><body></body></html>", **kwargs)

    def test_login_riuscito_registra_una_sola_voce_con_utente_e_orario(self):
        self.client.logout()
        response = self.client.post(reverse("login"), {
            "username": self.user.username, "password": "Accessi-tests-2026",
        })
        self.assertEqual(response.status_code, 302)
        entry = SistemaOperazioneCronologia.objects.get()
        self.assertEqual(entry.azione, "login")
        self.assertEqual(entry.utente_id, self.user.pk)
        self.assertEqual(entry.utente_label, "Mario Rossi")
        self.assertEqual(entry.modulo, "sistema")
        self.assertIsNotNone(entry.data_operazione)
        self.assertNotIn("Accessi-tests-2026", entry.descrizione)
        self.assertIsNone(get_current_audit_user())

    def test_login_fallito_e_pagine_anonime_non_generano_eventi(self):
        self.client.logout()
        self.client.get(reverse("login"))
        response = self.client.post(reverse("login"), {
            "username": self.user.username, "password": "errata",
        })
        self.assertEqual(response.status_code, 200)
        self.client.get(reverse("home"))
        self.assertFalse(SistemaOperazioneCronologia.objects.exists())

    def test_visite_reali_home_e_lista_registrate_una_volta_per_richiesta(self):
        for name in ("home", "lista_studenti", "lista_studenti"):
            self.assertEqual(self.client.get(reverse(name)).status_code, 200)
        entries = list(SistemaOperazioneCronologia.objects.filter(azione="view").order_by("pk"))
        self.assertEqual(len(entries), 3)
        self.assertEqual([entry.modulo for entry in entries], ["sistema", "anagrafica", "anagrafica"])
        self.assertTrue(all(entry.utente_id == self.user.pk for entry in entries))

    def test_scheda_identificata_dal_percorso_senza_parametri_o_contenuti(self):
        request = self.page_request(HTTP_SEC_FETCH_DEST="document")
        response = self.page_response()
        self.assertIs(AuditUserMiddleware(lambda req: response)(request), response)
        entry = SistemaOperazioneCronologia.objects.get()
        self.assertEqual(entry.azione, "view")
        self.assertEqual(entry.modulo, "anagrafica")
        self.assertIn("/studenti/42/modifica/", entry.descrizione)
        self.assertNotIn("riservato", entry.descrizione)
        self.assertNotIn("segreto", entry.descrizione)
        self.assertNotIn("<html", entry.descrizione)
        self.assertIsNone(get_current_audit_user())

    def test_richieste_automatiche_file_frammenti_ed_errori_esclusi(self):
        cases = [
            ("HEAD", {}, lambda: self.page_response()),
            ("POST", {}, lambda: self.page_response()),
            ("GET", {"HTTP_SEC_FETCH_DEST": "empty"}, lambda: self.page_response()),
            ("GET", {"HTTP_X_REQUESTED_WITH": "XMLHttpRequest"}, lambda: self.page_response()),
            ("GET", {"HTTP_HX_REQUEST": "true"}, lambda: self.page_response()),
            ("GET", {"HTTP_PURPOSE": "prefetch"}, lambda: self.page_response()),
            ("GET", {"HTTP_SEC_PURPOSE": "prefetch;prerender"}, lambda: self.page_response()),
            ("GET", {}, lambda: JsonResponse({"html": "<html>"})),
            ("GET", {}, lambda: HttpResponse("<div>Frammento</div>")),
            ("GET", {}, lambda: self.page_response(status=302)),
            ("GET", {}, lambda: self.page_response(status=403)),
            ("GET", {}, lambda: self.page_response(status=404)),
            ("GET", {}, lambda: self.page_response(status=500)),
            ("GET", {}, lambda: self.page_response(content_type="application/pdf")),
            ("GET", {}, lambda: self.page_response(headers={"Content-Disposition": "attachment; filename=pagina.html"})),
            ("GET", {}, lambda: StreamingHttpResponse(iter([b"<html></html>"]))),
        ]
        for method, headers, make_response in cases:
            response = make_response()
            with self.subTest(method=method, headers=headers, status=response.status_code, content_type=response.get("Content-Type")):
                request = self.page_request(method, **headers)
                AuditUserMiddleware(lambda req: response)(request)
                self.assertFalse(SistemaOperazioneCronologia.objects.exists())

    def test_utenti_anonimi_e_audit_disabilitato_non_registrati(self):
        request = self.page_request()
        request.user = AnonymousUser()
        middleware = AuditUserMiddleware(lambda req: self.page_response())
        middleware(request)
        request.user = self.user
        with audit_logging_disabled():
            middleware(request)
            self.client.force_login(self.admin)
        self.assertFalse(SistemaOperazioneCronologia.objects.exists())

    def test_autore_separato_fra_richieste_e_conservato_dopo_eliminazione(self):
        self.client.get(reverse("home"))
        with audit_logging_disabled():
            self.client.force_login(self.admin)
        self.client.get(reverse("home"))
        entries = list(SistemaOperazioneCronologia.objects.filter(azione="view").order_by("pk"))
        self.assertEqual([entry.utente_id for entry in entries], [self.user.pk, self.admin.pk])
        with audit_logging_disabled():
            self.user.delete()
        entries[0].refresh_from_db()
        self.assertIsNone(entries[0].utente_id)
        self.assertEqual(entries[0].utente_display, "Mario Rossi")

    def test_login_e_visite_visibili_nel_log_e_filtrabili_nella_cronologia(self):
        riepilogo_log(self.admin)
        self.client.logout()
        self.client.post(reverse("login"), {"username": self.user.username, "password": "Accessi-tests-2026"})
        self.client.get(reverse("lista_studenti"))
        events = list(SistemaOperazioneCronologia.objects.filter(azione__in=["login", "view"]))
        self.assertEqual(riepilogo_log(self.admin)["log_operazioni_non_lette"], 2)
        with audit_logging_disabled():
            self.client.force_login(self.admin)
        for action, counter in (("login", "count_login"), ("view", "count_visualizzazioni")):
            response = self.client.get(reverse("cronologia_operazioni_sistema"), {
                "azione": action, "q": self.user.username,
            })
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.context["totale_operazioni"], 1)
            self.assertEqual(response.context[counter], 1)
            self.assertEqual(response.context["operazioni"][0].utente_id, self.user.pk)
            self.assertContains(response, 'value="login"')
            self.assertContains(response, 'value="view"')
        response = self.client.get(reverse("cronologia_operazioni_sistema"), {"q": "/studenti/", "azione": "view"})
        self.assertEqual(response.context["totale_operazioni"], 1)
        for entry in events:
            self.assertEqual(self.client.post(reverse("segna_log_operazione_letta", args=[entry.pk])).status_code, 302)

    def test_polling_log_non_genera_visite(self):
        with audit_logging_disabled():
            self.client.force_login(self.admin)
        for _ in range(3):
            self.assertEqual(self.client.get(reverse("stato_log_operazioni")).status_code, 200)
        self.assertFalse(SistemaOperazioneCronologia.objects.exists())

    def test_accesso_negato_non_registrato_come_visita(self):
        self.assertEqual(self.client.get(reverse("cronologia_operazioni_sistema")).status_code, 302)
        self.assertFalse(SistemaOperazioneCronologia.objects.exists())

    def test_schema_non_disponibile_non_interrompe_la_pagina(self):
        request = self.page_request()
        response = self.page_response()
        with patch("sistema.signals.audit_table_exists", return_value=False):
            self.assertIs(AuditUserMiddleware(lambda req: response)(request), response)
        self.assertFalse(SistemaOperazioneCronologia.objects.exists())

    def test_eccezioni_ripristinano_il_contesto_utente(self):
        def broken_view(request):
            raise RuntimeError("errore simulato")

        with self.assertRaises(RuntimeError):
            AuditUserMiddleware(broken_view)(self.page_request())
        self.assertIsNone(get_current_audit_user())
        self.assertFalse(SistemaOperazioneCronologia.objects.exists())
