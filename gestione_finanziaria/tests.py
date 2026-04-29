from datetime import date
from decimal import Decimal
import shutil
import tempfile

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from anagrafica.models import Famiglia, StatoRelazioneFamiglia, Studente
from economia.models import CondizioneIscrizione, Iscrizione, RataIscrizione, StatoIscrizione, TariffaCondizioneIscrizione
from scuola.models import AnnoScolastico, Classe
from sistema.models import LivelloPermesso, SistemaUtentePermessi

from .models import (
    CategoriaFinanziaria,
    CategoriaSpesa,
    CondizioneRegolaCategorizzazione,
    ContoBancario,
    DocumentoFornitore,
    Fornitore,
    MovimentoFinanziario,
    ProviderBancario,
    RegolaCategorizzazione,
    ScadenzaPagamentoFornitore,
    SegnoMovimento,
    StatoRiconciliazione,
    StatoDocumentoFornitore,
    StatoScadenzaFornitore,
    TipoCategoriaFinanziaria,
    TipoProviderBancario,
    TipoDocumentoFornitore,
)
from .importers import CsvImporter, CsvImporterConfig, detect_csv_import_config
from .importers.service import importa_movimenti_da_file
from .services import applica_regole_a_movimento


CBI_CSV_SAMPLE = (
    '"Rag. Soc./ Intestatario";"ABI";"CAB";"Conto";"Operazione";"Valuta";"Importo";"Causale";'
    '"Causale Interna";"Descrizione";"Identificativo End to End";"Informazioni di riconciliazione"\n'
    '"IL SOLE E L\'ALTRE STELLE SRL IMPRESA SOCIALE";"05034";"37060";"000000003228";"24/04/2026";'
    '"24/04/2026";"300,00";"48";"0";"BONIF. VS. FAVORE - YYY24042026 GHEDUZZI";"NOTPROVIDED ";'
    '"Iscrizione 4 classe 2026-2027 Gheduzzi Sofia "\n'
    '"IL SOLE E L\'ALTRE STELLE SRL IMPRESA SOCIALE";"05034";"37060";"000000003228";"24/04/2026";'
    '"24/04/2026";"-24,40";"50";"C";"ADDEBITO DIRETTO SDD - PayPal Europe";"";""\n'
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

    def test_cbi_csv_autodetect_parses_movements(self):
        detection = detect_csv_import_config(CBI_CSV_SAMPLE.encode("utf-8"))

        self.assertEqual(detection.formato_rilevato, "CSV CBI")
        self.assertEqual(detection.config.delimiter, ";")
        self.assertEqual(detection.abi, "05034")
        self.assertEqual(detection.cab, "37060")
        self.assertEqual(detection.numero_conto, "000000003228")

        movimenti = list(CsvImporter(detection.config).parse(CBI_CSV_SAMPLE.encode("utf-8")))

        self.assertEqual(len(movimenti), 2)
        self.assertEqual(movimenti[0].data_contabile, date(2026, 4, 24))
        self.assertEqual(movimenti[0].importo, Decimal("300.00"))
        self.assertIn("Gheduzzi Sofia", movimenti[0].descrizione)
        self.assertIn("BONIF. VS. FAVORE", movimenti[0].descrizione)
        self.assertEqual(movimenti[0].provider_transaction_id, "")
        self.assertEqual(movimenti[1].importo, Decimal("-24.40"))

    def test_import_estratto_conto_preview_and_confirm_with_cbi_csv(self):
        provider = ProviderBancario.objects.create(
            nome="Import file test",
            tipo=TipoProviderBancario.IMPORT_FILE,
        )
        conto = ContoBancario.objects.create(
            nome_conto="Conto CBI",
            iban="IT00X0503437060000000003228",
            provider=provider,
            attivo=True,
        )
        uploaded = SimpleUploadedFile(
            "movimenti_cbi.csv",
            CBI_CSV_SAMPLE.encode("utf-8"),
            content_type="text/csv",
        )

        preview_response = self.client.post(
            reverse("import_estratto_conto"),
            {
                "import_action": "preview",
                "formato": "auto",
                "conto": "",
                "file": uploaded,
            },
        )

        self.assertEqual(preview_response.status_code, 200)
        self.assertContains(preview_response, "Anteprima import")
        self.assertContains(preview_response, "CSV CBI")
        self.assertEqual(preview_response.context["selected_conto"], conto)
        token = preview_response.context["import_token"]
        self.assertTrue(token)

        confirm_response = self.client.post(
            reverse("import_estratto_conto"),
            {
                "import_action": "confirm",
                "import_token": token,
                "conto": str(conto.pk),
            },
        )

        self.assertEqual(confirm_response.status_code, 200)
        self.assertEqual(MovimentoFinanziario.objects.filter(conto=conto).count(), 2)
        movimento = MovimentoFinanziario.objects.get(importo=Decimal("300.00"))
        self.assertIn("Gheduzzi Sofia", movimento.descrizione)

    def test_regole_categorizzazione_supportano_condizioni_testuali_avanzate(self):
        categoria = CategoriaFinanziaria.objects.create(nome="Incassi rette")
        RegolaCategorizzazione.objects.create(
            nome="Quote e commissioni",
            condizione_tipo=CondizioneRegolaCategorizzazione.DESCRIZIONE_CONTIENE,
            pattern="COMM. SU BONIFICI | quota + maggio",
            categoria_da_assegnare=categoria,
        )

        movimento_or = MovimentoFinanziario(
            data_contabile=date(2026, 4, 24),
            importo=Decimal("-2.00"),
            descrizione="COMM.SU BONIFICI AREA SEPA",
        )
        regola_or = applica_regole_a_movimento(movimento_or)

        self.assertIsNotNone(regola_or)
        self.assertEqual(movimento_or.categoria_id, categoria.pk)

        movimento_and = MovimentoFinanziario(
            data_contabile=date(2026, 5, 10),
            importo=Decimal("100.00"),
            descrizione="Versamento quota retta mese di maggio",
        )
        regola_and = applica_regole_a_movimento(movimento_and)

        self.assertIsNotNone(regola_and)
        self.assertEqual(movimento_and.categoria_id, categoria.pk)

        movimento_no_match = MovimentoFinanziario(
            data_contabile=date(2026, 5, 11),
            importo=Decimal("100.00"),
            descrizione="Versamento quota generica",
        )
        self.assertIsNone(applica_regole_a_movimento(movimento_no_match))

    def test_import_movimenti_riconcilia_automaticamente_retta_studente(self):
        provider = ProviderBancario.objects.create(
            nome="Import rette test",
            tipo=TipoProviderBancario.IMPORT_FILE,
        )
        conto = ContoBancario.objects.create(
            nome_conto="Conto rette",
            iban="IT00X0000000000000000000000",
            provider=provider,
            attivo=True,
        )
        stato_relazione = StatoRelazioneFamiglia.objects.create(stato="Iscritta")
        famiglia = Famiglia.objects.create(
            cognome_famiglia="Bianchi",
            stato_relazione_famiglia=stato_relazione,
        )
        studente = Studente.objects.create(
            famiglia=famiglia,
            nome="Luca",
            cognome="Bianchi",
            data_nascita=date(2020, 5, 5),
        )
        anno = AnnoScolastico.objects.create(
            nome_anno_scolastico="2025/2026",
            data_inizio=date(2025, 9, 1),
            data_fine=date(2026, 6, 30),
        )
        classe = Classe.objects.create(
            nome_classe="Materna",
            ordine_classe=1,
        )
        stato_iscrizione = StatoIscrizione.objects.create(stato_iscrizione="Iscritto")
        condizione = CondizioneIscrizione.objects.create(
            anno_scolastico=anno,
            nome_condizione_iscrizione="Retta standard",
            numero_mensilita_default=10,
            mese_prima_retta=9,
            giorno_scadenza_rate=10,
        )
        TariffaCondizioneIscrizione.objects.create(
            condizione_iscrizione=condizione,
            ordine_figlio_da=1,
            retta_annuale=Decimal("1000.00"),
            preiscrizione=Decimal("0.00"),
        )
        iscrizione = Iscrizione.objects.create(
            studente=studente,
            anno_scolastico=anno,
            classe=classe,
            stato_iscrizione=stato_iscrizione,
            condizione_iscrizione=condizione,
            data_iscrizione=date(2025, 9, 1),
            data_fine_iscrizione=date(2026, 6, 30),
        )
        self.assertEqual(iscrizione.sync_rate_schedule(), "created")
        rata = RataIscrizione.objects.get(iscrizione=iscrizione, numero_rata=1)
        self.assertEqual(rata.importo_finale, Decimal("100.00"))

        raw_csv = (
            "Data;Importo;Descrizione\n"
            "10/09/2025;100,00;Bonifico retta settembre Luca Bianchi\n"
        ).encode("utf-8")
        config = CsvImporterConfig(
            delimiter=";",
            ha_intestazione=True,
            colonna_data_contabile="Data",
            colonna_importo="Importo",
            colonna_descrizione="Descrizione",
        )

        risultato = importa_movimenti_da_file(
            parser=CsvImporter(config),
            raw_bytes=raw_csv,
            conto=conto,
            provider=provider,
            nome_file="rette.csv",
        )

        self.assertEqual(risultato.inseriti, 1)
        self.assertEqual(risultato.riconciliati, 1)

        movimento = MovimentoFinanziario.objects.get(conto=conto)
        rata.refresh_from_db()
        self.assertEqual(movimento.rata_iscrizione_id, rata.pk)
        self.assertEqual(movimento.stato_riconciliazione, StatoRiconciliazione.RICONCILIATO)
        self.assertTrue(rata.pagata)
        self.assertEqual(rata.importo_pagato, Decimal("100.00"))
        self.assertEqual(rata.data_pagamento, date(2025, 9, 10))

    def test_lista_movimenti_colora_entrate_e_uscite(self):
        categoria = CategoriaFinanziaria.objects.create(
            nome="Rette",
            tipo=TipoCategoriaFinanziaria.ENTRATA,
        )
        MovimentoFinanziario.objects.create(
            data_contabile=date(2026, 4, 1),
            importo=Decimal("100.00"),
            descrizione="Incasso retta",
            categoria=categoria,
        )
        MovimentoFinanziario.objects.create(
            data_contabile=date(2026, 4, 2),
            importo=Decimal("-25.00"),
            descrizione="Spesa bancaria",
            categoria=categoria,
        )

        response = self.client.get(reverse("lista_movimenti_finanziari"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "finance-movement-filters")
        self.assertContains(response, "finance-movement-row-incoming")
        self.assertContains(response, "finance-movement-row-outgoing")

    def test_report_categorie_filtra_per_anno_scolastico(self):
        anno = AnnoScolastico.objects.create(
            nome_anno_scolastico="2025/2026",
            data_inizio=date(2025, 9, 1),
            data_fine=date(2026, 6, 30),
        )
        categoria = CategoriaFinanziaria.objects.create(
            nome="Rette",
            tipo=TipoCategoriaFinanziaria.ENTRATA,
        )
        MovimentoFinanziario.objects.create(
            data_contabile=date(2025, 8, 31),
            importo=Decimal("999.00"),
            descrizione="Fuori anno scolastico",
            categoria=categoria,
        )
        MovimentoFinanziario.objects.create(
            data_contabile=date(2025, 9, 1),
            importo=Decimal("100.00"),
            descrizione="Inizio anno scolastico",
            categoria=categoria,
        )
        MovimentoFinanziario.objects.create(
            data_contabile=date(2026, 6, 30),
            importo=Decimal("50.00"),
            descrizione="Fine anno scolastico",
            categoria=categoria,
        )
        MovimentoFinanziario.objects.create(
            data_contabile=date(2026, 7, 1),
            importo=Decimal("999.00"),
            descrizione="Dopo anno scolastico",
            categoria=categoria,
        )

        response = self.client.get(
            reverse("report_categorie_annuale"),
            {"periodo": "scolastico", "anno_scolastico": str(anno.pk)},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["periodo_tipo"], "scolastico")
        self.assertEqual(response.context["periodo_label"], "anno scolastico 2025/2026")
        self.assertEqual(response.context["totale_entrate"], Decimal("150.00"))

        response = self.client.get(
            reverse("report_categorie_mensile"),
            {"periodo": "scolastico", "anno_scolastico": str(anno.pk)},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["periodo_tipo"], "scolastico")
        self.assertEqual(response.context["mesi"][0], "Set 2025")
        self.assertEqual(response.context["mesi"][-1], "Giu 2026")
        self.assertEqual(response.context["totale_generale"], Decimal("150.00"))
