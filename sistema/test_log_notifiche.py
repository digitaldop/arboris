from datetime import timedelta
from unittest.mock import patch

from django.apps import apps
from django.contrib.auth.models import User
from django.db.migrations.state import ProjectState
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from gestione_finanziaria.models import Fornitore, NotificaFinanziaria, NotificaFinanziariaLettura
from .audit import audit_actor, audit_logging_disabled
from .audit_retention import cleanup_cronologia_operazioni
from .log_notifiche import riepilogo_log
from .models import (
    LivelloPermesso, RuoloUtente, SistemaImpostazioniGenerali, SistemaLogLettura,
    SistemaLogStatoLettura, SistemaOperazioneCronologia, SistemaUtentePermessi,
)


class LogNotificheTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        with audit_logging_disabled():
            cls.admin = User.objects.create_superuser(username="log-admin", password="Log-tests-2026")
            cls.operativo = User.objects.create_user(username="log-operativo")
            SistemaUtentePermessi.objects.create(user=cls.operativo, ruolo=RuoloUtente.AMMINISTRATORE)
            cls.staff = User.objects.create_user(username="log-staff", is_staff=True)
            SistemaUtentePermessi.objects.create(user=cls.staff, permesso_sistema=LivelloPermesso.GESTIONE)
            cls.utente = User.objects.create_user(username="log-utente", first_name="Operatore", last_name="Prova")
            SistemaUtentePermessi.objects.create(user=cls.utente)

    def setUp(self):
        self.client.force_login(self.admin)
        riepilogo_log(self.admin)
        riepilogo_log(self.operativo)

    def operazione(self, descrizione="Modificato documento di prova.", **kwargs):
        dati = dict(azione="update", modulo="gestione_finanziaria", app_label="gestione_finanziaria",
                    model_name="fornitore", model_verbose_name="fornitore", descrizione=descrizione,
                    utente=self.utente, utente_label="Operatore Prova", oggetto_label="Fornitore di prova")
        dati.update(kwargs)
        return SistemaOperazioneCronologia.objects.create(**dati)

    def non_lette(self):
        response = self.client.get(reverse("stato_log_operazioni"))
        self.assertEqual(response.status_code, 200)
        self.assertIn("no-store", response.headers["Cache-Control"])
        return response.json()["non_lette"]

    def test_visibile_solo_ad_amministratori_anche_senza_modulo_finanziario(self):
        for user, permesso in ((self.admin, True), (self.operativo, True), (self.staff, False), (self.utente, False)):
            with self.subTest(user=user.username):
                self.client.force_login(user)
                response = self.client.get(reverse("home"))
                if permesso:
                    self.assertContains(response, "Apri LOG operazioni utenti")
                else:
                    self.assertNotContains(response, "Apri LOG operazioni utenti")
                    self.assertEqual(self.client.get(reverse("stato_log_operazioni")).status_code, 302)
        self.assertFalse(SistemaLogStatoLettura.objects.filter(user=self.staff).exists())

    def test_accesso_diretto_alle_letture_bloccato_ai_non_amministratori(self):
        operazione = self.operazione("Informazione riservata")
        for user in (self.staff, self.utente):
            self.client.force_login(user)
            for url in (reverse("segna_log_operazione_letta", args=[operazione.pk]), reverse("segna_tutti_log_operazioni_letti")):
                response = self.client.post(url, HTTP_ACCEPT="application/json")
                self.assertEqual(response.status_code, 302)
                self.assertNotContains(response, "Informazione riservata", status_code=302)
        self.assertEqual(SistemaLogLettura.objects.count(), 0)

    def test_primo_utilizzo_non_ripropone_lo_storico(self):
        with audit_logging_disabled():
            nuovo_admin = User.objects.create_superuser(username="nuovo-log-admin")
        vecchia = self.operazione("Operazione precedente")
        self.assertEqual(riepilogo_log(nuovo_admin)["log_operazioni_non_lette"], 0)
        nuova = self.operazione("Operazione successiva")
        self.assertEqual([op.pk for op in riepilogo_log(nuovo_admin)["log_operazioni_recenti"]], [nuova.pk])
        self.assertTrue(SistemaOperazioneCronologia.objects.filter(pk=vecchia.pk).exists())

    def test_elenco_rapido_mostra_ultime_cinque_operazioni_umane_e_testo_intero(self):
        testo = "Descrizione completa " * 20
        for _ in range(7):
            self.operazione(testo)
        self.operazione("Processo automatico", utente=None, utente_label="")
        response = self.client.get(reverse("stato_log_operazioni"))
        self.assertEqual(response.json()["non_lette"], 7)
        self.assertEqual(response.json()["html"].count(testo), 5)
        self.assertNotIn("Processo automatico", response.json()["html"])
        self.assertIn("Operatore Prova", response.json()["html"])

    def test_lettura_persiste_dopo_logout_e_login_ed_e_separata_per_admin(self):
        op = self.operazione()
        url = reverse("segna_log_operazione_letta", args=[op.pk])
        self.client.post(url, HTTP_ACCEPT="application/json")
        lettura = SistemaLogLettura.objects.get(user=self.admin, operazione=op)
        self.client.post(url, HTTP_ACCEPT="application/json")
        self.assertEqual(SistemaLogLettura.objects.get(pk=lettura.pk).letta_il, lettura.letta_il)
        self.client.get(reverse("logout"))
        self.client.post(reverse("login"), {"username": self.admin.username, "password": "Log-tests-2026"})
        self.assertTrue(SistemaLogLettura.objects.filter(pk=lettura.pk).exists())
        self.assertEqual(self.non_lette(), 1)  # Il nuovo login resta da leggere.
        self.assertEqual(riepilogo_log(self.operativo)["log_operazioni_non_lette"], 2)

    def test_segna_tutte_centinaia_di_operazioni_e_nuovi_eventi_successivi(self):
        SistemaOperazioneCronologia.objects.bulk_create([
            SistemaOperazioneCronologia(azione="update", modulo="sistema", app_label="sistema", model_name="scuola",
                                       model_verbose_name="scuola", descrizione=f"Operazione {i}", utente=self.utente)
            for i in range(601)
        ])
        response = self.client.post(reverse("segna_tutti_log_operazioni_letti"), HTTP_ACCEPT="application/json")
        self.assertEqual(response.json()["non_lette"], 0)
        self.assertEqual(SistemaLogLettura.objects.filter(user=self.admin).count(), 601)
        self.operazione()
        self.assertEqual(self.non_lette(), 1)

    def test_campanella_e_log_conservano_conteggi_indipendenti(self):
        op = self.operazione()
        notifica = NotificaFinanziaria.objects.create(titolo="Fattura di prova")
        self.client.post(reverse("segna_tutti_log_operazioni_letti"))
        self.assertFalse(NotificaFinanziariaLettura.objects.filter(notifica=notifica).exists())
        self.assertTrue(SistemaLogLettura.objects.filter(operazione=op).exists())
        self.operazione()
        self.client.post(reverse("segna_tutte_notifiche_finanziarie_lette"))
        self.assertEqual(self.non_lette(), 1)

    def test_lettura_e_inizializzazione_non_generano_nuovi_log(self):
        op = self.operazione()
        notifica = NotificaFinanziaria.objects.create(titolo="Avviso")
        totale = SistemaOperazioneCronologia.objects.count()
        with audit_actor(self.admin):
            SistemaLogStatoLettura.objects.filter(user=self.admin).delete()
            riepilogo_log(self.admin)
            SistemaLogLettura.objects.create(user=self.admin, operazione=op)
            NotificaFinanziariaLettura.objects.create(user=self.admin, notifica=notifica)
        self.assertEqual(SistemaOperazioneCronologia.objects.count(), totale)

    def test_modifiche_reali_registrate_con_autore(self):
        with audit_actor(self.utente):
            fornitore = Fornitore.objects.create(denominazione="Fornitore LOG")
            fornitore.denominazione = "Fornitore LOG aggiornato"
            fornitore.save()
            fornitore.delete()
        operazioni = riepilogo_log(self.admin)["log_operazioni_recenti"]
        self.assertEqual([op.azione for op in operazioni], ["delete", "update", "create"])
        self.assertTrue(all(op.utente_id == self.utente.pk for op in operazioni))

    def test_modelli_storici_delle_migrazioni_non_generano_log(self):
        historical_user = ProjectState.from_apps(apps).apps.get_model("auth", "User")
        totale = SistemaOperazioneCronologia.objects.count()
        with audit_actor(self.admin):
            user = historical_user.objects.create(username="utente-da-migrazione")
            user.first_name = "Aggiornato"
            user.save()
            user.delete()
        self.assertEqual(SistemaOperazioneCronologia.objects.count(), totale)

    def test_collegamento_apre_solo_operazione_selezionata_nella_cronologia(self):
        op = self.operazione("Operazione selezionata")
        altra = self.operazione("Altra operazione")
        response = self.client.get(reverse("cronologia_operazioni_sistema"), {"operazione": op.pk})
        self.assertEqual([entry.pk for entry in response.context["operazioni"]], [op.pk])
        self.assertEqual(response.context["totale_operazioni"], 1)
        self.assertNotIn(altra, response.context["operazioni"])
        self.assertContains(response, "Pulisci")

    def test_get_e_csrf_non_possono_segnare_lette(self):
        op = self.operazione()
        url = reverse("segna_log_operazione_letta", args=[op.pk])
        self.assertEqual(self.client.get(url).status_code, 405)
        self.assertEqual(self.client.get(reverse("segna_tutti_log_operazioni_letti")).status_code, 405)
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.admin)
        self.assertEqual(client.post(url).status_code, 403)
        self.assertEqual(SistemaLogLettura.objects.count(), 0)

    def test_errore_salvataggio_non_conferma_lettura(self):
        op = self.operazione()
        self.client.raise_request_exception = False
        with patch("sistema.log_notifiche.SistemaLogLettura.objects.get_or_create", side_effect=RuntimeError("errore simulato")):
            response = self.client.post(reverse("segna_log_operazione_letta", args=[op.pk]), HTTP_ACCEPT="application/json")
        self.assertEqual(response.status_code, 500)
        self.assertEqual(self.non_lette(), 1)

    def test_retention_elimina_letture_collegate_e_conta_solo_operazioni(self):
        op = self.operazione()
        SistemaOperazioneCronologia.objects.filter(pk=op.pk).update(data_operazione=timezone.now() - timedelta(days=800))
        SistemaLogLettura.objects.create(user=self.admin, operazione=op)
        with audit_logging_disabled():
            impostazioni = SistemaImpostazioniGenerali.objects.create(cronologia_retention_mesi=24)
        result = cleanup_cronologia_operazioni(impostazioni=impostazioni, force=True)
        self.assertEqual(result["deleted_count"], 1)
        self.assertEqual(SistemaLogLettura.objects.count(), 0)
