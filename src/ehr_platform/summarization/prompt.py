"""Prompt and input rendering for clinical summaries.

Bump ``PROMPT_VERSION`` whenever the prompt or the rendering changes: it is
part of the cache key, so old summaries are regenerated.
"""

from __future__ import annotations

from datetime import date

from ehr_platform.fhir.reader import PatientRecord
from ehr_platform.summarization.models import WORD_LIMIT

PROMPT_VERSION = "v1"

SYSTEM_PROMPT = f"""\
You are a clinical documentation assistant. You summarize one patient's records for a \
clinician who needs to find the relevant facts in seconds.

Rules:
1. Use only facts stated in the records provided. Never infer a diagnosis, value or date \
that is not written there. If something is not documented, write "Not documented".
2. Do not give treatment recommendations or advice. Report what the records say.
3. Copy numbers, units and dates exactly as they appear in the records.
4. Be brief. The whole summary, across all fields, must be under {WORD_LIMIT} words. \
Aim for about 120.

Fields:
- chief_concern: one sentence on why the patient sought care.
- key_diagnoses: diagnoses the records state explicitly, most important first, at most 5.
- recent_media_records: the most recent imaging and laboratory records, newest first, at \
most 4. Use the record's date (YYYY-MM-DD, or "undated"), its type, and its key finding in \
one short phrase.
- flagged_anomalies: abnormal results, findings that need follow-up, and every item listed \
under "Data-quality warnings", at most 5. Use an empty list if there are none.
- confidence:
  "high"   - three or more records that agree, and no data-quality warnings;
  "medium" - few records, or a minor gap such as an undated record;
  "low"    - records conflict with each other, or there is a data-quality warning about \
the patient's identity or demographics.
"""

STRICTER_INSTRUCTION = (
    "Your previous answer was {words} words. Rewrite it in under {limit} words in total: "
    "shorten every phrase and drop the least important items."
)


def _age(birth_date: date | None, on: date | None) -> str:
    if birth_date is None or on is None:
        return "age unknown"
    years = on.year - birth_date.year - ((on.month, on.day) < (birth_date.month, birth_date.day))
    return f"{years} years old at latest record"


def render_patient(patient: PatientRecord, data_quality_notes: list[str]) -> str:
    """Render a patient's records as compact text for the model.

    Plain text is used instead of FHIR JSON: it carries the same clinical
    content in a fraction of the tokens.
    """
    born = patient.birth_date.isoformat() if patient.birth_date else "not documented"
    lines = [
        f"Patient: {patient.name} ({patient.mrn})",
        f"Sex: {patient.gender}. Date of birth: {born} "
        f"({_age(patient.birth_date, patient.latest_record_date)}).",
        "",
        "Data-quality warnings:",
    ]
    lines += [f"- {note}" for note in data_quality_notes] or ["- none"]
    lines += ["", f"Records ({len(patient.documents)}, newest first):"]
    for document in patient.documents:
        when = document.record_date.isoformat() if document.record_date else "undated"
        flag = {True: " [flagged ABNORMAL]", False: " [flagged normal]", None: ""}[
            document.abnormal
        ]
        lines += ["", f"[{when}] {document.category}: {document.title}{flag}", document.text]
    return "\n".join(lines)
