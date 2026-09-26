from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import TestCase, SimpleTestCase
from django.urls import URLResolver, get_resolver, reverse

from .active_toggles import ACTIVE_TOGGLE_REGISTRY
from .context_processors import user_can_access_sidebar_url
from .forms import SistemaRuoloPermessiForm
from .models import PERMISSION_MODULE_FIELDS, SistemaRuoloPermessi, SistemaUtentePermessi
from .permission_catalog import PERMISSION_PAGES, PAGES_BY_KEY, PAGES_BY_VIEW, SIDEBAR_PAGE_ALIASES
from .permissions import user_has_page_permission
from .sidebar_menu import SIDEBAR_MENU_ITEM_KEYS


class PermissionCatalogueTests(SimpleTestCase):
    def test_every_protected_url_and_sidebar_item_has_a_page(self):
        def visit(patterns):
            for pattern in patterns:
                if isinstance(pattern, URLResolver):
                    if pattern.namespace != "admin":
                        yield from visit(pattern.url_patterns)
                else:
                    yield pattern

        for pattern in visit(get_resolver().url_patterns):
            if hasattr(pattern.callback, "permission_module"):
                self.assertIn(pattern.name, PAGES_BY_VIEW, pattern.name)
        self.assertEqual(len(PAGES_BY_VIEW), sum(len(page.views) for page in PERMISSION_PAGES))
        for key in SIDEBAR_MENU_ITEM_KEYS:
            self.assertIn(SIDEBAR_PAGE_ALIASES.get(key, key), PAGES_BY_KEY)
        for config in ACTIVE_TOGGLE_REGISTRY.values():
            self.assertIn(config.permission_page, PAGES_BY_KEY)


class PagePermissionsTests(TestCase):
    def setUp(self):
        cache.clear()
        self.role = SistemaRuoloPermessi.objects.create(
            nome="Segreteria pagine", permesso_anagrafica="view",
            permessi_pagine={"economia_panoramica_rette": "view", "gestione_finanziaria_movimenti_bancari": "view"},
        )
        self.user = User.objects.create_user(username="segreteria-pagine", password="test-password")
        SistemaUtentePermessi.objects.create(user=self.user, ruolo_permessi=self.role)
        self.client.force_login(self.user)

    def test_secretary_can_read_only_selected_economic_pages(self):
        for name in ("lista_studenti", "verifica_situazione_rette", "lista_movimenti_finanziari"):
            with self.subTest(url=name):
                response = self.client.get(reverse(name))
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.context["current_module_view_only"])
        for name in ("lista_iscrizioni", "lista_conti_bancari", "lista_fornitori", "dashboard_gestione_finanziaria"):
            with self.subTest(url=name):
                self.assertRedirects(self.client.get(reverse(name)), reverse("home"), fetch_redirect_response=False)

    def test_sidebar_and_custom_links_follow_page_exceptions(self):
        response = self.client.get(reverse("home"))
        items = response.context["sidebar_menu_items"]
        self.assertTrue(items["economia_panoramica_rette"])
        self.assertTrue(items["gestione_finanziaria_movimenti_bancari"])
        self.assertFalse(items["economia_iscrizioni"])
        self.assertFalse(items["gestione_finanziaria_conti_bancari"])
        self.assertTrue(user_can_access_sidebar_url(self.user, reverse("lista_movimenti_finanziari")))
        self.assertFalse(user_can_access_sidebar_url(self.user, reverse("lista_conti_bancari")))

    def test_read_only_blocks_post_create_delete_and_edit_mode(self):
        routes = [
            ("lista_movimenti_finanziari", []),
            ("crea_movimento_manuale", []),
            ("modifica_movimento_finanziario", [999999]),
            ("aggiorna_categoria_movimento", [999999]),
            ("elimina_movimento_finanziario", [999999]),
            ("verifica_situazione_rette", []),
        ]
        for name, args in routes:
            with self.subTest(url=name):
                response = self.client.post(reverse(name, args=args), {})
                self.assertRedirects(response, reverse("home"), fetch_redirect_response=False)
        for url in (reverse("crea_movimento_manuale"), reverse("modifica_movimento_finanziario", args=[999999]) + "?edit=1"):
            self.assertRedirects(self.client.get(url), reverse("home"), fetch_redirect_response=False)

    def test_page_deny_and_view_override_module_manage(self):
        self.role.permesso_gestione_finanziaria = "manage"
        self.role.permessi_pagine["gestione_finanziaria_conti_bancari"] = "none"
        self.role.save()
        self.assertRedirects(self.client.get(reverse("lista_conti_bancari")), reverse("home"), fetch_redirect_response=False)
        response = self.client.get(reverse("lista_movimenti_finanziari"))
        self.assertFalse(response.context["can_manage_gestione_finanziaria"])
        self.assertTrue(response.context["current_module_view_only"])

    def test_page_manage_grants_actions_without_other_module_access(self):
        self.role.permessi_pagine["gestione_finanziaria_movimenti_bancari"] = "manage"
        self.role.save()
        self.assertEqual(self.client.get(reverse("crea_movimento_manuale")).status_code, 200)
        self.assertEqual(self.client.get(reverse("modifica_movimento_finanziario", args=[999999]) + "?edit=1").status_code, 404)
        self.assertRedirects(self.client.get(reverse("crea_conto_bancario")), reverse("home"), fetch_redirect_response=False)

    def test_generic_toggle_cannot_bypass_page_deny(self):
        self.role.permesso_gestione_finanziaria = "manage"
        self.role.permessi_pagine["anagrafica_fornitori"] = "none"
        self.role.save()
        response = self.client.post(reverse("toggle_active_state"), {
            "model": "gestione_finanziaria.fornitore", "pk": 999999, "field": "attivo", "value": "0",
        })
        self.assertEqual(response.status_code, 403)

    def test_global_search_does_not_leak_denied_pages(self):
        self.role.permessi_pagine["anagrafica_familiari"] = "none"
        self.role.save()
        from .views import build_global_search_results
        with patch("sistema.views.build_anagrafica_global_search_results", return_value=[
            {"title": "Riservato", "url": reverse("modifica_familiare", args=[1])},
            {"title": "Consentito", "url": reverse("modifica_studente", args=[1])},
        ]):
            results = build_global_search_results(self.user, "nome")
        self.assertEqual([result["title"] for result in results], ["Consentito"])

    def test_inactive_role_and_disabled_module_block_page_grants(self):
        self.role.attivo = False
        self.role.save()
        self.assertFalse(user_has_page_permission(self.user, "economia_panoramica_rette"))
        self.role.attivo = True
        self.role.save()
        del self.user._arboris_permission_profile_cache
        with patch("sistema.permissions.module_is_enabled", return_value=False):
            self.assertFalse(user_has_page_permission(self.user, "economia_panoramica_rette"))

    def test_form_roundtrip_and_clear_overrides(self):
        data = {field: getattr(self.role, field) for field in PERMISSION_MODULE_FIELDS.values()}
        data.update(nome=self.role.nome, colore_principale="#417690", attivo="on", page_permissions_form_present="1")
        data.update(pagina_economia_panoramica_rette="view", pagina_gestione_finanziaria_movimenti_bancari="manage")
        form = SistemaRuoloPermessiForm(data, instance=self.role)
        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        self.role.refresh_from_db()
        self.assertEqual(self.role.permessi_pagine, {"economia_panoramica_rette": "view", "gestione_finanziaria_movimenti_bancari": "manage"})
        data["pagina_economia_panoramica_rette"] = ""
        data["pagina_gestione_finanziaria_movimenti_bancari"] = ""
        form = SistemaRuoloPermessiForm(data, instance=self.role)
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.save().permessi_pagine, {})

    def test_invalid_level_does_not_save(self):
        form = SistemaRuoloPermessiForm({"pagina_economia_panoramica_rette": "administrator"}, instance=self.role)
        self.assertFalse(form.is_valid())
        self.assertIn("pagina_economia_panoramica_rette", form.errors)

    def test_legacy_hidden_pages_are_denied_until_explicitly_enabled(self):
        self.role.voci_menu_disabilitate = ["anagrafica_studenti"]
        self.assertEqual(self.role.get_page_level("anagrafica_studenti"), "none")
        self.role.permessi_pagine["anagrafica_studenti"] = "view"
        self.assertEqual(self.role.get_page_level("anagrafica_studenti"), "view")

    def test_special_page_override_supports_read_only(self):
        self.role.permessi_pagine["anagrafica_comunicazioni_famiglie"] = "view"
        self.role.save()
        self.assertEqual(self.client.get(reverse("storico_comunicazioni_famiglie")).status_code, 200)
        self.assertRedirects(self.client.post(reverse("comunicazioni_famiglie"), {}), reverse("home"), fetch_redirect_response=False)

    def test_home_does_not_show_financial_dashboard_for_movements_only(self):
        response = self.client.get(reverse("home"))
        self.assertNotContains(response, 'data-dashboard-section-id="gestione-finanziaria"')
        self.assertNotContains(response, "Dashboard finanziaria")

    def test_revocation_applies_on_the_next_request(self):
        self.assertEqual(self.client.get(reverse("lista_movimenti_finanziari")).status_code, 200)
        self.role.permessi_pagine = {}
        self.role.save()
        self.assertRedirects(self.client.get(reverse("lista_movimenti_finanziari")), reverse("home"), fetch_redirect_response=False)

    def test_matrix_actions_follow_matrix_level_without_opening_rates_list(self):
        for level, permitted in (("view", False), ("manage", True)):
            self.role.permessi_pagine["economia_panoramica_rette"] = level
            self.role.save()
            response = self.client.get(reverse("modifica_rata_iscrizione", args=[999999]) + "?edit=1")
            self.assertEqual(response.status_code, 404 if permitted else 302)
        self.assertRedirects(self.client.get(reverse("lista_rate_iscrizione")), reverse("home"), fetch_redirect_response=False)

    def test_full_control_overrides_page_levels_but_not_disabled_modules(self):
        self.role.controllo_completo = True
        self.role.permessi_pagine["economia_panoramica_rette"] = "none"
        self.role.save()
        self.assertTrue(user_has_page_permission(self.user, "economia_panoramica_rette", "manage"))
        with patch("sistema.permissions.module_is_enabled", return_value=False):
            self.assertFalse(user_has_page_permission(self.user, "economia_panoramica_rette", "manage"))
