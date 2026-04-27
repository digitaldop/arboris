from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from sistema.models import LivelloPermesso, SistemaUtentePermessi

from .models import CategoriaCalendario


class CalendarioAgendaInterfaceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="calendario@example.com",
            email="calendario@example.com",
            password="Password123!",
        )
        SistemaUtentePermessi.objects.create(
            user=self.user,
            permesso_calendario=LivelloPermesso.GESTIONE,
        )
        CategoriaCalendario.objects.create(nome="Didattica", colore="#417690", ordine=1)

    def test_agenda_exposes_category_edit_icon_and_current_script(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse("calendario_agenda"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'class="admin-section-title-btn admin-section-title-icon-btn"')
        self.assertContains(response, f'href="{reverse("lista_categorie_calendario")}"')
        self.assertContains(response, "js/pages/calendario-agenda.js?v=5")
