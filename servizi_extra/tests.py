from datetime import date
from unittest import skip

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from anagrafica.models import Studente
from scuola.models import AnnoScolastico
from servizi_extra.forms.servizi import ServizioExtraForm
from servizi_extra.models import IscrizioneServizioExtra, ServizioExtra, TariffaServizioExtra


class ServiziExtraCurrentSchoolYearDefaultsTests(TestCase):
    def test_servizio_extra_form_defaults_to_current_school_year(self):
        AnnoScolastico.objects.create(
            nome_anno_scolastico="2024/2025",
            data_inizio=date(2024, 9, 1),
            data_fine=date(2025, 8, 31),
        )
        anno_corrente = AnnoScolastico.objects.create(
            nome_anno_scolastico="2025/2026",
            data_inizio=date(2025, 9, 1),
            data_fine=date(2026, 8, 31),
        )

        form = ServizioExtraForm()

        self.assertEqual(form.initial["anno_scolastico"], anno_corrente.pk)


class ServiziExtraServiziLayoutTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser(
            username="admin@example.com",
            email="admin@example.com",
            password="Password123!",
        )
        self.anno = AnnoScolastico.objects.create(
            nome_anno_scolastico="2025/2026",
            data_inizio=date(2025, 9, 1),
            data_fine=date(2026, 8, 31),
        )

    def test_servizi_list_renders_new_layout_and_popup_actions(self):
        servizio = ServizioExtra.objects.create(
            anno_scolastico=self.anno,
            nome_servizio="Doposcuola",
            descrizione="Servizio pomeridiano",
        )
        self.client.force_login(self.user)

        response = self.client.get(reverse("lista_servizi_extra"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "servizi-extra-list-shell")
        self.assertContains(response, "data-servizi-extra-search")
        self.assertContains(response, f"{reverse('crea_servizio_extra')}?popup=1")
        self.assertContains(response, f"{reverse('modifica_servizio_extra', args=[servizio.pk])}?popup=1")
        self.assertContains(response, f"{reverse('elimina_servizio_extra', args=[servizio.pk])}?popup=1")

    def test_popup_create_servizio_closes_and_refreshes_parent(self):
        self.client.force_login(self.user)

        response = self.client.post(
            f"{reverse('crea_servizio_extra')}?popup=1",
            {
                "anno_scolastico": self.anno.pk,
                "nome_servizio": "Mensa",
                "ordine": "",
                "descrizione": "Servizio mensa",
                "attiva": "on",
                "note": "",
                "popup": "1",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "window.close()")
        self.assertTrue(ServizioExtra.objects.filter(nome_servizio="Mensa").exists())


class ServiziExtraTariffeLayoutTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser(
            username="tariffe@example.com",
            email="tariffe@example.com",
            password="Password123!",
        )
        self.anno = AnnoScolastico.objects.create(
            nome_anno_scolastico="2025/2026",
            data_inizio=date(2025, 9, 1),
            data_fine=date(2026, 8, 31),
        )
        self.servizio = ServizioExtra.objects.create(
            anno_scolastico=self.anno,
            nome_servizio="Doposcuola",
            descrizione="Servizio pomeridiano",
        )

    def test_tariffe_list_renders_new_layout_and_popup_actions(self):
        tariffa = TariffaServizioExtra.objects.create(
            servizio=self.servizio,
            nome_tariffa="Mensile",
            rateizzata=True,
        )
        tariffa.rate_config.create(
            numero_rata=1,
            descrizione="Rata 1",
            importo="120.00",
            data_scadenza=date(2026, 1, 31),
        )
        self.client.force_login(self.user)

        response = self.client.get(reverse("lista_tariffe_servizi_extra"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "servizi-extra-tariffe-list-shell")
        self.assertContains(response, "data-servizi-extra-tariffe-search")
        self.assertContains(response, f"{reverse('crea_tariffa_servizio_extra')}?popup=1")
        self.assertContains(response, f"{reverse('modifica_tariffa_servizio_extra', args=[tariffa.pk])}?popup=1")
        self.assertContains(response, f"{reverse('elimina_tariffa_servizio_extra', args=[tariffa.pk])}?popup=1")

    def test_popup_create_tariffa_renders_new_layout(self):
        self.client.force_login(self.user)

        response = self.client.get(f"{reverse('crea_tariffa_servizio_extra')}?popup=1&servizio={self.servizio.pk}")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "servizi-extra-tariffa-form-shell")
        self.assertContains(response, "rate-config-table")
        self.assertContains(response, 'name="popup" value="1"')

    def test_popup_create_tariffa_closes_and_refreshes_parent(self):
        self.client.force_login(self.user)

        response = self.client.post(
            f"{reverse('crea_tariffa_servizio_extra')}?popup=1",
            {
                "servizio": self.servizio.pk,
                "nome_tariffa": "Annuale",
                "rateizzata": "",
                "attiva": "on",
                "note": "",
                "popup": "1",
                "rate-TOTAL_FORMS": "1",
                "rate-INITIAL_FORMS": "0",
                "rate-MIN_NUM_FORMS": "0",
                "rate-MAX_NUM_FORMS": "1000",
                "rate-0-numero_rata": "1",
                "rate-0-descrizione": "Unica soluzione",
                "rate-0-importo": "240,00",
                "rate-0-data_scadenza": "2026-01-31",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "window.close()")
        self.assertTrue(TariffaServizioExtra.objects.filter(nome_tariffa="Annuale").exists())


@skip("Legacy test basato sulla tabella anagrafica.Famiglia rimossa.")
class ServiziExtraIscrizioniLayoutTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser(
            username="iscrizioni@example.com",
            email="iscrizioni@example.com",
            password="Password123!",
        )
        self.anno = AnnoScolastico.objects.create(
            nome_anno_scolastico="2025/2026",
            data_inizio=date(2025, 9, 1),
            data_fine=date(2026, 8, 31),
        )
        self.stato_famiglia = StatoRelazioneFamiglia.objects.create(stato="Iscritta")
        self.famiglia = Famiglia.objects.create(
            cognome_famiglia="Rossi",
            stato_relazione_famiglia=self.stato_famiglia,
        )
        self.studente = Studente.objects.create(
            famiglia=self.famiglia,
            nome="Mario",
            cognome="Rossi",
        )
        self.servizio = ServizioExtra.objects.create(
            anno_scolastico=self.anno,
            nome_servizio="Doposcuola",
            descrizione="Servizio pomeridiano",
        )
        self.tariffa = TariffaServizioExtra.objects.create(
            servizio=self.servizio,
            nome_tariffa="Mensile",
        )
        self.tariffa.rate_config.create(
            numero_rata=1,
            descrizione="Rata 1",
            importo="120.00",
            data_scadenza=date(2026, 1, 31),
        )

    def test_iscrizioni_list_renders_new_layout_and_popup_actions(self):
        iscrizione = IscrizioneServizioExtra.objects.create(
            studente=self.studente,
            servizio=self.servizio,
            tariffa=self.tariffa,
            data_iscrizione=date(2025, 9, 1),
        )
        iscrizione.sync_rate_schedule()
        self.client.force_login(self.user)

        response = self.client.get(reverse("lista_iscrizioni_servizi_extra"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "servizi-extra-iscrizioni-list-shell")
        self.assertContains(response, "data-servizi-extra-iscrizioni-search")
        self.assertContains(response, f"{reverse('crea_iscrizione_servizio_extra')}?popup=1")
        self.assertContains(response, f"{reverse('modifica_iscrizione_servizio_extra', args=[iscrizione.pk])}?popup=1")
        self.assertContains(response, f"{reverse('elimina_iscrizione_servizio_extra', args=[iscrizione.pk])}?popup=1")

    def test_popup_create_iscrizione_renders_new_layout(self):
        self.client.force_login(self.user)

        response = self.client.get(f"{reverse('crea_iscrizione_servizio_extra')}?popup=1&servizio={self.servizio.pk}")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "servizi-extra-iscrizione-form-shell")
        self.assertContains(response, 'name="popup" value="1"')
        self.assertContains(response, "Le tariffe disponibili si aggiornano")

    def test_popup_create_iscrizione_closes_and_refreshes_parent(self):
        self.client.force_login(self.user)

        response = self.client.post(
            f"{reverse('crea_iscrizione_servizio_extra')}?popup=1",
            {
                "studente": self.studente.pk,
                "servizio": self.servizio.pk,
                "tariffa": self.tariffa.pk,
                "data_iscrizione": "2025-09-01",
                "data_fine_iscrizione": "",
                "attiva": "on",
                "note_amministrative": "",
                "note": "",
                "popup": "1",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "window.close()")
        self.assertTrue(IscrizioneServizioExtra.objects.filter(studente=self.studente, servizio=self.servizio).exists())

    def test_rate_list_renders_new_layout_and_live_search(self):
        iscrizione = IscrizioneServizioExtra.objects.create(
            studente=self.studente,
            servizio=self.servizio,
            tariffa=self.tariffa,
            data_iscrizione=date(2025, 9, 1),
        )
        iscrizione.sync_rate_schedule()
        rata = iscrizione.rate.first()
        self.client.force_login(self.user)

        response = self.client.get(reverse("lista_rate_servizi_extra"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "servizi-extra-rate-list-shell")
        self.assertContains(response, "data-servizi-extra-rate-search")
        self.assertContains(response, f"{reverse('modifica_rata_servizio_extra', args=[rata.pk])}")
