from datetime import date
from unittest.mock import patch

from django.test import TestCase

from .forms import ClasseForm
from .models import AnnoScolastico


class ClasseFormDefaultAnnoScolasticoTests(TestCase):
    def test_prefers_anno_marked_corrente_for_new_class(self):
        anno_passato = AnnoScolastico.objects.create(
            nome_anno_scolastico="2024/2025",
            data_inizio=date(2024, 9, 1),
            data_fine=date(2025, 8, 31),
            corrente=False,
        )
        anno_corrente = AnnoScolastico.objects.create(
            nome_anno_scolastico="2025/2026",
            data_inizio=date(2025, 9, 1),
            data_fine=date(2026, 8, 31),
            corrente=True,
        )

        with patch("scuola.utils.timezone.localdate", return_value=date(2026, 4, 24)):
            form = ClasseForm()

        self.assertEqual(form.initial["anno_scolastico"], anno_corrente.pk)
        self.assertNotEqual(form.initial["anno_scolastico"], anno_passato.pk)

    def test_falls_back_to_anno_matching_current_date_when_no_record_is_marked_corrente(self):
        AnnoScolastico.objects.create(
            nome_anno_scolastico="2024/2025",
            data_inizio=date(2024, 9, 1),
            data_fine=date(2025, 8, 31),
            corrente=False,
        )
        anno_per_data = AnnoScolastico.objects.create(
            nome_anno_scolastico="2025/2026",
            data_inizio=date(2025, 9, 1),
            data_fine=date(2026, 8, 31),
            corrente=False,
        )

        with patch("scuola.utils.timezone.localdate", return_value=date(2026, 4, 24)):
            form = ClasseForm()

        self.assertEqual(form.initial["anno_scolastico"], anno_per_data.pk)

    def test_falls_back_to_most_recent_anno_when_no_current_year_matches_today(self):
        AnnoScolastico.objects.create(
            nome_anno_scolastico="2023/2024",
            data_inizio=date(2023, 9, 1),
            data_fine=date(2024, 8, 31),
            corrente=False,
        )
        anno_piu_recente = AnnoScolastico.objects.create(
            nome_anno_scolastico="2024/2025",
            data_inizio=date(2024, 9, 1),
            data_fine=date(2025, 8, 31),
            corrente=False,
        )

        with patch("scuola.utils.timezone.localdate", return_value=date(2026, 4, 24)):
            form = ClasseForm()

        self.assertEqual(form.initial["anno_scolastico"], anno_piu_recente.pk)
