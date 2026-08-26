import base64
import gzip
import json
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory
from datetime import timedelta
from decimal import Decimal
from unittest import skip
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth.models import User
from django.core.cache import cache
from django.core import mail
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .database_backups import (
    build_sanitized_restore_sql,
    cancel_or_delete_restore_job,
    create_restore_job_from_backup_record,
    create_restore_job_from_local_file,
    create_restore_job_from_storage_reference,
    create_restore_job_from_upload,
    reset_public_schema_for_restore,
    restore_stderr_has_blocking_errors,
)
from .forms import ConfigurazioneEmailSMTPForm
from .models import (
    ConfigurazioneEmailSMTP,
    FeedbackSegnalazione,
    LivelloPermesso,
    RuoloUtente,
    SistemaDatabaseBackup,
    SistemaDatabaseRestoreJob,
    SistemaImpostazioniGenerali,
    SistemaOperazioneCronologia,
    SistemaRuoloPermessi,
    SidebarPersonalizzazione,
    SistemaUtentePermessi,
    StatoRipristinoDatabase,
    TipoFeedbackSegnalazione,
)
from .popup_manifest import build_popup_manifest
from .restore_job_runner import run_restore_job
from .sidebar_menu import SIDEBAR_MENU_ITEM_KEYS
from anagrafica.models import (
    Citta,
    Documento,
    Familiare,
    Provincia,
    Regione,
    RelazioneFamiliare,
    Studente,
    StudenteFamiliare,
    TipoDocumento,
)
from anagrafica.models import Indirizzo
from calendario.models import CategoriaCalendario, EventoCalendario
from economia.models import CondizioneIscrizione, Iscrizione, StatoIscrizione
from gestione_finanziaria.models import DocumentoFornitore, Fornitore, MovimentoFinanziario, ScadenzaPagamentoFornitore
from scuola.models import AnnoScolastico, Classe, GruppoClasse


class AuthenticationInterfaceTests(TestCase):
    def setUp(self):
        self.password = "Password123!"
        self.user = User.objects.create_user(
            username="operatore@example.com",
            email="operatore@example.com",
            password=self.password,
            first_name="Mario",
            last_name="Rossi",
        )

    def test_home_requires_login(self):
        response = self.client.get(reverse("home"))

        self.assertRedirects(response, f"{reverse('login')}?next={reverse('home')}")

    def test_school_routes_require_login(self):
        response = self.client.get(reverse("lista_anni_scolastici"))

        self.assertRedirects(
            response,
            f"{reverse('login')}?next={reverse('lista_anni_scolastici')}",
        )

    def test_login_page_renders_browser_friendly_controls(self):
        next_url = reverse("lista_famiglie")

        response = self.client.get(reverse("login"), {"next": next_url})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="remember_me"')
        self.assertContains(response, 'autocomplete="username"')
        self.assertContains(response, 'autocomplete="current-password"')
        self.assertContains(response, f'<input type="hidden" name="next" value="{next_url}">', html=True)
        self.assertContains(response, f'href="{reverse("crediti")}"', html=False)

    def test_credits_page_renders_streamline_attribution(self):
        response = self.client.get(reverse("crediti"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Crediti")
        self.assertContains(response, "streamline-vectors")
        self.assertContains(response, "Creative Commons Attribution 4.0")
        self.assertContains(response, "streamlinehq.com")

    def test_streamline_vendor_manifest_documents_source_and_license(self):
        manifest_path = settings.BASE_DIR / "static" / "vendor" / "streamline-vectors" / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

        self.assertEqual(manifest["source_repository"], "https://github.com/webalys-hq/streamline-vectors")
        self.assertEqual(manifest["license"], "CC BY 4.0")
        self.assertEqual(manifest["attribution_url"], "https://streamlinehq.com")
        self.assertGreaterEqual(len(manifest["icons"]), 30)

    def test_login_with_remember_me_keeps_session_persistent(self):
        response = self.client.post(
            reverse("login"),
            {
                "username": self.user.username,
                "password": self.password,
                "remember_me": "on",
                "next": reverse("home"),
            },
        )

        self.assertRedirects(response, reverse("home"))
        self.assertFalse(self.client.session.get_expire_at_browser_close())

    def test_login_without_remember_me_expires_on_browser_close(self):
        response = self.client.post(
            reverse("login"),
            {
                "username": self.user.username,
                "password": self.password,
                "next": reverse("home"),
            },
        )

        self.assertRedirects(response, reverse("home"))
        self.assertTrue(self.client.session.get_expire_at_browser_close())

    def test_home_hides_module_sections_when_user_has_no_permissions(self):
        SistemaUtentePermessi.objects.create(user=self.user)
        self.client.force_login(self.user)

        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context["can_view_anagrafica"])
        self.assertFalse(response.context["can_view_economia"])
        self.assertFalse(response.context["can_view_gestione_amministrativa"])
        self.assertNotContains(response, f'href="{reverse("lista_famiglie")}"', html=False)
        self.assertNotContains(response, f'href="{reverse("lista_iscrizioni")}"', html=False)
        self.assertNotContains(response, f'href="{reverse("lista_dipendenti")}"', html=False)
        self.assertNotContains(response, f'href="{reverse("lista_anni_scolastici")}"', html=False)
        self.assertNotContains(response, 'data-sidebar-section-key="sistema"', html=False)
        self.assertNotContains(response, "GESTIONE FINANZIARIA")


class ConfigurazioneEmailSMTPFormTests(TestCase):
    def test_password_vuota_preserva_password_salvata(self):
        configurazione = ConfigurazioneEmailSMTP.objects.create(
            host="smtp.example.com",
            port=587,
            sicurezza="starttls",
            username="segreteria",
            password="password-esistente",
            email_mittente="segreteria@example.com",
            nome_mittente="Segreteria",
            timeout_secondi=20,
        )

        form = ConfigurazioneEmailSMTPForm(
            {
                "host": "smtp.example.com",
                "port": "587",
                "sicurezza": "starttls",
                "username": "segreteria",
                "password": "",
                "email_mittente": "segreteria@example.com",
                "nome_mittente": "Segreteria",
                "reply_to": "",
                "timeout_secondi": "20",
            },
            instance=configurazione,
        )

        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        configurazione.refresh_from_db()
        self.assertEqual(configurazione.password, "password-esistente")

    def test_test_smtp_failure_renders_error_message_without_500(self):
        user = User.objects.create_superuser(username="smtp-admin@example.com", password="admin")
        self.client.login(username="smtp-admin@example.com", password="admin")
        ConfigurazioneEmailSMTP.objects.create(
            pk=1,
            host="smtp.example.com",
            port=587,
            sicurezza="starttls",
            email_mittente="segreteria@example.com",
        )

        with patch("sistema.views.invia_email_test_smtp", side_effect=RuntimeError("SMTP KO")):
            with patch("sistema.views.logger.exception"):
                response = self.client.post(
                    reverse("configurazione_email_smtp"),
                    {
                        "action": "test",
                        "test-destinatario": "destinatario@example.com",
                        "test-oggetto": "Test",
                        "test-messaggio": "Messaggio",
                    },
                )

        self.assertRedirects(response, reverse("configurazione_email_smtp"))


class ProfessionalInterfaceSettingsTests(TestCase):
    def setUp(self):
        cache.clear()
        self.password = "Password123!"
        self.admin = User.objects.create_user(
            username="ui-admin@example.com",
            email="ui-admin@example.com",
            password=self.password,
        )
        SistemaUtentePermessi.objects.create(
            user=self.admin,
            permesso_sistema=LivelloPermesso.GESTIONE,
        )

    def settings_payload(self, **overrides):
        payload = {
            "terminologia_studente": "studente",
            "terminologia_familiare": "familiare",
            "terminologia_educatore": "educatore",
            "interfaccia_colorata_attiva": "on",
            "modulo_anagrafica_attivo": "on",
            "modulo_famiglie_interessate_attivo": "on",
            "modulo_economia_attivo": "on",
            "modulo_calendario_attivo": "on",
            "modulo_gestione_finanziaria_attivo": "on",
            "modulo_gestione_amministrativa_attivo": "on",
            "modulo_servizi_extra_attivo": "on",
            "formato_visualizzazione_telefono": "it_plus_n3_2_2_3",
            "cronologia_retention_mesi": "24",
            "gestione_iscrizione_corso_anno": "mese_iscrizione_intero",
            "giorno_soglia_iscrizione_corso_anno": "15",
            "font_principale": "manrope",
            "font_titoli": "manrope",
        }
        payload.update(overrides)
        return payload

    def test_professional_interface_setting_adds_body_class(self):
        SistemaImpostazioniGenerali.objects.create(interfaccia_professionale_attiva=True)
        self.client.force_login(self.admin)

        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "ui-professional-interface")

    def test_professional_interface_keeps_anagrafica_sidebar_state_on_observation_links(self):
        SistemaImpostazioniGenerali.objects.create(interfaccia_professionale_attiva=True)
        SistemaUtentePermessi.objects.filter(user=self.admin).update(
            permesso_anagrafica=LivelloPermesso.GESTIONE
        )
        studente = Studente.objects.create(nome="Luca", cognome="Rossi")
        self.client.force_login(self.admin)

        response = self.client.get(reverse("osservazioni_studente", kwargs={"studente_pk": studente.pk}))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "ui-professional-interface module-anagrafica")
        self.assertContains(
            response,
            f'href="{reverse("lista_studenti")}" data-sidebar-menu-key="anagrafica_studenti" class="active"',
            html=False,
        )

    def test_professional_interface_maps_integrated_apps_to_parent_sidebar_modules(self):
        SistemaImpostazioniGenerali.objects.create(interfaccia_professionale_attiva=True)
        SistemaUtentePermessi.objects.filter(user=self.admin).update(
            permesso_economia=LivelloPermesso.VISUALIZZAZIONE
        )
        self.client.force_login(self.admin)

        response = self.client.get(reverse("fondo_piano_lista"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "ui-professional-interface module-economia")

        response = self.client.get(reverse("lista_anni_scolastici"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "ui-professional-interface module-sistema")

    def test_settings_form_renders_and_saves_professional_toggle(self):
        self.client.force_login(self.admin)

        response = self.client.get(reverse("impostazioni_generali_sistema"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Interfaccia professionale")

        response = self.client.post(
            reverse("impostazioni_generali_sistema"),
            self.settings_payload(interfaccia_professionale_attiva="on"),
        )

        self.assertRedirects(response, reverse("impostazioni_generali_sistema"))
        impostazioni = SistemaImpostazioniGenerali.objects.get()
        self.assertTrue(impostazioni.interfaccia_professionale_attiva)


class GlobalSearchTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="search@example.com",
            email="search@example.com",
            password="Password123!",
        )
        SistemaUtentePermessi.objects.create(
            user=self.user,
            permesso_anagrafica=LivelloPermesso.VISUALIZZAZIONE,
        )
        self.client.force_login(self.user)

    def test_header_renders_global_search_dropdown_controls(self):
        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "data-global-search-form")
        self.assertContains(response, f'data-global-search-url="{reverse("ricerca_globale_sistema")}"')
        self.assertContains(response, "data-global-search-dropdown")
        self.assertContains(response, "js/core/global-search.js")

    @skip("Legacy test basato sulla tabella anagrafica.Famiglia rimossa.")
    def test_global_search_returns_only_allowed_modules(self):
        stato = StatoRelazioneFamiglia.objects.create(stato="Attiva")
        famiglia = Famiglia.objects.create(cognome_famiglia="Rossi", stato_relazione_famiglia=stato)
        Studente.objects.create(nome="Luca", cognome="Rossi", famiglia=famiglia)
        Fornitore.objects.create(denominazione="Rossi Forniture")

        response = self.client.get(reverse("ricerca_globale_sistema"), {"q": "Rossi"})

        self.assertEqual(response.status_code, 200)
        categories = {item["category"] for item in response.json()["results"]}
        self.assertIn("Famiglia", categories)
        self.assertIn("Studente", categories)
        self.assertNotIn("Fornitore", categories)

        SistemaUtentePermessi.objects.filter(user=self.user).update(
            permesso_gestione_finanziaria=LivelloPermesso.VISUALIZZAZIONE
        )
        if hasattr(self.user, "_arboris_permission_profile_cache"):
            delattr(self.user, "_arboris_permission_profile_cache")

        response = self.client.get(reverse("ricerca_globale_sistema"), {"q": "Rossi"})

        self.assertEqual(response.status_code, 200)
        categories = {item["category"] for item in response.json()["results"]}
        self.assertIn("Fornitore", categories)

    def test_global_search_finds_logical_family_without_legacy_family(self):
        relazione = RelazioneFamiliare.objects.create(relazione="Genitore")
        studente = Studente.objects.create(nome="Sara", cognome="Verdi", attivo=True)
        familiare = Familiare.objects.create(
            relazione_familiare=relazione,
            nome="Giulia",
            cognome="Verdi",
            attivo=True,
        )
        StudenteFamiliare.objects.create(
            studente=studente,
            familiare=familiare,
            relazione_familiare=relazione,
            attivo=True,
        )

        response = self.client.get(reverse("ricerca_globale_sistema"), {"q": "Verdi"})

        self.assertEqual(response.status_code, 200)
        famiglia_results = [
            item for item in response.json()["results"] if item["category"] == "Famiglia"
        ]
        self.assertTrue(famiglia_results)
        self.assertEqual(
            famiglia_results[0]["url"],
            reverse("modifica_famiglia_logica", kwargs={"key": f"s-{studente.pk}"}),
        )

    def test_global_search_returns_only_people_and_suppliers(self):
        SistemaUtentePermessi.objects.filter(user=self.user).update(
            permesso_gestione_finanziaria=LivelloPermesso.VISUALIZZAZIONE,
            permesso_calendario=LivelloPermesso.VISUALIZZAZIONE,
            permesso_famiglie_interessate=LivelloPermesso.VISUALIZZAZIONE,
        )
        if hasattr(self.user, "_arboris_permission_profile_cache"):
            delattr(self.user, "_arboris_permission_profile_cache")

        today = timezone.localdate()
        relazione = RelazioneFamiliare.objects.create(relazione="Genitore")
        studente = Studente.objects.create(nome="Luca", cognome="Rossi", attivo=True)
        familiare = Familiare.objects.create(
            relazione_familiare=relazione,
            nome="Giulia",
            cognome="Rossi",
            attivo=True,
        )
        StudenteFamiliare.objects.create(
            studente=studente,
            familiare=familiare,
            relazione_familiare=relazione,
            attivo=True,
        )
        tipo_documento = TipoDocumento.objects.create(tipo_documento="Documento Rossi")
        Documento.objects.create(
            studente=studente,
            tipo_documento=tipo_documento,
            descrizione="Documento Rossi",
            file="documenti/rossi.pdf",
        )
        fornitore = Fornitore.objects.create(denominazione="Rossi Forniture")
        DocumentoFornitore.objects.create(
            fornitore=fornitore,
            numero_documento="Rossi-001",
            data_documento=today,
            descrizione="Fattura Rossi",
            totale=Decimal("10.00"),
        )
        MovimentoFinanziario.objects.create(
            data_contabile=today,
            importo=Decimal("10.00"),
            descrizione="Movimento Rossi",
        )
        categoria = CategoriaCalendario.objects.create(nome="Agenda Rossi")
        EventoCalendario.objects.create(
            titolo="Evento Rossi",
            categoria_evento=categoria,
            data_inizio=today,
            data_fine=today,
        )

        response = self.client.get(reverse("ricerca_globale_sistema"), {"q": "Rossi"})

        self.assertEqual(response.status_code, 200)
        categories = {item["category"] for item in response.json()["results"]}
        self.assertIn("Famiglia", categories)
        self.assertIn("Studente", categories)
        self.assertIn("Familiare", categories)
        self.assertIn("Fornitore", categories)
        self.assertNotIn("Documento", categories)
        self.assertNotIn("Fattura fornitore", categories)
        self.assertNotIn("Movimento bancario", categories)
        self.assertNotIn("Evento calendario", categories)

    def test_global_search_ignores_too_short_queries(self):
        response = self.client.get(reverse("ricerca_globale_sistema"), {"q": "R"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["results"], [])


class HomeDashboardSchoolYearTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="dashboard@example.com",
            email="dashboard@example.com",
            password="Password123!",
        )
        SistemaUtentePermessi.objects.create(user=self.user)
        self.client.force_login(self.user)

    def test_home_uses_school_year_dates_for_current_status(self):
        today = timezone.localdate()
        anno = AnnoScolastico.objects.create(
            nome_anno_scolastico="2025/2026",
            data_inizio=today - timedelta(days=30),
            data_fine=today + timedelta(days=30),
            attivo=True,
        )

        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Anno Scolastico 2025/2026")
        self.assertContains(response, "Corrente")
        self.assertContains(response, anno.data_inizio.strftime("%d/%m/%Y"))
        self.assertContains(response, anno.data_fine.strftime("%d/%m/%Y"))
        self.assertEqual(response.context["calendario_dashboard"]["today"], today)

    def test_home_marks_future_school_year_as_upcoming(self):
        today = timezone.localdate()
        AnnoScolastico.objects.create(
            nome_anno_scolastico="2026/2027",
            data_inizio=today + timedelta(days=30),
            data_fine=today + timedelta(days=395),
            attivo=True,
        )

        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Anno Scolastico 2026/2027")
        self.assertContains(response, "Prossimo")

    def test_home_can_switch_school_year_dashboard_data(self):
        SistemaUtentePermessi.objects.filter(user=self.user).update(
            permesso_economia=LivelloPermesso.VISUALIZZAZIONE
        )
        today = timezone.localdate()
        anno_corrente = AnnoScolastico.objects.create(
            nome_anno_scolastico="Anno corrente dashboard",
            data_inizio=today - timedelta(days=30),
            data_fine=today + timedelta(days=30),
            attivo=True,
        )
        anno_futuro = AnnoScolastico.objects.create(
            nome_anno_scolastico="Anno futuro dashboard",
            data_inizio=today + timedelta(days=31),
            data_fine=today + timedelta(days=395),
            attivo=True,
        )
        classe_corrente = Classe.objects.create(nome_classe="Corrente", sezione_classe="A", ordine_classe=1)
        classe_futura = Classe.objects.create(nome_classe="Futura", sezione_classe="B", ordine_classe=2)
        stato = StatoIscrizione.objects.create(stato_iscrizione="Attiva", ordine=1, attiva=True)
        condizione_corrente = CondizioneIscrizione.objects.create(
            anno_scolastico=anno_corrente,
            nome_condizione_iscrizione="Retta corrente",
            numero_mensilita_default=10,
            attiva=True,
        )
        condizione_futura = CondizioneIscrizione.objects.create(
            anno_scolastico=anno_futuro,
            nome_condizione_iscrizione="Retta futura",
            numero_mensilita_default=10,
            attiva=True,
        )
        studente_corrente = Studente.objects.create(nome="Anna", cognome="Corrente", attivo=True)
        studente_futuro = Studente.objects.create(nome="Marco", cognome="Futuro", attivo=True)
        Iscrizione.objects.create(
            studente=studente_corrente,
            anno_scolastico=anno_corrente,
            classe=classe_corrente,
            stato_iscrizione=stato,
            condizione_iscrizione=condizione_corrente,
            attiva=True,
        )
        Iscrizione.objects.create(
            studente=studente_futuro,
            anno_scolastico=anno_futuro,
            classe=classe_futura,
            stato_iscrizione=stato,
            condizione_iscrizione=condizione_futura,
            attiva=True,
        )

        response = self.client.get(reverse("home"), {"anno_scolastico": anno_futuro.pk})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["anno_scolastico_corrente_obj"].pk, anno_futuro.pk)
        self.assertEqual(response.context["dashboard_anno_scolastico_selezionato"], str(anno_futuro.pk))
        self.assertTrue(response.context["dashboard_has_year_switch"])
        self.assertEqual(response.context["count_studenti_iscritti"], 1)
        self.assertEqual(response.context["economia_dashboard"]["count_studenti_iscritti"], 1)
        self.assertEqual(response.context["calendario_dashboard"]["today"], anno_futuro.data_inizio)
        self.assertContains(response, "Anno Scolastico Anno futuro dashboard")
        self.assertContains(response, 'name="anno_scolastico"')
        self.assertContains(response, "Settimana di riferimento")
        self.assertContains(
            response,
            "RIEPILOGO E INDICATORI CHIAVE - Anno Scolastico Anno futuro dashboard",
        )
        self.assertContains(
            response,
            "RIEPILOGO FINANZIARIO - Anno Scolastico Anno futuro dashboard",
        )
        self.assertContains(response, str(studente_futuro))
        self.assertContains(response, reverse("modifica_studente", kwargs={"pk": studente_futuro.pk}))
        self.assertNotContains(response, str(studente_corrente))

    def test_home_class_composition_renders_expandable_class_and_group_views(self):
        today = timezone.localdate()
        anno = AnnoScolastico.objects.create(
            nome_anno_scolastico="Anno composizione dashboard",
            data_inizio=today - timedelta(days=30),
            data_fine=today + timedelta(days=30),
            attivo=True,
        )
        classe_prima = Classe.objects.create(nome_classe="Prima", sezione_classe="A", ordine_classe=1)
        classe_seconda = Classe.objects.create(nome_classe="Seconda", sezione_classe="B", ordine_classe=2)
        gruppo = GruppoClasse.objects.create(
            nome_gruppo_classe="Primaria mista",
            anno_scolastico=anno,
            attivo=True,
        )
        gruppo.classi.add(classe_prima, classe_seconda)
        stato = StatoIscrizione.objects.create(stato_iscrizione="Attiva", ordine=1, attiva=True)
        condizione = CondizioneIscrizione.objects.create(
            anno_scolastico=anno,
            nome_condizione_iscrizione="Retta standard",
            numero_mensilita_default=10,
            attiva=True,
        )
        luca = Studente.objects.create(nome="Luca", cognome="Rossi", attivo=True)
        sara = Studente.objects.create(nome="Sara", cognome="Verdi", attivo=True)
        for studente, classe in ((luca, classe_prima), (sara, classe_seconda)):
            Iscrizione.objects.create(
                studente=studente,
                anno_scolastico=anno,
                classe=classe,
                gruppo_classe=gruppo,
                stato_iscrizione=stato,
                condizione_iscrizione=condizione,
                attiva=True,
            )

        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-dashboard-class-view="classi"')
        self.assertContains(response, 'data-dashboard-class-view="pluriclassi"')
        self.assertContains(response, 'class="dashboard-class-item dashboard-class-expandable"', count=3)
        self.assertContains(response, "Prima A")
        self.assertContains(response, "Seconda B")
        self.assertContains(response, "Primaria mista")
        self.assertContains(response, str(luca))
        self.assertContains(response, str(sara))
        self.assertContains(response, reverse("modifica_studente", kwargs={"pk": luca.pk}))
        self.assertContains(response, reverse("modifica_studente", kwargs={"pk": sara.pk}))

    def test_home_week_calendar_uses_client_side_pagination(self):
        SistemaUtentePermessi.objects.filter(user=self.user).update(
            permesso_calendario=LivelloPermesso.VISUALIZZAZIONE
        )
        categoria = CategoriaCalendario.objects.create(nome="Agenda", colore="#417690", ordine=1)
        week_start = timezone.localdate() - timedelta(days=timezone.localdate().weekday())
        for index in range(4):
            EventoCalendario.objects.create(
                titolo=f"Evento settimana {index + 1}",
                categoria_evento=categoria,
                data_inizio=week_start + timedelta(days=index),
                data_fine=week_start + timedelta(days=index),
                intera_giornata=True,
            )

        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-dashboard-calendar-week')
        self.assertContains(response, 'data-dashboard-calendar-page-size="3"')
        self.assertContains(response, 'data-dashboard-calendar-next')
        self.assertContains(response, 'is-dashboard-calendar-hidden', count=1)
        self.assertNotContains(response, "dashboard_week_page")


class SidebarEconomiaTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="economia@example.com",
            email="economia@example.com",
            password="Password123!",
        )
        SistemaUtentePermessi.objects.create(
            user=self.user,
            permesso_economia=LivelloPermesso.VISUALIZZAZIONE,
        )

    def test_home_renders_economia_items_in_standard_sidebar_sections(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        content = response.content.decode("utf-8")
        self.assertNotIn('id="sidebar-economia-panel"', content)

        anagrafica_start = content.index('id="sidebar-anagrafica-panel"')
        anagrafica_end = content.index('data-sidebar-section-key="gestione-economica"', anagrafica_start)
        anagrafica_section = content[anagrafica_start:anagrafica_end]

        anagrafica_labels_in_order = [
            "<span>Rette e Iscrizioni</span>",
            '<span class="sidebar-link-text">Iscrizioni</span>',
            "Stati iscrizione",
            "Rate iscrizione",
            "<span>Impostazioni Rette</span>",
            "Condizioni economiche",
            "Tariffe",
            "Tariffe Scambio Retta",
            "Agevolazioni",
        ]

        previous_index = -1
        for label in anagrafica_labels_in_order:
            current_index = anagrafica_section.index(label)
            self.assertGreater(current_index, previous_index)
            previous_index = current_index

        start = content.index('id="sidebar-gestione-economica-panel"')
        end = content.index("<!-- FINE CODICE DELLA SIDEBAR -->", start)
        gestione_economica_section = content[start:end]

        labels_in_order = [
            "Panoramica Rette",
            "Scambi Retta",
            "Fondi di Accantonamento",
        ]

        previous_index = -1
        for label in labels_in_order:
            current_index = gestione_economica_section.index(label)
            self.assertGreater(current_index, previous_index)
            previous_index = current_index

        self.assertNotIn("Fondo accantonamento", content)
        self.assertNotIn("Scambio retta", content)
        self.assertNotIn("Tariffe scambio retta", content)
        self.assertNotContains(response, 'data-sidebar-section-key="sistema"', html=False)
        self.assertNotContains(response, 'data-sidebar-section-key="parcheggio"', html=False)

    def test_home_hides_parcheggio_accounting_links_for_view_only_roles(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'data-sidebar-section-key="parcheggio"', html=False)

        admin_user = User.objects.create_user(
            username="parcheggio-admin@example.com",
            email="parcheggio-admin@example.com",
            password="Password123!",
        )
        SistemaUtentePermessi.objects.create(
            user=admin_user,
            ruolo=RuoloUtente.AMMINISTRATORE,
            permesso_economia=LivelloPermesso.VISUALIZZAZIONE,
            permesso_gestione_finanziaria=LivelloPermesso.VISUALIZZAZIONE,
        )
        self.client.force_login(admin_user)

        admin_response = self.client.get(reverse("home"))

        self.assertEqual(admin_response.status_code, 200)
        content = admin_response.content.decode("utf-8")

        self.assertIn('data-sidebar-menu-group="anagrafica_rette_iscrizioni"', content)
        self.assertIn('data-sidebar-menu-key="economia_iscrizioni"', content)
        self.assertNotIn('data-sidebar-section-key="parcheggio"', content)
        self.assertNotIn('data-sidebar-menu-key="gestione_finanziaria_budgeting"', content)
        self.assertNotIn('data-sidebar-menu-key="gestione_finanziaria_documenti_fornitori"', content)
        self.assertNotIn('data-sidebar-menu-key="gestione_finanziaria_scadenziario_fornitori"', content)
        self.assertNotIn('data-sidebar-menu-key="gestione_finanziaria_pagamenti_fornitori"', content)
        self.assertNotIn('data-sidebar-menu-key="gestione_finanziaria_notifiche"', content)

    def test_home_renders_parcheggio_accounting_links_for_manage_roles(self):
        admin_user = User.objects.create_user(
            username="parcheggio-manager@example.com",
            email="parcheggio-manager@example.com",
            password="Password123!",
        )
        SistemaUtentePermessi.objects.create(
            user=admin_user,
            ruolo=RuoloUtente.AMMINISTRATORE,
            permesso_economia=LivelloPermesso.GESTIONE,
            permesso_gestione_finanziaria=LivelloPermesso.GESTIONE,
        )
        self.client.force_login(admin_user)

        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        content = response.content.decode("utf-8")
        start = content.index('data-sidebar-section-key="parcheggio"')
        end = content.index('data-sidebar-section-key="sistema"', start)
        parcheggio_section = content[start:end]

        self.assertIn("Parcheggio", parcheggio_section)
        self.assertIn(f'href="{reverse("budgeting_dashboard")}"', parcheggio_section)
        self.assertIn(f'href="{reverse("lista_documenti_fornitori")}"', parcheggio_section)
        self.assertIn(f'href="{reverse("scadenziario_fornitori")}"', parcheggio_section)
        self.assertIn(f'href="{reverse("lista_movimenti_da_riconciliare_fornitori")}"', parcheggio_section)
        self.assertIn(f'href="{reverse("lista_notifiche_finanziarie")}"', parcheggio_section)
        self.assertNotIn(f'href="{reverse("lista_iscrizioni")}"', parcheggio_section)
        self.assertLess(parcheggio_section.index("Budgeting"), parcheggio_section.index("Fatture fornitori"))
        self.assertLess(parcheggio_section.index("Fatture fornitori"), parcheggio_section.index("Scadenziario fornitori"))
        self.assertLess(parcheggio_section.index("Scadenziario fornitori"), parcheggio_section.index("Pagamenti fornitori"))

    def test_home_renders_gestione_amministrativa_inside_gestione_economica(self):
        SistemaImpostazioniGenerali.objects.create(gestione_dipendenti_dettagliata_attiva=True)
        user = User.objects.create_user(
            username="gestione-amministrativa@example.com",
            email="gestione-amministrativa@example.com",
            password="Password123!",
        )
        SistemaUtentePermessi.objects.create(
            user=user,
            permesso_gestione_amministrativa=LivelloPermesso.VISUALIZZAZIONE,
        )
        self.client.force_login(user)

        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'data-sidebar-section-key="gestione-amministrativa"', html=False)
        content = response.content.decode("utf-8")
        start = content.index('data-sidebar-section-key="gestione-economica"')
        end = content.index("<!-- FINE CODICE DELLA SIDEBAR -->", start)
        gestione_economica_section = content[start:end]

        labels_in_order = [
            "<span>Dipendenti e Collaboratori</span>",
            '<span class="sidebar-link-text">Dashboard</span>',
            '<span class="sidebar-link-text">Educatori</span>',
            '<span class="sidebar-link-text">Dipendenti</span>',
            '<span class="sidebar-link-text">Contratti</span>',
            '<span class="sidebar-link-text">Simulazioni costo</span>',
            '<span class="sidebar-link-text">Buste paga</span>',
            '<span class="sidebar-link-text">Parametri calcolo</span>',
            '<span class="sidebar-link-text">Dati payroll ufficiali</span>',
        ]

        previous_index = -1
        for label in labels_in_order:
            current_index = gestione_economica_section.index(label)
            self.assertGreater(current_index, previous_index)
            previous_index = current_index
        self.assertIn('id="sidebar-gestione-economica-dipendenti-collaboratori-panel"', gestione_economica_section)
        self.assertIn(f'href="{reverse("lista_educatori")}"', gestione_economica_section)
        self.assertNotContains(response, 'data-sidebar-section-key="parcheggio"', html=False)

    def test_home_moves_educatori_from_anagrafiche_to_gestione_economica(self):
        user = User.objects.create_user(
            username="educatori-parcheggio@example.com",
            email="educatori-parcheggio@example.com",
            password="Password123!",
        )
        SistemaUtentePermessi.objects.create(
            user=user,
            permesso_anagrafica=LivelloPermesso.VISUALIZZAZIONE,
            permesso_gestione_amministrativa=LivelloPermesso.VISUALIZZAZIONE,
        )
        self.client.force_login(user)

        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        content = response.content.decode("utf-8")
        anagrafica_start = content.index('id="sidebar-anagrafica-panel"')
        anagrafica_end = content.index('data-sidebar-section-key="gestione-economica"', anagrafica_start)
        anagrafica_section = content[anagrafica_start:anagrafica_end]
        gestione_economica_start = content.index('data-sidebar-section-key="gestione-economica"')
        gestione_economica_end = content.index("<!-- FINE CODICE DELLA SIDEBAR -->", gestione_economica_start)
        gestione_economica_section = content[gestione_economica_start:gestione_economica_end]

        self.assertNotIn(f'href="{reverse("lista_educatori")}"', anagrafica_section)
        self.assertIn(f'href="{reverse("lista_educatori")}"', gestione_economica_section)


class SidebarGestioneFinanziariaTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="gestione-finanziaria@example.com",
            email="gestione-finanziaria@example.com",
            password="Password123!",
        )
        SistemaUtentePermessi.objects.create(
            user=self.user,
            permesso_gestione_finanziaria=LivelloPermesso.GESTIONE,
        )

    def test_home_renders_gestione_economica_sidebar_in_requested_order(self):
        SistemaUtentePermessi.objects.filter(user=self.user).update(
            permesso_economia=LivelloPermesso.VISUALIZZAZIONE,
        )
        self.client.force_login(self.user)

        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        content = response.content.decode("utf-8")
        start = content.index('id="sidebar-gestione-economica-panel"')
        end = content.index('data-sidebar-section-key="sistema"', start)
        gestione_economica_section = content[start:end]

        labels_in_order = [
            '<span class="sidebar-link-text">Dashboard</span>',
            "Panoramica Rette",
            "Fatture e scadenze",
            "Spese Mensili",
            "Scambi Retta",
            "Fondi di Accantonamento",
            "<span>Conti Correnti</span>",
            "Movimenti Bancari",
            "Categorie movimenti",
            "Riconciliazione",
            "Report categorie",
            "<span>Impostazioni conti correnti</span>",
            "Conti bancari",
            "Saldi conti",
            "Import estratto conto",
            "Regole categorizzazione",
            "Connessioni PSD2",
            "Provider bancari",
            "Pianificazione sincronizzazione",
        ]

        previous_index = -1
        for label in labels_in_order:
            current_index = gestione_economica_section.index(label)
            self.assertGreater(current_index, previous_index)
            previous_index = current_index

        self.assertNotIn('id="sidebar-gestione-finanziaria-panel"', content)
        self.assertNotIn("Budgeting", gestione_economica_section)
        self.assertNotIn("Fatture Fornitori", gestione_economica_section)

        sistema_start = content.index('id="sidebar-sistema-panel"')
        sistema_section = content[sistema_start:]
        anagrafica_start = content.index('id="sidebar-anagrafica-panel"')
        anagrafica_end = content.index('data-sidebar-section-key="gestione-economica"', anagrafica_start)
        anagrafica_section = content[anagrafica_start:anagrafica_end]
        self.assertIn("<span>Rette e Iscrizioni</span>", anagrafica_section)
        self.assertIn("<span>Impostazioni Rette</span>", anagrafica_section)
        self.assertIn("Tariffe Scambio Retta", anagrafica_section)
        self.assertNotIn("<span>Impostazioni Rette</span>", sistema_section)
        self.assertIn("<span>Impostazioni Fornitori</span>", sistema_section)
        self.assertIn("Fatture in Cloud", sistema_section)
        self.assertIn("Categorie di spesa", sistema_section)
        self.assertNotIn("Fondo accantonamento", content)
        self.assertNotIn("Scambio retta", content)
        self.assertNotIn("Tariffe scambio retta", content)
        self.assertNotIn("<span>Fornitori</span>", content)
        self.assertNotIn("Gestione finanziaria", content)

    def test_home_renders_rubrica_fornitori_inside_anagrafiche_before_ricerche(self):
        SistemaUtentePermessi.objects.filter(user=self.user).update(
            permesso_anagrafica=LivelloPermesso.VISUALIZZAZIONE,
        )
        self.client.force_login(self.user)

        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        content = response.content.decode("utf-8")
        start = content.index('id="sidebar-anagrafica-panel"')
        end = content.index('data-sidebar-section-key="gestione-economica"', start)
        anagrafica_section = content[start:end]

        self.assertIn(f'href="{reverse("lista_fornitori")}"', anagrafica_section)
        self.assertLess(anagrafica_section.index("Rubrica Fornitori"), anagrafica_section.index("Ricerche"))

    def test_home_renders_financial_dashboard_block(self):
        self.client.force_login(self.user)
        today = timezone.localdate()
        MovimentoFinanziario.objects.create(
            data_contabile=today,
            importo=Decimal("120.00"),
            descrizione="Incasso test",
        )
        MovimentoFinanziario.objects.create(
            data_contabile=today,
            importo=Decimal("-35.00"),
            descrizione="Uscita test",
        )
        fornitore = Fornitore.objects.create(denominazione="Fornitore dashboard")
        documento = DocumentoFornitore.objects.create(
            fornitore=fornitore,
            numero_documento="FD-001",
            data_documento=today,
            totale=Decimal("230.00"),
        )
        ScadenzaPagamentoFornitore.objects.create(
            documento=documento,
            data_scadenza=today,
            importo_previsto=Decimal("230.00"),
            importo_pagato=Decimal("30.00"),
        )
        documento_scaduto = DocumentoFornitore.objects.create(
            fornitore=fornitore,
            numero_documento="FD-OLD",
            data_documento=today - timedelta(days=45),
            totale=Decimal("50.00"),
        )
        ScadenzaPagamentoFornitore.objects.create(
            documento=documento_scaduto,
            data_scadenza=today - timedelta(days=35),
            importo_previsto=Decimal("50.00"),
            importo_pagato=Decimal("0.00"),
        )

        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-dashboard-section-id="gestione-finanziaria"', html=False)
        self.assertContains(response, "dashboard-finance-chart-data")
        self.assertContains(response, "dashboard-finanziaria.js")
        self.assertContains(response, "EUR 120,00")
        self.assertContains(response, "EUR 35,00")
        self.assertContains(response, "Fatture fornitori in scadenza")
        self.assertContains(response, "incluse scadute")
        self.assertContains(response, "Fornitore dashboard")
        self.assertContains(response, "FD-001")
        self.assertContains(response, "FD-OLD")
        self.assertContains(response, "Scadenza:")
        self.assertContains(response, "Importo:")
        self.assertContains(response, "Conferma pagamento")
        self.assertContains(response, "EUR 250,00")
        self.assertContains(response, "Previsione mese corrente")
        self.assertContains(response, "Apri budgeting")

    def test_home_financial_dashboard_hides_supplier_payment_actions_for_viewers(self):
        viewer = User.objects.create_user(
            username="financial-dashboard-viewer@example.com",
            email="financial-dashboard-viewer@example.com",
            password="Password123!",
        )
        SistemaUtentePermessi.objects.create(
            user=viewer,
            permesso_gestione_finanziaria=LivelloPermesso.VISUALIZZAZIONE,
        )
        today = timezone.localdate()
        fornitore = Fornitore.objects.create(denominazione="Fornitore viewer dashboard")
        documento = DocumentoFornitore.objects.create(
            fornitore=fornitore,
            numero_documento="VIEW-001",
            data_documento=today,
            totale=Decimal("180.00"),
        )
        scadenza = ScadenzaPagamentoFornitore.objects.create(
            documento=documento,
            data_scadenza=today,
            importo_previsto=Decimal("180.00"),
        )
        pagamento_url = f"{reverse('registra_pagamento_scadenza_fornitore', kwargs={'pk': scadenza.pk})}?popup=1"
        self.client.force_login(viewer)

        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Fatture fornitori in scadenza")
        self.assertContains(response, "Fornitore viewer dashboard")
        self.assertContains(response, reverse("scadenziario_fornitori"))
        self.assertNotContains(response, "Conferma pagamento")
        self.assertNotContains(response, pagamento_url)
        item = response.context["gestione_finanziaria_dashboard"]["fatture_in_scadenza_mese"]["items"][0]
        self.assertNotIn("pagamento_url", item)


class SidebarSistemaTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(
            username="sistema@example.com",
            email="sistema@example.com",
            password="Password123!",
        )
        SistemaUtentePermessi.objects.create(
            user=self.user,
            permesso_sistema=LivelloPermesso.GESTIONE,
        )

    def tearDown(self):
        cache.clear()
        super().tearDown()

    def force_login_sidebar_admin(self, username="sidebar-admin@example.com"):
        admin = User.objects.create_superuser(
            username=username,
            email=username,
            password="Password123!",
        )
        self.client.force_login(admin)
        return admin

    def impostazioni_generali_post_data(self, **overrides):
        data = {
            "terminologia_studente": "studente",
            "formato_visualizzazione_telefono": "it_plus_n3_2_2_3",
            "cronologia_retention_mesi": "24",
            "gestione_iscrizione_corso_anno": "mese_iscrizione_intero",
            "giorno_soglia_iscrizione_corso_anno": "15",
            "osservazioni_solo_autori_modifica": "on",
            "interfaccia_colorata_attiva": "on",
            "modulo_anagrafica_attivo": "on",
            "modulo_famiglie_interessate_attivo": "on",
            "modulo_economia_attivo": "on",
            "modulo_gestione_finanziaria_attivo": "on",
            "modulo_gestione_amministrativa_attivo": "on",
            "modulo_servizi_extra_attivo": "on",
            "font_principale": "manrope",
            "font_titoli": "manrope",
        }
        data.update(overrides)
        return data

    def test_home_renders_school_settings_as_submenu_of_system(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        content = response.content.decode("utf-8")
        start = content.index('id="sidebar-sistema-panel"')
        sistema_section = content[start:]

        labels_in_order = [
            "Impostazioni generali",
            "Crediti",
            "<span>Gestione Account</span>",
            "Utenti",
            "Ruoli",
            "<span>Impostazioni Scuola</span>",
            "Dati Generali Scuola",
            "Anni scolastici",
            "Classi",
        ]

        previous_index = -1
        for label in labels_in_order:
            current_index = sistema_section.index(label)
            self.assertGreater(current_index, previous_index)
            previous_index = current_index

    def test_home_renders_standard_sidebar_top_level_order_for_admin(self):
        self.force_login_sidebar_admin("standard-sidebar-admin@example.com")

        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        content = response.content.decode("utf-8")
        dashboard_index = content.index('<span class="sidebar-link-text">Dashboard</span>')
        calendario_index = content.index('data-sidebar-menu-key="calendario_agenda"')
        reorder_list_index = content.index('id="sidebar-reorder-list"')
        self.assertGreater(calendario_index, dashboard_index)
        self.assertLess(calendario_index, reorder_list_index)
        self.assertNotIn('data-sidebar-section-key="calendario"', content)

        section_keys = [
            "anagrafica",
            "gestione-economica",
            "servizi-extra",
            "famiglie-interessate",
            "archivio-storico",
            "parcheggio",
            "sistema",
        ]

        previous_index = calendario_index
        for section_key in section_keys:
            current_index = content.index(f'data-sidebar-section-key="{section_key}"')
            self.assertGreater(current_index, previous_index)
            previous_index = current_index

        sistema_start = content.index('data-sidebar-section-key="sistema"')
        sistema_section = content[sistema_start:]
        self.assertIn("<span>Impostazioni generali</span>", sistema_section)

    def test_home_hides_sidebar_reorder_controls_for_non_admin_roles(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="sidebar-reorder-list"')
        self.assertNotContains(response, 'id="sidebar-reorder-toggle"')
        self.assertNotContains(response, "Riordina menu")
        self.assertNotContains(response, 'id="sidebar-customize-toggle"')
        self.assertNotContains(response, reverse("sidebar_personalizzazione_sistema"))

    def test_home_renders_sidebar_reorder_controls_for_operational_admin(self):
        self.force_login_sidebar_admin()

        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="sidebar-reorder-list"')
        self.assertContains(response, 'id="sidebar-reorder-toggle"')
        self.assertContains(response, "Riordina menu")
        self.assertContains(response, reverse("sidebar_personalizzazione_sistema"))
        self.assertContains(response, 'id="sidebar-personalizzazione-config"')
        self.assertContains(response, "sidebar-customization.js")
        self.assertContains(response, "sidebar-reorder.js")
        self.assertNotContains(response, 'id="sidebar-customize-toggle"')

    def test_home_ignores_non_admin_sidebar_personalization_config(self):
        SidebarPersonalizzazione.objects.create(
            user=self.user,
            config={
                "version": 1,
                "hidden": ["section:sistema"],
                "order": {"root": ["section:famiglie-interessate"]},
                "custom_sections": [],
            },
        )
        self.client.force_login(self.user)

        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="sidebar-reorder-list"')
        self.assertContains(response, 'id="sidebar-personalizzazione-config"')
        self.assertEqual(
            response.context["sidebar_personalizzazione_config"],
            {"version": 1, "hidden": [], "order": {}, "custom_sections": []},
        )

    def test_saved_sidebar_personalizations_do_not_affect_canonical_menu(self):
        admin = User.objects.create_superuser(
            username="sidebar-admin@example.com",
            email="sidebar-admin@example.com",
            password="Password123!",
        )
        SidebarPersonalizzazione.objects.create(
            user=admin,
            config={
                "version": 1,
                "hidden": ["section:gestione-economica"],
                "order": {"root": ["section:sistema", "section:anagrafica"]},
                "custom_sections": [
                    {
                        "id": "preferiti",
                        "label": "Preferiti",
                        "icon": "student",
                        "links": [
                            {
                                "id": "studenti",
                                "label": "Studenti",
                                "url": reverse("lista_studenti"),
                                "icon": "student",
                            },
                            {
                                "id": "utenti",
                                "label": "Utenti",
                                "url": reverse("lista_utenti"),
                                "icon": "user",
                            },
                        ],
                    },
                ],
            },
        )
        viewer = User.objects.create_user(
            username="sidebar-viewer@example.com",
            email="sidebar-viewer@example.com",
            password="Password123!",
        )
        SistemaUtentePermessi.objects.create(
            user=viewer,
            permesso_anagrafica=LivelloPermesso.VISUALIZZAZIONE,
        )
        SidebarPersonalizzazione.objects.create(
            user=viewer,
            config={
                "version": 1,
                "hidden": ["section:anagrafica"],
                "order": {"root": ["section:famiglie-interessate"]},
                "custom_sections": [],
            },
        )
        self.client.force_login(viewer)

        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.context["sidebar_personalizzazione_config"],
            {
                "version": 1,
                "hidden": [],
                "order": {"root": ["section:sistema", "section:anagrafica"]},
                "custom_sections": [],
            },
        )
        self.assertContains(response, 'data-sidebar-section-key="anagrafica"', html=False)
        self.assertContains(response, 'data-sidebar-menu-key="anagrafica_studenti"', html=False)
        self.assertNotContains(response, 'data-sidebar-section-key="sistema"', html=False)
        self.assertNotContains(response, "Preferiti")

    def test_role_menu_configuration_hides_disabled_sidebar_item(self):
        role = SistemaRuoloPermessi.objects.create(
            nome="Anagrafica senza bambini",
            permesso_anagrafica=LivelloPermesso.VISUALIZZAZIONE,
            voci_menu_disabilitate=["anagrafica_studenti"],
        )
        viewer = User.objects.create_user(
            username="menu-role-viewer@example.com",
            email="menu-role-viewer@example.com",
            password="Password123!",
        )
        SistemaUtentePermessi.objects.create(user=viewer, ruolo_permessi=role)
        self.client.force_login(viewer)

        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-sidebar-section-key="anagrafica"', html=False)
        self.assertNotContains(response, 'data-sidebar-menu-key="anagrafica_studenti"', html=False)
        self.assertContains(response, 'data-sidebar-menu-key="anagrafica_familiari"', html=False)

    def test_role_menu_configuration_hides_empty_sidebar_section(self):
        role = SistemaRuoloPermessi.objects.create(
            nome="Anagrafica menu spento",
            permesso_anagrafica=LivelloPermesso.VISUALIZZAZIONE,
            voci_menu_disabilitate=[
                "anagrafica_studenti",
                "anagrafica_familiari",
                "anagrafica_famiglie",
                "anagrafica_ricerche",
            ],
        )
        viewer = User.objects.create_user(
            username="menu-empty-viewer@example.com",
            email="menu-empty-viewer@example.com",
            password="Password123!",
        )
        SistemaUtentePermessi.objects.create(user=viewer, ruolo_permessi=role)
        self.client.force_login(viewer)

        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'data-sidebar-section-key="anagrafica"', html=False)

    def test_role_menu_configuration_hides_direct_calendar_link(self):
        role = SistemaRuoloPermessi.objects.create(
            nome="Calendario spento",
            permesso_calendario=LivelloPermesso.VISUALIZZAZIONE,
            voci_menu_disabilitate=["calendario_agenda"],
        )
        viewer = User.objects.create_user(
            username="menu-calendar-viewer@example.com",
            email="menu-calendar-viewer@example.com",
            password="Password123!",
        )
        SistemaUtentePermessi.objects.create(user=viewer, ruolo_permessi=role)
        self.client.force_login(viewer)

        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'data-sidebar-menu-key="calendario_agenda"', html=False)

    def test_sidebar_personalization_endpoint_saves_admin_config(self):
        admin = self.force_login_sidebar_admin("sidebar-save-admin@example.com")
        payload = {
            "config": {
                "hidden": ["section:gestione-finanziaria", "chiave non valida"],
                "order": {"root": ["section:sistema", "section:gestione-finanziaria"]},
                "custom_sections": [
                    {
                        "id": "preferiti",
                        "label": "Preferiti",
                        "icon": "star",
                        "links": [
                            {"id": "movimenti", "label": "Movimenti", "url": "/gestione-finanziaria/movimenti/", "icon": "finance"},
                            {"id": "bad", "label": "Pericoloso", "url": "javascript:alert(1)", "icon": "bug"},
                        ],
                    }
                ],
            }
        }

        response = self.client.post(
            reverse("sidebar_personalizzazione_sistema"),
            data=json.dumps(payload),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        saved = SidebarPersonalizzazione.objects.get(user=admin)
        self.assertEqual(saved.config["hidden"], ["section:gestione-finanziaria"])
        self.assertEqual(saved.config["order"]["root"], ["section:sistema", "section:gestione-finanziaria"])
        self.assertEqual(saved.config["custom_sections"][0]["label"], "Preferiti")
        self.assertEqual(len(saved.config["custom_sections"][0]["links"]), 1)
        self.assertEqual(saved.config["custom_sections"][0]["links"][0]["url"], "/gestione-finanziaria/movimenti/")

    def test_sidebar_personalization_endpoint_rejects_non_admin_config(self):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("sidebar_personalizzazione_sistema"),
            data=json.dumps({"config": {"order": {"root": ["section:sistema"]}}}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 403)
        self.assertFalse(SidebarPersonalizzazione.objects.filter(user=self.user).exists())

    def test_sidebar_personalization_endpoint_keeps_url_like_order_keys(self):
        admin = self.force_login_sidebar_admin("sidebar-order-admin@example.com")
        parent_key = "nav:section:gestione-finanziaria:0"
        url_key = "link:/gestione-finanziaria/movimenti/?search=Rossi+Mario&filter=a;b,c(1)"
        long_key = "link:/gestione-finanziaria/report/categorie-mensile/?q=" + ("x" * 230) + "+ok"
        payload = {
            "config": {
                "hidden": [url_key],
                "order": {
                    parent_key: [long_key, url_key],
                },
                "custom_sections": [],
            }
        }

        response = self.client.post(
            reverse("sidebar_personalizzazione_sistema"),
            data=json.dumps(payload),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        saved = SidebarPersonalizzazione.objects.get(user=admin)
        self.assertEqual(saved.config["hidden"], [url_key])
        self.assertEqual(saved.config["order"][parent_key], [long_key, url_key])

    def test_sidebar_personalization_endpoint_resets_user_config(self):
        admin = self.force_login_sidebar_admin("sidebar-reset-admin@example.com")
        SidebarPersonalizzazione.objects.create(
            user=admin,
            config={"version": 1, "hidden": ["section:sistema"], "order": {}, "custom_sections": []},
        )

        response = self.client.post(
            reverse("sidebar_personalizzazione_sistema"),
            data=json.dumps({"reset": True}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(SidebarPersonalizzazione.objects.filter(user=admin).exists())

    def test_sidebar_collapse_toggle_lives_inside_sidebar(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        content = response.content.decode("utf-8")
        sidebar_start = content.index('<aside class="sidebar">')
        header_end = content.index("</header>")
        button_index = content.index('id="sidebar-collapse-btn"')
        self.assertGreater(button_index, sidebar_start)
        self.assertGreater(button_index, header_end)
        self.assertContains(response, 'class="sidebar-topbar"')
        self.assertNotContains(response, 'class="header-menu-btn" id="sidebar-collapse-btn"')

    def test_general_settings_renders_module_toggles_with_new_layout(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse("impostazioni_generali_sistema"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Controllo sistema")
        self.assertContains(response, "Moduli del software")
        self.assertContains(response, "Cronologia operazioni")
        self.assertContains(response, 'name="cronologia_retention_mesi"')
        self.assertContains(response, 'name="interfaccia_colorata_attiva"')
        self.assertContains(response, 'name="stile_streamline_attivo"')
        self.assertContains(response, "Stile Streamline")
        self.assertContains(response, 'name="stile_iconscout_3d_attivo"')
        self.assertContains(response, "Stile IconScout 3D")
        self.assertContains(response, 'name="modulo_calendario_attivo"')
        self.assertContains(response, 'class="settings-module-grid"')

    def test_general_settings_switches_colorful_interface_class(self):
        SistemaImpostazioniGenerali.objects.create(interfaccia_colorata_attiva=False)
        self.client.force_login(self.user)

        response = self.client.get(reverse("impostazioni_generali_sistema"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'class="ui-uniform-modules module-sistema"')
        self.assertNotContains(response, "ui-colorful-modules")

    def test_general_settings_switches_streamline_icon_style(self):
        SistemaImpostazioniGenerali.objects.create(stile_streamline_attivo=True)
        self.client.force_login(self.user)

        response = self.client.get(reverse("impostazioni_generali_sistema"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "ui-streamline-icons")
        self.assertContains(response, "arboris-streamline-icons.svg")
        self.assertContains(response, "js/core/streamline-icons.js")

    def test_general_settings_switches_iconscout_3d_icon_style(self):
        SistemaImpostazioniGenerali.objects.create(stile_iconscout_3d_attivo=True)
        self.client.force_login(self.user)

        response = self.client.get(reverse("impostazioni_generali_sistema"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "ui-iconscout-3d-icons")
        self.assertContains(response, "arboris-iconscout-3d-icons.svg")
        self.assertContains(response, "IconScout 3D")
        self.assertContains(response, "js/core/streamline-icons.js")

    def test_general_settings_can_disable_module_globally(self):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("impostazioni_generali_sistema"),
            self.impostazioni_generali_post_data(),
        )

        self.assertRedirects(response, reverse("impostazioni_generali_sistema"))
        impostazioni = SistemaImpostazioniGenerali.objects.get()
        self.assertFalse(impostazioni.modulo_calendario_attivo)

    def test_general_settings_cleanup_audit_log_by_retention_period(self):
        self.client.force_login(self.user)
        old_entry = SistemaOperazioneCronologia.objects.create(
            azione="update",
            modulo="sistema",
            app_label="sistema",
            model_name="test",
            model_verbose_name="Test",
            oggetto_label="Vecchio",
            descrizione="Vecchia operazione",
        )
        recent_entry = SistemaOperazioneCronologia.objects.create(
            azione="update",
            modulo="sistema",
            app_label="sistema",
            model_name="test",
            model_verbose_name="Test",
            oggetto_label="Recente",
            descrizione="Operazione recente",
        )
        SistemaOperazioneCronologia.objects.filter(pk=old_entry.pk).update(
            data_operazione=timezone.now() - timedelta(days=400)
        )
        SistemaOperazioneCronologia.objects.filter(pk=recent_entry.pk).update(
            data_operazione=timezone.now() - timedelta(days=30)
        )

        response = self.client.post(
            reverse("impostazioni_generali_sistema"),
            self.impostazioni_generali_post_data(cronologia_retention_mesi="12"),
        )

        self.assertRedirects(response, reverse("impostazioni_generali_sistema"))
        impostazioni = SistemaImpostazioniGenerali.objects.get()
        self.assertEqual(impostazioni.cronologia_retention_mesi, 12)
        self.assertFalse(SistemaOperazioneCronologia.objects.filter(pk=old_entry.pk).exists())
        self.assertTrue(SistemaOperazioneCronologia.objects.filter(pk=recent_entry.pk).exists())

    def test_disabled_module_is_hidden_and_blocked_even_for_superuser(self):
        SistemaImpostazioniGenerali.objects.create(modulo_calendario_attivo=False)
        admin = User.objects.create_superuser(
            username="admin@example.com",
            email="admin@example.com",
            password="Password123!",
        )
        self.client.force_login(admin)

        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context["can_view_calendario"])
        self.assertNotContains(response, 'id="sidebar-calendario-panel"')

        response = self.client.get(reverse("calendario_agenda"))

        self.assertRedirects(response, reverse("home"))


class GlobalReadOnlyModuleInterfaceTests(TestCase):
    def setUp(self):
        cache.clear()

    def create_viewer(self, module_name):
        user = User.objects.create_user(
            username=f"{module_name}-viewer@example.com",
            email=f"{module_name}-viewer@example.com",
            password="Password123!",
        )
        permission_field = {
            "anagrafica": "permesso_anagrafica",
            "famiglie_interessate": "permesso_famiglie_interessate",
            "economia": "permesso_economia",
            "sistema": "permesso_sistema",
            "calendario": "permesso_calendario",
            "servizi_extra": "permesso_servizi_extra",
            "gestione_finanziaria": "permesso_gestione_finanziaria",
            "gestione_amministrativa": "permesso_gestione_amministrativa",
        }[module_name]
        SistemaUtentePermessi.objects.create(
            user=user,
            **{permission_field: LivelloPermesso.VISUALIZZAZIONE},
        )
        return user

    def test_view_only_body_class_and_context_apply_to_all_main_modules(self):
        routes = [
            ("anagrafica", "lista_studenti", "module-anagrafica"),
            ("famiglie_interessate", "lista_famiglie_interessate", "module-famiglie_interessate"),
            ("economia", "lista_iscrizioni", "module-economia"),
            ("sistema", "lista_classi", "module-sistema"),
            ("calendario", "lista_eventi_calendario", "module-calendario"),
            ("servizi_extra", "lista_servizi_extra", "module-servizi_extra"),
            ("gestione_finanziaria", "lista_movimenti_finanziari", "module-gestione_finanziaria"),
            ("gestione_amministrativa", "lista_dipendenti", "module-gestione_amministrativa"),
        ]

        for module_name, route_name, body_class in routes:
            with self.subTest(module=module_name):
                self.client.force_login(self.create_viewer(module_name))

                response = self.client.get(reverse(route_name))

                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.context["current_permission_module"], module_name)
                self.assertFalse(response.context["can_manage_current_module"])
                self.assertTrue(response.context["current_module_view_only"])
                self.assertContains(response, f"{body_class} module-view-only", html=False)

    def test_global_view_only_css_covers_common_crud_controls(self):
        css = (settings.BASE_DIR / "static" / "css" / "style.css").read_text(encoding="utf-8")

        required_selectors = [
            '.module-view-only a.btn-primary[href*="/nuovo"]',
            '.module-view-only a.btn-primary[href*="/nuova"]',
            '.module-view-only a.btn-secondary[href*="/nuovo"]',
            '.module-view-only a.btn-secondary[href*="/nuova"]',
            '.module-view-only .page-head-actions a.btn-secondary[href*="/duplicati"]',
            '.module-view-only .page-head-actions a.btn-secondary[href*="/ripulisci"]',
            '.module-view-only a[href*="/elimina/"]',
            '.module-view-only form[action*="/elimina/"] button[type="submit"]',
            ".module-view-only .table-icon-link-danger",
            ".module-view-only .observation-icon-btn-danger",
            ".module-view-only [id^=\"enable-edit-\"]",
            ".module-view-only [data-bulk-toolbar]",
            ".module-view-only [data-bulk-submit]",
            ".module-view-only [data-bulk-checkbox]",
            ".module-view-only .finance-bulk-select-col",
            ".module-view-only .active-toggle-form",
            ".module-view-only .actions-cell",
        ]
        for selector in required_selectors:
            with self.subTest(selector=selector):
                self.assertIn(selector, css)


class ActiveToggleTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username="toggle-admin@example.com",
            email="toggle-admin@example.com",
            password="Password123!",
        )
        SistemaUtentePermessi.objects.create(
            user=self.admin,
            permesso_gestione_finanziaria=LivelloPermesso.GESTIONE,
        )
        self.viewer = User.objects.create_user(
            username="toggle-viewer@example.com",
            email="toggle-viewer@example.com",
            password="Password123!",
        )
        SistemaUtentePermessi.objects.create(
            user=self.viewer,
            permesso_gestione_finanziaria=LivelloPermesso.VISUALIZZAZIONE,
        )
        self.fornitore = Fornitore.objects.create(denominazione="Fornitore toggle")

    def post_toggle(self, user, value):
        self.client.force_login(user)
        return self.client.post(
            reverse("toggle_active_state"),
            {
                "model": "gestione_finanziaria.fornitore",
                "pk": self.fornitore.pk,
                "field": "attivo",
                "value": value,
                "ajax": "1",
            },
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )

    def test_management_user_can_toggle_registered_active_field(self):
        response = self.post_toggle(self.admin, "0")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["value"], False)
        self.fornitore.refresh_from_db()
        self.assertFalse(self.fornitore.attivo)

    def test_view_only_user_cannot_toggle_active_field(self):
        response = self.post_toggle(self.viewer, "0")

        self.assertEqual(response.status_code, 403)
        self.fornitore.refresh_from_db()
        self.assertTrue(self.fornitore.attivo)

    def test_financial_supplier_list_renders_global_toggle(self):
        self.client.force_login(self.admin)

        response = self.client.get(reverse("lista_fornitori"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-active-toggle-form')
        self.assertContains(response, 'name="model" value="gestione_finanziaria.fornitore"', html=False)


class RuoliUtenteTests(TestCase):
    def setUp(self):
        self.admin_role = SistemaRuoloPermessi.objects.create(
            nome="Amministratore operativo",
            colore_principale="#f2c94c",
            controllo_completo=True,
            amministratore_operativo=True,
            accesso_backup_database=True,
            permesso_sistema=LivelloPermesso.GESTIONE,
        )
        self.user = User.objects.create_user(
            username="ruoli@example.com",
            email="ruoli@example.com",
            password="Password123!",
            first_name="Ada",
            last_name="Lovelace",
        )
        SistemaUtentePermessi.objects.create(
            user=self.user,
            ruolo_permessi=self.admin_role,
        )

    def test_role_drives_permissions_and_theme(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse("lista_ruoli_utenti"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Amministratore operativo")
        self.assertContains(response, "--primary: #f2c94c")
        self.assertContains(response, reverse("crea_ruolo_utente"))

    def test_role_form_renders_sidebar_menu_items(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse("modifica_ruolo_utente", args=[self.admin_role.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Voci menu")
        self.assertContains(response, 'name="voci_menu_attive"', html=False)
        self.assertContains(response, 'value="anagrafica_studenti"', html=False)
        self.assertContains(response, 'value="gestione_finanziaria_dashboard"', html=False)

    def test_role_form_saves_disabled_sidebar_menu_items(self):
        self.client.force_login(self.user)
        active_menu_keys = [
            key for key in SIDEBAR_MENU_ITEM_KEYS if key != "gestione_finanziaria_dashboard"
        ]

        response = self.client.post(
            reverse("modifica_ruolo_utente", args=[self.admin_role.pk]),
            {
                "nome": self.admin_role.nome,
                "descrizione": self.admin_role.descrizione,
                "colore_principale": self.admin_role.colore_principale,
                "attivo": "on",
                "amministratore_operativo": "on",
                "accesso_backup_database": "on",
                "controllo_completo": "on",
                "permesso_anagrafica": LivelloPermesso.GESTIONE,
                "permesso_famiglie_interessate": LivelloPermesso.GESTIONE,
                "permesso_economia": LivelloPermesso.GESTIONE,
                "permesso_sistema": LivelloPermesso.GESTIONE,
                "permesso_calendario": LivelloPermesso.GESTIONE,
                "permesso_gestione_finanziaria": LivelloPermesso.GESTIONE,
                "permesso_gestione_amministrativa": LivelloPermesso.GESTIONE,
                "permesso_servizi_extra": LivelloPermesso.GESTIONE,
                "sidebar_menu_form_present": "1",
                "voci_menu_attive": active_menu_keys,
            },
        )

        self.assertRedirects(response, reverse("modifica_ruolo_utente", args=[self.admin_role.pk]))
        self.admin_role.refresh_from_db()
        self.assertEqual(self.admin_role.voci_menu_disabilitate, ["gestione_finanziaria_dashboard"])

    def test_user_form_uses_role_instead_of_user_level_permissions(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse("modifica_utente", args=[self.user.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Permessi ereditati dal ruolo")
        self.assertContains(response, "Per cambiare i permessi modifica il ruolo collegato")
        self.assertContains(response, "Utente attivo")
        self.assertContains(response, "Gestione finanziaria")
        self.assertNotContains(response, "Modulo anagrafica")

    def test_user_form_renders_role_popup_controls(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse("crea_utente"), {"popup": "1"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="add-ruolo-permessi-btn"', html=False)
        self.assertContains(response, 'id="edit-ruolo-permessi-btn"', html=False)
        self.assertContains(response, 'id="delete-ruolo-permessi-btn"', html=False)
        self.assertContains(response, 'data-related-type="ruolo_permessi"', html=False)
        self.assertContains(response, 'relatedType: "ruolo_permessi"', html=False)

    def test_role_popup_create_updates_user_role_select(self):
        self.client.force_login(self.user)

        response = self.client.post(
            f"{reverse('crea_ruolo_utente')}?popup=1&target_input_name=ruolo_permessi",
            {
                "nome": "Ruolo popup",
                "descrizione": "",
                "colore_principale": "#417690",
                "attivo": "on",
                "permesso_anagrafica": LivelloPermesso.NESSUNO,
                "permesso_famiglie_interessate": LivelloPermesso.NESSUNO,
                "permesso_economia": LivelloPermesso.NESSUNO,
                "permesso_sistema": LivelloPermesso.GESTIONE,
                "permesso_calendario": LivelloPermesso.NESSUNO,
                "permesso_gestione_finanziaria": LivelloPermesso.NESSUNO,
                "permesso_gestione_amministrativa": LivelloPermesso.NESSUNO,
                "permesso_servizi_extra": LivelloPermesso.NESSUNO,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'const action = "select";', html=False)
        self.assertContains(response, 'const fieldName = "ruolo_permessi";', html=False)
        self.assertContains(response, 'const objectLabel = "Ruolo popup";', html=False)
        self.assertContains(response, 'const targetInputName = "ruolo_permessi";', html=False)

    def test_user_permission_lists_include_financial_management_and_interested_families_modules(self):
        self.client.force_login(self.user)

        users_response = self.client.get(reverse("lista_utenti"))
        roles_response = self.client.get(reverse("lista_ruoli_utenti"))

        self.assertEqual(users_response.status_code, 200)
        self.assertEqual(roles_response.status_code, 200)
        self.assertContains(users_response, "Gestione finanziaria")
        self.assertContains(roles_response, "Gestione finanziaria")
        self.assertContains(users_response, "Famiglie interessate")
        self.assertContains(roles_response, "Famiglie interessate")

    def test_role_permissions_override_stale_user_level_full_control(self):
        viewer_role = SistemaRuoloPermessi.objects.create(
            nome="Sistema sola visualizzazione",
            colore_principale="#64748b",
            permesso_sistema=LivelloPermesso.VISUALIZZAZIONE,
        )
        viewer = User.objects.create_user(
            username="stale-viewer@example.com",
            email="stale-viewer@example.com",
            password="Password123!",
        )
        SistemaUtentePermessi.objects.create(
            user=viewer,
            ruolo_permessi=viewer_role,
            controllo_completo=True,
            permesso_sistema=LivelloPermesso.GESTIONE,
        )
        self.client.force_login(viewer)

        response = self.client.get(reverse("lista_utenti"))

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context["can_manage_sistema"])
        self.assertContains(response, "module-view-only")

        response = self.client.get(reverse("crea_utente"))

        self.assertRedirects(response, reverse("home"))

    def test_header_settings_dropdown_renders_system_links(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse("lista_utenti"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "header-settings-dropdown")
        self.assertContains(response, "header-settings-icon")
        self.assertNotContains(response, "<span>IMPOSTAZIONI</span>", html=True)
        self.assertNotContains(response, "Admin tecnico")
        self.assertContains(response, "Gestione Account")
        self.assertContains(response, "Backup e Cronologia")
        self.assertContains(response, "Impostazioni Scuola")
        self.assertContains(response, reverse("lista_utenti"))
        self.assertContains(response, reverse("lista_ruoli_utenti"))

    def test_admin_can_delete_other_user(self):
        self.client.force_login(self.user)
        target = User.objects.create_user(
            username="da-eliminare@example.com",
            email="da-eliminare@example.com",
            password="Password123!",
            first_name="Grace",
            last_name="Hopper",
        )
        SistemaUtentePermessi.objects.create(
            user=target,
            ruolo_permessi=self.admin_role,
        )

        response = self.client.post(reverse("elimina_utente", args=[target.pk]))

        self.assertRedirects(response, reverse("lista_utenti"))
        self.assertFalse(User.objects.filter(pk=target.pk).exists())

    def test_admin_cannot_delete_current_user(self):
        self.client.force_login(self.user)

        response = self.client.post(reverse("elimina_utente", args=[self.user.pk]))

        self.assertRedirects(response, reverse("modifica_utente", args=[self.user.pk]))
        self.assertTrue(User.objects.filter(pk=self.user.pk).exists())


class PopupManifestTests(TestCase):
    def test_popup_manifest_exposes_metodo_pagamento_crud_routes(self):
        manifest = build_popup_manifest()

        self.assertIn("metodo_pagamento", manifest)
        self.assertEqual(manifest["metodo_pagamento"]["add"], reverse("crea_metodo_pagamento"))
        self.assertIn("__ID__", manifest["metodo_pagamento"]["edit"])
        self.assertIn("__ID__", manifest["metodo_pagamento"]["delete"])

    def test_popup_manifest_exposes_categoria_spesa_crud_routes(self):
        manifest = build_popup_manifest()

        self.assertIn("categoria_spesa", manifest)
        self.assertEqual(manifest["categoria_spesa"]["add"], reverse("crea_categoria_spesa"))
        self.assertIn("__ID__", manifest["categoria_spesa"]["edit"])
        self.assertIn("__ID__", manifest["categoria_spesa"]["delete"])

    def test_popup_manifest_exposes_supplier_document_related_routes(self):
        manifest = build_popup_manifest()

        expected = {
            "fornitore": "crea_fornitore",
            "conto_bancario": "crea_conto_bancario",
            "movimento_finanziario": "crea_movimento_manuale",
        }
        for key, add_route in expected.items():
            self.assertIn(key, manifest)
            self.assertEqual(manifest[key]["add"], reverse(add_route))
            self.assertIn("__ID__", manifest[key]["edit"])
            self.assertIn("__ID__", manifest[key]["delete"])

    def test_popup_manifest_exposes_role_crud_routes(self):
        manifest = build_popup_manifest()

        self.assertIn("ruolo_permessi", manifest)
        self.assertEqual(manifest["ruolo_permessi"]["add"], reverse("crea_ruolo_utente"))
        self.assertIn("__ID__", manifest["ruolo_permessi"]["edit"])
        self.assertIn("__ID__", manifest["ruolo_permessi"]["delete"])


class ScuolaSistemaInterfaceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="scuola-gestione@example.com",
            email="scuola-gestione@example.com",
            password="Password123!",
        )
        SistemaUtentePermessi.objects.create(
            user=self.user,
            permesso_sistema=LivelloPermesso.GESTIONE,
        )

        self.regione = Regione.objects.create(nome="Emilia-Romagna")
        self.provincia = Provincia.objects.create(nome="Bologna", sigla="BO", regione=self.regione)
        self.citta = Citta.objects.create(nome="Bologna", provincia=self.provincia, attiva=True)
        self.indirizzo = Indirizzo.objects.create(
            via="Via Test",
            numero_civico="1",
            citta=self.citta,
        )

    def test_scuola_page_uses_updated_title_and_inline_scopes(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse("scuola_sistema"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Dati Generali Scuola")
        self.assertContains(response, 'data-inline-scope="telefoni"', html=False)
        self.assertContains(response, 'data-inline-scope="email"', html=False)
        self.assertContains(response, 'data-inline-scope="socials"', html=False)
        self.assertContains(response, reverse("scuola_crea_indirizzo"))

    def test_school_address_popup_routes_are_available_with_system_permissions(self):
        self.client.force_login(self.user)

        create_response = self.client.get(reverse("scuola_crea_indirizzo"), {"popup": "1"})
        edit_response = self.client.get(reverse("scuola_modifica_indirizzo", args=[self.indirizzo.pk]), {"popup": "1"})
        delete_response = self.client.get(reverse("scuola_elimina_indirizzo", args=[self.indirizzo.pk]), {"popup": "1"})

        self.assertEqual(create_response.status_code, 200)
        self.assertEqual(edit_response.status_code, 200)
        self.assertEqual(delete_response.status_code, 200)


class BackupDatabaseAccessTests(TestCase):
    def setUp(self):
        self.password = "Password123!"
        self.operatore = User.objects.create_user(
            username="operatore-backup@example.com",
            email="operatore-backup@example.com",
            password=self.password,
        )
        SistemaUtentePermessi.objects.create(
            user=self.operatore,
            permesso_sistema=LivelloPermesso.GESTIONE,
        )

        self.amministratore = User.objects.create_user(
            username="amministratore-backup@example.com",
            email="amministratore-backup@example.com",
            password=self.password,
        )
        SistemaUtentePermessi.objects.create(
            user=self.amministratore,
            ruolo=RuoloUtente.AMMINISTRATORE,
            permesso_sistema=LivelloPermesso.GESTIONE,
        )

        self.staff_non_admin = User.objects.create_user(
            username="staff-backup@example.com",
            email="staff-backup@example.com",
            password=self.password,
            is_staff=True,
        )
        SistemaUtentePermessi.objects.create(
            user=self.staff_non_admin,
            permesso_sistema=LivelloPermesso.GESTIONE,
        )

        self.superuser = User.objects.create_superuser(
            username="superuser-backup@example.com",
            email="superuser-backup@example.com",
            password=self.password,
        )

    def test_backup_database_page_denies_non_admin_users(self):
        self.client.force_login(self.operatore)

        response = self.client.get(reverse("backup_database_sistema"))

        self.assertRedirects(response, reverse("home"))

    def test_backup_database_page_allows_administrator_role(self):
        self.client.force_login(self.amministratore)

        response = self.client.get(reverse("backup_database_sistema"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Backup Database")

    def test_backup_download_link_does_not_arm_long_wait_cursor(self):
        self.client.force_login(self.amministratore)
        with TemporaryDirectory() as tmpdir:
            with override_settings(MEDIA_ROOT=tmpdir):
                backup = SistemaDatabaseBackup.objects.create(
                    nome_file="backup-manuale.sql.gz",
                    tipo_backup="manuale",
                    dimensione_file_bytes=12,
                    creato_da=self.amministratore,
                    file_backup=SimpleUploadedFile(
                        "backup-manuale.sql.gz",
                        b"backup-source",
                        content_type="application/gzip",
                    ),
                )

                response = self.client.get(reverse("backup_database_sistema"))

        download_url = reverse("scarica_backup_database", kwargs={"pk": backup.pk})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, f'href="{download_url}"')
        self.assertContains(response, 'download="backup-manuale.sql.gz"')
        self.assertContains(response, 'data-long-wait-skip="1"')

    def test_backup_database_page_denies_staff_user_without_admin_role(self):
        self.client.force_login(self.staff_non_admin)

        response = self.client.get(reverse("backup_database_sistema"))

        self.assertRedirects(response, reverse("home"))

    def test_backup_database_page_allows_superuser(self):
        self.client.force_login(self.superuser)

        response = self.client.get(reverse("backup_database_sistema"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Backup Database")

    def test_backup_database_page_renders_chunked_restore_upload(self):
        self.client.force_login(self.amministratore)

        response = self.client.get(reverse("backup_database_sistema"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "data-restore-chunked-upload-form")
        self.assertContains(response, "upload_restore_file_chunk")
        self.assertContains(response, reverse("backup_database_restore_chunk_upload"))
        self.assertContains(response, "prepare_restore_storage_reference")

    def test_backup_database_page_renders_restore_error_copy_button(self):
        self.client.force_login(self.amministratore)
        SistemaDatabaseRestoreJob.objects.create(
            stato=StatoRipristinoDatabase.ERRORE,
            percorso_file="manual_restore/restore.sql.gz",
            nome_file_originale="restore.sql.gz",
            messaggio_errore="ERROR: cannot drop constraint sistema_scuola_pkey\nDETAIL: esempio log completo",
        )

        response = self.client.get(reverse("backup_database_sistema"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Copia log")
        self.assertContains(response, "data-copy-text=")
        self.assertContains(response, "cannot drop constraint sistema_scuola_pkey")

    def test_backup_database_page_renders_restore_job_remove_button(self):
        self.client.force_login(self.amministratore)
        job = SistemaDatabaseRestoreJob.objects.create(
            stato=StatoRipristinoDatabase.IN_CORSO,
            percorso_file="manual_restore/restore.sql.gz",
            nome_file_originale="restore.sql.gz",
        )

        response = self.client.get(reverse("backup_database_sistema"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse("rimuovi_job_ripristino_database", kwargs={"pk": job.pk}))
        self.assertContains(response, "Rimuovi job")

    def test_remove_restore_job_deletes_job_and_clears_pending_session(self):
        self.client.force_login(self.amministratore)
        job = SistemaDatabaseRestoreJob.objects.create(
            stato=StatoRipristinoDatabase.IN_ATTESA_CONFERMA,
            percorso_file="manual_restore/restore.sql.gz",
            nome_file_originale="restore.sql.gz",
        )
        session = self.client.session
        session["sistema_db_restore_job_id"] = job.pk
        session.save()

        response = self.client.post(reverse("rimuovi_job_ripristino_database", kwargs={"pk": job.pk}))

        self.assertRedirects(response, reverse("backup_database_sistema"))
        self.assertFalse(SistemaDatabaseRestoreJob.objects.filter(pk=job.pk).exists())
        self.assertNotIn("sistema_db_restore_job_id", self.client.session)

    def test_chunked_restore_upload_creates_pending_restore_job(self):
        self.client.force_login(self.amministratore)
        content = b"backup-data-from-chunks"
        chunks = [content[:8], content[8:]]
        upload_id = "restorechunk123"

        with TemporaryDirectory() as tmpdir:
            with override_settings(MEDIA_ROOT=tmpdir):
                for index, chunk in enumerate(chunks):
                    response = self.client.post(
                        reverse("backup_database_restore_chunk_upload"),
                        data=json.dumps(
                            {
                                "action": "upload_restore_file_chunk",
                                "upload_id": upload_id,
                                "file_name": "restore.sql.gz",
                                "file_size": len(content),
                                "chunk_index": index,
                                "total_chunks": len(chunks),
                                "data": base64.b64encode(chunk).decode("ascii"),
                            }
                        ),
                        content_type="application/json",
                    )
                    self.assertEqual(response.status_code, 200)

                payload = response.json()
                self.assertTrue(payload["ok"])
                self.assertTrue(payload["complete"])
                self.assertEqual(payload["redirect"], reverse("backup_database_sistema"))

                job = SistemaDatabaseRestoreJob.objects.get()
                self.assertEqual(job.nome_file_originale, "restore.sql.gz")
                self.assertEqual(job.dimensione_file_bytes, len(content))
                self.assertTrue(default_storage.exists(job.percorso_file))
                self.assertEqual(self.client.session["sistema_db_restore_job_id"], job.pk)

                cancel_or_delete_restore_job(job)
                self.assertFalse(default_storage.exists(job.percorso_file))

    def test_storage_restore_reference_creates_pending_restore_job(self):
        self.client.force_login(self.amministratore)

        with TemporaryDirectory() as tmpdir:
            with override_settings(MEDIA_ROOT=tmpdir):
                storage_name = default_storage.save(
                    "manual_restore/restore.sql.gz",
                    ContentFile(b"backup-data-from-storage"),
                )
                response = self.client.post(
                    reverse("backup_database_sistema"),
                    {
                        "action": "prepare_restore_storage_reference",
                        "storage_reference": storage_name,
                    },
                )

                self.assertEqual(response.status_code, 200)
                job = SistemaDatabaseRestoreJob.objects.get()
                self.assertEqual(job.percorso_file, storage_name)
                self.assertEqual(job.nome_file_originale, "restore.sql.gz")
                self.assertEqual(self.client.session["sistema_db_restore_job_id"], job.pk)

                cancel_or_delete_restore_job(job)


class BetaFeedbackTests(TestCase):
    def setUp(self):
        self.password = "Password123!"
        self.user = User.objects.create_user(
            username="operatore-feedback@example.com",
            email="operatore-feedback@example.com",
            password=self.password,
            first_name="Mario",
            last_name="Rossi",
        )
        SistemaUtentePermessi.objects.create(user=self.user)

        self.admin = User.objects.create_user(
            username="admin-feedback@example.com",
            email="admin-feedback@example.com",
            password=self.password,
        )
        SistemaUtentePermessi.objects.create(
            user=self.admin,
            ruolo=RuoloUtente.AMMINISTRATORE,
            permesso_sistema=LivelloPermesso.GESTIONE,
        )

        self.system_operator = User.objects.create_user(
            username="system-operator-feedback@example.com",
            email="system-operator-feedback@example.com",
            password=self.password,
        )
        SistemaUtentePermessi.objects.create(
            user=self.system_operator,
            permesso_sistema=LivelloPermesso.GESTIONE,
        )

        self.superuser = User.objects.create_superuser(
            username="superuser-feedback@example.com",
            email="superuser-feedback@example.com",
            password=self.password,
        )

    def test_base_layout_renders_beta_feedback_buttons_for_authenticated_users(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "beta-feedback-widget")
        self.assertContains(response, reverse("crea_feedback_beta"))
        self.assertContains(response, "Segnala un bug")
        self.assertContains(response, "Suggerisci una funzione")
        self.assertContains(response, "#bug")
        self.assertContains(response, "#lightbulb")
        self.assertContains(response, "beta-feedback.js")

    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
        BETA_FEEDBACK_RECIPIENT_EMAIL="gliptica.software@gmail.com",
        DEFAULT_FROM_EMAIL="Arboris Test <noreply@example.com>",
    )
    def test_authenticated_user_can_submit_feedback_and_email_is_sent(self):
        mail.outbox = []
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("crea_feedback_beta"),
            {
                "tipo": TipoFeedbackSegnalazione.BUG,
                "messaggio": "Il calendario non salva la data selezionata.",
                "pagina_url": "http://testserver/calendario/?view=month",
                "pagina_path": "/calendario/?view=month",
                "pagina_titolo": "Calendario - Arboris",
                "breadcrumb": "Home > Calendario",
            },
            HTTP_USER_AGENT="Firefox Test",
            HTTP_REFERER="http://testserver/calendario/",
            HTTP_X_FORWARDED_FOR="203.0.113.10",
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ok"])
        feedback = FeedbackSegnalazione.objects.get()
        self.assertEqual(feedback.tipo, TipoFeedbackSegnalazione.BUG)
        self.assertEqual(feedback.utente_nome, "Mario Rossi")
        self.assertEqual(feedback.utente_email, "operatore-feedback@example.com")
        self.assertEqual(feedback.pagina_path, "/calendario/?view=month")
        self.assertEqual(feedback.breadcrumb, "Home > Calendario")
        self.assertEqual(feedback.user_agent, "Firefox Test")
        self.assertEqual(feedback.ip_address, "203.0.113.10")
        self.assertIsNotNone(feedback.email_inviata_at)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["gliptica.software@gmail.com"])
        self.assertIn("[Arboris Beta][Bug]", mail.outbox[0].subject)
        self.assertIn("Il calendario non salva la data selezionata.", mail.outbox[0].body)
        self.assertIn("Home > Calendario", mail.outbox[0].body)

    def test_feedback_page_denies_non_admin_system_user(self):
        self.client.force_login(self.system_operator)

        response = self.client.get(reverse("lista_feedback_segnalazioni"))

        self.assertRedirects(response, reverse("home"))

    def test_feedback_page_allows_administrator_role(self):
        FeedbackSegnalazione.objects.create(
            tipo=TipoFeedbackSegnalazione.FUNZIONE,
            messaggio="Aggiungere esportazione feedback.",
            utente_nome="Utente beta",
            utente_email="utente@example.com",
            pagina_titolo="Dashboard",
            pagina_path="/",
        )
        self.client.force_login(self.admin)

        response = self.client.get(reverse("lista_feedback_segnalazioni"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Feedback beta")
        self.assertContains(response, "Aggiungere esportazione feedback.")
        self.assertContains(response, "Utente beta")

    def test_feedback_page_allows_superuser(self):
        self.client.force_login(self.superuser)

        response = self.client.get(reverse("lista_feedback_segnalazioni"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Feedback beta")


class BackupDatabaseStorageTests(TestCase):
    def test_restore_error_parser_ignores_legacy_cleanup_errors(self):
        stderr = "\n".join(
            [
                'psql:restore.sql:12: ERROR:  relation "public.vecchia_tabella" does not exist',
                'psql:restore.sql:13: ERROR:  constraint "vecchia_pkey" of relation "vecchia_tabella" does not exist',
                'psql:restore.sql:14: ERROR:  schema "public" already exists',
            ]
        )

        self.assertFalse(restore_stderr_has_blocking_errors(stderr))

    def test_restore_error_parser_blocks_real_restore_errors(self):
        stderr = 'psql:restore.sql:120: ERROR:  duplicate key value violates unique constraint "auth_user_pkey"'

        self.assertTrue(restore_stderr_has_blocking_errors(stderr))

    def test_reset_public_schema_for_restore_runs_cascade_cleanup(self):
        db_settings = {
            "NAME": "arboris_test",
            "HOST": "localhost",
            "PORT": "5432",
            "USER": "arboris",
        }

        with patch("sistema.database_backups.subprocess.run") as run_mock:
            run_mock.return_value = subprocess.CompletedProcess(args=[], returncode=0, stdout=b"", stderr=b"")

            reset_public_schema_for_restore("psql", db_settings, {"PGPASSWORD": "secret"})

        run_mock.assert_called_once()
        command = run_mock.call_args.args[0]
        self.assertIn("-c", command)
        sql = command[command.index("-c") + 1]
        self.assertIn("DROP SCHEMA IF EXISTS public CASCADE", sql)
        self.assertIn("CREATE SCHEMA public", sql)

    def test_sanitized_restore_sql_removes_cleanup_but_preserves_copy_data(self):
        with TemporaryDirectory() as tmpdir:
            source_path = Path(tmpdir) / "restore.sql"
            source_path.write_text(
                "\n".join(
                    [
                        "DROP TABLE IF EXISTS public.vecchia;",
                        "ALTER TABLE ONLY public.sistema_scuola DROP CONSTRAINT sistema_scuola_pkey;",
                        "CREATE SCHEMA public;",
                        "CREATE TABLE public.esempio (nome text);",
                        "COPY public.esempio (nome) FROM stdin;",
                        "DROP questo e dato, non comando;",
                        r"\.",
                    ]
                ),
                encoding="utf-8",
            )

            sanitized_path, cleanup = build_sanitized_restore_sql(source_path, reference_name="restore.sql")
            try:
                content = sanitized_path.read_text(encoding="utf-8")
            finally:
                cleanup()

        self.assertNotIn("DROP TABLE IF EXISTS", content)
        self.assertNotIn("DROP CONSTRAINT", content)
        self.assertNotIn("CREATE SCHEMA public", content)
        self.assertIn("CREATE TABLE public.esempio", content)
        self.assertIn("DROP questo e dato, non comando;", content)

    def test_sanitized_restore_sql_accepts_plain_sql_with_gz_name(self):
        with TemporaryDirectory() as tmpdir:
            source_path = Path(tmpdir) / "restore.sql.gz"
            source_path.write_text("-- plain sql, not gzipped\nCREATE TABLE public.esempio (id integer);", encoding="utf-8")

            sanitized_path, cleanup = build_sanitized_restore_sql(source_path, reference_name="restore.sql.gz")
            try:
                content = sanitized_path.read_text(encoding="utf-8")
            finally:
                cleanup()

        self.assertIn("CREATE TABLE public.esempio", content)

    def test_sanitized_restore_sql_unwraps_gzip_content(self):
        with TemporaryDirectory() as tmpdir:
            source_path = Path(tmpdir) / "restore.sql.gz"
            with gzip.open(source_path, "wt", encoding="utf-8") as handle:
                handle.write("CREATE TABLE public.esempio (id integer);")

            sanitized_path, cleanup = build_sanitized_restore_sql(source_path, reference_name="restore.sql.gz")
            try:
                content = sanitized_path.read_text(encoding="utf-8")
            finally:
                cleanup()

        self.assertIn("CREATE TABLE public.esempio", content)
        self.assertFalse(content.startswith("\x1f"))

    def test_sanitized_restore_sql_unwraps_nested_gzip_content(self):
        with TemporaryDirectory() as tmpdir:
            inner_path = Path(tmpdir) / "inner.sql.gz"
            source_path = Path(tmpdir) / "restore.sql.gz"
            with gzip.open(inner_path, "wt", encoding="utf-8") as handle:
                handle.write("CREATE TABLE public.esempio (id integer);")
            with gzip.open(source_path, "wb") as handle:
                handle.write(inner_path.read_bytes())

            sanitized_path, cleanup = build_sanitized_restore_sql(source_path, reference_name="restore.sql.gz")
            try:
                content = sanitized_path.read_text(encoding="utf-8")
            finally:
                cleanup()

        self.assertIn("CREATE TABLE public.esempio", content)
        self.assertFalse(content.startswith("\x1f"))

    def test_restore_runner_saves_in_progress_without_celery_task_id(self):
        job = SistemaDatabaseRestoreJob.objects.create(
            stato=StatoRipristinoDatabase.IN_CODA,
            percorso_file="manual_restore/restore.sql.gz",
            nome_file_originale="restore.sql.gz",
            dimensione_file_bytes=42,
        )

        def fake_restore(*args, **kwargs):
            job.refresh_from_db()
            self.assertEqual(job.stato, StatoRipristinoDatabase.IN_CORSO)
            self.assertIsNotNone(job.data_avvio_ripristino)

        with patch("sistema.restore_job_runner.restore_file_reference_exists", return_value=True), patch(
            "sistema.restore_job_runner.restore_database_from_backup_file",
            side_effect=fake_restore,
        ):
            run_restore_job(job.pk)

        job.refresh_from_db()
        self.assertEqual(job.stato, StatoRipristinoDatabase.COMPLETATO)
        self.assertEqual(job.messaggio_errore, "")

    def test_restore_uploads_are_saved_on_storage_backend(self):
        with TemporaryDirectory() as tmpdir:
            with override_settings(MEDIA_ROOT=tmpdir):
                uploaded_file = SimpleUploadedFile("restore.sql.gz", b"backup-data", content_type="application/gzip")

                job = create_restore_job_from_upload(uploaded_file)

                self.assertTrue(default_storage.exists(job.percorso_file))
                self.assertTrue(job.percorso_file.startswith("db_restore_uploads/"))

                cancel_or_delete_restore_job(job)
                self.assertFalse(default_storage.exists(job.percorso_file))

    def test_restore_local_files_are_saved_on_storage_backend(self):
        with TemporaryDirectory() as tmpdir:
            local_file = Path(tmpdir) / "restore.sql.gz"
            local_file.write_bytes(b"backup-data")
            media_root = Path(tmpdir) / "media"

            with override_settings(MEDIA_ROOT=media_root):
                job = create_restore_job_from_local_file(local_file, "restore.sql.gz")

                self.assertTrue(default_storage.exists(job.percorso_file))
                self.assertTrue(job.percorso_file.startswith("db_restore_uploads/"))
                self.assertEqual(job.dimensione_file_bytes, len(b"backup-data"))

                cancel_or_delete_restore_job(job)
                self.assertFalse(default_storage.exists(job.percorso_file))

    def test_restoring_from_existing_backup_keeps_backup_file_when_pending_job_is_cancelled(self):
        with TemporaryDirectory() as tmpdir:
            with override_settings(MEDIA_ROOT=tmpdir):
                backup = SistemaDatabaseBackup.objects.create(
                    nome_file="backup-manuale.sql.gz",
                    tipo_backup="manuale",
                    dimensione_file_bytes=12,
                    file_backup=SimpleUploadedFile("backup-manuale.sql.gz", b"backup-source", content_type="application/gzip"),
                )

                job = create_restore_job_from_backup_record(backup)

                self.assertTrue(default_storage.exists(job.percorso_file))
                cancel_or_delete_restore_job(job)

                backup.refresh_from_db()
                self.assertTrue(default_storage.exists(backup.file_backup.name))
