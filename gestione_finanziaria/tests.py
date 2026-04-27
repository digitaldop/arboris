from datetime import date
from decimal import Decimal
import shutil
import tempfile

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from sistema.models import LivelloPermesso, SistemaUtentePermessi

from .models import (
    CategoriaSpesa,
    DocumentoFornitore,
    Fornitore,
    ScadenzaPagamentoFornitore,
    StatoDocumentoFornitore,
    StatoScadenzaFornitore,
    TipoDocumentoFornitore,
)


class FornitoriGestioneFinanziariaTests(TestCase):
    def setUp(self):
        self.media_root = tempfile.mkdtemp()
        self.media_override = override_settings(MEDIA_ROOT=self.media_root)
        self.media_override.enable()
        self.user = User.objects.create_user(
            username="finanza@example.com",
            email="finanza@example.com",
            password="Password123!",
        )
        SistemaUtentePermessi.objects.create(
            user=self.user,
            permesso_gestione_finanziaria=LivelloPermesso.GESTIONE,
        )
        self.client.force_login(self.user)

    def tearDown(self):
        self.media_override.disable()
        shutil.rmtree(self.media_root, ignore_errors=True)
        super().tearDown()

    def test_tipo_documento_fornitore_include_proforma_after_fattura(self):
        choices = list(TipoDocumentoFornitore.choices)

        self.assertEqual(choices[0], (TipoDocumentoFornitore.FATTURA, "Fattura"))
        self.assertEqual(choices[1], (TipoDocumentoFornitore.PROFORMA, "Proforma"))

    def test_categoria_spesa_crud_pages(self):
        response = self.client.post(
            reverse("crea_categoria_spesa"),
            {
                "nome": "Consulenze",
                "descrizione": "Consulenze e servizi professionali",
                "ordine": "1",
                "attiva": "on",
            },
        )

        self.assertRedirects(response, reverse("lista_categorie_spesa"))
        categoria = CategoriaSpesa.objects.get(nome="Consulenze")
        self.assertTrue(categoria.attiva)

        response = self.client.get(reverse("lista_categorie_spesa"))
        self.assertContains(response, "Consulenze")

    def test_fornitore_uses_categoria_spesa(self):
        categoria = CategoriaSpesa.objects.create(nome="Utenze")

        response = self.client.post(
            reverse("crea_fornitore"),
            {
                "denominazione": "Energia Srl",
                "tipo_soggetto": "azienda",
                "categoria_spesa": str(categoria.pk),
                "codice_fiscale": "",
                "partita_iva": "12345678901",
                "indirizzo": "Via Roma 1",
                "telefono": "051000000",
                "email": "amministrazione@energia.test",
                "pec": "",
                "codice_sdi": "ABC1234",
                "referente": "Mario Bianchi",
                "iban": "",
                "banca": "",
                "note": "",
                "attivo": "on",
            },
        )

        fornitore = Fornitore.objects.get(denominazione="Energia Srl")
        self.assertRedirects(response, reverse("modifica_fornitore", kwargs={"pk": fornitore.pk}))
        self.assertEqual(fornitore.categoria_spesa, categoria)

    def test_fornitore_form_renders_categoria_spesa_popup_controls(self):
        response = self.client.get(reverse("crea_fornitore"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Categoria di spesa")
        self.assertContains(response, 'id="add-categoria-spesa-btn"')
        self.assertContains(response, 'id="edit-categoria-spesa-btn"')
        self.assertContains(response, 'id="delete-categoria-spesa-btn"')
        self.assertContains(response, "js/pages/fornitore-form.js")

    def test_categoria_spesa_popup_create_returns_select_response(self):
        response = self.client.post(
            f"{reverse('crea_categoria_spesa')}?popup=1&target_input_name=categoria_spesa",
            {
                "popup": "1",
                "target_input_name": "categoria_spesa",
                "nome": "Servizi",
                "descrizione": "",
                "ordine": "",
                "attiva": "on",
            },
        )

        categoria = CategoriaSpesa.objects.get(nome="Servizi")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "dismissRelatedPopup")
        self.assertContains(response, "categoria_spesa")
        self.assertContains(response, str(categoria.pk))

    def test_documento_fornitore_creates_scadenza_and_calculates_totals(self):
        categoria = CategoriaSpesa.objects.create(nome="Manutenzioni")
        fornitore = Fornitore.objects.create(
            denominazione="Tecnica Srl",
            tipo_soggetto="azienda",
            categoria_spesa=categoria,
        )

        response = self.client.post(
            reverse("crea_documento_fornitore"),
            {
                "fornitore": str(fornitore.pk),
                "categoria_spesa": "",
                "tipo_documento": "fattura",
                "numero_documento": "F-001",
                "data_documento": "2026-04-15",
                "data_ricezione": "2026-04-16",
                "anno_competenza": "",
                "mese_competenza": "",
                "descrizione": "Manutenzione ordinaria",
                "imponibile": "1000.00",
                "aliquota_iva": "22.00",
                "iva": "",
                "totale": "",
                "stato": StatoDocumentoFornitore.DA_PAGARE,
                "note": "",
                "scadenze-TOTAL_FORMS": "1",
                "scadenze-INITIAL_FORMS": "0",
                "scadenze-MIN_NUM_FORMS": "0",
                "scadenze-MAX_NUM_FORMS": "1000",
                "scadenze-0-data_scadenza": "2026-05-31",
                "scadenze-0-importo_previsto": "1220.00",
                "scadenze-0-importo_pagato": "0.00",
                "scadenze-0-data_pagamento": "",
                "scadenze-0-stato": StatoScadenzaFornitore.PREVISTA,
                "scadenze-0-conto_bancario": "",
                "scadenze-0-movimento_finanziario": "",
                "scadenze-0-note": "",
            },
        )

        documento = DocumentoFornitore.objects.get(numero_documento="F-001")
        self.assertRedirects(response, reverse("modifica_documento_fornitore", kwargs={"pk": documento.pk}))
        self.assertEqual(documento.categoria_spesa, categoria)
        self.assertEqual(documento.iva, Decimal("220.00"))
        self.assertEqual(documento.totale, Decimal("1220.00"))
        scadenza = ScadenzaPagamentoFornitore.objects.get(documento=documento)
        self.assertEqual(scadenza.importo_previsto, Decimal("1220.00"))
        self.assertEqual(scadenza.stato, StatoScadenzaFornitore.PREVISTA)

        response = self.client.get(reverse("scadenziario_fornitori"))
        self.assertContains(response, "Tecnica Srl")
        self.assertContains(response, "F-001")

    def test_documento_fornitore_form_renders_search_popup_controls(self):
        response = self.client.get(reverse("crea_documento_fornitore"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-searchable-placeholder="Cerca un fornitore..."')
        self.assertContains(response, 'id="add-fornitore-btn"')
        self.assertContains(response, "Categoria di spesa")
        self.assertContains(response, 'id="add-documento-categoria-spesa-btn"')
        self.assertContains(response, 'id="edit-documento-categoria-spesa-btn"')
        self.assertContains(response, 'id="delete-documento-categoria-spesa-btn"')
        self.assertContains(response, 'data-related-type="conto_bancario"')
        self.assertContains(response, 'data-related-type="movimento_finanziario"')
        self.assertContains(response, "Gennaio")
        self.assertContains(response, "js/pages/documento-fornitore-form.js")

    def test_documento_fornitore_calculates_net_and_vat_from_total(self):
        categoria = CategoriaSpesa.objects.create(nome="Servizi")
        fornitore = Fornitore.objects.create(
            denominazione="Servizi Srl",
            tipo_soggetto="azienda",
            categoria_spesa=categoria,
        )

        response = self.client.post(
            reverse("crea_documento_fornitore"),
            {
                "fornitore": str(fornitore.pk),
                "categoria_spesa": "",
                "tipo_documento": "fattura",
                "numero_documento": "F-002",
                "data_documento": "2026-04-15",
                "data_ricezione": "",
                "anno_competenza": "",
                "mese_competenza": "4",
                "descrizione": "",
                "imponibile": "0.00",
                "aliquota_iva": "22.00",
                "iva": "",
                "totale": "122.00",
                "stato": StatoDocumentoFornitore.DA_PAGARE,
                "note": "",
                "scadenze-TOTAL_FORMS": "0",
                "scadenze-INITIAL_FORMS": "0",
                "scadenze-MIN_NUM_FORMS": "0",
                "scadenze-MAX_NUM_FORMS": "1000",
            },
        )

        documento = DocumentoFornitore.objects.get(numero_documento="F-002")
        self.assertRedirects(response, reverse("modifica_documento_fornitore", kwargs={"pk": documento.pk}))
        self.assertEqual(documento.imponibile, Decimal("100.00"))
        self.assertEqual(documento.iva, Decimal("22.00"))
        self.assertEqual(documento.totale, Decimal("122.00"))
        self.assertEqual(documento.mese_competenza, 4)

    def test_documento_fornitore_accepts_italian_currency_format(self):
        categoria = CategoriaSpesa.objects.create(nome="Pulizie")
        fornitore = Fornitore.objects.create(
            denominazione="Pulizie Srl",
            tipo_soggetto="azienda",
            categoria_spesa=categoria,
        )

        response = self.client.post(
            reverse("crea_documento_fornitore"),
            {
                "fornitore": str(fornitore.pk),
                "categoria_spesa": "",
                "tipo_documento": "fattura",
                "numero_documento": "F-IT",
                "data_documento": "2026-04-15",
                "data_ricezione": "",
                "anno_competenza": "",
                "mese_competenza": "",
                "descrizione": "",
                "imponibile": "1.000,00",
                "aliquota_iva": "22.00",
                "iva": "",
                "totale": "",
                "stato": StatoDocumentoFornitore.DA_PAGARE,
                "note": "",
                "scadenze-TOTAL_FORMS": "0",
                "scadenze-INITIAL_FORMS": "0",
                "scadenze-MIN_NUM_FORMS": "0",
                "scadenze-MAX_NUM_FORMS": "1000",
            },
        )

        documento = DocumentoFornitore.objects.get(numero_documento="F-IT")
        self.assertRedirects(response, reverse("modifica_documento_fornitore", kwargs={"pk": documento.pk}))
        self.assertEqual(documento.imponibile, Decimal("1000.00"))
        self.assertEqual(documento.iva, Decimal("220.00"))
        self.assertEqual(documento.totale, Decimal("1220.00"))

    def test_documento_fornitore_allegato_uses_supplier_prefix(self):
        categoria = CategoriaSpesa.objects.create(nome="Materiali")
        fornitore = Fornitore.objects.create(
            denominazione="Upload Srl",
            tipo_soggetto="azienda",
            categoria_spesa=categoria,
        )
        allegato = SimpleUploadedFile("fattura.pdf", b"pdf-content", content_type="application/pdf")

        response = self.client.post(
            reverse("crea_documento_fornitore"),
            {
                "fornitore": str(fornitore.pk),
                "categoria_spesa": "",
                "tipo_documento": "fattura",
                "numero_documento": "F-UP",
                "data_documento": "2026-04-15",
                "data_ricezione": "",
                "anno_competenza": "",
                "mese_competenza": "",
                "descrizione": "",
                "imponibile": "10.00",
                "aliquota_iva": "22.00",
                "iva": "",
                "totale": "",
                "stato": StatoDocumentoFornitore.DA_PAGARE,
                "allegato": allegato,
                "note": "",
                "scadenze-TOTAL_FORMS": "0",
                "scadenze-INITIAL_FORMS": "0",
                "scadenze-MIN_NUM_FORMS": "0",
                "scadenze-MAX_NUM_FORMS": "1000",
            },
        )

        documento = DocumentoFornitore.objects.get(numero_documento="F-UP")
        self.assertRedirects(response, reverse("modifica_documento_fornitore", kwargs={"pk": documento.pk}))
        self.assertTrue(documento.allegato.name.startswith("documenti_fornitori/"))

    def test_scadenza_auto_status_allows_manual_override(self):
        categoria = CategoriaSpesa.objects.create(nome="Utenze")
        fornitore = Fornitore.objects.create(
            denominazione="Acqua Srl",
            tipo_soggetto="azienda",
            categoria_spesa=categoria,
        )
        documento = DocumentoFornitore.objects.create(
            fornitore=fornitore,
            categoria_spesa=categoria,
            numero_documento="SCAD-1",
            data_documento=date(2026, 4, 20),
            imponibile=Decimal("100.00"),
            iva=Decimal("22.00"),
            totale=Decimal("122.00"),
        )

        scadenza = ScadenzaPagamentoFornitore.objects.create(
            documento=documento,
            data_scadenza=date(2000, 1, 1),
            importo_previsto=Decimal("122.00"),
            importo_pagato=Decimal("0.00"),
            stato=StatoScadenzaFornitore.PREVISTA,
        )
        self.assertEqual(scadenza.stato, StatoScadenzaFornitore.SCADUTA)

        scadenza.stato = StatoScadenzaFornitore.PREVISTA
        scadenza._preserve_manual_stato = True
        scadenza.save()
        self.assertEqual(scadenza.stato, StatoScadenzaFornitore.PREVISTA)

    def test_fornitori_pages_render(self):
        categoria = CategoriaSpesa.objects.create(nome="Materiali")
        fornitore = Fornitore.objects.create(
            denominazione="Carta Srl",
            tipo_soggetto="azienda",
            categoria_spesa=categoria,
        )
        documento = DocumentoFornitore.objects.create(
            fornitore=fornitore,
            categoria_spesa=categoria,
            numero_documento="MAT-1",
            data_documento=date(2026, 4, 20),
            imponibile=Decimal("50.00"),
            iva=Decimal("11.00"),
            totale=Decimal("61.00"),
        )

        urls = [
            reverse("dashboard_gestione_finanziaria"),
            reverse("lista_fornitori"),
            reverse("modifica_fornitore", kwargs={"pk": fornitore.pk}),
            reverse("lista_documenti_fornitori"),
            reverse("modifica_documento_fornitore", kwargs={"pk": documento.pk}),
            reverse("scadenziario_fornitori"),
        ]

        for url in urls:
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200, url)
