from datetime import date, timedelta
from decimal import Decimal
from unittest import skip

from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from anagrafica.models import Documento, TipoDocumento
from economia.models import CondizioneIscrizione, Iscrizione, RataIscrizione, StatoIscrizione
from gestione_finanziaria.models import DocumentoFornitore, Fornitore, ScadenzaPagamentoFornitore
from scuola.models import AnnoScolastico
from sistema.models import LivelloPermesso, SistemaImpostazioniGenerali, SistemaUtentePermessi

from .data import build_dashboard_calendar_data
from .models import CategoriaCalendario, EventoCalendario


class CalendarioAgendaInterfaceTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(
            username="calendario@example.com",
            email="calendario@example.com",
            password="Password123!",
        )
        SistemaUtentePermessi.objects.create(
            user=self.user,
            permesso_calendario=LivelloPermesso.GESTIONE,
        )
        self.category = CategoriaCalendario.objects.create(nome="Didattica", colore="#417690", ordine=1)

    def tearDown(self):
        cache.clear()
        super().tearDown()

    def test_agenda_exposes_category_edit_icon_and_current_script(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse("calendario_agenda"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'class="admin-section-title-btn admin-section-title-icon-btn"')
        self.assertContains(response, f'href="{reverse("lista_categorie_calendario")}?popup=1"')
        self.assertContains(response, "js/pages/calendario-agenda.js?v=22")
        self.assertContains(response, 'id="calendar-events-card"')
        self.assertContains(response, 'data-full-create-url="{0}?popup=1"'.format(reverse("crea_evento_calendario")))
        self.assertContains(response, 'data-calendar-selected-create="1"')
        self.assertContains(response, "Doppio click")
        self.assertContains(response, "Informazioni doppio click")
        self.assertNotContains(response, "Elenco eventi")

    def test_agenda_embeds_paginated_event_list_with_filters(self):
        self.client.force_login(self.user)
        start_day = date(2026, 5, 1)
        for index in range(13):
            EventoCalendario.objects.create(
                titolo=f"Evento {index + 1}",
                categoria_evento=self.category,
                data_inizio=start_day + timedelta(days=index),
                data_fine=start_day + timedelta(days=index),
                intera_giornata=True,
            )

        response = self.client.get(reverse("calendario_agenda"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Eventi e scadenze")
        self.assertContains(response, 'name="categoria" data-calendar-category-filter')
        self.assertContains(response, 'name="q"')
        self.assertContains(response, "page=2#calendar-events-card")
        self.assertContains(response, "calendar-events-add-btn")
        self.assertContains(response, "calendar-row-action-btn")
        self.assertContains(response, 'data-calendar-event-popup="1"')
        self.assertContains(response, "width=920,height=760")

    def test_dashboard_week_events_are_paginated(self):
        start_day = date(2026, 5, 4)
        for index in range(7):
            EventoCalendario.objects.create(
                titolo=f"Evento dashboard {index + 1}",
                categoria_evento=self.category,
                data_inizio=start_day + timedelta(days=index),
                data_fine=start_day + timedelta(days=index),
                intera_giornata=True,
            )

        dashboard_data = build_dashboard_calendar_data(
            today=date(2026, 5, 5),
            user=self.user,
        )

        self.assertEqual(dashboard_data["count_week_records"], 7)
        self.assertEqual(dashboard_data["week_page_size"], 3)
        self.assertEqual(dashboard_data["week_total_pages"], 3)
        self.assertEqual(len(dashboard_data["week_records"]), 7)

    @skip("Legacy test basato sulla tabella anagrafica.Famiglia rimossa.")
    def test_document_deadline_links_to_owner_card_without_popup(self):
        self.client.force_login(self.user)
        stato_famiglia = StatoRelazioneFamiglia.objects.create(stato="Attiva")
        famiglia = Famiglia.objects.create(
            cognome_famiglia="Aldrovandi",
            stato_relazione_famiglia=stato_famiglia,
        )
        tipo_documento = TipoDocumento.objects.create(tipo_documento="Carta identita")
        current_year = timezone.localdate().year
        Documento.objects.create(
            famiglia=famiglia,
            tipo_documento=tipo_documento,
            file="documenti/carta-identita.pdf",
            scadenza=date(current_year, 5, 20),
        )
        Documento.objects.create(
            famiglia=famiglia,
            tipo_documento=tipo_documento,
            descrizione="Documento fuori anno corrente",
            file="documenti/documento-fuori-anno.pdf",
            scadenza=date(current_year + 1, 5, 20),
        )

        response = self.client.get(reverse("calendario_agenda"))

        owner_url = reverse("modifica_famiglia_logica", kwargs={"key": f"legacy-{famiglia.pk}"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Vai alla scheda")
        self.assertContains(response, f'href="{owner_url}?next=')
        self.assertContains(response, "%23calendar-events-card")
        self.assertNotContains(response, f"{owner_url}?popup=1")
        self.assertNotContains(response, "Documento fuori anno corrente")

    @skip("Legacy test basato sulla tabella anagrafica.Famiglia rimossa.")
    def test_rate_deadline_opens_rate_card_in_popup(self):
        self.client.force_login(self.user)
        stato_famiglia = StatoRelazioneFamiglia.objects.create(stato="Iscritta")
        famiglia = Famiglia.objects.create(
            cognome_famiglia="Bianchi",
            stato_relazione_famiglia=stato_famiglia,
        )
        studente = famiglia.studenti.create(nome="Luca", cognome="Bianchi")
        anno = AnnoScolastico.objects.create(
            nome_anno_scolastico="2025/2026",
            data_inizio=date(2025, 9, 1),
            data_fine=date(2026, 8, 31),
        )
        stato_iscrizione = StatoIscrizione.objects.create(stato_iscrizione="Attiva", ordine=1, attiva=True)
        condizione = CondizioneIscrizione.objects.create(
            anno_scolastico=anno,
            nome_condizione_iscrizione="Retta standard",
            numero_mensilita_default=10,
        )
        iscrizione = Iscrizione.objects.create(
            studente=studente,
            anno_scolastico=anno,
            stato_iscrizione=stato_iscrizione,
            condizione_iscrizione=condizione,
            data_iscrizione=date(2025, 9, 1),
        )
        rata = RataIscrizione.objects.create(
            iscrizione=iscrizione,
            famiglia=famiglia,
            tipo_rata=RataIscrizione.TIPO_MENSILE,
            numero_rata=1,
            mese_riferimento=9,
            anno_riferimento=2025,
            importo_dovuto=Decimal("100.00"),
            data_scadenza=date(2025, 9, 10),
        )

        response = self.client.get(reverse("calendario_agenda"))

        rata_url = reverse("modifica_rata_iscrizione", kwargs={"pk": rata.pk})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Scadenza retta - Bianchi Luca")
        self.assertContains(response, "Apri scheda")
        self.assertContains(response, f'data-popup-url="{rata_url}?popup=1"')
        self.assertContains(response, 'data-popup-title="Scheda rata"')
        self.assertContains(response, 'data-popup-window-features="width=1080,height=760,resizable=yes,scrollbars=yes"')

    def test_supplier_deadline_opens_supplier_document_card_in_popup(self):
        self.client.force_login(self.user)
        SistemaUtentePermessi.objects.filter(user=self.user).update(
            permesso_gestione_finanziaria=LivelloPermesso.GESTIONE
        )
        fornitore = Fornitore.objects.create(denominazione="Carta Srl")
        documento = DocumentoFornitore.objects.create(
            fornitore=fornitore,
            numero_documento="F-001",
            data_documento=date(2026, 5, 1),
            imponibile=Decimal("100.00"),
            iva=Decimal("22.00"),
            totale=Decimal("122.00"),
        )
        ScadenzaPagamentoFornitore.objects.create(
            documento=documento,
            data_scadenza=date(2026, 5, 20),
            importo_previsto=Decimal("122.00"),
        )

        response = self.client.get(reverse("calendario_agenda"))

        documento_url = reverse("modifica_documento_fornitore", kwargs={"pk": documento.pk})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Scadenza fornitore - Carta Srl")
        self.assertContains(response, "Apri scheda")
        self.assertContains(response, f'data-popup-url="{documento_url}?popup=1"')
        self.assertContains(response, 'data-popup-title="Scheda fattura fornitore"')
        self.assertContains(response, 'data-popup-window-features="width=1180,height=820,autoFit=no,resizable=yes,scrollbars=yes"')

        popup_response = self.client.get(f"{documento_url}?popup=1")
        self.assertEqual(popup_response.status_code, 200)
        self.assertContains(popup_response, 'body class="popup-page"')
        self.assertContains(popup_response, "supplier-document-detail-shell is-popup")
        self.assertContains(popup_response, "supplier-document-summary-grid")
        self.assertContains(popup_response, "supplier-document-form-grid")
        self.assertContains(popup_response, "supplier-deadline-view-list")
        self.assertContains(popup_response, "supplier-document-edit-table")
        self.assertContains(popup_response, 'id="documento-fornitore-form"')
        self.assertContains(popup_response, "is-view-mode")
        self.assertContains(
            popup_response,
            'id="documento-fornitore-lock-container" class="mode-lock-container supplier-document-fieldset main-fields-section" disabled',
        )
        self.assertContains(popup_response, 'id="enable-edit-documento-fornitore-btn"')
        self.assertContains(popup_response, "js/core/view-mode.js")
        self.assertContains(popup_response, 'name="popup" value="1"')
        self.assertNotContains(popup_response, '<span class="btn-label">Chiudi</span>')
        self.assertNotContains(popup_response, '<div class="breadcrumb">')

    def test_disabled_financial_module_hides_supplier_deadlines_from_calendar(self):
        self.client.force_login(self.user)
        SistemaUtentePermessi.objects.filter(user=self.user).update(
            permesso_gestione_finanziaria=LivelloPermesso.GESTIONE
        )
        SistemaImpostazioniGenerali.objects.create(modulo_gestione_finanziaria_attivo=False)
        fornitore = Fornitore.objects.create(denominazione="Carta Srl")
        documento = DocumentoFornitore.objects.create(
            fornitore=fornitore,
            numero_documento="F-001",
            data_documento=date(2026, 5, 1),
            imponibile=Decimal("100.00"),
            iva=Decimal("22.00"),
            totale=Decimal("122.00"),
        )
        ScadenzaPagamentoFornitore.objects.create(
            documento=documento,
            data_scadenza=date(2026, 5, 20),
            importo_previsto=Decimal("122.00"),
        )

        response = self.client.get(reverse("calendario_agenda"))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Scadenza fornitore - Carta Srl")
        self.assertNotContains(response, "fornitore-scadenza")

    def test_event_form_popup_closes_after_create(self):
        self.client.force_login(self.user)

        response = self.client.post(
            f'{reverse("crea_evento_calendario")}?popup=1',
            {
                "titolo": "Colloqui genitori",
                "categoria_evento": str(self.category.pk),
                "tipologia": "",
                "data_inizio": "2026-05-12",
                "data_fine": "2026-05-12",
                "intera_giornata": "on",
                "ripetizione": EventoCalendario.RIPETIZIONE_NESSUNA,
                "ripeti_ogni_intervallo": "1",
                "luogo": "Aula magna",
                "descrizione": "",
                "visibile": "on",
                "attivo": "on",
                "popup": "1",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Evento calendario creato correttamente.")
        self.assertTrue(EventoCalendario.objects.filter(titolo="Colloqui genitori").exists())

    def test_event_form_popup_uses_new_editor_layout(self):
        self.client.force_login(self.user)

        response = self.client.get(f'{reverse("crea_evento_calendario")}?popup=1&date=2026-05-12')

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "calendar-event-editor-shell is-popup")
        self.assertContains(response, "Nuovo evento calendario")
        self.assertContains(response, 'name="popup" value="1"')
        self.assertContains(response, 'value="2026-05-12"', count=2)

    def test_category_list_popup_opens_category_forms_in_popup(self):
        self.client.force_login(self.user)

        response = self.client.get(f'{reverse("lista_categorie_calendario")}?popup=1')

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "calendar-category-manager-shell is-popup")
        self.assertContains(response, "Chiudi e aggiorna")
        self.assertContains(response, f'data-popup-url="{reverse("crea_categoria_calendario")}?popup=1"')
        self.assertContains(response, f'data-popup-url="{reverse("modifica_categoria_calendario", kwargs={"pk": self.category.pk})}?popup=1"')

    def test_category_form_popup_uses_new_editor_layout(self):
        self.client.force_login(self.user)

        response = self.client.get(f'{reverse("modifica_categoria_calendario", kwargs={"pk": self.category.pk})}?popup=1')

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "calendar-category-manager-shell is-popup")
        self.assertContains(response, "Informazioni categoria")
        self.assertContains(response, 'name="popup" value="1"')
