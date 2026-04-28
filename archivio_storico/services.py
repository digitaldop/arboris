from collections import Counter
from datetime import date, datetime
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Prefetch, Q
from django.utils import timezone

from anagrafica.models import Documento, Familiare, Famiglia, Studente
from archivio_storico.models import ArchivioAnnoScolastico, ArchivioSnapshot, TipoSnapshotStorico
from economia.models import Iscrizione, RataIscrizione, TariffaCondizioneIscrizione
from osservazioni.models import OsservazioneStudente
from scuola.models import AnnoScolastico, Classe


def json_value(value):
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if value is None:
        return None
    return value


def user_label(user):
    if not user:
        return ""
    full_name = user.get_full_name().strip()
    return full_name or user.email or user.username


def address_label(indirizzo):
    if not indirizzo:
        return ""
    return indirizzo.label_full()


def model_source(instance):
    return {
        "source_app_label": instance._meta.app_label,
        "source_model": instance._meta.model_name,
        "source_pk": str(instance.pk),
    }


def anno_scolastico_archiviabile(anno_scolastico, today=None):
    today = today or timezone.localdate()
    motivi = []

    if anno_scolastico.data_inizio <= today <= anno_scolastico.data_fine:
        motivi.append("la data odierna rientra nel periodo dell'anno scolastico")
    elif anno_scolastico.data_fine >= today:
        motivi.append("l'anno scolastico non è ancora concluso")

    if ArchivioAnnoScolastico.objects.filter(anno_scolastico=anno_scolastico).exists():
        motivi.append("l'anno scolastico è già stato archiviato")

    return not motivi, motivi


def get_archiviazione_preview(anno_scolastico):
    iscrizioni_qs = Iscrizione.objects.filter(anno_scolastico=anno_scolastico)
    studenti_ids = set(iscrizioni_qs.values_list("studente_id", flat=True))
    famiglie_ids = set(
        Studente.objects.filter(pk__in=studenti_ids).values_list("famiglia_id", flat=True)
    )
    familiari_ids = set(Familiare.objects.filter(famiglia_id__in=famiglie_ids).values_list("pk", flat=True))

    documenti_qs = Documento.objects.filter(
        data_caricamento__gte=anno_scolastico.data_inizio,
        data_caricamento__lte=anno_scolastico.data_fine,
    ).filter(
        build_documenti_owner_query(studenti_ids, famiglie_ids, familiari_ids)
    )

    return {
        "classi": Classe.objects.filter(anno_scolastico=anno_scolastico).count(),
        "famiglie": len(famiglie_ids),
        "familiari": len(familiari_ids),
        "studenti": len(studenti_ids),
        "iscrizioni": iscrizioni_qs.count(),
        "rate": RataIscrizione.objects.filter(iscrizione__anno_scolastico=anno_scolastico).count(),
        "osservazioni": OsservazioneStudente.objects.filter(
            studente_id__in=studenti_ids,
            data_inserimento__gte=anno_scolastico.data_inizio,
            data_inserimento__lte=anno_scolastico.data_fine,
        ).count(),
        "documenti": documenti_qs.distinct().count(),
    }


def snapshot_fields(fields):
    return {key: json_value(value) for key, value in fields.items()}


def create_snapshot(archivio, instance, tipo, titolo, dati, ordine):
    return ArchivioSnapshot(
        archivio=archivio,
        tipo=tipo,
        titolo=titolo,
        dati=snapshot_fields(dati),
        ordine=ordine,
        **model_source(instance),
    )


def build_archivio_snapshots(archivio):
    anno = archivio.anno_scolastico
    snapshots = []
    ordine = 0

    classi = Classe.objects.filter(anno_scolastico=anno).order_by("ordine_classe", "nome_classe", "sezione_classe", "id")
    for classe in classi:
        ordine += 1
        snapshots.append(
            create_snapshot(
                archivio,
                classe,
                TipoSnapshotStorico.CLASSE,
                str(classe),
                {
                    "nome": classe.nome_classe,
                    "sezione": classe.sezione_classe,
                    "ordine": classe.ordine_classe,
                    "attiva": classe.attiva,
                    "note": classe.note,
                },
                ordine,
            )
        )

    tariffa_queryset = TariffaCondizioneIscrizione.objects.filter(attiva=True).order_by("ordine_figlio_da", "ordine_figlio_a", "id")
    rate_queryset = RataIscrizione.objects.order_by("anno_riferimento", "mese_riferimento", "numero_rata", "id")
    iscrizioni = (
        Iscrizione.objects.filter(anno_scolastico=anno)
        .select_related(
            "studente",
            "studente__famiglia",
            "studente__indirizzo__citta__provincia",
            "studente__indirizzo__provincia",
            "studente__famiglia__indirizzo_principale__citta__provincia",
            "studente__famiglia__indirizzo_principale__provincia",
            "classe",
            "stato_iscrizione",
            "condizione_iscrizione",
            "agevolazione",
        )
        .prefetch_related(
            Prefetch("rate", queryset=rate_queryset),
            Prefetch("condizione_iscrizione__tariffe", queryset=tariffa_queryset),
        )
        .order_by("studente__cognome", "studente__nome", "id")
    )

    studenti_by_id = {}
    famiglie_by_id = {}
    for iscrizione in iscrizioni:
        studenti_by_id[iscrizione.studente_id] = iscrizione.studente
        if iscrizione.studente.famiglia_id:
            famiglie_by_id[iscrizione.studente.famiglia_id] = iscrizione.studente.famiglia

    famiglie = sorted(famiglie_by_id.values(), key=lambda item: ((item.cognome_famiglia or "").lower(), item.pk))
    studenti = sorted(studenti_by_id.values(), key=lambda item: ((item.cognome or "").lower(), (item.nome or "").lower(), item.pk))
    familiari = Familiare.objects.filter(famiglia_id__in=famiglie_by_id.keys()).select_related(
        "famiglia",
        "relazione_familiare",
        "indirizzo__citta__provincia",
        "indirizzo__provincia",
        "luogo_nascita__provincia",
    ).order_by("famiglia__cognome_famiglia", "cognome", "nome", "id")

    for famiglia in famiglie:
        ordine += 1
        snapshots.append(
            create_snapshot(
                archivio,
                famiglia,
                TipoSnapshotStorico.FAMIGLIA,
                famiglia.cognome_famiglia,
                {
                    "cognome_famiglia": famiglia.cognome_famiglia,
                    "stato_relazione": str(famiglia.stato_relazione_famiglia) if famiglia.stato_relazione_famiglia_id else "",
                    "indirizzo_principale": address_label(famiglia.indirizzo_principale),
                    "referenti": famiglia.referenti_label(),
                    "note": famiglia.note,
                },
                ordine,
            )
        )

    for familiare in familiari:
        ordine += 1
        snapshots.append(
            create_snapshot(
                archivio,
                familiare,
                TipoSnapshotStorico.FAMILIARE,
                str(familiare),
                {
                    "famiglia": familiare.famiglia.cognome_famiglia if familiare.famiglia_id else "",
                    "nome": familiare.nome,
                    "cognome": familiare.cognome,
                    "relazione": str(familiare.relazione_familiare) if familiare.relazione_familiare_id else "",
                    "data_nascita": familiare.data_nascita,
                    "luogo_nascita": str(familiare.luogo_nascita) if familiare.luogo_nascita_id else "",
                    "codice_fiscale": familiare.codice_fiscale,
                    "telefono": familiare.telefono,
                    "email": familiare.email,
                    "indirizzo": address_label(familiare.indirizzo or getattr(familiare.famiglia, "indirizzo_principale", None)),
                    "convivente": familiare.convivente,
                    "referente_principale": familiare.referente_principale,
                    "scambio_retta": familiare.abilitato_scambio_retta,
                },
                ordine,
            )
        )

    for studente in studenti:
        ordine += 1
        snapshots.append(
            create_snapshot(
                archivio,
                studente,
                TipoSnapshotStorico.STUDENTE,
                str(studente),
                {
                    "famiglia": studente.famiglia.cognome_famiglia if studente.famiglia_id else "",
                    "nome": studente.nome,
                    "cognome": studente.cognome,
                    "data_nascita": studente.data_nascita,
                    "luogo_nascita": str(studente.luogo_nascita) if studente.luogo_nascita_id else "",
                    "sesso": studente.get_sesso_display() if studente.sesso else "",
                    "codice_fiscale": studente.codice_fiscale,
                    "indirizzo": address_label(studente.indirizzo_effettivo),
                    "note": studente.note,
                },
                ordine,
            )
        )

    for iscrizione in iscrizioni:
        ordine += 1
        riepilogo = iscrizione.get_riepilogo_economico()
        snapshots.append(
            create_snapshot(
                archivio,
                iscrizione,
                TipoSnapshotStorico.ISCRIZIONE,
                str(iscrizione),
                {
                    "studente": str(iscrizione.studente),
                    "famiglia": iscrizione.studente.famiglia.cognome_famiglia if iscrizione.studente.famiglia_id else "",
                    "classe": str(iscrizione.classe) if iscrizione.classe_id else "",
                    "data_iscrizione": iscrizione.data_iscrizione,
                    "data_fine_iscrizione": iscrizione.data_fine_iscrizione,
                    "stato": str(iscrizione.stato_iscrizione) if iscrizione.stato_iscrizione_id else "",
                    "condizione": str(iscrizione.condizione_iscrizione) if iscrizione.condizione_iscrizione_id else "",
                    "agevolazione": str(iscrizione.agevolazione) if iscrizione.agevolazione_id else "Nessuna",
                    "riduzione_speciale": iscrizione.riduzione_speciale,
                    "importo_riduzione_speciale": iscrizione.importo_riduzione_speciale,
                    "non_pagante": iscrizione.non_pagante,
                    "attiva": iscrizione.attiva,
                    "note_amministrative": iscrizione.note_amministrative,
                    "note": iscrizione.note,
                    "riepilogo_economico": {key: json_value(value) for key, value in riepilogo.items()},
                },
                ordine,
            )
        )

        for rata in iscrizione.rate.all():
            ordine += 1
            snapshots.append(
                create_snapshot(
                    archivio,
                    rata,
                    TipoSnapshotStorico.RATA,
                    f"{rata.display_label} - {iscrizione.studente}",
                    {
                        "studente": str(iscrizione.studente),
                        "famiglia": iscrizione.studente.famiglia.cognome_famiglia if iscrizione.studente.famiglia_id else "",
                        "iscrizione": str(iscrizione),
                        "tipo_rata": rata.get_tipo_rata_display(),
                        "numero_rata": rata.numero_rata,
                        "periodo": rata.display_period_label,
                        "mese_riferimento": rata.mese_riferimento,
                        "anno_riferimento": rata.anno_riferimento,
                        "descrizione": rata.descrizione,
                        "data_scadenza": rata.data_scadenza,
                        "importo_dovuto": rata.importo_dovuto,
                        "credito_applicato": rata.credito_applicato,
                        "altri_sgravi": rata.altri_sgravi,
                        "importo_finale": rata.importo_finale,
                        "pagata": rata.pagata,
                        "importo_pagato": rata.importo_pagato,
                        "data_pagamento": rata.data_pagamento,
                        "metodo_pagamento": str(rata.metodo_pagamento) if rata.metodo_pagamento_id else "",
                        "note": rata.note,
                    },
                    ordine,
                )
            )

    osservazioni = OsservazioneStudente.objects.filter(
        studente_id__in=studenti_by_id.keys(),
        data_inserimento__gte=anno.data_inizio,
        data_inserimento__lte=anno.data_fine,
    ).select_related("studente", "creato_da", "aggiornato_da").order_by("data_inserimento", "id")
    for osservazione in osservazioni:
        ordine += 1
        snapshots.append(
            create_snapshot(
                archivio,
                osservazione,
                TipoSnapshotStorico.OSSERVAZIONE,
                str(osservazione),
                {
                    "studente": str(osservazione.studente),
                    "titolo": osservazione.titolo or "",
                    "data_inserimento": osservazione.data_inserimento,
                    "testo": osservazione.testo,
                    "creato_da": user_label(osservazione.creato_da),
                    "aggiornato_da": user_label(osservazione.aggiornato_da),
                    "data_creazione": osservazione.data_creazione,
                    "data_aggiornamento": osservazione.data_aggiornamento,
                },
                ordine,
            )
        )

    familiari_ids = list(familiari.values_list("pk", flat=True))
    documenti = (
        Documento.objects.filter(data_caricamento__gte=anno.data_inizio, data_caricamento__lte=anno.data_fine)
        .filter(
            build_documenti_owner_query(studenti_by_id.keys(), famiglie_by_id.keys(), familiari_ids)
        )
        .select_related("tipo_documento", "famiglia", "familiare", "studente")
        .order_by("data_caricamento", "id")
    )
    for documento in documenti:
        ordine += 1
        owner = documento.studente or documento.familiare or documento.famiglia
        snapshots.append(
            create_snapshot(
                archivio,
                documento,
                TipoSnapshotStorico.DOCUMENTO,
                str(documento),
                {
                    "tipo_documento": str(documento.tipo_documento),
                    "descrizione": documento.descrizione,
                    "proprietario": str(owner) if owner else "",
                    "file_name": documento.filename,
                    "file_storage_name": documento.file.name if documento.file else "",
                    "data_caricamento": documento.data_caricamento,
                    "scadenza": documento.scadenza,
                    "visibile": documento.visibile,
                    "note": documento.note,
                },
                ordine,
            )
        )

    return snapshots


def build_documenti_owner_query(studenti_ids, famiglie_ids, familiari_ids):
    return (
        Q(studente_id__in=list(studenti_ids))
        | Q(famiglia_id__in=list(famiglie_ids))
        | Q(familiare_id__in=list(familiari_ids))
    )


def build_snapshot_counts(snapshots):
    return Counter(snapshot.tipo for snapshot in snapshots)


@transaction.atomic
def archivia_anno_scolastico(anno_scolastico, *, user=None, note=""):
    can_archive, motivi = anno_scolastico_archiviabile(anno_scolastico)
    if not can_archive:
        raise ValidationError("Anno scolastico non archiviabile: " + "; ".join(motivi) + ".")

    archivio = ArchivioAnnoScolastico.objects.create(
        anno_scolastico=anno_scolastico,
        nome_anno_scolastico=anno_scolastico.nome_anno_scolastico,
        data_inizio=anno_scolastico.data_inizio,
        data_fine=anno_scolastico.data_fine,
        archiviato_da=user if getattr(user, "is_authenticated", False) else None,
        note=note or "",
    )
    snapshots = build_archivio_snapshots(archivio)
    ArchivioSnapshot.objects.bulk_create(snapshots, batch_size=500)

    counts = build_snapshot_counts(snapshots)
    archivio.totale_snapshot = len(snapshots)
    archivio.totale_studenti = counts.get(TipoSnapshotStorico.STUDENTE, 0)
    archivio.totale_famiglie = counts.get(TipoSnapshotStorico.FAMIGLIA, 0)
    archivio.totale_iscrizioni = counts.get(TipoSnapshotStorico.ISCRIZIONE, 0)
    archivio.totale_rate = counts.get(TipoSnapshotStorico.RATA, 0)
    archivio.totale_osservazioni = counts.get(TipoSnapshotStorico.OSSERVAZIONE, 0)
    archivio.totale_documenti = counts.get(TipoSnapshotStorico.DOCUMENTO, 0)
    archivio.save(
        update_fields=[
            "totale_snapshot",
            "totale_studenti",
            "totale_famiglie",
            "totale_iscrizioni",
            "totale_rate",
            "totale_osservazioni",
            "totale_documenti",
        ]
    )
    return archivio
