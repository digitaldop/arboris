from datetime import date
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from .forms import AnnoScolasticoForm, ClasseForm, GruppoClasseForm
from .models import AnnoScolastico, Classe, GruppoClasse


class ClasseFormCatalogTests(TestCase):
    def test_class_form_creates_global_catalog_entry(self):
        form = ClasseForm(
            data={
                "nome_classe": "Prima Elementare",
                "sezione_classe": "",
                "ordine_classe": "1",
                "attiva": "on",
                "note": "",
            }
        )

        self.assertTrue(form.is_valid(), form.errors)
        self.assertNotIn("anno_scolastico", form.fields)
        classe = form.save()
        self.assertEqual(str(classe), "Prima Elementare")


class AnnoScolasticoFormValidationTests(TestCase):
    def test_active_school_years_cannot_overlap(self):
        AnnoScolastico.objects.create(
            nome_anno_scolastico="2025/2026",
            data_inizio=date(2025, 9, 1),
            data_fine=date(2026, 8, 31),
            attivo=True,
        )
        form = AnnoScolasticoForm(
            data={
                "nome_anno_scolastico": "Anno sovrapposto",
                "data_inizio": "2026-01-01",
                "data_fine": "2026-12-31",
                "attivo": "on",
                "note": "",
            }
        )

        self.assertFalse(form.is_valid())
        self.assertIn("date sovrapposte", str(form.errors))

    def test_inactive_school_years_can_overlap(self):
        AnnoScolastico.objects.create(
            nome_anno_scolastico="2025/2026",
            data_inizio=date(2025, 9, 1),
            data_fine=date(2026, 8, 31),
            attivo=True,
        )
        form = AnnoScolasticoForm(
            data={
                "nome_anno_scolastico": "Archivio manuale",
                "data_inizio": "2026-01-01",
                "data_fine": "2026-12-31",
                "attivo": "",
                "note": "",
            }
        )

        self.assertTrue(form.is_valid(), form.errors)


class GruppoClasseFormTests(TestCase):
    def setUp(self):
        self.anno = AnnoScolastico.objects.create(
            nome_anno_scolastico="2025/2026",
            data_inizio=date(2025, 9, 1),
            data_fine=date(2026, 8, 31),
        )
        self.altro_anno = AnnoScolastico.objects.create(
            nome_anno_scolastico="2026/2027",
            data_inizio=date(2026, 9, 1),
            data_fine=date(2027, 8, 31),
        )
        self.quarta = Classe.objects.create(
            nome_classe="Quarta Elementare",
            ordine_classe=4,
        )
        self.quinta = Classe.objects.create(
            nome_classe="Quinta Elementare",
            ordine_classe=5,
        )
        self.prima_futura = Classe.objects.create(
            nome_classe="Prima Elementare",
            ordine_classe=1,
        )

    def test_creates_group_with_multiple_classes(self):
        form = GruppoClasseForm(
            data={
                "nome_gruppo_classe": "Quarta - Quinta Elementare",
                "anno_scolastico": self.anno.pk,
                "classi": [self.quarta.pk, self.quinta.pk],
                "attivo": "on",
                "note": "",
            }
        )

        self.assertTrue(form.is_valid(), form.errors)
        gruppo = form.save()

        self.assertEqual(gruppo.classi.count(), 2)
        self.assertIn(self.quarta, gruppo.classi.all())
        self.assertIn(self.quinta, gruppo.classi.all())

    def test_rejects_single_class_pluriclasse(self):
        form = GruppoClasseForm(
            data={
                "nome_gruppo_classe": "Gruppo incompleto",
                "anno_scolastico": self.anno.pk,
                "classi": [self.quarta.pk],
                "attivo": "on",
                "note": "",
            }
        )

        self.assertFalse(form.is_valid())
        self.assertIn("classi", form.errors)


class ListaAnniScolasticiTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="scuola@example.com",
            email="scuola@example.com",
            password="Password123!",
        )
        self.client.force_login(self.user)

    def test_lista_anni_scolastici_separates_current_future_and_past_years(self):
        anno_passato = AnnoScolastico.objects.create(
            nome_anno_scolastico="2024/2025",
            data_inizio=date(2024, 9, 1),
            data_fine=date(2025, 8, 31),
        )
        anno_corrente = AnnoScolastico.objects.create(
            nome_anno_scolastico="2025/2026",
            data_inizio=date(2025, 9, 1),
            data_fine=date(2026, 8, 31),
        )
        anno_futuro = AnnoScolastico.objects.create(
            nome_anno_scolastico="2026/2027",
            data_inizio=date(2026, 9, 1),
            data_fine=date(2027, 8, 31),
        )

        with patch("scuola.views.timezone.localdate", return_value=date(2026, 4, 25)):
            response = self.client.get(reverse("lista_anni_scolastici"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            list(response.context["anni_correnti_e_futuri"]),
            [anno_corrente, anno_futuro],
        )
        self.assertEqual(list(response.context["anni_passati"]), [anno_passato])
        self.assertContains(response, "Anni scolastici passati")
