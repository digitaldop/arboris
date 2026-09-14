from datetime import date
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from anagrafica.models import Familiare, Studente, StudenteFamiliare
from economia.comunicazioni_famiglie import (
    classi_comunicazione_disponibili, costruisci_destinatari_famiglie,
    filtra_destinatari_famiglie, invia_comunicazione_famiglie,
)
from economia.models import CondizioneIscrizione, Iscrizione, StatoIscrizione
from scuola.models import AnnoScolastico, Classe, GruppoClasse
from sistema.models import ComunicazioneFamigliaLog, ConfigurazioneEmailSMTP


class CommunicationClassFilterTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_superuser(username="class-communications")
        cls.year = AnnoScolastico.objects.create(nome_anno_scolastico="2026/2027", data_inizio=date(2026, 9, 1), data_fine=date(2027, 8, 31))
        cls.old_year = AnnoScolastico.objects.create(nome_anno_scolastico="2025/2026", data_inizio=date(2025, 9, 1), data_fine=date(2026, 8, 31))
        cls.condition = CondizioneIscrizione.objects.create(nome_condizione_iscrizione="Standard", anno_scolastico=cls.year, numero_mensilita_default=10)
        cls.old_condition = CondizioneIscrizione.objects.create(nome_condizione_iscrizione="Standard precedente", anno_scolastico=cls.old_year, numero_mensilita_default=10)
        cls.state = StatoIscrizione.objects.create(stato_iscrizione="Attiva", attiva=True)
        cls.a = Classe.objects.create(nome_classe="Prima", sezione_classe="A", ordine_classe=1)
        cls.b = Classe.objects.create(nome_classe="Seconda", sezione_classe="A", ordine_classe=2)
        cls.c = Classe.objects.create(nome_classe="Terza", ordine_classe=3)
        cls.unused = Classe.objects.create(nome_classe="Quarta", ordine_classe=4)
        cls.group = GruppoClasse.objects.create(nome_gruppo_classe="Primaria unita", anno_scolastico=cls.year)
        cls.group.classi.set([cls.a, cls.b])
        cls.parent = Familiare.objects.create(nome="Paola", cognome="Rossi", email="rossi@example.test")

        def enroll(name, classroom, email, *, parent=None, group=None, year=None, active=True):
            student = Studente.objects.create(nome=name, cognome="Test")
            parent = parent or Familiare.objects.create(nome="Genitore", cognome=name, email=email)
            StudenteFamiliare.objects.create(studente=student, familiare=parent)
            return Iscrizione.objects.create(
                studente=student, anno_scolastico=year or cls.year,
                condizione_iscrizione=cls.old_condition if year else cls.condition,
                stato_iscrizione=cls.state, classe=classroom, gruppo_classe=group, attiva=active,
            )

        cls.enrollment_a = enroll("Anna", cls.a, "", parent=cls.parent, group=cls.group)
        cls.enrollment_b = enroll("Bruno", cls.b, "", parent=cls.parent, group=cls.group)
        cls.enrollment_b_outside = enroll("Carlo", cls.b, "carlo@example.test")
        cls.enrollment_c = enroll("Daria", cls.c, "daria@example.test")
        cls.enrollment_none = enroll("Eva", None, "eva@example.test")
        cls.enrollment_old = enroll("Fabio", cls.a, "fabio@example.test", year=cls.old_year)
        enroll("Inattivo", cls.unused, "inactive@example.test", active=False)
        cls.log = ComunicazioneFamigliaLog.objects.create(utente=cls.user, oggetto="Test", messaggio="Messaggio")

    def setUp(self):
        self.client.force_login(self.user)

    def recipients(self, *, years=None, classes=None):
        groups, recipients, _ = costruisci_destinatari_famiglie(years or [self.year])
        return filtra_destinatari_famiglie(groups, recipients, classes)

    def payload(self, *, classes=None, action="preview", recipients=None):
        return {
            "anni_scolastici": [self.year.pk], "anni_destinatari": [self.year.pk],
            "ambito_destinatari": "classi" if classes is not None else "tutti",
            "classi": classes or [], "action": action,
            "oggetto": "Riunione", "messaggio": "Comunicazione mirata",
            "destinatari": recipients or [],
        }

    def test_single_class_does_not_include_other_classes_in_the_same_group(self):
        _, recipients, stats = self.recipients(classes=[f"classe:{self.a.pk}"])
        self.assertEqual([item["iscrizione_id"] for item in recipients], [self.enrollment_a.pk])
        self.assertEqual(stats["email_uniche"], 1)
        self.assertIn("Prima A", recipients[0]["classe_label"])
        self.assertIn("Primaria unita", recipients[0]["classe_label"])

    def test_multiple_classes_use_union_and_keep_siblings(self):
        _, recipients, stats = self.recipients(classes=[f"classe:{self.a.pk}", f"classe:{self.b.pk}"])
        self.assertEqual({item["iscrizione_id"] for item in recipients}, {self.enrollment_a.pk, self.enrollment_b.pk, self.enrollment_b_outside.pk})
        self.assertEqual((stats["destinatari"], stats["email_uniche"], stats["duplicati"]), (3, 2, 1))

    def test_group_filter_uses_the_assigned_group(self):
        _, recipients, _ = self.recipients(classes=[f"gruppo:{self.group.pk}"])
        self.assertEqual({item["iscrizione_id"] for item in recipients}, {self.enrollment_a.pk, self.enrollment_b.pk})

    def test_all_classes_and_unassigned_class(self):
        _, recipients, stats = self.recipients()
        self.assertEqual((len(recipients), stats["email_uniche"]), (5, 4))
        _, unassigned, _ = self.recipients(classes=["senza_classe"])
        self.assertEqual([item["iscrizione_id"] for item in unassigned], [self.enrollment_none.pk])

    def test_available_classes_follow_active_enrollments_and_selected_years(self):
        groups, _, _ = self.recipients()
        options = dict(classi_comunicazione_disponibili(groups))
        self.assertNotIn(f"classe:{self.unused.pk}", options)
        old_groups, _, _ = self.recipients(years=[self.old_year])
        old_options = dict(classi_comunicazione_disponibili(old_groups))
        self.assertEqual(set(old_options), {f"classe:{self.a.pk}"})

    def test_class_filter_spans_only_the_selected_school_years(self):
        _, recipients, _ = self.recipients(years=[self.year, self.old_year], classes=[f"classe:{self.a.pk}"])
        self.assertEqual({item["iscrizione_id"] for item in recipients}, {self.enrollment_a.pk, self.enrollment_old.pk})

    def test_groups_classes_and_contact_emails_are_loaded_in_four_queries(self):
        with self.assertNumQueries(4):
            groups, recipients, _ = costruisci_destinatari_famiglie([self.year])
            self.assertEqual(len(classi_comunicazione_disponibili(groups)), 5)
            self.assertEqual(len(recipients), 5)

    def test_preview_selects_matching_recipients_and_keeps_message(self):
        response = self.client.post(reverse("comunicazioni_famiglie"), self.payload(classes=[f"classe:{self.a.pk}"]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["selected_keys"]), 1)
        self.assertEqual(response.context["statistiche"]["studenti"], 1)
        self.assertContains(response, "Comunicazione mirata")
        self.assertContains(response, 'name="classi"')

    def test_empty_manual_selection_remains_empty_after_preview_and_send(self):
        payload = {**self.payload(classes=[f"classe:{self.a.pk}"]), "selezione_presentata": "1"}
        response = self.client.post(reverse("comunicazioni_famiglie"), payload)
        self.assertFalse(response.context["selected_keys"])
        with patch("economia.views.comunicazioni.invia_comunicazione_famiglie") as send:
            response = self.client.post(reverse("comunicazioni_famiglie"), {**payload, "action": "send"})
            send.assert_not_called()
            self.assertFalse(response.context["selected_keys"])
            self.assertContains(response, "Seleziona almeno un destinatario.")

    def test_no_selected_class_and_unknown_classes_never_send(self):
        for classes in ([], ["classe:999999"], [f"classe:{self.unused.pk}"]):
            with self.subTest(classes=classes):
                with patch("economia.views.comunicazioni.invia_comunicazione_famiglie") as send:
                    response = self.client.post(reverse("comunicazioni_famiglie"), self.payload(classes=classes, action="send"))
                    send.assert_not_called()
                    self.assertIn("classi", response.context["form"].errors)
                    self.assertFalse(response.context["selected_keys"])
                    self.assertFalse(response.context["destinatari"])

    def test_out_of_filter_recipient_blocks_the_entire_send(self):
        _, all_recipients, _ = self.recipients()
        with patch("economia.views.comunicazioni.invia_comunicazione_famiglie") as send:
            response = self.client.post(reverse("comunicazioni_famiglie"), self.payload(
                classes=[f"classe:{self.a.pk}"], action="send", recipients=[item["key"] for item in all_recipients],
            ))
            send.assert_not_called()
            self.assertContains(response, "I destinatari o le classi sono cambiati.")

    def test_changed_enrollment_cannot_send_using_a_stale_class_selection(self):
        _, recipients, _ = self.recipients(classes=[f"gruppo:{self.group.pk}"])
        self.enrollment_a.gruppo_classe = None
        self.enrollment_a.save()
        with patch("economia.views.comunicazioni.invia_comunicazione_famiglie") as send:
            response = self.client.post(reverse("comunicazioni_famiglie"), self.payload(
                classes=[f"gruppo:{self.group.pk}"], action="send", recipients=[item["key"] for item in recipients],
            ))
            send.assert_not_called()
            self.assertTrue(response.context["form"].non_field_errors())

    def test_manual_subset_is_used_for_sending_and_preserved_after_error(self):
        _, recipients, _ = self.recipients(classes=[f"classe:{self.b.pk}"])
        payload = {**self.payload(classes=[f"classe:{self.b.pk}"], action="send", recipients=[recipients[0]["key"]]), "selezione_presentata": "1"}
        with patch("economia.views.comunicazioni.invia_comunicazione_famiglie", return_value={"log": self.log, "inviate": 1, "fallite": 0}) as send:
            response = self.client.post(reverse("comunicazioni_famiglie"), payload)
            self.assertEqual(response.status_code, 200)
            self.assertEqual([item["key"] for item in send.call_args.kwargs["destinatari"]], [recipients[0]["key"]])
        with patch("economia.views.comunicazioni.invia_comunicazione_famiglie") as send:
            response = self.client.post(reverse("comunicazioni_famiglie"), {**payload, "oggetto": ""})
            send.assert_not_called()
            self.assertEqual(response.context["selected_keys"], {recipients[0]["key"]})

    def test_siblings_and_overlapping_filters_produce_one_email_and_keep_class_in_log(self):
        _, recipients, _ = self.recipients(classes=[f"gruppo:{self.group.pk}", f"classe:{self.a.pk}"])
        config = ConfigurazioneEmailSMTP.objects.create(host="smtp.example.test", port=587, email_mittente="school@example.test")
        with patch("economia.comunicazioni_famiglie.crea_connessione_smtp"):
            with patch("economia.comunicazioni_famiglie.invia_email_singola", return_value=1) as send:
                result = invia_comunicazione_famiglie(configurazione=config, destinatari=recipients, oggetto="Test", messaggio="Test", anni_scolastici=[self.year], utente=self.user)
        send.assert_called_once()
        self.assertEqual(result["duplicati_saltati"], 1)
        self.assertTrue(all(item["classi_keys"] for item in result["log"].dettagli_destinatari))
