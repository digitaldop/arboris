from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from anagrafica.models import Citta, Familiare, Provincia, Studente, StudenteFamiliare
from archivio_storico.models import ArchivioAnnoScolastico, ArchivioSnapshot, TipoSnapshotStorico
from archivio_storico.services import anno_scolastico_archiviabile, archivia_anno_scolastico, get_archiviazione_preview
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

        self.studente = Studente.objects.create(
            nome="Luca",
            cognome="Bianchi",
            data_nascita=date(today.year - 7, 1, 15),
            codice_fiscale="BNCLCU19A01A944X",
            note="Note studente da congelare.",
        )
        self.familiare = Familiare.objects.create(nome="Anna", cognome="Bianchi")
        self.relazione = StudenteFamiliare.objects.create(
            studente=self.studente,
            familiare=self.familiare,
            referente_principale=True,
        )
        self.classe = Classe.objects.create(
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
        famiglia = archivio.snapshot.get(tipo=TipoSnapshotStorico.FAMIGLIA)
        self.assertEqual(famiglia.titolo, "Famiglia Bianchi")
        self.assertEqual(famiglia.source_pk, f"s-{self.studente.pk}")
        self.assertEqual(famiglia.dati["studenti"], str(self.studente))
        self.assertEqual(famiglia.dati["familiari"], str(self.familiare))
        dati_congelati = famiglia.dati.copy()

        self.studente.cognome = "Rossi"
        self.studente.save()
        self.familiare.cognome = "Verdi"
        self.familiare.save()
        self.relazione.delete()

        famiglia.refresh_from_db()
        self.assertEqual(famiglia.titolo, "Famiglia Bianchi")
        self.assertEqual(famiglia.dati, dati_congelati)
        self.assertEqual(
            set(archivio.snapshot.filter(tipo__in=[
                TipoSnapshotStorico.STUDENTE,
                TipoSnapshotStorico.FAMILIARE,
                TipoSnapshotStorico.ISCRIZIONE,
                TipoSnapshotStorico.RATA,
            ]).values_list("dati__famiglia", flat=True)),
            {"Famiglia Bianchi"},
        )

    def test_archive_family_counts_match_preview_with_siblings_and_inactive_links(self):
        fratello = Studente.objects.create(nome="Marco", cognome="Bianchi")
        isolato = Studente.objects.create(nome="Giulia", cognome="Verdi")
        estraneo = Studente.objects.create(nome="Paolo", cognome="Rossi")
        StudenteFamiliare.objects.create(studente=fratello, familiare=self.familiare)
        StudenteFamiliare.objects.create(studente=isolato, familiare=self.familiare, attivo=False)
        for studente in (fratello, isolato):
            Iscrizione.objects.create(
                studente=studente,
                anno_scolastico=self.anno_passato,
                classe=self.classe,
                stato_iscrizione=self.stato_iscrizione,
                condizione_iscrizione=self.condizione,
            )

        preview = get_archiviazione_preview(self.anno_passato)
        archivio = archivia_anno_scolastico(self.anno_passato, user=self.user)

        self.assertEqual(preview["famiglie"], 2)
        self.assertEqual(archivio.totale_famiglie, preview["famiglie"])
        self.assertEqual(archivio.totale_studenti, 3)
        self.assertEqual(archivio.totale_studenti, preview["studenti"])
        self.assertEqual(archivio.snapshot.filter(tipo=TipoSnapshotStorico.FAMILIARE).count(), preview["familiari"])
        famiglia = archivio.snapshot.get(tipo=TipoSnapshotStorico.FAMIGLIA, source_pk=f"s-{self.studente.pk}")
        self.assertIn(str(self.studente), famiglia.dati["studenti"])
        self.assertIn(str(fratello), famiglia.dati["studenti"])
        self.assertNotIn(str(isolato), famiglia.dati["studenti"])
        self.assertNotIn(str(estraneo), famiglia.dati["studenti"])
        self.assertFalse(archivio.snapshot.filter(tipo=TipoSnapshotStorico.STUDENTE, source_pk=str(estraneo.pk)).exists())

    def test_archive_preserves_birthplace_from_relative_person(self):
        provincia = Provincia.objects.create(nome="Bologna", sigla="BO")
        citta = Citta.objects.create(nome="Bologna", provincia=provincia)
        self.familiare.luogo_nascita = citta
        self.familiare.save()

        archivio = archivia_anno_scolastico(self.anno_passato, user=self.user)

        familiare = archivio.snapshot.get(tipo=TipoSnapshotStorico.FAMILIARE)
        self.assertEqual(familiare.dati["luogo_nascita"], "Bologna (BO)")

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
        self.assertContains(detail_response, "Famiglia Bianchi")
        self.assertContains(detail_response, "Osservazione anno passato")
        self.assertContains(detail_response, "BNCLCU19A01A944X")
