from datetime import date
from decimal import Decimal

from django.test import TestCase

from anagrafica.models import Famiglia, Familiare, RelazioneFamiliare, StatoRelazioneFamiglia, Studente
from economia.forms import (
    AgevolazioneForm,
    CondizioneIscrizioneForm,
    IscrizioneForm,
    ScambioRettaForm,
    TariffaCondizioneIscrizioneForm,
)
from economia.models import CondizioneIscrizione, Iscrizione, RataIscrizione, StatoIscrizione, TariffaCondizioneIscrizione, TariffaScambioRetta
from economia.services import (
    ricalcola_rate_anno_scolastico,
    riconcilia_pagamenti_iscrizione,
    riconcilia_pagamenti_rate_anno_scolastico,
)
from gestione_finanziaria.models import MovimentoFinanziario, StatoRiconciliazione
from scuola.models import AnnoScolastico


class EconomiaCurrentSchoolYearDefaultsTests(TestCase):
    def setUp(self):
        AnnoScolastico.objects.create(
            nome_anno_scolastico="2024/2025",
            data_inizio=date(2024, 9, 1),
            data_fine=date(2025, 8, 31),
        )
        self.anno_corrente = AnnoScolastico.objects.create(
            nome_anno_scolastico="2025/2026",
            data_inizio=date(2025, 9, 1),
            data_fine=date(2026, 8, 31),
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


class ScambioRettaFormFamilySyncTests(TestCase):
    def setUp(self):
        stato = StatoRelazioneFamiglia.objects.create(stato="Iscritta")
        relazione = RelazioneFamiliare.objects.create(relazione="Genitore")
        self.famiglia = Famiglia.objects.create(cognome_famiglia="Bianchi", stato_relazione_famiglia=stato)
        self.altra_famiglia = Famiglia.objects.create(cognome_famiglia="Rossi", stato_relazione_famiglia=stato)
        self.familiare = Familiare.objects.create(
            famiglia=self.famiglia,
            relazione_familiare=relazione,
            nome="Mario",
            cognome="Bianchi",
            abilitato_scambio_retta=True,
        )
        self.studente = Studente.objects.create(famiglia=self.famiglia, nome="Luca", cognome="Bianchi")
        self.altro_studente = Studente.objects.create(famiglia=self.altra_famiglia, nome="Anna", cognome="Rossi")
        self.anno = AnnoScolastico.objects.create(
            nome_anno_scolastico="2025/2026",
            data_inizio=date(2025, 9, 1),
            data_fine=date(2026, 8, 31),
        )
        self.tariffa = TariffaScambioRetta.objects.create(valore_orario="10.00", definizione="Standard")

    def test_familiare_is_searchable_and_famiglia_is_locked(self):
        form = ScambioRettaForm()

        self.assertEqual(form.fields["familiare"].widget.attrs["data-searchable-select"], "1")
        self.assertEqual(form.fields["familiare"].widget.attrs["data-searchable-placeholder"], "Cerca un familiare...")
        self.assertEqual(form.fields["famiglia"].widget.attrs["data-searchable-select"], "1")
        self.assertIn("submit-safe-locked", form.fields["famiglia"].widget.attrs["class"])
        self.assertEqual(form.fields["famiglia"].widget.attrs["aria-disabled"], "true")
        self.assertEqual(form.fields["famiglia"].widget.attrs["data-keep-submitted-locked"], "1")

    def test_famiglia_is_derived_from_selected_familiare_on_submit(self):
        form = ScambioRettaForm(
            data={
                "familiare": self.familiare.pk,
                "famiglia": self.altra_famiglia.pk,
                "studente": self.studente.pk,
                "anno_scolastico": self.anno.pk,
                "mese_riferimento": 9,
                "descrizione": "Supporto mensa",
                "ore_lavorate": "2.00",
                "tariffa_scambio_retta": self.tariffa.pk,
                "note": "",
            }
        )

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["famiglia"], self.famiglia)

    def test_studenti_are_limited_to_selected_familiare_family(self):
        form = ScambioRettaForm(data={"familiare": self.familiare.pk})

        self.assertIn(self.studente, form.fields["studente"].queryset)
        self.assertNotIn(self.altro_studente, form.fields["studente"].queryset)


class EconomiaBatchRateTests(TestCase):
    def setUp(self):
        stato_famiglia = StatoRelazioneFamiglia.objects.create(stato="Iscritta")
        self.famiglia = Famiglia.objects.create(
            cognome_famiglia="Bianchi",
            stato_relazione_famiglia=stato_famiglia,
        )
        self.studente = Studente.objects.create(
            famiglia=self.famiglia,
            nome="Luca",
            cognome="Bianchi",
        )
        self.anno = AnnoScolastico.objects.create(
            nome_anno_scolastico="2025/2026",
            data_inizio=date(2025, 9, 1),
            data_fine=date(2026, 8, 31),
        )
        self.stato_iscrizione = StatoIscrizione.objects.create(
            stato_iscrizione="Attiva",
            ordine=1,
            attiva=True,
        )
        self.condizione = CondizioneIscrizione.objects.create(
            anno_scolastico=self.anno,
            nome_condizione_iscrizione="Retta standard",
            numero_mensilita_default=10,
            mese_prima_retta=9,
            giorno_scadenza_rate=10,
        )
        TariffaCondizioneIscrizione.objects.create(
            condizione_iscrizione=self.condizione,
            ordine_figlio_da=1,
            ordine_figlio_a=None,
            retta_annuale=Decimal("1000.00"),
            preiscrizione=Decimal("100.00"),
        )
        self.iscrizione = Iscrizione.objects.create(
            studente=self.studente,
            anno_scolastico=self.anno,
            stato_iscrizione=self.stato_iscrizione,
            condizione_iscrizione=self.condizione,
            data_iscrizione=date(2025, 9, 1),
        )

    def test_batch_recalculation_creates_rates_for_school_year(self):
        risultato = ricalcola_rate_anno_scolastico(self.anno)

        self.assertEqual(risultato["summary"]["created"], 1)
        self.assertEqual(self.iscrizione.rate.count(), 11)

    def test_single_payment_plan_creates_one_annual_rate_with_discount(self):
        self.iscrizione.modalita_pagamento_retta = Iscrizione.MODALITA_PAGAMENTO_UNICA_SOLUZIONE
        self.iscrizione.sconto_unica_soluzione_tipo = Iscrizione.SCONTO_UNICA_PERCENTUALE
        self.iscrizione.sconto_unica_soluzione_valore = Decimal("10.00")
        self.iscrizione.full_clean()
        self.iscrizione.save()

        risultato = self.iscrizione.sync_rate_schedule()

        self.assertEqual(risultato, "created")
        self.assertEqual(self.iscrizione.rate.count(), 2)
        rata_unica = self.iscrizione.rate.get(tipo_rata=RataIscrizione.TIPO_UNICA_SOLUZIONE)
        self.assertEqual(rata_unica.importo_dovuto, Decimal("900.00"))
        self.assertEqual(rata_unica.importo_finale, Decimal("900.00"))
        self.assertEqual(rata_unica.data_scadenza, date(2025, 9, 10))

    def test_batch_reconciliation_links_single_confident_payment(self):
        self.iscrizione.sync_rate_schedule()
        rata = self.iscrizione.rate.filter(tipo_rata=self.iscrizione.rate.model.TIPO_MENSILE).first()
        movimento = MovimentoFinanziario.objects.create(
            data_contabile=rata.data_scadenza,
            importo=rata.importo_finale,
            descrizione="Pagamento retta",
            controparte="Bianchi Luca",
            stato_riconciliazione=StatoRiconciliazione.NON_RICONCILIATO,
        )

        risultato = riconcilia_pagamenti_rate_anno_scolastico(self.anno)

        movimento.refresh_from_db()
        rata.refresh_from_db()
        self.assertEqual(risultato["stats"]["riconciliati"], 1)
        self.assertEqual(movimento.rata_iscrizione, rata)
        self.assertTrue(rata.pagata)
        self.assertEqual(rata.importo_pagato, rata.importo_finale)

    def test_single_enrollment_reconciliation_links_only_that_enrollment(self):
        self.iscrizione.sync_rate_schedule()
        rata = self.iscrizione.rate.filter(tipo_rata=self.iscrizione.rate.model.TIPO_MENSILE).first()
        movimento = MovimentoFinanziario.objects.create(
            data_contabile=rata.data_scadenza,
            importo=rata.importo_finale,
            descrizione="Pagamento retta",
            controparte="Bianchi Luca",
            stato_riconciliazione=StatoRiconciliazione.NON_RICONCILIATO,
        )

        risultato = riconcilia_pagamenti_iscrizione(self.iscrizione)

        movimento.refresh_from_db()
        self.assertEqual(risultato["stats"]["riconciliati"], 1)
        self.assertEqual(movimento.rata_iscrizione, rata)
