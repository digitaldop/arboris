from datetime import date
from decimal import Decimal
from unittest import skip
from unittest.mock import patch

from django import forms
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from arboris.form_widgets import apply_eur_currency_widget
from anagrafica.models import (
    Familiare,
    RelazioneFamiliare,
    Studente,
    StudenteFamiliare,
)
from economia.forms import (
    AgevolazioneForm,
    CondizioneIscrizioneForm,
    IscrizioneForm,
    RimodulazioneRateFutureForm,
    ScambioRettaForm,
    TariffaCondizioneIscrizioneForm,
)
from economia.models import (
    Agevolazione,
    CondizioneIscrizione,
    Iscrizione,
    MetodoPagamento,
    RataIscrizione,
    RimodulazioneRetta,
    ScambioRetta,
    StatoIscrizione,
    TariffaCondizioneIscrizione,
    TariffaScambioRetta,
)
from economia.services import (
    anteprima_riconcilia_pagamenti_rate_anno_scolastico,
    ricalcola_rate_anno_scolastico,
    riconcilia_pagamenti_iscrizione,
    riconcilia_pagamenti_rate_anno_scolastico,
    rimodula_rate_future,
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
    def test_optional_zero_initial_currency_field_renders_as_placeholder(self):
        field = forms.DecimalField(required=False, initial=Decimal("0.00"))

        apply_eur_currency_widget(field)

        self.assertEqual(field.initial, "")
        self.assertEqual(field.widget.attrs["placeholder"], "0,00")

    def test_optional_italian_zero_initial_currency_field_renders_as_placeholder(self):
        field = forms.DecimalField(required=False, initial="0,00")

        apply_eur_currency_widget(field)

        self.assertEqual(field.initial, "")

    def test_required_zero_initial_currency_field_renders_as_placeholder(self):
        field = forms.DecimalField(required=True, initial=Decimal("0.00"))

        apply_eur_currency_widget(field)

        self.assertEqual(field.initial, "")

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


class CondizioneIscrizionePopupLayoutTests(TestCase):
    def setUp(self):
        User.objects.create_superuser(username="admin", password="admin")
        self.client.login(username="admin", password="admin")
        self.anno = AnnoScolastico.objects.create(
            nome_anno_scolastico="2025/2026",
            data_inizio=date(2025, 9, 1),
            data_fine=date(2026, 8, 31),
        )
        self.condizione = CondizioneIscrizione.objects.create(
            anno_scolastico=self.anno,
            nome_condizione_iscrizione="Retta standard",
            numero_mensilita_default=10,
            mese_prima_retta=9,
            giorno_scadenza_rate=10,
            attiva=True,
        )

    def test_condizioni_list_opens_crud_actions_in_popup(self):
        response = self.client.get(reverse("lista_condizioni_iscrizione"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "condizioni-list-table")
        self.assertContains(response, "data-popup-url=\"/economia/condizioni-iscrizione/nuova/?popup=1\"")
        self.assertContains(
            response,
            f"data-row-popup-url=\"/economia/condizioni-iscrizione/{self.condizione.pk}/modifica/?popup=1\"",
        )
        self.assertContains(response, "arboris-condizione-iscrizione-delete-popup")

    def test_condizione_popup_form_uses_card_layout(self):
        response = self.client.get(reverse("modifica_condizione_iscrizione", args=[self.condizione.pk]), {"popup": "1"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "condizione-form-shell")
        self.assertContains(response, "Dati condizione")
        self.assertContains(response, "fondo-plan-switch-ui")
        self.assertNotContains(response, "form-table")

    def test_condizione_delete_popup_uses_card_layout(self):
        response = self.client.get(reverse("elimina_condizione_iscrizione", args=[self.condizione.pk]), {"popup": "1"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "condizione-delete-card")
        self.assertContains(response, "Conferma eliminazione")
        self.assertNotContains(response, "empty-state")


class TariffaCondizionePopupLayoutTests(TestCase):
    def setUp(self):
        User.objects.create_superuser(username="admin", password="admin")
        self.client.login(username="admin", password="admin")
        self.anno = AnnoScolastico.objects.create(
            nome_anno_scolastico="2025/2026",
            data_inizio=date(2025, 9, 1),
            data_fine=date(2026, 8, 31),
        )
        self.condizione = CondizioneIscrizione.objects.create(
            anno_scolastico=self.anno,
            nome_condizione_iscrizione="Retta standard",
            numero_mensilita_default=10,
            mese_prima_retta=9,
            giorno_scadenza_rate=10,
            attiva=True,
        )
        self.tariffa = TariffaCondizioneIscrizione.objects.create(
            condizione_iscrizione=self.condizione,
            ordine_figlio_da=1,
            ordine_figlio_a=None,
            retta_annuale=Decimal("2800.00"),
            preiscrizione=Decimal("250.00"),
            attiva=True,
        )

    def test_tariffe_list_opens_crud_actions_in_popup(self):
        response = self.client.get(reverse("lista_tariffe_condizione_iscrizione"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "tariffe-condizioni-list-table")
        self.assertContains(response, "data-popup-url=\"/economia/tariffe-condizione-iscrizione/nuova/?popup=1\"")
        self.assertContains(
            response,
            f"data-row-popup-url=\"/economia/tariffe-condizione-iscrizione/{self.tariffa.pk}/modifica/?popup=1\"",
        )
        self.assertContains(response, "arboris-tariffa-condizione-delete-popup")

    def test_tariffa_popup_form_uses_card_layout(self):
        response = self.client.get(reverse("modifica_tariffa_condizione_iscrizione", args=[self.tariffa.pk]), {"popup": "1"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "tariffa-condizione-form-shell")
        self.assertContains(response, "Dati tariffa")
        self.assertContains(response, "fondo-plan-switch-ui")
        self.assertNotContains(response, "form-table")

    def test_tariffa_delete_popup_uses_card_layout(self):
        response = self.client.get(reverse("elimina_tariffa_condizione_iscrizione", args=[self.tariffa.pk]), {"popup": "1"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "tariffa-condizione-delete-card")
        self.assertContains(response, "Conferma eliminazione")
        self.assertNotContains(response, "empty-state")


class AgevolazionePopupLayoutTests(TestCase):
    def setUp(self):
        User.objects.create_superuser(username="admin", password="admin")
        self.client.login(username="admin", password="admin")
        self.agevolazione = Agevolazione.objects.create(
            nome_agevolazione="ISEE",
            importo_annuale_agevolazione=Decimal("500.00"),
            attiva=True,
        )

    def test_agevolazioni_list_opens_crud_actions_in_popup(self):
        response = self.client.get(reverse("lista_agevolazioni"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "agevolazioni-list-table")
        self.assertContains(response, "data-popup-url=\"/economia/agevolazioni/nuova/?popup=1\"")
        self.assertContains(
            response,
            f"data-row-popup-url=\"/economia/agevolazioni/{self.agevolazione.pk}/modifica/?popup=1\"",
        )
        self.assertContains(response, "arboris-agevolazione-delete-popup")

    def test_agevolazione_popup_form_uses_card_layout(self):
        response = self.client.get(reverse("modifica_agevolazione", args=[self.agevolazione.pk]), {"popup": "1"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "agevolazione-form-shell")
        self.assertContains(response, "Dati agevolazione")
        self.assertContains(response, "fondo-plan-switch-ui")
        self.assertNotContains(response, "form-table")

    def test_agevolazione_delete_popup_uses_card_layout(self):
        response = self.client.get(reverse("elimina_agevolazione", args=[self.agevolazione.pk]), {"popup": "1"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "agevolazione-delete-card")
        self.assertContains(response, "Conferma eliminazione")
        self.assertNotContains(response, "empty-state")


@skip("Legacy test basato sulla tabella anagrafica.Famiglia rimossa.")
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

    def test_tariffa_choice_label_shows_currency_symbol(self):
        form = ScambioRettaForm()

        label = form.fields["tariffa_scambio_retta"].label_from_instance(self.tariffa)

        self.assertEqual(label, "Standard - 10.00 \u20ac")

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

    def test_studenti_choices_are_rendered_for_client_side_filtering(self):
        form = ScambioRettaForm()

        self.assertIn(self.studente, form.fields["studente"].queryset)
        self.assertIn(self.altro_studente, form.fields["studente"].queryset)
        rendered = str(form["studente"])
        self.assertIn(f'data-famiglia-id="{self.famiglia.pk}"', rendered)
        self.assertIn(f'data-famiglia-id="{self.altra_famiglia.pk}"', rendered)
        self.assertIn(f'data-studente-ids="{self.studente.pk}"', str(form["familiare"]))

    def test_studenti_are_limited_to_direct_relations_when_available(self):
        StudenteFamiliare.objects.create(
            studente=self.altro_studente,
            familiare=self.familiare,
            attivo=True,
        )

        form = ScambioRettaForm(data={"familiare": self.familiare.pk})

        self.assertNotIn(self.studente, form.fields["studente"].queryset)
        self.assertIn(self.altro_studente, form.fields["studente"].queryset)

    def test_direct_relation_allows_student_from_different_legacy_family(self):
        StudenteFamiliare.objects.create(
            studente=self.altro_studente,
            familiare=self.familiare,
            attivo=True,
        )
        form = ScambioRettaForm(
            data={
                "familiare": self.familiare.pk,
                "famiglia": self.famiglia.pk,
                "studente": self.altro_studente.pk,
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


@skip("Legacy test basato sulla tabella anagrafica.Famiglia rimossa.")
class ScambioRettaPopupModeTests(TestCase):
    def setUp(self):
        User.objects.create_superuser(username="admin", password="admin")
        self.client.login(username="admin", password="admin")

        stato = StatoRelazioneFamiglia.objects.create(stato="Iscritta")
        relazione = RelazioneFamiliare.objects.create(relazione="Genitore")
        self.famiglia = Famiglia.objects.create(cognome_famiglia="Bianchi", stato_relazione_famiglia=stato)
        self.familiare = Familiare.objects.create(
            famiglia=self.famiglia,
            relazione_familiare=relazione,
            nome="Mario",
            cognome="Bianchi",
            abilitato_scambio_retta=True,
        )
        self.studente = Studente.objects.create(famiglia=self.famiglia, nome="Luca", cognome="Bianchi")
        self.anno = AnnoScolastico.objects.create(
            nome_anno_scolastico="2025/2026",
            data_inizio=date(2025, 9, 1),
            data_fine=date(2026, 8, 31),
        )
        self.tariffa = TariffaScambioRetta.objects.create(valore_orario=Decimal("10.00"), definizione="Standard")
        self.scambio = ScambioRetta.objects.create(
            familiare=self.familiare,
            famiglia=self.famiglia,
            studente=self.studente,
            anno_scolastico=self.anno,
            mese_riferimento=9,
            ore_lavorate=Decimal("2.00"),
            tariffa_scambio_retta=self.tariffa,
        )

    def test_list_edit_action_opens_popup_in_edit_mode(self):
        response = self.client.get(reverse("lista_scambi_retta"))

        self.assertEqual(response.status_code, 200)
        edit_url = f"{reverse('modifica_scambio_retta', kwargs={'pk': self.scambio.pk})}?popup=1&edit=1"
        self.assertContains(response, edit_url)

    def test_popup_detail_starts_in_edit_mode_when_requested(self):
        url = reverse("modifica_scambio_retta", kwargs={"pk": self.scambio.pk})

        view_response = self.client.get(url, {"popup": "1"})
        edit_response = self.client.get(url, {"popup": "1", "edit": "1"})

        self.assertContains(view_response, "startInEditMode: false")
        self.assertContains(edit_response, "startInEditMode: true")

    def test_popup_status_fields_do_not_render_toggle_or_checkbox(self):
        response = self.client.get(reverse("modifica_scambio_retta", kwargs={"pk": self.scambio.pk}), {"popup": "1"})

        self.assertNotContains(response, "fondo-plan-switch-control")
        self.assertNotContains(response, 'type="checkbox"')


class RateCustomizationAndRemodulationTests(TestCase):
    def setUp(self):
        self.studente = Studente.objects.create(nome="Luca", cognome="Bianchi")
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
            retta_annuale=Decimal("1200.00"),
            preiscrizione=Decimal("0.00"),
        )
        self.iscrizione = Iscrizione.objects.create(
            studente=self.studente,
            anno_scolastico=self.anno,
            stato_iscrizione=self.stato_iscrizione,
            condizione_iscrizione=self.condizione,
            data_iscrizione=date(2025, 9, 1),
        )

    def _rate_mensili(self):
        return list(
            self.iscrizione.rate.filter(tipo_rata=RataIscrizione.TIPO_MENSILE).order_by(
                "anno_riferimento",
                "mese_riferimento",
                "numero_rata",
            )
        )

    def test_rate_custom_controls_initial_month_count(self):
        self.iscrizione.rate_custom = 6
        self.iscrizione.save()

        piano = self.iscrizione.build_rate_plan()
        rate_mensili = [item for item in piano if item["tipo_rata"] == RataIscrizione.TIPO_MENSILE]

        self.assertEqual(len(rate_mensili), 6)
        self.assertEqual(rate_mensili[0]["importo_dovuto"], Decimal("200.00"))
        self.assertEqual(sum(item["importo_dovuto"] for item in rate_mensili), Decimal("1200.00"))

    def test_rate_custom_cannot_change_after_generated_rates(self):
        self.iscrizione.rate_custom = 6
        self.iscrizione.save()
        self.iscrizione.sync_rate_schedule()

        self.iscrizione.rate_custom = 8

        with self.assertRaises(ValidationError):
            self.iscrizione.full_clean()

    def test_rimodula_rate_future_redistributes_unpaid_residual(self):
        self.iscrizione.sync_rate_schedule()
        rate = self._rate_mensili()
        for rata in rate[:2]:
            rata.pagata = True
            rata.importo_pagato = rata.importo_finale
            rata.data_pagamento = rata.data_scadenza
            rata.save()

        rimodulazione = rimodula_rate_future(
            self.iscrizione,
            rata_decorrenza=rate[2],
            modalita=RimodulazioneRetta.MODALITA_RIDISTRIBUISCI_RESIDUO,
            numero_rate_future=10,
        )
        nuove_future = self._rate_mensili()[2:]

        self.assertEqual(rimodulazione.rate_sostituite, 8)
        self.assertEqual(rimodulazione.numero_rate_future, 10)
        self.assertEqual(rimodulazione.totale_precedente, Decimal("960.00"))
        self.assertEqual(rimodulazione.totale_rimodulato, Decimal("960.00"))
        self.assertEqual(len(nuove_future), 10)
        self.assertEqual(sum(rata.importo_finale for rata in nuove_future), Decimal("960.00"))
        self.assertTrue(all(rata.importo_finale == Decimal("96.00") for rata in nuove_future))

    def test_rimodula_rate_future_redistributes_partial_payment_residual(self):
        self.iscrizione.sync_rate_schedule()
        rate = self._rate_mensili()
        rate[4].importo_pagato = Decimal("20.00")
        rate[4].save(update_fields=["importo_pagato"])

        rimodulazione = rimodula_rate_future(
            self.iscrizione,
            rata_decorrenza=rate[2],
            modalita=RimodulazioneRetta.MODALITA_RIDISTRIBUISCI_RESIDUO,
            numero_rate_future=10,
        )
        rate[4].refresh_from_db()
        rate_aggiornate = self._rate_mensili()[2:]

        self.assertEqual(rimodulazione.totale_precedente, Decimal("940.00"))
        self.assertEqual(rimodulazione.totale_rimodulato, Decimal("940.00"))
        self.assertEqual(rate[4].importo_finale, Decimal("114.00"))
        self.assertFalse(rate[4].pagata)
        self.assertEqual(sum(rata.importo_finale - rata.importo_pagato for rata in rate_aggiornate), Decimal("940.00"))
        self.assertEqual(len(rate_aggiornate), 10)

    def test_rimodula_rate_future_updates_existing_rates_without_duplicates(self):
        self.iscrizione.sync_rate_schedule()
        rate = self._rate_mensili()
        for rata in rate[4:]:
            rata.importo_pagato = Decimal("20.00")
            rata.save(update_fields=["importo_pagato"])

        rimodulazione = rimodula_rate_future(
            self.iscrizione,
            rata_decorrenza=rate[4],
            modalita=RimodulazioneRetta.MODALITA_IMPORTO_MENSILE,
            numero_rate_future=6,
            importo_mensile=Decimal("20.00"),
        )
        rate_aggiornate = self._rate_mensili()

        self.assertEqual(rimodulazione.totale_precedente, Decimal("600.00"))
        self.assertEqual(rimodulazione.totale_rimodulato, Decimal("0.00"))
        self.assertEqual(len(rate_aggiornate), 10)
        self.assertFalse(self.iscrizione.rate.filter(descrizione__startswith="Rata rimodulata").exists())
        self.assertTrue(all(rata.importo_finale == Decimal("20.00") for rata in rate_aggiornate[4:]))
        self.assertTrue(all(rata.pagata for rata in rate_aggiornate[4:]))

    def test_rimodula_form_lists_rates_with_partial_payments(self):
        self.iscrizione.sync_rate_schedule()
        rate = self._rate_mensili()
        for rata in rate[:4]:
            rata.pagata = True
            rata.importo_pagato = rata.importo_finale
            rata.save(update_fields=["pagata", "importo_pagato"])
        for rata in rate[4:]:
            rata.importo_pagato = Decimal("20.00")
            rata.save(update_fields=["importo_pagato"])

        form = RimodulazioneRateFutureForm(iscrizione=self.iscrizione)

        self.assertGreater(form.fields["rata_decorrenza"].queryset.count(), 0)
        self.assertIn(rate[4], form.fields["rata_decorrenza"].queryset)
        self.assertEqual(form.initial["numero_rate_future"], 6)
        self.assertEqual(form.fields["numero_rate_future"].widget.attrs["readonly"], "readonly")

    def test_rimodula_form_uses_default_rate_count_unless_custom_enabled(self):
        self.iscrizione.sync_rate_schedule()
        rate = self._rate_mensili()

        form = RimodulazioneRateFutureForm(
            {
                "rata_decorrenza": str(rate[3].pk),
                "modalita": RimodulazioneRetta.MODALITA_RIDISTRIBUISCI_RESIDUO,
                "numero_rate_future": "99",
            },
            iscrizione=self.iscrizione,
        )
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["numero_rate_future"], 7)

        custom_form = RimodulazioneRateFutureForm(
            {
                "rata_decorrenza": str(rate[3].pk),
                "modalita": RimodulazioneRetta.MODALITA_RIDISTRIBUISCI_RESIDUO,
                "numero_rate_future": "5",
                "personalizza_numero_rate": "on",
            },
            iscrizione=self.iscrizione,
        )
        self.assertTrue(custom_form.is_valid(), custom_form.errors)
        self.assertEqual(custom_form.cleaned_data["numero_rate_future"], 5)

    def test_rimodula_rate_view_renders_popup_form(self):
        User.objects.create_superuser(username="admin", password="admin")
        self.client.login(username="admin", password="admin")
        self.iscrizione.sync_rate_schedule()

        response = self.client.get(reverse("rimodula_rate_iscrizione", args=[self.iscrizione.pk]), {"popup": "1"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Rimodula rate future")
        self.assertContains(response, "Nuovo piano futuro")
        self.assertContains(response, "name=\"rata_decorrenza\"")
        self.assertContains(response, "data-rimodulazione-rate-count")
        self.assertContains(response, "name=\"personalizza_numero_rate\"")
        self.assertContains(response, "Personalizza")
        self.assertContains(response, "onclick=\"window.close()\"", count=2)
        self.assertContains(response, "La procedura ricalcola il residuo")

    def test_verifica_situazione_rette_matrix_uses_drag_scroll_and_right_click_detail(self):
        User.objects.create_superuser(username="admin", password="admin")
        self.client.login(username="admin", password="admin")
        self.iscrizione.sync_rate_schedule()

        response = self.client.get(
            reverse("verifica_situazione_rette"),
            {"anno_scolastico": self.anno.pk},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "data-rate-matrix-scroll")
        self.assertContains(response, "data-rate-matrix-row")
        self.assertContains(response, "data-rate-matrix-cell")
        self.assertContains(response, "data-rate-detail-link")
        self.assertContains(response, "verifica-rette-scroll-help")
        self.assertContains(response, "class=\"studente-link\"")
        self.assertContains(response, reverse("modifica_studente", args=[self.studente.pk]))
        self.assertContains(response, "?next=/economia/verifica-situazione-rette/%3Fanno_scolastico%3D")
        self.assertContains(response, "classe-separator-cell")
        self.assertContains(response, "classe-separator-fill")
        self.assertContains(response, "top: 34px")
        self.assertContains(response, "is-row-highlighted")
        self.assertContains(response, "aria-selected=\"false\"")
        self.assertContains(response, "verifica-rette-scroll-help-mark")
        self.assertContains(response, "max-height: calc(100vh - 220px)")
        self.assertContains(response, "overflow: visible")
        self.assertContains(response, "mousedown")
        self.assertContains(response, "dblclick")
        self.assertContains(response, "contextmenu")
        self.assertContains(response, "toggleMatrixRowHighlight")
        self.assertContains(response, "closestElement(event.target, \".studente-link\")")
        self.assertContains(response, "Bianchi Luca - Settembre")
        self.assertContains(response, "Bianchi Luca - Settembre&#10;Doppio click su una cella", html=False)
        self.assertContains(
            response,
            "Doppio click su una cella: evidenzia la riga. Tieni premuto e trascina per scorrere. Tasto destro: apri il dettaglio rata.",
        )
        self.assertContains(response, "Click sul nome: apri la scheda studente.")


@skip("Legacy test basato sulla tabella anagrafica.Famiglia rimossa.")
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
