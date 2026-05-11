import re
from collections import Counter
from datetime import date, timedelta
from decimal import Decimal
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import skip
from unittest.mock import patch

import pandas as pd
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from anagrafica.contact_services import sync_all_student_family_relations
from anagrafica.dati_base_import import run_import_dati_base, run_import_nazioni_belfiore
from anagrafica.forms import (
    DocumentoFamigliaFormSet,
    DocumentoStudenteForm,
    DocumentoStudenteFormSet,
    FamiliareForm,
    FamiliareInlineForm,
    IndirizzoForm,
    IscrizioneStudenteInlineForm,
    StudenteForm,
    StudenteInlineForm,
    StudenteStandaloneForm,
    nazione_choice_queryset,
)
from anagrafica.views import famiglia_studenti_inline_queryset, sync_studente_iscrizioni_rate_schedules
from anagrafica.models import (
    CAP,
    Citta,
    Documento,
    Familiare,
    Indirizzo,
    Nazione,
    Provincia,
    Regione,
    RelazioneFamiliare,
    Studente,
    StudenteFamiliare,
    TipoDocumento,
)
from economia.models import (
    Agevolazione,
    CondizioneIscrizione,
    Iscrizione,
    PrestazioneScambioRetta,
    RataIscrizione,
    StatoIscrizione,
    TariffaScambioRetta,
    TariffaCondizioneIscrizione,
)
from gestione_amministrativa.models import (
    BustaPagaDipendente,
    ContrattoDipendente,
    Dipendente,
    DocumentoDipendente,
    RuoloAnagraficoDipendente,
    StatoBustaPaga,
    StatoDipendente,
    TipoContrattoDipendente,
)
from osservazioni.models import OsservazioneStudente
from scuola.models import AnnoScolastico, Classe, GruppoClasse
from sistema.models import (
    AzioneOperazioneCronologia,
    SistemaOperazioneCronologia,
    SistemaRuoloPermessi,
    SistemaUtentePermessi,
)


class ImportDatiBaseTests(TestCase):
    def _build_excel(self, path: Path) -> None:
        df = pd.DataFrame(
            [
                {
                    "Regione": "Lazio",
                    "Provincia": "Roma",
                    "Sigla": "RM",
                    "Comune": "Roma",
                    "CAP": "00118",
                    "codice_istat": "058091",
                    "codice_belfiore": "H501",
                },
                {
                    "Regione": "Lazio",
                    "Provincia": "Roma",
                    "Sigla": "RM",
                    "Comune": "Roma",
                    "CAP": "00119",
                    "codice_istat": "058091",
                    "codice_belfiore": "H501",
                },
                {
                    "Regione": "Lazio",
                    "Provincia": "Roma",
                    "Sigla": "RM",
                    "Comune": "Fiumicino",
                    "CAP": "00054",
                    "codice_istat": "058120",
                    "codice_belfiore": "M297",
                },
            ]
        )
        df.to_excel(path, index=False)

    def test_run_import_dati_base_imports_geography_and_belfiore(self):
        with TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / "gi_comuni_cap.xlsx"
            self._build_excel(file_path)

            stats = run_import_dati_base(file_path=file_path, header=0)

        self.assertEqual(stats["regioni_creati"], 1)
        self.assertEqual(stats["province_creati"], 1)
        self.assertEqual(stats["citta_righe"], 2)
        self.assertEqual(stats["cap_creati"], 3)
        self.assertEqual(stats["cap_saltati"], 0)
        self.assertIn("durata_secondi", stats)

        self.assertEqual(Regione.objects.count(), 1)
        self.assertEqual(Provincia.objects.count(), 1)
        self.assertEqual(Citta.objects.count(), 2)
        self.assertEqual(CAP.objects.count(), 3)

        roma = Citta.objects.get(nome="Roma")
        fiumicino = Citta.objects.get(nome="Fiumicino")
        self.assertEqual(roma.codice_catastale, "H501")
        self.assertEqual(fiumicino.codice_catastale, "M297")
        self.assertEqual(
            list(CAP.objects.filter(citta=roma).order_by("codice").values_list("codice", flat=True)),
            ["00118", "00119"],
        )

        with TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / "gi_comuni_cap.xlsx"
            self._build_excel(file_path)

            second_stats = run_import_dati_base(file_path=file_path, header=0)

        self.assertEqual(second_stats["regioni_creati"], 0)
        self.assertEqual(second_stats["province_creati"], 0)
        self.assertEqual(second_stats["citta_righe"], 2)
        self.assertEqual(second_stats["cap_creati"], 0)
        self.assertEqual(Citta.objects.count(), 2)
        self.assertEqual(CAP.objects.count(), 3)

    def test_run_import_nazioni_belfiore_imports_by_belfiore_code(self):
        with TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / "nazioni_belfiore.csv"
            file_path.write_text(
                "\n".join(
                    [
                        "nome_nazione,nazionalita,codice_iso2,codice_iso3,codice_belfiore",
                        "ARMENIA,armena,AM,ARM,Z252",
                        "ARMENIA,armena,AM,ARM,Z137",
                        "STATI UNITI,statunitense,US,USA,Z404",
                        "ZANZIBAR,,,,Z356",
                    ]
                ),
                encoding="utf-8",
            )

            stats = run_import_nazioni_belfiore(file_path=file_path)
            second_stats = run_import_nazioni_belfiore(file_path=file_path)

        self.assertEqual(stats["righe"], 4)
        self.assertEqual(stats["nazioni_create"], 4)
        self.assertEqual(stats["nazioni_aggiornate"], 0)
        self.assertEqual(second_stats["nazioni_create"], 0)
        self.assertEqual(second_stats["nazioni_invariate"], 4)
        self.assertEqual(Nazione.objects.filter(nome="Armenia").count(), 2)
        armenia = Nazione.objects.get(codice_belfiore="Z252")
        self.assertEqual(armenia.nome_nazionalita, "Armena")
        self.assertEqual(armenia.codice_iso2, "AM")
        stati_uniti = Nazione.objects.get(codice_belfiore="Z404")
        self.assertEqual(stati_uniti.nome, "Stati Uniti")
        self.assertEqual(stati_uniti.nome_nazionalita, "Statunitense")
        zanzibar = Nazione.objects.get(codice_belfiore="Z356")
        self.assertEqual(zanzibar.nome, "Zanzibar")
        self.assertEqual(zanzibar.nome_nazionalita, "")

    def test_nazione_choice_queryset_shows_unique_nationality_labels(self):
        Nazione.objects.create(
            nome="Armenia",
            nome_nazionalita="Armena",
            codice_iso2="AM",
            codice_iso3="ARM",
            codice_belfiore="Z252",
            ordine=1,
            attiva=True,
        )
        Nazione.objects.create(
            nome="Armenia",
            nome_nazionalita="Armena",
            codice_iso2="AM",
            codice_iso3="ARM",
            codice_belfiore="Z137",
            ordine=2,
            attiva=True,
        )
        Nazione.objects.create(
            nome="Antille Britanniche",
            nome_nazionalita="",
            codice_belfiore="Z500",
            ordine=3,
            attiva=True,
        )

        queryset = nazione_choice_queryset()

        self.assertEqual(queryset.filter(nome_nazionalita="Armena").count(), 1)
        self.assertFalse(queryset.filter(nome_nazionalita="").exists())

    def test_run_import_nazioni_belfiore_rejects_duplicate_belfiore(self):
        with TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / "nazioni_belfiore.csv"
            file_path.write_text(
                "\n".join(
                    [
                        "nome_nazione,nazionalita,codice_iso2,codice_iso3,codice_belfiore",
                        "ALBANIA,albanese,AL,ALB,Z100",
                        "AFGHANISTAN,afghana,AF,AFG,Z100",
                    ]
                ),
                encoding="utf-8",
            )

            with self.assertRaises(ValidationError):
                run_import_nazioni_belfiore(file_path=file_path)


class AjaxCercaCittaTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser(
            username="admin@example.com",
            email="admin@example.com",
            password="Password123!",
        )
        self.client.force_login(self.user)

    def test_ajax_cerca_citta_supports_lookup_by_id_with_caps(self):
        regione = Regione.objects.create(nome="Lazio", ordine=1, attiva=True)
        provincia = Provincia.objects.create(sigla="RM", nome="Roma", regione=regione, ordine=1, attiva=True)
        citta = Citta.objects.create(
            nome="Roma",
            provincia=provincia,
            codice_istat="058091",
            codice_catastale="H501",
            ordine=1,
            attiva=True,
        )
        cap_1 = CAP.objects.create(codice="00118", citta=citta, ordine=1, attivo=True)
        cap_2 = CAP.objects.create(codice="00119", citta=citta, ordine=2, attivo=True)

        response = self.client.get(reverse("ajax_cerca_citta"), {"id": citta.pk})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(len(payload["results"]), 1)
        result = payload["results"][0]
        self.assertEqual(result["id"], citta.pk)
        self.assertEqual(result["provincia_nome"], "Roma")
        self.assertEqual(result["provincia_sigla"], "RM")
        self.assertEqual(result["regione_nome"], "Lazio")
        self.assertEqual(
            result["caps"],
            [
                {"id": cap_1.pk, "codice": "00118"},
                {"id": cap_2.pk, "codice": "00119"},
            ],
        )

    def test_ajax_cerca_citta_prioritizes_exact_city_match(self):
        regione = Regione.objects.create(nome="Lazio", ordine=1, attiva=True)
        provincia = Provincia.objects.create(sigla="RM", nome="Roma", regione=regione, ordine=1, attiva=True)
        roma = Citta.objects.create(
            nome="Roma",
            provincia=provincia,
            codice_istat="058091",
            codice_catastale="H501",
            ordine=100,
            attiva=True,
        )
        for index in range(25):
            Citta.objects.create(
                nome=f"Aroma {index:02d}",
                provincia=provincia,
                ordine=index,
                attiva=True,
            )

        response = self.client.get(reverse("ajax_cerca_citta"), {"q": "Roma"})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["results"][0]["id"], roma.pk)
        self.assertEqual(payload["results"][0]["label"], "Roma (RM)")

    def test_ajax_cerca_citta_can_include_foreign_countries(self):
        francia, _ = Nazione.objects.update_or_create(
            nome="Francia",
            defaults={
                "codice_iso2": "FR",
                "codice_iso3": "FRA",
                "codice_belfiore": "Z110",
                "ordine": 1,
                "attiva": True,
            },
        )

        response = self.client.get(reverse("ajax_cerca_citta"), {"q": "Fra", "include_nazioni": "1"})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(any(result["type"] == "nazione" for result in payload["results"]))
        result = next(result for result in payload["results"] if result["type"] == "nazione")
        self.assertEqual(result["id"], francia.pk)
        self.assertEqual(result["label"], "Francia")
        self.assertEqual(result["codice_catastale"], "Z110")
        self.assertEqual(result["nazionalita_id"], francia.pk)
        self.assertEqual(result["nazionalita_label"], "Francese")

    def test_crea_indirizzo_page_renders(self):
        response = self.client.get(reverse("crea_indirizzo"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="id_provincia_display"')
        self.assertContains(response, 'id="id_cap_scelto"')
        self.assertContains(response, "Via / Strada / Piazza")
        self.assertContains(response, "Città")

    def test_crea_indirizzo_popup_uses_visual_address_layout(self):
        response = self.client.get(f"{reverse('crea_indirizzo')}?popup=1&target_input_name=indirizzo")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "related-address-popup-hero")
        self.assertContains(response, "related-address-icon-tile")
        self.assertContains(response, "related-address-popup-info")
        self.assertContains(response, "related-address-input-shell")
        self.assertContains(response, "Aggiungi un nuovo indirizzo di residenza o domicilio.")
        self.assertContains(response, '<button type="button" class="related-address-popup-close"')
        self.assertContains(response, "Seleziona il CAP")

    def test_crea_relazione_familiare_popup_uses_visual_relation_layout(self):
        response = self.client.get(
            f"{reverse('crea_relazione_familiare')}?popup=1&target_input_name=relazione_familiare"
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "related-relation-popup-hero")
        self.assertContains(response, "related-relation-icon-tile")
        self.assertContains(response, "related-relation-popup-info")
        self.assertContains(response, "related-relation-input-shell")
        self.assertContains(response, "Definisci il tipo di relazione tra il familiare e il bambino.")
        self.assertContains(response, '<button type="button" class="related-relation-popup-close"')
        self.assertContains(response, 'data-rich-notes="1"')

    @skip("Legacy test basato sulla tabella anagrafica.Famiglia rimossa.")
    def test_crea_stato_relazione_famiglia_popup_uses_visual_status_layout(self):
        response = self.client.get(
            f"{reverse('crea_stato_relazione_famiglia')}?popup=1&target_input_name=stato_relazione_famiglia"
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "related-status-popup-hero")
        self.assertContains(response, "related-status-icon-tile")
        self.assertContains(response, "related-status-popup-info")
        self.assertContains(response, "related-status-input-shell")
        self.assertContains(response, "Definisci lo stato e la priorit")
        self.assertContains(response, '<button type="button" class="related-status-popup-close"')
        self.assertContains(response, "Es. Attiva, Interessata, Ex-Famiglia, Ritirata, etc.")

    def test_crea_studente_hides_inline_actions_and_uses_cancel_back(self):
        response = self.client.get(reverse("crea_studente"))

        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        header_match = re.search(
            r'<div class="page-head-actions family-page-actions">(.*?)</div>\s*</div>\s*<form',
            html,
            re.S,
        )
        self.assertIsNotNone(header_match)
        header_html = header_match.group(1)
        self.assertIn("Salva studente", header_html)
        self.assertIn("Annulla", header_html)
        self.assertNotIn("data-enrollment-card-action", header_html)
        self.assertNotIn("data-relative-card-action", header_html)
        self.assertNotIn("data-document-card-action", header_html)
        self.assertNotIn(">Elenco<", header_html)
        self.assertContains(response, "student-create-stat-grid is-hidden")
        self.assertContains(response, 'id="studente-inline-lock-container"')
        self.assertContains(response, "student-tabs-stack-card is-hidden")
        self.assertContains(response, 'id="sticky-cancel-edit-studente-btn" data-fallback-url="%s"' % reverse("lista_studenti"))
        self.assertContains(response, 'formEl.classList.contains("is-create-mode")')
        self.assertContains(response, "ArborisAppNavigation.resolveBackUrl")

    def test_lista_famiglie_uses_standalone_panel(self):
        response = self.client.get(reverse("lista_famiglie"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "panel-standalone")
        self.assertContains(response, 'data-live-list-form')
        self.assertContains(response, 'data-live-list-target="#famiglie-results"')

    def test_anagrafica_search_lists_enable_progressive_filtering(self):
        list_expectations = [
            ("lista_famiglie", "#famiglie-results"),
            ("lista_familiari", "#familiari-results"),
            ("lista_studenti", "#studenti-results"),
        ]

        for url_name, target in list_expectations:
            with self.subTest(url_name=url_name):
                response = self.client.get(reverse(url_name))
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, 'data-live-list-form')
                self.assertContains(response, f'data-live-list-target="{target}"')
                self.assertContains(response, 'data-live-list-input')

    @skip("Legacy test basato sulla tabella anagrafica.Famiglia rimossa.")
    def test_famiglie_omonime_show_disambiguating_context(self):
        regione = Regione.objects.create(nome="Lazio", ordine=1, attiva=True)
        provincia = Provincia.objects.create(sigla="RM", nome="Roma", regione=regione, ordine=1, attiva=True)
        roma = Citta.objects.create(nome="Roma", provincia=provincia, codice_catastale="H501", ordine=1, attiva=True)
        indirizzo = Indirizzo.objects.create(via="Via Roma", numero_civico="10", citta=roma)
        stato = StatoRelazioneFamiglia.objects.create(stato="Iscritta", ordine=1, attivo=True)
        relazione = RelazioneFamiliare.objects.create(relazione="Padre", ordine=1)
        famiglia = Famiglia.objects.create(
            cognome_famiglia="Rossi",
            stato_relazione_famiglia=stato,
            indirizzo_principale=indirizzo,
            attiva=True,
        )
        Famiglia.objects.create(cognome_famiglia="Rossi", stato_relazione_famiglia=stato, attiva=True)
        familiare = Familiare.objects.create(
            famiglia=famiglia,
            relazione_familiare=relazione,
            nome="Mario",
            cognome="Rossi",
            referente_principale=True,
            attivo=True,
        )
        studente = Studente.objects.create(famiglia=famiglia, nome="Luca", cognome="Rossi", attivo=True)
        StudenteFamiliare.objects.create(
            studente=studente,
            familiare=familiare,
            relazione_familiare=relazione,
            referente_principale=True,
            attivo=True,
        )

        self.assertEqual(str(famiglia), "Rossi")
        self.assertIn("Referenti: Mario Rossi", famiglia.label_select())
        self.assertIn("Studenti: Luca Rossi", famiglia.label_select())
        self.assertIn("Indirizzo: Via Roma 10 - Roma", famiglia.label_select())

        response = self.client.get(reverse("lista_famiglie"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Referenti: Mario Rossi")
        self.assertContains(response, "Studenti: Luca Rossi")
        self.assertNotContains(response, "Indirizzo: Via Roma 10 - Roma")

        response = self.client.get(reverse("lista_familiari"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Luca Rossi")
        self.assertNotContains(response, "Famiglia legacy")
        self.assertNotContains(response, "Indirizzo: Via Roma 10 - Roma")

        response = self.client.get(reverse("lista_studenti"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Mario Rossi")
        self.assertNotContains(response, "Famiglia legacy")
        self.assertNotContains(response, "Indirizzo: Via Roma 10 - Roma")

        form = StudenteStandaloneForm()
        self.assertNotIn("famiglia", form.fields)

        nuovo_familiare_form = FamiliareForm()
        self.assertNotIn("famiglia", nuovo_familiare_form.fields)

    @skip("Legacy test basato sulla tabella anagrafica.Famiglia rimossa.")
    def test_studenti_and_familiari_lists_use_direct_relations_for_context_and_search(self):
        stato = StatoRelazioneFamiglia.objects.create(stato="Iscritta", ordine=1, attivo=True)
        relazione = RelazioneFamiliare.objects.create(relazione="Madre", ordine=1)
        famiglia_studente = Famiglia.objects.create(
            cognome_famiglia="Bianchi",
            stato_relazione_famiglia=stato,
            attiva=True,
        )
        famiglia_familiare = Famiglia.objects.create(
            cognome_famiglia="Verdi",
            stato_relazione_famiglia=stato,
            attiva=True,
        )
        studente = Studente.objects.create(
            famiglia=famiglia_studente,
            nome="Lia",
            cognome="Bianchi",
            attivo=True,
        )
        familiare = Familiare.objects.create(
            famiglia=famiglia_familiare,
            relazione_familiare=relazione,
            nome="Paola",
            cognome="Verdi",
            email="paola@example.com",
            telefono="3331234567",
            attivo=True,
        )
        StudenteFamiliare.objects.create(
            studente=studente,
            familiare=familiare,
            relazione_familiare=relazione,
            attivo=True,
        )

        response = self.client.get(reverse("lista_studenti"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Familiari collegati")
        self.assertContains(response, "Paola Verdi (Madre)")
        self.assertNotContains(response, "Famiglia legacy: Bianchi")

        response = self.client.get(reverse("lista_familiari"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Studenti collegati")
        self.assertContains(response, "Lia Bianchi")
        self.assertNotContains(response, "Famiglia legacy: Verdi")

        response = self.client.get(reverse("lista_studenti"), {"q": "Paola"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Lia Bianchi")

        response = self.client.get(reverse("lista_familiari"), {"q": "Lia"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Paola Verdi")

    def test_indirizzo_form_uses_updated_labels_and_placeholder(self):
        form = IndirizzoForm()

        self.assertEqual(form.fields["via"].label, "Via / Strada / Piazza")
        self.assertEqual(
            form.fields["via"].widget.attrs.get("placeholder"),
            "Via Roma, Piazza Maggiore, Viale dei Mille, etc.",
        )
        self.assertEqual(
            form.fields["numero_civico"].widget.attrs.get("placeholder"),
            "Es. 15, 3/B, interno 2, etc.",
        )
        self.assertEqual(form.fields["citta_search"].label, "Città")
        self.assertEqual(form.fields["citta_search"].widget.attrs.get("placeholder"), "Cerca una città...")


class LuogoNascitaAutocompletePerformanceTests(TestCase):
    def test_crea_famiglia_redirects_to_list_after_family_entity_creation_disabled(self):
        user = User.objects.create_superuser(
            username="nuova-famiglia@example.com",
            email="nuova-famiglia@example.com",
            password="Password123!",
        )
        self.client.force_login(user)

        response = self.client.get(reverse("crea_famiglia"))

        self.assertRedirects(response, reverse("lista_famiglie"), fetch_redirect_response=False)

    def test_crea_famiglia_popup_reports_disabled_entity_creation(self):
        user = User.objects.create_superuser(
            username="nuova-famiglia-popup@example.com",
            email="nuova-famiglia-popup@example.com",
            password="Password123!",
        )
        self.client.force_login(user)

        response = self.client.get(f"{reverse('crea_famiglia')}?popup=1&target_input_name=famiglia")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "La creazione di famiglie come entita autonoma e stata disattivata")

        response = self.client.post(
            f"{reverse('crea_famiglia')}?popup=1&target_input_name=famiglia",
            data={
                "popup": "1",
                "target_input_name": "famiglia",
                "cognome_famiglia": "Popup",
                "stato_relazione_famiglia": "",
                "indirizzo_principale": "",
                "attiva": "on",
                "note": "",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "La creazione di famiglie come entita autonoma e stata disattivata")

    def test_inline_forms_render_selected_birth_city_without_loading_all_cities(self):
        regione = Regione.objects.create(nome="Lazio", ordine=1, attiva=True)
        provincia_roma = Provincia.objects.create(sigla="RM", nome="Roma", regione=regione, ordine=1, attiva=True)
        provincia_milano = Provincia.objects.create(sigla="MI", nome="Milano", regione=regione, ordine=2, attiva=True)
        roma = Citta.objects.create(nome="Roma", provincia=provincia_roma, codice_catastale="H501", ordine=1, attiva=True)
        Citta.objects.create(nome="Milano", provincia=provincia_milano, codice_catastale="F205", ordine=2, attiva=True)

        relazione = RelazioneFamiliare.objects.create(relazione="Madre", ordine=1)
        familiare = Familiare.objects.create(
            relazione_familiare=relazione,
            nome="Maria",
            cognome="Rossi",
            luogo_nascita=roma,
            attivo=True,
        )
        studente = Studente.objects.create(
            nome="Luca",
            cognome="Rossi",
            luogo_nascita=roma,
            attivo=True,
        )

        familiare_form = FamiliareInlineForm(instance=familiare, prefix="familiari-0")
        studente_form = StudenteInlineForm(instance=studente, prefix="studenti-0")

        self.assertIn('type="hidden"', str(familiare_form["luogo_nascita"]))
        self.assertIn("Roma (RM)", str(familiare_form["luogo_nascita_search"]))
        self.assertNotIn("Milano", str(familiare_form["luogo_nascita"]))

        self.assertIn('type="hidden"', str(studente_form["luogo_nascita"]))
        self.assertIn("Roma (RM)", str(studente_form["luogo_nascita_search"]))
        self.assertNotIn("Milano", str(studente_form["luogo_nascita"]))

    @skip("Legacy test basato sulla tabella anagrafica.Famiglia rimossa.")
    def test_modifica_famiglia_page_renders_city_search_inputs(self):
        user = User.objects.create_superuser(
            username="famiglie@example.com",
            email="famiglie@example.com",
            password="Password123!",
        )
        self.client.force_login(user)

        regione = Regione.objects.create(nome="Lazio", ordine=1, attiva=True)
        provincia = Provincia.objects.create(sigla="RM", nome="Roma", regione=regione, ordine=1, attiva=True)
        roma = Citta.objects.create(nome="Roma", provincia=provincia, codice_catastale="H501", ordine=1, attiva=True)
        stato = StatoRelazioneFamiglia.objects.create(stato="Iscritta", ordine=1, attivo=True)
        famiglia = Famiglia.objects.create(cognome_famiglia="Bianchi", stato_relazione_famiglia=stato, attiva=True)
        relazione = RelazioneFamiliare.objects.create(relazione="Padre", ordine=1)
        familiare = Familiare.objects.create(
            famiglia=famiglia,
            relazione_familiare=relazione,
            nome="Paolo",
            cognome="Bianchi",
            sesso="M",
            luogo_nascita=roma,
            referente_principale=True,
            attivo=True,
        )
        studente = Studente.objects.create(
            famiglia=famiglia,
            nome="Anna",
            cognome="Bianchi",
            luogo_nascita=roma,
            attivo=True,
        )
        tipo_documento = TipoDocumento.objects.create(tipo_documento="Contratto iscrizione", ordine=1, attivo=True)
        documento_famiglia = Documento.objects.create(
            famiglia=famiglia,
            tipo_documento=tipo_documento,
            descrizione="Documento famiglia",
            file=SimpleUploadedFile("contratto.pdf", b"contratto", content_type="application/pdf"),
        )
        documento_familiare = Documento.objects.create(
            familiare=familiare,
            tipo_documento=tipo_documento,
            descrizione="Documento familiare",
            file=SimpleUploadedFile("familiare.pdf", b"familiare", content_type="application/pdf"),
        )
        documento_studente = Documento.objects.create(
            studente=studente,
            tipo_documento=tipo_documento,
            descrizione="Documento studente",
            file=SimpleUploadedFile("studente.pdf", b"studente", content_type="application/pdf"),
        )

        response = self.client.get(reverse("modifica_famiglia", kwargs={"pk": famiglia.pk}))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["count_documenti"], 2)
        self.assertContains(response, 'name="familiari-0-luogo_nascita_search"')
        self.assertContains(response, 'name="studenti-0-luogo_nascita_search"')
        self.assertContains(response, 'id="family-card-sticky-actions"')
        self.assertContains(response, 'data-family-card-sticky-save="1"')
        self.assertContains(response, 'data-family-card-sticky-cancel="1"')
        self.assertNotContains(response, 'data-family-general-action="edit"')
        self.assertContains(response, 'data-relative-card-action="add"')
        self.assertContains(response, 'data-relative-card-action="edit"')
        self.assertContains(response, 'data-relative-form-prefix="familiari-0"')
        self.assertNotContains(response, 'data-document-card-action="add"')
        self.assertNotContains(response, 'data-document-card-action="edit"')
        self.assertContains(response, 'data-document-card-action="delete"')
        self.assertNotContains(response, 'data-document-form-prefix="documenti-0"')
        self.assertContains(response, reverse("elimina_documento", kwargs={"pk": documento_familiare.pk}))
        self.assertContains(response, reverse("elimina_documento", kwargs={"pk": documento_studente.pk}))
        self.assertNotContains(response, reverse("elimina_documento", kwargs={"pk": documento_famiglia.pk}))
        self.assertNotContains(response, "Modifica dati generali")
        self.assertNotContains(response, "Documento famiglia")
        self.assertContains(response, "family-relation-pill")
        self.assertContains(response, "is-male")
        self.assertNotContains(response, 'class="family-person-chip">Referente</span>')
        self.assertNotContains(response, 'id="enable-edit-famiglia-btn"')

    @skip("Legacy test basato sulla tabella anagrafica.Famiglia rimossa.")
    def test_modifica_famiglia_student_cards_show_current_class_or_group(self):
        user = User.objects.create_superuser(
            username="famiglie-classi@example.com",
            email="famiglie-classi@example.com",
            password="Password123!",
        )
        self.client.force_login(user)

        today = timezone.localdate()
        stato = StatoRelazioneFamiglia.objects.create(stato="Iscritta", ordine=1, attivo=True)
        famiglia = Famiglia.objects.create(cognome_famiglia="Bianchi", stato_relazione_famiglia=stato, attiva=True)
        studente_classe = Studente.objects.create(
            famiglia=famiglia,
            nome="Anna",
            cognome="Bianchi",
            attivo=True,
        )
        studente_pluriclasse = Studente.objects.create(
            famiglia=famiglia,
            nome="Luca",
            cognome="Bianchi",
            attivo=True,
        )
        anno = AnnoScolastico.objects.create(
            nome_anno_scolastico="Anno corrente test famiglia",
            data_inizio=today - timedelta(days=30),
            data_fine=today + timedelta(days=30),
        )
        classe_infanzia = Classe.objects.create(
            nome_classe="Infanzia",
            sezione_classe="A",
            ordine_classe=1,
            attiva=True,
        )
        classe_seconda = Classe.objects.create(
            nome_classe="Seconda primaria",
            ordine_classe=2,
            attiva=True,
        )
        gruppo_classe = GruppoClasse.objects.create(
            nome_gruppo_classe="Primaria mista",
            anno_scolastico=anno,
            attivo=True,
        )
        gruppo_classe.classi.add(classe_seconda)
        stato_iscrizione = StatoIscrizione.objects.create(stato_iscrizione="Attiva", ordine=1, attiva=True)
        condizione = CondizioneIscrizione.objects.create(
            anno_scolastico=anno,
            nome_condizione_iscrizione="Retta standard",
            numero_mensilita_default=10,
            attiva=True,
        )
        Iscrizione.objects.create(
            studente=studente_classe,
            classe=classe_infanzia,
            anno_scolastico=anno,
            stato_iscrizione=stato_iscrizione,
            condizione_iscrizione=condizione,
            attiva=True,
        )
        Iscrizione.objects.create(
            studente=studente_pluriclasse,
            classe=classe_seconda,
            gruppo_classe=gruppo_classe,
            anno_scolastico=anno,
            stato_iscrizione=stato_iscrizione,
            condizione_iscrizione=condizione,
            attiva=True,
        )

        response = self.client.get(reverse("modifica_famiglia", kwargs={"pk": famiglia.pk}))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Classe: Infanzia A")
        self.assertContains(response, "Pluriclasse: Primaria mista (Seconda primaria)")

    @skip("Legacy test basato sulla tabella anagrafica.Famiglia rimossa.")
    def test_modifica_famiglia_rate_card_can_switch_to_future_school_year(self):
        user = User.objects.create_superuser(
            username="famiglie-rette-switch@example.com",
            email="famiglie-rette-switch@example.com",
            password="Password123!",
        )
        self.client.force_login(user)

        today = timezone.localdate()
        stato = StatoRelazioneFamiglia.objects.create(stato="Iscritta", ordine=1, attivo=True)
        famiglia = Famiglia.objects.create(cognome_famiglia="Verdi", stato_relazione_famiglia=stato, attiva=True)
        anna = Studente.objects.create(famiglia=famiglia, nome="Anna", cognome="Verdi", attivo=True)
        luca = Studente.objects.create(famiglia=famiglia, nome="Luca", cognome="Verdi", attivo=True)
        anno_corrente = AnnoScolastico.objects.create(
            nome_anno_scolastico="Anno corrente rette famiglia",
            data_inizio=today - timedelta(days=120),
            data_fine=today + timedelta(days=30),
        )
        anno_futuro = AnnoScolastico.objects.create(
            nome_anno_scolastico="Anno futuro rette famiglia",
            data_inizio=today + timedelta(days=31),
            data_fine=today + timedelta(days=395),
        )
        stato_iscrizione = StatoIscrizione.objects.create(stato_iscrizione="Attiva", ordine=1, attiva=True)
        condizione_corrente = CondizioneIscrizione.objects.create(
            anno_scolastico=anno_corrente,
            nome_condizione_iscrizione="Retta standard corrente",
            numero_mensilita_default=10,
            attiva=True,
        )
        condizione_futura = CondizioneIscrizione.objects.create(
            anno_scolastico=anno_futuro,
            nome_condizione_iscrizione="Retta standard futura",
            numero_mensilita_default=10,
            attiva=True,
        )
        TariffaCondizioneIscrizione.objects.create(
            condizione_iscrizione=condizione_corrente,
            ordine_figlio_da=1,
            retta_annuale=Decimal("1200.00"),
            attiva=True,
        )
        TariffaCondizioneIscrizione.objects.create(
            condizione_iscrizione=condizione_futura,
            ordine_figlio_da=1,
            retta_annuale=Decimal("1500.00"),
            attiva=True,
        )
        Iscrizione.objects.create(
            studente=anna,
            anno_scolastico=anno_corrente,
            stato_iscrizione=stato_iscrizione,
            condizione_iscrizione=condizione_corrente,
            attiva=True,
        )
        Iscrizione.objects.create(
            studente=luca,
            anno_scolastico=anno_futuro,
            stato_iscrizione=stato_iscrizione,
            condizione_iscrizione=condizione_futura,
            attiva=True,
        )

        response = self.client.get(reverse("modifica_famiglia", kwargs={"pk": famiglia.pk}))

        self.assertEqual(response.status_code, 200)
        summary = response.context["famiglia_rette_summary"]
        self.assertTrue(summary["has_year_switch"])
        self.assertEqual([item["anno_id"] for item in summary["years"]], [anno_corrente.pk, anno_futuro.pk])
        self.assertContains(response, 'data-family-rate-year-tab="anno-%s"' % anno_corrente.pk)
        self.assertContains(response, 'data-family-rate-year-tab="anno-%s"' % anno_futuro.pk)
        self.assertContains(response, "Anno corrente rette famiglia")
        self.assertContains(response, "Anno futuro rette famiglia")
        self.assertContains(response, "Anna Verdi")
        self.assertContains(response, "Luca Verdi")

    @skip("Legacy test basato sulla tabella anagrafica.Famiglia rimossa.")
    def test_modifica_famiglia_page_shows_recent_component_activity(self):
        user = User.objects.create_superuser(
            username="audit-famiglie@example.com",
            email="audit-famiglie@example.com",
            password="Password123!",
            first_name="Giulia",
            last_name="Rossi",
        )
        updater = User.objects.create_user(
            username="audit-operatore@example.com",
            email="audit-operatore@example.com",
            password="Password123!",
            first_name="Marco",
            last_name="Bianchi",
        )
        ruolo_creatore = SistemaRuoloPermessi.objects.create(nome="Direzione")
        ruolo_operatore = SistemaRuoloPermessi.objects.create(nome="Segreteria")
        SistemaUtentePermessi.objects.create(user=user, ruolo_permessi=ruolo_creatore)
        SistemaUtentePermessi.objects.create(user=updater, ruolo_permessi=ruolo_operatore)
        self.client.force_login(user)

        stato = StatoRelazioneFamiglia.objects.create(stato="Iscritta", ordine=1, attivo=True)
        famiglia = Famiglia.objects.create(cognome_famiglia="Audit", stato_relazione_famiglia=stato, attiva=True)
        relazione = RelazioneFamiliare.objects.create(relazione="Madre", ordine=1)
        familiare = Familiare.objects.create(
            famiglia=famiglia,
            relazione_familiare=relazione,
            nome="Paola",
            cognome="Audit",
            attivo=True,
        )
        base_kwargs = {
            "modulo": "anagrafica",
            "app_label": "anagrafica",
            "model_name": "famiglia",
            "model_verbose_name": "Famiglia",
            "oggetto_id": str(famiglia.pk),
            "oggetto_label": str(famiglia),
            "campi_coinvolti": [],
        }
        SistemaOperazioneCronologia.objects.create(
            **base_kwargs,
            azione=AzioneOperazioneCronologia.CREAZIONE,
            utente=user,
            utente_label=user.get_full_name(),
            descrizione="Creata famiglia.",
        )
        SistemaOperazioneCronologia.objects.create(
            **base_kwargs,
            azione=AzioneOperazioneCronologia.MODIFICA,
            utente=updater,
            utente_label=updater.get_full_name(),
            descrizione="Modificata famiglia.",
        )
        SistemaOperazioneCronologia.objects.create(
            modulo="anagrafica",
            app_label="anagrafica",
            model_name="familiare",
            model_verbose_name="Familiare",
            oggetto_id=str(familiare.pk),
            oggetto_label=str(familiare),
            campi_coinvolti=[],
            azione=AzioneOperazioneCronologia.MODIFICA,
            utente=updater,
            utente_label=updater.get_full_name(),
            descrizione="Aggiornato familiare collegato.",
        )

        response = self.client.get(reverse("modifica_famiglia", kwargs={"pk": famiglia.pk}))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Informazioni di sistema")
        self.assertNotContains(response, "Creato da")
        self.assertNotContains(response, "Aggiornato da")
        self.assertContains(response, "Cronologia attivit")
        self.assertNotContains(response, "Creata famiglia.")
        self.assertNotContains(response, "Modificata famiglia.")
        self.assertContains(response, "Aggiornato familiare collegato.")
        self.assertGreaterEqual(len(response.context["famiglia_activity_entries"]), 1)
        self.assertLessEqual(len(response.context["famiglia_activity_entries"]), 5)

    def test_lista_famiglie_uses_direct_relations_without_legacy_family(self):
        user = User.objects.create_superuser(
            username="famiglie-logiche@example.com",
            email="famiglie-logiche@example.com",
            password="Password123!",
        )
        self.client.force_login(user)

        relazione = RelazioneFamiliare.objects.create(relazione="Madre", ordine=1)
        familiare = Familiare.objects.create(
            relazione_familiare=relazione,
            nome="Maria",
            cognome="Rossi",
            referente_principale=True,
            attivo=True,
        )
        studente = Studente.objects.create(
            nome="Luca",
            cognome="Rossi",
            attivo=True,
        )
        StudenteFamiliare.objects.create(
            studente=studente,
            familiare=familiare,
            relazione_familiare=relazione,
            referente_principale=True,
            attivo=True,
        )

        response = self.client.get(reverse("lista_famiglie"))

        logical_url = reverse("modifica_famiglia_logica", kwargs={"key": f"s-{studente.pk}"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Rossi")
        self.assertContains(response, "Referenti: Maria Rossi")
        self.assertContains(response, "Studenti: Luca Rossi")
        self.assertContains(response, logical_url)

    def test_modifica_famiglia_logica_renders_relation_group_without_legacy_family(self):
        user = User.objects.create_superuser(
            username="scheda-famiglia-logica@example.com",
            email="scheda-famiglia-logica@example.com",
            password="Password123!",
        )
        self.client.force_login(user)

        relazione = RelazioneFamiliare.objects.create(relazione="Padre", ordine=1)
        familiare = Familiare.objects.create(
            relazione_familiare=relazione,
            nome="Paolo",
            cognome="Bianchi",
            referente_principale=True,
            attivo=True,
        )
        studente = Studente.objects.create(
            nome="Anna",
            cognome="Bianchi",
            attivo=True,
        )
        StudenteFamiliare.objects.create(
            studente=studente,
            familiare=familiare,
            relazione_familiare=relazione,
            referente_principale=True,
            attivo=True,
        )

        response = self.client.get(
            reverse("modifica_famiglia_logica", kwargs={"key": f"s-{studente.pk}"})
        )

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("legacy_famiglia", response.context)
        self.assertEqual(response.context["count_studenti"], 1)
        self.assertEqual(response.context["count_familiari"], 1)
        self.assertContains(response, "Famiglia Bianchi")
        self.assertContains(response, "Anna Bianchi")
        self.assertContains(response, "Paolo Bianchi")
        self.assertNotContains(response, "Informazioni di sistema")
        self.assertNotContains(response, "data-document-card-action")

    @skip("Legacy test basato sulla tabella anagrafica.Famiglia rimossa.")
    def test_scheda_studente_links_to_logical_family(self):
        user = User.objects.create_superuser(
            username="scheda-studente-famiglia-logica@example.com",
            email="scheda-studente-famiglia-logica@example.com",
            password="Password123!",
        )
        self.client.force_login(user)
        stato = StatoRelazioneFamiglia.objects.create(stato="Iscritta", ordine=1, attivo=True)
        famiglia = Famiglia.objects.create(cognome_famiglia="Rossi", stato_relazione_famiglia=stato, attiva=True)
        studente = Studente.objects.create(nome="Luca", cognome="Rossi", famiglia=famiglia, attivo=True)

        response = self.client.get(reverse("modifica_studente", kwargs={"pk": studente.pk}))

        logical_url = reverse("modifica_famiglia_logica", kwargs={"key": f"s-{studente.pk}"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, logical_url)
        self.assertNotContains(response, reverse("modifica_famiglia", kwargs={"pk": famiglia.pk}))

    @skip("Legacy test basato sulla tabella anagrafica.Famiglia rimossa.")
    def test_scheda_familiare_links_to_logical_family(self):
        user = User.objects.create_superuser(
            username="scheda-familiare-famiglia-logica@example.com",
            email="scheda-familiare-famiglia-logica@example.com",
            password="Password123!",
        )
        self.client.force_login(user)
        stato = StatoRelazioneFamiglia.objects.create(stato="Iscritta", ordine=1, attivo=True)
        relazione = RelazioneFamiliare.objects.create(relazione="Madre", ordine=1)
        famiglia = Famiglia.objects.create(cognome_famiglia="Verdi", stato_relazione_famiglia=stato, attiva=True)
        familiare = Familiare.objects.create(
            nome="Paola",
            cognome="Verdi",
            famiglia=famiglia,
            relazione_familiare=relazione,
            attivo=True,
        )

        response = self.client.get(reverse("modifica_familiare", kwargs={"pk": familiare.pk}))

        logical_url = reverse("modifica_famiglia_logica", kwargs={"key": f"f-{familiare.pk}"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, logical_url)
        self.assertNotContains(response, reverse("modifica_famiglia", kwargs={"pk": famiglia.pk}))


class FamiliareCurrentDetailViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser(
            username="familiare-current-detail@example.com",
            email="familiare-current-detail@example.com",
            password="Password123!",
        )
        self.client.force_login(self.user)
        self.regione = Regione.objects.create(nome="Emilia-Romagna", ordine=1, attiva=True)
        self.provincia = Provincia.objects.create(
            sigla="BO",
            nome="Bologna",
            regione=self.regione,
            ordine=1,
            attiva=True,
        )
        self.citta = Citta.objects.create(
            nome="Bologna",
            provincia=self.provincia,
            codice_catastale="A944",
            ordine=1,
            attiva=True,
        )
        self.indirizzo_condiviso = Indirizzo.objects.create(
            via="Via Comune",
            numero_civico="10",
            citta=self.citta,
        )
        self.indirizzo_secondario = Indirizzo.objects.create(
            via="Via Secondaria",
            numero_civico="5",
            citta=self.citta,
        )
        self.relazione = RelazioneFamiliare.objects.create(relazione="Madre", ordine=1)
        self.altra_relazione = RelazioneFamiliare.objects.create(relazione="Padre", ordine=2)
        self.familiare = Familiare.objects.create(
            relazione_familiare=self.relazione,
            nome="Ada",
            cognome="Rossi",
            telefono="3331234567",
            email="ada.rossi@example.com",
            attivo=True,
        )
        self.parente = Familiare.objects.create(
            relazione_familiare=self.altra_relazione,
            nome="Mario",
            cognome="Rossi",
            indirizzo=self.indirizzo_condiviso,
            attivo=True,
        )
        self.studente = Studente.objects.create(
            nome="Luca",
            cognome="Rossi",
            indirizzo=self.indirizzo_condiviso,
            attivo=True,
        )
        StudenteFamiliare.objects.create(
            studente=self.studente,
            familiare=self.familiare,
            relazione_familiare=self.relazione,
            attivo=True,
        )
        StudenteFamiliare.objects.create(
            studente=self.studente,
            familiare=self.parente,
            relazione_familiare=self.altra_relazione,
            attivo=True,
        )
        self.tipo_contratto = TipoContrattoDipendente.objects.create(nome="Tempo indeterminato")
        self.profilo = Dipendente.objects.create(
            familiare_collegato=self.familiare,
            ruolo_anagrafico=RuoloAnagraficoDipendente.EDUCATORE,
            nome="Ada",
            cognome="Rossi",
            email="ada.rossi@example.com",
            telefono="3331234567",
            mansione="Coordinamento",
            iban="IT60X0542811101000000123456",
            stato=StatoDipendente.ATTIVO,
        )
        self.contratto = ContrattoDipendente.objects.create(
            dipendente=self.profilo,
            tipo_contratto=self.tipo_contratto,
            descrizione="Contratto principale",
            data_inizio=date(2026, 1, 1),
            mansione="Coordinamento",
            retribuzione_lorda_mensile=Decimal("1800.00"),
            attivo=True,
        )
        self.busta = BustaPagaDipendente.objects.create(
            dipendente=self.profilo,
            contratto=self.contratto,
            anno=2026,
            mese=5,
            stato=StatoBustaPaga.EFFETTIVA,
            netto_previsto=Decimal("1300.00"),
            costo_azienda_previsto=Decimal("2200.00"),
        )

    def test_modifica_familiare_renders_work_profile_inline_with_tabs(self):
        with TemporaryDirectory() as tmpdir:
            with override_settings(MEDIA_ROOT=tmpdir):
                self.busta.file_busta_paga = SimpleUploadedFile(
                    "busta-maggio.pdf",
                    b"pdf",
                    content_type="application/pdf",
                )
                self.busta.save(update_fields=["file_busta_paga"])
                DocumentoDipendente.objects.create(
                    dipendente=self.profilo,
                    busta_paga=self.busta,
                    titolo="Allegato cedolino",
                    file=SimpleUploadedFile(
                        "allegato-cedolino.pdf",
                        b"pdf",
                        content_type="application/pdf",
                    ),
                )

                response = self.client.get(reverse("modifica_familiare", kwargs={"pk": self.familiare.pk}))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="profilo-lavorativo-inline"')
        self.assertContains(response, 'data-work-tab-target="tab-lavoro-generali"')
        self.assertContains(response, 'data-work-tab-target="tab-lavoro-contratti"')
        self.assertContains(response, 'data-work-tab-target="tab-lavoro-buste"')
        self.assertContains(response, "Dati generali")
        self.assertContains(response, "Educatore")
        self.assertContains(response, "Coordinamento")
        self.assertContains(response, "IT60X0542811101000000123456")
        self.assertContains(response, "Contratto principale")
        self.assertContains(response, reverse("crea_contratto_dipendente", kwargs={"dipendente_pk": self.profilo.pk}))
        self.assertContains(response, reverse("modifica_contratto_dipendente", kwargs={"pk": self.contratto.pk}))
        self.assertContains(response, reverse("elimina_contratto_dipendente", kwargs={"pk": self.contratto.pk}))
        self.assertContains(response, "05/2026")
        self.assertContains(response, "File busta paga")
        self.assertContains(response, "Allegato cedolino")
        self.assertContains(response, reverse("crea_busta_paga_dipendente"))
        self.assertContains(response, reverse("modifica_busta_paga_dipendente", kwargs={"pk": self.busta.pk}))
        self.assertContains(response, reverse("elimina_busta_paga_dipendente", kwargs={"pk": self.busta.pk}))

    def test_modifica_familiare_labels_work_reference_as_materia_when_no_class(self):
        self.profilo.materia = "Francese"
        self.profilo.save(update_fields=["materia"])

        response = self.client.get(reverse("modifica_familiare", kwargs={"pk": self.familiare.pk}))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Materia")
        self.assertContains(response, "Francese")
        self.assertNotIn("<span>Riferimento</span>", response.content.decode("utf-8"))

    def test_modifica_familiare_renders_related_address_suggestions_and_card_sticky_menu(self):
        response = self.client.get(reverse("modifica_familiare", kwargs={"pk": self.familiare.pk}))

        self.assertEqual(response.status_code, 200)
        suggestions = response.context["familiare_indirizzi_correlati"]
        self.assertEqual(suggestions[0]["id"], str(self.indirizzo_condiviso.pk))
        self.assertEqual(suggestions[0]["count"], 2)
        self.assertContains(response, 'data-searchable-min-chars="3"')
        self.assertContains(response, 'data-address-suggestion-apply')
        self.assertContains(response, "Via Comune 10 - Bologna (2)")
        self.assertContains(response, 'id="familiare-indirizzi-correlati"')
        self.assertContains(response, 'id="relative-card-sticky-actions"')
        self.assertContains(response, 'data-relative-card-sticky-cancel="1"')
        self.assertContains(response, 'id="relative-card-sticky-cancel"')

    def test_modifica_familiare_renders_current_and_future_student_enrollment_badges(self):
        today = timezone.localdate()
        anno_corrente = AnnoScolastico.objects.create(
            nome_anno_scolastico="2025/2026",
            data_inizio=today - timedelta(days=30),
            data_fine=today + timedelta(days=30),
            attivo=True,
        )
        anno_futuro = AnnoScolastico.objects.create(
            nome_anno_scolastico="2026/2027",
            data_inizio=today + timedelta(days=90),
            data_fine=today + timedelta(days=450),
            attivo=True,
        )
        stato_iscrizione = StatoIscrizione.objects.create(stato_iscrizione="Iscritto", ordine=1, attiva=True)
        condizione_corrente = CondizioneIscrizione.objects.create(
            anno_scolastico=anno_corrente,
            nome_condizione_iscrizione="Standard corrente",
            numero_mensilita_default=10,
        )
        condizione_futura = CondizioneIscrizione.objects.create(
            anno_scolastico=anno_futuro,
            nome_condizione_iscrizione="Standard futuro",
            numero_mensilita_default=10,
        )
        Iscrizione.objects.create(
            studente=self.studente,
            anno_scolastico=anno_corrente,
            stato_iscrizione=stato_iscrizione,
            condizione_iscrizione=condizione_corrente,
            data_iscrizione=anno_corrente.data_inizio,
            data_fine_iscrizione=anno_corrente.data_fine,
            attiva=True,
        )
        Iscrizione.objects.create(
            studente=self.studente,
            anno_scolastico=anno_futuro,
            stato_iscrizione=stato_iscrizione,
            condizione_iscrizione=condizione_futura,
            data_iscrizione=today,
            data_fine_iscrizione=anno_futuro.data_fine,
            attiva=True,
        )

        response = self.client.get(reverse("modifica_familiare", kwargs={"pk": self.familiare.pk}))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "ISCRITTO 2025/2026")
        self.assertContains(response, "PREISCRITTO 2026/2027")
        self.assertNotContains(response, "NON ISCRITTO")


@skip("Legacy test basato sulla tabella anagrafica.Famiglia rimossa.")
class FamigliaInlineDefaultsTests(TestCase):
    def test_new_person_forms_default_to_italian_nationality(self):
        italia = Nazione.objects.get(nome__iexact="Italia")

        familiare_form = FamiliareForm()
        studente_form = StudenteStandaloneForm()

        self.assertEqual(familiare_form.initial["nazionalita"], italia.pk)
        self.assertEqual(studente_form.initial["nazionalita"], italia.pk)


    def test_new_familiare_forms_default_referente_principale_checked(self):
        standalone_form = FamiliareForm()
        inline_form = FamiliareInlineForm(prefix="familiari-0")

        self.assertIs(standalone_form["referente_principale"].value(), True)
        self.assertIn("checked", str(standalone_form["referente_principale"]))
        self.assertIs(inline_form["referente_principale"].value(), True)
        self.assertIn("checked", str(inline_form["referente_principale"]))

    def test_inline_forms_do_not_inherit_legacy_family_address(self):
        regione = Regione.objects.create(nome="Lazio", ordine=1, attiva=True)
        provincia = Provincia.objects.create(sigla="RM", nome="Roma", regione=regione, ordine=1, attiva=True)
        roma = Citta.objects.create(nome="Roma", provincia=provincia, codice_catastale="H501", ordine=1, attiva=True)
        indirizzo = Indirizzo.objects.create(via="Via Roma", numero_civico="10", citta=roma)
        stato = StatoRelazioneFamiglia.objects.create(stato="Iscritta", ordine=1, attivo=True)
        famiglia = Famiglia.objects.create(
            cognome_famiglia="Verdi",
            stato_relazione_famiglia=stato,
            indirizzo_principale=indirizzo,
            attiva=True,
        )
        relazione = RelazioneFamiliare.objects.create(relazione="Madre", ordine=1)
        familiare = Familiare.objects.create(
            famiglia=famiglia,
            relazione_familiare=relazione,
            nome="Laura",
            cognome="Verdi",
            attivo=True,
        )
        studente = Studente.objects.create(
            famiglia=famiglia,
            nome="Marco",
            cognome="Verdi",
            attivo=True,
        )

        familiare_form = FamiliareInlineForm(instance=familiare, prefix="familiari-0")
        studente_form = StudenteInlineForm(instance=studente, prefix="studenti-0")

        self.assertIsNone(familiare_form["indirizzo"].value())
        self.assertNotIn("indirizzo_search", familiare_form.initial)
        self.assertNotIn('data-inherited-address="1"', str(familiare_form["indirizzo"]))

        self.assertIsNone(studente_form["indirizzo"].value())
        self.assertNotIn("indirizzo_search", studente_form.initial)
        self.assertNotIn('data-inherited-address="1"', str(studente_form["indirizzo"]))

    def test_forms_keep_explicit_address_without_legacy_family_normalization(self):
        regione = Regione.objects.create(nome="Lazio", ordine=1, attiva=True)
        provincia = Provincia.objects.create(sigla="RM", nome="Roma", regione=regione, ordine=1, attiva=True)
        roma = Citta.objects.create(nome="Roma", provincia=provincia, codice_catastale="H501", ordine=1, attiva=True)
        indirizzo = Indirizzo.objects.create(via="Via Roma", numero_civico="10", citta=roma)
        stato = StatoRelazioneFamiglia.objects.create(stato="Iscritta", ordine=1, attivo=True)
        famiglia = Famiglia.objects.create(
            cognome_famiglia="Verdi",
            stato_relazione_famiglia=stato,
            indirizzo_principale=indirizzo,
            attiva=True,
        )
        relazione = RelazioneFamiliare.objects.create(relazione="Madre", ordine=1)

        familiare_form = FamiliareForm(
            data={
                "famiglia": famiglia.pk,
                "relazione_familiare": relazione.pk,
                "indirizzo": indirizzo.pk,
                "nome": "Laura",
                "cognome": "Verdi",
                "telefono": "",
                "email": "",
                "codice_fiscale": "",
                "sesso": "F",
                "data_nascita": "1980-01-15",
                "luogo_nascita": roma.pk,
                "luogo_nascita_search": "Roma (RM)",
                "convivente": "",
                "referente_principale": "",
                "abilitato_scambio_retta": "",
                "attivo": "on",
                "note": "",
            }
        )
        self.assertTrue(familiare_form.is_valid(), familiare_form.errors)
        self.assertEqual(familiare_form.cleaned_data["indirizzo"], indirizzo)

        studente_form = StudenteForm(
            data={
                "nome": "Marco",
                "cognome": "Verdi",
                "sesso": "M",
                "data_nascita": "2015-05-20",
                "luogo_nascita": roma.pk,
                "luogo_nascita_search": "Roma (RM)",
                "codice_fiscale": "",
                "indirizzo": indirizzo.pk,
                "attivo": "on",
            },
            instance=Studente(famiglia=famiglia),
        )
        self.assertTrue(studente_form.is_valid(), studente_form.errors)
        self.assertEqual(studente_form.cleaned_data["indirizzo"], indirizzo)

    def test_familiare_form_accepts_custom_foreign_birthplace(self):
        stato = StatoRelazioneFamiglia.objects.create(stato="Iscritta", ordine=1, attivo=True)
        famiglia = Famiglia.objects.create(cognome_famiglia="Dubois", stato_relazione_famiglia=stato, attiva=True)
        relazione = RelazioneFamiliare.objects.create(relazione="Madre", ordine=1)

        form = FamiliareForm(
            data={
                "famiglia": famiglia.pk,
                "relazione_familiare": relazione.pk,
                "indirizzo": "",
                "nome": "Claire",
                "cognome": "Dubois",
                "telefono": "",
                "email": "",
                "codice_fiscale": "",
                "sesso": "F",
                "data_nascita": "1985-01-15",
                "luogo_nascita": "",
                "nazione_nascita": "",
                "luogo_nascita_custom": "Parigi",
                "luogo_nascita_search": "Parigi",
                "nazionalita": "",
                "convivente": "",
                "referente_principale": "",
                "abilitato_scambio_retta": "",
                "attivo": "on",
                "note": "",
            }
        )

        self.assertTrue(form.is_valid(), form.errors)
        self.assertIsNone(form.cleaned_data["luogo_nascita"])
        self.assertIsNone(form.cleaned_data["nazione_nascita"])
        self.assertEqual(form.cleaned_data["luogo_nascita_custom"], "Parigi")

    def test_familiare_form_accepts_selected_foreign_country_birthplace(self):
        stato = StatoRelazioneFamiglia.objects.create(stato="Iscritta", ordine=1, attivo=True)
        famiglia = Famiglia.objects.create(cognome_famiglia="Dubois", stato_relazione_famiglia=stato, attiva=True)
        relazione = RelazioneFamiliare.objects.create(relazione="Madre", ordine=1)
        francia, _ = Nazione.objects.update_or_create(
            nome="Francia",
            defaults={
                "codice_iso2": "FR",
                "codice_iso3": "FRA",
                "codice_belfiore": "Z110",
                "ordine": 2,
                "attiva": True,
            },
        )

        form = FamiliareForm(
            data={
                "famiglia": famiglia.pk,
                "relazione_familiare": relazione.pk,
                "indirizzo": "",
                "nome": "Claire",
                "cognome": "Dubois",
                "telefono": "",
                "email": "",
                "codice_fiscale": "",
                "sesso": "F",
                "data_nascita": "1985-01-15",
                "luogo_nascita": "",
                "nazione_nascita": francia.pk,
                "luogo_nascita_custom": "",
                "luogo_nascita_search": "Francia",
                "nazionalita": francia.pk,
                "convivente": "",
                "referente_principale": "",
                "abilitato_scambio_retta": "",
                "attivo": "on",
                "note": "",
            }
        )

        self.assertTrue(form.is_valid(), form.errors)
        self.assertIsNone(form.cleaned_data["luogo_nascita"])
        self.assertEqual(form.cleaned_data["nazione_nascita"], francia)
        self.assertEqual(form.cleaned_data["luogo_nascita_custom"], "")
        self.assertEqual(form.cleaned_data["nazionalita"], francia)

    def test_studente_standalone_form_ignores_legacy_family_initial_and_keeps_cf_binding(self):
        regione = Regione.objects.create(nome="Lazio", ordine=1, attiva=True)
        provincia = Provincia.objects.create(sigla="RM", nome="Roma", regione=regione, ordine=1, attiva=True)
        roma = Citta.objects.create(nome="Roma", provincia=provincia, codice_catastale="H501", ordine=1, attiva=True)
        indirizzo = Indirizzo.objects.create(via="Via Roma", numero_civico="10", citta=roma)
        stato = StatoRelazioneFamiglia.objects.create(stato="Iscritta", ordine=1, attivo=True)
        famiglia = Famiglia.objects.create(
            cognome_famiglia="Verdi",
            stato_relazione_famiglia=stato,
            indirizzo_principale=indirizzo,
            attiva=True,
        )

        form = StudenteStandaloneForm(initial={"famiglia": famiglia.pk})

        self.assertNotIn("famiglia", form.fields)
        self.assertIsNone(form["indirizzo"].value())
        self.assertNotIn("famiglia_search", form.initial)
        self.assertNotIn("indirizzo_search", form.initial)
        self.assertNotIn('data-inherited-address="1"', str(form["indirizzo"]))
        self.assertIn('data-cf-luogo-id="1"', str(form["luogo_nascita"]))

    def test_studente_standalone_form_keeps_explicit_address_without_legacy_family_normalization(self):
        regione = Regione.objects.create(nome="Lazio", ordine=1, attiva=True)
        provincia = Provincia.objects.create(sigla="RM", nome="Roma", regione=regione, ordine=1, attiva=True)
        roma = Citta.objects.create(nome="Roma", provincia=provincia, codice_catastale="H501", ordine=1, attiva=True)
        indirizzo = Indirizzo.objects.create(via="Via Roma", numero_civico="10", citta=roma)
        stato = StatoRelazioneFamiglia.objects.create(stato="Iscritta", ordine=1, attivo=True)
        famiglia = Famiglia.objects.create(
            cognome_famiglia="Verdi",
            stato_relazione_famiglia=stato,
            indirizzo_principale=indirizzo,
            attiva=True,
        )

        form = StudenteStandaloneForm(
            data={
                "famiglia": famiglia.pk,
                "cognome": "Verdi",
                "nome": "Marco",
                "sesso": "M",
                "data_nascita": "2015-05-20",
                "luogo_nascita": roma.pk,
                "luogo_nascita_search": "Roma (RM)",
                "codice_fiscale": "",
                "indirizzo": indirizzo.pk,
                "attivo": "on",
                "note": "",
            }
        )

        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data["indirizzo"], indirizzo)

    def test_student_and_relative_forms_save_direct_relations(self):
        stato = StatoRelazioneFamiglia.objects.create(stato="Iscritta", ordine=1, attivo=True)
        relazione = RelazioneFamiliare.objects.create(relazione="Madre", ordine=1)
        famiglia_rossi = Famiglia.objects.create(cognome_famiglia="Rossi", stato_relazione_famiglia=stato, attiva=True)
        famiglia_bianchi = Famiglia.objects.create(cognome_famiglia="Bianchi", stato_relazione_famiglia=stato, attiva=True)
        familiare_rossi = Familiare.objects.create(
            famiglia=famiglia_rossi,
            relazione_familiare=relazione,
            nome="Maria",
            cognome="Rossi",
            attivo=True,
        )
        familiare_bianchi = Familiare.objects.create(
            famiglia=famiglia_bianchi,
            relazione_familiare=relazione,
            nome="Laura",
            cognome="Bianchi",
            attivo=True,
        )

        studente_form = StudenteStandaloneForm(
            data={
                "famiglia": famiglia_rossi.pk,
                "cognome": "Rossi",
                "nome": "Luca",
                "sesso": "",
                "data_nascita": "",
                "luogo_nascita": "",
                "nazione_nascita": "",
                "luogo_nascita_custom": "",
                "luogo_nascita_search": "",
                "nazionalita": "",
                "codice_fiscale": "",
                "indirizzo": "",
                "familiari_collegati": [str(familiare_bianchi.pk)],
                "attivo": "on",
                "note": "",
            }
        )

        self.assertTrue(studente_form.is_valid(), studente_form.errors)
        studente = studente_form.save()
        self.assertEqual(
            list(studente.relazioni_familiari.filter(attivo=True).values_list("familiare_id", flat=True)),
            [familiare_bianchi.pk],
        )
        self.assertFalse(
            StudenteFamiliare.objects.filter(
                studente=studente,
                familiare=familiare_rossi,
                attivo=True,
            ).exists()
        )

        studente_bianchi = Studente.objects.create(
            famiglia=famiglia_bianchi,
            nome="Anna",
            cognome="Bianchi",
            attivo=True,
        )
        familiare_form = FamiliareForm(
            data={
                "famiglia": famiglia_rossi.pk,
                "relazione_familiare": relazione.pk,
                "indirizzo": "",
                "nome": "Maria",
                "cognome": "Rossi",
                "telefono": "",
                "email": "",
                "codice_fiscale": "",
                "sesso": "",
                "data_nascita": "",
                "luogo_nascita": "",
                "nazione_nascita": "",
                "luogo_nascita_custom": "",
                "luogo_nascita_search": "",
                "nazionalita": "",
                "convivente": "",
                "referente_principale": "",
                "abilitato_scambio_retta": "",
                "studenti_collegati": [str(studente_bianchi.pk)],
                "attivo": "on",
                "note": "",
            },
            instance=familiare_rossi,
            enable_direct_relations_field=True,
        )

        self.assertTrue(familiare_form.is_valid(), familiare_form.errors)
        familiare_form.save()
        self.assertEqual(
            list(familiare_rossi.relazioni_studenti.filter(attivo=True).values_list("studente_id", flat=True)),
            [studente_bianchi.pk],
        )

    def test_inline_relative_form_does_not_expose_direct_relation_field(self):
        inline_form = FamiliareInlineForm(prefix="familiari-0")

        self.assertNotIn("studenti_collegati", inline_form.fields)

    def test_direct_relation_create_forms_honor_explicit_initial_links(self):
        stato = StatoRelazioneFamiglia.objects.create(stato="Interessata", ordine=1, attivo=True)
        relazione = RelazioneFamiliare.objects.create(relazione="Madre", ordine=1)
        famiglia = Famiglia.objects.create(cognome_famiglia="Rossi", stato_relazione_famiglia=stato, attiva=True)
        studente = Studente.objects.create(famiglia=famiglia, nome="Luca", cognome="Rossi", attivo=True)
        familiare = Familiare.objects.create(
            famiglia=famiglia,
            relazione_familiare=relazione,
            nome="Maria",
            cognome="Rossi",
            attivo=True,
        )

        familiare_form = FamiliareForm(
            initial={"studenti_collegati": [studente.pk]},
            enable_direct_relations_field=True,
        )
        self.assertEqual(familiare_form.initial["studenti_collegati"], [studente.pk])
        self.assertIn(studente, list(familiare_form.fields["studenti_collegati"].queryset))

        studente_form = StudenteStandaloneForm(initial={"familiari_collegati": [familiare.pk]})
        self.assertEqual(studente_form.initial["familiari_collegati"], [familiare.pk])
        self.assertIn(familiare, list(studente_form.fields["familiari_collegati"].queryset))

    def test_iscrizione_inline_prefers_current_school_year(self):
        from datetime import date
        from scuola.models import AnnoScolastico

        AnnoScolastico.objects.create(
            nome_anno_scolastico="2024/2025",
            data_inizio=date(2024, 9, 1),
            data_fine=date(2025, 8, 31),
        )
        anno_corrente = AnnoScolastico.objects.create(
            nome_anno_scolastico="2025/2026",
            data_inizio=date(2025, 9, 1),
            data_fine=date(2026, 8, 31),
        )

        form = IscrizioneStudenteInlineForm(prefix="iscrizioni-0")

        self.assertEqual(form.initial["anno_scolastico"], anno_corrente.pk)
        self.assertEqual(form.initial["data_iscrizione"], anno_corrente.data_inizio)

    def test_iscrizione_inline_defaults_to_first_active_status(self):
        StatoIscrizione.objects.create(stato_iscrizione="Secondo", ordine=2, attiva=True)
        primo_stato = StatoIscrizione.objects.create(stato_iscrizione="Primo", ordine=1, attiva=True)
        StatoIscrizione.objects.create(stato_iscrizione="Non attivo", ordine=0, attiva=False)

        form = IscrizioneStudenteInlineForm(prefix="iscrizioni-0")

        self.assertEqual(form.initial["stato_iscrizione"], primo_stato.pk)

    def test_iscrizione_inline_empty_extra_row_ignores_default_status(self):
        primo_stato = StatoIscrizione.objects.create(stato_iscrizione="Primo", ordine=1, attiva=True)
        form = IscrizioneStudenteInlineForm(
            data={
                "iscrizioni-0-stato_iscrizione": str(primo_stato.pk),
                "iscrizioni-0-data_iscrizione": "2025-09-01",
            },
            prefix="iscrizioni-0",
        )

        self.assertFalse(form.has_changed())

    def test_studenti_inline_queryset_orders_students_from_oldest_to_youngest(self):
        stato = StatoRelazioneFamiglia.objects.create(stato="Iscritta", ordine=1, attivo=True)
        famiglia = Famiglia.objects.create(
            cognome_famiglia="Verdi",
            stato_relazione_famiglia=stato,
            attiva=True,
        )
        studente_piu_giovane = Studente.objects.create(
            famiglia=famiglia,
            nome="Aurelia",
            cognome="Verdi",
            data_nascita="2022-08-28",
            attivo=True,
        )
        studente_piu_vecchio = Studente.objects.create(
            famiglia=famiglia,
            nome="Agnese",
            cognome="Verdi",
            data_nascita="2020-09-14",
            attivo=True,
        )
        studente_senza_data = Studente.objects.create(
            famiglia=famiglia,
            nome="Teresa",
            cognome="Verdi",
            attivo=True,
        )

        studenti = list(famiglia_studenti_inline_queryset(famiglia))

        self.assertEqual(
            [studente.pk for studente in studenti],
            [studente_piu_vecchio.pk, studente_piu_giovane.pk, studente_senza_data.pk],
        )

    def test_studenti_inline_queryset_annotates_current_active_enrollment(self):
        today = timezone.localdate()
        stato = StatoRelazioneFamiglia.objects.create(stato="Iscritta", ordine=1, attivo=True)
        famiglia = Famiglia.objects.create(
            cognome_famiglia="Verdi",
            stato_relazione_famiglia=stato,
            attiva=True,
        )
        studente_iscritto = Studente.objects.create(
            famiglia=famiglia,
            nome="Agnese",
            cognome="Verdi",
            data_nascita="2020-09-14",
            attivo=True,
        )
        studente_non_iscritto = Studente.objects.create(
            famiglia=famiglia,
            nome="Aurelia",
            cognome="Verdi",
            data_nascita="2022-08-28",
            attivo=True,
        )
        anno_corrente = AnnoScolastico.objects.create(
            nome_anno_scolastico=f"{today.year}/{today.year + 1}",
            data_inizio=date(today.year, 1, 1),
            data_fine=date(today.year, 12, 31),
        )
        stato_iscrizione = StatoIscrizione.objects.create(stato_iscrizione="Attiva", ordine=1, attiva=True)
        condizione = CondizioneIscrizione.objects.create(
            anno_scolastico=anno_corrente,
            nome_condizione_iscrizione="Retta standard",
            numero_mensilita_default=10,
            attiva=True,
        )
        Iscrizione.objects.create(
            studente=studente_iscritto,
            anno_scolastico=anno_corrente,
            stato_iscrizione=stato_iscrizione,
            condizione_iscrizione=condizione,
            attiva=True,
        )

        studenti = {studente.pk: studente for studente in famiglia_studenti_inline_queryset(famiglia)}

        self.assertTrue(studenti[studente_iscritto.pk].ha_iscrizione_attiva_corrente)
        self.assertFalse(studenti[studente_non_iscritto.pk].ha_iscrizione_attiva_corrente)


@skip("Legacy test basato sulla tabella anagrafica.Famiglia rimossa.")
class AnagraficaDirectRelationSyncTests(TestCase):
    def setUp(self):
        self.stato = StatoRelazioneFamiglia.objects.create(stato="Iscritta", ordine=1, attivo=True)
        self.relazione_madre = RelazioneFamiliare.objects.create(relazione="Madre", ordine=1)
        self.relazione_padre = RelazioneFamiliare.objects.create(relazione="Padre", ordine=2)
        self.famiglia = Famiglia.objects.create(
            cognome_famiglia="Rossi",
            stato_relazione_famiglia=self.stato,
            attiva=True,
        )
        self.altra_famiglia = Famiglia.objects.create(
            cognome_famiglia="Bianchi",
            stato_relazione_famiglia=self.stato,
            attiva=True,
        )
        self.studente = Studente.objects.create(
            famiglia=self.famiglia,
            nome="Luca",
            cognome="Rossi",
            attivo=True,
        )
        self.madre = Familiare.objects.create(
            famiglia=self.famiglia,
            relazione_familiare=self.relazione_madre,
            nome="Maria",
            cognome="Rossi",
            referente_principale=True,
            convivente=True,
            attivo=True,
        )
        self.padre = Familiare.objects.create(
            famiglia=self.famiglia,
            relazione_familiare=self.relazione_padre,
            nome="Paolo",
            cognome="Rossi",
            referente_principale=False,
            convivente=False,
            attivo=False,
        )

    def test_sync_all_student_family_relations_creates_and_updates_legacy_family_pairs(self):
        StudenteFamiliare.objects.create(
            studente=self.studente,
            familiare=self.padre,
            relazione_familiare=self.relazione_madre,
            referente_principale=True,
            convivente=True,
            attivo=True,
        )
        familiare_esterno = Familiare.objects.create(
            famiglia=self.altra_famiglia,
            relazione_familiare=self.relazione_madre,
            nome="Laura",
            cognome="Bianchi",
            attivo=True,
        )
        StudenteFamiliare.objects.create(studente=self.studente, familiare=familiare_esterno, attivo=True)

        stats = sync_all_student_family_relations()

        self.assertEqual(stats["created"], 1)
        self.assertEqual(stats["updated"], 1)
        self.assertEqual(stats["unchanged"], 0)
        madre_relation = StudenteFamiliare.objects.get(studente=self.studente, familiare=self.madre)
        self.assertEqual(madre_relation.relazione_familiare, self.relazione_madre)
        self.assertTrue(madre_relation.referente_principale)
        self.assertTrue(madre_relation.convivente)
        self.assertTrue(madre_relation.attivo)
        padre_relation = StudenteFamiliare.objects.get(studente=self.studente, familiare=self.padre)
        self.assertEqual(padre_relation.relazione_familiare, self.relazione_padre)
        self.assertFalse(padre_relation.referente_principale)
        self.assertFalse(padre_relation.convivente)
        self.assertFalse(padre_relation.attivo)
        self.assertTrue(
            StudenteFamiliare.objects.filter(
                studente=self.studente,
                familiare=familiare_esterno,
                attivo=True,
            ).exists()
        )

    def test_sync_all_student_family_relations_dry_run_does_not_persist(self):
        stats = sync_all_student_family_relations(dry_run=True)

        self.assertEqual(stats["created"], 2)
        self.assertFalse(StudenteFamiliare.objects.filter(studente=self.studente).exists())

    def test_sync_all_student_family_relations_missing_only_keeps_existing_values(self):
        relation = StudenteFamiliare.objects.create(
            studente=self.studente,
            familiare=self.madre,
            relazione_familiare=self.relazione_padre,
            referente_principale=False,
            convivente=False,
            attivo=False,
        )

        stats = sync_all_student_family_relations(update_existing=False)

        self.assertEqual(stats["created"], 1)
        self.assertEqual(stats["unchanged"], 1)
        relation.refresh_from_db()
        self.assertEqual(relation.relazione_familiare, self.relazione_padre)
        self.assertFalse(relation.referente_principale)
        self.assertFalse(relation.convivente)
        self.assertFalse(relation.attivo)

    def test_relation_sync_management_command_dry_run(self):
        output = StringIO()

        call_command("riallinea_relazioni_anagrafiche", "--dry-run", stdout=output)

        self.assertIn("dry-run", output.getvalue())
        self.assertFalse(StudenteFamiliare.objects.filter(studente=self.studente).exists())


@skip("Legacy test basato sulla tabella anagrafica.Famiglia rimossa.")
class FamiliareScambioRettaInlineTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser(
            username="familiare-scambio@example.com",
            email="familiare-scambio@example.com",
            password="Password123!",
        )
        self.client.force_login(self.user)
        self.regione = Regione.objects.create(nome="Emilia-Romagna", ordine=1, attiva=True)
        self.provincia = Provincia.objects.create(sigla="BO", nome="Bologna", regione=self.regione, ordine=1, attiva=True)
        self.citta = Citta.objects.create(nome="Bologna", provincia=self.provincia, codice_catastale="A944", ordine=1, attiva=True)
        self.indirizzo = Indirizzo.objects.create(
            via="Via Roma",
            numero_civico="1",
            citta=self.citta,
            provincia=self.provincia,
            regione=self.regione,
        )
        self.stato = StatoRelazioneFamiglia.objects.create(stato="Iscritta", ordine=1, attivo=True)
        self.famiglia = Famiglia.objects.create(
            cognome_famiglia="Rossi",
            stato_relazione_famiglia=self.stato,
            indirizzo_principale=self.indirizzo,
            attiva=True,
        )
        self.relazione = RelazioneFamiliare.objects.create(relazione="Madre", ordine=1)
        self.familiare = Familiare.objects.create(
            famiglia=self.famiglia,
            relazione_familiare=self.relazione,
            nome="Ada",
            cognome="Rossi",
            sesso="F",
            abilitato_scambio_retta=True,
            attivo=True,
        )
        self.anno = AnnoScolastico.objects.create(
            nome_anno_scolastico="2025/2026",
            data_inizio=date(2025, 9, 1),
            data_fine=date(2026, 8, 31),
            attivo=True,
        )
        self.tariffa = TariffaScambioRetta.objects.create(
            valore_orario=Decimal("10.00"),
            definizione="Base",
        )
        PrestazioneScambioRetta.objects.create(
            familiare=self.familiare,
            famiglia=self.famiglia,
            anno_scolastico=self.anno,
            data=date(2026, 4, 20),
            descrizione="Supporto mensa",
            ore_lavorate=Decimal("2.00"),
            tariffa_scambio_retta=self.tariffa,
        )

    def test_scambio_retta_view_switch_get_keeps_familiare_enabled(self):
        url = reverse("modifica_familiare", kwargs={"pk": self.familiare.pk})

        for view_name in ["week", "month"]:
            response = self.client.get(
                url,
                {
                    "scambio_year": self.anno.pk,
                    "scambio_view": view_name,
                },
            )

            self.assertEqual(response.status_code, 200)
            self.familiare.refresh_from_db()
            self.assertTrue(self.familiare.abilitato_scambio_retta)
            self.assertContains(response, "Scambio retta")
            self.assertContains(response, 'id="scambio-retta-inline"')
            self.assertContains(response, "family-scambio-card")
            self.assertContains(response, "scambio-summary-card")
            self.assertContains(response, "scambio-primary-add")
            self.assertContains(response, "family-dashed-add scambio-year-add")
            self.assertContains(response, 'data-window-popup="1"')
            self.assertContains(response, "arboris-prestazione-scambio-popup")
            self.assertContains(response, "popup=1")
            self.assertContains(response, f"familiare={self.familiare.pk}")
            self.assertContains(response, "Aggiungi prestazione")
            self.assertContains(response, "Vista settimana")
            self.assertContains(response, "Vista mensile")

    def test_create_prestazione_scambio_retta_popup_renders_and_closes_after_save(self):
        url = reverse("crea_prestazione_scambio_retta")
        return_to = reverse("modifica_familiare", kwargs={"pk": self.familiare.pk})

        response = self.client.get(
            url,
            {
                "popup": "1",
                "familiare": self.familiare.pk,
                "return_to": return_to,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'class="popup-page"')
        self.assertContains(response, 'name="popup" value="1"')

        response = self.client.post(
            url,
            {
                "popup": "1",
                "familiare": self.familiare.pk,
                "data": "2026-04-21",
                "ora_ingresso": "",
                "ora_uscita": "",
                "ore_lavorate": "1.50",
                "tariffa_scambio_retta": self.tariffa.pk,
                "descrizione": "Supporto ingresso",
                "note": "",
                "return_to": return_to,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "popup/popup_close.html")
        self.assertContains(response, "window.close()")
        self.assertTrue(
            PrestazioneScambioRetta.objects.filter(
                familiare=self.familiare,
                data=date(2026, 4, 21),
                descrizione="Supporto ingresso",
            ).exists()
        )

    def test_view_mode_post_cannot_disable_scambio_retta(self):
        url = reverse("modifica_familiare", kwargs={"pk": self.familiare.pk})

        response = self.client.post(
            url,
            {
                "_edit_scope": "view",
                "famiglia": self.famiglia.pk,
                "relazione_familiare": self.relazione.pk,
                "nome": self.familiare.nome,
                "cognome": self.familiare.cognome,
            },
        )

        self.assertEqual(response.status_code, 302)
        self.familiare.refresh_from_db()
        self.assertTrue(self.familiare.abilitato_scambio_retta)


@skip("Legacy test basato sulla tabella anagrafica.Famiglia rimossa.")
class FamiliareDetailViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser(
            username="familiare-detail@example.com",
            email="familiare-detail@example.com",
            password="Password123!",
        )
        self.client.force_login(self.user)
        self.regione = Regione.objects.create(nome="Emilia-Romagna", ordine=1, attiva=True)
        self.provincia = Provincia.objects.create(sigla="BO", nome="Bologna", regione=self.regione, ordine=1, attiva=True)
        self.citta = Citta.objects.create(nome="Bologna", provincia=self.provincia, codice_catastale="A944", ordine=1, attiva=True)
        self.indirizzo = Indirizzo.objects.create(
            via="Via Roma",
            numero_civico="1",
            citta=self.citta,
            provincia=self.provincia,
            regione=self.regione,
        )
        self.stato = StatoRelazioneFamiglia.objects.create(stato="Iscritta", ordine=1, attivo=True)
        self.famiglia = Famiglia.objects.create(
            cognome_famiglia="Rossi",
            stato_relazione_famiglia=self.stato,
            indirizzo_principale=self.indirizzo,
            attiva=True,
        )
        self.relazione = RelazioneFamiliare.objects.create(relazione="Madre", ordine=1)
        self.nazione = Nazione.objects.create(
            nome="Italia",
            nome_nazionalita="Italiana",
            codice_iso2="IT",
            codice_iso3="ITA",
            codice_belfiore="Z000",
            ordine=1,
            attiva=True,
        )
        self.familiare = Familiare.objects.create(
            famiglia=self.famiglia,
            relazione_familiare=self.relazione,
            nome="Ada",
            cognome="Rossi",
            sesso="F",
            nazionalita=self.nazione,
            referente_principale=True,
            attivo=True,
        )

    def test_modifica_familiare_renders_view_mode_and_hidden_blank_document_row(self):
        response = self.client.get(reverse("modifica_familiare", kwargs={"pk": self.familiare.pk}))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="familiare-detail-form" class="detail-form is-view-mode"')
        self.assertContains(response, 'name="documenti-0-id"')
        self.assertContains(response, 'class="inline-form-row inline-empty-row is-hidden"')

    def test_crea_familiare_cancel_actions_use_wrapped_application_back(self):
        response = self.client.get(reverse("crea_familiare"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="familiare-detail-form" class="detail-form is-create-mode is-edit-mode"')
        self.assertContains(response, 'class="btn btn-intent-danger btn-icon-text js-page-back-btn"')
        self.assertContains(response, 'id="sticky-cancel-edit-familiare-btn"')
        self.assertContains(response, f'data-fallback-url="{reverse("lista_familiari")}"')
        self.assertContains(response, '<span class="btn-label">Annulla</span>')
        self.assertContains(response, 'formEl.classList.contains("is-create-mode")')
        self.assertContains(response, "ArborisAppNavigation.resolveBackUrl")

    def test_modifica_familiare_renders_family_style_card_tabs(self):
        padre = RelazioneFamiliare.objects.create(relazione="Padre", ordine=2)
        altro_familiare = Familiare.objects.create(
            famiglia=self.famiglia,
            relazione_familiare=padre,
            nome="Mario",
            cognome="Rossi",
            sesso="M",
            referente_principale=True,
            attivo=True,
        )
        studente = Studente.objects.create(
            famiglia=self.famiglia,
            nome="Luca",
            cognome="Rossi",
            sesso="M",
            attivo=True,
        )
        tipo_documento = TipoDocumento.objects.create(tipo_documento="Documento identita", ordine=1, attivo=True)
        Documento.objects.create(familiare=self.familiare, tipo_documento=tipo_documento)

        response = self.client.get(reverse("modifica_familiare", kwargs={"pk": self.familiare.pk}))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="tab-studenti"')
        self.assertContains(response, 'id="tab-parenti"')
        self.assertContains(response, 'id="tab-documenti"')
        self.assertContains(response, f'data-student-id="{studente.pk}"')
        self.assertContains(response, f'data-relative-id="{altro_familiare.pk}"')
        self.assertContains(response, 'data-document-card')
        self.assertContains(response, "Figli e Figlie")
        self.assertContains(response, 'name="direct_studenti_collegati"')
        self.assertContains(response, 'data-student-card-action="edit"')
        self.assertContains(response, 'data-relative-card-action="edit"')
        self.assertContains(response, 'data-document-card-action="edit"')
        self.assertNotContains(response, "Nazionalit&agrave; non indicata")
        self.assertContains(response, "Nazionalit&agrave;: Italiana")
        self.assertContains(response, 'class="family-status-pill is-muted">Referente</span>')
        self.assertContains(response, "family-relation-pill")
        self.assertContains(response, "is-male")
        self.assertNotContains(response, 'class="family-person-chip">Referente</span>')
        self.assertContains(response, 'class="family-related-list mode-view-only person-student-card-list"')
        self.assertNotIn("famiglia", response.context["form"].fields)

    def test_modifica_familiare_uses_direct_student_relations_with_inline_editor(self):
        famiglia_studente = Famiglia.objects.create(
            cognome_famiglia="Bianchi",
            stato_relazione_famiglia=self.stato,
            attiva=True,
        )
        studente = Studente.objects.create(
            famiglia=famiglia_studente,
            nome="Lia",
            cognome="Bianchi",
            attivo=True,
        )
        StudenteFamiliare.objects.create(
            studente=studente,
            familiare=self.familiare,
            relazione_familiare=self.relazione,
            attivo=True,
        )

        response = self.client.get(reverse("modifica_familiare", kwargs={"pk": self.familiare.pk}))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Figli e Figlie")
        self.assertContains(response, "Lia Bianchi")
        self.assertContains(response, "Madre")
        self.assertContains(response, "Vedi profilo")
        self.assertNotContains(response, f'href="{reverse("modifica_studente", kwargs={"pk": studente.pk})}?edit=1"')
        self.assertNotContains(response, f'href="{reverse("crea_studente")}?familiare={self.familiare.pk}"')
        self.assertContains(response, "Aggiungi figlio o figlia")
        self.assertContains(response, 'name="direct_studenti_collegati"')
        self.assertContains(response, 'id="enable-inline-edit-familiare-btn"')
        self.assertContains(response, "Modifica Figli e Figlie")
        self.assertContains(response, 'data-student-card-action="edit"')
        self.assertContains(response, 'data-student-card-action="add"')
        self.assertContains(response, 'id="studenti-table"')

    def test_modifica_familiare_inline_studenti_updates_direct_relations(self):
        famiglia_alt = Famiglia.objects.create(
            cognome_famiglia="Bianchi",
            stato_relazione_famiglia=self.stato,
            attiva=True,
        )
        studente_attuale = Studente.objects.create(
            famiglia=self.famiglia,
            nome="Luca",
            cognome="Rossi",
            attivo=True,
        )
        studente_nuovo = Studente.objects.create(
            famiglia=famiglia_alt,
            nome="Lia",
            cognome="Bianchi",
            attivo=True,
        )
        StudenteFamiliare.objects.create(
            studente=studente_attuale,
            familiare=self.familiare,
            relazione_familiare=self.relazione,
            attivo=True,
        )

        response = self.client.post(
            reverse("modifica_familiare", kwargs={"pk": self.familiare.pk}),
            {
                "_edit_scope": "inline",
                "_inline_target": "studenti",
                "_continue": "1",
                "direct_studenti_collegati": [str(studente_nuovo.pk)],
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertFalse(
            StudenteFamiliare.objects.get(studente=studente_attuale, familiare=self.familiare).attivo
        )
        self.assertTrue(
            StudenteFamiliare.objects.get(studente=studente_nuovo, familiare=self.familiare).attivo
        )

    def test_modifica_familiare_full_save_redirects_to_detail_view_with_blank_inline_rows(self):
        response = self.client.post(
            reverse("modifica_familiare", kwargs={"pk": self.familiare.pk}),
            {
                "_edit_scope": "full",
                "famiglia": self.famiglia.pk,
                "relazione_familiare": self.relazione.pk,
                "indirizzo": "",
                "nome": "Ada",
                "cognome": "Rossi",
                "telefono": "",
                "email": "",
                "codice_fiscale": "",
                "sesso": "F",
                "data_nascita": "",
                "luogo_nascita": "",
                "luogo_nascita_search": "",
                "convivente": "",
                "referente_principale": "",
                "abilitato_scambio_retta": "",
                "attivo": "on",
                "note": "",
                "studenti-TOTAL_FORMS": "1",
                "studenti-INITIAL_FORMS": "0",
                "studenti-MIN_NUM_FORMS": "0",
                "studenti-MAX_NUM_FORMS": "1000",
                "studenti-0-id": "",
                "studenti-0-cognome": "",
                "studenti-0-nome": "",
                "studenti-0-sesso": "",
                "studenti-0-data_nascita": "",
                "studenti-0-luogo_nascita": "",
                "studenti-0-luogo_nascita_search": "",
                "studenti-0-codice_fiscale": "",
                "studenti-0-indirizzo": "",
                "studenti-0-attivo": "on",
                "documenti-TOTAL_FORMS": "1",
                "documenti-INITIAL_FORMS": "0",
                "documenti-MIN_NUM_FORMS": "0",
                "documenti-MAX_NUM_FORMS": "1000",
                "documenti-0-id": "",
                "documenti-0-tipo_documento": "",
                "documenti-0-descrizione": "",
                "documenti-0-file": "",
                "documenti-0-scadenza": "",
                "documenti-0-visibile": "on",
                "documenti-0-note": "",
            },
        )

        self.assertRedirects(
            response,
            reverse("modifica_familiare", kwargs={"pk": self.familiare.pk}),
            fetch_redirect_response=False,
        )

    def test_modifica_familiare_creates_linked_work_profile_without_duplicate_person(self):
        classe = Classe.objects.create(nome_classe="Prima", sezione_classe="A", ordine_classe=1, attiva=True)

        response = self.client.post(
            reverse("modifica_familiare", kwargs={"pk": self.familiare.pk}),
            {
                "_edit_scope": "full",
                "famiglia": self.famiglia.pk,
                "relazione_familiare": self.relazione.pk,
                "indirizzo": "",
                "nome": "Ada",
                "cognome": "Rossi",
                "telefono": "3331234567",
                "email": "ada.rossi@example.com",
                "codice_fiscale": "",
                "sesso": "F",
                "data_nascita": "1980-01-01",
                "luogo_nascita": self.citta.pk,
                "luogo_nascita_search": "Bologna",
                "nazione_nascita": "",
                "nazionalita": "",
                "convivente": "",
                "referente_principale": "on",
                "abilitato_scambio_retta": "",
                "profilo_dipendente_attivo": "",
                "profilo_educatore_attivo": "on",
                "classe_principale_educatore": classe.pk,
                "materia_educatore": "Inglese",
                "profilo_mansione": "Coordinamento didattico",
                "profilo_iban": "IT60 X054 2811 1010 0000 0123 456",
                "profilo_stato": StatoDipendente.ATTIVO,
                "attivo": "on",
                "note": "",
            },
        )

        self.assertRedirects(
            response,
            reverse("modifica_familiare", kwargs={"pk": self.familiare.pk}),
            fetch_redirect_response=False,
        )
        profilo = Dipendente.objects.get(familiare_collegato=self.familiare)
        self.assertEqual(profilo.ruolo_anagrafico, RuoloAnagraficoDipendente.EDUCATORE)
        self.assertEqual(profilo.classe_principale, classe)
        self.assertEqual(profilo.materia, "Inglese")
        self.assertEqual(profilo.stato, StatoDipendente.ATTIVO)
        self.assertEqual(profilo.mansione, "Coordinamento didattico")
        self.assertEqual(profilo.iban, "IT60X0542811101000000123456")
        self.assertEqual(profilo.nome, "Ada")
        self.assertEqual(profilo.cognome, "Rossi")
        self.assertEqual(profilo.email, "ada.rossi@example.com")

        detail_response = self.client.get(reverse("modifica_familiare", kwargs={"pk": self.familiare.pk}))
        self.assertContains(detail_response, 'id="profilo-lavorativo-card"')
        self.assertContains(detail_response, "Profilo lavorativo")
        self.assertContains(detail_response, "Educatore")
        self.assertContains(detail_response, "Prima A")
        self.assertContains(detail_response, "Inglese")

    def test_modifica_familiare_accetta_gruppo_classe_come_classe_principale_educatore(self):
        anno = AnnoScolastico.objects.create(
            nome_anno_scolastico="2025/2026 - familiare gruppo classe test",
            data_inizio=date(2025, 9, 1),
            data_fine=date(2026, 6, 30),
        )
        classe_prima = Classe.objects.create(nome_classe="Prima", sezione_classe="A", ordine_classe=1, attiva=True)
        classe_seconda = Classe.objects.create(nome_classe="Seconda", sezione_classe="A", ordine_classe=2, attiva=True)
        gruppo = GruppoClasse.objects.create(nome_gruppo_classe="Prima e Seconda", anno_scolastico=anno, attivo=True)
        gruppo.classi.set([classe_prima, classe_seconda])

        response = self.client.post(
            reverse("modifica_familiare", kwargs={"pk": self.familiare.pk}),
            {
                "_edit_scope": "full",
                "famiglia": self.famiglia.pk,
                "relazione_familiare": self.relazione.pk,
                "indirizzo": "",
                "nome": "Ada",
                "cognome": "Rossi",
                "telefono": "3331234567",
                "email": "ada.rossi@example.com",
                "codice_fiscale": "",
                "sesso": "F",
                "data_nascita": "1980-01-01",
                "luogo_nascita": self.citta.pk,
                "luogo_nascita_search": "Bologna",
                "nazione_nascita": "",
                "nazionalita": "",
                "convivente": "",
                "referente_principale": "on",
                "abilitato_scambio_retta": "",
                "profilo_dipendente_attivo": "",
                "profilo_educatore_attivo": "on",
                "classe_principale_educatore": f"gruppo:{gruppo.pk}",
                "attivo": "on",
                "note": "",
            },
        )

        self.assertRedirects(
            response,
            reverse("modifica_familiare", kwargs={"pk": self.familiare.pk}),
            fetch_redirect_response=False,
        )
        profilo = Dipendente.objects.get(familiare_collegato=self.familiare)
        self.assertEqual(profilo.ruolo_anagrafico, RuoloAnagraficoDipendente.EDUCATORE)
        self.assertIsNone(profilo.classe_principale)
        self.assertEqual(profilo.gruppo_classe_principale, gruppo)

        detail_response = self.client.get(reverse("modifica_familiare", kwargs={"pk": self.familiare.pk}))
        self.assertContains(detail_response, "Prima e Seconda")


@skip("Legacy test basato sulla tabella anagrafica.Famiglia rimossa.")
class StudenteListTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser(
            username="lista-studenti@example.com",
            email="lista-studenti@example.com",
            password="Password123!",
        )
        self.client.force_login(self.user)
        self.regione = Regione.objects.create(nome="Emilia-Romagna", ordine=1, attiva=True)
        self.provincia = Provincia.objects.create(sigla="BO", nome="Bologna", regione=self.regione, ordine=1, attiva=True)
        self.citta = Citta.objects.create(nome="Crevalcore", provincia=self.provincia, codice_catastale="D166", ordine=1, attiva=True)
        self.cap = CAP.objects.create(codice="40014", citta=self.citta, ordine=1, attivo=True)
        self.stato = StatoRelazioneFamiglia.objects.create(stato="Iscritta", ordine=1, attivo=True)

    def test_lista_studenti_shows_effective_address_instead_of_inheritance_label(self):
        indirizzo_famiglia = Indirizzo.objects.create(
            via="Via Don Lorenzo Milani",
            numero_civico="70",
            citta=self.citta,
            cap_scelto=self.cap,
        )
        indirizzo_studente = Indirizzo.objects.create(
            via="Via Specifica",
            numero_civico="12",
            citta=self.citta,
            cap_scelto=self.cap,
        )
        famiglia = Famiglia.objects.create(
            cognome_famiglia="Bersani",
            stato_relazione_famiglia=self.stato,
            indirizzo_principale=indirizzo_famiglia,
            attiva=True,
        )
        Studente.objects.create(famiglia=famiglia, cognome="Bersani", nome="Agnese", attivo=True)
        Studente.objects.create(famiglia=famiglia, cognome="Bersani", nome="Teresa", indirizzo=indirizzo_studente, attivo=True)

        response = self.client.get(reverse("lista_studenti"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Via Don Lorenzo Milani 70 - Crevalcore (BO) - 40014")
        self.assertContains(response, "Via Specifica 12 - Crevalcore (BO) - 40014")
        self.assertNotContains(response, "Eredita famiglia")

    def test_lista_studenti_shows_current_enrollment_status_badges(self):
        today = timezone.localdate()
        anno_corrente = AnnoScolastico.objects.create(
            nome_anno_scolastico=f"{today.year}/{today.year + 1}",
            data_inizio=date(today.year, 1, 1),
            data_fine=date(today.year, 12, 31),
        )
        stato_iscrizione = StatoIscrizione.objects.create(stato_iscrizione="Attiva", ordine=1, attiva=True)
        condizione = CondizioneIscrizione.objects.create(
            anno_scolastico=anno_corrente,
            nome_condizione_iscrizione="Retta standard",
            numero_mensilita_default=10,
            attiva=True,
        )
        famiglia = Famiglia.objects.create(
            cognome_famiglia="Bersani",
            stato_relazione_famiglia=self.stato,
            attiva=True,
        )
        studente_iscritto = Studente.objects.create(famiglia=famiglia, cognome="Bersani", nome="Agnese", attivo=True)
        Studente.objects.create(famiglia=famiglia, cognome="Bersani", nome="Teresa", attivo=True)
        Iscrizione.objects.create(
            studente=studente_iscritto,
            anno_scolastico=anno_corrente,
            stato_iscrizione=stato_iscrizione,
            condizione_iscrizione=condizione,
            attiva=True,
        )

        response = self.client.get(reverse("lista_studenti"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Iscritto")
        self.assertContains(response, "Non iscritto")
        self.assertContains(response, "status-chip-success student-enrollment-status")
        self.assertContains(response, "status-chip-danger student-enrollment-status")


@skip("Legacy test basato sulla tabella anagrafica.Famiglia rimossa.")
class RicercheAnagraficaTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser(
            username="ricerche-anagrafica@example.com",
            email="ricerche-anagrafica@example.com",
            password="Password123!",
        )
        self.client.force_login(self.user)
        self.stato = StatoRelazioneFamiglia.objects.create(stato="Iscritta", ordine=1, attivo=True)
        self.relazione = RelazioneFamiliare.objects.create(relazione="Genitore", ordine=1)
        self.famiglia = Famiglia.objects.create(
            cognome_famiglia="Bianchi",
            stato_relazione_famiglia=self.stato,
            attiva=True,
        )
        self.tipo_documento = TipoDocumento.objects.create(tipo_documento="Carta identita", ordine=1, attivo=True)
        self.familiare_con_documento = Familiare.objects.create(
            famiglia=self.famiglia,
            relazione_familiare=self.relazione,
            nome="Completo",
            cognome="Bianchi",
        )
        self.familiare_senza_documento = Familiare.objects.create(
            famiglia=self.famiglia,
            relazione_familiare=self.relazione,
            nome="Mancante",
            cognome="Bianchi",
        )

    def test_ricerca_familiari_senza_tipo_documento(self):
        with TemporaryDirectory() as tmpdir:
            with override_settings(MEDIA_ROOT=tmpdir):
                Documento.objects.create(
                    familiare=self.familiare_con_documento,
                    tipo_documento=self.tipo_documento,
                    file=SimpleUploadedFile("documento.pdf", b"test", content_type="application/pdf"),
                )

                response = self.client.get(
                    reverse("ricerche_anagrafica"),
                    {
                        "query": "documenti_mancanti",
                        "target": "familiari",
                        "tipo_documento": self.tipo_documento.pk,
                    },
                )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Familiari senza Carta identita")
        self.assertContains(response, "Bianchi Mancante")
        self.assertNotContains(response, "Bianchi Completo")

    def test_ricerca_famiglie_senza_tipo_documento_uses_logical_family_url(self):
        studente = Studente.objects.create(nome="Sara", cognome="Verdi", attivo=True)
        familiare = Familiare.objects.create(
            relazione_familiare=self.relazione,
            nome="Giulia",
            cognome="Verdi",
            attivo=True,
        )
        StudenteFamiliare.objects.create(
            studente=studente,
            familiare=familiare,
            relazione_familiare=self.relazione,
            attivo=True,
        )

        response = self.client.get(
            reverse("ricerche_anagrafica"),
            {
                "query": "documenti_mancanti",
                "target": "famiglie",
                "tipo_documento": self.tipo_documento.pk,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Famiglie senza Carta identita")
        self.assertContains(response, "Verdi")
        self.assertContains(
            response,
            reverse("modifica_famiglia_logica", kwargs={"key": f"s-{studente.pk}"}),
        )


@skip("Legacy test basato sulla tabella anagrafica.Famiglia rimossa.")
class DocumentoStorageTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser(
            username="documenti@example.com",
            email="documenti@example.com",
            password="Password123!",
        )
        self.regione = Regione.objects.create(nome="Lazio", ordine=1, attiva=True)
        self.provincia = Provincia.objects.create(sigla="RM", nome="Roma", regione=self.regione, ordine=1, attiva=True)
        self.citta = Citta.objects.create(nome="Roma", provincia=self.provincia, codice_catastale="H501", ordine=1, attiva=True)
        self.stato = StatoRelazioneFamiglia.objects.create(stato="Iscritta", ordine=1, attivo=True)
        self.famiglia = Famiglia.objects.create(cognome_famiglia="Neri", stato_relazione_famiglia=self.stato, attiva=True)
        self.relazione = RelazioneFamiliare.objects.create(relazione="Madre", ordine=1)
        self.familiare = Familiare.objects.create(
            famiglia=self.famiglia,
            relazione_familiare=self.relazione,
            nome="Anna",
            cognome="Neri",
            attivo=True,
        )
        self.studente = Studente.objects.create(
            famiglia=self.famiglia,
            nome="Luca",
            cognome="Neri",
            attivo=True,
        )
        self.tipo_documento = TipoDocumento.objects.create(tipo_documento="Carta identita", ordine=1, attivo=True)
        today = timezone.localdate()
        self.anno_scolastico = AnnoScolastico.objects.create(
            nome_anno_scolastico=f"{today.year}/{today.year + 1}",
            data_inizio=date(today.year, 1, 1),
            data_fine=date(today.year, 12, 31),
            attivo=True,
        )

    def test_uploaded_documents_are_partitioned_by_owner_type(self):
        with TemporaryDirectory() as tmpdir:
            with override_settings(MEDIA_ROOT=tmpdir):
                documento_famiglia = Documento.objects.create(
                    famiglia=self.famiglia,
                    tipo_documento=self.tipo_documento,
                    file=SimpleUploadedFile("famiglia.pdf", b"famiglia", content_type="application/pdf"),
                )
                documento_familiare = Documento.objects.create(
                    familiare=self.familiare,
                    tipo_documento=self.tipo_documento,
                    file=SimpleUploadedFile("familiare.pdf", b"familiare", content_type="application/pdf"),
                )
                documento_studente = Documento.objects.create(
                    studente=self.studente,
                    tipo_documento=self.tipo_documento,
                    file=SimpleUploadedFile("studente.pdf", b"studente", content_type="application/pdf"),
                )

                expected_prefix = f"{self.anno_scolastico.nome_anno_scolastico.replace('/', '-')}/documenti"
                self.assertTrue(documento_famiglia.file.name.startswith(f"{expected_prefix}/famiglie/"))
                self.assertTrue(documento_familiare.file.name.startswith(f"{expected_prefix}/familiari/"))
                self.assertTrue(documento_studente.file.name.startswith(f"{expected_prefix}/studenti/"))

    def test_document_download_view_streams_uploaded_file(self):
        with TemporaryDirectory() as tmpdir:
            with override_settings(MEDIA_ROOT=tmpdir):
                self.client.force_login(self.user)
                documento = Documento.objects.create(
                    famiglia=self.famiglia,
                    tipo_documento=self.tipo_documento,
                    file=SimpleUploadedFile("documento-test.pdf", b"contenuto-pdf", content_type="application/pdf"),
                )

                response = self.client.get(reverse("apri_documento", kwargs={"pk": documento.pk}))

                self.assertEqual(response.status_code, 200)
                self.assertIn('filename="documento-test.pdf"', response["Content-Disposition"])
                self.assertEqual(b"".join(response.streaming_content), b"contenuto-pdf")

    def test_deleting_document_removes_file_from_storage(self):
        with TemporaryDirectory() as tmpdir:
            with override_settings(MEDIA_ROOT=tmpdir):
                documento = Documento.objects.create(
                    famiglia=self.famiglia,
                    tipo_documento=self.tipo_documento,
                    file=SimpleUploadedFile("documento-delete.pdf", b"da-eliminare", content_type="application/pdf"),
                )
                file_path = Path(tmpdir) / documento.file.name
                self.assertTrue(file_path.exists())

                with self.captureOnCommitCallbacks(execute=True):
                    documento.delete()

                self.assertFalse(file_path.exists())

    def test_family_document_formset_honors_delete_flag_for_existing_rows(self):
        documento = Documento.objects.create(
            famiglia=self.famiglia,
            tipo_documento=self.tipo_documento,
            descrizione="Documento da eliminare",
        )

        formset = DocumentoFamigliaFormSet(
            data={
                "documenti-TOTAL_FORMS": "1",
                "documenti-INITIAL_FORMS": "1",
                "documenti-MIN_NUM_FORMS": "0",
                "documenti-MAX_NUM_FORMS": "1000",
                "documenti-0-id": str(documento.pk),
                "documenti-0-tipo_documento": str(self.tipo_documento.pk),
                "documenti-0-descrizione": "Documento da eliminare",
                "documenti-0-scadenza": "",
                "documenti-0-note": "",
                "documenti-0-visibile": "on",
                "documenti-0-DELETE": "on",
            },
            files={},
            instance=self.famiglia,
            prefix="documenti",
        )

        self.assertTrue(formset.is_valid(), formset.errors)
        self.assertEqual(len(formset.deleted_forms), 1)

    def test_popup_delete_document_removes_record_and_storage_file(self):
        with TemporaryDirectory() as tmpdir:
            with override_settings(MEDIA_ROOT=tmpdir):
                self.client.force_login(self.user)
                documento = Documento.objects.create(
                    famiglia=self.famiglia,
                    tipo_documento=self.tipo_documento,
                    descrizione="Documento popup",
                    file=SimpleUploadedFile("documento-popup.pdf", b"contenuto", content_type="application/pdf"),
                )
                file_path = Path(tmpdir) / documento.file.name
                self.assertTrue(file_path.exists())

                response_get = self.client.get(
                    reverse("elimina_documento", kwargs={"pk": documento.pk}),
                    {"popup": "1"},
                )
                self.assertEqual(response_get.status_code, 200)
                self.assertContains(response_get, "Conferma eliminazione")

                with self.captureOnCommitCallbacks(execute=True):
                    response_post = self.client.post(
                        reverse("elimina_documento", kwargs={"pk": documento.pk}),
                        {"popup": "1"},
                    )

                self.assertEqual(response_post.status_code, 200)
                self.assertContains(response_post, "window.close()")
                self.assertFalse(Documento.objects.filter(pk=documento.pk).exists())
                self.assertFalse(file_path.exists())


@skip("Legacy test basato sulla tabella anagrafica.Famiglia rimossa.")
class DocumentoInlineFormTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser(
            username="documenti-inline@example.com",
            email="documenti-inline@example.com",
            password="Password123!",
        )
        self.regione = Regione.objects.create(nome="Lazio", ordine=1, attiva=True)
        self.provincia = Provincia.objects.create(sigla="RM", nome="Roma", regione=self.regione, ordine=1, attiva=True)
        self.citta = Citta.objects.create(nome="Roma", provincia=self.provincia, codice_catastale="H501", ordine=1, attiva=True)
        self.stato = StatoRelazioneFamiglia.objects.create(stato="Iscritta", ordine=1, attivo=True)
        self.famiglia = Famiglia.objects.create(cognome_famiglia="Neri", stato_relazione_famiglia=self.stato, attiva=True)
        self.studente = Studente.objects.create(famiglia=self.famiglia, nome="Luca", cognome="Neri", attivo=True)
        self.tipo_documento = TipoDocumento.objects.create(tipo_documento="Carta identita", ordine=1, attivo=True)

    def test_documento_studente_form_defaults_to_first_tipo_documento(self):
        secondo = TipoDocumento.objects.create(tipo_documento="Secondo", ordine=2, attivo=True)
        primo = self.tipo_documento

        form = DocumentoStudenteForm(prefix="documenti-0")

        self.assertIsNone(form.fields["tipo_documento"].empty_label)
        self.assertEqual(form.initial["tipo_documento"], primo.pk)
        self.assertEqual(list(form.fields["tipo_documento"].queryset), [primo, secondo])

    def test_documento_studente_formset_requires_tipo_documento_with_clear_message(self):
        formset = DocumentoStudenteFormSet(
            data={
                "documenti-TOTAL_FORMS": "1",
                "documenti-INITIAL_FORMS": "0",
                "documenti-MIN_NUM_FORMS": "0",
                "documenti-MAX_NUM_FORMS": "1000",
                "documenti-0-tipo_documento": "",
                "documenti-0-descrizione": "Documento senza tipo",
                "documenti-0-scadenza": "",
                "documenti-0-note": "",
                "documenti-0-visibile": "on",
            },
            files={
                "documenti-0-file": SimpleUploadedFile(
                    "documento-test.pdf",
                    b"contenuto-pdf",
                    content_type="application/pdf",
                )
            },
            instance=self.studente,
            prefix="documenti",
        )

        self.assertFalse(formset.is_valid())
        self.assertIn("Seleziona un tipo documento.", formset.forms[0].errors["tipo_documento"])

    def test_documento_famiglia_formset_ignores_blank_extra_row_with_default_tipo(self):
        formset = DocumentoFamigliaFormSet(
            data={
                "documenti-TOTAL_FORMS": "1",
                "documenti-INITIAL_FORMS": "0",
                "documenti-MIN_NUM_FORMS": "0",
                "documenti-MAX_NUM_FORMS": "1000",
                "documenti-0-id": "",
                "documenti-0-tipo_documento": str(self.tipo_documento.pk),
                "documenti-0-descrizione": "",
                "documenti-0-scadenza": "",
                "documenti-0-note": "",
                "documenti-0-visibile": "on",
            },
            files={},
            instance=self.famiglia,
            prefix="documenti",
        )

        self.assertTrue(formset.is_valid(), formset.errors)
        self.assertEqual(formset.forms[0].errors, {})
        formset.save()
        self.assertFalse(Documento.objects.filter(famiglia=self.famiglia).exists())

    def test_popup_delete_document_succeeds_even_if_storage_file_is_missing(self):
        with TemporaryDirectory() as tmpdir:
            with override_settings(MEDIA_ROOT=tmpdir):
                self.client.force_login(self.user)
                documento = Documento.objects.create(
                    famiglia=self.famiglia,
                    tipo_documento=self.tipo_documento,
                    descrizione="Documento orfano",
                    file=SimpleUploadedFile("documento-orfano.pdf", b"contenuto", content_type="application/pdf"),
                )
                file_path = Path(tmpdir) / documento.file.name
                self.assertTrue(file_path.exists())
                file_path.unlink()
                self.assertFalse(file_path.exists())

                with self.captureOnCommitCallbacks(execute=True):
                    response_post = self.client.post(
                        reverse("elimina_documento", kwargs={"pk": documento.pk}),
                        {"popup": "1"},
                    )

                self.assertEqual(response_post.status_code, 200)
                self.assertContains(response_post, "window.close()")
                self.assertFalse(Documento.objects.filter(pk=documento.pk).exists())


@skip("Legacy test basato sulla tabella anagrafica.Famiglia rimossa.")
class StudenteDetailPerformanceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser(
            username="studente-performance@example.com",
            email="studente-performance@example.com",
            password="Password123!",
        )
        self.regione = Regione.objects.create(nome="Emilia-Romagna", ordine=1, attiva=True)
        self.provincia = Provincia.objects.create(sigla="BO", nome="Bologna", regione=self.regione, ordine=1, attiva=True)
        self.citta = Citta.objects.create(nome="Bologna", provincia=self.provincia, codice_catastale="A944", ordine=1, attiva=True)
        self.indirizzo = Indirizzo.objects.create(
            via="Via Roma",
            numero_civico="1",
            citta=self.citta,
            provincia=self.provincia,
            regione=self.regione,
        )
        self.stato_famiglia = StatoRelazioneFamiglia.objects.create(stato="Iscritta", ordine=1, attivo=True)
        self.famiglia = Famiglia.objects.create(
            cognome_famiglia="Bersani",
            stato_relazione_famiglia=self.stato_famiglia,
            indirizzo_principale=self.indirizzo,
            attiva=True,
        )
        self.studente = Studente.objects.create(
            famiglia=self.famiglia,
            indirizzo=self.indirizzo,
            nome="Aurelia",
            cognome="Bersani",
            luogo_nascita=self.citta,
            attivo=True,
        )
        self.anno = AnnoScolastico.objects.create(
            nome_anno_scolastico="2025/2026",
            data_inizio=date(2025, 9, 1),
            data_fine=date(2026, 8, 31),
        )
        self.classe = Classe.objects.create(
            nome_classe="Infanzia",
            sezione_classe="A",
            ordine_classe=1,
            attiva=True,
        )
        self.stato_iscrizione = StatoIscrizione.objects.create(stato_iscrizione="Attiva", ordine=1, attiva=True)
        self.condizione = CondizioneIscrizione.objects.create(
            anno_scolastico=self.anno,
            nome_condizione_iscrizione="Retta standard",
            numero_mensilita_default=10,
            riduzione_speciale_ammessa=True,
            attiva=True,
        )
        TariffaCondizioneIscrizione.objects.create(
            condizione_iscrizione=self.condizione,
            ordine_figlio_da=1,
            ordine_figlio_a=None,
            retta_annuale=Decimal("4100.00"),
            preiscrizione=Decimal("200.00"),
            attiva=True,
        )
        self.agevolazione = Agevolazione.objects.create(
            nome_agevolazione="ISEE",
            importo_annuale_agevolazione=Decimal("300.00"),
            attiva=True,
        )
        self.iscrizione = Iscrizione.objects.create(
            studente=self.studente,
            classe=self.classe,
            anno_scolastico=self.anno,
            data_iscrizione=date(2025, 9, 15),
            data_fine_iscrizione=date(2026, 6, 5),
            stato_iscrizione=self.stato_iscrizione,
            condizione_iscrizione=self.condizione,
            agevolazione=self.agevolazione,
            riduzione_speciale=True,
            importo_riduzione_speciale=Decimal("150.00"),
            non_pagante=True,
            note_amministrative="Riduzione straordinaria approvata.",
            note="Verificare rinnovo a giugno.",
            attiva=True,
        )
        self.tipo_documento = TipoDocumento.objects.create(tipo_documento="Carta identita", ordine=1, attivo=True)
        self.documento = Documento.objects.create(
            studente=self.studente,
            tipo_documento=self.tipo_documento,
            descrizione="Documento studente",
        )
        self.client.force_login(self.user)

    def create_next_year_enrollment(self):
        anno_successivo = AnnoScolastico.objects.create(
            nome_anno_scolastico="2026/2027",
            data_inizio=date(2026, 9, 1),
            data_fine=date(2027, 8, 31),
        )
        condizione_successiva = CondizioneIscrizione.objects.create(
            anno_scolastico=anno_successivo,
            nome_condizione_iscrizione="Retta standard 2026",
            numero_mensilita_default=10,
            attiva=True,
        )
        TariffaCondizioneIscrizione.objects.create(
            condizione_iscrizione=condizione_successiva,
            ordine_figlio_da=1,
            ordine_figlio_a=None,
            retta_annuale=Decimal("4100.00"),
            preiscrizione=Decimal("200.00"),
            attiva=True,
        )
        return Iscrizione.objects.create(
            studente=self.studente,
            classe=self.classe,
            anno_scolastico=anno_successivo,
            data_iscrizione=date(2026, 9, 15),
            stato_iscrizione=self.stato_iscrizione,
            condizione_iscrizione=condizione_successiva,
            attiva=True,
        )

    def test_modifica_studente_page_stays_within_reasonable_query_budget(self):
        with CaptureQueriesContext(connection) as queries:
            response = self.client.get(reverse("modifica_studente", kwargs={"pk": self.studente.pk}))

        self.assertEqual(response.status_code, 200)
        normalized = Counter(re.sub(r"\s+", " ", item["sql"]).strip()[:260] for item in queries.captured_queries)
        self.assertLess(
            len(queries),
            110,
            msg="\n".join(
                [f"Total queries: {len(queries)}"]
                + [f"{count}x {sql}" for sql, count in normalized.most_common(20)]
            ),
        )

    def test_sync_studente_rate_schedules_limits_work_to_saved_enrollments(self):
        altra_iscrizione = self.create_next_year_enrollment()

        with patch.object(Iscrizione, "sync_rate_schedule", autospec=True, return_value="unchanged") as sync_mock:
            missing_count = sync_studente_iscrizioni_rate_schedules(
                self.studente,
                iscrizioni=[self.iscrizione],
            )

        self.assertEqual(missing_count, 0)
        self.assertEqual(sync_mock.call_count, 1)
        self.assertEqual(sync_mock.call_args.args[0].pk, self.iscrizione.pk)
        self.assertNotEqual(sync_mock.call_args.args[0].pk, altra_iscrizione.pk)

    def test_sync_studente_rate_schedules_can_force_full_student_sync(self):
        seconda_iscrizione = self.create_next_year_enrollment()

        with patch.object(Iscrizione, "sync_rate_schedule", autospec=True, return_value="unchanged") as sync_mock:
            missing_count = sync_studente_iscrizioni_rate_schedules(
                self.studente,
                iscrizioni=[],
                sync_all=True,
            )

        synced_ids = {call.args[0].pk for call in sync_mock.call_args_list}
        self.assertEqual(missing_count, 0)
        self.assertEqual(synced_ids, {self.iscrizione.pk, seconda_iscrizione.pk})

    def test_modifica_studente_inline_iscrizioni_renders_each_edit_field_once(self):
        response = self.client.get(reverse("modifica_studente", kwargs={"pk": self.studente.pk}))

        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        for field_name in [
            "condizione_iscrizione",
            "agevolazione",
            "riduzione_speciale",
            "importo_riduzione_speciale",
            "non_pagante",
            "modalita_pagamento_retta",
            "sconto_unica_soluzione_tipo",
            "sconto_unica_soluzione_valore",
            "scadenza_pagamento_unica",
            "attiva",
        ]:
            self.assertEqual(html.count(f'id="id_iscrizioni-0-{field_name}"'), 1)
            self.assertEqual(html.count(f'id="id_iscrizioni-__prefix__-{field_name}"'), 1)

    def test_modifica_studente_view_mode_shows_iscrizione_summary_fields(self):
        self.iscrizione.non_pagante = False
        self.iscrizione.save(update_fields=["non_pagante"])
        self.iscrizione.rate.all().delete()
        RataIscrizione.objects.create(
            iscrizione=self.iscrizione,
            famiglia=self.famiglia,
            tipo_rata=RataIscrizione.TIPO_PREISCRIZIONE,
            numero_rata=0,
            mese_riferimento=8,
            anno_riferimento=2025,
            importo_dovuto=Decimal("200.00"),
            importo_finale=Decimal("200.00"),
            importo_pagato=Decimal("200.00"),
            pagata=True,
        )
        for numero_rata, importo_pagato, pagata in [
            (1, Decimal("100.00"), True),
            (2, Decimal("50.00"), False),
            (3, Decimal("0.00"), False),
        ]:
            RataIscrizione.objects.create(
                iscrizione=self.iscrizione,
                famiglia=self.famiglia,
                numero_rata=numero_rata,
                mese_riferimento=numero_rata,
                anno_riferimento=2026,
                importo_dovuto=Decimal("100.00"),
                importo_finale=Decimal("100.00"),
                importo_pagato=importo_pagato,
                pagata=pagata,
            )

        response = self.client.get(reverse("modifica_studente", kwargs={"pk": self.studente.pk}))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="student-card-sticky-actions"')
        self.assertContains(response, 'data-student-card-sticky-save="1"')
        self.assertContains(response, 'id="studente-inline-lock-container"')
        self.assertContains(response, 'data-student-main-card-reorder')
        self.assertContains(response, 'data-student-stack-card-key="rates"')
        self.assertContains(response, 'data-student-stack-card-key="tabs"')
        self.assertContains(response, 'data-student-main-card-drag-handle')
        self.assertContains(response, 'data-student-main-card-collapse-toggle')
        self.assertContains(response, 'class="student-tabs-card-body"')
        self.assertContains(response, 'class="student-enrollment-card-list mode-view-only"')
        self.assertContains(response, 'id="tab-parenti"')
        self.assertContains(response, "Classe: Infanzia A")
        self.assertContains(response, "student-main-rate-card")
        self.assertContains(response, "Resoconto rate iscrizione")
        self.assertContains(response, 'data-family-rate-year-panel="student-rate-main-%s"' % self.iscrizione.pk)
        self.assertContains(response, 'class="student-main-rate-head-controls"')
        self.assertContains(response, 'data-family-rate-year-actions="student-rate-main-%s"' % self.iscrizione.pk)
        self.assertContains(response, 'data-action-url="%s"' % reverse("ricalcola_rate_iscrizione", kwargs={"pk": self.iscrizione.pk}))
        self.assertContains(response, "Chiudi iscrizione")
        self.assertContains(response, "Riconcilia")
        rata_da_riconciliare = RataIscrizione.objects.filter(
            iscrizione=self.iscrizione,
            tipo_rata=RataIscrizione.TIPO_MENSILE,
            pagata=False,
        ).first()
        self.assertContains(response, reverse("riconcilia_rata_iscrizione", kwargs={"pk": rata_da_riconciliare.pk}))
        self.assertContains(response, "Totale anno")
        self.assertContains(response, "Totale con Preiscrizione: EUR 500,00")
        self.assertContains(response, "Residuo EUR")
        self.assertContains(response, "student-main-rate-month is-paid")
        self.assertContains(response, "student-main-rate-month is-partial")
        self.assertContains(response, "student-main-rate-month is-unpaid")
        self.assertContains(response, '<span class="student-main-rate-month-period">Gennaio 2026</span>')
        self.assertContains(response, '<span class="student-main-rate-month-period">Febbraio 2026</span>')
        self.assertContains(response, "Pagata parzialmente")
        self.assertContains(response, "Da pagare")
        self.assertNotContains(response, 'data-student-overdue-rate-stat="1"')
        self.assertNotContains(response, "student-rate-compact-list")
        self.assertContains(response, "arboris-delete-studente-popup")
        self.assertNotContains(response, "Iscrizione corrente")
        self.assertNotContains(response, "Stato iscrizione:")
        self.assertContains(response, "Tipo di retta")
        self.assertContains(response, "Retta standard")
        self.assertContains(response, "Agevolazione")
        self.assertContains(response, "ISEE")
        self.assertContains(response, "Riduzione speciale")
        self.assertContains(response, "Importo riduzione speciale")
        self.assertContains(response, "Studente non pagante")
        self.assertContains(response, "Note generali")
        self.assertContains(response, "Note amministrative")

    def test_modifica_studente_view_mode_shows_overdue_rate_stat_only_when_present(self):
        self.iscrizione.rate.all().delete()
        today = timezone.localdate()
        for numero_rata, data_scadenza, importo_pagato, pagata in [
            (1, today - timedelta(days=2), Decimal("20.00"), False),
            (2, today - timedelta(days=3), Decimal("100.00"), True),
            (3, today + timedelta(days=5), Decimal("0.00"), False),
        ]:
            RataIscrizione.objects.create(
                iscrizione=self.iscrizione,
                famiglia=self.famiglia,
                numero_rata=numero_rata,
                mese_riferimento=numero_rata,
                anno_riferimento=today.year,
                importo_dovuto=Decimal("100.00"),
                importo_pagato=importo_pagato,
                data_scadenza=data_scadenza,
                pagata=pagata,
            )

        response = self.client.get(reverse("modifica_studente", kwargs={"pk": self.studente.pk}))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-student-overdue-rate-stat="1"')
        self.assertContains(response, 'data-student-overdue-rate-count="1"')
        self.assertContains(response, "Rate scadute")

    def test_modifica_studente_parenti_tab_uses_direct_relation_editor(self):
        relazione = RelazioneFamiliare.objects.create(relazione="Padre", ordine=1)
        familiare = Familiare.objects.create(
            famiglia=self.famiglia,
            relazione_familiare=relazione,
            nome="Simone",
            cognome="Bersani",
            sesso="M",
            telefono="3293560757",
            email="simone_bersani@example.com",
            referente_principale=True,
            attivo=True,
        )

        response = self.client.get(reverse("modifica_studente", kwargs={"pk": self.studente.pk}))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, f'data-relative-id="{familiare.pk}"')
        self.assertContains(response, "Genitori e Tutori")
        self.assertContains(response, 'name="direct_familiari_collegati"')
        self.assertContains(response, 'data-relative-card-action="edit"')
        self.assertContains(response, 'data-relative-card-action="add"')
        self.assertNotContains(response, "Aggiungi un parente")
        self.assertContains(response, 'id="parenti-table"')
        self.assertContains(response, 'id="parenti-empty-form-template"')
        self.assertContains(response, 'name="parenti-TOTAL_FORMS"')
        self.assertContains(response, "family-relation-pill")
        self.assertContains(response, "is-male")
        self.assertNotContains(response, 'class="family-person-chip">Referente</span>')

    def test_modifica_studente_uses_direct_relatives_with_inline_editor_and_siblings_tab(self):
        famiglia_familiare = Famiglia.objects.create(
            cognome_famiglia="Verdi",
            stato_relazione_famiglia=self.stato_famiglia,
            indirizzo_principale=self.indirizzo,
            attiva=True,
        )
        relazione = RelazioneFamiliare.objects.create(relazione="Madre", ordine=1)
        familiare = Familiare.objects.create(
            famiglia=famiglia_familiare,
            relazione_familiare=relazione,
            nome="Paola",
            cognome="Verdi",
            sesso="F",
            telefono="3331234567",
            email="paola.verdi@example.com",
            attivo=True,
        )
        StudenteFamiliare.objects.create(
            studente=self.studente,
            familiare=familiare,
            relazione_familiare=relazione,
            attivo=True,
        )
        sorella = Studente.objects.create(
            famiglia=famiglia_familiare,
            nome="Lisa",
            cognome="Verdi",
            sesso="F",
            attivo=True,
        )
        StudenteFamiliare.objects.create(
            studente=sorella,
            familiare=familiare,
            relazione_familiare=relazione,
            attivo=True,
        )

        response = self.client.get(reverse("modifica_studente", kwargs={"pk": self.studente.pk}))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Genitori e Tutori")
        self.assertContains(response, "Fratelli e Sorelle")
        self.assertContains(response, "Paola Verdi")
        self.assertContains(response, "Madre")
        self.assertContains(response, "Lisa Verdi")
        self.assertContains(response, "Sorella")
        self.assertContains(response, "Vedi profilo")
        self.assertNotContains(response, f'href="{reverse("modifica_familiare", kwargs={"pk": familiare.pk})}?edit=1"')
        self.assertNotContains(response, f'href="{reverse("crea_familiare")}?studente={self.studente.pk}"')
        self.assertContains(response, "Aggiungi un genitore o tutore")
        self.assertContains(response, 'name="direct_familiari_collegati"')
        self.assertContains(response, 'id="enable-inline-edit-studente-btn"')
        self.assertContains(response, 'data-relative-card-action="edit"')
        self.assertContains(response, 'data-relative-card-action="add"')
        self.assertContains(response, 'id="parenti-table"')
        self.assertNotContains(response, "Aggiungi un parente")

    def test_modifica_studente_inline_parenti_updates_direct_relations(self):
        relazione = RelazioneFamiliare.objects.create(relazione="Madre", ordine=1)
        familiare_attuale = Familiare.objects.create(
            famiglia=self.famiglia,
            relazione_familiare=relazione,
            nome="Maria",
            cognome="Bersani",
            attivo=True,
        )
        famiglia_alt = Famiglia.objects.create(
            cognome_famiglia="Verdi",
            stato_relazione_famiglia=self.stato_famiglia,
            attiva=True,
        )
        familiare_nuovo = Familiare.objects.create(
            famiglia=famiglia_alt,
            relazione_familiare=relazione,
            nome="Paola",
            cognome="Verdi",
            attivo=True,
        )
        StudenteFamiliare.objects.create(
            studente=self.studente,
            familiare=familiare_attuale,
            relazione_familiare=relazione,
            attivo=True,
        )

        response = self.client.post(
            reverse("modifica_studente", kwargs={"pk": self.studente.pk}),
            {
                "_edit_scope": "inline",
                "_inline_target": "parenti",
                "_continue": "1",
                "direct_familiari_collegati": [str(familiare_nuovo.pk)],
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertFalse(
            StudenteFamiliare.objects.get(studente=self.studente, familiare=familiare_attuale).attivo
        )
        self.assertTrue(
            StudenteFamiliare.objects.get(studente=self.studente, familiare=familiare_nuovo).attivo
        )

    def test_modifica_studente_documenti_view_shows_data_caricamento(self):
        response = self.client.get(reverse("modifica_studente", kwargs={"pk": self.studente.pk}))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "DATA CARICAMENTO")
        self.assertContains(response, self.documento.data_caricamento.strftime("%d / %m / %Y"))

    def test_modifica_studente_without_iscrizioni_renders_revealable_empty_row(self):
        studente_senza_iscrizioni = Studente.objects.create(
            famiglia=self.famiglia,
            nome="Agnese",
            cognome="Bersani",
            luogo_nascita=self.citta,
            attivo=True,
        )

        response = self.client.get(reverse("modifica_studente", kwargs={"pk": studente_senza_iscrizioni.pk}))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="id_iscrizioni-0-anno_scolastico"')
        self.assertContains(response, 'id="id_iscrizioni-0-classe"')
        self.assertContains(response, 'id="id_iscrizioni-0-condizione_iscrizione"')
        self.assertContains(response, 'id="iscrizioni-empty-form-template"')
        self.assertContains(response, 'data-inline-action="add" data-inline-prefix="iscrizioni"')

    def test_modifica_studente_inline_iscrizioni_ignores_default_empty_extra_row(self):
        studente_senza_iscrizioni = Studente.objects.create(
            famiglia=self.famiglia,
            nome="Agnese",
            cognome="Bersani",
            luogo_nascita=self.citta,
            attivo=True,
        )

        response = self.client.post(
            reverse("modifica_studente", kwargs={"pk": studente_senza_iscrizioni.pk}),
            {
                "_edit_scope": "inline",
                "_inline_target": "iscrizioni",
                "famiglia": self.famiglia.pk,
                "cognome": "Bersani",
                "nome": "Agnese",
                "sesso": "F",
                "data_nascita": "2020-09-14",
                "luogo_nascita": self.citta.pk,
                "luogo_nascita_search": "Bologna (BO)",
                "codice_fiscale": "",
                "indirizzo": "",
                "attivo": "on",
                "note": "",
                "iscrizioni-TOTAL_FORMS": "1",
                "iscrizioni-INITIAL_FORMS": "0",
                "iscrizioni-MIN_NUM_FORMS": "0",
                "iscrizioni-MAX_NUM_FORMS": "1000",
                "iscrizioni-0-id": "",
                "iscrizioni-0-anno_scolastico": self.anno.pk,
                "iscrizioni-0-classe": "",
                "iscrizioni-0-data_iscrizione": "",
                "iscrizioni-0-data_fine_iscrizione": "",
                "iscrizioni-0-stato_iscrizione": "",
                "iscrizioni-0-condizione_iscrizione": "",
                "iscrizioni-0-agevolazione": "",
                "iscrizioni-0-riduzione_speciale": "",
                "iscrizioni-0-importo_riduzione_speciale": "",
                "iscrizioni-0-non_pagante": "",
                "iscrizioni-0-modalita_pagamento_retta": Iscrizione.MODALITA_PAGAMENTO_RATEALE,
                "iscrizioni-0-sconto_unica_soluzione_tipo": Iscrizione.SCONTO_UNICA_NESSUNO,
                "iscrizioni-0-sconto_unica_soluzione_valore": "",
                "iscrizioni-0-scadenza_pagamento_unica": "",
                "iscrizioni-0-attiva": "on",
                "iscrizioni-0-note_amministrative": "",
                "iscrizioni-0-note": "",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertFalse(Iscrizione.objects.filter(studente=studente_senza_iscrizioni).exists())


@skip("Legacy test basato sulla tabella anagrafica.Famiglia rimossa.")
class StudentePrintTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser(
            username="print-admin@example.com",
            email="print-admin@example.com",
            password="Password123!",
            first_name="Anna",
            last_name="Admin",
        )
        self.client.force_login(self.user)
        stato_famiglia = StatoRelazioneFamiglia.objects.create(stato="Iscritta", ordine=1, attivo=True)
        self.famiglia = Famiglia.objects.create(
            cognome_famiglia="Bianchi",
            stato_relazione_famiglia=stato_famiglia,
        )
        self.studente = Studente.objects.create(
            famiglia=self.famiglia,
            nome="Luca",
            cognome="Bianchi",
            data_nascita=date(2020, 5, 10),
            codice_fiscale="BNCLCU20E10A944X",
            note="Nessuna intolleranza nota.",
        )
        self.anno = AnnoScolastico.objects.create(
            nome_anno_scolastico="2025/2026",
            data_inizio=date(2025, 9, 1),
            data_fine=date(2026, 8, 31),
            attivo=True,
        )
        self.stato_iscrizione = StatoIscrizione.objects.create(
            stato_iscrizione="Attiva",
            ordine=1,
            attiva=True,
        )
        self.condizione = CondizioneIscrizione.objects.create(
            anno_scolastico=self.anno,
            nome_condizione_iscrizione="Retta standard",
            numero_mensilita_default=10,
            mese_prima_retta=9,
            giorno_scadenza_rate=10,
        )
        TariffaCondizioneIscrizione.objects.create(
            condizione_iscrizione=self.condizione,
            ordine_figlio_da=1,
            ordine_figlio_a=None,
            retta_annuale=Decimal("1000.00"),
            preiscrizione=Decimal("100.00"),
        )
        self.iscrizione = Iscrizione.objects.create(
            studente=self.studente,
            anno_scolastico=self.anno,
            stato_iscrizione=self.stato_iscrizione,
            condizione_iscrizione=self.condizione,
            data_iscrizione=date(2025, 9, 1),
            attiva=True,
        )
        self.iscrizione.sync_rate_schedule()
        OsservazioneStudente.objects.create(
            studente=self.studente,
            titolo="Colloquio iniziale",
            data_inserimento=date(2026, 1, 10),
            testo="Osservazione di prova.",
            creato_da=self.user,
        )

    def test_student_detail_has_print_popup_button(self):
        response = self.client.get(reverse("modifica_studente", kwargs={"pk": self.studente.pk}))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Stampa")
        self.assertContains(response, reverse("stampa_studente_opzioni", kwargs={"pk": self.studente.pk}))
        self.assertContains(response, 'data-window-popup="1"')

    def test_print_options_popup_renders_section_checkboxes(self):
        response = self.client.get(reverse("stampa_studente_opzioni", kwargs={"pk": self.studente.pk}))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="dati_generali"')
        self.assertContains(response, 'name="piano_rate"')
        self.assertContains(response, 'name="osservazioni"')

    def test_print_sheet_composes_selected_sections(self):
        response = self.client.get(
            reverse("stampa_studente", kwargs={"pk": self.studente.pk}),
            {
                "dati_generali": "1",
                "piano_rate": "1",
                "osservazioni": "1",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Dati generali dello studente")
        self.assertContains(response, "Piano rate - 2025/2026")
        self.assertContains(response, "Retta standard")
        self.assertContains(response, "Osservazioni")
        self.assertContains(response, "Colloquio iniziale")
