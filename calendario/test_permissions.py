from datetime import date, datetime, time
from decimal import Decimal

from django.contrib.auth.models import AnonymousUser, User
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from anagrafica.models import Documento, Studente, TipoDocumento
from economia.models import CondizioneIscrizione, Iscrizione, RataIscrizione, StatoIscrizione
from famiglie_interessate.models import AttivitaFamigliaInteressata, FamigliaInteressata
from gestione_finanziaria.models import DocumentoFornitore, Fornitore, ScadenzaPagamentoFornitore
from scuola.models import AnnoScolastico
from sistema.models import SistemaImpostazioniGenerali, SistemaRuoloPermessi, SistemaUtentePermessi
from sistema.permissions import get_user_permission_profile, user_has_module_permission

from .data import (
    build_calendar_agenda_bundle, build_calendar_deadline_records,
    build_calendar_list_bundle, build_dashboard_calendar_data,
    build_interested_family_activity_records,
)
from .models import (
    CategoriaCalendario, EventoCalendario, SYSTEM_CATEGORY_DOCUMENTS,
    SYSTEM_CATEGORY_INTERESTED_FAMILIES, SYSTEM_CATEGORY_RATE_DUE,
    SYSTEM_CATEGORY_SUPPLIER_DUE, ensure_system_calendar_categories,
)


class CalendarModulePermissionTests(TestCase):
    sources = {
        "economia": ("rata", SYSTEM_CATEGORY_RATE_DUE, "Scadenza retta - Riservato Studente"),
        "anagrafica": ("documento", SYSTEM_CATEGORY_DOCUMENTS, "Documento riservato"),
        "gestione_finanziaria": ("fornitore_scadenza", SYSTEM_CATEGORY_SUPPLIER_DUE, "Fornitore riservato"),
        "famiglie_interessate": ("famiglia_interessata", SYSTEM_CATEGORY_INTERESTED_FAMILIES, "Colloquio riservato"),
    }

    @classmethod
    def setUpTestData(cls):
        cls.day = timezone.localdate()
        cls.role = SistemaRuoloPermessi.objects.create(nome="Solo calendario", permesso_calendario="view")
        cls.user = User.objects.create_user(username="calendar-reader")
        cls.profile = SistemaUtentePermessi.objects.create(user=cls.user, ruolo_permessi=cls.role)
        cls.author = User.objects.create_user(username="calendar-author")
        cls.system_categories = ensure_system_calendar_categories()
        category = CategoriaCalendario.objects.create(nome="Eventi condivisi")
        cls.manual = EventoCalendario.objects.create(
            titolo="Riunione condivisa", categoria_evento=category, creato_da=cls.author,
            data_inizio=cls.day, data_fine=cls.day,
        )
        # A manually chosen category does not turn an event into a financial record.
        cls.manual_financial_category = EventoCalendario.objects.create(
            titolo="Promemoria condiviso", creato_da=cls.user,
            categoria_evento=cls.system_categories[SYSTEM_CATEGORY_SUPPLIER_DUE],
            data_inizio=cls.day, data_fine=cls.day,
        )
        cls.manual_titles = {cls.manual.titolo, cls.manual_financial_category.titolo}
        year = AnnoScolastico.objects.create(
            nome_anno_scolastico=f"Calendario {cls.day.year}",
            data_inizio=date(cls.day.year, 1, 1), data_fine=date(cls.day.year, 12, 31),
        )
        student = Studente.objects.create(nome="Studente", cognome="Riservato")
        enrollment = Iscrizione.objects.create(
            studente=student, anno_scolastico=year,
            stato_iscrizione=StatoIscrizione.objects.create(stato_iscrizione="Attiva", attiva=True),
            condizione_iscrizione=CondizioneIscrizione.objects.create(
                anno_scolastico=year, nome_condizione_iscrizione="Standard", numero_mensilita_default=10,
            ),
        )
        RataIscrizione.objects.create(
            iscrizione=enrollment, tipo_rata=RataIscrizione.TIPO_MENSILE, numero_rata=1,
            mese_riferimento=cls.day.month, anno_riferimento=cls.day.year,
            importo_dovuto=Decimal("100.00"), data_scadenza=cls.day,
        )
        Documento.objects.create(
            studente=student, tipo_documento=TipoDocumento.objects.create(tipo_documento="Documento riservato"),
            file="documenti/calendar-permissions-test.pdf", scadenza=cls.day,
        )
        invoice = DocumentoFornitore.objects.create(
            fornitore=Fornitore.objects.create(denominazione="Fornitore riservato"),
            numero_documento="PRIVATE-001", data_documento=cls.day,
            imponibile=Decimal("100.00"), iva=Decimal("22.00"), totale=Decimal("122.00"),
        )
        ScadenzaPagamentoFornitore.objects.create(
            documento=invoice, data_scadenza=cls.day, importo_previsto=Decimal("122.00"),
        )
        AttivitaFamigliaInteressata.objects.create(
            famiglia=FamigliaInteressata.objects.create(nome="Famiglia riservata"),
            titolo="Colloquio riservato", calendarizza=True,
            data_programmata=timezone.make_aware(datetime.combine(cls.day, time(10))),
        )

    def setUp(self):
        cache.clear()
        self.addCleanup(cache.clear)
        self.client.force_login(self.user)

    def grant_modules(self, *modules, level="view"):
        for module in self.sources:
            setattr(self.role, f"permesso_{module}", level if module in modules else "none")
        self.role.save()

    def assert_visible_surfaces(self, allowed_modules):
        allowed_sources = {self.sources[module][0] for module in allowed_modules} | {"locale"}
        total = len(allowed_modules) + 2
        for route, records_key, total_key in (
            ("calendario_agenda", "calendar_entries", "count_eventi_locali"),
            ("lista_eventi_calendario", "eventi", "count_eventi_totali"),
        ):
            with self.subTest(route=route):
                response = self.client.get(reverse(route))
                self.assertEqual(response.status_code, 200)
                records = response.context[records_key]
                self.assertEqual({record["source"] for record in records}, allowed_sources)
                self.assertEqual(len(records), total)
                self.assertEqual(response.context[total_key], total)
                self.assertTrue(self.manual_titles <= {record["title"] for record in records})
                for module, (_, _, marker) in self.sources.items():
                    if module not in allowed_modules:
                        self.assertNotContains(response, marker)
                if route == "calendario_agenda":
                    self.assertEqual(response.context["lista_count_eventi_totali"], total)
                    self.assertEqual(sum(item["event_count"] for item in response.context["calendar_categories_payload"]), total)
                    self.assertEqual({record["source"] for record in response.context["lista_eventi"]}, allowed_sources)

        categories = self.client.get(reverse("lista_categorie_calendario"))
        self.assertEqual(categories.status_code, 200)
        counts = {category.chiave_sistema: category.count_eventi_agenda for category in categories.context["categorie"]}
        for module, (_, key, _) in self.sources.items():
            # Keep the manually created event even without supplier access.
            self.assertEqual(counts[key], int(module in allowed_modules) + int(key == SYSTEM_CATEGORY_SUPPLIER_DUE))

        home = self.client.get(reverse("home"))
        self.assertEqual(home.status_code, 200)
        dashboard = home.context["calendario_dashboard"]
        self.assertEqual({record["source"] for record in dashboard["today_records"]}, allowed_sources)
        self.assertEqual({record["source"] for record in dashboard["week_records"]}, allowed_sources)
        self.assertEqual(dashboard["count_today_records"], total)
        self.assertEqual(dashboard["count_week_records"], total)

    def test_calendar_only_role_sees_shared_events_without_private_deadlines_or_counts(self):
        self.assert_visible_surfaces(set())
        detail = self.client.get(reverse("modifica_evento_calendario", args=[self.manual.pk]))
        self.assertEqual(detail.status_code, 200)
        self.assertContains(detail, self.manual.titolo)

    def test_each_module_allows_only_its_own_records_with_view_or_manage_permission(self):
        for level in ("view", "manage"):
            for module in self.sources:
                with self.subTest(module=module, level=level):
                    self.grant_modules(module, level=level)
                    self.assert_visible_surfaces({module})

    def test_multiple_module_permissions_are_combined(self):
        self.grant_modules("anagrafica", "gestione_finanziaria")
        self.assert_visible_surfaces({"anagrafica", "gestione_finanziaria"})

    def test_role_restrictions_override_old_copied_profile_permissions(self):
        for module in self.sources:
            setattr(self.profile, f"permesso_{module}", "manage")
        self.profile.controllo_completo = True
        self.profile.save()
        self.assert_visible_surfaces(set())

    def test_role_changes_take_effect_on_next_request(self):
        self.grant_modules(*self.sources)
        self.assert_visible_surfaces(set(self.sources))
        self.grant_modules()
        self.assert_visible_surfaces(set())

    def test_profile_permissions_work_without_an_assigned_role(self):
        self.profile.ruolo_permessi = None
        self.profile.permesso_calendario = "view"
        self.profile.permesso_economia = "view"
        self.profile.save()
        self.assert_visible_surfaces({"economia"})

    def test_full_control_and_superuser_keep_all_enabled_module_records(self):
        self.role.controllo_completo = True
        self.role.save()
        self.assert_visible_surfaces(set(self.sources))
        admin = User.objects.create_superuser(username="calendar-superuser")
        self.client.force_login(admin)
        self.assert_visible_surfaces(set(self.sources))

    def test_disabled_modules_remain_hidden_even_with_full_control(self):
        self.role.controllo_completo = True
        self.role.save()
        settings = SistemaImpostazioniGenerali.objects.create()
        for module in self.sources:
            with self.subTest(module=module):
                field = f"modulo_{module}_attivo"
                setattr(settings, field, False)
                settings.save()
                cache.clear()
                self.assert_visible_surfaces(set(self.sources) - {module})
                setattr(settings, field, True)
                settings.save()

    def test_inactive_role_cannot_expose_records_using_full_control(self):
        self.role.attivo = False
        self.role.controllo_completo = True
        self.role.save()
        self.profile.controllo_completo = True
        self.profile.save()
        user = User.objects.get(pk=self.user.pk)
        records = build_calendar_agenda_bundle(user=user)["records"]
        self.assertEqual({record["title"] for record in records}, self.manual_titles)
        self.assertRedirects(self.client.get(reverse("calendario_agenda")), reverse("home"), fetch_redirect_response=False)

    def test_category_and_text_filters_cannot_restore_denied_records(self):
        for module, (_, key, marker) in self.sources.items():
            with self.subTest(module=module):
                for route, record_key in (("calendario_agenda", "lista_eventi"), ("lista_eventi_calendario", "eventi")):
                    response = self.client.get(reverse(route), {"categoria": self.system_categories[key].pk, "q": marker})
                    self.assertEqual(response.status_code, 200)
                    self.assertEqual(len(response.context[record_key]), 0)

    def test_denied_sources_are_not_queried(self):
        get_user_permission_profile(self.user)
        for module in self.sources:
            self.assertFalse(user_has_module_permission(self.user, module))
        with self.assertNumQueries(0):
            self.assertEqual(build_calendar_deadline_records(self.system_categories, user=self.user), [])
            self.assertEqual(build_interested_family_activity_records(self.system_categories, user=self.user), [])

    def test_missing_or_anonymous_user_does_not_get_automatic_records(self):
        for user in (None, AnonymousUser()):
            with self.subTest(user=user):
                self.assertEqual(build_calendar_deadline_records(self.system_categories, user=user), [])
                self.assertEqual(build_interested_family_activity_records(self.system_categories, user=user), [])
                for bundle in (build_calendar_agenda_bundle(user=user), build_calendar_list_bundle(user=user)):
                    self.assertEqual({record["title"] for record in bundle["records"]}, self.manual_titles)
                dashboard = build_dashboard_calendar_data(today=self.day, user=user)
                self.assertEqual({record["title"] for record in dashboard["today_records"]}, self.manual_titles)
                self.assertFalse(dashboard["birthdays"]["can_view_records"])
