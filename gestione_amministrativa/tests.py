from datetime import date
from decimal import Decimal
from tempfile import TemporaryDirectory
from unittest import skip

from django.contrib.auth.models import User
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse

from anagrafica.models import Citta, Familiare, Nazione, Provincia, Regione, RelazioneFamiliare
from gestione_finanziaria.models import MovimentoFinanziario, StatoRiconciliazione
from scuola.models import AnnoScolastico, Classe, GruppoClasse
from sistema.models import LivelloPermesso, SistemaImpostazioniGenerali, SistemaUtentePermessi

from .forms import BustaPagaDipendenteForm
from .models import (
    BustaPagaDipendente,
    CategoriaDatoPayrollUfficiale,
    ContrattoDipendente,
    DatoPayrollUfficiale,
    Dipendente,
    ParametroCalcoloStipendio,
    RuoloAnagraficoDipendente,
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
            permesso_anagrafica=LivelloPermesso.GESTIONE,
            permesso_gestione_amministrativa=LivelloPermesso.GESTIONE,
        )
        self.impostazioni = SistemaImpostazioniGenerali.objects.create(
            gestione_dipendenti_dettagliata_attiva=True,
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
        self.assertContains(response, "anagrafica-list-panel")
        self.assertContains(response, "anagrafica-record-avatar-employee")
        self.assertContains(response, "data-ga-dipendenti-search")
        self.assertContains(response, f"{reverse('crea_dipendente')}")
        self.assertContains(response, f"{reverse('genera_previsione_busta_paga', args=[self.dipendente.pk])}")

    def test_lista_educatori_mostra_solo_profili_educatore(self):
        self.client.force_login(self.user)
        educatore = Dipendente.objects.create(
            nome="Elena",
            cognome="Bianchi",
            ruolo_anagrafico=RuoloAnagraficoDipendente.EDUCATORE,
            materia="Musica",
        )

        response = self.client.get(reverse("lista_educatori"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Educatori")
        self.assertContains(response, "anagrafica-record-avatar-educator")
        self.assertContains(response, "Bianchi Elena")
        self.assertContains(response, "Materia Musica")
        self.assertContains(response, f"{reverse('modifica_educatore', args=[educatore.pk])}")
        self.assertNotContains(response, "Rossi Mario")

        search_response = self.client.get(reverse("lista_educatori"), {"q": "Musica"})
        self.assertContains(search_response, "Bianchi Elena")

    def test_scheda_dipendente_usa_scheda_familiare_collegata(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse("modifica_dipendente", args=[self.dipendente.pk]))

        self.assertEqual(response.status_code, 302)
        self.dipendente.refresh_from_db()
        self.assertIsNotNone(self.dipendente.familiare_collegato_id)
        self.assertEqual(self.dipendente.familiare_collegato.nome, self.dipendente.nome)
        self.assertEqual(self.dipendente.familiare_collegato.cognome, self.dipendente.cognome)
        self.assertRedirects(
            response,
            f"{reverse('modifica_familiare', args=[self.dipendente.familiare_collegato_id])}#profilo-lavorativo-inline",
            fetch_redirect_response=False,
        )

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
        italia, _ = Nazione.objects.update_or_create(
            nome="Italia",
            defaults={
                "nome_nazionalita": "Italiana",
                "codice_iso2": "IT",
                "codice_iso3": "ITA",
                "codice_belfiore": "Z100",
                "attiva": True,
            },
        )
        regione, _ = Regione.objects.update_or_create(nome="Lazio", defaults={"attiva": True})
        provincia, _ = Provincia.objects.update_or_create(
            sigla="RM",
            defaults={"nome": "Roma", "regione": regione, "attiva": True},
        )
        Citta.objects.update_or_create(
            nome="Roma",
            provincia=provincia,
            defaults={"codice_catastale": "H501", "attiva": True},
        )

        response = self.client.get(reverse("crea_dipendente"))

        self.assertRedirects(
            response,
            f"{reverse('crea_familiare')}?profilo_lavorativo=dipendente",
            fetch_redirect_response=False,
        )

        response = self.client.get(f"{reverse('crea_familiare')}?profilo_lavorativo=dipendente")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "familiare-detail-form")
        self.assertContains(response, "Nuovo dipendente")
        self.assertContains(response, "Scheda anagrafica unica con profilo lavorativo gia' attivo")
        self.assertContains(response, "Anche dipendente")
        self.assertContains(response, "Anche educatore")
        self.assertContains(response, "profilo_dipendente_attivo")
        self.assertContains(response, "Mansione")
        self.assertContains(response, "Salva dipendente")
        self.assertContains(response, "Italiana")
        self.assertNotContains(response, "Data cessazione")
        self.assertEqual(italia.label_nazionalita, "Italiana")

    def test_crea_educatore_accetta_gruppo_classe_principale(self):
        self.client.force_login(self.user)
        anno = AnnoScolastico.objects.create(
            nome_anno_scolastico="2025/2026 - gestione amministrativa test",
            data_inizio=date(2025, 9, 1),
            data_fine=date(2026, 6, 30),
        )
        classe_prima = Classe.objects.create(nome_classe="Prima", sezione_classe="A", ordine_classe=1, attiva=True)
        classe_seconda = Classe.objects.create(nome_classe="Seconda", sezione_classe="A", ordine_classe=2, attiva=True)
        gruppo = GruppoClasse.objects.create(nome_gruppo_classe="Prima e Seconda", anno_scolastico=anno, attivo=True)
        gruppo.classi.set([classe_prima, classe_seconda])

        response = self.client.post(
            reverse("crea_educatore"),
            {
                "ruolo_anagrafico": RuoloAnagraficoDipendente.EDUCATORE,
                "familiare_collegato": "",
                "classe_principale_ref": f"gruppo:{gruppo.pk}",
                "materia": "Musica",
                "mansione": "Non salvare",
                "nome": "Elena",
                "cognome": "Bianchi",
                "data_nascita": "",
                "luogo_nascita": "",
                "nazionalita": "",
                "sesso": "",
                "codice_fiscale": "",
                "indirizzo": "",
                "telefono": "",
                "email": "",
                "iban": "",
                "codice_dipendente": "",
                "stato": "attivo",
                "note": "",
            },
        )

        self.assertEqual(response.status_code, 302)
        educatore = Dipendente.objects.get(nome="Elena", cognome="Bianchi")
        self.assertEqual(educatore.gruppo_classe_principale, gruppo)
        self.assertIsNone(educatore.classe_principale)
        self.assertEqual(educatore.materia, "Musica")
        self.assertEqual(educatore.mansione, "")

    @skip("Legacy test basato sulla tabella anagrafica.Famiglia rimossa.")
    def test_crea_dipendente_da_familiare_collegato_sincronizza_anagrafica(self):
        self.client.force_login(self.user)
        regione = Regione.objects.create(nome="Emilia-Romagna", ordine=1, attiva=True)
        provincia = Provincia.objects.create(sigla="BO", nome="Bologna", regione=regione, ordine=1, attiva=True)
        citta = Citta.objects.create(nome="Bologna", provincia=provincia, codice_catastale="A944", ordine=1, attiva=True)
        nazione = Nazione.objects.create(
            nome="Italia",
            nome_nazionalita="Italiana",
            codice_iso2="IT",
            codice_iso3="ITA",
            codice_belfiore="Z100",
            attiva=True,
        )
        stato = StatoRelazioneFamiglia.objects.create(stato="Interessata", ordine=1, attivo=True)
        famiglia = Famiglia.objects.create(cognome_famiglia="Verdi", stato_relazione_famiglia=stato)
        relazione = RelazioneFamiliare.objects.create(relazione="Madre", ordine=1)
        familiare = Familiare.objects.create(
            famiglia=famiglia,
            relazione_familiare=relazione,
            nome="Anna",
            cognome="Verdi",
            telefono="3331234567",
            email="anna.verdi@example.com",
            codice_fiscale="VRDNNA80A41A944R",
            sesso="F",
            data_nascita=date(1980, 1, 1),
            luogo_nascita=citta,
            nazionalita=nazione,
        )

        response = self.client.post(
            reverse("crea_dipendente"),
            {
                "ruolo_anagrafico": RuoloAnagraficoDipendente.DIPENDENTE,
                "familiare_collegato": str(familiare.pk),
                "classe_principale_ref": "",
                "mansione": "Segreteria",
                "nome": "Nome modificato",
                "cognome": "Cognome modificato",
                "data_nascita": "",
                "luogo_nascita": "",
                "nazionalita": "",
                "sesso": "",
                "codice_fiscale": "",
                "indirizzo": "",
                "telefono": "",
                "email": "",
                "iban": "",
                "codice_dipendente": "",
                "stato": "attivo",
                "note": "",
            },
        )

        self.assertEqual(response.status_code, 302)
        dipendente = Dipendente.objects.get(familiare_collegato=familiare)
        self.assertEqual(dipendente.nome, "Anna")
        self.assertEqual(dipendente.cognome, "Verdi")
        self.assertEqual(dipendente.email, "anna.verdi@example.com")
        self.assertEqual(dipendente.telefono, "3331234567")
        self.assertEqual(dipendente.codice_fiscale, "VRDNNA80A41A944R")
        self.assertEqual(dipendente.luogo_nascita, "Bologna (BO)")
        self.assertEqual(dipendente.nazionalita, "Italiana")
        self.assertEqual(dipendente.mansione, "Segreteria")

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
        self.assertContains(response, 'type="date"', count=2)
        self.assertContains(response, 'value="2025-09-01"')

    def test_modalita_semplice_contratto_mostra_previsione_e_nasconde_campi_tecnici(self):
        self.client.force_login(self.user)
        self.impostazioni.gestione_dipendenti_dettagliata_attiva = False
        self.impostazioni.save()

        response = self.client.get(f"{reverse('modifica_contratto_dipendente', args=[self.contratto.pk])}?popup=1")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Previsione economica")
        self.assertContains(response, "Costo aziendale ipotizzato")
        self.assertNotContains(response, 'id="popup-add-parametro-calcolo-btn"')
        self.assertNotContains(response, "CCNL")
        self.assertNotContains(response, "Simulazioni costo collegate")

    def test_modalita_semplice_contratto_salva_simulazione_previsionale(self):
        self.client.force_login(self.user)
        self.impostazioni.gestione_dipendenti_dettagliata_attiva = False
        self.impostazioni.save()

        response = self.client.post(
            f"{reverse('modifica_contratto_dipendente', args=[self.contratto.pk])}?popup=1",
            {
                "popup": "1",
                "descrizione": "Contratto semplificato",
                "tipo_contratto": str(self.tipo_contratto.pk),
                "data_inizio": "2025-09-01",
                "data_fine": "",
                "mansione": "Maestro",
                "costo_azienda_ipotizzato": "2300.00",
                "lordo_ipotizzato": "1600.00",
                "netto_ipotizzato": "1250.00",
                "contributi_mensili_ipotizzati": "700.00",
                "mensilita_annue": "13.00",
                "valuta": "EUR",
                "attivo": "on",
                "note": "",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.contratto.refresh_from_db()
        simulazione = self.contratto.simulazioni_costo.filter(attiva=True).order_by("-id").first()
        self.assertEqual(self.contratto.retribuzione_lorda_mensile, Decimal("1600.00"))
        self.assertEqual(simulazione.titolo, "Profilo previsionale semplificato")
        self.assertEqual(simulazione.costo_azienda_mensile, Decimal("2300.00"))
        self.assertEqual(simulazione.netto_mensile, Decimal("1250.00"))
        self.assertEqual(simulazione.contributi_previdenziali_azienda, Decimal("700.00"))

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
        self.assertContains(response, f'href="{reverse("crea_busta_paga_dipendente")}"')
        self.assertContains(response, f'data-popup-url="{reverse("crea_busta_paga_dipendente")}?popup=1"')
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
        self.assertContains(response, '<select name="mese"', html=False)
        self.assertContains(response, '<option value="10" selected>Ottobre</option>', html=True)
        self.assertContains(response, 'data-popup-note-collapse="false"', html=False)
        self.assertContains(response, 'data-long-wait-immediate="1"', html=False)
        self.assertContains(response, "long-wait-cursor.js", html=False)
        self.assertContains(response, 'id="add-busta-movimento-btn"', html=False)
        self.assertContains(response, 'data-related-type="movimento_finanziario"', html=False)
        self.assertNotContains(response, "Note previsione")

    def test_busta_paga_file_card_usa_link_interno_e_non_widget_standard(self):
        self.client.force_login(self.user)
        with TemporaryDirectory() as tmpdir, override_settings(
            MEDIA_ROOT=tmpdir,
            STORAGES={
                "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
                "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
            },
        ):
            self.busta.file_busta_paga.save("cedolino-ottobre.pdf", ContentFile(b"pdf"), save=True)
            response = self.client.get(f"{reverse('modifica_busta_paga_dipendente', args=[self.busta.pk])}?popup=1")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "ga-busta-file-current")
        self.assertContains(response, "cedolino-ottobre")
        self.assertContains(response, reverse("apri_file_busta_paga_dipendente", args=[self.busta.pk]))
        self.assertContains(response, 'name="svuota_file_busta_paga"', html=False)
        self.assertNotContains(response, "Attualmente:")
        self.assertNotContains(response, "Modifica:")

    def test_busta_paga_file_viene_servito_da_arboris(self):
        self.client.force_login(self.user)
        with TemporaryDirectory() as tmpdir, override_settings(
            MEDIA_ROOT=tmpdir,
            STORAGES={
                "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
                "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
            },
        ):
            self.busta.file_busta_paga.save("cedolino-ottobre.pdf", ContentFile(b"%PDF-1.4"), save=True)

            response = self.client.get(reverse("apri_file_busta_paga_dipendente", args=[self.busta.pk]))

            self.assertEqual(response.status_code, 200)
            self.assertEqual(response["Content-Type"], "application/pdf")
            self.assertIn("inline", response["Content-Disposition"])
            self.assertIn("cedolino-ottobre.pdf", response["Content-Disposition"])
            self.assertEqual(b"".join(response.streaming_content), b"%PDF-1.4")

    def test_busta_paga_file_puo_essere_svuotato_dalla_card(self):
        self.client.force_login(self.user)
        with TemporaryDirectory() as tmpdir, override_settings(
            MEDIA_ROOT=tmpdir,
            STORAGES={
                "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
                "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
            },
        ):
            self.busta.file_busta_paga.save("cedolino-ottobre.pdf", ContentFile(b"%PDF-1.4"), save=True)
            response = self.client.post(
                f"{reverse('modifica_busta_paga_dipendente', args=[self.busta.pk])}?popup=1",
                {
                    "popup": "1",
                    "dipendente": str(self.dipendente.pk),
                    "contratto": str(self.contratto.pk),
                    "anno": "2025",
                    "mese": "10",
                    "stato": StatoBustaPaga.EFFETTIVA,
                    "valuta": "EUR",
                    "svuota_file_busta_paga": "on",
                    "note_effettivo": "",
                },
            )

            self.assertEqual(response.status_code, 200)
            self.busta.refresh_from_db()
            self.assertFalse(self.busta.file_busta_paga)

    def test_busta_paga_importi_zero_restano_placeholder(self):
        form = BustaPagaDipendenteForm()

        field = form.fields["lordo_effettivo"]
        self.assertEqual(field.widget.attrs["placeholder"], "0,00")
        self.assertEqual(form["lordo_effettivo"].value(), "")

    def test_nuova_busta_paga_precompila_contratto_del_dipendente(self):
        self.client.force_login(self.user)

        response = self.client.get(f"{reverse('crea_busta_paga_dipendente')}?dipendente={self.dipendente.pk}&popup=1")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, f'<option value="{self.contratto.pk}" selected>', html=False)

    def test_busta_paga_collega_pagamento_e_compila_data_da_movimento(self):
        self.client.force_login(self.user)
        movimento = MovimentoFinanziario.objects.create(
            data_contabile=date(2025, 10, 31),
            importo=Decimal("-1302.00"),
            valuta="EUR",
            descrizione="Pagamento busta paga Mario Rossi",
            stato_riconciliazione=StatoRiconciliazione.NON_RICONCILIATO,
        )

        response = self.client.post(
            f"{reverse('modifica_busta_paga_dipendente', args=[self.busta.pk])}?popup=1",
            {
                "popup": "1",
                "dipendente": str(self.dipendente.pk),
                "contratto": str(self.contratto.pk),
                "anno": "2025",
                "mese": "10",
                "stato": StatoBustaPaga.EFFETTIVA,
                "valuta": "EUR",
                "netto_effettivo": "1302,00",
                "data_pagamento_effettiva": "",
                "movimento_pagamento": str(movimento.pk),
                "note_previsione": self.busta.note_previsione,
                "note_effettivo": "",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.busta.refresh_from_db()
        movimento.refresh_from_db()
        self.assertEqual(self.busta.movimento_pagamento, movimento)
        self.assertEqual(self.busta.data_pagamento_effettiva, date(2025, 10, 31))
        self.assertEqual(movimento.stato_riconciliazione, StatoRiconciliazione.RICONCILIATO)

    def test_modalita_semplice_busta_paga_nasconde_previsione_dettagliata(self):
        self.client.force_login(self.user)
        self.impostazioni.gestione_dipendenti_dettagliata_attiva = False
        self.impostazioni.save()

        response = self.client.get(f"{reverse('modifica_busta_paga_dipendente', args=[self.busta.pk])}?popup=1")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Importi busta paga")
        self.assertContains(response, "Lordo effettivo")
        self.assertContains(response, "Netto effettivo")
        self.assertContains(response, "File busta paga")
        self.assertNotContains(response, 'id="ga-busta-forecast-title"')
        self.assertNotContains(response, "Voci previsionali generate")
        self.assertNotContains(response, "Contributi datore effettivi")
        self.assertNotContains(response, "Movimento pagamento")

    def test_modalita_semplice_nuova_busta_paga_mostra_upload_file(self):
        self.client.force_login(self.user)
        self.impostazioni.gestione_dipendenti_dettagliata_attiva = False
        self.impostazioni.save()

        response = self.client.get(f"{reverse('crea_busta_paga_dipendente')}?popup=1")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Importi busta paga")
        self.assertContains(response, "File busta paga")
        self.assertContains(response, 'type="file"', html=False)
        self.assertContains(response, 'name="file_busta_paga"', html=False)
        self.assertNotContains(response, "Movimento pagamento")
        self.assertNotContains(response, "Data pagamento effettiva")

    def test_modalita_semplice_busta_paga_salva_lordo_e_netto(self):
        self.client.force_login(self.user)
        self.impostazioni.gestione_dipendenti_dettagliata_attiva = False
        self.impostazioni.save()

        response = self.client.post(
            f"{reverse('modifica_busta_paga_dipendente', args=[self.busta.pk])}?popup=1",
            {
                "popup": "1",
                "dipendente": str(self.dipendente.pk),
                "contratto": str(self.contratto.pk),
                "anno": "2025",
                "mese": "10",
                "stato": StatoBustaPaga.BOZZA,
                "valuta": "EUR",
                "lordo_effettivo": "1500,00",
                "netto_effettivo": "1200,00",
                "note_previsione": self.busta.note_previsione,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.busta.refresh_from_db()
        self.assertEqual(self.busta.lordo_effettivo, Decimal("1500.00"))
        self.assertEqual(self.busta.netto_effettivo, Decimal("1200.00"))
        self.assertEqual(self.busta.contributi_datore_effettivi, Decimal("0.00"))

    def test_modalita_semplice_busta_paga_salva_file(self):
        self.client.force_login(self.user)
        self.impostazioni.gestione_dipendenti_dettagliata_attiva = False
        self.impostazioni.save()
        with TemporaryDirectory() as tmpdir, override_settings(
            MEDIA_ROOT=tmpdir,
            STORAGES={
                "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
                "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
            },
        ):
            response = self.client.post(
                f"{reverse('modifica_busta_paga_dipendente', args=[self.busta.pk])}?popup=1",
                {
                    "popup": "1",
                    "dipendente": str(self.dipendente.pk),
                    "contratto": str(self.contratto.pk),
                    "anno": "2025",
                    "mese": "10",
                    "stato": StatoBustaPaga.BOZZA,
                    "valuta": "EUR",
                    "lordo_effettivo": "1500,00",
                    "netto_effettivo": "1200,00",
                    "file_busta_paga": SimpleUploadedFile("cedolino.pdf", b"%PDF-1.4", "application/pdf"),
                },
            )

            self.assertEqual(response.status_code, 200)
            self.busta.refresh_from_db()
            self.assertTrue(self.busta.file_busta_paga)

    def test_sidebar_modalita_semplice_nasconde_voci_avanzate_dipendenti(self):
        self.client.force_login(self.user)
        self.impostazioni.gestione_dipendenti_dettagliata_attiva = False
        self.impostazioni.save()

        response = self.client.get(reverse("lista_dipendenti"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Dipendenti e collaboratori")
        self.assertContains(response, "Buste paga")
        self.assertNotContains(response, "Parametri calcolo")
        self.assertNotContains(response, "Dati payroll ufficiali")

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
        DatoPayrollUfficiale.objects.create(
            categoria=CategoriaDatoPayrollUfficiale.FONTE,
            codice="INPS_TEST",
            nome="Fonte INPS test",
            ente="INPS",
            valore_testo="Fonte ufficiale",
            fonte_url="https://www.inps.it/",
        )

        response = self.client.get(reverse("lista_parametri_calcolo_stipendi"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "ga-parametri-list-shell")
        self.assertContains(response, "data-ga-parametri-search")
        self.assertContains(response, f"{reverse('lista_dati_payroll_ufficiali')}")
        self.assertContains(response, "Fonti ufficiali payroll")
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

    def test_nuovo_parametro_calcolo_prefilla_da_ultimo_parametro_attivo(self):
        self.client.force_login(self.user)

        response = self.client.get(f"{reverse('crea_parametro_calcolo_stipendio')}?popup=1")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Aliquote copiate dall&#x27;ultimo parametro attivo: Standard payroll")
        self.assertContains(response, 'value="30.00"')
        self.assertContains(response, 'value="9.00"')
        self.assertContains(response, 'value="7.41"')
        self.assertContains(response, 'value="1.00"')
        self.assertContains(response, 'value="2.00"')

    def test_parametro_calcolo_delete_popup_renderizza_nuovo_layout(self):
        self.client.force_login(self.user)

        response = self.client.get(
            f"{reverse('elimina_parametro_calcolo_stipendio', args=[self.parametro.pk])}?popup=1"
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "ga-parametro-delete-shell")
        self.assertContains(response, 'name="popup" value="1"')

    def test_catalogo_dati_payroll_ufficiali_si_popola_da_comando(self):
        call_command("aggiorna_dati_payroll_ufficiali", "--solo-catalogo")

        self.assertGreaterEqual(
            DatoPayrollUfficiale.objects.filter(categoria=CategoriaDatoPayrollUfficiale.FONTE).count(),
            5,
        )
        self.assertTrue(DatoPayrollUfficiale.objects.filter(codice="MEF_ADDIZIONALI_COMUNALI").exists())

    def test_lista_dati_payroll_ufficiali_renderizza_nuovo_layout(self):
        self.client.force_login(self.user)
        DatoPayrollUfficiale.objects.create(
            categoria=CategoriaDatoPayrollUfficiale.FONTE,
            codice="INPS_TEST",
            nome="Fonte INPS test",
            ente="INPS",
            valore_testo="Fonte ufficiale",
            fonte_url="https://www.inps.it/",
        )

        response = self.client.get(reverse("lista_dati_payroll_ufficiali"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "ga-payroll-data-shell")
        self.assertContains(response, "Fonte INPS test")
        self.assertContains(response, "aggiorna_dati_payroll_ufficiali")
