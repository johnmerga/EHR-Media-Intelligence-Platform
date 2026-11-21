"""Pure functions that turn one messy value into its canonical form.

Each function returns a :class:`Normalized` value that also says *which rule*
fired, so the caller can write an audit entry. A rule of ``None`` means the
input was already canonical (or absent) and nothing needs recording.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from typing import Generic, TypeVar

from ehr_platform.ingestion.models import EncounterClass, Gender, RecordKind, Severity

T = TypeVar("T")


@dataclass(frozen=True)
class Normalized(Generic[T]):
    value: T
    rule: str | None = None
    severity: Severity = Severity.INFO
    message: str = ""


def is_blank(raw: str | None) -> bool:
    return raw is None or not raw.strip()


# --------------------------------------------------------------------------- #
# MRN
# --------------------------------------------------------------------------- #

_MRN_PATTERN = re.compile(r"^(?:mrn)?[\s#:\-]*(\d{1,6})$", re.IGNORECASE)


def normalize_mrn(raw: str | None) -> Normalized[str | None]:
    """Canonical form is ``MRN-`` followed by six zero-padded digits."""
    if is_blank(raw):
        return Normalized(None)
    assert raw is not None
    match = _MRN_PATTERN.match(raw.strip())
    if match is None:
        return Normalized(
            None, "mrn.unrecognized", Severity.WARNING, f"'{raw}' is not a recognizable MRN"
        )
    canonical = f"MRN-{int(match.group(1)):06d}"
    if canonical == raw:
        return Normalized(canonical)
    return Normalized(canonical, "mrn.canonicalized", message="MRN rewritten in canonical format")


# --------------------------------------------------------------------------- #
# Dates
# --------------------------------------------------------------------------- #

_MONTHS = {
    name: number
    for number, names in enumerate(
        [
            ("jan", "january"),
            ("feb", "february"),
            ("mar", "march"),
            ("apr", "april"),
            ("may",),
            ("jun", "june"),
            ("jul", "july"),
            ("aug", "august"),
            ("sep", "sept", "september"),
            ("oct", "october"),
            ("nov", "november"),
            ("dec", "december"),
        ],
        start=1,
    )
    for name in names
}

_ISO = re.compile(r"^(\d{4})-(\d{2})-(\d{2})(?:[T ].*)?$")
_COMPACT = re.compile(r"^(\d{4})(\d{2})(\d{2})$")
_SLASHED = re.compile(r"^(\d{1,2})/(\d{1,2})/(\d{4})$")
_DAY_MONTH_NAME = re.compile(r"^(\d{1,2})[-\s]([A-Za-z]+)[-\s](\d{2}|\d{4})$")
_MONTH_NAME_DAY = re.compile(r"^([A-Za-z]+)\s+(\d{1,2}),?\s+(\d{4})$")


def _build(year: int, month: int, day: int) -> date | None:
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _unparseable(raw: str) -> Normalized[date | None]:
    return Normalized(
        None,
        "date.unparseable",
        Severity.WARNING,
        f"'{raw}' is not a valid date; the value was cleared",
    )


def parse_date(raw: str | None, *, today: date) -> Normalized[date | None]:
    """Parse the date formats seen in the sources into a ``date``.

    ``today`` anchors two-digit years: ``14-Mar-62`` cannot be in the future,
    so it is read as 1962.
    """
    if is_blank(raw):
        return Normalized(None)
    assert raw is not None
    text = raw.strip()

    if match := _ISO.match(text):
        year, month, day = (int(part) for part in match.groups())
        parsed = _build(year, month, day)
        if parsed is None:
            return _unparseable(text)
        if len(text) == 10:
            return Normalized(parsed)
        return Normalized(parsed, "date.reformatted", message="Time component removed")

    if match := _COMPACT.match(text):
        year, month, day = (int(part) for part in match.groups())
        parsed = _build(year, month, day)
        if parsed is None:
            return _unparseable(text)
        return Normalized(parsed, "date.reformatted", message="Compact YYYYMMDD date rewritten")

    if match := _SLASHED.match(text):
        first, second, year = (int(part) for part in match.groups())
        if first > 12 >= second:
            parsed = _build(year, second, first)
            if parsed is None:
                return _unparseable(text)
            return Normalized(
                parsed, "date.reformatted", message="Day-first date rewritten (day is above 12)"
            )
        parsed = _build(year, first, second)
        if parsed is None:
            return _unparseable(text)
        if second <= 12 and first != second:
            return Normalized(
                parsed,
                "date.ambiguous_month_first",
                Severity.INFO,
                "Date is ambiguous; read as month/day/year by assumption (US convention)",
            )
        return Normalized(parsed, "date.reformatted", message="Month-first date rewritten")

    if match := _DAY_MONTH_NAME.match(text):
        named_month = _MONTHS.get(match.group(2).lower())
        if named_month is None:
            return _unparseable(text)
        month, day, year_text = named_month, int(match.group(1)), match.group(3)
        if len(year_text) == 4:
            parsed = _build(int(year_text), month, day)
            if parsed is None:
                return _unparseable(text)
            return Normalized(parsed, "date.reformatted", message="Named-month date rewritten")
        parsed = _build(2000 + int(year_text), month, day)
        if parsed is not None and parsed > today:
            parsed = _build(1900 + int(year_text), month, day)
        if parsed is None:
            return _unparseable(text)
        return Normalized(
            parsed,
            "date.two_digit_year",
            Severity.WARNING,
            f"Two-digit year expanded to {parsed.year} (the latest year that is not in the future)",
        )

    if match := _MONTH_NAME_DAY.match(text):
        named_month = _MONTHS.get(match.group(1).lower())
        if named_month is None:
            return _unparseable(text)
        parsed = _build(int(match.group(3)), named_month, int(match.group(2)))
        if parsed is None:
            return _unparseable(text)
        return Normalized(parsed, "date.reformatted", message="Named-month date rewritten")

    return _unparseable(text)


# --------------------------------------------------------------------------- #
# Gender
# --------------------------------------------------------------------------- #

_GENDER_CODES = {
    "m": Gender.MALE,
    "male": Gender.MALE,
    "man": Gender.MALE,
    "f": Gender.FEMALE,
    "female": Gender.FEMALE,
    "woman": Gender.FEMALE,
    "o": Gender.OTHER,
    "other": Gender.OTHER,
    "u": Gender.UNKNOWN,
    "unk": Gender.UNKNOWN,
    "unknown": Gender.UNKNOWN,
}


def normalize_gender(raw: str | None) -> Normalized[Gender | None]:
    """Map source sex codes to FHIR administrative gender. Blank stays ``None``."""
    if is_blank(raw):
        return Normalized(None)
    assert raw is not None
    gender = _GENDER_CODES.get(raw.strip().lower())
    if gender is None:
        return Normalized(
            Gender.UNKNOWN,
            "gender.unrecognized",
            Severity.WARNING,
            f"'{raw}' is not a known sex code; recorded as unknown",
        )
    if raw == gender.value:
        return Normalized(gender)
    return Normalized(gender, "gender.mapped", message="Sex code mapped to FHIR gender")


# --------------------------------------------------------------------------- #
# Names
# --------------------------------------------------------------------------- #


def _capitalize(word: str) -> str:
    """Title-case one name part, keeping apostrophes and hyphens: O'CONNOR -> O'Connor."""
    return re.sub(r"[A-Za-z]+", lambda m: m.group(0).capitalize(), word)


def normalize_name(raw: str | None) -> Normalized[tuple[str, str] | None]:
    """Split a full name into ``(given, family)``.

    Accepts ``"Family, Given"`` and ``"Given Family"``. Names written entirely
    in one case are title-cased.
    """
    if is_blank(raw):
        return Normalized(None)
    assert raw is not None
    text = " ".join(raw.split())
    if "," in text:
        family, _, given = (part.strip() for part in text.partition(","))
    elif " " in text:
        given, _, family = text.rpartition(" ")
    else:
        given, family = "", text
    if text.isupper() or text.islower():
        given, family = _capitalize(given), _capitalize(family)
    if f"{given} {family}".strip() == raw:
        return Normalized((given, family))
    return Normalized(
        (given, family), "name.normalized", message="Name reordered or re-cased to 'Given Family'"
    )


# --------------------------------------------------------------------------- #
# Record attributes
# --------------------------------------------------------------------------- #

_KIND_KEYWORDS: list[tuple[str, RecordKind]] = [
    ("discharge", RecordKind.DISCHARGE_SUMMARY),
    ("imaging", RecordKind.IMAGING_REPORT),
    ("radiology", RecordKind.IMAGING_REPORT),
    ("lab", RecordKind.LAB_REPORT),
    ("progress", RecordKind.PROGRESS_NOTE),
]


def classify_kind(hint: str | None, title: str | None, default: RecordKind) -> RecordKind:
    """Decide the record kind from the source's category, then its title."""
    for candidate in (hint, title):
        lowered = (candidate or "").lower()
        for keyword, kind in _KIND_KEYWORDS:
            if keyword in lowered:
                return kind
    return default


_ABNORMAL_FLAGS = {"h": True, "l": True, "a": True, "hh": True, "ll": True, "n": False}


def parse_abnormal_flag(raw: str | None) -> bool | None:
    """HL7-style lab flags: H/L/A are abnormal, N is normal, anything else is unknown."""
    if is_blank(raw):
        return None
    assert raw is not None
    return _ABNORMAL_FLAGS.get(raw.strip().lower())


_ENCOUNTER_CLASSES = {
    "emergency": EncounterClass.EMERGENCY,
    "ed": EncounterClass.EMERGENCY,
    "inpatient": EncounterClass.INPATIENT,
    "outpatient": EncounterClass.OUTPATIENT,
    "ambulatory": EncounterClass.OUTPATIENT,
}


def normalize_encounter_class(raw: str | None) -> EncounterClass:
    return _ENCOUNTER_CLASSES.get((raw or "").strip().lower(), EncounterClass.OUTPATIENT)


def collapse_whitespace(text: str) -> str:
    return " ".join(text.split())


def text_fingerprint(text: str) -> str:
    """Case- and whitespace-insensitive form used to spot near-duplicate records."""
    return collapse_whitespace(text).lower()
