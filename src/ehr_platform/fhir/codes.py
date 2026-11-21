"""Code systems and fixed codes used when mapping to FHIR R4."""

from __future__ import annotations

from ehr_platform.ingestion.models import EncounterClass, RecordKind

FHIR_VERSION = "4.0.1"

# Local naming systems. A real deployment would use the organization's OIDs.
MRN_SYSTEM = "urn:ehr-media-intelligence:mrn"
RECORD_ID_SYSTEM = "urn:ehr-media-intelligence:record-id"
ENCOUNTER_ID_SYSTEM = "urn:ehr-media-intelligence:encounter-id"
DATA_QUALITY_SYSTEM = "urn:ehr-media-intelligence:data-quality"
DEMOGRAPHIC_CONFLICT_TAG = "demographic-conflict"

LOINC = "http://loinc.org"
IDENTIFIER_TYPE_SYSTEM = "http://terminology.hl7.org/CodeSystem/v2-0203"
ENCOUNTER_CLASS_SYSTEM = "http://terminology.hl7.org/CodeSystem/v3-ActCode"
DIAGNOSTIC_SECTION_SYSTEM = "http://terminology.hl7.org/CodeSystem/v2-0074"
INTERPRETATION_SYSTEM = "http://terminology.hl7.org/CodeSystem/v3-ObservationInterpretation"
DOCUMENT_CATEGORY_SYSTEM = (
    "http://hl7.org/fhir/us/core/CodeSystem/us-core-documentreference-category"
)

# (code, display) pairs.
ENCOUNTER_CLASS_CODES: dict[EncounterClass, tuple[str, str]] = {
    EncounterClass.EMERGENCY: ("EMER", "emergency"),
    EncounterClass.INPATIENT: ("IMP", "inpatient encounter"),
    EncounterClass.OUTPATIENT: ("AMB", "ambulatory"),
}

# Document-level LOINC codes. Individual panels and studies are not coded here;
# the specific name is carried in ``code.text`` / ``description``.
DOCUMENT_TYPE_CODES: dict[RecordKind, tuple[str, str]] = {
    RecordKind.DISCHARGE_SUMMARY: ("18842-5", "Discharge summary"),
    RecordKind.PROGRESS_NOTE: ("11506-3", "Progress note"),
    RecordKind.SCANNED_NOTE: ("34109-9", "Note"),
}
REPORT_CODES: dict[RecordKind, tuple[str, str]] = {
    RecordKind.LAB_REPORT: ("11502-2", "Laboratory report"),
    RecordKind.IMAGING_REPORT: ("18748-4", "Diagnostic imaging study"),
}
REPORT_CATEGORIES: dict[RecordKind, tuple[str, str]] = {
    RecordKind.LAB_REPORT: ("LAB", "Laboratory"),
    RecordKind.IMAGING_REPORT: ("RAD", "Radiology"),
}

# Value sets with a *required* binding in R4. Neither FHIR library checks these.
REQUIRED_BINDINGS: dict[tuple[str, str], frozenset[str]] = {
    ("Patient", "gender"): frozenset({"male", "female", "other", "unknown"}),
    ("Encounter", "status"): frozenset(
        {
            "planned",
            "arrived",
            "triaged",
            "in-progress",
            "onleave",
            "finished",
            "cancelled",
            "entered-in-error",
            "unknown",
        }
    ),
    ("DocumentReference", "status"): frozenset({"current", "superseded", "entered-in-error"}),
    ("DiagnosticReport", "status"): frozenset(
        {
            "registered",
            "partial",
            "preliminary",
            "final",
            "amended",
            "corrected",
            "appended",
            "cancelled",
            "entered-in-error",
            "unknown",
        }
    ),
    ("Bundle", "type"): frozenset(
        {
            "document",
            "message",
            "transaction",
            "transaction-response",
            "batch",
            "batch-response",
            "history",
            "searchset",
            "collection",
        }
    ),
}
