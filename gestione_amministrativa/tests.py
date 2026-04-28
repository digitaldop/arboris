from datetime import date
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from sistema.models import LivelloPermesso, SistemaUtentePermessi

from .models import (
    BustaPagaDipendente,
    ContrattoDipendente,
    Dipendente,
    ScenarioValorePayroll,
    SimulazioneCostoDipendente,
    TipoContrattoDipendente,
    VoceBustaPaga,
)
from .services import crea_o_aggiorna_previsione_busta_paga


class SimulazioneCostoDipendenteTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="admin", password="test")
        SistemaUtentePermessi.objects.create(
            user=self.user,
            permesso_gestione_amministrativa=LivelloPermesso.GESTIONE,
        )
        self.tipo_contratto = TipoContrattoDipendente.objects.create(nome="Tempo determinato")
        self.dipendente = Dipendente.objects.create(
            nome="Mario",
            cognome="Rossi",
            codice_fiscale="RSSMRA80A01H501U",
        )
        self.contratto = ContrattoDipendente.objects.create(
            dipendente=self.dipendente,
            tipo_contratto=self.tipo_contratto,
            data_inizio=date(2025, 9, 1),
            retribuzione_lorda_mensile=Decimal("1000.00"),
            mensilita_annue=Decimal("13.00"),
        )
        self.simulazione = SimulazioneCostoDipendente.objects.create(
            contratto=self.contratto,
            titolo="Simulazione consulente",
            valido_dal=date(2025, 9, 1),
            netto_mensile=Decimal("1302.00"),
            lordo_mensile=Decimal("1469.47"),
            costo_azienda_mensile=Decimal("2186.94"),
            contributi_previdenziali_azienda=Decimal("439.71"),
            contributi_assicurativi_azienda=Decimal("8.59"),
            contributi_previdenziali_dipendente=Decimal("140.95"),
            trattamento_fine_rapporto=Decimal("101.40"),
            costo_mensilita_aggiuntive=Decimal("167.77"),
            mensilita_annue=Decimal("13.00"),
            attiva=True,
        )

    def test_previsione_busta_usa_simulazione_costo_attiva(self):
        busta = crea_o_aggiorna_previsione_busta_paga(self.dipendente, 2025, 9)

        self.assertIsInstance(busta, BustaPagaDipendente)
        self.assertEqual(busta.contratto, self.contratto)
        self.assertEqual(busta.lordo_previsto, Decimal("1469.47"))
        self.assertEqual(busta.netto_previsto, Decimal("1302.00"))
        self.assertEqual(busta.costo_azienda_previsto, Decimal("2186.94"))
        self.assertEqual(busta.contributi_datore_previsti, Decimal("448.30"))
        self.assertEqual(busta.contributi_dipendente_previsti, Decimal("140.95"))
        self.assertIn("simulazione costo", busta.note_previsione)

        codici = set(
            VoceBustaPaga.objects.filter(
                busta_paga=busta,
                scenario=ScenarioValorePayroll.PREVISTO,
            ).values_list("codice", flat=True)
        )
        self.assertIn("NETTO_SIM", codici)
        self.assertIn("COSTO_SIM", codici)

    def test_lista_simulazioni_costo_richiede_permesso_e_mostra_record(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse("lista_simulazioni_costo_dipendenti"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Simulazione consulente")
        self.assertContains(response, "Rossi Mario")
