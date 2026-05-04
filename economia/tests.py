from datetime import date
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from anagrafica.models import Famiglia, Familiare, RelazioneFamiliare, StatoRelazioneFamiglia, Studente
from economia.forms import (
    AgevolazioneForm,
    CondizioneIscrizioneForm,
    IscrizioneForm,
    ScambioRettaForm,
    TariffaCondizioneIscrizioneForm,
)
from economia.models import (
    CondizioneIscrizione,
    Iscrizione,
    MetodoPagamento,
    RataIscrizione,
    StatoIscrizione,
    TariffaCondizioneIscrizione,
    TariffaScambioRetta,
)
from economia.services import (
    anteprima_riconcilia_pagamenti_rate_anno_scolastico,
    ricalcola_rate_anno_scolastico,
    riconcilia_pagamenti_iscrizione,
    riconcilia_pagamenti_rate_anno_scolastico,
)
from gestione_finanziaria.models import MovimentoFinanziario, StatoRiconciliazione
from scuola.models import AnnoScolastico, Classe
from sistema.models import GestioneIscrizioneCorsoAnno, SistemaImpostazioniGenerali


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
        self.assertEqual(form.initial["data_iscrizione"], self.anno_corrente.data_inizio)

    def test_iscrizione_form_defaults_to_first_active_status(self):
        self.stato_iscrizione.ordine = 5
        self.stato_iscrizione.save(update_fields=["ordine"])
        StatoIscrizione.objects.create(stato_iscrizione="Non attivo", ordine=0, attiva=False)
        primo_stato = StatoIscrizione.objects.create(stato_iscrizione="Primo attivo", ordine=1, attiva=True)

        form = IscrizioneForm()

        self.assertEqual(form.initial["stato_iscrizione"], primo_stato.pk)

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

    def test_metodo_pagamento_popup_uses_new_card_layout(self):
        User.objects.create_superuser(username="admin", password="admin")
        self.client.login(username="admin", password="admin")

        response = self.client.get(reverse("crea_metodo_pagamento"), {"popup": "1"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "method-payment-shell")
        self.assertContains(response, "calendar-event-form-card")
        self.assertContains(response, "Dati metodo")
        self.assertNotContains(response, "form-table")


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

    def test_verifica_situazione_rette_exposes_column_and_summary_totals(self):
        User.objects.create_superuser(username="admin", password="admin")
        self.client.login(username="admin", password="admin")
        self.iscrizione.sync_rate_schedule()

        preiscrizione = self.iscrizione.rate.get(tipo_rata=RataIscrizione.TIPO_PREISCRIZIONE)
        preiscrizione.importo_pagato = Decimal("100.00")
        preiscrizione.pagata = True
        preiscrizione.data_pagamento = date(2025, 8, 1)
        preiscrizione.save()

        settembre = self.iscrizione.rate.get(
            tipo_rata=RataIscrizione.TIPO_MENSILE,
            anno_riferimento=2025,
            mese_riferimento=9,
        )
        settembre.importo_pagato = Decimal("50.00")
        settembre.data_pagamento = date(2025, 9, 20)
        settembre.save()

        with patch("economia.views.iscrizioni.timezone.localdate", return_value=date(2025, 9, 30)):
            response = self.client.get(
                reverse("verifica_situazione_rette"),
                {"anno_scolastico": self.anno.pk},
            )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "verifica-rette-page-shell")
        self.assertContains(response, "verifica-rette-control-card")
        self.assertContains(response, "verifica-rette-card-title")
        totali_colonne = response.context["totali_colonne"]
        riepilogo_totali = response.context["riepilogo_totali"]

        totale_preiscrizione = totali_colonne[0]
        totale_settembre = next(
            totale
            for totale in totali_colonne
            if totale["colonna"]["key"] == (2025, 9)
        )

        self.assertEqual(totale_preiscrizione["dovuto"], Decimal("100.00"))
        self.assertEqual(totale_preiscrizione["pagato"], Decimal("100.00"))
        self.assertEqual(totale_settembre["dovuto"], Decimal("100.00"))
        self.assertEqual(totale_settembre["pagato"], Decimal("50.00"))
        self.assertEqual(riepilogo_totali["dovuto_con_preiscrizioni"], Decimal("200.00"))
        self.assertEqual(riepilogo_totali["pagato_con_preiscrizioni"], Decimal("150.00"))
        self.assertEqual(riepilogo_totali["dovuto_senza_preiscrizioni"], Decimal("100.00"))
        self.assertEqual(riepilogo_totali["pagato_senza_preiscrizioni"], Decimal("50.00"))
        self.assertEqual(riepilogo_totali["totale_anno_con_preiscrizioni"], Decimal("1100.00"))
        self.assertEqual(riepilogo_totali["totale_anno_senza_preiscrizioni"], Decimal("1000.00"))
        self.assertEqual(riepilogo_totali["rimanente_anno_con_preiscrizioni"], Decimal("950.00"))
        self.assertEqual(riepilogo_totali["rimanente_anno_senza_preiscrizioni"], Decimal("950.00"))
        self.assertContains(response, "Rimanente per l'anno scolastico", count=2)

    def test_verifica_situazione_rette_defaults_to_alphabetical_matrix(self):
        User.objects.create_superuser(username="admin", password="admin")
        self.client.login(username="admin", password="admin")
        classe_prima = Classe.objects.create(nome_classe="Prima", ordine_classe=1)
        classe_seconda = Classe.objects.create(nome_classe="Seconda", ordine_classe=2)
        self.iscrizione.classe = classe_seconda
        self.iscrizione.save(update_fields=["classe"])

        altra_famiglia = Famiglia.objects.create(
            cognome_famiglia="Azzurri",
            stato_relazione_famiglia=self.famiglia.stato_relazione_famiglia,
        )
        altro_studente = Studente.objects.create(
            famiglia=altra_famiglia,
            nome="Anna",
            cognome="Azzurri",
        )
        Iscrizione.objects.create(
            studente=altro_studente,
            anno_scolastico=self.anno,
            stato_iscrizione=self.stato_iscrizione,
            condizione_iscrizione=self.condizione,
            data_iscrizione=date(2025, 9, 1),
            classe=classe_prima,
        )

        response = self.client.get(
            reverse("verifica_situazione_rette"),
            {"anno_scolastico": self.anno.pk},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-matrix-view-panel="alfabetica"')
        self.assertContains(response, 'data-matrix-view-panel="classe" hidden')
        self.assertContains(response, "Ordine alfabetico")
        self.assertContains(response, "Per classe")
        self.assertEqual(
            [riga["studente"].cognome for riga in response.context["righe_matrice_alfabetica"]],
            ["Azzurri", "Bianchi"],
        )

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

    def test_mid_year_enrollment_default_starts_from_enrollment_month(self):
        self.iscrizione.data_iscrizione = date(2025, 11, 12)
        self.iscrizione.save()

        piano = self.iscrizione.build_rate_plan()
        rate_mensili = [item for item in piano if item["tipo_rata"] == RataIscrizione.TIPO_MENSILE]

        self.assertEqual(len(rate_mensili), 8)
        self.assertEqual(rate_mensili[0]["mese_riferimento"], 11)
        self.assertEqual(rate_mensili[0]["anno_riferimento"], 2025)
        self.assertEqual(rate_mensili[0]["data_scadenza"], date(2025, 11, 12))
        self.assertEqual(rate_mensili[-1]["mese_riferimento"], 6)
        self.assertEqual(rate_mensili[-1]["anno_riferimento"], 2026)
        self.assertEqual(sum(item["importo_dovuto"] for item in rate_mensili), Decimal("800.00"))

    def test_mid_year_enrollment_can_start_from_next_month_after_threshold(self):
        SistemaImpostazioniGenerali.objects.create(
            gestione_iscrizione_corso_anno=GestioneIscrizioneCorsoAnno.MESE_SUCCESSIVO_DOPO_SOGLIA,
            giorno_soglia_iscrizione_corso_anno=15,
        )
        self.iscrizione.data_iscrizione = date(2025, 11, 20)
        self.iscrizione.save()

        rate_mensili = [
            item
            for item in self.iscrizione.build_rate_plan()
            if item["tipo_rata"] == RataIscrizione.TIPO_MENSILE
        ]

        self.assertEqual(len(rate_mensili), 7)
        self.assertEqual(rate_mensili[0]["mese_riferimento"], 12)
        self.assertEqual(rate_mensili[0]["anno_riferimento"], 2025)
        self.assertEqual(rate_mensili[0]["data_scadenza"], date(2025, 12, 10))
        self.assertEqual(sum(item["importo_dovuto"] for item in rate_mensili), Decimal("700.00"))

    def test_mid_year_enrollment_can_prorate_first_month(self):
        SistemaImpostazioniGenerali.objects.create(
            gestione_iscrizione_corso_anno=GestioneIscrizioneCorsoAnno.PRO_RATA_GIORNALIERO,
        )
        self.iscrizione.data_iscrizione = date(2025, 11, 16)
        self.iscrizione.save()

        rate_mensili = [
            item
            for item in self.iscrizione.build_rate_plan()
            if item["tipo_rata"] == RataIscrizione.TIPO_MENSILE
        ]

        self.assertEqual(len(rate_mensili), 8)
        self.assertEqual(rate_mensili[0]["mese_riferimento"], 11)
        self.assertEqual(rate_mensili[0]["data_scadenza"], date(2025, 11, 16))
        self.assertEqual(rate_mensili[0]["importo_dovuto"], Decimal("50.00"))
        self.assertEqual(sum(item["importo_dovuto"] for item in rate_mensili), Decimal("750.00"))

    def test_single_payment_mid_year_uses_only_due_months_before_discount(self):
        self.iscrizione.data_iscrizione = date(2025, 11, 12)
        self.iscrizione.modalita_pagamento_retta = Iscrizione.MODALITA_PAGAMENTO_UNICA_SOLUZIONE
        self.iscrizione.sconto_unica_soluzione_tipo = Iscrizione.SCONTO_UNICA_PERCENTUALE
        self.iscrizione.sconto_unica_soluzione_valore = Decimal("10.00")
        self.iscrizione.full_clean()
        self.iscrizione.save()

        piano = self.iscrizione.build_rate_plan()
        rata_unica = next(item for item in piano if item["tipo_rata"] == RataIscrizione.TIPO_UNICA_SOLUZIONE)

        self.assertEqual(rata_unica["importo_dovuto"], Decimal("720.00"))
        self.assertEqual(rata_unica["data_scadenza"], date(2025, 11, 12))

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

    def test_batch_reconciliation_preview_does_not_write_until_confirmed(self):
        self.iscrizione.sync_rate_schedule()
        rata = self.iscrizione.rate.filter(tipo_rata=self.iscrizione.rate.model.TIPO_MENSILE).first()
        movimento = MovimentoFinanziario.objects.create(
            data_contabile=rata.data_scadenza,
            importo=rata.importo_finale,
            descrizione="Pagamento retta",
            controparte="Bianchi Luca",
            stato_riconciliazione=StatoRiconciliazione.NON_RICONCILIATO,
        )

        preview = anteprima_riconcilia_pagamenti_rate_anno_scolastico(self.anno)

        movimento.refresh_from_db()
        rata.refresh_from_db()
        self.assertEqual(preview["stats"]["proposti"], 1)
        self.assertEqual(movimento.stato_riconciliazione, StatoRiconciliazione.NON_RICONCILIATO)
        self.assertFalse(rata.pagata)

    def test_batch_reconciliation_view_confirms_selected_preview_rows(self):
        User.objects.create_superuser(username="admin", password="admin")
        self.client.login(username="admin", password="admin")
        self.iscrizione.sync_rate_schedule()
        rata = self.iscrizione.rate.filter(tipo_rata=self.iscrizione.rate.model.TIPO_MENSILE).first()
        movimento = MovimentoFinanziario.objects.create(
            data_contabile=rata.data_scadenza,
            importo=rata.importo_finale,
            descrizione="Pagamento retta",
            controparte="Bianchi Luca",
            stato_riconciliazione=StatoRiconciliazione.NON_RICONCILIATO,
        )
        url = reverse("riconcilia_pagamenti_rate_anno_scolastico")

        response = self.client.post(url, {"anno_scolastico": self.anno.pk})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Proposte di riconciliazione")
        movimento.refresh_from_db()
        self.assertEqual(movimento.stato_riconciliazione, StatoRiconciliazione.NON_RICONCILIATO)
        selected_key = response.context["preview"]["dettagli"][0]["key"]

        response = self.client.post(
            url,
            {
                "azione": "conferma",
                "anno_scolastico": self.anno.pk,
                "selected_items": [selected_key],
            },
        )

        self.assertEqual(response.status_code, 302)
        movimento.refresh_from_db()
        rata.refresh_from_db()
        self.assertEqual(movimento.rata_iscrizione, rata)
        self.assertTrue(rata.pagata)

    def test_batch_reconciliation_splits_cumulative_family_payment(self):
        sorella = Studente.objects.create(
            famiglia=self.famiglia,
            nome="Marta",
            cognome="Bianchi",
        )
        iscrizione_sorella = Iscrizione.objects.create(
            studente=sorella,
            anno_scolastico=self.anno,
            stato_iscrizione=self.stato_iscrizione,
            condizione_iscrizione=self.condizione,
            data_iscrizione=date(2025, 9, 1),
        )
        self.iscrizione.sync_rate_schedule()
        iscrizione_sorella.sync_rate_schedule()
        rata_luca = self.iscrizione.rate.get(
            tipo_rata=RataIscrizione.TIPO_MENSILE,
            mese_riferimento=9,
            anno_riferimento=2025,
        )
        rata_marta = iscrizione_sorella.rate.get(
            tipo_rata=RataIscrizione.TIPO_MENSILE,
            mese_riferimento=9,
            anno_riferimento=2025,
        )
        movimento = MovimentoFinanziario.objects.create(
            data_contabile=date(2025, 9, 10),
            importo=rata_luca.importo_finale + rata_marta.importo_finale,
            descrizione="Bonifico rette settembre Luca e Marta Bianchi",
            stato_riconciliazione=StatoRiconciliazione.NON_RICONCILIATO,
        )

        risultato = riconcilia_pagamenti_rate_anno_scolastico(self.anno)

        movimento.refresh_from_db()
        rata_luca.refresh_from_db()
        rata_marta.refresh_from_db()
        self.assertEqual(risultato["stats"]["riconciliati"], 1)
        self.assertEqual(risultato["stats"]["riconciliati_cumulativi"], 1)
        self.assertEqual(movimento.stato_riconciliazione, StatoRiconciliazione.RICONCILIATO)
        self.assertIsNone(movimento.rata_iscrizione_id)
        self.assertTrue(rata_luca.pagata)
        self.assertTrue(rata_marta.pagata)
        self.assertEqual(rata_luca.importo_pagato, rata_luca.importo_finale)
        self.assertEqual(rata_marta.importo_pagato, rata_marta.importo_finale)
        self.assertEqual(movimento.riconciliazioni_rate.count(), 2)

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

    def test_reverse_reconciliation_popup_links_selected_movement(self):
        User.objects.create_superuser(username="admin", password="admin")
        self.client.login(username="admin", password="admin")
        self.iscrizione.sync_rate_schedule()
        rata = self.iscrizione.rate.filter(tipo_rata=RataIscrizione.TIPO_MENSILE).first()
        movimento = MovimentoFinanziario.objects.create(
            data_contabile=rata.data_scadenza,
            importo=rata.importo_finale,
            descrizione="Bonifico retta Luca Bianchi",
            controparte="Bianchi",
            stato_riconciliazione=StatoRiconciliazione.NON_RICONCILIATO,
        )

        response = self.client.get(
            reverse("riconcilia_rata_iscrizione", kwargs={"pk": rata.pk}),
            {"popup": "1"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Riconcilia rate")
        self.assertContains(response, "Movimenti candidati")
        self.assertContains(response, f'value="{movimento.pk}"')

        response = self.client.post(
            reverse("riconcilia_rata_iscrizione", kwargs={"pk": rata.pk}),
            {
                "popup": "1",
                "movimento_pk": str(movimento.pk),
                f"importo_rata_{rata.pk}": "100,00",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Riconciliazione registrata correttamente")
        movimento.refresh_from_db()
        rata.refresh_from_db()
        self.assertEqual(movimento.stato_riconciliazione, StatoRiconciliazione.RICONCILIATO)
        self.assertEqual(movimento.rata_iscrizione_id, rata.pk)
        self.assertTrue(rata.pagata)
        self.assertEqual(rata.riconciliazioni_movimenti.count(), 1)

    def test_rate_detail_popup_uses_new_card_layout(self):
        User.objects.create_superuser(username="admin", password="admin")
        self.client.login(username="admin", password="admin")
        self.iscrizione.sync_rate_schedule()
        rata = self.iscrizione.rate.filter(tipo_rata=RataIscrizione.TIPO_MENSILE).first()
        metodo = MetodoPagamento.objects.create(metodo_pagamento="Bonifico")
        rata.importo_pagato = rata.importo_finale
        rata.pagata = True
        rata.data_pagamento = date(2025, 9, 10)
        rata.metodo_pagamento = metodo
        rata.save(update_fields=["importo_pagato", "pagata", "data_pagamento", "metodo_pagamento"])

        response = self.client.get(
            reverse("modifica_rata_iscrizione", kwargs={"pk": rata.pk}),
            {"popup": "1"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "rate-detail-shell is-popup")
        self.assertContains(response, "Dettagli rata")
        self.assertContains(response, 'name="popup" value="1"')
        self.assertContains(response, "rate-detail-payment-method-field")
        self.assertContains(response, 'id="detail-add-metodo-pagamento-btn"')
        self.assertContains(response, 'id="detail-edit-metodo-pagamento-btn"')
        self.assertContains(response, 'id="detail-delete-metodo-pagamento-btn"')
        self.assertContains(response, 'data-searchable-placeholder="Cerca un metodo di pagamento..."')
        self.assertContains(response, "rata-iscrizione-form.js")
        self.assertNotContains(response, "site-header")
