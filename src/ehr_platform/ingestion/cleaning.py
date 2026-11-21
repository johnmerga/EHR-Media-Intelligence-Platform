"""Turn raw records into the clean intermediate representation.

The policy, in short:

* Normalize formats confidently (MRN, dates, gender, names) and log each change.
* A patient is identified by canonical MRN only. Records with different MRNs
  are never merged, even when name and date of birth match; they are flagged.
* When sources disagree about a patient, the most trusted source wins
  (JSON export, then lab CSV, then scanned text) and the losing value is kept
  in the audit log.
* Exact duplicates are dropped; near-duplicates (same patient, kind, date and
  text ignoring case and spacing) are merged.
* Nothing is dropped silently. Records that cannot be attributed to a patient
  or have no content are quarantined with a reason.
"""

from __future__ import annotations

import hashlib
from collections import defaultdict
from collections.abc import Callable, Hashable, Sequence
from dataclasses import dataclass
from datetime import date
from typing import TypeVar

from ehr_platform.ingestion.models import (
    AuditEntry,
    CleanEncounter,
    CleanPatient,
    CleanRecord,
    Gender,
    IngestionResult,
    QuarantinedRecord,
    RawBatch,
    RawDemographics,
    RawEncounter,
    RawRecord,
    RecordKind,
    Severity,
    Source,
)
from ehr_platform.ingestion.normalizers import (
    Normalized,
    classify_kind,
    collapse_whitespace,
    is_blank,
    normalize_encounter_class,
    normalize_gender,
    normalize_mrn,
    normalize_name,
    parse_abnormal_flag,
    parse_date,
    text_fingerprint,
)

V = TypeVar("V")

_DEFAULT_KIND = {
    Source.JSON: RecordKind.PROGRESS_NOTE,
    Source.CSV: RecordKind.LAB_REPORT,
    Source.TEXT: RecordKind.SCANNED_NOTE,
}


@dataclass(frozen=True)
class _Sighting:
    """One source's view of a patient's demographics."""

    source: Source
    demographics: RawDemographics


@dataclass(frozen=True)
class _Candidate:
    """A normalized demographic value and the source that supplied it."""

    source: Source
    value: object
    label: str


class _Audit:
    """Collects audit entries for one entity, skipping exact repeats."""

    def __init__(self, entity_id: str = "") -> None:
        self.entity_id = entity_id
        self._entries: list[AuditEntry] = []

    def add(
        self,
        field: str,
        old: object,
        new: object,
        rule: str,
        severity: Severity,
        message: str,
    ) -> None:
        entry = AuditEntry(
            entity_id=self.entity_id,
            field=field,
            old_value=None if old is None else str(old),
            new_value=None if new is None else str(new),
            rule=rule,
            severity=severity,
            message=message,
        )
        if entry not in self._entries:
            self._entries.append(entry)

    def add_normalized(self, field: str, raw: str | None, result: Normalized[V]) -> None:
        if result.rule is not None:
            self.add(
                field, raw, _display(result.value), result.rule, result.severity, result.message
            )

    def entries(self, entity_id: str | None = None) -> list[AuditEntry]:
        """Return the entries, optionally re-addressed to an ID decided late."""
        if entity_id is None:
            return list(self._entries)
        return [entry.model_copy(update={"entity_id": entity_id}) for entry in self._entries]


def _display(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, tuple):
        return " ".join(str(part) for part in value if part)
    return str(value)


def clean(batch: RawBatch, *, today: date | None = None) -> IngestionResult:
    """Clean a raw batch. ``today`` is injectable so results are reproducible."""
    today = today or date.today()

    identified, quarantined = _triage(batch.records)

    sightings: dict[str, list[_Sighting]] = defaultdict(list)
    for mrn, record in identified:
        sighting = _Sighting(record.source, record.patient)
        if sighting not in sightings[mrn]:
            sightings[mrn].append(sighting)

    patients = [_resolve_patient(mrn, seen, today) for mrn, seen in sorted(sightings.items())]
    _flag_possible_duplicates(patients)

    encounters = _clean_encounters(batch.encounters, set(sightings), today)
    known_encounters = {(e.patient_mrn, e.encounter_id) for e in encounters}
    records = _clean_records(identified, known_encounters, today)

    return IngestionResult(
        patients=patients,
        encounters=encounters,
        records=records,
        quarantined=quarantined,
        raw_record_count=len(batch.records),
    )


# --------------------------------------------------------------------------- #
# Triage
# --------------------------------------------------------------------------- #


def _triage(
    records: Sequence[RawRecord],
) -> tuple[list[tuple[str, RawRecord]], list[QuarantinedRecord]]:
    """Separate records that can be cleaned from those that must be set aside."""
    identified: list[tuple[str, RawRecord]] = []
    quarantined: list[QuarantinedRecord] = []
    for record in records:
        mrn = normalize_mrn(record.patient.mrn)
        if mrn.value is None:
            reason = mrn.message or "The record has no MRN, so it cannot be attributed to a patient"
            quarantined.append(
                QuarantinedRecord(
                    source_ref=record.source_ref,
                    rule="record.missing_patient_identifier",
                    reason=reason,
                    raw=record,
                )
            )
        elif is_blank(record.text):
            quarantined.append(
                QuarantinedRecord(
                    source_ref=record.source_ref,
                    rule="record.empty_content",
                    reason="The record has no text content",
                    raw=record,
                )
            )
        else:
            identified.append((mrn.value, record))
    return identified, quarantined


# --------------------------------------------------------------------------- #
# Patients
# --------------------------------------------------------------------------- #


def _resolve_patient(mrn: str, sightings: list[_Sighting], today: date) -> CleanPatient:
    audit = _Audit(mrn)
    names: list[_Candidate] = []
    births: list[_Candidate] = []
    genders: list[_Candidate] = []

    for sighting in sightings:
        raw = sighting.demographics
        audit.add_normalized("mrn", raw.mrn, normalize_mrn(raw.mrn))

        name = normalize_name(raw.name)
        audit.add_normalized("name", raw.name, name)
        if name.value is not None:
            names.append(_Candidate(sighting.source, name.value, " ".join(name.value).strip()))

        birth = _parse_birth_date(raw.dob, today)
        audit.add_normalized("birth_date", raw.dob, birth)
        if birth.value is not None:
            births.append(_Candidate(sighting.source, birth.value, birth.value.isoformat()))

        gender = normalize_gender(raw.sex)
        audit.add_normalized("gender", raw.sex, gender)
        # "unknown" carries no information, so it never competes with a real value.
        if gender.value not in (None, Gender.UNKNOWN):
            genders.append(_Candidate(sighting.source, gender.value, str(gender.value)))

    sources = sorted({s.source for s in sightings}, key=lambda source: source.precedence)
    name_value, name_conflict = _resolve_field(
        "name", names, sources, audit, key=lambda v: str(v).casefold()
    )
    birth_value, birth_conflict = _resolve_field("birth_date", births, sources, audit)
    gender_value, gender_conflict = _resolve_field("gender", genders, sources, audit)

    if name_value is None:
        audit.add(
            "name",
            None,
            None,
            "demographics.missing",
            Severity.WARNING,
            "No source provides a patient name",
        )
    if birth_value is None:
        audit.add(
            "birth_date",
            None,
            None,
            "demographics.missing",
            Severity.WARNING,
            "No source provides a usable date of birth",
        )
    if gender_value is None:
        audit.add(
            "gender",
            None,
            Gender.UNKNOWN,
            "gender.defaulted_unknown",
            Severity.WARNING,
            "No source provides the patient's sex; recorded as unknown",
        )

    given, family = name_value if isinstance(name_value, tuple) else (None, None)
    return CleanPatient(
        mrn=mrn,
        given_name=given or None,
        family_name=family or None,
        birth_date=birth_value if isinstance(birth_value, date) else None,
        gender=gender_value if isinstance(gender_value, Gender) else Gender.UNKNOWN,
        has_conflict=name_conflict or birth_conflict or gender_conflict,
        sources=sources,
        audit=audit.entries(),
    )


def _parse_birth_date(raw: str | None, today: date) -> Normalized[date | None]:
    parsed = parse_date(raw, today=today)
    if parsed.value is not None and parsed.value > today:
        return Normalized(
            None,
            "date.implausible",
            Severity.WARNING,
            f"Date of birth '{raw}' is in the future; the value was cleared",
        )
    return parsed


def _identity(value: object) -> Hashable:
    return value


def _resolve_field(
    field: str,
    candidates: list[_Candidate],
    patient_sources: list[Source],
    audit: _Audit,
    key: Callable[[object], Hashable] = _identity,
) -> tuple[object | None, bool]:
    """Pick one value for a field. Returns the value and whether sources conflicted."""
    if not candidates:
        return None, False

    ranked = sorted(candidates, key=lambda candidate: candidate.source.precedence)
    winner = ranked[0]
    losers = {
        key(c.value): c for c in reversed(ranked) if key(c.value) != key(winner.value)
    }  # one entry per distinct losing value

    if losers:
        rejected = "; ".join(f"{c.label} ({c.source})" for c in losers.values())
        audit.add(
            field,
            rejected,
            f"{winner.label} ({winner.source})",
            "demographics.conflict_resolved",
            Severity.CONFLICT,
            f"Sources disagree on {field}; kept the value from the most trusted source "
            f"({winner.source})",
        )
        return winner.value, True

    if winner.source != patient_sources[0]:
        audit.add(
            field,
            None,
            winner.label,
            "demographics.filled_from_other_source",
            Severity.INFO,
            f"{field} is missing from the {patient_sources[0]} source; "
            f"taken from the {winner.source} source",
        )
    return winner.value, False


def _flag_possible_duplicates(patients: list[CleanPatient]) -> None:
    """Flag, but never merge, patients who share a name and date of birth."""
    groups: dict[tuple[str, date], list[CleanPatient]] = defaultdict(list)
    for patient in patients:
        if patient.birth_date is not None and patient.family_name:
            groups[(patient.display_name.casefold(), patient.birth_date)].append(patient)

    for group in groups.values():
        if len(group) < 2:
            continue
        for patient in group:
            others = ", ".join(other.mrn for other in group if other is not patient)
            patient.audit.append(
                AuditEntry(
                    entity_id=patient.mrn,
                    field="mrn",
                    old_value=None,
                    new_value=None,
                    rule="patient.possible_duplicate",
                    severity=Severity.WARNING,
                    message=f"Same name and date of birth as {others}; "
                    "not merged because the MRNs differ. Needs human review.",
                )
            )


# --------------------------------------------------------------------------- #
# Encounters
# --------------------------------------------------------------------------- #


def _clean_encounters(
    raw_encounters: Sequence[RawEncounter], known_mrns: set[str], today: date
) -> list[CleanEncounter]:
    encounters: dict[str, CleanEncounter] = {}
    for raw in raw_encounters:
        mrn = normalize_mrn(raw.mrn).value
        if mrn is None or mrn not in known_mrns or raw.encounter_id is None:
            continue
        if raw.encounter_id in encounters:
            continue
        audit = _Audit(raw.encounter_id)
        start = parse_date(raw.start, today=today)
        end = parse_date(raw.end, today=today)
        audit.add_normalized("start", raw.start, start)
        audit.add_normalized("end", raw.end, end)
        encounters[raw.encounter_id] = CleanEncounter(
            encounter_id=raw.encounter_id,
            patient_mrn=mrn,
            encounter_class=normalize_encounter_class(raw.encounter_class),
            start=start.value,
            end=end.value,
            audit=audit.entries(),
        )
    return sorted(encounters.values(), key=lambda e: (e.patient_mrn, e.encounter_id))


# --------------------------------------------------------------------------- #
# Records
# --------------------------------------------------------------------------- #


def _clean_records(
    identified: Sequence[tuple[str, RawRecord]],
    known_encounters: set[tuple[str, str]],
    today: date,
) -> list[CleanRecord]:
    by_raw_content: dict[str, CleanRecord] = {}
    by_id: dict[str, CleanRecord] = {}

    for mrn, raw in identified:
        raw_key = raw.model_dump_json(exclude={"source_ref"})
        survivor = by_raw_content.get(raw_key)
        if survivor is not None:
            survivor.source_refs.append(raw.source_ref)
            survivor.audit.append(
                _record_entry(
                    survivor.record_id,
                    "record.exact_duplicate_dropped",
                    f"Exact duplicate at {raw.source_ref} was dropped",
                )
            )
            continue

        record = _clean_record(mrn, raw, known_encounters, today)
        existing = by_id.get(record.record_id)
        if existing is None:
            by_id[record.record_id] = record
            by_raw_content[raw_key] = record
            continue

        # Same patient, kind, date and text once case and spacing are ignored.
        kept, merged = sorted(
            (existing, record), key=lambda r: min(s.precedence for s in r.sources)
        )
        kept.sources = sorted({*kept.sources, *merged.sources}, key=lambda s: s.precedence)
        kept.source_refs = [*kept.source_refs, *merged.source_refs]
        kept.audit.append(
            _record_entry(
                kept.record_id,
                "record.near_duplicate_merged",
                f"Near-duplicate at {', '.join(merged.source_refs)} was merged into this record",
            )
        )
        by_id[kept.record_id] = kept
        by_raw_content[raw_key] = kept

    return sorted(
        by_id.values(),
        key=lambda r: (r.patient_mrn, r.record_date or date.min, r.record_id),
    )


def _record_entry(record_id: str, rule: str, message: str) -> AuditEntry:
    return AuditEntry(
        entity_id=record_id,
        field="record",
        old_value=None,
        new_value=None,
        rule=rule,
        severity=Severity.INFO,
        message=message,
    )


def _clean_record(
    mrn: str, raw: RawRecord, known_encounters: set[tuple[str, str]], today: date
) -> CleanRecord:
    audit = _Audit()
    kind = classify_kind(raw.kind, raw.title, _DEFAULT_KIND[raw.source])

    title = raw.title
    if title is None:
        title = kind.replace("_", " ").capitalize()
        audit.add(
            "title",
            None,
            title,
            "record.title_defaulted",
            Severity.WARNING,
            "Record has no title; a generic one was assigned",
        )

    record_date = parse_date(raw.record_date, today=today)
    audit.add_normalized("record_date", raw.record_date, record_date)
    if is_blank(raw.record_date):
        audit.add(
            "record_date", None, None, "record.date_missing", Severity.WARNING, "Record has no date"
        )

    assert raw.text is not None  # guaranteed by triage
    text = collapse_whitespace(raw.text)
    if text != raw.text:
        audit.add(
            "text",
            None,
            None,
            "text.whitespace_normalized",
            Severity.INFO,
            "Line breaks and repeated spaces were collapsed",
        )

    encounter_id = raw.encounter_id
    if encounter_id is not None and (mrn, encounter_id) not in known_encounters:
        audit.add(
            "encounter_id",
            encounter_id,
            None,
            "encounter.unknown_reference_removed",
            Severity.WARNING,
            f"Encounter {encounter_id} is not known for this patient; the link was removed",
        )
        encounter_id = None

    identity = "|".join(
        [
            mrn,
            kind,
            record_date.value.isoformat() if record_date.value else "",
            text_fingerprint(text),
        ]
    )
    record_id = "rec-" + hashlib.sha256(identity.encode()).hexdigest()[:16]

    return CleanRecord(
        record_id=record_id,
        patient_mrn=mrn,
        kind=kind,
        title=title,
        record_date=record_date.value,
        text=text,
        encounter_id=encounter_id,
        author=raw.author,
        abnormal=parse_abnormal_flag(raw.abnormal_flag),
        sources=[raw.source],
        source_refs=[raw.source_ref],
        audit=audit.entries(record_id),
    )
