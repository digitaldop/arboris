from datetime import date, datetime
from decimal import Decimal
import shutil
import tempfile
from unittest.mock import Mock, patch

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from anagrafica.models import Famiglia, Familiare, RelazioneFamiliare, StatoRelazioneFamiglia, Studente
from economia.models import CondizioneIscrizione, Iscrizione, RataIscrizione, StatoIscrizione, TariffaCondizioneIscrizione
from scuola.models import AnnoScolastico, Classe
from sistema.models import LivelloPermesso, SistemaUtentePermessi

from .models import (
    CategoriaFinanziaria,
    CanaleMovimento,
    CondizioneRegolaCategorizzazione,
    ContoBancario,
    DocumentoFornitore,
    FattureInCloudConnessione,
    Fornitore,
    FonteSaldo,
    MovimentoFinanziario,
    NotificaFinanziaria,
    PagamentoFornitore,
    OrigineMovimento,
    ProviderBancario,
    RiconciliazioneRataMovimento,
    RegolaCategorizzazione,
    SaldoConto,
    ScadenzaPagamentoFornitore,
    SegnoMovimento,
    StatoRiconciliazione,
    StatoDocumentoFornitore,
    StatoScadenzaFornitore,
    TipoCategoriaFinanziaria,
    TipoContoFinanziario,
    TipoProviderBancario,
    TipoDocumentoFornitore,
)


def crea_categoria_spesa_test(nome, **kwargs):
    kwargs.setdefault("tipo", TipoCategoriaFinanziaria.SPESA)
    return CategoriaFinanziaria.objects.create(nome=nome, **kwargs)
from .fatture_in_cloud import (
    authorization_url,
    has_oauth_credentials,
    importa_documento_fatture_in_cloud,
    sincronizza_fatture_in_cloud,
)
from .importers import CsvImporter, CsvImporterConfig, detect_csv_import_config
from .importers.service import importa_movimenti_da_file
from .services import (
    applica_regole_a_movimento,
    importo_movimento_disponibile_fornitori,
    riconcilia_movimento_con_scadenza_fornitore,
    riconcilia_movimento_con_rate,
    trova_scadenze_fornitori_candidate,
    trova_movimenti_candidati_per_rate,
    trova_rate_candidate,
)


CBI_CSV_SAMPLE = (
    '"Rag. Soc./ Intestatario";"ABI";"CAB";"Conto";"Operazione";"Valuta";"Importo";"Causale";'
    '"Causale Interna";"Descrizione";"Identificativo End to End";"Informazioni di riconciliazione"\n'
    '"IL SOLE E L\'ALTRE STELLE SRL IMPRESA SOCIALE";"05034";"37060";"000000003228";"24/04/2026";'
    '"24/04/2026";"300,00";"48";"0";"BONIF. VS. FAVORE - YYY24042026 GHEDUZZI";"NOTPROVIDED ";'
    '"Iscrizione 4 classe 2026-2027 Gheduzzi Sofia "\n'
    '"IL SOLE E L\'ALTRE STELLE SRL IMPRESA SOCIALE";"05034";"37060";"000000003228";"24/04/2026";'
    '"24/04/2026";"-24,40";"50";"C";"ADDEBITO DIRETTO SDD - PayPal Europe";"";""\n'
)


class RiconciliazioneRateMatchingTests(TestCase):
    def setUp(self):
        self.stato_relazione = StatoRelazioneFamiglia.objects.create(stato="Iscritta")
        self.relazione_genitore = RelazioneFamiliare.objects.create(relazione="Genitore")
        self.anno = AnnoScolastico.objects.create(
            nome_anno_scolastico="2025/2026",
            data_inizio=date(2025, 9, 1),
            data_fine=date(2026, 6, 30),
        )
        self.classe = Classe.objects.create(nome_classe="Primaria", ordine_classe=1)
        self.stato_iscrizione = StatoIscrizione.objects.create(stato_iscrizione="Iscritto")
        self.condizione = CondizioneIscrizione.objects.create(
            anno_scolastico=self.anno,
            nome_condizione_iscrizione="Retta standard",
            numero_mensilita_default=10,
        )
        TariffaCondizioneIscrizione.objects.create(
            condizione_iscrizione=self.condizione,
            ordine_figlio_da=1,
            retta_annuale=Decimal("1000.00"),
        )

    def _crea_rata(self, *, famiglia_cognome, studente_nome, studente_cognome, genitore_nome, genitore_cognome):
        famiglia = Famiglia.objects.create(
            cognome_famiglia=famiglia_cognome,
            stato_relazione_famiglia=self.stato_relazione,
        )
        Familiare.objects.create(
            famiglia=famiglia,
            relazione_familiare=self.relazione_genitore,
            nome=genitore_nome,
            cognome=genitore_cognome,
        )
        studente = Studente.objects.create(
            famiglia=famiglia,
            nome=studente_nome,
            cognome=studente_cognome,
            data_nascita=date(2020, 5, 5),
        )
        iscrizione = Iscrizione.objects.create(
            studente=studente,
            anno_scolastico=self.anno,
            classe=self.classe,
            stato_iscrizione=self.stato_iscrizione,
            condizione_iscrizione=self.condizione,
            data_iscrizione=date(2025, 9, 1),
            data_fine_iscrizione=date(2026, 6, 30),
        )
        rata = RataIscrizione.objects.create(
            iscrizione=iscrizione,
            famiglia=famiglia,
            numero_rata=1,
            mese_riferimento=9,
            anno_riferimento=2025,
            importo_dovuto=Decimal("100.00"),
            importo_finale=Decimal("100.00"),
            data_scadenza=date(2025, 9, 10),
        )
        return famiglia, studente, rata

    def test_rate_candidate_usa_nominativi_genitori_in_causale(self):
        _, _, rata_corretta = self._crea_rata(
            famiglia_cognome="Rossi",
            studente_nome="Luca",
            studente_cognome="Rossi",
            genitore_nome="Simone",
            genitore_cognome="Rossi",
        )
        _, _, rata_altra_famiglia = self._crea_rata(
            famiglia_cognome="Rossi",
            studente_nome="Anna",
            studente_cognome="Rossi",
            genitore_nome="Paolo",
            genitore_cognome="Rossi",
        )
        movimento = MovimentoFinanziario.objects.create(
            data_contabile=date(2025, 9, 10),
            importo=Decimal("100.00"),
            descrizione="Bonifico retta settembre Simone Rossi",
            stato_riconciliazione=StatoRiconciliazione.NON_RICONCILIATO,
        )

        candidate_ids = [candidato.rata.pk for candidato in trova_rate_candidate(movimento)]

        self.assertIn(rata_corretta.pk, candidate_ids)
        self.assertNotIn(rata_altra_famiglia.pk, candidate_ids)

    def test_movimenti_candidati_escludono_causali_di_altri_genitori(self):
        _, _, rata = self._crea_rata(
            famiglia_cognome="Rossi",
            studente_nome="Luca",
            studente_cognome="Rossi",
            genitore_nome="Simone",
            genitore_cognome="Rossi",
        )
        movimento_corretto = MovimentoFinanziario.objects.create(
            data_contabile=date(2025, 9, 10),
            importo=Decimal("100.00"),
            descrizione="Bonifico retta settembre Simone Rossi",
            stato_riconciliazione=StatoRiconciliazione.NON_RICONCILIATO,
        )
        movimento_altra_famiglia = MovimentoFinanziario.objects.create(
            data_contabile=date(2025, 9, 10),
            importo=Decimal("100.00"),
            descrizione="Bonifico retta settembre Paolo Rossi",
            stato_riconciliazione=StatoRiconciliazione.NON_RICONCILIATO,
        )

        candidate_ids = [
            candidato.movimento.pk
            for candidato in trova_movimenti_candidati_per_rate(rata, [rata])
        ]

        self.assertIn(movimento_corretto.pk, candidate_ids)
        self.assertNotIn(movimento_altra_famiglia.pk, candidate_ids)

    def test_salvataggio_riconciliazione_blocca_movimento_senza_nominativo_compatibile(self):
        _, _, rata = self._crea_rata(
            famiglia_cognome="Rossi",
            studente_nome="Luca",
            studente_cognome="Rossi",
            genitore_nome="Simone",
            genitore_cognome="Rossi",
        )
        movimento = MovimentoFinanziario.objects.create(
            data_contabile=date(2025, 9, 10),
            importo=Decimal("100.00"),
            descrizione="Bonifico retta settembre Paolo Rossi",
            stato_riconciliazione=StatoRiconciliazione.NON_RICONCILIATO,
        )

        with self.assertRaisesMessage(ValidationError, "Controllo di sicurezza"):
            riconcilia_movimento_con_rate(movimento, [(rata, Decimal("100.00"))])

        movimento.refresh_from_db()
        rata.refresh_from_db()
        self.assertEqual(movimento.stato_riconciliazione, StatoRiconciliazione.NON_RICONCILIATO)
        self.assertFalse(rata.pagata)


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
        categoria = CategoriaFinanziaria.objects.get(nome="Consulenze", tipo=TipoCategoriaFinanziaria.SPESA)
        self.assertTrue(categoria.attiva)

        response = self.client.get(reverse("lista_categorie_spesa"))
        self.assertContains(response, "Consulenze")

    def test_categorie_finanziarie_list_renders_parent_child_tree(self):
        categoria_padre = CategoriaFinanziaria.objects.create(
            nome="Utenze",
            tipo=TipoCategoriaFinanziaria.SPESA,
            ordine=1,
        )
        CategoriaFinanziaria.objects.create(
            nome="Energia elettrica",
            tipo=TipoCategoriaFinanziaria.SPESA,
            parent=categoria_padre,
            ordine=1,
        )

        response = self.client.get(reverse("lista_categorie_finanziarie"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Utenze")
        self.assertContains(response, "Energia elettrica")
        self.assertContains(response, 'data-report-category-toggle="categoria-')
        self.assertContains(response, 'data-report-category-parent="categoria-')
        self.assertContains(response, "category-tree-badge-parent")
        self.assertContains(response, "Figlia")

    def test_categoria_finanziaria_form_has_color_picker_and_icon_library(self):
        response = self.client.get(reverse("crea_categoria_finanziaria"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'type="color"')
        self.assertContains(response, 'id="id_colore_picker"')
        self.assertContains(response, "data-category-icon-picker")
        self.assertContains(response, 'data-icon-value="banknote"')
        self.assertContains(response, "js/pages/categoria-finanziaria-form.js")

    def test_fornitore_uses_categoria_spesa(self):
        categoria = crea_categoria_spesa_test("Utenze")

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

        categoria = CategoriaFinanziaria.objects.get(nome="Servizi", tipo=TipoCategoriaFinanziaria.SPESA)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "dismissRelatedPopup")
        self.assertContains(response, "categoria_spesa")
        self.assertContains(response, str(categoria.pk))

    def test_documento_fornitore_creates_scadenza_and_calculates_totals(self):
        categoria = crea_categoria_spesa_test("Manutenzioni")
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
        categoria = crea_categoria_spesa_test("Servizi")
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
        categoria = crea_categoria_spesa_test("Pulizie")
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
        categoria = crea_categoria_spesa_test("Materiali")
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
        categoria = crea_categoria_spesa_test("Utenze")
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

    def test_importa_documento_fatture_in_cloud_crea_documento_scadenza_notifica(self):
        connessione = FattureInCloudConnessione.objects.create(
            nome="FIC",
            company_id=123,
        )
        payload = {
            "id": 987,
            "type": "expense",
            "description": "Consulenza mensile",
            "invoice_number": "FC-42",
            "date": "2026-04-20",
            "next_due_date": "2026-05-20",
            "amount_net": "1000.00",
            "amount_vat": "220.00",
            "amount_gross": "1220.00",
            "entity": {
                "name": "Cloud Supplier Srl",
                "vat_number": "IT12345678901",
                "tax_code": "12345678901",
                "address_street": "Via Nuvola 7",
                "address_postal_code": "40100",
                "address_city": "Bologna",
                "address_province": "BO",
                "email": "info@example.com",
                "certified_email": "cloud@examplepec.it",
                "phone": "051123456",
                "ei_code": "ABC1234",
                "bank_iban": "IT60X0542811101000000123456",
                "bank_name": "Banca Cloud",
            },
            "payments_list": [
                {
                    "due_date": "2026-05-20",
                    "amount": "1220.00",
                    "status": "not_paid",
                }
            ],
        }

        result = importa_documento_fatture_in_cloud(connessione, payload, pending=False, utente=self.user)

        self.assertTrue(result["created"])
        self.assertTrue(result["fornitore_created"])
        self.assertFalse(result["fornitore_updated"])
        documento = DocumentoFornitore.objects.get(external_id="987")
        self.assertEqual(documento.fornitore.denominazione, "Cloud Supplier Srl")
        self.assertEqual(documento.fornitore.partita_iva, "12345678901")
        self.assertEqual(documento.fornitore.codice_fiscale, "12345678901")
        self.assertEqual(documento.fornitore.indirizzo, "Via Nuvola 7 40100 Bologna BO")
        self.assertEqual(documento.fornitore.email, "info@example.com")
        self.assertEqual(documento.fornitore.pec, "cloud@examplepec.it")
        self.assertEqual(documento.fornitore.telefono, "051123456")
        self.assertEqual(documento.fornitore.codice_sdi, "ABC1234")
        self.assertEqual(documento.fornitore.iban, "IT60X0542811101000000123456")
        self.assertEqual(documento.fornitore.banca, "Banca Cloud")
        self.assertEqual(documento.numero_documento, "FC-42")
        self.assertEqual(documento.totale, Decimal("1220.00"))
        self.assertEqual(documento.origine, "fatture_in_cloud")
        scadenza = documento.scadenze.get()
        self.assertEqual(scadenza.data_scadenza, date(2026, 5, 20))
        self.assertEqual(scadenza.importo_previsto, Decimal("1220.00"))
        self.assertTrue(NotificaFinanziaria.objects.filter(documento=documento).exists())

        result = importa_documento_fatture_in_cloud(connessione, payload, pending=False, utente=self.user)
        self.assertFalse(result["created"])
        self.assertFalse(result["fornitore_created"])
        self.assertFalse(result["fornitore_updated"])
        self.assertEqual(DocumentoFornitore.objects.filter(external_id="987").count(), 1)
        self.assertEqual(NotificaFinanziaria.objects.filter(documento=documento).count(), 1)

    def test_importa_documento_fatture_in_cloud_arricchisce_fornitore_esistente(self):
        connessione = FattureInCloudConnessione.objects.create(
            nome="FIC",
            company_id=123,
        )
        fornitore = Fornitore.objects.create(
            denominazione="Fornitore gia censito",
            tipo_soggetto="azienda",
            partita_iva="12345678906",
            email="manuale@example.com",
            attivo=False,
        )
        payload = {
            "id": 992,
            "type": "expense",
            "description": "Fattura con anagrafica completa",
            "invoice_number": "SUP-1",
            "date": "2026-04-24",
            "amount_net": "200.00",
            "amount_vat": "44.00",
            "amount_gross": "244.00",
            "entity": {
                "name": "Nome da Fatture in Cloud",
                "vat_number": "IT12345678906",
                "tax_code": "12345678906",
                "address_street": "Via Dati 10",
                "address_postal_code": "20100",
                "address_city": "Milano",
                "address_province": "MI",
                "email": "fic@example.com",
                "certified_email": "fornitore@examplepec.it",
                "phone": "02123456",
                "ei_code": "XYZ9876",
            },
            "payments_list": [
                {
                    "due_date": "2026-05-24",
                    "amount": "244.00",
                    "iban": "IT60 X054 2811 1010 0000 0123 456",
                    "bank_name": "Banca Test",
                }
            ],
        }

        result = importa_documento_fatture_in_cloud(connessione, payload, pending=False, utente=self.user)

        self.assertFalse(result["fornitore_created"])
        self.assertTrue(result["fornitore_updated"])
        self.assertEqual(Fornitore.objects.count(), 1)
        fornitore.refresh_from_db()
        self.assertEqual(fornitore.denominazione, "Fornitore gia censito")
        self.assertEqual(fornitore.email, "manuale@example.com")
        self.assertEqual(fornitore.codice_fiscale, "12345678906")
        self.assertEqual(fornitore.indirizzo, "Via Dati 10 20100 Milano MI")
        self.assertEqual(fornitore.pec, "fornitore@examplepec.it")
        self.assertEqual(fornitore.telefono, "02123456")
        self.assertEqual(fornitore.codice_sdi, "XYZ9876")
        self.assertEqual(fornitore.iban, "IT60X0542811101000000123456")
        self.assertEqual(fornitore.banca, "Banca Test")
        self.assertFalse(fornitore.attivo)

    def test_importa_documento_fatture_in_cloud_accetta_url_allegato_lunghi(self):
        connessione = FattureInCloudConnessione.objects.create(
            nome="FIC",
            company_id=123,
        )
        attachment_url = "https://files.example.com/" + ("a" * 1200)
        payload = {
            "id": 988,
            "type": "expense",
            "description": "Documento con URL allegato lungo",
            "invoice_number": "FC-43",
            "date": "2026-04-21",
            "amount_net": "100.00",
            "amount_vat": "22.00",
            "amount_gross": "122.00",
            "attachment_url": attachment_url,
            "entity": {"name": "Long Link Supplier Srl", "vat_number": "IT12345678902"},
        }

        importa_documento_fatture_in_cloud(connessione, payload, pending=False, utente=self.user)

        documento = DocumentoFornitore.objects.get(external_id="988")
        self.assertLessEqual(len(documento.external_url), 1000)
        self.assertEqual(documento.external_payload["attachment_url"], attachment_url)
        self.assertEqual(
            DocumentoFornitore._meta.get_field("external_url").max_length,
            1000,
        )

    def test_importa_documento_fatture_in_cloud_legge_fornitore_e_scadenza_da_e_invoice(self):
        connessione = FattureInCloudConnessione.objects.create(
            nome="FIC",
            company_id=123,
        )
        payload = {
            "id": 989,
            "type": "expense",
            "description": "Fattura elettronica ricevuta",
            "date": "2026-04-22",
            "amount_net": "100.00",
            "amount_vat": "22.00",
            "e_invoice": {
                "dati_generali": {
                    "dati_generali_documento": {
                        "numero": "EI-44",
                        "importo_totale_documento": "122.00",
                    }
                },
                "cedente_prestatore": {
                    "dati_anagrafici": {
                        "id_fiscale_iva": {"id_codice": "12345678903"},
                        "codice_fiscale": "12345678903",
                        "anagrafica": {"denominazione": "E Invoice Supplier Srl"},
                    },
                    "sede": {
                        "indirizzo": "Via Roma 1",
                        "cap": "40100",
                        "comune": "Bologna",
                        "provincia": "BO",
                    },
                    "contatti": {"email": "fatture@example.com"},
                },
                "dati_pagamento": [
                    {
                        "dettaglio_pagamento": [
                            {
                                "data_scadenza_pagamento": "2026-06-15",
                                "importo_pagamento": "122.00",
                            }
                        ]
                    }
                ],
            },
        }

        importa_documento_fatture_in_cloud(connessione, payload, pending=True, utente=self.user)

        documento = DocumentoFornitore.objects.get(external_id="989")
        self.assertEqual(documento.fornitore.denominazione, "E Invoice Supplier Srl")
        self.assertEqual(documento.fornitore.partita_iva, "12345678903")
        self.assertEqual(documento.numero_documento, "EI-44")
        self.assertEqual(documento.totale, Decimal("122.00"))
        scadenza = documento.scadenze.get()
        self.assertEqual(scadenza.data_scadenza, date(2026, 6, 15))
        self.assertEqual(scadenza.importo_previsto, Decimal("122.00"))

    def test_importa_documento_fatture_in_cloud_aggiorna_scadenza_importata_non_pagata(self):
        connessione = FattureInCloudConnessione.objects.create(
            nome="FIC",
            company_id=123,
        )
        fornitore = Fornitore.objects.create(denominazione="Fornitore temporaneo")
        documento = DocumentoFornitore.objects.create(
            fornitore=fornitore,
            numero_documento="OLD-1",
            data_documento=date(2026, 4, 22),
            imponibile=Decimal("100.00"),
            iva=Decimal("22.00"),
            totale=Decimal("122.00"),
            external_source="fatture_in_cloud",
            external_id="990",
        )
        ScadenzaPagamentoFornitore.objects.create(
            documento=documento,
            data_scadenza=date(2026, 4, 22),
            importo_previsto=Decimal("122.00"),
        )
        payload = {
            "id": 990,
            "type": "expense",
            "description": "Fattura aggiornata",
            "invoice_number": "NEW-1",
            "date": "2026-04-22",
            "amount_net": "100.00",
            "amount_vat": "22.00",
            "amount_gross": "122.00",
            "entity": {"name": "Supplier Correct Srl", "vat_number": "IT12345678904"},
            "payments_list": [{"due_date": "2026-06-30", "amount": "122.00"}],
        }

        importa_documento_fatture_in_cloud(connessione, payload, pending=False, utente=self.user)

        documento.refresh_from_db()
        self.assertEqual(documento.fornitore.denominazione, "Supplier Correct Srl")
        scadenza = documento.scadenze.get()
        self.assertEqual(scadenza.data_scadenza, date(2026, 6, 30))

    @patch("gestione_finanziaria.fatture_in_cloud.FattureInCloudClient")
    def test_sincronizza_fatture_in_cloud_recupera_dettaglio_prima_di_importare(self, mock_client_class):
        connessione = FattureInCloudConnessione.objects.create(
            nome="FIC",
            company_id=123,
            sincronizza_documenti_da_registrare=False,
        )
        client = Mock()
        client.list_received_documents.side_effect = [
            {"data": [{"id": 991}], "pagination": {"current_page": 1, "last_page": 1}},
            {"data": [], "pagination": {"current_page": 1, "last_page": 1}},
        ]
        client.get_received_document.return_value = {
            "id": 991,
            "type": "expense",
            "description": "Dettaglio completo",
            "invoice_number": "DET-1",
            "date": "2026-04-23",
            "amount_net": "100.00",
            "amount_vat": "22.00",
            "amount_gross": "122.00",
            "entity": {"name": "Detailed Supplier Srl", "vat_number": "IT12345678905"},
            "payments_list": [{"due_date": "2026-07-01", "amount": "122.00"}],
        }
        mock_client_class.return_value = client

        stats = sincronizza_fatture_in_cloud(connessione, utente=self.user)

        self.assertEqual(stats["creati"], 1)
        self.assertEqual(stats["fornitori_creati"], 1)
        self.assertEqual(stats["fornitori_aggiornati"], 0)
        self.assertIn("Fornitori: 1 creati, 0 aggiornati.", stats["messaggi"][0])
        client.get_received_document.assert_called_once_with(991)
        documento = DocumentoFornitore.objects.get(external_id="991")
        self.assertEqual(documento.fornitore.denominazione, "Detailed Supplier Srl")
        self.assertEqual(documento.scadenze.get().data_scadenza, date(2026, 7, 1))

    @override_settings(
        FATTURE_IN_CLOUD_OAUTH_CLIENT_ID="render-client",
        FATTURE_IN_CLOUD_OAUTH_CLIENT_SECRET="render-secret",
        FATTURE_IN_CLOUD_OAUTH_REDIRECT_URI="https://arboris-test.onrender.com/gestione-finanziaria/fatture-in-cloud/callback/",
    )
    def test_fatture_in_cloud_oauth_usa_credenziali_render(self):
        connessione = FattureInCloudConnessione.objects.create(nome="FIC Render")

        self.assertTrue(has_oauth_credentials(connessione))
        auth_url = authorization_url(
            connessione,
            "https://arboris-test.onrender.com/gestione-finanziaria/fatture-in-cloud/callback/",
            "state-test",
        )

        self.assertIn("client_id=render-client", auth_url)
        self.assertIn("state=state-test", auth_url)

    @override_settings(
        FATTURE_IN_CLOUD_OAUTH_CLIENT_ID="render-client",
        FATTURE_IN_CLOUD_OAUTH_CLIENT_SECRET="render-secret",
        FATTURE_IN_CLOUD_OAUTH_REDIRECT_URI="https://arboris-test.onrender.com/gestione-finanziaria/fatture-in-cloud/callback/",
    )
    def test_avvia_oauth_fatture_in_cloud_con_credenziali_render(self):
        connessione = FattureInCloudConnessione.objects.create(nome="FIC Render")

        response = self.client.get(reverse("avvia_oauth_fatture_in_cloud", kwargs={"pk": connessione.pk}))

        self.assertEqual(response.status_code, 302)
        self.assertIn("https://api-v2.fattureincloud.it/oauth/authorize", response["Location"])
        self.assertIn("client_id=render-client", response["Location"])
        self.assertIn("state=", response["Location"])
        self.assertIn("redirect_uri=https%3A%2F%2Farboris-test.onrender.com", response["Location"])

    @override_settings(
        FATTURE_IN_CLOUD_OAUTH_CLIENT_ID="render-client",
        FATTURE_IN_CLOUD_OAUTH_CLIENT_SECRET="render-secret",
        FATTURE_IN_CLOUD_OAUTH_REDIRECT_URI="https://arboris-test.onrender.com/gestione-finanziaria/fatture-in-cloud/callback/",
    )
    @patch("gestione_finanziaria.fatture_in_cloud.requests.request")
    @patch("gestione_finanziaria.fatture_in_cloud.requests.post")
    def test_callback_fatture_in_cloud_legge_company_id_da_data_companies(self, mock_post, mock_request):
        connessione = FattureInCloudConnessione.objects.create(nome="FIC Render", oauth_state="state-test")
        token_response = Mock(
            status_code=200,
            content=b"{}",
            text='{"access_token": "token"}',
        )
        token_response.json.return_value = {
            "access_token": "access-token",
            "refresh_token": "refresh-token",
            "expires_in": 86400,
        }
        companies_response = Mock(
            status_code=200,
            content=b"{}",
            text='{"data": {"companies": [{"id": 456}]}}',
        )
        companies_response.json.return_value = {"data": {"companies": [{"id": 456}]}}
        mock_post.return_value = token_response
        mock_request.return_value = companies_response

        response = self.client.get(
            reverse("callback_fatture_in_cloud"),
            {"code": "auth-code", "state": "state-test"},
        )

        self.assertEqual(response.status_code, 302)
        expected_url = f"{reverse('modifica_fatture_in_cloud', kwargs={'pk': connessione.pk})}?oauth=ok"
        self.assertEqual(response["Location"], expected_url)
        connessione.refresh_from_db()
        self.assertEqual(connessione.company_id, 456)
        self.assertEqual(connessione.oauth_state, "")
        self.assertTrue(connessione.access_token_cifrato)
        self.assertTrue(connessione.refresh_token_cifrato)
        page_response = self.client.get(expected_url)
        self.assertContains(page_response, "Collegamento OAuth completato")
        self.assertContains(page_response, "Company ID collegato: 456")

    def test_riconciliazione_fornitore_collega_movimento_in_uscita(self):
        categoria = crea_categoria_spesa_test("Utenze")
        fornitore = Fornitore.objects.create(
            denominazione="Energia Srl",
            tipo_soggetto="azienda",
            partita_iva="12345678901",
            categoria_spesa=categoria,
        )
        documento = DocumentoFornitore.objects.create(
            fornitore=fornitore,
            tipo_documento=TipoDocumentoFornitore.FATTURA,
            numero_documento="E-001",
            data_documento=date(2026, 4, 1),
            imponibile=Decimal("100.00"),
            iva=Decimal("22.00"),
            totale=Decimal("122.00"),
        )
        scadenza = ScadenzaPagamentoFornitore.objects.create(
            documento=documento,
            data_scadenza=date(2026, 4, 30),
            importo_previsto=Decimal("122.00"),
        )
        movimento = MovimentoFinanziario.objects.create(
            data_contabile=date(2026, 4, 29),
            importo=Decimal("-122.00"),
            descrizione="Bonifico Energia Srl fattura E-001",
            controparte="Energia Srl",
            stato_riconciliazione=StatoRiconciliazione.NON_RICONCILIATO,
        )

        candidati = trova_scadenze_fornitori_candidate(movimento)
        self.assertEqual(candidati[0].scadenza, scadenza)

        pagamento = riconcilia_movimento_con_scadenza_fornitore(
            movimento,
            scadenza,
            utente=self.user,
        )

        self.assertEqual(pagamento.importo, Decimal("122.00"))
        scadenza.refresh_from_db()
        documento.refresh_from_db()
        movimento.refresh_from_db()
        self.assertEqual(scadenza.importo_pagato, Decimal("122.00"))
        self.assertEqual(scadenza.stato, StatoScadenzaFornitore.PAGATA)
        self.assertEqual(documento.stato, StatoDocumentoFornitore.PAGATO)
        self.assertEqual(movimento.stato_riconciliazione, StatoRiconciliazione.RICONCILIATO)
        self.assertEqual(movimento.categoria, categoria)
        self.assertTrue(movimento.categorizzazione_automatica)
        self.assertEqual(importo_movimento_disponibile_fornitori(movimento), Decimal("0.00"))
        self.assertEqual(PagamentoFornitore.objects.count(), 1)

    def test_fornitori_pages_render(self):
        categoria = crea_categoria_spesa_test("Materiali")
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

    def test_eliminazione_multipla_documenti_fornitori_con_conferma(self):
        fornitore = Fornitore.objects.create(
            denominazione="Fornitore bulk",
            tipo_soggetto="azienda",
        )
        documenti = [
            DocumentoFornitore.objects.create(
                fornitore=fornitore,
                numero_documento=f"BULK-{index}",
                data_documento=date(2026, 4, index),
                imponibile=Decimal("100.00"),
                iva=Decimal("22.00"),
                totale=Decimal("122.00"),
            )
            for index in (1, 2, 3)
        ]
        ScadenzaPagamentoFornitore.objects.create(
            documento=documenti[0],
            data_scadenza=date(2026, 5, 1),
            importo_previsto=Decimal("122.00"),
        )
        next_url = reverse("lista_documenti_fornitori") + "?stato=da_pagare"

        response = self.client.get(reverse("lista_documenti_fornitori"))
        self.assertContains(response, reverse("elimina_documenti_fornitori_multipla"))
        self.assertContains(response, "data-bulk-form")

        response = self.client.post(
            reverse("elimina_documenti_fornitori_multipla"),
            {
                "selected_ids": [str(documenti[0].pk), str(documenti[1].pk)],
                "next": next_url,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Elimina documenti fornitori")
        self.assertContains(response, "BULK-1")
        self.assertContains(response, "BULK-2")

        response = self.client.post(
            reverse("elimina_documenti_fornitori_multipla"),
            {
                "selected_ids": [str(documenti[0].pk), str(documenti[1].pk)],
                "next": next_url,
                "conferma": "1",
            },
        )

        self.assertRedirects(response, next_url)
        self.assertFalse(DocumentoFornitore.objects.filter(pk__in=[documenti[0].pk, documenti[1].pk]).exists())
        self.assertTrue(DocumentoFornitore.objects.filter(pk=documenti[2].pk).exists())
        self.assertFalse(ScadenzaPagamentoFornitore.objects.filter(documento=documenti[0]).exists())

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

    def test_riconcilia_movimento_con_rate_supporta_pagamento_cumulativo(self):
        stato_relazione = StatoRelazioneFamiglia.objects.create(stato="Iscritta")
        famiglia = Famiglia.objects.create(
            cognome_famiglia="Rossi",
            stato_relazione_famiglia=stato_relazione,
        )
        anno = AnnoScolastico.objects.create(
            nome_anno_scolastico="2025/2026",
            data_inizio=date(2025, 9, 1),
            data_fine=date(2026, 6, 30),
        )
        classe = Classe.objects.create(nome_classe="Materna", ordine_classe=1)
        stato_iscrizione = StatoIscrizione.objects.create(stato_iscrizione="Iscritto")
        condizione = CondizioneIscrizione.objects.create(
            anno_scolastico=anno,
            nome_condizione_iscrizione="Retta standard",
            numero_mensilita_default=10,
        )
        TariffaCondizioneIscrizione.objects.create(
            condizione_iscrizione=condizione,
            ordine_figlio_da=1,
            retta_annuale=Decimal("1000.00"),
        )
        rate = []
        for nome in ["Luca", "Marta"]:
            studente = Studente.objects.create(
                famiglia=famiglia,
                nome=nome,
                cognome="Rossi",
                data_nascita=date(2020, 5, 5),
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
            rate.append(
                RataIscrizione.objects.create(
                    iscrizione=iscrizione,
                    famiglia=famiglia,
                    numero_rata=1,
                    mese_riferimento=9,
                    anno_riferimento=2025,
                    importo_dovuto=Decimal("100.00"),
                    importo_finale=Decimal("100.00"),
                    data_scadenza=date(2025, 9, 10),
                )
            )

        movimento = MovimentoFinanziario.objects.create(
            data_contabile=date(2025, 9, 11),
            importo=Decimal("200.00"),
            descrizione="Bonifico rette Luca e Marta Rossi",
        )

        riconcilia_movimento_con_rate(
            movimento,
            [(rate[0], Decimal("100.00")), (rate[1], Decimal("100.00"))],
            utente=self.user,
        )

        movimento.refresh_from_db()
        for rata in rate:
            rata.refresh_from_db()
            self.assertTrue(rata.pagata)
            self.assertEqual(rata.importo_pagato, Decimal("100.00"))
            self.assertEqual(rata.data_pagamento, date(2025, 9, 11))
        self.assertEqual(movimento.stato_riconciliazione, StatoRiconciliazione.RICONCILIATO)
        self.assertIsNone(movimento.rata_iscrizione_id)
        self.assertEqual(RiconciliazioneRataMovimento.objects.filter(movimento=movimento).count(), 2)

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

        response = self.client.get(reverse("dashboard_gestione_finanziaria"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "finance-movement-row-incoming")
        self.assertContains(response, "finance-movement-row-outgoing")

    def test_eliminazione_multipla_movimenti_conferma_e_ricalcola_saldo(self):
        conto = ContoBancario.objects.create(
            nome_conto="Conto bulk",
            tipo_conto=TipoContoFinanziario.CONTO_CORRENTE,
            attivo=True,
        )
        SaldoConto.objects.create(
            conto=conto,
            data_riferimento=timezone.make_aware(datetime(2026, 4, 1, 23, 59)),
            saldo_contabile=Decimal("1000.00"),
            fonte=FonteSaldo.MANUALE,
        )
        movimento_da_eliminare = MovimentoFinanziario.objects.create(
            conto=conto,
            canale=CanaleMovimento.BANCA,
            data_contabile=date(2026, 4, 2),
            importo=Decimal("-100.00"),
            descrizione="Movimento da eliminare",
            incide_su_saldo_banca=True,
        )
        movimento_da_mantenere = MovimentoFinanziario.objects.create(
            conto=conto,
            canale=CanaleMovimento.BANCA,
            data_contabile=date(2026, 4, 3),
            importo=Decimal("-25.00"),
            descrizione="Movimento da mantenere",
            incide_su_saldo_banca=True,
        )
        next_url = reverse("lista_movimenti_finanziari") + f"?conto={conto.pk}"

        response = self.client.get(reverse("lista_movimenti_finanziari"))
        self.assertContains(response, reverse("elimina_movimenti_finanziari_multipla"))
        self.assertContains(response, "data-bulk-form")

        response = self.client.post(
            reverse("elimina_movimenti_finanziari_multipla"),
            {
                "selected_ids": [str(movimento_da_eliminare.pk)],
                "next": next_url,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Elimina movimenti")
        self.assertContains(response, "Movimento da eliminare")

        response = self.client.post(
            reverse("elimina_movimenti_finanziari_multipla"),
            {
                "selected_ids": [str(movimento_da_eliminare.pk)],
                "next": next_url,
                "conferma": "1",
            },
        )

        self.assertRedirects(response, next_url)
        self.assertFalse(MovimentoFinanziario.objects.filter(pk=movimento_da_eliminare.pk).exists())
        self.assertTrue(MovimentoFinanziario.objects.filter(pk=movimento_da_mantenere.pk).exists())
        conto.refresh_from_db()
        self.assertEqual(conto.saldo_corrente, Decimal("975.00"))

    def test_saldo_conto_manuale_alimenta_saldo_corrente_con_movimenti_successivi(self):
        conto = ContoBancario.objects.create(
            nome_conto="Cassa contanti",
            tipo_conto=TipoContoFinanziario.CASSA_CONTANTI,
            attivo=True,
        )

        response = self.client.post(
            reverse("crea_saldo_conto"),
            {
                "conto": str(conto.pk),
                "data_riferimento": "2026-04-01T23:59",
                "saldo_contabile": "1000.00",
                "saldo_disponibile": "",
                "valuta": "EUR",
                "fonte": FonteSaldo.MANUALE,
                "note": "Saldo iniziale cassa",
            },
        )

        self.assertRedirects(response, reverse("lista_saldi_conti"))
        self.assertEqual(SaldoConto.objects.filter(conto=conto).count(), 1)
        conto.refresh_from_db()
        self.assertEqual(conto.saldo_corrente, Decimal("1000.00"))

        response = self.client.post(
            reverse("crea_movimento_manuale"),
            {
                "conto": str(conto.pk),
                "canale": CanaleMovimento.CONTANTI,
                "data_contabile": "2026-04-02",
                "data_valuta": "",
                "importo": "-100.00",
                "valuta": "EUR",
                "descrizione": "Acquisto contanti",
                "controparte": "",
                "iban_controparte": "",
                "categoria": "",
                "incide_su_saldo_banca": "on",
                "sostenuta_da_terzi": "",
                "rimborsabile": "",
                "sostenitore": "",
                "note": "",
            },
        )

        self.assertRedirects(response, reverse("lista_movimenti_finanziari"))
        conto.refresh_from_db()
        self.assertEqual(conto.saldo_corrente, Decimal("900.00"))

    def test_saldo_manuale_e_accessibile_dalle_impostazioni_con_conto_preselezionato(self):
        conto = ContoBancario.objects.create(
            nome_conto="Conto operativo",
            tipo_conto=TipoContoFinanziario.CONTO_CORRENTE,
            attivo=True,
        )

        response = self.client.get(reverse("lista_conti_bancari"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Inserisci saldo manuale")
        self.assertContains(response, f"{reverse('crea_saldo_conto')}?conto={conto.pk}")

        response = self.client.get(f"{reverse('crea_saldo_conto')}?conto={conto.pk}")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Inserisci qui il saldo rilevato")
        self.assertContains(response, f'<option value="{conto.pk}" selected>{conto.nome_conto}</option>', html=True)

    def test_movimento_personale_usa_badge_e_non_incide_sul_saldo(self):
        conto = ContoBancario.objects.create(
            nome_conto="Conto operativo",
            tipo_conto=TipoContoFinanziario.CONTO_CORRENTE,
            saldo_corrente=Decimal("500.00"),
            saldo_corrente_aggiornato_al=timezone.now(),
            attivo=True,
        )

        response = self.client.post(
            reverse("crea_movimento_manuale"),
            {
                "conto": str(conto.pk),
                "canale": CanaleMovimento.PERSONALE,
                "data_contabile": "2026-04-03",
                "data_valuta": "",
                "importo": "-35.00",
                "valuta": "EUR",
                "descrizione": "Materiale pagato da genitore",
                "controparte": "Genitore",
                "iban_controparte": "",
                "categoria": "",
                "incide_su_saldo_banca": "",
                "sostenuta_da_terzi": "",
                "rimborsabile": "",
                "sostenitore": "Genitore",
                "note": "",
            },
        )

        self.assertRedirects(response, reverse("lista_movimenti_finanziari"))
        movimento = MovimentoFinanziario.objects.get(descrizione="Materiale pagato da genitore")
        self.assertTrue(movimento.sostenuta_da_terzi)
        self.assertFalse(movimento.incide_su_saldo_banca)

        response = self.client.get(reverse("lista_movimenti_finanziari"))
        self.assertContains(response, "finance-channel-badge-personale")
        self.assertContains(response, "senza rimborso")

        response = self.client.get(reverse("crea_movimento_manuale"))
        self.assertContains(response, "movimento-finanziario-form.js")

    def test_dashboard_mostra_saldi_per_tipo_conto(self):
        conto = ContoBancario.objects.create(
            nome_conto="Cassa",
            tipo_conto=TipoContoFinanziario.CASSA_CONTANTI,
            attivo=True,
        )
        SaldoConto.objects.create(
            conto=conto,
            data_riferimento=timezone.now(),
            saldo_contabile=Decimal("250.00"),
            fonte=FonteSaldo.MANUALE,
        )

        response = self.client.get(reverse("dashboard_gestione_finanziaria"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Saldi per tipo")
        self.assertContains(response, "Cassa contanti")
        self.assertContains(response, "250,00")

    def test_template_import_saldi_conti_csv(self):
        response = self.client.get(reverse("scarica_template_saldi_conti_csv"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/csv; charset=utf-8")
        self.assertContains(response, "nome_conto;data_riferimento;saldo_contabile")

    def test_import_saldi_banco_bpm_cbi_usa_iban_e_colonne_banca(self):
        conto = ContoBancario.objects.create(
            nome_conto="Conto Banco BPM",
            iban="IT67C0503437060000000003228",
            attivo=True,
        )
        raw_csv = (
            '"Ragione sociale";"Banca";"Rapporto";"IBAN";"Data";"Saldo divisa";"Saldo liquido";"Div."\n'
            '"IL SOLE E L\'ALTRE STELLE SRL IMPRESA SOCIALE";"05034 - BANCO BPM S.P.A.";'
            '"37060 - 000000003228";"IT67C0503437060000000003228";"28/04/2026";'
            '"980,89";"980,89";"EUR"\n'
        )
        uploaded = SimpleUploadedFile(
            "RiepilogoSaldiCBI_30_04_2026_01.24.53.csv",
            raw_csv.encode("utf-8"),
            content_type="text/csv",
        )

        response = self.client.post(reverse("import_saldi_conti"), {"file": uploaded})

        self.assertRedirects(response, reverse("lista_saldi_conti"))
        saldo = SaldoConto.objects.get(conto=conto)
        self.assertEqual(saldo.data_riferimento.date(), date(2026, 4, 28))
        self.assertEqual(saldo.saldo_contabile, Decimal("980.89"))
        self.assertEqual(saldo.saldo_disponibile, Decimal("980.89"))
        conto.refresh_from_db()
        self.assertEqual(conto.saldo_corrente, Decimal("980.89"))

    def test_import_saldi_banco_bpm_online_deduce_data_da_nome_file_e_crea_conto(self):
        raw_csv = (
            '"Ragione sociale";"Banca";"Rapporto";"IBAN";"Saldo finale";"Saldo disponibile";"Div."\n'
            '"IL SOLE E L\'ALTRE STELLE SRL IMPRESA SOCIALE";"05034 - BANCO BPM S.P.A.";'
            '"37060 - 056300003228";"IT67C0503437060000000003228";"980,89";"980,89";"EUR"\n'
        )
        uploaded = SimpleUploadedFile(
            "SaldiCC_OnLine_30_04_2026_01.24.38.csv",
            raw_csv.encode("utf-8"),
            content_type="text/csv",
        )

        response = self.client.post(reverse("import_saldi_conti"), {"file": uploaded})

        self.assertRedirects(response, reverse("lista_saldi_conti"))
        conto = ContoBancario.objects.get(iban="IT67C0503437060000000003228")
        saldo = SaldoConto.objects.get(conto=conto)
        self.assertEqual(timezone.localtime(saldo.data_riferimento).date(), date(2026, 4, 30))
        self.assertEqual(saldo.saldo_contabile, Decimal("980.89"))
        self.assertEqual(conto.banca, "05034 - BANCO BPM S.P.A.")

    def test_pulizia_movimenti_automatici_elimina_import_non_manuali(self):
        provider = ProviderBancario.objects.create(
            nome="Import test",
            tipo=TipoProviderBancario.IMPORT_FILE,
        )
        conto = ContoBancario.objects.create(
            nome_conto="Conto operativo",
            iban="IT00X0000000000000000000000",
            provider=provider,
            attivo=True,
            saldo_corrente=Decimal("75.00"),
        )
        MovimentoFinanziario.objects.create(
            conto=conto,
            origine=OrigineMovimento.IMPORT_FILE,
            data_contabile=date(2026, 4, 1),
            importo=Decimal("100.00"),
            descrizione="Import file",
            incide_su_saldo_banca=True,
        )
        MovimentoFinanziario.objects.create(
            conto=conto,
            origine=OrigineMovimento.BANCA,
            data_contabile=date(2026, 4, 2),
            importo=Decimal("-25.00"),
            descrizione="Sync banca",
            incide_su_saldo_banca=True,
        )
        manuale = MovimentoFinanziario.objects.create(
            conto=conto,
            origine=OrigineMovimento.MANUALE,
            data_contabile=date(2026, 4, 3),
            importo=Decimal("50.00"),
            descrizione="Manuale",
            incide_su_saldo_banca=False,
        )

        response = self.client.get(reverse("lista_movimenti_finanziari"))
        self.assertContains(response, reverse("pulizia_movimenti_finanziari"))

        response = self.client.get(reverse("pulizia_movimenti_finanziari"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Ripulisci movimenti")
        self.assertEqual(response.context["statistiche"]["totale"], 3)
        self.assertEqual(response.context["statistiche"]["automatici"], 2)
        self.assertEqual(response.context["statistiche"]["manuali"], 1)

        response = self.client.post(
            reverse("pulizia_movimenti_finanziari"),
            {
                "ambito": "automatici",
                "conferma": "ELIMINA",
            },
        )

        self.assertRedirects(response, reverse("lista_movimenti_finanziari"))
        self.assertEqual(MovimentoFinanziario.objects.count(), 1)
        self.assertTrue(MovimentoFinanziario.objects.filter(pk=manuale.pk).exists())
        conto.refresh_from_db()
        self.assertEqual(conto.saldo_corrente, Decimal("0"))

    def test_pulizia_movimenti_richiede_conferma_testuale(self):
        MovimentoFinanziario.objects.create(
            origine=OrigineMovimento.MANUALE,
            data_contabile=date(2026, 4, 1),
            importo=Decimal("10.00"),
            descrizione="Manuale",
        )

        response = self.client.post(
            reverse("pulizia_movimenti_finanziari"),
            {
                "ambito": "manuali",
                "conferma": "elimina tutto",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(MovimentoFinanziario.objects.count(), 1)
        self.assertContains(response, "Per confermare devi digitare")

    def test_report_categorie_filtra_per_anno_scolastico(self):
        anno = AnnoScolastico.objects.create(
            nome_anno_scolastico="2025/2026",
            data_inizio=date(2025, 9, 1),
            data_fine=date(2026, 8, 31),
        )
        CondizioneIscrizione.objects.create(
            anno_scolastico=anno,
            nome_condizione_iscrizione="Retta standard",
            numero_mensilita_default=10,
            mese_prima_retta=9,
            giorno_scadenza_rate=10,
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
        self.assertContains(response, "Sintesi")
        self.assertContains(response, "EUR 150,00")
        self.assertContains(response, "report-category-entrata")

    def test_report_categorie_annuale_mostra_categorie_figlie(self):
        categoria_padre = CategoriaFinanziaria.objects.create(
            nome="Utenze",
            tipo=TipoCategoriaFinanziaria.SPESA,
        )
        categoria_figlia = CategoriaFinanziaria.objects.create(
            nome="Energia elettrica",
            tipo=TipoCategoriaFinanziaria.SPESA,
            parent=categoria_padre,
        )
        MovimentoFinanziario.objects.create(
            data_contabile=date(2026, 1, 10),
            importo=Decimal("-1000.00"),
            descrizione="Bolletta luce",
            categoria=categoria_figlia,
        )

        response = self.client.get(
            reverse("report_categorie_annuale"),
            {"periodo": "solare", "anno": "2026"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Utenze")
        self.assertContains(response, "Energia elettrica")
        self.assertContains(response, "2026")
        self.assertNotContains(response, "2.026")
        self.assertContains(response, 'data-report-category-toggle="categoria-')
        self.assertContains(response, "report-category-spesa")
        self.assertContains(response, "-1.000,00")
        self.assertEqual(response.context["totale_uscite"], Decimal("-1000.00"))
