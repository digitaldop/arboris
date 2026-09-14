"""Batch loading for read-only enrollment summaries; caches live on these instances only."""

from collections import defaultdict

from anagrafica.models import StudenteFamiliare
from economia.models import Iscrizione, TariffaCondizioneIscrizione
from economia.models.iscrizioni import get_mid_year_enrollment_settings


def prepare_iscrizioni_for_display(iscrizioni):
    if not iscrizioni:
        return

    student_ids = {item.studente_id for item in iscrizioni}
    relatives_by_student = defaultdict(set)
    for student_id, relative_id in StudenteFamiliare.objects.filter(
        studente_id__in=student_ids, attivo=True,
    ).values_list("studente_id", "familiare_id"):
        relatives_by_student[student_id].add(relative_id)

    siblings_by_relative = defaultdict(set)
    relative_ids = {pk for ids in relatives_by_student.values() for pk in ids}
    for student_id, relative_id in StudenteFamiliare.objects.filter(
        familiare_id__in=relative_ids, attivo=True, studente__attivo=True,
    ).values_list("studente_id", "familiare_id"):
        siblings_by_relative[relative_id].add(student_id)

    all_student_ids = student_ids | {pk for ids in siblings_by_relative.values() for pk in ids}
    positions_by_year = defaultdict(dict)
    # Use the same database ordering as Iscrizione.get_ordine_figlio(), including
    # null birth dates and inactive enrollments. Kinship here is direct, not transitive.
    for pk, student_id, year_id in Iscrizione.objects.filter(
        studente_id__in=all_student_ids,
        anno_scolastico_id__in={item.anno_scolastico_id for item in iscrizioni},
    ).order_by(
        "studente__data_nascita", "studente__cognome", "studente__nome", "studente_id", "id",
    ).values_list("pk", "studente_id", "anno_scolastico_id"):
        positions = positions_by_year[year_id]
        positions[student_id] = (pk, len(positions))

    tariffs_by_condition = defaultdict(list)
    for tariff in TariffaCondizioneIscrizione.objects.filter(
        condizione_iscrizione_id__in={item.condizione_iscrizione_id for item in iscrizioni},
        attiva=True,
    ).order_by("ordine_figlio_da", "ordine_figlio_a", "id"):
        tariffs_by_condition[tariff.condizione_iscrizione_id].append(tariff)

    mid_year_settings = get_mid_year_enrollment_settings()
    for item in iscrizioni:
        siblings = {item.studente_id}
        for relative_id in relatives_by_student[item.studente_id]:
            siblings.update(siblings_by_relative[relative_id])
        positions = positions_by_year[item.anno_scolastico_id]
        own_position = positions.get(item.studente_id, (None, len(positions)))[1]
        order = 1 + sum(
            positions[pk][1] < own_position for pk in siblings if pk in positions
        )
        item._ordine_figlio_cache = order
        item._tariffa_applicabile_cache = next((
            tariff for tariff in tariffs_by_condition[item.condizione_iscrizione_id]
            if tariff.ordine_figlio_da <= order
            and (tariff.ordine_figlio_a is None or tariff.ordine_figlio_a >= order)
        ), None)
        item._mid_year_settings_cache = mid_year_settings
