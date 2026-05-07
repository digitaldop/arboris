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
    ParametroCalcoloStipendio,
    ScenarioValorePayroll,
    SimulazioneCostoDipendente,
    StatoBustaPaga,
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
        self.parametro = ParametroCalcoloStipendio.objects.create(
            nome="Standard payroll",
            valido_dal=date(2025, 9, 1),
            aliquota_contributi_datore=Decimal("30.00"),
            aliquota_contributi_dipendente=Decimal("9.00"),
            aliquota_tfr=Decimal("7.41"),
            aliquota_inail=Decimal("1.00"),
            aliquota_altri_oneri=Decimal("2.00"),
        )
        self.busta = BustaPagaDipendente.objects.create(
            dipendente=self.dipendente,
            contratto=self.contratto,
            anno=2025,
            mese=10,
            stato=StatoBustaPaga.PREVISTA,
            netto_previsto=Decimal("1302.00"),
            costo_azienda_previsto=Decimal("2186.94"),
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

    def test_lista_dipendenti_renderizza_nuovo_layout(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse("lista_dipendenti"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "ga-dipendenti-list-shell")
        self.assertContains(response, "data-ga-dipendenti-search")
        self.assertContains(response, f"{reverse('crea_dipendente')}")
        self.assertContains(response, f"{reverse('genera_previsione_busta_paga', args=[self.dipendente.pk])}")

    def test_dashboard_gestione_amministrativa_renderizza_nuovo_layout_e_tooltip(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse("dashboard_gestione_amministrativa"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "ga-admin-dashboard-shell")
        self.assertContains(response, "data-floating-text")
        self.assertContains(response, "Procedura consigliata")
        self.assertContains(response, "ga-admin-dashboard-workflow")
        self.assertContains(response, f"{reverse('modifica_busta_paga_dipendente', args=[self.busta.pk])}?popup=1")

    def test_crea_dipendente_renderizza_nuovo_layout(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse("crea_dipendente"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "ga-dipendente-form-shell")
        self.assertContains(response, "ga-dipendente-related-field")
        self.assertContains(response, 'id="add-indirizzo-btn"')
        self.assertContains(response, 'id="add-contratto-btn"')

    def test_lista_contratti_renderizza_nuovo_layout_e_popup(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse("lista_contratti_dipendenti"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "ga-contracts-list-shell")
        self.assertContains(response, "data-ga-contracts-search")
        self.assertContains(response, f"{reverse('crea_contratto_dipendente_generico')}?popup=1")
        self.assertContains(response, f"{reverse('modifica_contratto_dipendente', args=[self.contratto.pk])}?popup=1")
        self.assertContains(response, f"{reverse('elimina_contratto_dipendente', args=[self.contratto.pk])}?popup=1")
        self.assertContains(response, 'data-window-popup="1"')

    def test_contratto_popup_form_renderizza_nuovo_layout(self):
        self.client.force_login(self.user)

        response = self.client.get(f"{reverse('modifica_contratto_dipendente', args=[self.contratto.pk])}?popup=1")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "ga-contract-form-shell")
        self.assertContains(response, 'name="popup" value="1"')
        self.assertContains(response, 'id="popup-add-tipo-contratto-btn"')
        self.assertContains(response, 'id="popup-add-parametro-calcolo-btn"')

    def test_contratto_delete_popup_renderizza_nuovo_layout(self):
        self.client.force_login(self.user)

        response = self.client.get(f"{reverse('elimina_contratto_dipendente', args=[self.contratto.pk])}?popup=1")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "ga-contract-delete-shell")
        self.assertContains(response, 'name="popup" value="1"')

    def test_lista_buste_paga_renderizza_nuovo_layout_e_popup(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse("lista_buste_paga_dipendenti"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "ga-buste-list-shell")
        self.assertContains(response, "data-ga-buste-search")
        self.assertContains(response, f"{reverse('crea_busta_paga_dipendente')}?popup=1")
        self.assertContains(response, f"{reverse('modifica_busta_paga_dipendente', args=[self.busta.pk])}?popup=1")
        self.assertContains(response, f"{reverse('elimina_busta_paga_dipendente', args=[self.busta.pk])}?popup=1")

    def test_busta_paga_popup_form_renderizza_nuovo_layout(self):
        self.client.force_login(self.user)

        response = self.client.get(f"{reverse('modifica_busta_paga_dipendente', args=[self.busta.pk])}?popup=1")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "ga-busta-form-shell")
        self.assertContains(response, 'name="popup" value="1"')
        self.assertContains(response, "Periodo e dipendente")
        self.assertContains(response, "Previsione")

    def test_busta_paga_delete_popup_renderizza_nuovo_layout(self):
        self.client.force_login(self.user)

        response = self.client.get(f"{reverse('elimina_busta_paga_dipendente', args=[self.busta.pk])}?popup=1")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "ga-busta-delete-shell")
        self.assertContains(response, 'name="popup" value="1"')

    def test_lista_simulazioni_costo_renderizza_nuovo_layout_e_popup(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse("lista_simulazioni_costo_dipendenti"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "ga-simulazioni-list-shell")
        self.assertContains(response, "data-ga-simulazioni-search")
        self.assertContains(response, f"{reverse('crea_simulazione_costo_dipendente')}?popup=1")
        self.assertContains(
            response,
            f"{reverse('modifica_simulazione_costo_dipendente', args=[self.simulazione.pk])}?popup=1",
        )
        self.assertContains(
            response,
            f"{reverse('elimina_simulazione_costo_dipendente', args=[self.simulazione.pk])}?popup=1",
        )

    def test_simulazione_costo_popup_form_renderizza_nuovo_layout(self):
        self.client.force_login(self.user)

        response = self.client.get(
            f"{reverse('modifica_simulazione_costo_dipendente', args=[self.simulazione.pk])}?popup=1"
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "ga-simulazione-form-shell")
        self.assertContains(response, 'name="popup" value="1"')
        self.assertContains(response, "Riferimenti")
        self.assertContains(response, "Contributi e imposte")

    def test_simulazione_costo_delete_popup_renderizza_nuovo_layout(self):
        self.client.force_login(self.user)

        response = self.client.get(
            f"{reverse('elimina_simulazione_costo_dipendente', args=[self.simulazione.pk])}?popup=1"
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "ga-simulazione-delete-shell")
        self.assertContains(response, 'name="popup" value="1"')

    def test_lista_parametri_calcolo_renderizza_nuovo_layout_e_popup(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse("lista_parametri_calcolo_stipendi"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "ga-parametri-list-shell")
        self.assertContains(response, "data-ga-parametri-search")
        self.assertContains(response, f"{reverse('crea_parametro_calcolo_stipendio')}?popup=1")
        self.assertContains(
            response,
            f"{reverse('modifica_parametro_calcolo_stipendio', args=[self.parametro.pk])}?popup=1",
        )
        self.assertContains(
            response,
            f"{reverse('elimina_parametro_calcolo_stipendio', args=[self.parametro.pk])}?popup=1",
        )

    def test_parametro_calcolo_popup_form_renderizza_nuovo_layout(self):
        self.client.force_login(self.user)

        response = self.client.get(
            f"{reverse('modifica_parametro_calcolo_stipendio', args=[self.parametro.pk])}?popup=1"
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "ga-parametro-form-shell")
        self.assertContains(response, 'name="popup" value="1"')
        self.assertContains(response, "Periodo e identificazione")
        self.assertContains(response, "Aliquote")

    def test_parametro_calcolo_delete_popup_renderizza_nuovo_layout(self):
        self.client.force_login(self.user)

        response = self.client.get(
            f"{reverse('elimina_parametro_calcolo_stipendio', args=[self.parametro.pk])}?popup=1"
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "ga-parametro-delete-shell")
        self.assertContains(response, 'name="popup" value="1"')
