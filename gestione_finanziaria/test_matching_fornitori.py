from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from django.contrib.auth.models import User
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from .models import DocumentoFornitore, Fornitore, MovimentoFinanziario, PagamentoFornitore, ScadenzaPagamentoFornitore
from .services import (
    _normalizza_testo_match, _supplier_match_score,
    anteprima_riconcilia_fornitori_automaticamente,
    trova_movimenti_candidati_per_scadenza_fornitore,
)


class DenominazioneFornitoreTests(SimpleTestCase):
    def test_sigle_societarie_con_punti_e_spazi_equivalgono_alla_forma_compatta(self):
        for sigla in ("SRLS", "SRL", "SPA", "SAS", "SNC"):
            for scrittura in (".".join(sigla) + ".", " ".join(sigla), sigla):
                with self.subTest(sigla=sigla, scrittura=scrittura):
                    fornitore = SimpleNamespace(denominazione=f"Aurora Servizi {scrittura}")
                    causale = _normalizza_testo_match(f"Bonifico AURORA SERVIZI {sigla}")
                    riferimento = _supplier_match_score(SimpleNamespace(denominazione=f"Aurora Servizi {sigla}"), causale)
                    self.assertEqual(_supplier_match_score(fornitore, causale), riferimento)

    def test_sigla_societaria_da_sola_non_identifica_il_fornitore(self):
        for sigla in ("SRLS", "S.R.L.S."):
            with self.subTest(sigla=sigla):
                fornitore = SimpleNamespace(denominazione=f"Aurora {sigla}")
                score, _ = _supplier_match_score(fornitore, _normalizza_testo_match("Bonifico Boreale SRLS"))
                self.assertEqual(score, 0)

    def test_non_confonde_nome_con_sottostringa_di_un_altro_nome(self):
        fornitore = SimpleNamespace(denominazione="Alfa S.R.L.")
        score, _ = _supplier_match_score(fornitore, _normalizza_testo_match("Bonifico Alfabeta SRL"))
        self.assertEqual(score, 0)


class AccontiFornitoriMatchingTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_superuser(username="matching-fornitori-test")

    def setUp(self):
        self.client.force_login(self.user)

    def crea_caso(self, *, nome, beneficiario, totale, acconto, scadenza, tipo="fattura"):
        fornitore = Fornitore.objects.create(denominazione=nome)
        documento = DocumentoFornitore.objects.create(
            fornitore=fornitore, tipo_documento=tipo, numero_documento="TEST-ACCONTO",
            data_documento=scadenza, totale=Decimal(totale),
        )
        rata = ScadenzaPagamentoFornitore.objects.create(
            documento=documento, data_scadenza=scadenza, importo_previsto=Decimal(totale),
        )
        movimento = MovimentoFinanziario.objects.create(
            data_contabile=date(2026, 9, 8), importo=-Decimal(acconto),
            descrizione=f"VOSTRA DISPOSIZIONE - FAVORE {beneficiario} - ADD.TOT NR. BONIFICO SEPA",
        )
        return rata, movimento

    def test_acconti_fattura_e_proforma_lontani_dalla_scadenza_compaiono_e_si_collegano(self):
        casi = [
            dict(nome="Sicurezzambiente s.r.l.s.", beneficiario="sicurezzambiente srls", totale="2440", acconto="1440", scadenza=date(2026, 6, 23), tipo="proforma"),
            dict(nome="SDC PRODUZIONI S.R.L.S.", beneficiario="SDC PRODUZIONI SRLS", totale="854", acconto="154", scadenza=date(2026, 7, 14)),
        ]
        for caso in casi:
            with self.subTest(fornitore=caso["nome"]):
                scadenza, movimento = self.crea_caso(**caso)
                url = reverse("riconcilia_movimento", args=[movimento.pk])
                response = self.client.get(url)
                proposte = response.context["proposte_fornitori"]
                self.assertIn(scadenza.pk, [p.allocazioni[0].target.pk for p in proposte])
                self.assertFalse(PagamentoFornitore.objects.filter(movimento_finanziario=movimento).exists())
                response = self.client.post(url, {"scadenza": scadenza.pk, "importo": caso["acconto"]})
                self.assertEqual(response.status_code, 302)
                pagamento = PagamentoFornitore.objects.get(movimento_finanziario=movimento)
                self.assertEqual(pagamento.scadenza_id, scadenza.pk)
                self.assertEqual(pagamento.importo, Decimal(caso["acconto"]))
                scadenza.refresh_from_db()
                self.assertEqual(scadenza.importo_previsto - scadenza.importo_pagato, Decimal(caso["totale"]) - Decimal(caso["acconto"]))

    def test_ricerca_dalla_scadenza_riconosce_la_sigla_bancaria(self):
        scadenza, movimento = self.crea_caso(
            nome="SDC PRODUZIONI S.R.L.S.", beneficiario="SDC PRODUZIONI SRLS",
            totale="854", acconto="154", scadenza=date(2026, 7, 14),
        )
        candidati = trova_movimenti_candidati_per_scadenza_fornitore(scadenza)
        self.assertEqual([c.movimento.pk for c in candidati], [movimento.pk])

    def test_acconto_con_nome_riconosciuto_richiede_comunque_conferma_manuale(self):
        self.crea_caso(
            nome="SDC PRODUZIONI S.R.L.S.", beneficiario="SDC PRODUZIONI SRLS",
            totale="854", acconto="154", scadenza=date(2026, 7, 14),
        )
        anteprima = anteprima_riconcilia_fornitori_automaticamente()
        self.assertEqual(anteprima["dettagli"], [])
        self.assertEqual(PagamentoFornitore.objects.count(), 0)
