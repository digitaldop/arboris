from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from sistema.models import LivelloPermesso, SistemaUtentePermessi

from .models import PianoAccantonamento


class FondoAccantonamentoListaTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="fondo@example.com",
            email="fondo@example.com",
            password="Password123!",
        )
        SistemaUtentePermessi.objects.create(
            user=self.user,
            permesso_economia=LivelloPermesso.VISUALIZZAZIONE,
        )

    def test_lista_piani_non_mostra_paginazione(self):
        for index in range(12):
            PianoAccantonamento.objects.create(
                nome=f"Piano accantonamento {index + 1:02d}",
                sempre_attivo=True,
            )

        self.client.force_login(self.user)
        response = self.client.get(reverse("fondo_piano_lista"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Piano accantonamento", count=12)
        self.assertNotContains(response, "Risultati per pagina")
        self.assertNotContains(response, "fondo-plans-pager")
        self.assertNotContains(response, "fondo-plans-list-footer")
