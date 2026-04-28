from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from anagrafica.models import Famiglia, StatoRelazioneFamiglia, Studente
from archivio_storico.models import ArchivioAnnoScolastico, ArchivioSnapshot, TipoSnapshotStorico
from archivio_storico.services import anno_scolastico_archiviabile, archivia_anno_scolastico
from economia.models import CondizioneIscrizione, Iscrizione, StatoIscrizione, TariffaCondizioneIscrizione
from osservazioni.models import OsservazioneStudente
from scuola.models import AnnoScolastico, Classe
from sistema.models import LivelloPermesso, SistemaUtentePermessi


class ArchivioStoricoTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="archivio@example.com",
            email="archivio@example.com",
            password="Password123!",
            first_name="Anna",
            last_name="Archivista",
        )
        SistemaUtentePermessi.objects.create(
            user=self.user,
            permesso_sistema=LivelloPermesso.GESTIONE,
        )

        today = timezone.localdate()
        self.anno_passato = AnnoScolastico.objects.create(
            nome_anno_scolastico=f"{today.year - 2}/{today.year - 1}",
            data_inizio=today.replace(year=today.year - 2, month=9, day=1),
            data_fine=today.replace(year=today.year - 1, month=8, day=31),
            attivo=True,
        )
        self.anno_in_corso = AnnoScolastico.objects.create(
            nome_anno_scolastico="Anno in corso test",
            data_inizio=today - timedelta(days=30),
            data_fine=today + timedelta(days=30),
            attivo=True,
        )
        self.anno_futuro = AnnoScolastico.objects.create(
            nome_anno_scolastico="Anno futuro test",
            data_inizio=today + timedelta(days=30),
            data_fine=today + timedelta(days=390),
            attivo=True,
        )

        stato_famiglia = StatoRelazioneFamiglia.objects.create(stato="Iscritta", ordine=1, attivo=True)
        self.famiglia = Famiglia.objects.create(cognome_famiglia="Bianchi", stato_relazione_famiglia=stato_famiglia)
        self.studente = Studente.objects.create(
            famiglia=self.famiglia,
            nome="Luca",
            cognome="Bianchi",
            data_nascita=date(today.year - 7, 1, 15),
            codice_fiscale="BNCLCU19A01A944X",
            note="Note studente da congelare.",
        )
        self.classe = Classe.objects.create(
            anno_scolastico=self.anno_passato,
            nome_classe="Primavera",
            sezione_classe="A",
            ordine_classe=1,
        )
        self.stato_iscrizione = StatoIscrizione.objects.create(stato_iscrizione="Attiva", ordine=1, attiva=True)
        self.condizione = CondizioneIscrizione.objects.create(
            anno_scolastico=self.anno_passato,
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
            classe=self.classe,
            anno_scolastico=self.anno_passato,
            stato_iscrizione=self.stato_iscrizione,
            condizione_iscrizione=self.condizione,
            data_iscrizione=self.anno_passato.data_inizio,
            attiva=True,
        )
        self.iscrizione.sync_rate_schedule()
        OsservazioneStudente.objects.create(
            studente=self.studente,
            titolo="Osservazione anno passato",
            data_inserimento=self.anno_passato.data_inizio + timedelta(days=30),
            testo="Testo osservazione congelata.",
            creato_da=self.user,
        )

    def test_current_or_not_finished_school_year_is_not_archivable(self):
        can_archive, reasons = anno_scolastico_archiviabile(self.anno_in_corso)

        self.assertFalse(can_archive)
        self.assertIn("la data odierna rientra nel periodo dell'anno scolastico", reasons)

        can_archive, reasons = anno_scolastico_archiviabile(self.anno_futuro)

        self.assertFalse(can_archive)
        self.assertIn("l'anno scolastico non è ancora concluso", reasons)

    def test_archive_past_school_year_creates_frozen_snapshots(self):
        archivio = archivia_anno_scolastico(self.anno_passato, user=self.user, note="Chiusura anno")

        self.assertEqual(archivio.nome_anno_scolastico, self.anno_passato.nome_anno_scolastico)
        self.assertEqual(archivio.archiviato_da, self.user)
        self.assertGreater(archivio.totale_snapshot, 0)
        self.assertEqual(archivio.totale_studenti, 1)
        self.assertEqual(archivio.totale_famiglie, 1)
        self.assertEqual(archivio.totale_iscrizioni, 1)
        self.assertEqual(archivio.totale_osservazioni, 1)
        self.assertTrue(
            ArchivioSnapshot.objects.filter(
                archivio=archivio,
                tipo=TipoSnapshotStorico.STUDENTE,
                dati__codice_fiscale="BNCLCU19A01A944X",
            ).exists()
        )

    def test_archive_cannot_be_repeated_for_same_school_year(self):
        archivia_anno_scolastico(self.anno_passato, user=self.user)

        with self.assertRaises(ValidationError):
            archivia_anno_scolastico(self.anno_passato, user=self.user)

    def test_archive_views_preview_and_confirm_flow(self):
        self.client.force_login(self.user)

        preview_response = self.client.get(
            reverse("anteprima_archiviazione_anno", kwargs={"anno_pk": self.anno_passato.pk})
        )

        self.assertEqual(preview_response.status_code, 200)
        self.assertContains(preview_response, "Archiviabile")
        self.assertContains(preview_response, "Osservazioni")

        post_response = self.client.post(
            reverse("archivia_anno_scolastico", kwargs={"anno_pk": self.anno_passato.pk}),
            {
                "conferma_archiviazione": "1",
                "conferma_testo": "ARCHIVIA",
                "note": "Archiviazione test",
            },
        )

        archivio = ArchivioAnnoScolastico.objects.get(anno_scolastico=self.anno_passato)
        self.assertRedirects(post_response, reverse("dettaglio_archivio_storico", kwargs={"pk": archivio.pk}))

        detail_response = self.client.get(reverse("dettaglio_archivio_storico", kwargs={"pk": archivio.pk}))
        self.assertContains(detail_response, "Osservazione anno passato")
        self.assertContains(detail_response, "BNCLCU19A01A944X")
