"""Unit tests for the single-value normalizers."""

from __future__ import annotations

from datetime import date

import pytest

from ehr_platform.ingestion.models import Gender, RecordKind, Severity
from ehr_platform.ingestion.normalizers import (
    classify_kind,
    normalize_gender,
    normalize_mrn,
    normalize_name,
    parse_abnormal_flag,
    parse_date,
)
from tests.conftest import TODAY


@pytest.mark.parametrize(
    ("raw", "expected", "rule"),
    [
        ("1962-03-14", date(1962, 3, 14), None),
        ("2025-01-13T08:30:00Z", date(2025, 1, 13), "date.reformatted"),
        ("20250310", date(2025, 3, 10), "date.reformatted"),
        ("03/14/1962", date(1962, 3, 14), "date.reformatted"),
        ("19/12/1950", date(1950, 12, 19), "date.reformatted"),
        ("14-Mar-1962", date(1962, 3, 14), "date.reformatted"),
        ("March 3, 1972", date(1972, 3, 3), "date.reformatted"),
        ("11/02/1978", date(1978, 11, 2), "date.ambiguous_month_first"),
    ],
)
def test_parse_date_accepts_every_source_format(raw: str, expected: date, rule: str | None) -> None:
    result = parse_date(raw, today=TODAY)

    assert result.value == expected
    assert result.rule == rule


def test_two_digit_year_is_never_read_as_a_future_date() -> None:
    result = parse_date("14-Mar-62", today=TODAY)

    assert result.value == date(1962, 3, 14)
    assert result.rule == "date.two_digit_year"
    assert result.severity is Severity.WARNING


def test_two_digit_year_in_the_recent_past_stays_in_this_century() -> None:
    assert parse_date("05-Jan-24", today=TODAY).value == date(2024, 1, 5)


@pytest.mark.parametrize("raw", ["02/30/2025", "2025-13-01", "31-Foo-2024", "not a date"])
def test_impossible_dates_are_cleared_with_a_warning(raw: str) -> None:
    result = parse_date(raw, today=TODAY)

    assert result.value is None
    assert result.rule == "date.unparseable"
    assert result.severity is Severity.WARNING


@pytest.mark.parametrize("raw", [None, "", "   "])
def test_blank_dates_are_missing_not_errors(raw: str | None) -> None:
    result = parse_date(raw, today=TODAY)

    assert result.value is None
    assert result.rule is None


@pytest.mark.parametrize(
    "raw", ["1234", "001234", "mrn 001234", "MRN1234", "mrn#1234", "MRN: 1234"]
)
def test_mrn_variants_share_one_canonical_form(raw: str) -> None:
    result = normalize_mrn(raw)

    assert result.value == "MRN-001234"
    assert result.rule == "mrn.canonicalized"


def test_canonical_mrn_is_left_alone() -> None:
    assert normalize_mrn("MRN-001234").rule is None


@pytest.mark.parametrize("raw", ["ABC-12", "12345678", "MRN-"])
def test_unrecognizable_mrn_yields_no_identifier(raw: str) -> None:
    result = normalize_mrn(raw)

    assert result.value is None
    assert result.rule == "mrn.unrecognized"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("M", Gender.MALE),
        ("male", Gender.MALE),
        ("F", Gender.FEMALE),
        ("FEMALE", Gender.FEMALE),
        ("f", Gender.FEMALE),
        ("U", Gender.UNKNOWN),
        ("other", Gender.OTHER),
    ],
)
def test_sex_codes_map_to_fhir_gender(raw: str, expected: Gender) -> None:
    assert normalize_gender(raw).value is expected


def test_blank_sex_is_missing_and_unknown_code_is_flagged() -> None:
    assert normalize_gender("").value is None
    unrecognized = normalize_gender("X9")
    assert unrecognized.value is Gender.UNKNOWN
    assert unrecognized.severity is Severity.WARNING


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Robert Hayes", ("Robert", "Hayes")),
        ("Hayes, Robert", ("Robert", "Hayes")),
        ("CHEN, WILLIAM", ("William", "Chen")),
        ("O'CONNOR, JAMES", ("James", "O'Connor")),
        ("Mary Ann Smith", ("Mary Ann", "Smith")),
    ],
)
def test_names_are_split_into_given_and_family(raw: str, expected: tuple[str, str]) -> None:
    assert normalize_name(raw).value == expected


def test_record_kind_comes_from_category_then_title() -> None:
    assert (
        classify_kind("Imaging", "CT head", RecordKind.PROGRESS_NOTE) is RecordKind.IMAGING_REPORT
    )
    assert (
        classify_kind(None, "Discharge summary", RecordKind.SCANNED_NOTE)
        is RecordKind.DISCHARGE_SUMMARY
    )
    assert classify_kind(None, "Dietitian note", RecordKind.SCANNED_NOTE) is RecordKind.SCANNED_NOTE


def test_lab_flags() -> None:
    assert parse_abnormal_flag("H") is True
    assert parse_abnormal_flag("n") is False
    assert parse_abnormal_flag("") is None
