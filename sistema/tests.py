from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from .models import LivelloPermesso, SistemaUtentePermessi


class AuthenticationInterfaceTests(TestCase):
    def setUp(self):
        self.password = "Password123!"
        self.user = User.objects.create_user(
            username="operatore@example.com",
            email="operatore@example.com",
            password=self.password,
            first_name="Mario",
            last_name="Rossi",
        )

    def test_home_requires_login(self):
        response = self.client.get(reverse("home"))

        self.assertRedirects(response, f"{reverse('login')}?next={reverse('home')}")

    def test_school_routes_require_login(self):
        response = self.client.get(reverse("lista_anni_scolastici"))

        self.assertRedirects(
            response,
            f"{reverse('login')}?next={reverse('lista_anni_scolastici')}",
        )

    def test_login_page_renders_browser_friendly_controls(self):
        next_url = reverse("lista_famiglie")

        response = self.client.get(reverse("login"), {"next": next_url})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="remember_me"')
        self.assertContains(response, 'autocomplete="username"')
        self.assertContains(response, 'autocomplete="current-password"')
        self.assertContains(response, f'<input type="hidden" name="next" value="{next_url}">', html=True)

    def test_login_with_remember_me_keeps_session_persistent(self):
        response = self.client.post(
            reverse("login"),
            {
                "username": self.user.username,
                "password": self.password,
                "remember_me": "on",
                "next": reverse("home"),
            },
        )

        self.assertRedirects(response, reverse("home"))
        self.assertFalse(self.client.session.get_expire_at_browser_close())

    def test_login_without_remember_me_expires_on_browser_close(self):
        response = self.client.post(
            reverse("login"),
            {
                "username": self.user.username,
                "password": self.password,
                "next": reverse("home"),
            },
        )

        self.assertRedirects(response, reverse("home"))
        self.assertTrue(self.client.session.get_expire_at_browser_close())

    def test_home_hides_module_sections_when_user_has_no_permissions(self):
        SistemaUtentePermessi.objects.create(user=self.user)
        self.client.force_login(self.user)

        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context["can_view_anagrafica"])
        self.assertFalse(response.context["can_view_economia"])
        self.assertFalse(response.context["can_view_gestione_amministrativa"])
        self.assertNotContains(response, reverse("lista_famiglie"))
        self.assertNotContains(response, reverse("lista_iscrizioni"))
        self.assertNotContains(response, reverse("lista_dipendenti"))


class SidebarEconomiaTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="economia@example.com",
            email="economia@example.com",
            password="Password123!",
        )
        SistemaUtentePermessi.objects.create(
            user=self.user,
            permesso_economia=LivelloPermesso.VISUALIZZAZIONE,
        )

    def test_home_renders_economia_sidebar_in_requested_order(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        content = response.content.decode("utf-8")
        start = content.index('id="sidebar-economia-panel"')
        end = content.index('data-sidebar-section-key="scuola"')
        economia_section = content[start:end]

        labels_in_order = [
            "Verifica situazione rette",
            "Fondo accantonamento",
            "<span>Scambi retta</span>",
            "Scambio retta",
            "Tariffe scambio retta",
            "<span>Iscrizioni</span>",
            "Iscrizioni",
            "Stati iscrizione",
            "Rate iscrizione",
            "<span>Impostazioni rette</span>",
        ]

        previous_index = -1
        for label in labels_in_order:
            current_index = economia_section.index(label)
            self.assertGreater(current_index, previous_index)
            previous_index = current_index
