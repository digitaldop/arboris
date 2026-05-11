import base64
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from datetime import timedelta
from decimal import Decimal
from unittest import skip

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
    cancel_or_delete_restore_job,
    create_restore_job_from_backup_record,
    create_restore_job_from_local_file,
    create_restore_job_from_storage_reference,
    create_restore_job_from_upload,
)
from .models import (
    FeedbackSegnalazione,
    LivelloPermesso,
    RuoloUtente,
    SistemaDatabaseBackup,
    SistemaDatabaseRestoreJob,
    SistemaImpostazioniGenerali,
    SistemaOperazioneCronologia,
    SistemaRuoloPermessi,
    SistemaUtentePermessi,
    TipoFeedbackSegnalazione,
)
from .popup_manifest import build_popup_manifest
from anagrafica.models import (
    Citta,
    Familiare,
    Provincia,
    Regione,
    RelazioneFamiliare,
    Studente,
    StudenteFamiliare,
)
from anagrafica.models import Indirizzo
from calendario.models import CategoriaCalendario, EventoCalendario
from gestione_finanziaria.models import DocumentoFornitore, Fornitore, MovimentoFinanziario, ScadenzaPagamentoFornitore
from scuola.models import AnnoScolastico


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
        self.assertNotContains(response, "GESTIONE FINANZIARIA")


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

    def test_home_renders_economia_sidebar_in_requested_order(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        content = response.content.decode("utf-8")
        start = content.index('id="sidebar-economia-panel"')
        end = content.index('data-sidebar-section-key="sistema"')
        economia_section = content[start:end]

        labels_in_order = [
            "Verifica situazione rette",
            "Fondo accantonamento",
            "<span>Scambi retta</span>",
            "Scambio retta",
            "Tariffe scambio retta",
            "<span>Impostazioni rette</span>",
        ]

        previous_index = -1
        for label in labels_in_order:
            current_index = economia_section.index(label)
            self.assertGreater(current_index, previous_index)
            previous_index = current_index
        self.assertNotIn('id="sidebar-economia-iscrizioni-panel"', economia_section)
        self.assertNotContains(response, f'href="{reverse("lista_iscrizioni")}"', html=False)

    def test_home_renders_parcheggio_only_for_operational_admin(self):
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
        )
        self.client.force_login(admin_user)

        admin_response = self.client.get(reverse("home"))

        self.assertEqual(admin_response.status_code, 200)
        content = admin_response.content.decode("utf-8")
        start = content.index('data-sidebar-section-key="parcheggio"')
        end = content.index('data-sidebar-section-key="sistema"', start)
        parcheggio_section = content[start:end]

        self.assertIn("Parcheggio", parcheggio_section)
        self.assertIn('id="sidebar-parcheggio-iscrizioni-panel"', parcheggio_section)
        self.assertIn(f'href="{reverse("lista_iscrizioni")}"', parcheggio_section)
        self.assertIn(f'href="{reverse("lista_stati_iscrizione")}"', parcheggio_section)
        self.assertIn(f'href="{reverse("lista_rate_iscrizione")}"', parcheggio_section)
        self.assertIn(f'href="{reverse("lista_notifiche_finanziarie")}"', parcheggio_section)


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

    def test_home_renders_conti_correnti_sidebar_in_requested_order(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        content = response.content.decode("utf-8")
        start = content.index('id="sidebar-gestione-finanziaria-panel"')
        end = content.index('data-sidebar-section-key="sistema"', start)
        gestione_finanziaria_section = content[start:end]

        labels_in_order = [
            "Dashboard",
            "Budgeting",
            "<span>Fornitori</span>",
            "Fornitori",
            "Fatture fornitori",
            "Scadenziario fornitori",
            "Pagamenti fornitori",
            "<span>Impostazioni Fornitori</span>",
            "Fatture in Cloud",
            "Categorie di spesa",
            "<span>Conti correnti</span>",
            "Movimenti",
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
            current_index = gestione_finanziaria_section.index(label)
            self.assertGreater(current_index, previous_index)
            previous_index = current_index
        self.assertNotIn("Notifiche", gestione_finanziaria_section)

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

    def impostazioni_generali_post_data(self, **overrides):
        data = {
            "terminologia_studente": "studente",
            "formato_visualizzazione_telefono": "it_plus_n3_2_2_3",
            "cronologia_retention_mesi": "24",
            "gestione_iscrizione_corso_anno": "mese_iscrizione_intero",
            "giorno_soglia_iscrizione_corso_anno": "15",
            "osservazioni_solo_autori_modifica": "on",
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

    def test_home_keeps_sidebar_reorder_toggle_available(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse("home"))
        css = (settings.BASE_DIR / "static" / "css" / "style.css").read_text(encoding="utf-8")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="sidebar-reorder-toggle"')
        self.assertContains(response, "Modalita drag and drop")
        self.assertNotRegex(
            css,
            r"\.sidebar-reorder-footer\s*,\s*\.sidebar-reorder-list[^{]*\{\s*display:\s*none",
        )

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
        self.assertContains(response, 'name="modulo_calendario_attivo"')
        self.assertContains(response, 'class="settings-module-grid"')

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
