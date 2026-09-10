from datetime import date
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from .forms import DocumentoFornitoreForm
from .models import DocumentoFornitore, Fornitore
from .proforme import annulla_collegamento_proforma, collega_proforma


class RigheImportoProformaTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.fornitore = Fornitore.objects.create(denominazione="Fornitore collaudo righe")
        cls.user = User.objects.create_superuser(username="righe-test")

    def dati(self, righe=None, initial=0, **overrides):
        if righe is None:
            righe = [{"descrizione": "Cassa ENPACL", "tipo": "percentuale", "valore": "4", "soggetta_iva": "on"}]
        data = {
            "fornitore": self.fornitore.pk, "tipo_documento": "proforma", "numero_documento": "PF-ENPACL",
            "data_documento": "2026-09-10", "imponibile": "81,00", "aliquota_iva": "22",
            "imponibile_ritenuta_acconto": "81,00", "aliquota_ritenuta_acconto": "20",
            "stato": "da_pagare", "righe_importo-TOTAL_FORMS": str(len(righe)),
            "righe_importo-INITIAL_FORMS": str(initial),
            "scadenze-TOTAL_FORMS": "0", "scadenze-INITIAL_FORMS": "0",
        }
        for index, row in enumerate(righe):
            data.update({f"righe_importo-{index}-{key}": value for key, value in row.items()})
        data.update(overrides)
        return data

    def salva(self, data=None, instance=None):
        form = DocumentoFornitoreForm(data if data is not None else self.dati(), instance=instance)
        self.assertTrue(form.is_valid(), (form.errors, form.righe_importo_formset.errors))
        return form.save()

    def test_enpacl_calcola_e_salva_esempio_allegato(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse("crea_documento_fornitore"), self.dati(totale="999", iva="999"))
        self.assertEqual(response.status_code, 302)
        doc = DocumentoFornitore.objects.get(numero_documento="PF-ENPACL")
        self.assertEqual(doc.importo_base, Decimal("81.00"))
        self.assertEqual(doc.imponibile, Decimal("84.24"))
        self.assertEqual(doc.iva, Decimal("18.53"))
        self.assertEqual(doc.totale, Decimal("102.77"))
        self.assertEqual(doc.ritenuta_acconto, Decimal("16.20"))
        self.assertEqual(doc.totale_da_pagare, Decimal("86.57"))
        self.assertEqual(doc.scadenze.get().importo_previsto, Decimal("86.57"))
        self.assertEqual(doc.righe_importo_personalizzate[0]["importo"], "3.24")

    def test_riapertura_e_salvataggi_ripetuti_non_sommano_due_volte(self):
        doc = self.salva()
        for _ in range(2):
            doc.refresh_from_db()
            form = DocumentoFornitoreForm(instance=doc)
            self.assertEqual(form.initial["imponibile"], Decimal("81.00"))
            doc = self.salva(self.dati(initial=1), instance=doc)
            self.assertEqual(doc.totale, Decimal("102.77"))

    def test_modifica_base_ricalcola_percentuale(self):
        doc = self.salva()
        doc = self.salva(self.dati(initial=1, imponibile="100", imponibile_ritenuta_acconto="100"), instance=doc)
        self.assertEqual(doc.righe_importo_personalizzate[0]["importo"], "4.00")
        self.assertEqual(doc.totale_da_pagare, Decimal("106.88"))

    def test_importo_fisso_italiano_spesa_senza_iva_e_sconto(self):
        doc = self.salva(self.dati(righe=[
            {"descrizione": "Cassa", "tipo": "fisso", "valore": "3,24", "soggetta_iva": "on"},
            {"descrizione": "Spese", "tipo": "fisso", "valore": "2,00"},
            {"descrizione": "Sconto", "tipo": "fisso", "valore": "-1,00", "soggetta_iva": "on"},
        ]))
        self.assertEqual(doc.imponibile, Decimal("83.24"))
        self.assertEqual(doc.iva, Decimal("18.31"))
        self.assertEqual(doc.totale, Decimal("103.55"))
        self.assertEqual(doc.totale_da_pagare, Decimal("87.35"))

    def test_percentuali_indipendenti_e_arrotondamento_al_centesimo(self):
        doc = self.salva(self.dati(imponibile="1.25", imponibile_ritenuta_acconto="0", righe=[
            {"descrizione": "Cassa A", "tipo": "percentuale", "valore": "2", "soggetta_iva": "on"},
            {"descrizione": "Cassa B", "tipo": "percentuale", "valore": "2", "soggetta_iva": "on"},
            {"descrizione": "Sconto", "tipo": "percentuale", "valore": "-2"},
        ]))
        self.assertEqual([row["importo"] for row in doc.righe_importo_personalizzate], ["0.03", "0.03", "-0.03"])
        self.assertEqual(doc.imponibile, Decimal("1.31"))
        self.assertEqual(doc.totale, Decimal("1.57"))

    def test_rimozione_riga_ripristina_totali_base(self):
        doc = self.salva()
        doc = self.salva(self.dati(initial=1, **{"righe_importo-0-DELETE": "on"}), instance=doc)
        self.assertEqual(doc.righe_importo_personalizzate, [])
        self.assertEqual(doc.imponibile, Decimal("81.00"))
        self.assertEqual(doc.totale_da_pagare, Decimal("82.62"))

    def test_campo_errato_non_salva_e_mantiene_righe_nel_form(self):
        self.client.force_login(self.user)
        data = self.dati(**{"righe_importo-0-valore": "non numerico"})
        response = self.client.post(reverse("crea_documento_fornitore"), data)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Cassa ENPACL")
        self.assertTrue(response.context["form"].righe_importo_formset.forms[0].errors)
        self.assertFalse(DocumentoFornitore.objects.exists())

    def test_validazione_righe(self):
        for field, value in [("descrizione", ""), ("tipo", "ignoto"), ("valore", "NaN"), ("valore", "Infinity"), ("valore", "101")]:
            with self.subTest(field=field, value=value):
                form = DocumentoFornitoreForm(self.dati(**{f"righe_importo-0-{field}": value}))
                self.assertFalse(form.is_valid())
                self.assertIn(field, form.righe_importo_formset.forms[0].errors)

    def test_importo_base_richiesto_con_righe(self):
        form = DocumentoFornitoreForm(self.dati(imponibile="", totale="102.77"))
        self.assertFalse(form.is_valid())
        self.assertIn("imponibile", form.errors)

    def test_base_zero_con_importi_fissi_rimane_compilata_alla_riapertura(self):
        doc = self.salva(self.dati(imponibile="0", imponibile_ritenuta_acconto="0", righe=[{
            "descrizione": "Spese", "tipo": "fisso", "valore": "2",
        }]))
        self.assertEqual(doc.totale, Decimal("2.00"))
        form = DocumentoFornitoreForm(instance=doc)
        self.assertIn('value="0,00"', str(form["imponibile"]))

    def test_ritenuta_non_puo_superare_totale_con_righe(self):
        form = DocumentoFornitoreForm(self.dati(imponibile_ritenuta_acconto="1000"))
        self.assertFalse(form.is_valid())
        self.assertIn("ritenuta_acconto", form.errors)

    def test_righe_invariate_dopo_errore_su_altro_campo(self):
        doc = self.salva()
        self.client.force_login(self.user)
        response = self.client.post(reverse("modifica_documento_fornitore", args=[doc.pk]) + "?popup=1",
                                    self.dati(initial=1, numero_documento=""))
        self.assertContains(response, "Cassa ENPACL")
        self.assertIn("numero_documento", response.context["form"].errors)
        doc.refresh_from_db()
        self.assertEqual(doc.imponibile, Decimal("84.24"))
        self.assertEqual(doc.righe_importo_personalizzate[0]["importo"], "3.24")

    def test_sconti_non_possono_rendere_negativo_imponibile_o_totale(self):
        for taxable, error_field in [("on", "imponibile"), ("", "totale")]:
            form = DocumentoFornitoreForm(self.dati(righe=[{
                "descrizione": "Sconto", "tipo": "fisso", "valore": "-200", "soggetta_iva": taxable,
            }]))
            self.assertFalse(form.is_valid())
            self.assertIn(error_field, form.errors)

    def test_formset_mancante_non_cancella_righe_salvate(self):
        doc = self.salva()
        data = {key: value for key, value in self.dati().items() if not key.startswith("righe_importo-")}
        form = DocumentoFornitoreForm(data, instance=doc)
        self.assertFalse(form.is_valid())
        doc.refresh_from_db()
        self.assertEqual(len(doc.righe_importo_personalizzate), 1)

    def test_limite_righe_e_tipo_documento(self):
        for data in [self.dati(**{"righe_importo-TOTAL_FORMS": "51"}), self.dati(tipo_documento="fattura")]:
            form = DocumentoFornitoreForm(data)
            self.assertFalse(form.is_valid())

    def test_schermata_standard_e_popup_mostrano_righe_ed_errori(self):
        doc = self.salva()
        self.client.force_login(self.user)
        for query in ["", "?popup=1"]:
            response = self.client.get(reverse("modifica_documento_fornitore", args=[doc.pk]) + query)
            self.assertContains(response, "Cassa ENPACL")
            self.assertContains(response, "Totale imponibile IVA")
            self.assertContains(response, 'id="add-riga-importo"')
            self.assertEqual(response.context["form"].initial["imponibile"], Decimal("81.00"))

    def test_collegamento_fattura_conserva_righe_e_scadenza(self):
        self.client.force_login(self.user)
        self.client.post(reverse("crea_documento_fornitore"), self.dati())
        doc = DocumentoFornitore.objects.get(numero_documento="PF-ENPACL")
        scadenza_pk = doc.scadenze.get().pk
        fattura = DocumentoFornitore.objects.create(
            fornitore=self.fornitore, numero_documento="F-ENPACL", data_documento=date(2026, 9, 10),
            imponibile=doc.imponibile, iva=doc.iva, totale=doc.totale, ritenuta_acconto=doc.ritenuta_acconto,
        )
        collega_proforma(fattura, doc, utente=self.user)
        doc.refresh_from_db()
        self.assertEqual(doc.righe_importo_personalizzate[0]["importo"], "3.24")
        self.assertEqual(fattura.scadenze.get().pk, scadenza_pk)
        response = self.client.post(reverse("modifica_documento_fornitore", args=[doc.pk]), self.dati())
        self.assertEqual(response.status_code, 302)
        annulla_collegamento_proforma(fattura, utente=self.user)
        self.assertEqual(doc.scadenze.get().importo_previsto, Decimal("86.57"))
