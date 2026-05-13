import json
from datetime import date, datetime, timedelta
from decimal import Decimal
from io import BytesIO, StringIO
import shutil
import tempfile
from unittest import skip
from unittest.mock import Mock, patch

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from anagrafica.models import Familiare, RelazioneFamiliare, Studente, StudenteFamiliare
from economia.models import CondizioneIscrizione, Iscrizione, RataIscrizione, StatoIscrizione, TariffaCondizioneIscrizione
from scuola.models import AnnoScolastico, Classe
from sistema.models import LivelloPermesso, SistemaUtentePermessi

from .models import (
    CategoriaFinanziaria,
    CanaleMovimento,
    CondizioneRegolaCategorizzazione,
    ContoBancario,
    DocumentoFornitore,
    EsitoSincronizzazione,
    FattureInCloudConnessione,
    FattureInCloudSyncLog,
    FrequenzaVoceBudget,
    Fornitore,
    FonteSaldo,
    MetodoPagamentoFornitore,
    MovimentoFinanziario,
    NotificaFinanziaria,
    PagamentoFornitore,
    PianoRatealeSpesa,
    OrigineDocumentoFornitore,
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
    SpesaOperativa,
    TipoCategoriaFinanziaria,
    TipoContoFinanziario,
    TipoPianoRatealeSpesa,
    TipoProviderBancario,
    TipoSpesaOperativa,
    TipoDocumentoFornitore,
    TipoVoceBudget,
    VoceBudgetRicorrente,
)


def crea_categoria_spesa_test(nome, **kwargs):
    kwargs.setdefault("tipo", TipoCategoriaFinanziaria.SPESA)
    return CategoriaFinanziaria.objects.create(nome=nome, **kwargs)


from .fatture_in_cloud import (
    FattureInCloudClient,
    FattureInCloudError,
    authorization_url,
    has_oauth_credentials,
    importa_documento_fatture_in_cloud,
    sincronizza_fatture_in_cloud,
)
from .importers import CsvImporter, CsvImporterConfig, ExcelImporter, detect_csv_import_config, detect_excel_import_config
from .importers.service import importa_movimenti_da_file
from .services import (
    annulla_pagamento_fornitore,
    anteprima_riconcilia_fornitori_automaticamente,
    applica_regole_a_movimento,
    importo_movimento_disponibile_fornitori,
    applica_anteprima_riconciliazione_fornitori,
    build_budgeting_dashboard_data,
    riconcilia_movimento_con_scadenza_fornitore,
    riconcilia_movimento_con_rate,
    trova_scadenze_fornitori_candidate,
    trova_movimenti_candidati_per_rate,
    trova_rate_cumulative_candidate,
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


@skip("Legacy test basato sulla tabella anagrafica.Famiglia rimossa.")
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

    def test_rate_cumulative_candidate_limits_search_on_many_open_rates(self):
        famiglia = Famiglia.objects.create(
            cognome_famiglia="Rossi",
            stato_relazione_famiglia=self.stato_relazione,
        )
        Familiare.objects.create(
            famiglia=famiglia,
            relazione_familiare=self.relazione_genitore,
            nome="Simone",
            cognome="Rossi",
        )
        nomi = ["Luca", "Marta", "Anna", "Pietro", "Giulia", "Marco"]
        for nome in nomi:
            studente = Studente.objects.create(
                famiglia=famiglia,
                nome=nome,
                cognome="Rossi",
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
            for index, mese in enumerate(range(9, 13), start=1):
                RataIscrizione.objects.create(
                    iscrizione=iscrizione,
                    famiglia=famiglia,
                    numero_rata=index,
                    mese_riferimento=mese,
                    anno_riferimento=2025,
                    importo_dovuto=Decimal("100.00"),
                    importo_finale=Decimal("100.00"),
                    data_scadenza=date(2025, mese, 10),
                )

        movimento = MovimentoFinanziario.objects.create(
            data_contabile=date(2025, 9, 10),
            importo=Decimal("200.00"),
            descrizione="Bonifico rette settembre Luca e Marta Rossi",
            stato_riconciliazione=StatoRiconciliazione.NON_RICONCILIATO,
        )

        candidati = trova_rate_cumulative_candidate(movimento)

        self.assertTrue(candidati)
        self.assertEqual(len(candidati[0].allocazioni), 2)
        self.assertEqual(
            sum(importo for _rata, importo in candidati[0].allocazioni),
            Decimal("200.00"),
        )

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


class BudgetingGestioneFinanziariaTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="budget@example.com",
            email="budget@example.com",
            password="Password123!",
        )
        SistemaUtentePermessi.objects.create(
            user=self.user,
            permesso_gestione_finanziaria=LivelloPermesso.GESTIONE,
        )
        self.client.force_login(self.user)
        self.today = timezone.localdate()
        AnnoScolastico.objects.create(
            nome_anno_scolastico="2025/2026",
            data_inizio=date(2025, 9, 1),
            data_fine=date(2026, 6, 30),
        )

    def test_budgeting_dashboard_renders_recurring_forecast(self):
        categoria = CategoriaFinanziaria.objects.create(
            nome="Affitto",
            tipo=TipoCategoriaFinanziaria.SPESA,
        )
        VoceBudgetRicorrente.objects.create(
            nome="Affitto sede",
            tipo=TipoVoceBudget.USCITA,
            categoria=categoria,
            importo=Decimal("1500.00"),
            frequenza=FrequenzaVoceBudget.MENSILE,
            data_inizio=date(self.today.year, self.today.month, 1),
            giorno_previsto=5,
        )

        data = build_budgeting_dashboard_data(today=self.today)
        self.assertEqual(data["current_month"]["ricorrenti_uscite"], Decimal("1500.00"))
        self.assertEqual(data["current_month"]["uscite_previste"], Decimal("1500.00"))

        response = self.client.get(reverse("budgeting_dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Budgeting")
        self.assertContains(response, "Affitto sede")
        self.assertContains(response, "EUR 1.500,00")
        self.assertContains(response, "Flusso di cassa")
        self.assertContains(response, "Bilancio mese per mese")
        self.assertContains(response, "Affitto")

    def test_crea_voce_budget(self):
        response = self.client.post(
            reverse("crea_voce_budget"),
            {
                "nome": "Contributo pubblico previsto",
                "tipo": TipoVoceBudget.ENTRATA,
                "categoria": "",
                "fornitore": "",
                "importo": "500.00",
                "frequenza": FrequenzaVoceBudget.UNA_TANTUM,
                "data_inizio": self.today.strftime("%Y-%m-%d"),
                "data_fine": "",
                "giorno_previsto": str(self.today.day),
                "attiva": "on",
                "note": "Prima ipotesi di budget.",
            },
        )

        self.assertRedirects(response, reverse("budgeting_dashboard"))
        voce = VoceBudgetRicorrente.objects.get(nome="Contributo pubblico previsto")
        self.assertEqual(voce.tipo, TipoVoceBudget.ENTRATA)
        self.assertEqual(voce.importo, Decimal("500.00"))
        self.assertIsNone(voce.mese_previsto)

    def test_crea_voce_budget_popup_chiude_dopo_salvataggio(self):
        response = self.client.post(
            reverse("crea_voce_budget"),
            {
                "popup": "1",
                "nome": "Contributo popup",
                "tipo": TipoVoceBudget.ENTRATA,
                "categoria": "",
                "fornitore": "",
                "importo": "300.00",
                "frequenza": FrequenzaVoceBudget.UNA_TANTUM,
                "data_inizio": self.today.strftime("%Y-%m-%d"),
                "data_fine": "",
                "giorno_previsto": str(self.today.day),
                "attiva": "on",
                "note": "",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "popup/popup_close.html")
        self.assertContains(response, "Voce di budget creata correttamente.")
        self.assertTrue(VoceBudgetRicorrente.objects.filter(nome="Contributo popup").exists())

    def test_dashboard_apre_voci_budget_in_popup(self):
        voce = VoceBudgetRicorrente.objects.create(
            nome="Canone da popup",
            tipo=TipoVoceBudget.USCITA,
            importo=Decimal("900.00"),
            frequenza=FrequenzaVoceBudget.MENSILE,
            data_inizio=date(2026, 1, 1),
            giorno_previsto=1,
        )

        response = self.client.get(reverse("budgeting_dashboard"))

        self.assertContains(response, f'{reverse("crea_voce_budget")}?popup=1')
        self.assertContains(response, f'{reverse("modifica_voce_budget", args=[voce.pk])}?popup=1')
        self.assertContains(response, 'data-window-popup="1"')

    def test_voce_budget_inattiva_resta_visibile_e_togglabile(self):
        categoria = CategoriaFinanziaria.objects.create(
            nome="Utenze",
            tipo=TipoCategoriaFinanziaria.SPESA,
        )
        voce = VoceBudgetRicorrente.objects.create(
            nome="Utenza stimata",
            tipo=TipoVoceBudget.USCITA,
            categoria=categoria,
            importo=Decimal("280.00"),
            frequenza=FrequenzaVoceBudget.MENSILE,
            data_inizio=date(self.today.year, self.today.month, 1),
            giorno_previsto=15,
            attiva=False,
        )

        data = build_budgeting_dashboard_data(today=self.today)
        self.assertEqual(data["current_month"]["ricorrenti_uscite"], Decimal("0.00"))
        self.assertEqual(data["voci_budget_count"], 1)
        self.assertEqual(data["voci_budget_attive_count"], 0)

        response = self.client.get(reverse("budgeting_dashboard"))
        self.assertContains(response, "Utenza stimata")
        self.assertContains(response, "Non attiva")

        response = self.client.post(
            reverse("toggle_voce_budget", args=[voce.pk]),
            {"attiva": "1", "ajax": "1"},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response.status_code, 200)
        voce.refresh_from_db()
        self.assertTrue(voce.attiva)

        data = build_budgeting_dashboard_data(today=self.today)
        self.assertEqual(data["current_month"]["ricorrenti_uscite"], Decimal("280.00"))

    def test_modifica_voce_budget_precompila_date_e_nasconde_mese_previsto(self):
        voce = VoceBudgetRicorrente.objects.create(
            nome="Canone annuale",
            tipo=TipoVoceBudget.USCITA,
            importo=Decimal("900.00"),
            frequenza=FrequenzaVoceBudget.ANNUALE,
            data_inizio=date(2026, 1, 15),
            data_fine=date(2026, 12, 31),
            giorno_previsto=15,
            mese_previsto=4,
        )

        response = self.client.get(reverse("modifica_voce_budget", args=[voce.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'value="2026-01-15"')
        self.assertContains(response, 'value="2026-12-31"')
        self.assertNotContains(response, "Mese previsto")
        self.assertContains(response, 'id="add-budget-categoria-btn"')
        self.assertContains(response, 'id="add-budget-fornitore-btn"')

    def test_modifica_voce_budget_popup_usa_template_popup(self):
        voce = VoceBudgetRicorrente.objects.create(
            nome="Canone popup",
            tipo=TipoVoceBudget.USCITA,
            importo=Decimal("900.00"),
            frequenza=FrequenzaVoceBudget.ANNUALE,
            data_inizio=date(2026, 1, 15),
            data_fine=date(2026, 12, 31),
            giorno_previsto=15,
        )

        response = self.client.get(f'{reverse("modifica_voce_budget", args=[voce.pk])}?popup=1')

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'body class="popup-page"')
        self.assertContains(response, 'name="popup" value="1"')
        self.assertContains(response, "budget-voice-popup-card")
        self.assertContains(response, "budget-voice-input-shell")
        self.assertContains(response, 'value="2026-01-15"')

    def test_modifica_voce_budget_popup_chiude_dopo_salvataggio(self):
        voce = VoceBudgetRicorrente.objects.create(
            nome="Canone da aggiornare",
            tipo=TipoVoceBudget.USCITA,
            importo=Decimal("900.00"),
            frequenza=FrequenzaVoceBudget.ANNUALE,
            data_inizio=date(2026, 1, 15),
            data_fine=date(2026, 12, 31),
            giorno_previsto=15,
        )

        response = self.client.post(
            reverse("modifica_voce_budget", args=[voce.pk]),
            {
                "popup": "1",
                "nome": "Canone aggiornato",
                "tipo": TipoVoceBudget.USCITA,
                "categoria": "",
                "fornitore": "",
                "importo": "950.00",
                "frequenza": FrequenzaVoceBudget.ANNUALE,
                "data_inizio": "2026-01-15",
                "data_fine": "2026-12-31",
                "giorno_previsto": "15",
                "attiva": "on",
                "note": "",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "popup/popup_close.html")
        self.assertContains(response, "Voce di budget aggiornata correttamente.")
        voce.refresh_from_db()
        self.assertEqual(voce.nome, "Canone aggiornato")
        self.assertEqual(voce.importo, Decimal("950.00"))


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

    def _crea_scadenza_pagamento_test(self, *, importo=Decimal("100.00")):
        fornitore = Fornitore.objects.create(denominazione="Beta Servizi")
        documento = DocumentoFornitore.objects.create(
            fornitore=fornitore,
            numero_documento="BETA-001",
            data_documento=timezone.localdate(),
            totale=importo,
        )
        scadenza = ScadenzaPagamentoFornitore.objects.create(
            documento=documento,
            data_scadenza=timezone.localdate(),
            importo_previsto=importo,
        )
        movimento = MovimentoFinanziario.objects.create(
            data_contabile=timezone.localdate(),
            importo=-importo,
            descrizione="Bonifico Beta Servizi",
            controparte="Beta Servizi",
            stato_riconciliazione=StatoRiconciliazione.NON_RICONCILIATO,
        )
        return scadenza, movimento

    def test_tipo_documento_fornitore_include_proforma_after_fattura(self):
        choices = list(TipoDocumentoFornitore.choices)

        self.assertEqual(choices[0], (TipoDocumentoFornitore.FATTURA, "Fattura"))
        self.assertEqual(choices[1], (TipoDocumentoFornitore.PROFORMA, "Proforma"))

    def test_pagamento_fornitore_popup_usa_layout_senza_shell_globale(self):
        scadenza, _movimento = self._crea_scadenza_pagamento_test()

        response = self.client.get(f"{reverse('registra_pagamento_scadenza_fornitore', kwargs={'pk': scadenza.pk})}?popup=1")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'class="popup-page"', html=False)
        self.assertContains(response, "supplier-payment-shell is-popup")
        self.assertContains(response, "Riconciliazione bancaria")
        self.assertContains(response, "Riconcilia")
        self.assertContains(response, "Conferma pagamento")
        self.assertContains(response, 'onclick="window.close()"')
        self.assertContains(response, '<span class="btn-label">Annulla</span>', html=False)
        self.assertContains(response, "Confermi la riconciliazione con questo movimento bancario")
        self.assertNotContains(response, "NAVIGAZIONE")

    def test_pagamento_fornitore_popup_riconcilia_movimento_candidato(self):
        scadenza, movimento = self._crea_scadenza_pagamento_test()

        response = self.client.post(
            f"{reverse('registra_pagamento_scadenza_fornitore', kwargs={'pk': scadenza.pk})}?popup=1",
            {
                "popup": "1",
                "scadenza": str(scadenza.pk),
                "quick_movimento": str(movimento.pk),
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Pagamento fornitore registrato correttamente.")
        self.assertContains(response, r"gestione\u002Dfinanziaria/documenti\u002Dfornitori")
        self.assertContains(response, "handleReloadToUrl")
        self.assertContains(response, "popup-close-fallback")
        pagamento = PagamentoFornitore.objects.get(scadenza=scadenza)
        self.assertEqual(pagamento.movimento_finanziario, movimento)
        self.assertEqual(pagamento.metodo, MetodoPagamentoFornitore.BANCA)
        self.assertEqual(pagamento.importo, Decimal("100.00"))
        scadenza.refresh_from_db()
        movimento.refresh_from_db()
        self.assertEqual(scadenza.stato, StatoScadenzaFornitore.PAGATA)
        self.assertEqual(movimento.stato_riconciliazione, StatoRiconciliazione.RICONCILIATO)

    def test_documento_fornitore_popup_annulla_pagamento_usa_popup_gestito(self):
        scadenza, movimento = self._crea_scadenza_pagamento_test()
        pagamento = riconcilia_movimento_con_scadenza_fornitore(movimento, scadenza, utente=self.user)
        documento_url = reverse("modifica_documento_fornitore", kwargs={"pk": scadenza.documento.pk})
        annulla_url = f"{reverse('elimina_pagamento_fornitore', kwargs={'pk': pagamento.pk})}?popup=1"

        response = self.client.get(f"{documento_url}?popup=1")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, annulla_url)
        self.assertContains(response, 'data-window-popup="1"')
        self.assertContains(response, f'data-popup-url="{annulla_url}"')
        self.assertContains(response, 'data-popup-window-features="width=760,height=560,resizable=yes,scrollbars=yes"')

    def test_documento_fornitore_popup_mostra_elimina_movimento_in_sola_lettura(self):
        scadenza, movimento = self._crea_scadenza_pagamento_test()
        pagamento = riconcilia_movimento_con_scadenza_fornitore(movimento, scadenza, utente=self.user)
        documento_url = reverse("modifica_documento_fornitore", kwargs={"pk": scadenza.documento.pk})
        annulla_url = f"{reverse('elimina_pagamento_fornitore', kwargs={'pk': pagamento.pk})}?popup=1"

        response = self.client.get(f"{documento_url}?popup=1")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "is-view-mode")
        self.assertContains(response, "Elimina movimento")
        self.assertContains(response, f'href="{annulla_url}"')
        content = response.content.decode()
        anchor_start = content.index(f'href="{annulla_url}"')
        anchor_end = content.index(">", anchor_start)
        self.assertNotIn("mode-edit-only", content[anchor_start:anchor_end])
        actions_start = content.rfind('data-label="Azioni"', 0, anchor_start)
        payments_start = content.rfind('data-label="Pagamenti"', 0, anchor_start)
        self.assertGreater(actions_start, payments_start)
        actions_end = content.index("</td>", actions_start)
        self.assertIn("Elimina movimento", content[actions_start:actions_end])

    def test_elimina_pagamento_fornitore_popup_usa_layout_e_chiude(self):
        scadenza, movimento = self._crea_scadenza_pagamento_test()
        pagamento = riconcilia_movimento_con_scadenza_fornitore(movimento, scadenza, utente=self.user)
        annulla_url = f"{reverse('elimina_pagamento_fornitore', kwargs={'pk': pagamento.pk})}?popup=1"

        response = self.client.get(annulla_url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'class="popup-page"', html=False)
        self.assertContains(response, "supplier-payment-shell is-popup")
        self.assertContains(response, '<input type="hidden" name="popup" value="1">', html=False)
        self.assertContains(response, 'onclick="window.close()"')
        self.assertNotContains(response, "NAVIGAZIONE")

        response = self.client.post(annulla_url, {"popup": "1"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Pagamento fornitore annullato.")
        self.assertContains(response, r"gestione\u002Dfinanziaria/documenti\u002Dfornitori")
        self.assertContains(response, "handleReloadToUrl")
        self.assertContains(response, "popup-close-fallback")
        self.assertContains(response, "handleReload")
        self.assertFalse(PagamentoFornitore.objects.filter(pk=pagamento.pk).exists())
        movimento.refresh_from_db()
        self.assertEqual(movimento.stato_riconciliazione, StatoRiconciliazione.NON_RICONCILIATO)

    def test_categoria_spesa_crud_pages(self):
        response = self.client.get(reverse("crea_categoria_spesa"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "category-expense-editor-shell")
        self.assertContains(response, "Categoria padre")

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

        response = self.client.post(
            reverse("crea_categoria_spesa"),
            {
                "nome": "Consulenze legali",
                "parent": str(categoria.pk),
                "descrizione": "Sottocategoria per consulenze legali",
                "ordine": "2",
                "attiva": "on",
            },
        )

        self.assertRedirects(response, reverse("lista_categorie_spesa"))
        sottocategoria = CategoriaFinanziaria.objects.get(
            nome="Consulenze legali",
            tipo=TipoCategoriaFinanziaria.SPESA,
        )
        self.assertEqual(sottocategoria.parent, categoria)

        response = self.client.get(reverse("lista_categorie_spesa"))
        self.assertContains(response, "Consulenze")
        self.assertContains(response, "Consulenze legali")
        self.assertContains(response, 'data-report-category-toggle="categoria-spesa-')
        self.assertContains(response, 'data-report-category-parent="categoria-spesa-')
        self.assertContains(response, "category-tree-badge-parent")
        self.assertContains(response, "Figlia")

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
        self.assertContains(response, "supplier-profile-card")
        self.assertContains(response, "js/pages/fornitore-form.js")

    def test_fornitore_detail_renders_view_mode_and_sidebar_cards(self):
        categoria = crea_categoria_spesa_test("Cancelleria")
        fornitore = Fornitore.objects.create(
            denominazione="Carta Srl",
            tipo_soggetto="azienda",
            categoria_spesa=categoria,
            partita_iva="12345678901",
            email="ordini@carta.test",
        )
        documento = DocumentoFornitore.objects.create(
            fornitore=fornitore,
            categoria_spesa=categoria,
            numero_documento="C-001",
            data_documento=date(2026, 5, 1),
            imponibile=Decimal("100.00"),
            iva=Decimal("22.00"),
            totale=Decimal("122.00"),
        )
        ScadenzaPagamentoFornitore.objects.create(
            documento=documento,
            data_scadenza=date(2026, 5, 31),
            importo_previsto=Decimal("122.00"),
        )

        response = self.client.get(reverse("modifica_fornitore", kwargs={"pk": fornitore.pk}))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="fornitore-detail-form"')
        self.assertContains(response, "is-view-mode")
        self.assertContains(response, 'id="enable-edit-fornitore-btn"')
        self.assertContains(response, 'id="fornitore-main-fields"')
        self.assertContains(response, "supplier-profile-layout")
        self.assertContains(response, "supplier-profile-sidebar")
        self.assertContains(response, "Fatture recenti")
        self.assertContains(response, "Scadenze aperte")
        self.assertContains(response, "C-001")
        self.assertContains(response, "31/05/2026")
        self.assertContains(response, 'class="btn btn-secondary btn-icon-text js-page-back-btn"')
        self.assertContains(response, "view-mode.js")

    def test_categoria_spesa_popup_create_returns_select_response(self):
        padre = crea_categoria_spesa_test("Servizi generali")
        response = self.client.get(f"{reverse('crea_categoria_spesa')}?popup=1&target_input_name=categoria_spesa")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "category-expense-editor-shell is-popup")
        self.assertContains(response, "Categoria padre")

        response = self.client.post(
            f"{reverse('crea_categoria_spesa')}?popup=1&target_input_name=categoria_spesa",
            {
                "popup": "1",
                "target_input_name": "categoria_spesa",
                "nome": "Servizi",
                "parent": str(padre.pk),
                "descrizione": "",
                "ordine": "",
                "attiva": "on",
            },
        )

        categoria = CategoriaFinanziaria.objects.get(nome="Servizi", tipo=TipoCategoriaFinanziaria.SPESA)
        self.assertEqual(categoria.parent, padre)
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

    def test_documento_fornitore_popup_mostra_dati_effettivi(self):
        categoria = crea_categoria_spesa_test("Cancelleria")
        fornitore = Fornitore.objects.create(
            denominazione="Cartoleria Test",
            tipo_soggetto="azienda",
        )
        documento = DocumentoFornitore.objects.create(
            fornitore=fornitore,
            tipo_documento=TipoDocumentoFornitore.FATTURA,
            numero_documento="CAR-1",
            data_documento=date(2026, 5, 2),
            imponibile=Decimal("100.00"),
            iva=Decimal("22.00"),
            totale=Decimal("122.00"),
            importato_at=timezone.make_aware(datetime(2026, 5, 4, 12, 0)),
        )
        fornitore.categoria_spesa = categoria
        fornitore.save(update_fields=["categoria_spesa", "data_aggiornamento"])

        response = self.client.get(f'{reverse("modifica_documento_fornitore", kwargs={"pk": documento.pk})}?popup=1')

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Data ricezione")
        self.assertContains(response, "04 / 05 / 2026")
        self.assertContains(response, "Cancelleria")
        self.assertContains(response, "Maggio")

        response = self.client.get(reverse("lista_documenti_fornitori"), {"categoria": str(categoria.pk)})
        self.assertContains(response, "CAR-1")

    def test_documento_fornitore_popup_limits_movimento_choices_but_keeps_selected_one(self):
        fornitore = Fornitore.objects.create(denominazione="Tecnica Srl")
        documento = DocumentoFornitore.objects.create(
            fornitore=fornitore,
            numero_documento="F-010",
            data_documento=date(2026, 5, 1),
            imponibile=Decimal("100.00"),
            iva=Decimal("22.00"),
            totale=Decimal("122.00"),
        )
        movimento_storico_collegato = MovimentoFinanziario.objects.create(
            data_contabile=date(2024, 1, 2),
            importo=Decimal("-122.00"),
            descrizione="Movimento storico collegato",
        )
        MovimentoFinanziario.objects.create(
            data_contabile=date(2024, 1, 1),
            importo=Decimal("-50.00"),
            descrizione="Movimento storico non collegato",
        )
        MovimentoFinanziario.objects.bulk_create(
            [
                MovimentoFinanziario(
                    data_contabile=date(2026, 5, 1) + timedelta(days=index),
                    importo=Decimal("-10.00"),
                    descrizione=f"Movimento recente {index}",
                )
                for index in range(130)
            ]
        )
        ScadenzaPagamentoFornitore.objects.create(
            documento=documento,
            data_scadenza=date(2026, 5, 31),
            importo_previsto=Decimal("122.00"),
            movimento_finanziario=movimento_storico_collegato,
        )

        response = self.client.get(f'{reverse("modifica_documento_fornitore", kwargs={"pk": documento.pk})}?popup=1')

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "supplier-document-detail-shell is-popup")
        self.assertContains(response, "supplier-document-summary-grid")
        self.assertContains(response, "supplier-deadline-view-list")
        self.assertContains(response, "supplier-document-edit-table")
        self.assertContains(response, "is-view-mode")
        self.assertContains(response, 'id="enable-edit-documento-fornitore-btn"')
        self.assertContains(response, "Collega movimento bancario")
        self.assertContains(response, "mode-edit-only-table-cell")
        self.assertContains(response, "Movimento storico collegato")
        self.assertNotContains(response, "Movimento storico non collegato")
        pagamento_url = f"{reverse('registra_pagamento_scadenza_fornitore', kwargs={'pk': documento.scadenze.first().pk})}?popup=1"
        self.assertContains(response, f'href="{pagamento_url}"')
        self.assertContains(response, f'data-popup-url="{pagamento_url}"')
        self.assertContains(response, 'data-window-popup="1"')
        self.assertContains(response, 'data-popup-window-features="width=1120,height=820,resizable=yes,scrollbars=yes"')

    def test_notifica_fattura_ricevuta_apre_fattura_in_popup(self):
        fornitore = Fornitore.objects.create(denominazione="Cloud Supplier Srl")
        documento = DocumentoFornitore.objects.create(
            fornitore=fornitore,
            numero_documento="FC-42",
            data_documento=date(2026, 4, 20),
            imponibile=Decimal("100.00"),
            iva=Decimal("22.00"),
            totale=Decimal("122.00"),
        )
        documento_url = reverse("modifica_documento_fornitore", kwargs={"pk": documento.pk})
        NotificaFinanziaria.objects.create(
            titolo="Nuova fattura fornitore ricevuta",
            messaggio="Cloud Supplier Srl - FC-42 - EUR 122.00",
            tipo="fattura_ricevuta",
            url=documento_url,
            documento=documento,
        )

        response = self.client.get(reverse("lista_notifiche_finanziarie"))

        popup_url = f"{documento_url}?popup=1"
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, f'href="{popup_url}"', count=2)
        self.assertContains(response, f'data-popup-url="{popup_url}"', count=2)
        self.assertContains(response, 'data-window-popup="1"', count=2)
        self.assertNotContains(response, f'href="{documento_url}"')

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

    def test_importa_documento_fatture_in_cloud_legge_fornitore_da_header_xml_standard(self):
        connessione = FattureInCloudConnessione.objects.create(
            nome="FIC",
            company_id=123,
        )
        payload = {
            "id": 994,
            "type": "expense",
            "description": "Fattura elettronica standard",
            "date": "2026-05-02",
            "amount_net": "100.00",
            "amount_vat": "22.00",
            "e_invoice": {
                "FatturaElettronicaHeader": {
                    "CedentePrestatore": {
                        "DatiAnagrafici": {
                            "IdFiscaleIVA": {"IdPaese": "IT", "IdCodice": "12345678907"},
                            "CodiceFiscale": "ABCDEF12G34H567I",
                            "Anagrafica": {"Denominazione": "Header Supplier Srl"},
                        },
                        "Sede": {
                            "Indirizzo": "Via Header 4",
                            "CAP": "40121",
                            "Comune": "Bologna",
                            "Provincia": "BO",
                        },
                        "Contatti": {
                            "Telefono": "051999",
                            "Email": "header@example.com",
                            "PECMail": "header@examplepec.it",
                        },
                    },
                },
                "FatturaElettronicaBody": {
                    "DatiGenerali": {
                        "DatiGeneraliDocumento": {
                            "Numero": "STD-55",
                            "ImportoTotaleDocumento": "122.00",
                        }
                    },
                    "DatiPagamento": [
                        {
                            "DettaglioPagamento": [
                                {
                                    "DataScadenzaPagamento": "2026-06-30",
                                    "ImportoPagamento": "122.00",
                                    "IBAN": "IT60X0542811101000000123456",
                                    "IstitutoFinanziario": "Banca Header",
                                }
                            ]
                        }
                    ],
                },
            },
        }

        importa_documento_fatture_in_cloud(connessione, payload, pending=True, utente=self.user)

        documento = DocumentoFornitore.objects.get(external_id="994")
        fornitore = documento.fornitore
        self.assertEqual(fornitore.denominazione, "Header Supplier Srl")
        self.assertEqual(fornitore.partita_iva, "12345678907")
        self.assertEqual(fornitore.codice_fiscale, "ABCDEF12G34H567I")
        self.assertEqual(fornitore.indirizzo, "Via Header 4 40121 Bologna BO")
        self.assertEqual(fornitore.telefono, "051999")
        self.assertEqual(fornitore.email, "header@example.com")
        self.assertEqual(fornitore.pec, "header@examplepec.it")
        self.assertEqual(fornitore.codice_sdi, "")
        self.assertEqual(fornitore.iban, "IT60X0542811101000000123456")
        self.assertEqual(fornitore.banca, "Banca Header")
        self.assertEqual(documento.numero_documento, "STD-55")
        scadenza = documento.scadenze.get()
        self.assertEqual(scadenza.data_scadenza, date(2026, 6, 30))

    def test_importa_documento_fatture_in_cloud_pending_usa_supplier_name_e_scadenza(self):
        connessione = FattureInCloudConnessione.objects.create(
            nome="FIC",
            company_id=123,
        )
        payload = {
            "id": 993,
            "type": "agyo",
            "document_type": "expense",
            "subject": "Fattura da registrare",
            "supplier_name": "Fornitore Pending Srl",
            "invoice_number": "PEND-1",
            "emssion_date": "2026-04-25",
            "amount_net": "300.00",
            "amount_vat": "66.00",
            "amount_gross": "366.00",
            "payments_list": [
                {
                    "due_date": "2026-06-10",
                    "amount": "366.00",
                    "status": "not_paid",
                }
            ],
        }

        result = importa_documento_fatture_in_cloud(connessione, payload, pending=True, utente=self.user)

        self.assertTrue(result["created"])
        self.assertTrue(result["fornitore_created"])
        documento = DocumentoFornitore.objects.get(external_id="993")
        self.assertEqual(documento.fornitore.denominazione, "Fornitore Pending Srl")
        self.assertEqual(documento.tipo_documento, TipoDocumentoFornitore.FATTURA)
        self.assertEqual(documento.data_documento, date(2026, 4, 25))
        self.assertEqual(documento.numero_documento, "PEND-1")
        self.assertEqual(documento.totale, Decimal("366.00"))
        scadenza = documento.scadenze.get()
        self.assertEqual(scadenza.data_scadenza, date(2026, 6, 10))
        self.assertEqual(scadenza.importo_previsto, Decimal("366.00"))

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

    @patch("gestione_finanziaria.fatture_in_cloud.FattureInCloudClient")
    def test_sincronizza_fatture_in_cloud_arricchisce_fornitore_da_entity_supplier(self, mock_client_class):
        connessione = FattureInCloudConnessione.objects.create(
            nome="FIC",
            company_id=123,
            sincronizza_documenti_da_registrare=False,
        )
        Fornitore.objects.create(denominazione="Supplier Basic Srl", tipo_soggetto="azienda")
        client = Mock()
        client.list_received_documents.side_effect = [
            {"data": [{"id": 995, "entity": {"id": 77, "name": "Supplier Basic Srl"}}], "pagination": {"current_page": 1, "last_page": 1}},
            {"data": [], "pagination": {"current_page": 1, "last_page": 1}},
        ]
        client.get_received_document.return_value = {
            "id": 995,
            "type": "expense",
            "description": "Dettaglio con fornitore minimo",
            "invoice_number": "DET-SUP-1",
            "date": "2026-05-04",
            "amount_net": "100.00",
            "amount_vat": "22.00",
            "amount_gross": "122.00",
            "entity": {"id": 77, "name": "Supplier Basic Srl", "vat_number": "IT12345678909"},
            "payments_list": [{"due_date": "2026-06-04", "amount": "122.00"}],
        }
        client.get_supplier.return_value = {
            "id": 77,
            "name": "Supplier Basic Srl",
            "vat_number": "IT12345678909",
            "tax_code": "12345678909",
            "address_street": "Via Completa 8",
            "address_postal_code": "40122",
            "address_city": "Bologna",
            "address_province": "BO",
            "email": "fornitore@example.com",
            "certified_email": "fornitore@examplepec.it",
            "phone": "051888",
        }
        mock_client_class.return_value = client

        stats = sincronizza_fatture_in_cloud(connessione, utente=self.user)

        self.assertEqual(stats["creati"], 1)
        self.assertEqual(stats["fornitori_creati"], 0)
        self.assertEqual(stats["fornitori_aggiornati"], 1)
        client.get_supplier.assert_called_once_with("77")
        fornitore = Fornitore.objects.get(denominazione="Supplier Basic Srl")
        self.assertEqual(fornitore.partita_iva, "12345678909")
        self.assertEqual(fornitore.codice_fiscale, "12345678909")
        self.assertEqual(fornitore.indirizzo, "Via Completa 8 40122 Bologna BO")
        self.assertEqual(fornitore.email, "fornitore@example.com")
        self.assertEqual(fornitore.pec, "fornitore@examplepec.it")
        self.assertEqual(fornitore.telefono, "051888")

    @patch("gestione_finanziaria.fatture_in_cloud.FattureInCloudClient")
    def test_sincronizza_fatture_in_cloud_importa_documento_se_supplier_scope_manca(self, mock_client_class):
        connessione = FattureInCloudConnessione.objects.create(
            nome="FIC",
            company_id=123,
            sincronizza_documenti_da_registrare=False,
        )
        client = Mock()
        client.list_received_documents.side_effect = [
            {"data": [{"id": 996, "entity": {"id": 78, "name": "Supplier Scope Srl"}}], "pagination": {"current_page": 1, "last_page": 1}},
            {"data": [], "pagination": {"current_page": 1, "last_page": 1}},
        ]
        client.get_received_document.return_value = {
            "id": 996,
            "type": "expense",
            "invoice_number": "NO-SCOPE-1",
            "date": "2026-05-04",
            "amount_net": "100.00",
            "amount_vat": "22.00",
            "amount_gross": "122.00",
            "entity": {"id": 78, "name": "Supplier Scope Srl"},
            "payments_list": [{"due_date": "2026-06-04", "amount": "122.00"}],
        }
        client.get_supplier.side_effect = FattureInCloudError("Errore API Fatture in Cloud 403")
        mock_client_class.return_value = client

        stats = sincronizza_fatture_in_cloud(connessione, utente=self.user)

        self.assertEqual(stats["creati"], 1)
        self.assertEqual(stats["esito"], EsitoSincronizzazione.PARZIALE)
        self.assertTrue(DocumentoFornitore.objects.filter(numero_documento="NO-SCOPE-1").exists())
        self.assertTrue(any("lettura dei fornitori" in message for message in stats["messaggi"]))

    @patch("gestione_finanziaria.fatture_in_cloud_xml.requests.get")
    @patch("gestione_finanziaria.fatture_in_cloud.FattureInCloudClient")
    def test_sincronizza_fatture_in_cloud_arricchisce_fornitore_da_xml_allegato_pending(
        self,
        mock_client_class,
        mock_requests_get,
    ):
        connessione = FattureInCloudConnessione.objects.create(
            nome="FIC",
            company_id=123,
            sincronizza_documenti_registrati=False,
            sincronizza_documenti_da_registrare=True,
        )
        client = Mock()

        def list_pending(doc_type, *, page=1, per_page=50):
            if doc_type == "agyo":
                return {"data": [{"id": 998}], "pagination": {"current_page": 1, "last_page": 1}}
            return {"data": [], "pagination": {"current_page": 1, "last_page": 1}}

        client.list_pending_received_documents.side_effect = list_pending
        client.get_pending_received_document.return_value = {
            "id": 998,
            "type": "agyo",
            "document_type": "invoice",
            "ei_number": "42",
            "supplier_name": "Fornitore da XML",
            "subject": "Documento pending con XML",
            "filename": "fattura.xml",
            "attachment_url": "https://fic.example.test/download/998",
            "emission_date": "2026-05-04",
            "amount_net": "100.00",
            "amount_vat": "22.00",
            "amount_gross": "122.00",
            "payments_list": [{"due_date": "2026-06-04", "amount": "122.00"}],
        }
        mock_client_class.return_value = client
        xml = b"""<?xml version="1.0" encoding="UTF-8"?>
<FatturaElettronica>
  <FatturaElettronicaHeader>
    <CedentePrestatore>
      <DatiAnagrafici>
        <IdFiscaleIVA><IdPaese>IT</IdPaese><IdCodice>12345678901</IdCodice></IdFiscaleIVA>
        <CodiceFiscale>12345678901</CodiceFiscale>
        <Anagrafica><Nome>Mario</Nome><Cognome>Rossi</Cognome></Anagrafica>
      </DatiAnagrafici>
      <Sede><Indirizzo>Via Completa 9</Indirizzo><CAP>40100</CAP><Comune>Bologna</Comune><Provincia>BO</Provincia></Sede>
      <Contatti><Email>fornitore.xml@example.com</Email></Contatti>
    </CedentePrestatore>
  </FatturaElettronicaHeader>
</FatturaElettronica>"""
        attachment_response = Mock(status_code=200, headers={"Content-Type": "text/xml"})
        attachment_response.iter_content.return_value = [xml]
        mock_requests_get.return_value = attachment_response

        stats = sincronizza_fatture_in_cloud(connessione, utente=self.user)

        self.assertEqual(stats["creati"], 1)
        self.assertEqual(stats["fornitori_creati"], 1)
        self.assertEqual(stats["fornitori_aggiornati"], 0)
        fornitore = Fornitore.objects.get(denominazione="Fornitore da XML")
        self.assertEqual(fornitore.partita_iva, "12345678901")
        self.assertEqual(fornitore.codice_fiscale, "12345678901")
        self.assertEqual(fornitore.indirizzo, "Via Completa 9 40100 Bologna BO")
        self.assertEqual(fornitore.email, "fornitore.xml@example.com")
        documento = DocumentoFornitore.objects.get(external_id="998")
        self.assertEqual(documento.fornitore, fornitore)
        self.assertEqual(documento.scadenze.get().data_scadenza, date(2026, 6, 4))
        mock_requests_get.assert_called_once()

    @patch("gestione_finanziaria.management.commands.debug_fatture_in_cloud_payload.FattureInCloudClient")
    def test_debug_fatture_in_cloud_payload_maschera_dati_sensibili(self, mock_client_class):
        connessione = FattureInCloudConnessione.objects.create(nome="FIC", company_id=123)
        client = Mock()
        client.get_received_document.return_value = {
            "id": 997,
            "entity": {"id": 77, "name": "Fornitore Segreto Srl"},
            "e_invoice": {
                "FatturaElettronicaHeader": {
                    "CedentePrestatore": {
                        "DatiAnagrafici": {
                            "IdFiscaleIVA": {"IdCodice": "12345678901"},
                            "Anagrafica": {"Denominazione": "Ragione Segreta Srl"},
                        },
                        "Sede": {"Indirizzo": "Via Segreta 1", "Comune": "Bologna"},
                    }
                }
            },
            "payments_list": [{"iban": "IT60X0000000000000000000000"}],
        }
        mock_client_class.return_value = client
        output = StringIO()

        call_command(
            "debug_fatture_in_cloud_payload",
            "--connessione",
            str(connessione.pk),
            "--document-id",
            "997",
            stdout=output,
        )

        text = output.getvalue()
        self.assertNotIn("Fornitore Segreto", text)
        self.assertNotIn("Ragione Segreta", text)
        self.assertNotIn("Via Segreta", text)
        self.assertNotIn("12345678901", text)
        self.assertNotIn("IT60X", text)
        report = json.loads(text)
        self.assertTrue(report["entity_supplier_fields_present"]["name"])
        self.assertTrue(report["e_invoice_supplier_fields_present"]["vat_number"])
        self.assertTrue(report["e_invoice_supplier_fields_present"]["address_street"])
        self.assertTrue(report["supplier_payment_fields_present"]["bank_iban"])

    @patch("gestione_finanziaria.views.FattureInCloudClient")
    def test_diagnostica_payload_fatture_in_cloud_via_browser_maschera_dati(self, mock_client_class):
        self.user.is_superuser = True
        self.user.save(update_fields=["is_superuser"])
        connessione = FattureInCloudConnessione.objects.create(nome="FIC", company_id=123)
        fornitore = Fornitore.objects.create(denominazione="Fornitore Gia Importato", tipo_soggetto="azienda")
        documento = DocumentoFornitore.objects.create(
            fornitore=fornitore,
            numero_documento="FIC-1",
            data_documento=date(2026, 5, 4),
            totale=Decimal("100.00"),
            origine=OrigineDocumentoFornitore.FATTURE_IN_CLOUD,
            external_source="fatture_in_cloud",
            external_id="997",
        )
        client = Mock()
        client.get_received_document.return_value = {
            "id": 997,
            "entity": {"id": 77, "name": "Fornitore Segreto Srl"},
            "e_invoice": {
                "FatturaElettronicaHeader": {
                    "CedentePrestatore": {
                        "DatiAnagrafici": {
                            "IdFiscaleIVA": {"IdCodice": "12345678901"},
                            "Anagrafica": {"Denominazione": "Ragione Segreta Srl"},
                        },
                        "Sede": {"Indirizzo": "Via Segreta 1", "Comune": "Bologna"},
                    }
                }
            },
        }
        mock_client_class.return_value = client

        response = self.client.post(
            reverse("diagnostica_payload_fatture_in_cloud", kwargs={"pk": connessione.pk}),
            {"documento_fornitore": str(documento.pk), "source_type": "registered"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Report mascherato")
        self.assertContains(response, "e_invoice_supplier_fields_present")
        self.assertNotContains(response, "Fornitore Segreto")
        self.assertNotContains(response, "Ragione Segreta")
        self.assertNotContains(response, "Via Segreta")
        self.assertNotContains(response, "12345678901")
        client.get_received_document.assert_called_once_with("997")

    def test_diagnostica_payload_fatture_in_cloud_riservata_admin(self):
        connessione = FattureInCloudConnessione.objects.create(nome="FIC", company_id=123)

        response = self.client.get(reverse("diagnostica_payload_fatture_in_cloud", kwargs={"pk": connessione.pk}))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("modifica_fatture_in_cloud", kwargs={"pk": connessione.pk}))

    @patch("gestione_finanziaria.fatture_in_cloud_xml.requests.get")
    @patch("gestione_finanziaria.views.FattureInCloudClient")
    def test_diagnostica_payload_fatture_in_cloud_analizza_allegato_xml_mascherato(
        self,
        mock_client_class,
        mock_requests_get,
    ):
        self.user.is_superuser = True
        self.user.save(update_fields=["is_superuser"])
        connessione = FattureInCloudConnessione.objects.create(nome="FIC", company_id=123)
        client = Mock()
        client.get_pending_received_document.return_value = {
            "id": 998,
            "supplier_name": "Nome Visibile Solo Nel Payload Reale",
            "attachment_url": "https://fic.example.test/download/998",
            "filename": "fattura-segreta.xml",
        }
        mock_client_class.return_value = client
        xml = b"""<?xml version="1.0" encoding="UTF-8"?>
<FatturaElettronica>
  <FatturaElettronicaHeader>
    <CedentePrestatore>
      <DatiAnagrafici>
        <IdFiscaleIVA><IdPaese>IT</IdPaese><IdCodice>12345678901</IdCodice></IdFiscaleIVA>
        <CodiceFiscale>12345678901</CodiceFiscale>
        <Anagrafica><Denominazione>Ragione Segreta Srl</Denominazione></Anagrafica>
      </DatiAnagrafici>
      <Sede><Indirizzo>Via Segreta 1</Indirizzo><CAP>40100</CAP><Comune>Bologna</Comune><Provincia>BO</Provincia></Sede>
      <Contatti><Telefono>051123456</Telefono><Email>segreta@example.com</Email></Contatti>
    </CedentePrestatore>
  </FatturaElettronicaHeader>
</FatturaElettronica>"""
        attachment_response = Mock(status_code=200, headers={"Content-Type": "application/xml"})
        attachment_response.iter_content.return_value = [xml]
        mock_requests_get.return_value = attachment_response

        response = self.client.post(
            reverse("diagnostica_payload_fatture_in_cloud", kwargs={"pk": connessione.pk}),
            {"document_id": "998", "source_type": "pending"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "attachment_analysis")
        self.assertContains(response, "xml_detected")
        self.assertContains(response, "cedente_prestatore_detected")
        self.assertContains(response, "attachment_supplier_fields_present")
        self.assertNotContains(response, "Ragione Segreta")
        self.assertNotContains(response, "Via Segreta")
        self.assertNotContains(response, "12345678901")
        self.assertNotContains(response, "segreta@example.com")
        mock_requests_get.assert_called_once()
        client.get_pending_received_document.assert_called_once_with("998")

    @override_settings(
        FATTURE_IN_CLOUD_API_CONNECT_TIMEOUT_SECONDS=2,
        FATTURE_IN_CLOUD_API_READ_TIMEOUT_SECONDS=6,
    )
    @patch("gestione_finanziaria.fatture_in_cloud.requests.request")
    def test_fatture_in_cloud_client_usa_timeout_api_breve(self, mock_request):
        connessione = FattureInCloudConnessione.objects.create(nome="FIC", company_id=123)
        response = Mock(status_code=200, content=b"{}", text="{}")
        response.json.return_value = {}
        mock_request.return_value = response
        client = FattureInCloudClient(connessione)
        client._headers = Mock(return_value={})

        client.request("GET", "/test")

        self.assertEqual(mock_request.call_args.kwargs["timeout"], (2.0, 6.0))

    @patch("gestione_finanziaria.fatture_in_cloud.FattureInCloudClient")
    def test_sincronizza_fatture_in_cloud_restituisce_parziale_su_errore_dettaglio(self, mock_client_class):
        connessione = FattureInCloudConnessione.objects.create(
            nome="FIC",
            company_id=123,
            sincronizza_documenti_registrati=False,
            sincronizza_documenti_da_registrare=True,
        )
        client = Mock()

        def list_pending(doc_type, *, page=1, per_page=50):
            if doc_type == "agyo":
                return {"data": [{"id": 992}], "pagination": {"current_page": 1, "last_page": 1}}
            return {"data": [], "pagination": {"current_page": 1, "last_page": 1}}

        client.list_pending_received_documents.side_effect = list_pending
        client.get_pending_received_document.side_effect = FattureInCloudError("Timeout Fatture in Cloud")
        mock_client_class.return_value = client

        stats = sincronizza_fatture_in_cloud(connessione, utente=self.user)

        self.assertEqual(stats["esito"], EsitoSincronizzazione.PARZIALE)
        self.assertEqual(stats["creati"], 0)
        self.assertIn("documento 992", stats["messaggi"][0])
        connessione.refresh_from_db()
        self.assertEqual(connessione.ultimo_esito, EsitoSincronizzazione.PARZIALE)

    @patch("gestione_finanziaria.fatture_in_cloud.FattureInCloudClient")
    def test_sincronizza_fatture_in_cloud_pending_usa_tipi_sorgente_fic(self, mock_client_class):
        connessione = FattureInCloudConnessione.objects.create(
            nome="FIC",
            company_id=123,
            sincronizza_documenti_registrati=False,
            sincronizza_documenti_da_registrare=True,
        )
        client = Mock()
        client.list_pending_received_documents.return_value = {
            "data": [],
            "pagination": {"current_page": 1, "last_page": 1},
        }
        mock_client_class.return_value = client

        stats = sincronizza_fatture_in_cloud(connessione, utente=self.user)

        self.assertEqual(stats["esito"], EsitoSincronizzazione.OK)
        called_types = [
            call.args[0]
            for call in client.list_pending_received_documents.call_args_list
        ]
        self.assertEqual(called_types, ["agyo", "mail", "browser"])
        client.get_pending_received_document.assert_not_called()

    def test_fatture_in_cloud_connessione_puo_essere_rimossa(self):
        connessione = FattureInCloudConnessione.objects.create(
            nome="FIC da rifare",
            company_id=123,
            access_token_cifrato="token-cifrato",
            refresh_token_cifrato="refresh-cifrato",
        )
        FattureInCloudSyncLog.objects.create(
            connessione=connessione,
            esito=EsitoSincronizzazione.OK,
            documenti_creati=2,
        )
        delete_url = reverse("elimina_fatture_in_cloud", kwargs={"pk": connessione.pk})

        response = self.client.get(reverse("modifica_fatture_in_cloud", kwargs={"pk": connessione.pk}))
        self.assertContains(response, delete_url)
        self.assertContains(response, "Rimuovi connessione")

        confirm_response = self.client.get(delete_url)
        self.assertEqual(confirm_response.status_code, 200)
        self.assertContains(confirm_response, "fatture fornitori")
        self.assertContains(confirm_response, "Rimuovi connessione")

        response = self.client.post(delete_url)

        self.assertRedirects(response, reverse("lista_fatture_in_cloud"))
        self.assertFalse(FattureInCloudConnessione.objects.filter(pk=connessione.pk).exists())
        log = FattureInCloudSyncLog.objects.get()
        self.assertIsNone(log.connessione)

    @patch("gestione_finanziaria.fatture_in_cloud.FattureInCloudClient")
    @patch("gestione_finanziaria.fatture_in_cloud.time.monotonic")
    def test_sincronizza_fatture_in_cloud_si_interrompe_prima_del_timeout_worker(
        self,
        mock_monotonic,
        mock_client_class,
    ):
        connessione = FattureInCloudConnessione.objects.create(
            nome="FIC",
            company_id=123,
            sincronizza_documenti_registrati=True,
            sincronizza_documenti_da_registrare=True,
        )
        mock_monotonic.side_effect = [0, 30, 30]
        mock_client_class.return_value = Mock()

        stats = sincronizza_fatture_in_cloud(connessione, utente=self.user, max_seconds=10)

        self.assertEqual(stats["esito"], EsitoSincronizzazione.PARZIALE)
        self.assertTrue(stats["interrotta_per_tempo"])
        self.assertIn("Tempo massimo", stats["messaggi"][0])
        mock_client_class.return_value.list_received_documents.assert_not_called()
        connessione.refresh_from_db()
        self.assertEqual(connessione.ultimo_esito, EsitoSincronizzazione.PARZIALE)

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

    def test_annulla_pagamento_fornitore_rende_movimento_riconciliabile(self):
        fornitore = Fornitore.objects.create(denominazione="Energia Srl", tipo_soggetto="azienda")
        documento = DocumentoFornitore.objects.create(
            fornitore=fornitore,
            tipo_documento=TipoDocumentoFornitore.FATTURA,
            numero_documento="E-002",
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
            descrizione="Bonifico Energia Srl fattura E-002",
            controparte="Energia Srl",
            stato_riconciliazione=StatoRiconciliazione.NON_RICONCILIATO,
        )
        pagamento = riconcilia_movimento_con_scadenza_fornitore(movimento, scadenza, utente=self.user)

        annulla_pagamento_fornitore(pagamento)

        movimento.refresh_from_db()
        scadenza.refresh_from_db()
        documento.refresh_from_db()
        self.assertEqual(movimento.stato_riconciliazione, StatoRiconciliazione.NON_RICONCILIATO)
        self.assertEqual(importo_movimento_disponibile_fornitori(movimento), Decimal("122.00"))
        self.assertEqual(scadenza.importo_pagato, Decimal("0.00"))
        self.assertNotEqual(documento.stato, StatoDocumentoFornitore.PAGATO)
        self.assertEqual(PagamentoFornitore.objects.count(), 0)

    def test_anteprima_riconciliazione_fornitori_non_scrive_prima_della_conferma(self):
        fornitore = Fornitore.objects.create(denominazione="Energia Srl", tipo_soggetto="azienda")
        documento = DocumentoFornitore.objects.create(
            fornitore=fornitore,
            tipo_documento=TipoDocumentoFornitore.FATTURA,
            numero_documento="E-003",
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
            descrizione="Bonifico Energia Srl fattura E-003",
            controparte="Energia Srl",
            stato_riconciliazione=StatoRiconciliazione.NON_RICONCILIATO,
        )

        preview = anteprima_riconcilia_fornitori_automaticamente()

        movimento.refresh_from_db()
        scadenza.refresh_from_db()
        self.assertEqual(preview["stats"]["proposti"], 1)
        self.assertEqual(movimento.stato_riconciliazione, StatoRiconciliazione.NON_RICONCILIATO)
        self.assertEqual(scadenza.importo_pagato, Decimal("0.00"))

        risultato = applica_anteprima_riconciliazione_fornitori(
            preview["dettagli"],
            [preview["dettagli"][0]["key"]],
            utente=self.user,
        )

        movimento.refresh_from_db()
        scadenza.refresh_from_db()
        self.assertEqual(risultato["stats"]["riconciliati"], 1)
        self.assertEqual(movimento.stato_riconciliazione, StatoRiconciliazione.RICONCILIATO)
        self.assertEqual(scadenza.importo_pagato, Decimal("122.00"))

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
        ScadenzaPagamentoFornitore.objects.create(
            documento=documento,
            data_scadenza=date(2026, 5, 31),
            importo_previsto=Decimal("61.00"),
        )

        urls = [
            reverse("dashboard_gestione_finanziaria"),
            reverse("lista_fornitori"),
            reverse("modifica_fornitore", kwargs={"pk": fornitore.pk}),
            reverse("lista_documenti_fornitori"),
            reverse("modifica_documento_fornitore", kwargs={"pk": documento.pk}),
            reverse("scadenziario_fornitori"),
            reverse("fatture_scadenze_fornitori"),
        ]

        for url in urls:
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200, url)

        response = self.client.get(reverse("lista_documenti_fornitori"))
        self.assertContains(response, "Fatture fornitori")
        self.assertContains(response, "Data di scadenza")
        self.assertContains(response, "31/05/2026")
        self.assertContains(response, f'{reverse("modifica_documento_fornitore", kwargs={"pk": documento.pk})}?popup=1')
        self.assertContains(response, 'data-live-list-form')
        self.assertContains(response, 'data-live-list-input')
        self.assertContains(response, 'id="documenti-fornitori-results"')
        self.assertContains(response, 'title="Seleziona tutto"')
        self.assertNotContains(response, ">Seleziona Tutto<")
        self.assertContains(response, "live-list-search.js")

    def test_fatture_scadenze_fornitori_fonde_fatture_e_scadenziario(self):
        categoria = crea_categoria_spesa_test("Servizi")
        fornitore = Fornitore.objects.create(
            denominazione="Fusioni Srl",
            tipo_soggetto="azienda",
            categoria_spesa=categoria,
        )
        documento_da_pagare = DocumentoFornitore.objects.create(
            fornitore=fornitore,
            numero_documento="FUS-1",
            data_documento=date(2026, 5, 1),
            descrizione="Canone sede",
            imponibile=Decimal("100.00"),
            iva=Decimal("22.00"),
            totale=Decimal("122.00"),
            stato=StatoDocumentoFornitore.DA_PAGARE,
        )
        scadenza_da_pagare = ScadenzaPagamentoFornitore.objects.create(
            documento=documento_da_pagare,
            data_scadenza=date(2020, 1, 31),
            importo_previsto=Decimal("122.00"),
            importo_pagato=Decimal("0.00"),
        )
        documento_pagato = DocumentoFornitore.objects.create(
            fornitore=fornitore,
            numero_documento="FUS-2",
            data_documento=date(2026, 5, 2),
            descrizione="Materiali",
            imponibile=Decimal("50.00"),
            iva=Decimal("0.00"),
            totale=Decimal("50.00"),
            stato=StatoDocumentoFornitore.PAGATO,
        )
        ScadenzaPagamentoFornitore.objects.create(
            documento=documento_pagato,
            data_scadenza=date(2026, 5, 31),
            importo_previsto=Decimal("50.00"),
            importo_pagato=Decimal("50.00"),
        )

        response = self.client.get(reverse("fatture_scadenze_fornitori"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Fatture e scadenze")
        self.assertContains(response, "Tutte le fatture")
        self.assertContains(response, "Solo fatture insolute")
        self.assertContains(response, f'{reverse("fatture_scadenze_fornitori")}?vista=insolute')
        self.assertContains(response, "Totale previsto")
        self.assertContains(response, "Totale pagato")
        self.assertContains(response, "Totale residuo")
        self.assertContains(response, "<th>Scadenza</th>", html=False)
        self.assertContains(response, "<th>Fornitore</th>", html=False)
        self.assertContains(response, "<th>Categoria</th>", html=False)
        self.assertContains(response, "Previsto")
        self.assertContains(response, "Pagato")
        self.assertContains(response, "Residuo")
        self.assertNotContains(response, "<th>Fattura</th>", html=False)
        self.assertNotContains(response, "<th>IVA</th>", html=False)
        self.assertContains(response, "Da pagare")
        self.assertContains(response, "Pagata")
        self.assertContains(response, "Scaduta")
        self.assertContains(response, "supplier-invoice-row-unpaid", count=1)
        self.assertContains(response, "supplier-invoice-row-paid", count=1)
        self.assertContains(
            response,
            f'data-row-popup-url="{reverse("modifica_documento_fornitore", kwargs={"pk": documento_da_pagare.pk})}?popup=1"',
        )
        pagamento_url = (
            f"{reverse('registra_pagamento_scadenza_fornitore', kwargs={'pk': scadenza_da_pagare.pk})}"
            f"?popup=1&reload_url={reverse('fatture_scadenze_fornitori')}"
        )
        self.assertContains(response, "Registra pagamento")
        self.assertContains(response, pagamento_url)

        response = self.client.get(reverse("fatture_scadenze_fornitori"), {"vista": "insolute"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["totale_previsto"], Decimal("172.00"))
        self.assertEqual(response.context["totale_pagato"], Decimal("50.00"))
        self.assertEqual(response.context["totale_residuo"], Decimal("122.00"))
        self.assertContains(response, "Solo fatture insolute")
        self.assertContains(response, "supplier-invoice-row-unpaid", count=1)
        self.assertNotContains(response, "supplier-invoice-row-paid")
        self.assertNotContains(response, "Materiali")

    def test_spese_mensili_dashboard_unisce_fatture_spese_e_introiti(self):
        categoria = crea_categoria_spesa_test("Servizi generali")
        fornitore = Fornitore.objects.create(
            denominazione="Supermercato Verde",
            tipo_soggetto="azienda",
            categoria_spesa=categoria,
        )
        documento = DocumentoFornitore.objects.create(
            fornitore=fornitore,
            numero_documento="MAG-1",
            data_documento=date(2026, 5, 3),
            descrizione="Materiale didattico",
            imponibile=Decimal("100.00"),
            iva=Decimal("22.00"),
            totale=Decimal("122.00"),
            stato=StatoDocumentoFornitore.DA_PAGARE,
        )
        ScadenzaPagamentoFornitore.objects.create(
            documento=documento,
            data_scadenza=date(2026, 5, 31),
            importo_previsto=Decimal("122.00"),
            importo_pagato=Decimal("0.00"),
        )
        SpesaOperativa.objects.create(
            tipo=TipoSpesaOperativa.CONTANTI,
            descrizione="Spesa supermercato",
            categoria=categoria,
            fornitore=fornitore,
            data_scadenza=date(2026, 5, 12),
            importo_previsto=Decimal("48.50"),
            importo_pagato=Decimal("48.50"),
        )
        SpesaOperativa.objects.create(
            tipo=TipoSpesaOperativa.F24,
            descrizione="F24 contributi maggio",
            categoria=categoria,
            data_scadenza=date(2026, 5, 16),
            importo_previsto=Decimal("300.00"),
            importo_pagato=Decimal("120.00"),
        )
        MovimentoFinanziario.objects.create(
            data_contabile=date(2026, 5, 20),
            importo=Decimal("850.00"),
            descrizione="Incasso rette maggio",
            controparte="Famiglie",
            origine=OrigineMovimento.BANCA,
        )

        response = self.client.get(
            reverse("spese_mensili_dashboard"),
            {"periodo": "solare", "anno": "2026", "mese": "2026-05"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Spese mensili")
        self.assertContains(response, "Mag 2026")
        self.assertContains(response, "Materiale didattico")
        self.assertContains(response, "Spesa supermercato")
        self.assertContains(response, "F24 contributi maggio")
        self.assertContains(response, "Incasso rette maggio")
        self.assertContains(response, "Introiti 850,00")
        selected_month = next(month for month in response.context["month_stats"] if month["key"] == "2026-05")
        self.assertEqual(selected_month["totale_spese"], Decimal("470.50"))
        self.assertEqual(selected_month["residuo"], Decimal("302.00"))
        self.assertEqual(selected_month["spese_count"], 3)
        self.assertEqual(selected_month["insolute_count"], 2)
        self.assertContains(response, "supplier-invoice-row-unpaid", count=2)
        self.assertContains(response, "supplier-invoice-row-paid", count=1)

        response = self.client.get(
            reverse("spese_mensili_dashboard"),
            {"periodo": "solare", "anno": "2026", "mese": "2026-05", "vista": "insolute"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Materiale didattico")
        self.assertContains(response, "F24 contributi maggio")
        self.assertNotContains(response, "Spesa supermercato")

    def test_crea_piano_rateale_spesa_genera_rate(self):
        categoria = crea_categoria_spesa_test("Finanziamenti")

        response = self.client.post(
            reverse("crea_piano_rateale_spesa"),
            {
                "tipo": TipoPianoRatealeSpesa.FINANZIAMENTO,
                "descrizione": "Finanziamento cucina",
                "categoria": categoria.pk,
                "fornitore": "",
                "importo_totale": "100.00",
                "numero_rate": "3",
                "frequenza_mesi": "1",
                "data_prima_scadenza": "2026-05-31",
                "giorno_scadenza": "31",
                "note": "",
            },
        )

        self.assertEqual(response.status_code, 302)
        piano = PianoRatealeSpesa.objects.get(descrizione="Finanziamento cucina")
        rate = list(piano.rate.order_by("numero_rata"))
        self.assertEqual(len(rate), 3)
        self.assertEqual([rata.importo_previsto for rata in rate], [Decimal("33.33"), Decimal("33.33"), Decimal("33.34")])
        self.assertEqual([rata.data_scadenza for rata in rate], [date(2026, 5, 31), date(2026, 6, 30), date(2026, 7, 31)])
        self.assertEqual(rate[0].tipo, TipoSpesaOperativa.FINANZIAMENTO)

    def test_lista_documenti_fornitori_mostra_riepilogo_e_colori_stato(self):
        fornitore = Fornitore.objects.create(
            denominazione="Riepilogo Srl",
            tipo_soggetto="azienda",
        )
        DocumentoFornitore.objects.create(
            fornitore=fornitore,
            numero_documento="APER-1",
            data_documento=date(2026, 5, 1),
            imponibile=Decimal("100.00"),
            iva=Decimal("22.00"),
            totale=Decimal("122.00"),
            stato=StatoDocumentoFornitore.DA_PAGARE,
        )
        documento_parziale = DocumentoFornitore.objects.create(
            fornitore=fornitore,
            numero_documento="PARZ-1",
            data_documento=date(2026, 5, 2),
            imponibile=Decimal("200.00"),
            iva=Decimal("0.00"),
            totale=Decimal("200.00"),
            stato=StatoDocumentoFornitore.PARZIALMENTE_PAGATO,
        )
        documento_pagato = DocumentoFornitore.objects.create(
            fornitore=fornitore,
            numero_documento="PAG-1",
            data_documento=date(2026, 5, 3),
            imponibile=Decimal("80.00"),
            iva=Decimal("0.00"),
            totale=Decimal("80.00"),
            stato=StatoDocumentoFornitore.PAGATO,
        )
        ScadenzaPagamentoFornitore.objects.create(
            documento=documento_parziale,
            data_scadenza=date(2026, 5, 31),
            importo_previsto=Decimal("200.00"),
            importo_pagato=Decimal("50.00"),
        )
        ScadenzaPagamentoFornitore.objects.create(
            documento=documento_pagato,
            data_scadenza=date(2026, 5, 31),
            importo_previsto=Decimal("80.00"),
            importo_pagato=Decimal("80.00"),
        )

        response = self.client.get(reverse("lista_documenti_fornitori"))

        self.assertEqual(response.context["totale_documenti_non_saldati"], Decimal("272.00"))
        self.assertEqual(response.context["numero_documenti_non_saldati"], 2)
        self.assertContains(response, "Totale fatture non saldate")
        self.assertContains(response, "272,00")
        self.assertContains(response, "supplier-invoice-row-unpaid", count=2)
        self.assertContains(response, "supplier-invoice-row-paid", count=1)

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
        self.assertContains(response, "Elimina fatture fornitori")
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

    def test_excel_autodetect_parses_movements(self):
        from openpyxl import Workbook

        workbook = Workbook()
        sheet = workbook.active
        sheet.append(["Data", "Data valuta", "Importo", "Descrizione", "ID transazione"])
        sheet.append([date(2026, 4, 24), date(2026, 4, 24), 315.50, "Bonifico retta Rossi", "TX-1"])
        sheet.append([date(2026, 4, 25), date(2026, 4, 25), -12.40, "Commissione banca", "TX-2"])
        buffer = BytesIO()
        workbook.save(buffer)
        raw_excel = buffer.getvalue()

        detection = detect_excel_import_config(raw_excel)

        self.assertEqual(detection.formato_rilevato, "Excel")
        self.assertEqual(detection.config.colonna_data_contabile, "data")
        self.assertEqual(detection.config.colonna_importo, "importo")

        movimenti = list(ExcelImporter(detection.config).parse(raw_excel))

        self.assertEqual(len(movimenti), 2)
        self.assertEqual(movimenti[0].data_contabile, date(2026, 4, 24))
        self.assertEqual(movimenti[0].importo, Decimal("315.50"))
        self.assertIn("Rossi", movimenti[0].descrizione)
        self.assertEqual(movimenti[0].provider_transaction_id, "TX-1")
        self.assertEqual(movimenti[1].importo, Decimal("-12.40"))

    def test_excel_html_xls_autodetect_parses_movements(self):
        raw_excel = (
            "<html><body><table>"
            "<tr><th>Data</th><th>Importo</th><th>Descrizione</th></tr>"
            "<tr><td>02/05/2026</td><td>98,40</td><td>Incasso mensa</td></tr>"
            "<tr><td>03/05/2026</td><td>-15,20</td><td>Commissione</td></tr>"
            "</table></body></html>"
        ).encode("utf-8")

        detection = detect_excel_import_config(raw_excel)
        movimenti = list(ExcelImporter(detection.config).parse(raw_excel))

        self.assertEqual(detection.formato_rilevato, "Excel")
        self.assertEqual(len(movimenti), 2)
        self.assertEqual(movimenti[0].data_contabile, date(2026, 5, 2))
        self.assertEqual(movimenti[0].importo, Decimal("98.40"))
        self.assertIn("mensa", movimenti[0].descrizione)
        self.assertEqual(movimenti[1].importo, Decimal("-15.20"))

    def test_excel_unicredit_two_line_header_autodetect_parses_movements(self):
        from openpyxl import Workbook

        workbook = Workbook()
        sheet = workbook.active
        sheet.append(["Rapporto IT 40 A 02008 13030 000107342804 - SCUOLA TEST"])
        sheet.append(["Data", "", "Descrizione", "EUR", "Caus."])
        sheet.append(["Operaz.", "Valuta"])
        sheet.append(["03/12/2025", "03/12/2025", "EROGAZIONE FINANZIAMENTO", "39800", "061"])
        sheet.append(["04/12/2025", "04/12/2025", "DISPOSIZIONE DI BONIFICO", "-15005,75", "208"])
        buffer = BytesIO()
        workbook.save(buffer)
        raw_excel = buffer.getvalue()

        detection = detect_excel_import_config(raw_excel)
        movimenti = list(ExcelImporter(detection.config).parse(raw_excel))

        self.assertEqual(detection.formato_rilevato, "Excel UniCredit")
        self.assertEqual(detection.config.righe_da_saltare, 3)
        self.assertFalse(detection.config.ha_intestazione)
        self.assertEqual(detection.config.colonna_data_contabile, 0)
        self.assertEqual(detection.config.colonna_data_valuta, 1)
        self.assertEqual(detection.config.colonna_importo, 3)
        self.assertEqual(detection.abi, "02008")
        self.assertEqual(detection.cab, "13030")
        self.assertEqual(detection.numero_conto, "000107342804")
        self.assertEqual(len(movimenti), 2)
        self.assertEqual(movimenti[0].data_contabile, date(2025, 12, 3))
        self.assertEqual(movimenti[0].data_valuta, date(2025, 12, 3))
        self.assertEqual(movimenti[0].importo, Decimal("39800"))
        self.assertEqual(movimenti[1].importo, Decimal("-15005.75"))

    def test_import_estratto_conto_preview_and_confirm_with_xlsx(self):
        from openpyxl import Workbook

        provider = ProviderBancario.objects.create(
            nome="Import Excel test",
            tipo=TipoProviderBancario.IMPORT_FILE,
        )
        conto = ContoBancario.objects.create(
            nome_conto="Conto Excel",
            iban="IT00X0503437060000000003228",
            provider=provider,
            attivo=True,
        )
        workbook = Workbook()
        sheet = workbook.active
        sheet.append(["Data", "Data valuta", "Importo", "Descrizione", "ID transazione"])
        sheet.append([date(2026, 5, 1), date(2026, 5, 1), 120.75, "Bonifico laboratorio", "XLSX-1"])
        buffer = BytesIO()
        workbook.save(buffer)
        uploaded = SimpleUploadedFile(
            "movimenti_unicredit.xlsx",
            buffer.getvalue(),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
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
        self.assertContains(preview_response, "Excel")
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
        movimento = MovimentoFinanziario.objects.get(conto=conto)
        self.assertEqual(movimento.importo, Decimal("120.75"))
        self.assertIn("laboratorio", movimento.descrizione)

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

    @skip("Legacy test basato sulla tabella anagrafica.Famiglia rimossa.")
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

    @skip("Legacy test basato sulla tabella anagrafica.Famiglia rimossa.")
    def test_import_movimenti_riconcilia_pagamento_cumulativo_rette(self):
        provider = ProviderBancario.objects.create(
            nome="Import rette cumulative test",
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
            mese_prima_retta=9,
            giorno_scadenza_rate=10,
        )
        TariffaCondizioneIscrizione.objects.create(
            condizione_iscrizione=condizione,
            ordine_figlio_da=1,
            retta_annuale=Decimal("1000.00"),
            preiscrizione=Decimal("0.00"),
        )
        iscrizioni = []
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
            self.assertEqual(iscrizione.sync_rate_schedule(), "created")
            iscrizioni.append(iscrizione)

        rate = [
            iscrizione.rate.get(tipo_rata=RataIscrizione.TIPO_MENSILE, numero_rata=1)
            for iscrizione in iscrizioni
        ]
        raw_csv = (
            "Data;Importo;Descrizione\n"
            "10/09/2025;200,00;Bonifico rette settembre Luca e Marta Rossi\n"
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
            nome_file="rette-cumulative.csv",
        )

        self.assertEqual(risultato.inseriti, 1)
        self.assertEqual(risultato.riconciliati, 1)
        movimento = MovimentoFinanziario.objects.get(conto=conto)
        movimento.refresh_from_db()
        self.assertEqual(movimento.stato_riconciliazione, StatoRiconciliazione.RICONCILIATO)
        self.assertIsNone(movimento.rata_iscrizione_id)
        self.assertEqual(movimento.riconciliazioni_rate.count(), 2)
        for rata in rate:
            rata.refresh_from_db()
            self.assertTrue(rata.pagata)
            self.assertEqual(rata.importo_pagato, Decimal("100.00"))
            self.assertEqual(rata.data_pagamento, date(2025, 9, 10))

    @skip("Legacy test basato sulla tabella anagrafica.Famiglia rimossa.")
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
