from pathlib import Path
from tempfile import TemporaryDirectory

import pandas as pd
from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from anagrafica.dati_base_import import run_import_dati_base
from anagrafica.models import CAP, Citta, Provincia, Regione


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
