from datetime import date

from django.test import TestCase

from economia.forms import (
    AgevolazioneForm,
    CondizioneIscrizioneForm,
    IscrizioneForm,
    ScambioRettaForm,
    TariffaCondizioneIscrizioneForm,
)
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


class EconomiaCurrencyWidgetTests(TestCase):
    def test_agevolazione_form_marks_annual_amount_as_compact_euro_field(self):
        form = AgevolazioneForm()

        field = form.fields["importo_annuale_agevolazione"]
        self.assertEqual(field.widget.attrs["data-currency"], "EUR")
        self.assertEqual(field.widget.attrs["data-currency-display"], "suffix")
        self.assertIn("currency-field-compact", field.widget.attrs["class"])

    def test_tariffa_form_marks_fee_fields_as_compact_euro_fields(self):
        form = TariffaCondizioneIscrizioneForm()

        retta_field = form.fields["retta_annuale"]
        preiscrizione_field = form.fields["preiscrizione"]

        self.assertEqual(retta_field.widget.attrs["data-currency"], "EUR")
        self.assertEqual(preiscrizione_field.widget.attrs["data-currency"], "EUR")
        self.assertIn("currency-field-compact", retta_field.widget.attrs["class"])
        self.assertIn("currency-field-compact", preiscrizione_field.widget.attrs["class"])
