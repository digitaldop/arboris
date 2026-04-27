from tempfile import TemporaryDirectory

from django.contrib.auth.models import User
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from .database_backups import cancel_or_delete_restore_job, create_restore_job_from_backup_record, create_restore_job_from_upload
from .models import LivelloPermesso, RuoloUtente, SistemaDatabaseBackup, SistemaUtentePermessi
from .popup_manifest import build_popup_manifest
from anagrafica.models import Citta, Provincia, Regione
from anagrafica.models import Indirizzo


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
            "<span>Iscrizioni</span>",
            "Iscrizioni",
            "Stati iscrizione",
            "Rate iscrizione",
            "<span>Impostazioni rette</span>",
        ]

        previous_index = -1
        for label in labels_in_order:
            current_index = economia_section.index(label)
            self.assertGreater(current_index, previous_index)
            previous_index = current_index


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
            "<span>Fornitori</span>",
            "Fornitori",
            "Documenti fornitori",
            "Scadenziario fornitori",
            "Categorie spesa",
            "<span>Conti correnti</span>",
            "Conti bancari",
            "Movimenti",
            "Categorie movimenti",
            "Import estratto conto",
            "Riconciliazione",
            "Report categorie",
            "<span>Impostazioni conti correnti</span>",
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


class SidebarSistemaTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="sistema@example.com",
            email="sistema@example.com",
            password="Password123!",
        )
        SistemaUtentePermessi.objects.create(
            user=self.user,
            permesso_sistema=LivelloPermesso.GESTIONE,
        )

    def test_home_renders_school_settings_as_submenu_of_system(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse("home"))

        self.assertEqual(response.status_code, 200)
        content = response.content.decode("utf-8")
        start = content.index('id="sidebar-sistema-panel"')
        sistema_section = content[start:]

        labels_in_order = [
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

    def test_backup_database_page_denies_staff_user_without_admin_role(self):
        self.client.force_login(self.staff_non_admin)

        response = self.client.get(reverse("backup_database_sistema"))

        self.assertRedirects(response, reverse("home"))

    def test_backup_database_page_allows_superuser(self):
        self.client.force_login(self.superuser)

        response = self.client.get(reverse("backup_database_sistema"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Backup Database")


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
