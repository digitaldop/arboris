from datetime import datetime

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from calendario.data import build_calendar_agenda_bundle
from sistema.models import LivelloPermesso, SistemaUtentePermessi

from .models import (
    AttivitaFamigliaInteressata,
    FamigliaInteressata,
    FonteContattoFamigliaInteressata,
    PrioritaFamigliaInteressata,
    StatoAttivitaFamigliaInteressata,
    StatoFamigliaInteressata,
)


class FamiglieInteressateModuleTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="segreteria@example.com",
            email="segreteria@example.com",
            password="Password123!",
        )
        SistemaUtentePermessi.objects.create(
            user=self.user,
            permesso_famiglie_interessate=LivelloPermesso.GESTIONE,
            permesso_calendario=LivelloPermesso.GESTIONE,
        )

    def famiglia_create_payload(self, **overrides):
        payload = {
            "nome": "",
            "referente_principale": "",
            "telefono": "3331234567",
            "email": "",
            "fonte_contatto": FonteContattoFamigliaInteressata.TELEFONO,
            "fonte_note": "Chiamata ricevuta",
            "stato": StatoFamigliaInteressata.NUOVO_CONTATTO,
            "priorita": PrioritaFamigliaInteressata.NORMALE,
            "anno_scolastico_interesse": "",
            "classe_eta_interesse": "",
            "note": "Prima richiesta informazioni.",
            "referenti-TOTAL_FORMS": "1",
            "referenti-INITIAL_FORMS": "0",
            "referenti-MIN_NUM_FORMS": "0",
            "referenti-MAX_NUM_FORMS": "1000",
            "referenti-0-nome": "",
            "referenti-0-relazione": "",
            "referenti-0-telefono": "",
            "referenti-0-email": "",
            "referenti-0-note": "",
            "minori-TOTAL_FORMS": "1",
            "minori-INITIAL_FORMS": "0",
            "minori-MIN_NUM_FORMS": "0",
            "minori-MAX_NUM_FORMS": "1000",
            "minori-0-nome": "",
            "minori-0-cognome": "",
            "minori-0-data_nascita": "",
            "minori-0-eta_indicativa": "",
            "minori-0-classe_eta_interesse": "",
            "minori-0-note": "",
        }
        payload.update(overrides)
        return payload

    def test_list_uses_new_layout_and_sidebar_entry(self):
        self.client.force_login(self.user)
        FamigliaInteressata.objects.create(
            nome="Famiglia Rossi",
            telefono="3331234567",
            stato=StatoFamigliaInteressata.DA_RICONTATTARE,
        )

        response = self.client.get(reverse("lista_famiglie_interessate"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Famiglie interessate")
        self.assertContains(response, "interested-summary-grid")
        self.assertContains(response, "Contatti e follow-up")
        self.assertContains(response, f'{reverse("crea_famiglia_interessata")}?popup=1')
        self.assertContains(response, 'data-window-popup="1"')
        self.assertContains(response, "width=980,height=820")

    def test_create_accepts_minimal_phone_only_contact(self):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("crea_famiglia_interessata"),
            self.famiglia_create_payload(),
        )

        famiglia = FamigliaInteressata.objects.get()
        self.assertRedirects(response, reverse("modifica_famiglia_interessata", kwargs={"pk": famiglia.pk}))
        self.assertEqual(famiglia.telefono, "3331234567")
        self.assertEqual(famiglia.creata_da, self.user)

    def test_create_form_uses_modern_popup_layout_and_dynamic_children(self):
        self.client.force_login(self.user)

        response = self.client.get(f'{reverse("crea_famiglia_interessata")}?popup=1')

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'body class="popup-page"')
        self.assertContains(response, "interested-editor-layout")
        self.assertContains(response, "interested-card-head-actions")
        self.assertContains(response, 'data-formset-add="referenti"')
        self.assertContains(response, 'data-formset-empty="referenti"')
        self.assertContains(response, 'data-formset-add="minori"')
        self.assertContains(response, 'data-formset-empty="minori"')
        self.assertContains(response, "js/pages/famiglie-interessate-form.js?v=2")

    def test_create_accepts_no_referents_and_multiple_referents(self):
        self.client.force_login(self.user)

        response_without_referents = self.client.post(
            reverse("crea_famiglia_interessata"),
            self.famiglia_create_payload(
                telefono="3330001111",
                **{
                    "referenti-TOTAL_FORMS": "0",
                },
            ),
        )

        famiglia_senza_referenti = FamigliaInteressata.objects.get(telefono="3330001111")
        self.assertRedirects(
            response_without_referents,
            reverse("modifica_famiglia_interessata", kwargs={"pk": famiglia_senza_referenti.pk}),
        )
        self.assertEqual(famiglia_senza_referenti.referenti.count(), 0)

        response_with_referents = self.client.post(
            reverse("crea_famiglia_interessata"),
            self.famiglia_create_payload(
                telefono="3330002222",
                **{
                    "referenti-TOTAL_FORMS": "2",
                    "referenti-0-nome": "Maria Rossi",
                    "referenti-0-relazione": "Madre",
                    "referenti-0-telefono": "3331112222",
                    "referenti-0-email": "maria@example.com",
                    "referenti-0-note": "Preferisce chiamata al mattino.",
                    "referenti-0-principale": "on",
                    "referenti-1-nome": "Luca Rossi",
                    "referenti-1-relazione": "Padre",
                    "referenti-1-telefono": "3333334444",
                    "referenti-1-email": "",
                    "referenti-1-note": "",
                },
            ),
        )

        famiglia_con_referenti = FamigliaInteressata.objects.get(telefono="3330002222")
        self.assertRedirects(
            response_with_referents,
            reverse("modifica_famiglia_interessata", kwargs={"pk": famiglia_con_referenti.pk}),
        )
        self.assertEqual(famiglia_con_referenti.referenti.count(), 2)
        self.assertEqual(
            list(famiglia_con_referenti.referenti.order_by("nome").values_list("nome", "relazione", "principale")),
            [("Luca Rossi", "Padre", False), ("Maria Rossi", "Madre", True)],
        )

    def test_create_accepts_multiple_children(self):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("crea_famiglia_interessata"),
            self.famiglia_create_payload(
                telefono="3337654321",
                **{
                    "minori-TOTAL_FORMS": "2",
                    "minori-0-nome": "Luca",
                    "minori-0-cognome": "Rossi",
                    "minori-0-data_nascita": "2020-05-10",
                    "minori-0-eta_indicativa": "",
                    "minori-0-classe_eta_interesse": "Infanzia",
                    "minori-1-nome": "Anna",
                    "minori-1-cognome": "Rossi",
                    "minori-1-data_nascita": "",
                    "minori-1-eta_indicativa": "3 anni",
                    "minori-1-classe_eta_interesse": "Nido",
                    "minori-1-note": "Possibile inserimento da settembre.",
                },
            ),
        )

        famiglia = FamigliaInteressata.objects.get()
        self.assertRedirects(response, reverse("modifica_famiglia_interessata", kwargs={"pk": famiglia.pk}))
        self.assertEqual(famiglia.minori.count(), 2)
        self.assertEqual(
            list(famiglia.minori.order_by("nome").values_list("nome", "cognome")),
            [("Anna", "Rossi"), ("Luca", "Rossi")],
        )

    def test_detail_and_activity_forms_use_modern_layout(self):
        self.client.force_login(self.user)
        famiglia = FamigliaInteressata.objects.create(nome="Famiglia Verdi", telefono="3330000000")

        detail_response = self.client.get(reverse("modifica_famiglia_interessata", kwargs={"pk": famiglia.pk}))
        activity_response = self.client.get(
            f'{reverse("crea_attivita_famiglia_interessata", kwargs={"pk": famiglia.pk})}?popup=1'
        )

        self.assertEqual(detail_response.status_code, 200)
        self.assertContains(detail_response, "interested-detail-shell")
        self.assertContains(detail_response, "interested-form-grid")
        self.assertContains(detail_response, "interested-editor-layout")
        self.assertEqual(activity_response.status_code, 200)
        self.assertContains(activity_response, 'body class="popup-page"')
        self.assertContains(activity_response, "interested-activity-editor-shell is-popup")

    def test_calendar_includes_followups_only_for_enabled_users(self):
        famiglia = FamigliaInteressata.objects.create(nome="Famiglia Neri", telefono="3335550000")
        scheduled_at = timezone.make_aware(datetime(2026, 5, 14, 10, 30))
        AttivitaFamigliaInteressata.objects.create(
            famiglia=famiglia,
            tipo="follow_up",
            titolo="Ricontattare Famiglia Neri",
            stato=StatoAttivitaFamigliaInteressata.PROGRAMMATA,
            data_programmata=scheduled_at,
            durata_minuti=45,
            calendarizza=True,
        )
        calendar_only_user = User.objects.create_user(
            username="calendar-only@example.com",
            email="calendar-only@example.com",
            password="Password123!",
        )
        SistemaUtentePermessi.objects.create(
            user=calendar_only_user,
            permesso_calendario=LivelloPermesso.GESTIONE,
        )

        enabled_records = build_calendar_agenda_bundle(user=self.user)["records"]
        disabled_records = build_calendar_agenda_bundle(user=calendar_only_user)["records"]

        self.assertTrue(any(record["source"] == "famiglia_interessata" for record in enabled_records))
        self.assertFalse(any(record["source"] == "famiglia_interessata" for record in disabled_records))
