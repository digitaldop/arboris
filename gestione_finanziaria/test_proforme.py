from datetime import date
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db.models.deletion import ProtectedError
from django.test import TestCase, TransactionTestCase, skipUnlessDBFeature
from django.urls import reverse

from .fatture_in_cloud import importa_documento_fatture_in_cloud
from .fatture_in_cloud_xml import document_data_from_e_invoice_xml
from .models import (
    CollegamentoProforma, DocumentoFornitore, FattureInCloudConnessione, Fornitore,
    MovimentoFinanziario, PagamentoFornitore, ScadenzaPagamentoFornitore, StatoDocumentoFornitore, TipoDocumentoFornitore,
    VerificaProforma,
)
from .proforme import (
    annulla_collegamento_proforma, candidati_proforma, collega_proforma, conferma_fattura_distinta,
    conferma_variazione_importi,
)
from .services import registra_pagamento_fornitore, annulla_pagamento_fornitore, importo_movimento_disponibile_fornitori


class ProformeFornitoriTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser(username="proforme-test")
        self.client.force_login(self.user)
        self.fornitore = Fornitore.objects.create(denominazione="Fornitore Proforme", partita_iva="01234567890")
        self.connessione = FattureInCloudConnessione.objects.create(company_id=123)
        allegato = patch("gestione_finanziaria.fatture_in_cloud._salva_allegato_fatture_in_cloud", return_value={})
        auto = patch("gestione_finanziaria.fatture_in_cloud._auto_reconcile_imported_supplier_deadlines", return_value=0)
        allegato.start()
        auto.start()
        self.addCleanup(allegato.stop)
        self.addCleanup(auto.stop)

    def documento(self, numero="PF-1", totale="1000.00", tipo="proforma", **kwargs):
        return DocumentoFornitore.objects.create(
            fornitore=self.fornitore, tipo_documento=tipo, numero_documento=numero,
            data_documento=date(2026, 1, 3), totale=Decimal(totale), **kwargs,
        )

    def scadenza(self, documento, importo="1000.00", pagato="0.00"):
        scadenza = ScadenzaPagamentoFornitore.objects.create(
            documento=documento, data_scadenza=date(2026, 2, 1), importo_previsto=Decimal(importo),
        )
        if Decimal(pagato):
            registra_pagamento_fornitore(scadenza, importo=Decimal(pagato), utente=self.user)
            scadenza.refresh_from_db()
        return scadenza

    def importa(self, riferimento=None, totale="1000.00", pk=120, extra=None):
        payload = {
            "id": pk, "date": "2026-03-10", "invoice_number": f"F-{pk}", "type": "expense",
            "entity": {"name": self.fornitore.denominazione, "vat_number": self.fornitore.partita_iva},
            "amount_gross": totale, "payments_list": [{"amount": totale, "due_date": "2026-04-01", "status": "not_paid"}],
        }
        if riferimento:
            payload["e_invoice"] = {"FatturaElettronicaBody": {"DatiGenerali": {"DatiFattureCollegate": {"IdDocumento": riferimento}}}}
        payload.update(extra or {})
        return importa_documento_fatture_in_cloud(self.connessione, payload, source_doc_type="expense", utente=self.user)["documento"]

    def test_collegamento_preserva_scadenze_pagamenti_e_residuo(self):
        proforma = self.documento(allegato="documenti_fornitori/proforma.pdf")
        scadenza = self.scadenza(proforma, pagato="400.00")
        pagamento = scadenza.pagamenti.get()
        fattura = self.documento("F-1", tipo="fattura")
        self.scadenza(fattura)
        collega_proforma(fattura, proforma, utente=self.user)
        scadenza.refresh_from_db()
        pagamento.refresh_from_db()
        fattura.refresh_from_db()
        proforma.refresh_from_db()
        self.assertEqual(scadenza.documento_id, fattura.pk)
        self.assertEqual(pagamento.scadenza_id, scadenza.pk)
        self.assertEqual(fattura.residuo_da_pagare, Decimal("600.00"))
        self.assertEqual(proforma.residuo_da_pagare, Decimal("0.00"))
        self.assertEqual(proforma.allegato.name, "documenti_fornitori/proforma.pdf")
        self.assertEqual(ScadenzaPagamentoFornitore.objects.count(), 1)
        self.assertEqual(PagamentoFornitore.objects.count(), 1)
        self.assertEqual(proforma.verifica_proforma, VerificaProforma.SOSTITUITA)

    def test_import_automatico_include_proforma_saldato_e_reimport_idempotente(self):
        proforma = self.documento()
        scadenza = self.scadenza(proforma, pagato="1000")
        fattura = self.importa("PF-1")
        self.assertEqual(fattura.proforma_origine_id, proforma.pk)
        self.assertEqual(fattura.stato, StatoDocumentoFornitore.PAGATO)
        self.assertEqual(fattura.anno_competenza, 2026)
        self.assertEqual(fattura.mese_competenza, 1)
        nuovo_import = self.importa("PF-1")
        self.assertEqual(nuovo_import.pk, fattura.pk)
        self.assertEqual(nuovo_import.scadenze.get().pk, scadenza.pk)
        self.assertEqual(CollegamentoProforma.objects.count(), 1)
        self.assertEqual(DocumentoFornitore.objects.count(), 2)
        self.assertEqual(PagamentoFornitore.objects.count(), 1)
        self.assertEqual(nuovo_import.stato, StatoDocumentoFornitore.PAGATO)

    def test_stesso_importo_senza_riferimento_richiede_verifica(self):
        proforma = self.documento()
        self.scadenza(proforma, pagato="400")
        fattura = self.importa()
        self.assertEqual(fattura.verifica_proforma, VerificaProforma.DA_VERIFICARE)
        self.assertFalse(fattura.scadenze.exists())
        self.assertEqual(fattura.residuo_da_pagare, Decimal("0.00"))
        self.importa()
        self.assertEqual(ScadenzaPagamentoFornitore.objects.count(), 1)
        response = self.client.get(reverse("fatture_scadenze_fornitori"))
        self.assertEqual(response.context["totale_residuo"], Decimal("600.00"))
        self.assertContains(response, "Da verificare")

    def test_fattura_distinta_crea_scadenze_e_non_ripropone_match(self):
        self.scadenza(self.documento())
        fattura = self.importa()
        conferma_fattura_distinta(fattura, utente=self.user)
        fattura = self.importa()
        self.assertEqual(fattura.verifica_proforma, VerificaProforma.DISTINTA)
        self.assertEqual(fattura.scadenze.count(), 1)
        self.assertEqual(ScadenzaPagamentoFornitore.objects.count(), 2)

    def test_importo_diverso_con_riferimento_va_in_verifica(self):
        self.scadenza(self.documento())
        fattura = self.importa("PF-1", totale="1100")
        self.assertEqual(fattura.verifica_proforma, VerificaProforma.DA_VERIFICARE)
        self.assertFalse(fattura.scadenze.exists())

    def test_due_candidate_non_vengono_collegate_automaticamente(self):
        self.scadenza(self.documento())
        self.scadenza(self.documento("PF-2"))
        fattura = self.importa("PF-1")
        self.assertEqual(fattura.verifica_proforma, VerificaProforma.DA_VERIFICARE)

    def test_riferimento_ordine_univoco(self):
        self.scadenza(self.documento(riferimento_ordine="ORD/2026-1"))
        fattura = self.importa(extra={"e_invoice": {"DatiOrdineAcquisto": {"IdDocumento": "ORD/2026-1"}}})
        self.assertIsNotNone(fattura.proforma_origine_id)

    def test_riferimento_data_errata_non_autocollega(self):
        self.scadenza(self.documento())
        fattura = self.importa(extra={"e_invoice": {"DatiFattureCollegate": {"IdDocumento": "PF-1", "Data": "2025-01-03"}}})
        self.assertEqual(fattura.verifica_proforma, VerificaProforma.DA_VERIFICARE)

    def test_import_normale_se_nessuna_candidata(self):
        self.scadenza(self.documento(totale="250"), importo="250")
        fattura = self.importa()
        self.assertEqual(fattura.verifica_proforma, "")
        self.assertEqual(fattura.scadenze.count(), 1)

    def test_conferma_differenza_e_correzione_preservano_due_pagamenti(self):
        proforma = self.documento()
        scadenza = self.scadenza(proforma, pagato="300")
        registra_pagamento_fornitore(scadenza, importo=Decimal("100"), utente=self.user)
        fattura = self.documento("F-1", totale="1100", tipo="fattura")
        with self.assertRaises(ValidationError):
            collega_proforma(fattura, proforma)
        collega_proforma(fattura, proforma, conferma_differenza=True)
        fattura.refresh_from_db()
        self.assertEqual(fattura.residuo_da_pagare, Decimal("700"))
        annulla_collegamento_proforma(fattura, utente=self.user)
        scadenza.refresh_from_db()
        fattura.refresh_from_db()
        self.assertEqual(scadenza.documento_id, proforma.pk)
        self.assertEqual(scadenza.importo_previsto, Decimal("1000"))
        self.assertEqual(scadenza.pagamenti.count(), 2)
        self.assertFalse(fattura.scadenze.exists())
        self.assertIsNotNone(CollegamentoProforma.objects.get().annullato_at)
        self.assertEqual(fattura.verifica_proforma, VerificaProforma.DA_VERIFICARE)

    def test_divieto_pagato_superiore_e_rollback(self):
        proforma = self.documento()
        self.scadenza(proforma, pagato="1000")
        fattura = self.documento("F-1", totale="900", tipo="fattura")
        scadenza = self.scadenza(fattura, importo="900")
        with self.assertRaises(ValidationError):
            collega_proforma(fattura, proforma, conferma_differenza=True)
        self.assertTrue(fattura.scadenze.filter(pk=scadenza.pk).exists())
        self.assertEqual(CollegamentoProforma.objects.count(), 0)

    def test_divieto_fornitore_diverso_o_fattura_gia_pagata(self):
        proforma = self.documento()
        self.scadenza(proforma)
        fattura = self.documento("F-1", tipo="fattura")
        self.scadenza(fattura, pagato="400")
        with self.assertRaises(ValidationError):
            collega_proforma(fattura, proforma)
        altro = Fornitore.objects.create(denominazione="Altro")
        fattura.fornitore = altro
        fattura.save()
        with self.assertRaises(ValidationError):
            collega_proforma(fattura, proforma)

    def test_variazione_reimport_non_modifica_residuo_senza_conferma(self):
        self.scadenza(self.documento(), pagato="400")
        fattura = self.importa("PF-1")
        fattura = self.importa("PF-1", totale="1200")
        self.assertEqual(fattura.totale, Decimal("1000"))
        self.assertEqual(fattura.residuo_da_pagare, Decimal("600"))
        self.assertIn("_arboris_proforma_variazione", fattura.external_payload)
        fattura = conferma_variazione_importi(fattura)
        self.assertEqual(fattura.residuo_da_pagare, Decimal("800"))
        self.assertEqual(PagamentoFornitore.objects.count(), 1)

    def test_storico_impedisce_eliminazione(self):
        self.scadenza(self.documento())
        fattura = self.importa("PF-1")
        with self.assertRaises(ProtectedError):
            fattura.delete()
        response = self.client.post(reverse("elimina_documento_fornitore", args=[fattura.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(DocumentoFornitore.objects.filter(pk=fattura.pk).exists())

    def test_filtro_attesa_include_proforma_pagata(self):
        proforma = self.documento()
        scadenza = self.scadenza(proforma, pagato="1000")
        response = self.client.get(reverse("fatture_scadenze_fornitori"), {"vista": "proforme"})
        self.assertEqual([s.pk for s in response.context["scadenze"]], [scadenza.pk])
        self.assertContains(response, "In attesa di fattura definitiva")

    def test_ui_verifica_e_collegamento_manuale(self):
        proforma = self.documento()
        self.scadenza(proforma, pagato="400")
        fattura = self.importa()
        url = reverse("gestisci_proforma_documento", args=[fattura.pk])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Pagamento da conservare")
        response = self.client.post(url, {"azione": "collega", "proforma": proforma.pk})
        self.assertEqual(response.status_code, 302)
        self.assertContains(self.client.get(url), "Pro-forma collegata")
        self.assertContains(self.client.get(reverse("modifica_documento_fornitore", args=[proforma.pk]), {"popup": "1"}), "Fattura definitiva ricevuta")

    def test_nuova_proforma_tipo_preselezionato(self):
        response = self.client.get(reverse("crea_documento_fornitore"), {"tipo": "proforma", "popup": "1"})
        self.assertEqual(response.context["form"]["tipo_documento"].value(), "proforma")
        self.assertContains(response, "Nuova pro-forma")
        self.assertContains(response, "Riferimento ordine")

    def test_permessi_verifica(self):
        fattura = self.documento("F-1", tipo="fattura")
        self.client.force_login(User.objects.create_user(username="senza-permessi"))
        response = self.client.post(reverse("gestisci_proforma_documento", args=[fattura.pk]), {"azione": "distinta"})
        self.assertRedirects(response, reverse("home"), fetch_redirect_response=False)

    def test_banca_collegamento_correzione_e_annullamento_pagamento(self):
        proforma = self.documento()
        scadenza = self.scadenza(proforma)
        movimento = MovimentoFinanziario.objects.create(data_contabile=date(2026, 2, 1), importo=Decimal("-400"), descrizione="Bonifico pro-forma")
        pagamento = registra_pagamento_fornitore(scadenza, importo=Decimal("400"), movimento=movimento, metodo="banca", utente=self.user)
        fattura = self.importa("PF-1")
        pagamento.refresh_from_db()
        self.assertEqual(pagamento.movimento_finanziario_id, movimento.pk)
        self.assertEqual(pagamento.scadenza.documento_id, fattura.pk)
        self.assertEqual(importo_movimento_disponibile_fornitori(movimento), Decimal("0"))
        annulla_collegamento_proforma(fattura)
        pagamento.refresh_from_db()
        self.assertEqual(pagamento.scadenza.documento_id, proforma.pk)
        annulla_pagamento_fornitore(pagamento)
        movimento.refresh_from_db()
        self.assertEqual(importo_movimento_disponibile_fornitori(movimento), Decimal("400"))

    def test_pagina_movimento_propone_proforma_e_riconcilia_acconto(self):
        proforma = self.documento()
        scadenza = self.scadenza(proforma)
        movimento = MovimentoFinanziario.objects.create(
            data_contabile=date(2026, 2, 1), importo=Decimal("-400"),
            descrizione="Acconto PF-1 Fornitore Proforme", controparte=self.fornitore.denominazione,
        )
        url = reverse("riconcilia_movimento", args=[movimento.pk])
        response = self.client.get(url, {"next": reverse("lista_movimenti_finanziari")})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, proforma.numero_documento)
        self.assertEqual([p.allocazioni[0].target.pk for p in response.context["proposte_fornitori"]], [scadenza.pk])

        response = self.client.post(url, {"scadenza": scadenza.pk, "importo": "400", "next": reverse("lista_movimenti_finanziari")})
        self.assertRedirects(response, reverse("lista_movimenti_finanziari"), fetch_redirect_response=False)
        pagamento = PagamentoFornitore.objects.get(movimento_finanziario=movimento)
        self.assertEqual(pagamento.scadenza_id, scadenza.pk)
        self.assertEqual(pagamento.importo, Decimal("400"))
        proforma.refresh_from_db()
        self.assertEqual(proforma.residuo_da_pagare, Decimal("600"))
        self.assertEqual(importo_movimento_disponibile_fornitori(movimento), Decimal("0"))

        fattura = self.importa("PF-1")
        pagamento.refresh_from_db()
        self.assertEqual(pagamento.scadenza.documento_id, fattura.pk)
        self.assertEqual(pagamento.movimento_finanziario_id, movimento.pk)
        self.assertEqual(fattura.residuo_da_pagare, Decimal("600"))

    def test_pagina_movimento_riconcilia_cumulativa_proforma_e_fattura(self):
        proforma = self.documento(totale="400")
        prima = self.scadenza(proforma, importo="400")
        fattura = self.documento("F-2", totale="600", tipo="fattura")
        seconda = self.scadenza(fattura, importo="600")
        movimento = MovimentoFinanziario.objects.create(
            data_contabile=date(2026, 2, 1), importo=Decimal("-1000"),
            descrizione="Pagamento Fornitore Proforme", controparte=self.fornitore.denominazione,
        )
        url = reverse("riconcilia_movimento", args=[movimento.pk])
        response = self.client.get(url)
        proposte = response.context["proposte_fornitori_cumulative"]
        self.assertEqual(len(proposte), 1)
        self.assertEqual({a.target.pk for a in proposte[0].allocazioni}, {prima.pk, seconda.pk})
        response = self.client.post(url, {
            "azione": "collega_fornitori_cumulativa", "scadenza_ids": [prima.pk, seconda.pk],
            f"importo_scadenza_{prima.pk}": "400", f"importo_scadenza_{seconda.pk}": "600",
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(PagamentoFornitore.objects.filter(movimento_finanziario=movimento).count(), 2)
        for documento in (proforma, fattura):
            documento.refresh_from_db()
            self.assertEqual(documento.residuo_da_pagare, Decimal("0"))
        self.assertEqual(importo_movimento_disponibile_fornitori(movimento), Decimal("0"))

    def test_pagina_movimento_dopo_collegamento_propone_solo_residuo_fattura(self):
        proforma = self.documento()
        scadenza = self.scadenza(proforma, pagato="400")
        fattura = self.importa("PF-1")
        movimento = MovimentoFinanziario.objects.create(
            data_contabile=date(2026, 2, 1), importo=Decimal("-600"),
            descrizione="Saldo Fornitore Proforme", controparte=self.fornitore.denominazione,
        )
        response = self.client.get(reverse("riconcilia_movimento", args=[movimento.pk]))
        proposte = response.context["proposte_fornitori"]
        self.assertEqual(len(proposte), 1)
        allocazione = proposte[0].allocazioni[0]
        self.assertEqual(allocazione.target.pk, scadenza.pk)
        self.assertEqual(allocazione.target.documento_id, fattura.pk)
        self.assertEqual(allocazione.importo, Decimal("600"))
        self.assertFalse(response.context["proposte_fornitori_cumulative"])

    def test_pagina_movimento_non_propone_proforma_saldata(self):
        self.scadenza(self.documento(), pagato="1000")
        movimento = MovimentoFinanziario.objects.create(
            data_contabile=date(2026, 2, 1), importo=Decimal("-1000"),
            descrizione="Pagamento Fornitore Proforme", controparte=self.fornitore.denominazione,
        )
        response = self.client.get(reverse("riconcilia_movimento", args=[movimento.pk]))
        self.assertEqual(response.context["proposte_fornitori"], [])
        self.assertEqual(response.context["proposte_fornitori_cumulative"], [])

    def test_due_scadenze_non_pagata_non_rigenerate_da_reimport(self):
        proforma = self.documento()
        prima = self.scadenza(proforma, importo="400")
        seconda = self.scadenza(proforma, importo="600")
        fattura = self.importa("PF-1")
        fattura = self.importa("PF-1")
        self.assertEqual(list(fattura.scadenze.values_list("pk", flat=True)), [prima.pk, seconda.pk])
        self.assertEqual(list(fattura.scadenze.values_list("importo_previsto", flat=True)), [Decimal("400"), Decimal("600")])

    def test_riduzione_importo_su_piu_scadenze_rispetta_pagamenti(self):
        proforma = self.documento()
        prima = self.scadenza(proforma, importo="400", pagato="300")
        seconda = self.scadenza(proforma, importo="600", pagato="200")
        fattura = self.documento("F-1", totale="550", tipo="fattura")
        collega_proforma(fattura, proforma, conferma_differenza=True)
        prima.refresh_from_db()
        seconda.refresh_from_db()
        self.assertEqual(prima.importo_previsto, Decimal("350"))
        self.assertEqual(seconda.importo_previsto, Decimal("200"))
        annulla_collegamento_proforma(fattura)
        prima.refresh_from_db()
        seconda.refresh_from_db()
        self.assertEqual(prima.importo_previsto, Decimal("400"))
        self.assertEqual(seconda.importo_previsto, Decimal("600"))

    def test_reimport_dopo_correzione_rimane_in_verifica(self):
        self.scadenza(self.documento())
        fattura = self.importa("PF-1")
        annulla_collegamento_proforma(fattura)
        fattura = self.importa("PF-1")
        self.assertEqual(fattura.verifica_proforma, VerificaProforma.DA_VERIFICARE)
        self.assertIsNone(fattura.proforma_origine_id)
        self.assertFalse(fattura.scadenze.exists())

    def test_proforma_pagata_da_anni_viene_collegata(self):
        proforma = self.documento()
        proforma.data_documento = date(2020, 1, 3)
        proforma.save()
        self.scadenza(proforma, pagato="1000")
        fattura = self.importa("PF-1")
        self.assertEqual(fattura.proforma_origine_id, proforma.pk)

    def test_ritenuta_diversa_non_autocollega(self):
        self.scadenza(self.documento(ritenuta_acconto=Decimal("200")), importo="800")
        fattura = self.importa("PF-1")
        self.assertEqual(fattura.verifica_proforma, VerificaProforma.DA_VERIFICARE)

    def test_creazione_proforma_senza_scadenze_genera_scadenza_intero_netto(self):
        response = self.client.post(reverse("crea_documento_fornitore"), {
            "fornitore": self.fornitore.pk, "tipo_documento": "proforma", "numero_documento": "PF-NUOVA",
            "data_documento": "2026-01-03", "aliquota_iva": "0", "totale": "1000", "ritenuta_acconto": "200",
            "aliquota_ritenuta_acconto": "20", "stato": "da_pagare", "scadenze-TOTAL_FORMS": "0", "scadenze-INITIAL_FORMS": "0",
        })
        self.assertEqual(response.status_code, 302)
        proforma = DocumentoFornitore.objects.get(numero_documento="PF-NUOVA")
        self.assertEqual(proforma.scadenze.get().importo_previsto, Decimal("800"))

    def test_documento_collegato_non_modificabile_dal_form_generico(self):
        self.scadenza(self.documento())
        fattura = self.importa("PF-1")
        response = self.client.post(reverse("modifica_documento_fornitore", args=[fattura.pk]), {"totale": "9999"})
        self.assertEqual(response.status_code, 302)
        fattura.refresh_from_db()
        self.assertEqual(fattura.totale, Decimal("1000"))

    def test_import_registrato_legge_riferimento_da_xml_allegato(self):
        self.scadenza(self.documento())
        xml_data = {"e_invoice": {"DatiFattureCollegate": {"IdDocumento": "PF-1"}}}
        with patch("gestione_finanziaria.fatture_in_cloud._attachment_xml_details", return_value={"document": xml_data}) as xml:
            fattura = self.importa(extra={"attachment_url": "https://example.invalid/fattura.xml"})
        xml.assert_called_once()
        self.assertIsNotNone(fattura.proforma_origine_id)

    def test_doppio_collegamento_non_riusa_proforma(self):
        proforma = self.documento()
        self.scadenza(proforma)
        fattura = self.documento("F-1", tipo="fattura")
        altra = self.documento("F-2", tipo="fattura")
        collega_proforma(fattura, proforma)
        with self.assertRaises(ValidationError):
            collega_proforma(altra, proforma)
        self.assertEqual(CollegamentoProforma.objects.count(), 1)

    def test_form_verifica_differenza_non_accettata_senza_checkbox(self):
        proforma = self.documento()
        self.scadenza(proforma, pagato="400")
        fattura = self.importa("PF-1", totale="1100")
        response = self.client.post(reverse("gestisci_proforma_documento", args=[fattura.pk]), {"azione": "collega", "proforma": proforma.pk})
        self.assertContains(response, "conferma il nuovo residuo")
        fattura.refresh_from_db()
        self.assertIsNone(fattura.proforma_origine_id)

    def test_xml_preserva_riferimenti_tipizzati(self):
        data = document_data_from_e_invoice_xml('''<FatturaElettronica><FatturaElettronicaBody><DatiGenerali>
          <DatiGeneraliDocumento><Numero>F-1</Numero><Data>2026-03-10</Data></DatiGeneraliDocumento>
          <DatiFattureCollegate><IdDocumento>PF-1</IdDocumento><Data>2026-01-03</Data></DatiFattureCollegate>
          <DatiOrdineAcquisto><IdDocumento>ORD-1</IdDocumento></DatiOrdineAcquisto>
          </DatiGenerali></FatturaElettronicaBody></FatturaElettronica>''')
        general = data["e_invoice"]["FatturaElettronicaBody"]["DatiGenerali"]
        self.assertEqual(general["DatiFattureCollegate"][0]["IdDocumento"], "PF-1")
        self.assertEqual(general["DatiOrdineAcquisto"][0]["IdDocumento"], "ORD-1")


class ProformeConcorrenzaTests(TransactionTestCase):
    @skipUnlessDBFeature("has_select_for_update")
    def test_due_collegamenti_simultanei_non_riutilizzano_la_proforma(self):
        from concurrent.futures import ThreadPoolExecutor
        from threading import Barrier
        from django.db import connections

        fornitore = Fornitore.objects.create(denominazione="Concorrenza pro-forma")
        documenti = [DocumentoFornitore.objects.create(
            fornitore=fornitore, numero_documento=numero, tipo_documento=tipo,
            data_documento=date(2026, 1, 1), totale=Decimal("100"),
        ) for numero, tipo in [("PF-1", "proforma"), ("F-1", "fattura"), ("F-2", "fattura")]]
        proforma = documenti[0]
        scadenza = ScadenzaPagamentoFornitore.objects.create(documento=proforma, data_scadenza=date(2026, 2, 1), importo_previsto=Decimal("100"))
        barrier = Barrier(2)

        def collega(pk):
            try:
                fattura = DocumentoFornitore.objects.get(pk=pk)
                pf = DocumentoFornitore.objects.get(pk=proforma.pk)
                barrier.wait(timeout=10)
                collega_proforma(fattura, pf)
                return "collegata"
            except ValidationError:
                return "rifiutata"
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as pool:
            risultati = list(pool.map(collega, [doc.pk for doc in documenti[1:]]))
        self.assertCountEqual(risultati, ["collegata", "rifiutata"])
        self.assertEqual(CollegamentoProforma.objects.count(), 1)
        scadenza.refresh_from_db()
        self.assertEqual(scadenza.documento_id, CollegamentoProforma.objects.get().fattura_id)
