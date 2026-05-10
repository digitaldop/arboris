from collections import Counter, defaultdict, deque
from dataclasses import dataclass, field

from django.db.models import Q
from django.urls import reverse

from .models import Documento, Familiare, Studente, StudenteFamiliare


def _person_label(person):
    return " ".join(
        part
        for part in [getattr(person, "nome", ""), getattr(person, "cognome", "")]
        if part
    ).strip()


def _join_limited(labels, limit=2):
    values = [label for label in labels if label]
    if not values:
        return ""

    visible = values[:limit]
    label = ", ".join(visible)
    remaining = len(values) - len(visible)
    if remaining > 0:
        label = f"{label} +{remaining}"
    return label


@dataclass
class LogicalFamilyNote:
    owner_label: str
    owner_type: str
    note: str


@dataclass
class LogicalFamilySnapshot:
    legacy_family: object | None = None
    logical_key: str = ""
    student_ids: set[int] = field(default_factory=set)
    familiare_ids: set[int] = field(default_factory=set)
    studenti: list[Studente] = field(default_factory=list)
    familiari: list[Familiare] = field(default_factory=list)
    cognome_famiglia: str = ""
    indirizzo_principale: object | None = None
    note_entries: list[LogicalFamilyNote] = field(default_factory=list)

    @property
    def pk(self):
        if self.logical_key:
            return self.logical_key
        return self.legacy_family.pk if self.legacy_family else None

    @property
    def legacy_family_id(self):
        return self.legacy_family.pk if self.legacy_family else None

    def __str__(self):
        return self.cognome_famiglia or "Famiglia"

    def referenti_label(self):
        referenti = [familiare for familiare in self.familiari if familiare.referente_principale]
        if not referenti:
            referenti = self.familiari
        return _join_limited([_person_label(familiare) for familiare in referenti])

    def studenti_label(self):
        return _join_limited([_person_label(studente) for studente in self.studenti])

    def label_contesto_anagrafica(self):
        dettagli = []
        referenti = self.referenti_label()
        if referenti:
            dettagli.append(f"Referenti: {referenti}")
        studenti = self.studenti_label()
        if studenti:
            dettagli.append(f"Studenti: {studenti}")
        return " | ".join(dettagli)

    def label_select(self):
        dettagli = self.label_contesto_anagrafica()
        if dettagli:
            return f"{self.cognome_famiglia} - {dettagli}"
        return self.cognome_famiglia


def _logical_family_key(student_ids=None, familiare_ids=None, legacy_family_id=None):
    student_ids = sorted(int(pk) for pk in (student_ids or []) if pk)
    if student_ids:
        return f"s-{student_ids[0]}"

    familiare_ids = sorted(int(pk) for pk in (familiare_ids or []) if pk)
    if familiare_ids:
        return f"f-{familiare_ids[0]}"

    if legacy_family_id:
        return f"legacy-{legacy_family_id}"

    return ""


def _connected_member_ids(seed_student_ids=None, seed_familiare_ids=None):
    student_ids = set(seed_student_ids or [])
    familiare_ids = set(seed_familiare_ids or [])

    changed = True
    while changed and (student_ids or familiare_ids):
        changed = False

        relation_filter = Q()
        if student_ids:
            relation_filter |= Q(studente_id__in=student_ids)
        if familiare_ids:
            relation_filter |= Q(familiare_id__in=familiare_ids)
        if relation_filter:
            relazioni = StudenteFamiliare.objects.filter(attivo=True).filter(relation_filter)
            for studente_id, familiare_id in relazioni.values_list("studente_id", "familiare_id"):
                if studente_id and studente_id not in student_ids:
                    student_ids.add(studente_id)
                    changed = True
                if familiare_id and familiare_id not in familiare_ids:
                    familiare_ids.add(familiare_id)
                    changed = True

    return student_ids, familiare_ids


def _derive_family_name(students, relatives, fallback=""):
    surnames = []
    for person in list(students) + list(relatives):
        surname = (getattr(person, "cognome", "") or "").strip()
        if surname:
            surnames.append(surname)
    if not surnames:
        return fallback or "Famiglia"

    counts = Counter(surnames)
    return sorted(counts.items(), key=lambda item: (-item[1], item[0].lower()))[0][0]


def _derive_family_address(students, relatives, fallback=None):
    addresses = []
    by_id = {}
    for person in list(students) + list(relatives):
        address = getattr(person, "indirizzo_effettivo", None)
        if address and getattr(address, "pk", None):
            addresses.append(address.pk)
            by_id[address.pk] = address

    if not addresses:
        return fallback

    counts = Counter(addresses)
    selected_id = sorted(counts.items(), key=lambda item: (-item[1], item[0]))[0][0]
    return by_id.get(selected_id) or fallback


def _build_note_entries(students, relatives):
    entries = []
    for familiare in relatives:
        note = (getattr(familiare, "note", "") or "").strip()
        if note:
            entries.append(
                LogicalFamilyNote(
                    owner_label=_person_label(familiare),
                    owner_type="Familiare",
                    note=note,
                )
            )
    for studente in students:
        note = (getattr(studente, "note", "") or "").strip()
        if note:
            entries.append(
                LogicalFamilyNote(
                    owner_label=_person_label(studente),
                    owner_type="Studente",
                    note=note,
                )
            )
    return entries


def _load_students(student_ids):
    return list(
        Studente.objects.filter(pk__in=student_ids)
        .select_related(
            "indirizzo__citta__provincia",
            "indirizzo__provincia",
            "luogo_nascita__provincia",
            "nazione_nascita",
            "nazionalita",
        )
        .order_by("cognome", "nome", "id")
    )


def _load_relatives(familiare_ids):
    return list(
        Familiare.objects.filter(pk__in=familiare_ids)
        .select_related(
            "relazione_familiare",
            "indirizzo__citta__provincia",
            "indirizzo__provincia",
            "luogo_nascita__provincia",
            "nazione_nascita",
            "nazionalita",
        )
        .order_by("cognome", "nome", "id")
    )


def build_logical_family_snapshot_from_ids(
    student_ids=None,
    familiare_ids=None,
    *,
    legacy_family=None,
):
    student_ids = set(student_ids or [])
    familiare_ids = set(familiare_ids or [])
    students = _load_students(student_ids)
    relatives = _load_relatives(familiare_ids)
    fallback_name = getattr(legacy_family, "cognome_famiglia", "")
    fallback_address = getattr(legacy_family, "indirizzo_principale", None)

    return LogicalFamilySnapshot(
        legacy_family=legacy_family,
        logical_key=_logical_family_key(
            student_ids,
            familiare_ids,
            getattr(legacy_family, "pk", None),
        ),
        student_ids=set(student_ids),
        familiare_ids=set(familiare_ids),
        studenti=students,
        familiari=relatives,
        cognome_famiglia=_derive_family_name(students, relatives, fallback_name),
        indirizzo_principale=_derive_family_address(
            students,
            relatives,
            fallback_address,
        ),
        note_entries=_build_note_entries(students, relatives),
    )


def build_logical_family_snapshot(famiglia):
    if isinstance(famiglia, LogicalFamilySnapshot):
        return famiglia

    return LogicalFamilySnapshot()


def apply_logical_family_snapshot(famiglia):
    if isinstance(famiglia, LogicalFamilySnapshot):
        return famiglia

    return build_logical_family_snapshot(famiglia)


def iter_logical_family_snapshots():
    nodes = set()
    adjacency = defaultdict(set)

    def add_node(node):
        nodes.add(node)
        adjacency.setdefault(node, set())

    def link(left, right):
        add_node(left)
        add_node(right)
        adjacency[left].add(right)
        adjacency[right].add(left)

    for studente_id in Studente.objects.values_list("pk", flat=True):
        add_node(("s", studente_id))

    for familiare_id in Familiare.objects.values_list("pk", flat=True):
        add_node(("f", familiare_id))

    for studente_id, familiare_id in StudenteFamiliare.objects.filter(attivo=True).values_list(
        "studente_id",
        "familiare_id",
    ):
        if studente_id and familiare_id:
            link(("s", studente_id), ("f", familiare_id))

    seen = set()
    snapshots = []
    for node in sorted(nodes, key=lambda item: (item[0], item[1])):
        if node in seen:
            continue
        queue = deque([node])
        seen.add(node)
        component = set()
        while queue:
            current = queue.popleft()
            component.add(current)
            for neighbor in adjacency[current]:
                if neighbor not in seen:
                    seen.add(neighbor)
                    queue.append(neighbor)

        student_ids = {pk for kind, pk in component if kind == "s"}
        familiare_ids = {pk for kind, pk in component if kind == "f"}
        snapshots.append(build_logical_family_snapshot_from_ids(student_ids, familiare_ids))

    return sorted(
        snapshots,
        key=lambda snapshot: (
            (snapshot.cognome_famiglia or "").lower(),
            snapshot.logical_key or "",
        ),
    )


def resolve_logical_family_snapshot(logical_key):
    logical_key = (logical_key or "").strip()
    if not logical_key:
        return None

    if logical_key.startswith("s-"):
        try:
            student_id = int(logical_key.removeprefix("s-"))
        except (TypeError, ValueError):
            return None
        if not Studente.objects.filter(pk=student_id).exists():
            return None
        student_ids, familiare_ids = _connected_member_ids(seed_student_ids={student_id})
        return build_logical_family_snapshot_from_ids(student_ids, familiare_ids)

    if logical_key.startswith("f-"):
        try:
            familiare_id = int(logical_key.removeprefix("f-"))
        except (TypeError, ValueError):
            return None
        if not Familiare.objects.filter(pk=familiare_id).exists():
            return None
        student_ids, familiare_ids = _connected_member_ids(seed_familiare_ids={familiare_id})
        return build_logical_family_snapshot_from_ids(student_ids, familiare_ids)

    return None


def logical_family_detail_url(snapshot):
    if getattr(snapshot, "logical_key", ""):
        return reverse("modifica_famiglia_logica", kwargs={"key": snapshot.logical_key})
    return reverse("lista_famiglie")


def build_logical_family_snapshot_for_person(record):
    if isinstance(record, Studente) and getattr(record, "pk", None):
        student_ids, familiare_ids = _connected_member_ids(seed_student_ids={record.pk})
        return build_logical_family_snapshot_from_ids(student_ids, familiare_ids)
    if isinstance(record, Familiare) and getattr(record, "pk", None):
        student_ids, familiare_ids = _connected_member_ids(seed_familiare_ids={record.pk})
        return build_logical_family_snapshot_from_ids(student_ids, familiare_ids)
    return LogicalFamilySnapshot()


def logical_family_summary_for_person(record):
    snapshot = build_logical_family_snapshot_for_person(record)
    if not snapshot.logical_key and not snapshot.legacy_family_id:
        return {
            "label": "",
            "context": "",
            "referenti": "",
            "url": "",
            "snapshot": snapshot,
        }

    label = f"Famiglia {snapshot.cognome_famiglia}" if snapshot.cognome_famiglia else "Famiglia logica"
    return {
        "label": label,
        "context": f"Famiglia: {snapshot.cognome_famiglia}" if snapshot.cognome_famiglia else "Famiglia logica",
        "referenti": snapshot.referenti_label(),
        "url": logical_family_detail_url(snapshot),
        "snapshot": snapshot,
    }


def family_document_queryset(snapshot):
    return Documento.objects.filter(
        Q(familiare_id__in=snapshot.familiare_ids) | Q(studente_id__in=snapshot.student_ids)
    )


def logical_family_matches(snapshot, query):
    query = (query or "").strip().lower()
    if not query:
        return True

    values = [
        snapshot.cognome_famiglia,
        snapshot.referenti_label(),
        snapshot.studenti_label(),
    ]
    if snapshot.indirizzo_principale:
        values.append(snapshot.indirizzo_principale.label_full())

    for familiare in snapshot.familiari:
        values.extend(
            [
                familiare.nome,
                familiare.cognome,
                familiare.email,
                familiare.telefono,
                familiare.codice_fiscale,
            ]
        )
    for studente in snapshot.studenti:
        values.extend([studente.nome, studente.cognome, studente.codice_fiscale])

    return any(query in str(value or "").lower() for value in values)
