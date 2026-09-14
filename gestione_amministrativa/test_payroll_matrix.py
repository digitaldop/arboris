from datetime import date
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from gestione_finanziaria.models import MovimentoFinanziario
from sistema.models import LivelloPermesso, SistemaUtentePermessi

from .models import BustaPagaDipendente, Dipendente, PagamentoBustaPagaDipendente, StatoBustaPaga
from .payroll_matrix import build_payroll_matrix


class PayrollMatrixTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="payroll-matrix")
        cls.permissions = SistemaUtentePermessi.objects.create(
            user=cls.user, permesso_gestione_amministrativa=LivelloPermesso.GESTIONE,
        )
        cls.rossi = Dipendente.objects.create(nome="Ada", cognome="Rossi")
        cls.bianchi = Dipendente.objects.create(nome="Luca", cognome="Bianchi")

    def setUp(self):
        self.client.force_login(self.user)

    def busta(self, mese=1, dipendente=None, **kwargs):
        data = {"dipendente": dipendente or self.rossi, "anno": 2026, "mese": mese,
                "stato": StatoBustaPaga.EFFETTIVA, "netto_effettivo": Decimal("1000.00")}
        data.update(kwargs)
        return BustaPagaDipendente.objects.create(**data)

    def pagamento(self, busta, importo, giorno=1):
        return PagamentoBustaPagaDipendente.objects.create(
            busta_paga=busta, importo=Decimal(importo), data_pagamento=date(2026, 2, giorno),
        )

    def overview(self, **params):
        response = self.client.get(reverse("lista_buste_paga_dipendenti"), {
            "vista": "matrice", "anno": "2026", **params,
        })
        self.assertEqual(response.status_code, 200)
        return response

    def test_multiple_partial_payments_totals_and_missing_months(self):
        paid = self.busta()
        self.pagamento(paid, "400", 1)
        self.pagamento(paid, "600", 5)
        partial = self.busta(mese=2, data_pagamento_effettiva=date(2026, 2, 1))
        self.pagamento(partial, "250")
        self.busta(mese=3)
        matrix = self.overview().context["matrice"]
        cells = matrix["righe"][0]["celle"]
        self.assertEqual([cell["stato"] for cell in cells[:3]], ["pagata", "parziale", "non_pagata"])
        self.assertEqual(cells[0]["data_pagamento"], date(2026, 2, 5))
        self.assertIsNone(cells[3])
        self.assertEqual(matrix["totali"]["dovuto"], Decimal("3000"))
        self.assertEqual(matrix["totali"]["pagato"], Decimal("1250"))
        self.assertEqual(matrix["totali"]["residuo"], Decimal("1750"))
        self.assertEqual(matrix["totali"]["da_pagare"], 2)
        self.assertEqual(matrix["colonne"][1]["residuo"], Decimal("750"))

    def test_legacy_date_and_cumulative_movement_pay_only_the_payslip_amount(self):
        self.busta(data_pagamento_effettiva=date(2026, 2, 1))
        movimento = MovimentoFinanziario.objects.create(
            data_contabile=date(2026, 2, 10), importo=Decimal("-5000"), descrizione="Stipendi",
        )
        self.busta(mese=2, movimento_pagamento=movimento)
        matrix = self.overview().context["matrice"]
        self.assertEqual(matrix["totali"]["pagato"], Decimal("2000"))
        self.assertEqual(matrix["totali"]["pagate"], 2)
        self.assertEqual(matrix["righe"][0]["celle"][1]["data_pagamento"], date(2026, 2, 10))

    def test_forecast_thirteenth_zero_and_effective_amount_precedence(self):
        self.busta(mese=13, netto_effettivo=0, netto_previsto=900, stato=StatoBustaPaga.PREVISTA)
        self.busta(mese=1, netto_previsto=1500)
        self.busta(mese=2, netto_effettivo=0)
        matrix = self.overview().context["matrice"]
        self.assertEqual(matrix["colonne"][-1]["label"], "Tredicesima")
        self.assertEqual(matrix["totali"]["dovuto"], Decimal("1900"))
        self.assertEqual(matrix["totali"]["residuo_previsto"], Decimal("900"))
        self.assertEqual(matrix["totali"]["da_definire"], 1)
        self.assertEqual(matrix["totali"]["pagate"], 0)
        self.assertTrue(matrix["righe"][0]["celle"][-1]["prevista"])

    def test_excess_payment_does_not_offset_another_payslip(self):
        self.pagamento(self.busta(), "1100")
        self.busta(mese=2)
        totals = self.overview().context["matrice"]["totali"]
        self.assertEqual(totals["pagato"], Decimal("1100"))
        self.assertEqual(totals["eccedenza"], Decimal("100"))
        self.assertEqual(totals["residuo"], Decimal("1000"))

    def test_payment_filter_applies_to_cells_rows_and_totals(self):
        self.pagamento(self.busta(), "1000")
        self.pagamento(self.busta(mese=2), "250")
        self.busta(mese=3)
        self.pagamento(self.busta(dipendente=self.bianchi), "1000")
        matrix = self.overview(stato_pagamento="da_pagare").context["matrice"]
        self.assertEqual(len(matrix["righe"]), 1)
        self.assertEqual(matrix["righe"][0]["celle"][0], {"esclusa": True})
        self.assertEqual(matrix["totali"]["totale"], 2)
        self.assertEqual(matrix["totali"]["pagato"], Decimal("250"))
        self.assertEqual(matrix["totali"]["residuo"], Decimal("1750"))
        self.assertEqual(self.overview(stato_pagamento="pagata").context["matrice"]["totali"]["totale"], 2)
        self.assertEqual(self.overview(stato_pagamento="parziale").context["matrice"]["totali"]["totale"], 1)

    def test_year_month_employee_and_search_filters(self):
        self.busta(mese=13)
        self.busta(anno=2025)
        self.busta(dipendente=self.bianchi)
        matrix = self.overview(mese="13", dipendente=str(self.rossi.pk), q="ROSSI Ada").context["matrice"]
        self.assertEqual(matrix["totali"]["totale"], 1)
        self.assertEqual(matrix["num_colonne"], 3)
        self.assertEqual(matrix["colonne"][0]["mese"], 13)
        self.assertEqual(self.overview(q="non-esiste").context["matrice"]["totali"]["totale"], 0)

    def test_matrix_defaults_to_current_year_and_normalizes_invalid_filters(self):
        self.busta()
        for params in ({"anno": ""}, {"anno": "9" * 40, "mese": "99", "dipendente": "²", "stato_pagamento": "invalid"}):
            with self.subTest(params=params), patch("gestione_amministrativa.views.timezone.localdate", return_value=date(2026, 9, 14)):
                response = self.overview(**params)
                self.assertEqual(response.context["anno"], "2026")
                self.assertEqual(response.context["matrice"]["totali"]["totale"], 1)

    def test_alphabetical_order_and_existing_list_tab(self):
        self.busta()
        self.busta(dipendente=self.bianchi)
        response = self.overview(mese="1")
        self.assertEqual([row["dipendente"].pk for row in response.context["matrice"]["righe"]], [self.bianchi.pk, self.rossi.pk])
        self.assertIn("mese=1", response.context["elenco_url"])
        self.assertContains(response, "Matrice pagamenti")
        listing = self.client.get(reverse("lista_buste_paga_dipendenti"))
        self.assertEqual(listing.context["vista"], "elenco")
        self.assertContains(listing, "Netto effettivo")
        self.assertNotContains(listing, 'class="ga-payroll-table"')

    def test_read_only_permissions_hide_reconciliation_and_deny_unauthorized_access(self):
        self.busta()
        self.permissions.permesso_gestione_amministrativa = LivelloPermesso.VISUALIZZAZIONE
        self.permissions.save()
        response = self.overview()
        self.assertNotContains(response, 'class="ga-payroll-reconcile"')
        self.permissions.permesso_gestione_amministrativa = LivelloPermesso.NESSUNO
        self.permissions.save()
        response = self.client.get(reverse("lista_buste_paga_dipendenti"), {"vista": "matrice"})
        self.assertRedirects(response, reverse("home"), fetch_redirect_response=False)

    def test_matrix_query_count_is_constant_with_many_payslips(self):
        for mese in range(1, 14):
            self.pagamento(self.busta(mese=mese), "500")
        buste = BustaPagaDipendente.objects.select_related("dipendente__persona_collegata", "movimento_pagamento").prefetch_related("pagamenti")
        with self.assertNumQueries(2):
            matrix = build_payroll_matrix(buste, [(mese, str(mese)) for mese in range(1, 14)])
        self.assertEqual(matrix["totali"]["residuo"], Decimal("6500"))
