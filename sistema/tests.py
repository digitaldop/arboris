from tempfile import TemporaryDirectory

from django.contrib.auth.models import User
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from .database_backups import cancel_or_delete_restore_job, create_restore_job_from_backup_record, create_restore_job_from_upload
from .models import LivelloPermesso, RuoloUtente, SistemaDatabaseBackup, SistemaUtentePermessi


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
        self.assertNotContains(response, reverse("lista_famiglie"))
        self.assertNotContains(response, reverse("lista_iscrizioni"))
        self.assertNotContains(response, reverse("lista_dipendenti"))


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
            "Dati Scuola",
            "Anni scolastici",
            "Classi",
        ]

        previous_index = -1
        for label in labels_in_order:
            current_index = sistema_section.index(label)
            self.assertGreater(current_index, previous_index)
            previous_index = current_index


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
