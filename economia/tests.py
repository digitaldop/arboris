from datetime import date

from django.test import TestCase

from economia.forms import CondizioneIscrizioneForm, IscrizioneForm, ScambioRettaForm
from economia.models import StatoIscrizione
from scuola.models import AnnoScolastico


class EconomiaCurrentSchoolYearDefaultsTests(TestCase):
    def setUp(self):
        AnnoScolastico.objects.create(
            nome_anno_scolastico="2024/2025",
            data_inizio=date(2024, 9, 1),
            data_fine=date(2025, 8, 31),
            corrente=False,
        )
        self.anno_corrente = AnnoScolastico.objects.create(
            nome_anno_scolastico="2025/2026",
            data_inizio=date(2025, 9, 1),
            data_fine=date(2026, 8, 31),
            corrente=True,
        )
        self.stato_iscrizione = StatoIscrizione.objects.create(stato_iscrizione="Attiva", ordine=1, attiva=True)

    def test_condizione_iscrizione_form_defaults_to_current_school_year(self):
        form = CondizioneIscrizioneForm()

        self.assertEqual(form.initial["anno_scolastico"], self.anno_corrente.pk)

    def test_iscrizione_form_defaults_to_current_school_year(self):
        form = IscrizioneForm()

        self.assertEqual(form.initial["anno_scolastico"], self.anno_corrente.pk)
        self.assertEqual(form.initial["stato_iscrizione"], self.stato_iscrizione.pk)

    def test_scambio_retta_form_defaults_to_current_school_year(self):
        form = ScambioRettaForm()

        self.assertEqual(form.initial["anno_scolastico"], self.anno_corrente.pk)
