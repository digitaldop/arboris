from datetime import date
from importlib import import_module
from types import SimpleNamespace
from unittest.mock import patch

from django.apps import apps
from django.contrib.auth.models import AnonymousUser, User
from django.db import connection
from django.test import TestCase
from django.urls import reverse

from scuola.models import AnnoScolastico
from sistema.forms import SistemaUtenteForm
from sistema.models import (
    ComunicazioneFamigliaLog, PERMISSION_MODULE_FIELDS,
    SistemaRuoloPermessi, SistemaUtentePermessi,
)
from sistema.permissions import user_can_communicate_with_families, user_has_module_permission


class FamilyCommunicationPermissionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.role = SistemaRuoloPermessi.objects.create(
            nome="Comunicazioni", permesso_anagrafica="view",
            accesso_comunicazioni_famiglie=True,
        )
        cls.user = User.objects.create_user(username="comunicazioni@example.test")
        cls.profile = SistemaUtentePermessi.objects.create(user=cls.user, ruolo_permessi=cls.role)
        cls.year = AnnoScolastico.objects.create(
            nome_anno_scolastico="2026/2027", data_inizio=date(2026, 9, 1), data_fine=date(2027, 8, 31),
        )
        cls.log = ComunicazioneFamigliaLog.objects.create(oggetto="Comunicazione precedente", messaggio="Testo")

    def setUp(self):
        self.client.force_login(self.user)

    def test_access_and_menu_are_independent_of_module_levels(self):
        for level in ("none", "view", "manage"):
            with self.subTest(level=level):
                self.role.permesso_anagrafica = level
                self.role.save()
                response = self.client.get(reverse("comunicazioni_famiglie"))
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, 'data-sidebar-menu-key="anagrafica_comunicazioni_famiglie"')
                self.assertEqual(response.context["current_permission_module"], "anagrafica")
                self.assertFalse(response.context["current_module_view_only"])
                self.assertEqual(response.context["can_manage_anagrafica"], level == "manage")
                self.assertFalse(response.context["can_view_economia"])

    def test_permission_does_not_allow_editing_people_or_financial_data(self):
        for name in ("crea_studente", "lista_iscrizioni", "configurazione_email_smtp"):
            with self.subTest(name=name):
                self.assertRedirects(self.client.get(reverse(name)), reverse("home"), fetch_redirect_response=False)
        self.assertFalse(user_has_module_permission(self.user, "anagrafica", "manage"))
        self.assertFalse(user_has_module_permission(self.user, "economia"))

    def test_history_and_detail_use_the_same_permission(self):
        for url in (reverse("storico_comunicazioni_famiglie"), reverse("dettaglio_comunicazione_famiglia", args=[self.log.pk])):
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, self.log.oggetto)

    def test_disabled_permission_blocks_direct_access_and_sending(self):
        self.role.accesso_comunicazioni_famiglie = False
        self.role.permesso_anagrafica = self.role.permesso_economia = "manage"
        self.role.save()
        urls = [reverse("comunicazioni_famiglie"), reverse("storico_comunicazioni_famiglie"), reverse("dettaglio_comunicazione_famiglia", args=[self.log.pk])]
        with patch("economia.views.comunicazioni.invia_comunicazione_famiglie") as send:
            for url in urls:
                self.assertRedirects(self.client.get(url), reverse("home"), fetch_redirect_response=False)
            self.assertRedirects(self.client.post(urls[0], {"action": "send"}), reverse("home"), fetch_redirect_response=False)
            send.assert_not_called()
        home = self.client.get(reverse("home"))
        self.assertNotContains(home, 'data-sidebar-menu-key="anagrafica_comunicazioni_famiglie"')

    def test_revoking_role_permission_takes_effect_on_next_request(self):
        self.assertEqual(self.client.get(reverse("comunicazioni_famiglie")).status_code, 200)
        SistemaRuoloPermessi.objects.filter(pk=self.role.pk).update(accesso_comunicazioni_famiglie=False)
        self.assertRedirects(self.client.get(reverse("comunicazioni_famiglie")), reverse("home"), fetch_redirect_response=False)

    def test_inactive_role_cannot_use_copied_or_full_permissions(self):
        self.role.attivo = False
        self.role.controllo_completo = True
        self.role.save()
        self.profile.accesso_comunicazioni_famiglie = True
        self.profile.controllo_completo = True
        self.profile.save()
        self.assertFalse(user_can_communicate_with_families(self.user))
        self.assertRedirects(self.client.get(reverse("comunicazioni_famiglie")), reverse("home"), fetch_redirect_response=False)

    def test_superusers_and_full_control_roles_keep_access(self):
        self.role.controllo_completo = True
        self.role.accesso_comunicazioni_famiglie = False
        self.role.save()
        self.assertTrue(user_can_communicate_with_families(self.user))
        admin = User.objects.create_superuser(username="communications-admin")
        self.assertTrue(user_can_communicate_with_families(admin))
        self.assertFalse(user_can_communicate_with_families(AnonymousUser()))

    def test_anonymous_visitors_are_sent_to_login(self):
        self.client.logout()
        response = self.client.get(reverse("comunicazioni_famiglie"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response.url)

    def test_authorized_user_can_preview_and_send_without_module_write_access(self):
        recipient = {"key": "family:1", "email": "family@example.test"}
        stats = {"studenti": 1, "studenti_senza_email": 0, "destinatari": 1, "email_uniche": 1, "duplicati": 0}
        data = {"anni_scolastici": [self.year.pk], "oggetto": "Avviso", "messaggio": "Messaggio", "destinatari": [recipient["key"]]}
        with patch("economia.views.comunicazioni.costruisci_destinatari_famiglie", return_value=([], [recipient], stats)):
            with patch("economia.views.comunicazioni.invia_comunicazione_famiglie", return_value={"log": self.log, "fallite": 0, "inviate": 1}) as send:
                preview = self.client.post(reverse("comunicazioni_famiglie"), {**data, "action": "preview"})
                self.assertEqual(preview.status_code, 200)
                send.assert_not_called()
                response = self.client.post(reverse("comunicazioni_famiglie"), {**data, "action": "send"})
                self.assertEqual(response.status_code, 200)
                send.assert_called_once()
                self.assertEqual(send.call_args.kwargs["utente"].pk, self.user.pk)
                self.assertEqual(send.call_args.kwargs["destinatari"], [recipient])
                self.assertFalse(response.context["current_module_view_only"])

    def test_role_form_saves_permission_and_syncs_user_profile(self):
        admin = User.objects.create_superuser(username="role-admin")
        self.client.force_login(admin)
        url = reverse("modifica_ruolo_utente", args=[self.role.pk])
        self.assertContains(self.client.get(url), 'name="accesso_comunicazioni_famiglie"')
        data = {
            "nome": self.role.nome, "colore_principale": self.role.colore_principale, "attivo": "on",
            **{field: "none" for field in PERMISSION_MODULE_FIELDS.values()},
            "permesso_anagrafica": "view",
        }
        for enabled in (False, True):
            with self.subTest(enabled=enabled):
                payload = {**data, "accesso_comunicazioni_famiglie": "on"} if enabled else data
                self.assertEqual(self.client.post(url, payload).status_code, 302)
                self.role.refresh_from_db()
                self.profile.refresh_from_db()
                self.assertEqual(self.role.accesso_comunicazioni_famiglie, enabled)
                self.assertEqual(self.profile.accesso_comunicazioni_famiglie, enabled)
                self.assertEqual(self.role.permesso_anagrafica, "view")

    def test_user_assignment_copies_role_permission(self):
        form = SistemaUtenteForm(data={
            "first_name": "Ada", "last_name": "Test", "email": "ada@example.test",
            "password": "Local-test-2026!", "is_active": "on", "ruolo_permessi": self.role.pk,
        })
        self.assertTrue(form.is_valid(), form.errors)
        user = form.save()
        self.assertTrue(user.profilo_permessi.accesso_comunicazioni_famiglie)
        self.assertTrue(user_can_communicate_with_families(user))

    def test_migration_preserves_previous_access_without_granting_it_to_viewers(self):
        old_role = SistemaRuoloPermessi.objects.create(nome="Vecchia segreteria", permesso_economia="manage")
        viewer_role = SistemaRuoloPermessi.objects.create(nome="Visualizzazione", permesso_anagrafica="view")
        legacy = User.objects.create_user(username="legacy-communications")
        legacy_profile = SistemaUtentePermessi.objects.create(user=legacy, permesso_economia="manage")
        linked_user = User.objects.create_user(username="linked-communications")
        linked = SistemaUtentePermessi.objects.create(user=linked_user, ruolo_permessi=old_role)
        migrate = import_module("sistema.migrations.0012_accesso_comunicazioni_famiglie").preserve_existing_access
        migrate(apps, SimpleNamespace(connection=connection))
        for obj in (old_role, viewer_role, legacy_profile, linked):
            obj.refresh_from_db()
        self.assertTrue(old_role.accesso_comunicazioni_famiglie)
        self.assertTrue(legacy_profile.accesso_comunicazioni_famiglie)
        self.assertTrue(linked.accesso_comunicazioni_famiglie)
        self.assertFalse(viewer_role.accesso_comunicazioni_famiglie)
