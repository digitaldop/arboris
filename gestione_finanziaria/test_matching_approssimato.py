from datetime import date
from decimal import Decimal

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import connection
from django.test import SimpleTestCase, TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from anagrafica.models import Familiare, RelazioneFamiliare, Studente, StudenteFamiliare
from economia.models import CondizioneIscrizione, Iscrizione, RataIscrizione, StatoIscrizione
from scuola.models import AnnoScolastico
from .models import (
    DocumentoFornitore, Fornitore, MovimentoFinanziario, PagamentoFornitore,
    ScadenzaPagamentoFornitore,
)
from .name_matching import person_similarity, phrase_similarity, supplier_similarity
from .services import (
    anteprima_riconcilia_fornitori_automaticamente,
    proposte_riconciliazione_da_movimento,
    riconcilia_movimento_automaticamente,
    riconcilia_movimento_con_rate,
    trova_movimenti_candidati_per_rate,
    trova_movimenti_candidati_per_scadenza_fornitore,
    trova_movimenti_cumulativi_candidati_per_rate,
    trova_rate_candidate,
    trova_rate_cumulative_candidate,
    trova_scadenze_fornitori_candidate,
    trova_scadenze_fornitori_cumulative_candidate,
)


class NominativiApprossimatiTests(SimpleTestCase):
    def test_spazi_refusi_accenti_e_ordine_invertito(self):
        for nome, testo in (
            ("Luce Sophia", "Retta LUCE SOPHI A"),
            ("Sophia Luce", "Retta SOPHI A LUCE"),
            ("Nicolò Bianchi", "Bonifico NICOLO BIANCHI"),
            ("Luce Sophia Neri", "Pagamento LUCE SOPHIA NERJ"),
        ):
            with self.subTest(testo=testo):
                self.assertGreaterEqual(phrase_similarity(nome, testo), 0.86)

    def test_nome_composto_senza_cognome_e_un_indizio_piu_debole(self):
        parziale, _ = person_similarity("Luce Sophia", "Neri", "Retta LUCE SOPHI A")
        completo, _ = person_similarity("Luce Sophia", "Neri", "Retta LUCE SOPHI A NERI")
        self.assertGreater(parziale, 0)
        self.assertLess(parziale, completo)

    def test_non_bastano_un_cognome_comune_sigle_o_sottostringhe(self):
        for nome, cognome, testo in (
            ("Simone", "Rossi", "Bonifico Paolo Rossi"),
            ("Anna", "Rossi", "Bonifico Paolo Rossi"),
            ("Marco", "Scamporlino", "Bonifico Paolo Scamporlino"),
            ("Luce Sophia", "Neri", "Retta scuola settembre"),
        ):
            self.assertEqual(person_similarity(nome, cognome, testo)[0], 0)
        self.assertEqual(supplier_similarity("Alfa SRL", "Alfabeta SRL"), 0)
        self.assertEqual(supplier_similarity("Aurora Service SRL", "Boreale Service SRL"), 0)


class RetteMatchingApprossimatoTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.relazione = RelazioneFamiliare.objects.create(relazione="Genitore")
        cls.anno = AnnoScolastico.objects.create(
            nome_anno_scolastico="2025/2026", data_inizio=date(2025, 9, 1), data_fine=date(2026, 6, 30),
        )
        cls.stato = StatoIscrizione.objects.create(stato_iscrizione="Attiva", ordine=1, attiva=True)
        cls.condizione = CondizioneIscrizione.objects.create(
            anno_scolastico=cls.anno, nome_condizione_iscrizione="Retta standard",
            numero_mensilita_default=10, mese_prima_retta=9, giorno_scadenza_rate=10,
        )

    def crea_rata(self, *, studente_nome, studente_cognome, genitore_nome, genitore_cognome):
        familiare = Familiare.objects.create(
            relazione_familiare=self.relazione, nome=genitore_nome, cognome=genitore_cognome,
        )
        studente = Studente.objects.create(nome=studente_nome, cognome=studente_cognome)
        StudenteFamiliare.objects.create(
            studente=studente, familiare=familiare, relazione_familiare=self.relazione, attivo=True,
        )
        iscrizione = Iscrizione.objects.create(
            studente=studente, anno_scolastico=self.anno, stato_iscrizione=self.stato,
            condizione_iscrizione=self.condizione, data_iscrizione=date(2025, 9, 1),
        )
        rata = RataIscrizione.objects.create(
            iscrizione=iscrizione, numero_rata=1, mese_riferimento=9, anno_riferimento=2025,
            importo_dovuto=100, importo_finale=100, data_scadenza=date(2025, 9, 10),
        )
        return studente, rata

    def caso(self, descrizione="Retta LUCE SOPHI A", importo="100.00"):
        _, rata = self.crea_rata(
            studente_nome="Luce Sophia", studente_cognome="Neri",
            genitore_nome="Marco", genitore_cognome="Neri",
        )
        movimento = MovimentoFinanziario.objects.create(
            data_contabile=rata.data_scadenza, importo=Decimal(importo), descrizione=descrizione,
        )
        return rata, movimento

    def test_luce_sophi_a_proposta_in_entrambe_le_direzioni(self):
        rata, movimento = self.caso()
        forward = trova_rate_candidate(movimento)
        backward = trova_movimenti_candidati_per_rate(rata, [rata])
        self.assertEqual([c.rata.pk for c in forward], [rata.pk])
        self.assertEqual([c.movimento.pk for c in backward], [movimento.pk])
        for candidato in [forward[0], backward[0]]:
            self.assertTrue(candidato.richiede_conferma)
            self.assertLess(candidato.score_percentuale, 85)
            self.assertTrue(any("da verificare" in motivo for motivo in candidato.motivazioni))

    def test_importo_e_data_influenzano_lordine(self):
        rata, esatto = self.caso("Retta LUCE SOPHI A NERI")
        parziale = MovimentoFinanziario.objects.create(
            data_contabile=rata.data_scadenza, importo=Decimal("50.00"), descrizione=esatto.descrizione,
        )
        distante = MovimentoFinanziario.objects.create(
            data_contabile=date(2026, 8, 1), importo=Decimal("100.00"), descrizione=esatto.descrizione,
        )
        candidati = trova_movimenti_candidati_per_rate(rata, [rata])
        scores = {c.movimento.pk: c.score_percentuale for c in candidati}
        self.assertGreater(scores[esatto.pk], scores[parziale.pk])
        self.assertGreater(scores[esatto.pk], scores[distante.pk])

    def test_nome_approssimato_non_viene_riconciliato_automaticamente(self):
        rata, movimento = self.caso()
        self.assertIsNone(riconcilia_movimento_automaticamente(movimento, punteggio_minimo=0))
        rata.refresh_from_db()
        self.assertFalse(rata.pagata)

    def test_proposte_cumulative_conservano_la_minore_affidabilita_del_nome(self):
        rata, movimento = self.caso(importo="50.00")
        MovimentoFinanziario.objects.create(
            data_contabile=rata.data_scadenza, importo=50, descrizione=movimento.descrizione,
        )
        proposte = trova_movimenti_cumulativi_candidati_per_rate(rata, [rata])
        self.assertEqual(len(proposte), 1)
        self.assertEqual(len(proposte[0].allocazioni), 2)
        self.assertTrue(proposte[0].richiede_conferma)
        self.assertLess(proposte[0].score_percentuale, 85)
        RataIscrizione.objects.create(
            iscrizione=rata.iscrizione, numero_rata=2, mese_riferimento=10, anno_riferimento=2025,
            importo_dovuto=100, importo_finale=100, data_scadenza=date(2025, 10, 10),
        )
        movimento.importo = Decimal("200.00")
        movimento.save()
        proposte = trova_rate_cumulative_candidate(movimento)
        self.assertEqual(len(proposte), 1)
        self.assertTrue(proposte[0].richiede_conferma)
        self.assertLess(proposte[0].score_percentuale, 85)
        self.assertEqual(trova_rate_cumulative_candidate(movimento, allow_fuzzy=False), [])

    def test_conferma_manuale_salva_la_proposta_e_interfacce_mostrano_compatibilita(self):
        rata, movimento = self.caso()
        user = User.objects.create_superuser(username="conferma-matching")
        self.client.force_login(user)
        url = reverse("riconcilia_movimento", args=[movimento.pk])
        response = self.client.get(url)
        self.assertContains(response, 'class="reconciliation-confidence"')
        self.assertContains(response, "Compatibilità stimata")
        response = self.client.get(reverse("riconcilia_rata_iscrizione", args=[rata.pk]))
        self.assertContains(response, "reconciliation-confidence")
        self.assertEqual([p.allocazioni[0].movimento.pk for p in response.context["proposte_movimento"]], [movimento.pk])
        response = self.client.post(url, {"rata_pk": rata.pk, "marca_rata_pagata": "1", "azione": "collega"})
        self.assertEqual(response.status_code, 302)
        self.assertTrue(movimento.riconciliazioni_rate.filter(rata=rata).exists())

    def test_movimento_corretto_oltre_i_primi_300_record(self):
        rata, movimento = self.caso()
        MovimentoFinanziario.objects.bulk_create([
            MovimentoFinanziario(data_contabile=date(2026, 9, 1), importo=100, descrizione="Bonifico altra famiglia")
            for _ in range(305)
        ])
        # I residui vengono caricati a blocchi: non una query per movimento.
        with CaptureQueriesContext(connection) as queries:
            candidati = trova_movimenti_candidati_per_rate(rata, [rata])
        self.assertLessEqual(len(queries), 15)
        self.assertEqual([c.movimento.pk for c in candidati], [movimento.pk])

    def test_rata_corretta_oltre_i_primi_200_record(self):
        rata, movimento = self.caso()
        _, altra = self.crea_rata(
            studente_nome="Anna", studente_cognome="Verdi",
            genitore_nome="Paolo", genitore_cognome="Verdi",
        )
        RataIscrizione.objects.bulk_create([
            RataIscrizione(iscrizione=altra.iscrizione, numero_rata=i + 2,
                           mese_riferimento=9, anno_riferimento=2026, importo_dovuto=100, importo_finale=100,
                           data_scadenza=date(2026, 9, 1))
            for i in range(205)
        ])
        self.assertEqual([c.rata.pk for c in trova_rate_candidate(movimento)], [rata.pk])

    def test_stesso_cognome_con_altro_genitore_non_basta(self):
        _, rata = self.crea_rata(
            studente_nome="Luca", studente_cognome="Rossi", genitore_nome="Simone", genitore_cognome="Rossi",
        )
        movimento = MovimentoFinanziario.objects.create(
            data_contabile=rata.data_scadenza, importo=100, descrizione="Retta Paolo Rossi",
        )
        self.assertEqual(trova_rate_candidate(movimento), [])
        self.assertEqual(trova_movimenti_candidati_per_rate(rata, [rata]), [])
        with self.assertRaises(ValidationError):
            riconcilia_movimento_con_rate(movimento, [(rata, Decimal("100.00"))])


class FornitoriMatchingApprossimatoTests(TestCase):
    def caso(self, nome="Artan Gjata", testo="Garden service di Gjata", importo="-150.00"):
        fornitore = Fornitore.objects.create(denominazione=nome)
        documento = DocumentoFornitore.objects.create(
            fornitore=fornitore, numero_documento="G-2026", data_documento=date(2026, 6, 1), totale=500,
        )
        scadenza = ScadenzaPagamentoFornitore.objects.create(
            documento=documento, data_scadenza=date(2026, 6, 15), importo_previsto=500,
        )
        movimento = MovimentoFinanziario.objects.create(
            data_contabile=date(2026, 9, 1), importo=Decimal(importo), controparte=testo, descrizione="Acconto",
        )
        return scadenza, movimento

    def test_gjata_ragione_sociale_parziale_e_acconto_lontano_dalla_scadenza(self):
        for nome in ("Gjata", "Artan Gjata", "Garden Service di Gjata Artan"):
            with self.subTest(nome=nome):
                scadenza, movimento = self.caso(nome=nome)
                self.assertIn(scadenza.pk, [c.scadenza.pk for c in trova_scadenze_fornitori_candidate(movimento)])
                self.assertIn(movimento.pk, [c.movimento.pk for c in trova_movimenti_candidati_per_scadenza_fornitore(scadenza)])

    def test_refuso_fornitore_con_importo_esatto_richiede_conferma(self):
        scadenza, movimento = self.caso(nome="Sicurezzambiente SRL", testo="Sicurezzambinte SRL", importo="-500")
        movimento.data_contabile = scadenza.data_scadenza
        movimento.save()
        candidato = trova_scadenze_fornitori_candidate(movimento)[0]
        self.assertTrue(candidato.richiede_conferma)
        self.assertLess(candidato.score_percentuale, 85)
        self.assertEqual(anteprima_riconcilia_fornitori_automaticamente()["dettagli"], [])
        self.assertEqual(PagamentoFornitore.objects.count(), 0)

    def test_refuso_fornitore_cumulativo_non_diventa_certo_sommando_scadenze(self):
        scadenza, movimento = self.caso(nome="Sicurezzambiente SRL", testo="Sicurezzambinte SRL", importo="-1000")
        ScadenzaPagamentoFornitore.objects.create(
            documento=scadenza.documento, data_scadenza=scadenza.data_scadenza, importo_previsto=500,
        )
        proposte = trova_scadenze_fornitori_cumulative_candidate(movimento)
        self.assertEqual(len(proposte), 1)
        self.assertTrue(proposte[0].richiede_conferma)
        self.assertLess(proposte[0].score_percentuale, 85)
        self.assertEqual(trova_scadenze_fornitori_cumulative_candidate(movimento, allow_fuzzy=False), [])

    def test_scadenza_corretta_oltre_le_prime_300(self):
        scadenza, movimento = self.caso()
        altro = Fornitore.objects.create(denominazione="Altro fornitore")
        documento = DocumentoFornitore.objects.create(
            fornitore=altro, numero_documento="ALTRO", data_documento=date(2025, 1, 1), totale=500,
        )
        ScadenzaPagamentoFornitore.objects.bulk_create([
            ScadenzaPagamentoFornitore(documento=documento, data_scadenza=date(2025, 2, 1), importo_previsto=500)
            for _ in range(305)
        ])
        self.assertEqual([c.scadenza.pk for c in trova_scadenze_fornitori_candidate(movimento)], [scadenza.pk])

    def test_movimento_corretto_oltre_i_primi_300(self):
        scadenza, movimento = self.caso()
        MovimentoFinanziario.objects.bulk_create([
            MovimentoFinanziario(data_contabile=date(2026, 9, 8), importo=-150, descrizione="Acconto altro fornitore")
            for _ in range(305)
        ])
        self.assertEqual([c.movimento.pk for c in trova_movimenti_candidati_per_scadenza_fornitore(scadenza)], [movimento.pk])

    def test_movimenti_gia_allocati_propongono_solo_il_residuo_disponibile(self):
        scadenza, movimento = self.caso()
        pagamento = PagamentoFornitore.objects.create(
            scadenza=scadenza, movimento_finanziario=movimento,
            data_pagamento=movimento.data_contabile, importo=100,
        )
        candidati = trova_movimenti_candidati_per_scadenza_fornitore(scadenza)
        self.assertEqual(len(candidati), 1)
        self.assertEqual(candidati[0].importo_disponibile, Decimal("50.00"))
        pagamento.importo = Decimal("150.00")
        pagamento.save()
        self.assertEqual(trova_movimenti_candidati_per_scadenza_fornitore(scadenza), [])

    def test_colore_e_percentuale_nei_due_versi_fornitore(self):
        scadenza, movimento = self.caso()
        user = User.objects.create_superuser(username="fornitore-matching")
        self.client.force_login(user)
        response = self.client.get(reverse("riconcilia_movimento", args=[movimento.pk]))
        self.assertContains(response, 'class="reconciliation-confidence"')
        self.assertTrue(response.context["proposte_fornitori"])
        response = self.client.get(reverse("registra_pagamento_scadenza_fornitore", args=[scadenza.pk]))
        self.assertContains(response, "reconciliation-confidence")
        self.assertEqual([p.allocazioni[0].movimento.pk for p in response.context["proposte_movimento"]], [movimento.pk])
        proposte = proposte_riconciliazione_da_movimento(movimento)
        self.assertTrue(all(0 <= p.score_percentuale <= 100 for p in proposte))
