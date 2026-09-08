from datetime import date
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse

from sistema.models import LivelloPermesso, SistemaUtentePermessi
from .models import DocumentoFornitore, Fornitore, NotificaFinanziaria, NotificaFinanziariaLettura
from .services import crea_notifica_finanziaria


class NotifichePersistenzaTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_superuser(username="notification-admin", password="Local-tests-123")
        cls.viewer = User.objects.create_user(username="notification-viewer", password="Local-tests-123")
        SistemaUtentePermessi.objects.create(user=cls.viewer, permesso_gestione_finanziaria=LivelloPermesso.VISUALIZZAZIONE)

    def setUp(self):
        self.client.force_login(self.user)
        self.notifica = NotificaFinanziaria.objects.create(titolo="Notifica persistente", messaggio="Testo intero " * 30)

    def non_lette(self, client=None):
        response = (client or self.client).get(reverse("stato_notifiche_finanziarie"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("no-store", response.headers["Cache-Control"])
        return response.json()["non_lette"]

    def test_spunta_persistente_dopo_logout_e_login_reale(self):
        self.client.post(reverse("segna_notifica_finanziaria_letta", args=[self.notifica.pk]))
        self.assertEqual(self.non_lette(), 0)
        self.client.get(reverse("logout"))
        self.assertFalse(self.client.session.get("_auth_user_id"))
        self.client.post(reverse("login"), {"username": self.user.username, "password": "Local-tests-123"})
        self.assertEqual(self.non_lette(), 0)
        self.assertTrue(NotificaFinanziariaLettura.objects.filter(user=self.user, notifica=self.notifica).exists())
        self.assertNotContains(self.client.get(reverse("lista_notifiche_finanziarie")), self.notifica.titolo)
        self.assertContains(self.client.get(reverse("lista_notifiche_finanziarie"), {"stato": "tutte"}), self.notifica.titolo)

    def test_segna_tutte_persistente_in_nuova_sessione_con_centinaia_di_notifiche(self):
        NotificaFinanziaria.objects.bulk_create([NotificaFinanziaria(titolo=f"Notifica {i}") for i in range(600)])
        response = self.client.post(reverse("segna_tutte_notifiche_finanziarie_lette"), HTTP_ACCEPT="application/json")
        self.assertEqual(response.json()["non_lette"], 0)
        self.assertEqual(NotificaFinanziariaLettura.objects.filter(user=self.user).count(), 601)
        altro_browser = Client()
        altro_browser.login(username=self.user.username, password="Local-tests-123")
        self.assertEqual(self.non_lette(altro_browser), 0)
        nuova = NotificaFinanziaria.objects.create(titolo="Arrivata dopo Segna tutte")
        self.assertEqual(self.non_lette(altro_browser), 1)
        self.assertFalse(NotificaFinanziariaLettura.objects.filter(user=self.user, notifica=nuova).exists())

    def test_letture_separate_per_account(self):
        self.client.post(reverse("segna_tutte_notifiche_finanziarie_lette"))
        self.client.force_login(self.viewer)
        self.assertEqual(self.non_lette(), 1)

    def test_visibilita_coerente_e_impossibile_leggere_notifica_riservata(self):
        riservata = NotificaFinanziaria.objects.create(titolo="Riservata", richiede_gestione=True)
        self.client.force_login(self.viewer)
        self.assertEqual(self.non_lette(), 1)
        self.assertEqual(self.client.post(reverse("segna_notifica_finanziaria_letta", args=[riservata.pk])).status_code, 404)
        self.client.post(reverse("segna_tutte_notifiche_finanziarie_lette"))
        self.assertFalse(NotificaFinanziariaLettura.objects.filter(user=self.viewer, notifica=riservata).exists())

    def test_doppio_click_non_duplica_ne_resetta_data_lettura(self):
        url = reverse("segna_notifica_finanziaria_letta", args=[self.notifica.pk])
        self.client.post(url, HTTP_ACCEPT="application/json")
        lettura = NotificaFinanziariaLettura.objects.get(user=self.user, notifica=self.notifica)
        self.client.post(url, HTTP_ACCEPT="application/json")
        self.assertEqual(NotificaFinanziariaLettura.objects.get(pk=lettura.pk).letta_il, lettura.letta_il)
        self.assertEqual(self.non_lette(), 0)

    def test_risposta_json_conferma_lettura_e_contatore_database(self):
        response = self.client.post(reverse("segna_notifica_finanziaria_letta", args=[self.notifica.pk]), HTTP_ACCEPT="application/json")
        self.assertEqual(response.json()["lette_ids"], [self.notifica.pk])
        self.assertEqual(response.json()["non_lette"], 0)
        self.assertIn("Nessuna nuova notifica", response.json()["html"])

    def test_get_non_segna_lette_e_sessione_scaduta_non_restituisce_zero(self):
        for nome, args in [("segna_notifica_finanziaria_letta", [self.notifica.pk]), ("segna_tutte_notifiche_finanziarie_lette", [])]:
            self.assertEqual(self.client.get(reverse(nome, args=args)).status_code, 405)
        self.client.logout()
        response = self.client.post(reverse("segna_notifica_finanziaria_letta", args=[self.notifica.pk]), HTTP_ACCEPT="application/json")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(NotificaFinanziariaLettura.objects.count(), 0)

    def test_errore_database_non_salva_ne_conferma_lettura(self):
        self.client.raise_request_exception = False
        with patch("gestione_finanziaria.views.NotificaFinanziariaLettura.objects.get_or_create", side_effect=RuntimeError("errore simulato")):
            response = self.client.post(reverse("segna_notifica_finanziaria_letta", args=[self.notifica.pk]), HTTP_ACCEPT="application/json")
        self.assertEqual(response.status_code, 500)
        self.assertEqual(self.non_lette(), 1)

    def test_testo_completo_disponibile_per_hover_nella_campanella(self):
        response = self.client.get(reverse("lista_notifiche_finanziarie"))
        self.assertContains(response, self.notifica.messaggio, count=2)
        self.assertContains(response, "notification-preview")
        self.assertContains(response, "data-notification-read-url")

    def test_reimport_stessa_fattura_con_altro_id_non_ripropone_notifica_letta(self):
        fornitore = Fornitore.objects.create(denominazione="Fornitore test notifiche")
        documento = DocumentoFornitore.objects.create(fornitore=fornitore, numero_documento="F-1", data_documento=date(2026, 1, 1))
        prima, _ = crea_notifica_finanziaria(titolo="Fattura ricevuta", tipo="fattura_ricevuta", documento=documento, chiave_deduplica="fic-document-pending-1")
        NotificaFinanziariaLettura.objects.create(user=self.user, notifica=prima)
        seconda, creata = crea_notifica_finanziaria(titolo="Fattura aggiornata", tipo="fattura_ricevuta", documento=documento, chiave_deduplica="fic-document-expense-2")
        self.assertFalse(creata)
        self.assertEqual(seconda.pk, prima.pk)
        self.assertTrue(NotificaFinanziariaLettura.objects.filter(user=self.user, notifica=seconda).exists())

    def test_migrazione_duplicati_conserva_letture_di_tutti_gli_account(self):
        from importlib import import_module
        from django.apps import apps
        from django.db import connection
        from types import SimpleNamespace

        fornitore = Fornitore.objects.create(denominazione="Fornitore migrazione notifiche")
        documento = DocumentoFornitore.objects.create(fornitore=fornitore, numero_documento="F-2", data_documento=date(2026, 1, 1))
        prima = NotificaFinanziaria.objects.create(titolo="Ricevuta", documento=documento, tipo="fattura_ricevuta", chiave_deduplica="fic-document-old")
        seconda = NotificaFinanziaria.objects.create(titolo="Aggiornata", documento=documento, tipo="fattura_ricevuta", chiave_deduplica="fic-document-new")
        NotificaFinanziariaLettura.objects.create(user=self.user, notifica=prima)
        lettura = NotificaFinanziariaLettura.objects.create(user=self.viewer, notifica=seconda)
        NotificaFinanziariaLettura.objects.create(user=self.user, notifica=seconda)
        migration = import_module("gestione_finanziaria.migrations.0014_notifiche_import_stabili")
        migration.conserva_letture_notifiche_import(apps, SimpleNamespace(connection=connection))
        self.assertEqual(NotificaFinanziaria.objects.filter(documento=documento).count(), 1)
        self.assertEqual(NotificaFinanziariaLettura.objects.filter(notifica=prima).count(), 2)
        lettura.refresh_from_db()
        self.assertEqual(lettura.notifica_id, prima.pk)
        self.assertEqual(self.non_lette(), 1)  # Solo la notifica indipendente del setUp.
