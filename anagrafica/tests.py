from pathlib import Path
from tempfile import TemporaryDirectory

import pandas as pd
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from anagrafica.dati_base_import import run_import_dati_base
from anagrafica.forms import (
    DocumentoFamigliaFormSet,
    FamiliareForm,
    FamiliareInlineForm,
    IscrizioneStudenteInlineForm,
    StudenteForm,
    StudenteInlineForm,
    StudenteStandaloneForm,
)
from anagrafica.views import famiglia_studenti_inline_queryset
from anagrafica.models import (
    CAP,
    Citta,
    Documento,
    Famiglia,
    Familiare,
    Indirizzo,
    Provincia,
    Regione,
    RelazioneFamiliare,
    StatoRelazioneFamiglia,
    Studente,
    TipoDocumento,
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

    def test_crea_indirizzo_page_renders(self):
        response = self.client.get(reverse("crea_indirizzo"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="id_provincia_display"')
        self.assertContains(response, 'id="id_cap_scelto"')

    def test_lista_famiglie_uses_standalone_panel(self):
        response = self.client.get(reverse("lista_famiglie"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'class="panel panel-standalone"')


class LuogoNascitaAutocompletePerformanceTests(TestCase):
    def test_inline_forms_render_selected_birth_city_without_loading_all_cities(self):
        regione = Regione.objects.create(nome="Lazio", ordine=1, attiva=True)
        provincia_roma = Provincia.objects.create(sigla="RM", nome="Roma", regione=regione, ordine=1, attiva=True)
        provincia_milano = Provincia.objects.create(sigla="MI", nome="Milano", regione=regione, ordine=2, attiva=True)
        roma = Citta.objects.create(nome="Roma", provincia=provincia_roma, codice_catastale="H501", ordine=1, attiva=True)
        Citta.objects.create(nome="Milano", provincia=provincia_milano, codice_catastale="F205", ordine=2, attiva=True)

        stato = StatoRelazioneFamiglia.objects.create(stato="Iscritta", ordine=1, attivo=True)
        famiglia = Famiglia.objects.create(cognome_famiglia="Rossi", stato_relazione_famiglia=stato, attiva=True)
        relazione = RelazioneFamiliare.objects.create(relazione="Madre", ordine=1)
        familiare = Familiare.objects.create(
            famiglia=famiglia,
            relazione_familiare=relazione,
            nome="Maria",
            cognome="Rossi",
            luogo_nascita=roma,
            attivo=True,
        )
        studente = Studente.objects.create(
            famiglia=famiglia,
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
        Familiare.objects.create(
            famiglia=famiglia,
            relazione_familiare=relazione,
            nome="Paolo",
            cognome="Bianchi",
            luogo_nascita=roma,
            attivo=True,
        )
        Studente.objects.create(
            famiglia=famiglia,
            nome="Anna",
            cognome="Bianchi",
            luogo_nascita=roma,
            attivo=True,
        )

        response = self.client.get(reverse("modifica_famiglia", kwargs={"pk": famiglia.pk}))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="familiari-0-luogo_nascita_search"')
        self.assertContains(response, 'name="studenti-0-luogo_nascita_search"')


class FamigliaInlineDefaultsTests(TestCase):
    def test_inline_forms_prefill_family_address(self):
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

        self.assertEqual(str(familiare_form["indirizzo"].value()), str(indirizzo.pk))
        self.assertEqual(familiare_form.initial["indirizzo_search"], indirizzo.label_select())
        self.assertIn('data-inherited-address="1"', str(familiare_form["indirizzo"]))

        self.assertEqual(str(studente_form["indirizzo"].value()), str(indirizzo.pk))
        self.assertEqual(studente_form.initial["indirizzo_search"], indirizzo.label_select())
        self.assertIn('data-inherited-address="1"', str(studente_form["indirizzo"]))

    def test_forms_normalize_family_address_back_to_inherited(self):
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
        self.assertIsNone(familiare_form.cleaned_data["indirizzo"])

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
        self.assertIsNone(studente_form.cleaned_data["indirizzo"])

    def test_studente_standalone_form_prefills_family_address_and_cf_binding(self):
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

        self.assertEqual(str(form["indirizzo"].value()), str(indirizzo.pk))
        self.assertEqual(form.initial["indirizzo_search"], indirizzo.label_select())
        self.assertIn('data-inherited-address="1"', str(form["indirizzo"]))
        self.assertIn('data-cf-luogo-id="1"', str(form["luogo_nascita"]))

    def test_studente_standalone_form_normalizes_family_address_back_to_inherited(self):
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
        self.assertIsNone(form.cleaned_data["indirizzo"])

    def test_iscrizione_inline_prefers_current_school_year(self):
        from datetime import date
        from scuola.models import AnnoScolastico

        AnnoScolastico.objects.create(
            nome_anno_scolastico="2024/2025",
            data_inizio=date(2024, 9, 1),
            data_fine=date(2025, 8, 31),
            corrente=False,
        )
        anno_corrente = AnnoScolastico.objects.create(
            nome_anno_scolastico="2025/2026",
            data_inizio=date(2025, 9, 1),
            data_fine=date(2026, 8, 31),
            corrente=True,
        )

        form = IscrizioneStudenteInlineForm(prefix="iscrizioni-0")

        self.assertEqual(form.initial["anno_scolastico"], anno_corrente.pk)

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
        self.tipo_documento = TipoDocumento.objects.create(tipo_documento="Carta identita", ordine=1, attivo=True)

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
