from datetime import date

from django.test import TestCase

from scuola.models import AnnoScolastico
from servizi_extra.forms.servizi import ServizioExtraForm


class ServiziExtraCurrentSchoolYearDefaultsTests(TestCase):
    def test_servizio_extra_form_defaults_to_current_school_year(self):
        AnnoScolastico.objects.create(
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

        form = ServizioExtraForm()

        self.assertEqual(form.initial["anno_scolastico"], anno_corrente.pk)
