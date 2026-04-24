from pathlib import Path
from tempfile import TemporaryDirectory

import pandas as pd
from django.test import TestCase

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
