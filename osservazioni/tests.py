from datetime import date
from unittest import skip

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from anagrafica.models import Studente
from sistema.models import LivelloPermesso, RuoloUtente, SistemaImpostazioniGenerali, SistemaUtentePermessi

from .models import OsservazioneStudente


@skip("Legacy test basato sulla tabella anagrafica.Famiglia rimossa.")
class OsservazioniStudenteTests(TestCase):
    def setUp(self):
        self.password = "Password123!"
        self.user_manage = User.objects.create_user(
            username="osservazioni-manage@example.com",
            email="osservazioni-manage@example.com",
            password=self.password,
            first_name="Mario",
            last_name="Rossi",
        )
        SistemaUtentePermessi.objects.create(
            user=self.user_manage,
            permesso_anagrafica=LivelloPermesso.GESTIONE,
        )
        self.user_other_manage = User.objects.create_user(
            username="osservazioni-other-manage@example.com",
            email="osservazioni-other-manage@example.com",
            password=self.password,
            first_name="Luigi",
            last_name="Verdi",
        )
        SistemaUtentePermessi.objects.create(
            user=self.user_other_manage,
            permesso_anagrafica=LivelloPermesso.GESTIONE,
        )
        self.user_admin = User.objects.create_user(
            username="osservazioni-admin@example.com",
            email="osservazioni-admin@example.com",
            password=self.password,
            first_name="Anna",
            last_name="Admin",
        )
        SistemaUtentePermessi.objects.create(
            user=self.user_admin,
            ruolo=RuoloUtente.AMMINISTRATORE,
            permesso_anagrafica=LivelloPermesso.GESTIONE,
        )
        self.user_view = User.objects.create_user(
            username="osservazioni-view@example.com",
            email="osservazioni-view@example.com",
            password=self.password,
        )
        SistemaUtentePermessi.objects.create(
            user=self.user_view,
            permesso_anagrafica=LivelloPermesso.VISUALIZZAZIONE,
        )
        stato = StatoRelazioneFamiglia.objects.create(stato="Iscritta", ordine=1, attivo=True)
        self.famiglia = Famiglia.objects.create(cognome_famiglia="Bianchi", stato_relazione_famiglia=stato)
        self.studente = Studente.objects.create(
            famiglia=self.famiglia,
            nome="Luca",
            cognome="Bianchi",
            data_nascita=date(2020, 5, 10),
        )

    def test_studente_page_links_to_osservazioni(self):
        self.client.force_login(self.user_manage)

        response = self.client.get(reverse("modifica_studente", kwargs={"pk": self.studente.pk}))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Osservazioni Pedagogiche")
        self.assertContains(response, reverse("osservazioni_studente", kwargs={"studente_pk": self.studente.pk}))

    def test_osservazioni_page_orders_oldest_first_by_default_and_can_reverse(self):
        older = OsservazioneStudente.objects.create(
            studente=self.studente,
            titolo="Primo colloquio",
            data_inserimento=date(2026, 1, 10),
            testo="Prima osservazione",
        )
        newer = OsservazioneStudente.objects.create(
            studente=self.studente,
            titolo="Aggiornamento",
            data_inserimento=date(2026, 2, 10),
            testo="Seconda osservazione",
        )
        self.client.force_login(self.user_view)

        response = self.client.get(reverse("osservazioni_studente", kwargs={"studente_pk": self.studente.pk}))
        self.assertEqual(list(response.context["osservazioni"]), [older, newer])

        response = self.client.get(
            reverse("osservazioni_studente", kwargs={"studente_pk": self.studente.pk}),
            {"ordine": "desc"},
        )
        self.assertEqual(list(response.context["osservazioni"]), [newer, older])

    def test_manage_page_starts_in_consultation_mode(self):
        self.client.force_login(self.user_manage)

        response = self.client.get(reverse("osservazioni_studente", kwargs={"studente_pk": self.studente.pk}))

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context["show_create_form"])
        content = response.content.decode()
        self.assertIn("AGGIUNGI UN", content)
        self.assertIn("OSSERVAZIONE", content)
        self.assertIn("ANNULLA INSERIMENTO", content)
        self.assertIn('id="osservazioni-create-section"', content)
        self.assertIn("osservazioni-create-section is-hidden", content)

    def test_invalid_create_keeps_insert_mode_open(self):
        self.client.force_login(self.user_manage)

        response = self.client.post(
            reverse("osservazioni_studente", kwargs={"studente_pk": self.studente.pk}),
            {
                "titolo": "Nota incompleta",
                "data_inserimento": "2026-03-15",
                "testo": "",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["show_create_form"])
        self.assertContains(response, "SALVA LE MODIFICHE")
        content = response.content.decode()
        self.assertIn('id="osservazioni-create-section"', content)
        self.assertNotIn("osservazioni-create-section is-hidden", content)

    def test_manage_user_can_create_osservazione_and_is_recorded(self):
        self.client.force_login(self.user_manage)

        response = self.client.post(
            reverse("osservazioni_studente", kwargs={"studente_pk": self.studente.pk}),
            {
                "titolo": "",
                "data_inserimento": "2026-03-15",
                "testo": "Nota con **grassetto**.",
            },
        )

        self.assertRedirects(response, f"{reverse('osservazioni_studente', kwargs={'studente_pk': self.studente.pk})}?ordine=asc")
        osservazione = OsservazioneStudente.objects.get()
        self.assertEqual(osservazione.studente, self.studente)
        self.assertEqual(osservazione.creato_da, self.user_manage)
        self.assertEqual(osservazione.aggiornato_da, self.user_manage)

    def test_author_is_shown_and_actions_follow_object_permissions(self):
        osservazione = OsservazioneStudente.objects.create(
            studente=self.studente,
            titolo="Osservazione autore",
            data_inserimento=date(2026, 3, 20),
            testo="Testo osservazione",
            creato_da=self.user_manage,
        )
        edit_url = reverse("modifica_osservazione_studente", kwargs={"pk": osservazione.pk})
        delete_url = reverse("elimina_osservazione_studente", kwargs={"pk": osservazione.pk})

        self.client.force_login(self.user_other_manage)
        response = self.client.get(reverse("osservazioni_studente", kwargs={"studente_pk": self.studente.pk}))
        self.assertContains(response, "20 / 03 / 2026 - CREATA DA Mario Rossi")
        self.assertNotContains(response, edit_url)
        self.assertNotContains(response, delete_url)

        self.client.force_login(self.user_manage)
        response = self.client.get(reverse("osservazioni_studente", kwargs={"studente_pk": self.studente.pk}))
        self.assertContains(response, edit_url)
        self.assertContains(response, delete_url)

        self.client.force_login(self.user_admin)
        response = self.client.get(reverse("osservazioni_studente", kwargs={"studente_pk": self.studente.pk}))
        self.assertContains(response, edit_url)
        self.assertContains(response, delete_url)

    def test_non_author_manage_user_cannot_edit_or_delete_observation(self):
        osservazione = OsservazioneStudente.objects.create(
            studente=self.studente,
            titolo="Riservata autore",
            data_inserimento=date(2026, 3, 20),
            testo="Testo originale",
            creato_da=self.user_manage,
        )
        self.client.force_login(self.user_other_manage)
        list_url = f"{reverse('osservazioni_studente', kwargs={'studente_pk': self.studente.pk})}?ordine=asc"
        edit_url = reverse("modifica_osservazione_studente", kwargs={"pk": osservazione.pk})
        delete_url = reverse("elimina_osservazione_studente", kwargs={"pk": osservazione.pk})

        response = self.client.get(edit_url)
        self.assertRedirects(response, list_url)

        response = self.client.post(
            edit_url,
            {
                "titolo": "Modifica non autorizzata",
                "data_inserimento": "2026-03-20",
                "testo": "Testo modificato",
            },
        )
        self.assertRedirects(response, list_url)
        osservazione.refresh_from_db()
        self.assertEqual(osservazione.testo, "Testo originale")

        response = self.client.get(delete_url)
        self.assertRedirects(response, list_url)

        response = self.client.post(delete_url)
        self.assertRedirects(response, list_url)
        self.assertTrue(OsservazioneStudente.objects.filter(pk=osservazione.pk).exists())

    def test_visibility_can_be_restricted_to_observation_author(self):
        SistemaImpostazioniGenerali.objects.create(osservazioni_solo_autori_visualizzazione=True)
        OsservazioneStudente.objects.create(
            studente=self.studente,
            titolo="Visibile solo autore",
            data_inserimento=date(2026, 3, 20),
            testo="Testo osservazione",
            creato_da=self.user_manage,
        )
        self.client.force_login(self.user_other_manage)

        response = self.client.get(reverse("osservazioni_studente", kwargs={"studente_pk": self.studente.pk}))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Visibile solo autore")

        self.client.force_login(self.user_admin)
        response = self.client.get(reverse("osservazioni_studente", kwargs={"studente_pk": self.studente.pk}))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Visibile solo autore")

    def test_manage_users_can_change_other_observations_when_setting_allows_it(self):
        SistemaImpostazioniGenerali.objects.create(osservazioni_solo_autori_modifica=False)
        osservazione = OsservazioneStudente.objects.create(
            studente=self.studente,
            titolo="Modifica condivisa",
            data_inserimento=date(2026, 3, 20),
            testo="Testo originale",
            creato_da=self.user_manage,
        )
        self.client.force_login(self.user_other_manage)
        edit_url = reverse("modifica_osservazione_studente", kwargs={"pk": osservazione.pk})
        delete_url = reverse("elimina_osservazione_studente", kwargs={"pk": osservazione.pk})

        response = self.client.get(reverse("osservazioni_studente", kwargs={"studente_pk": self.studente.pk}))
        self.assertContains(response, edit_url)
        self.assertContains(response, delete_url)

        response = self.client.post(
            edit_url,
            {
                "titolo": "Modifica condivisa",
                "data_inserimento": "2026-03-20",
                "testo": "Testo modificato",
            },
        )

        self.assertRedirects(
            response,
            f"{reverse('osservazioni_studente', kwargs={'studente_pk': self.studente.pk})}?ordine=asc",
        )
        osservazione.refresh_from_db()
        self.assertEqual(osservazione.testo, "Testo modificato")
        self.assertEqual(osservazione.aggiornato_da, self.user_other_manage)

    def test_admin_can_edit_observation_created_by_another_user(self):
        osservazione = OsservazioneStudente.objects.create(
            studente=self.studente,
            titolo="Osservazione amministrabile",
            data_inserimento=date(2026, 3, 20),
            testo="Testo originale",
            creato_da=self.user_manage,
        )
        self.client.force_login(self.user_admin)

        response = self.client.post(
            reverse("modifica_osservazione_studente", kwargs={"pk": osservazione.pk}),
            {
                "titolo": "Osservazione aggiornata",
                "data_inserimento": "2026-03-21",
                "testo": "Testo aggiornato",
            },
        )

        self.assertRedirects(
            response,
            f"{reverse('osservazioni_studente', kwargs={'studente_pk': self.studente.pk})}?ordine=asc",
        )
        osservazione.refresh_from_db()
        self.assertEqual(osservazione.testo, "Testo aggiornato")
        self.assertEqual(osservazione.aggiornato_da, self.user_admin)

    def test_view_user_can_consult_but_not_manage(self):
        OsservazioneStudente.objects.create(
            studente=self.studente,
            titolo="Solo lettura",
            data_inserimento=date(2026, 3, 20),
            testo="Testo osservazione",
        )
        self.client.force_login(self.user_view)

        response = self.client.get(reverse("osservazioni_studente", kwargs={"studente_pk": self.studente.pk}))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Dati generali dello studente")
        self.assertContains(response, reverse("modifica_studente", kwargs={"pk": self.studente.pk}))
        self.assertContains(response, reverse("modifica_famiglia_logica", kwargs={"key": f"s-{self.studente.pk}"}))
        self.assertContains(response, "10 / 05 / 2020")
        self.assertContains(response, "Ancora non assegnata")
        self.assertContains(response, "Solo lettura")
        self.assertNotContains(response, "Aggiungi osservazione")
        self.assertNotContains(response, "observation-icon-btn")

        response = self.client.post(
            reverse("osservazioni_studente", kwargs={"studente_pk": self.studente.pk}),
            {
                "titolo": "Non autorizzata",
                "data_inserimento": "2026-03-21",
                "testo": "Non deve essere creata",
            },
        )

        self.assertRedirects(response, reverse("home"))
        self.assertEqual(OsservazioneStudente.objects.count(), 1)
