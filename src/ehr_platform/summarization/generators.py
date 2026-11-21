"""Summary generators: an LLM behind an OpenAI-compatible API, and a rule-based fallback."""

from __future__ import annotations

import re
from typing import Protocol

from openai import OpenAI, OpenAIError

from ehr_platform.fhir.reader import ClinicalDocument, PatientRecord
from ehr_platform.summarization.models import MediaRecord, SummaryContent
from ehr_platform.summarization.prompt import SYSTEM_PROMPT


class GenerationError(Exception):
    """The generator could not produce a usable summary."""


class SummaryGenerator(Protocol):
    """Anything that can turn a patient's records into summary content."""

    kind: str  # "llm" or "rule_based"
    model: str

    def generate(
        self, patient: PatientRecord, patient_text: str, extra_instruction: str | None = None
    ) -> SummaryContent: ...


class OpenAICompatibleGenerator:
    """Calls a chat completions API and parses the reply into ``SummaryContent``.

    Works with OpenAI and with any provider exposing the same API, such as
    Gemini's OpenAI-compatible endpoint. The response schema is sent as a
    structured-output format, so the reply is validated JSON rather than prose.
    """

    kind = "llm"

    def __init__(self, *, api_key: str, base_url: str, model: str, timeout: float) -> None:
        self.model = model
        self._client = OpenAI(api_key=api_key, base_url=base_url, timeout=timeout, max_retries=6)

    def generate(
        self, patient: PatientRecord, patient_text: str, extra_instruction: str | None = None
    ) -> SummaryContent:
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": patient_text},
        ]
        if extra_instruction:
            messages.append({"role": "user", "content": extra_instruction})
        try:
            completion = self._client.chat.completions.parse(
                model=self.model,
                messages=messages,  # type: ignore[arg-type]
                response_format=SummaryContent,
            )
        except OpenAIError as error:
            raise GenerationError(f"LLM request failed: {error}") from error

        content = completion.choices[0].message.parsed
        if content is None:
            raise GenerationError("LLM returned no structured content")
        return content


# --------------------------------------------------------------------------- #
# Rule-based fallback
# --------------------------------------------------------------------------- #

_DIAGNOSIS = re.compile(r"\bdiagnosis:\s*([^.]+)\.", re.IGNORECASE)
_NARRATIVE_CATEGORIES = ("Discharge summary", "Progress note", "Note")


def _first_sentence(text: str, max_words: int = 22) -> str:
    sentence = re.split(r"(?<=[.!?])\s", text.strip(), maxsplit=1)[0]
    words = sentence.split()
    return sentence if len(words) <= max_words else " ".join(words[:max_words]) + "..."


def _is_report(document: ClinicalDocument) -> bool:
    return document.resource_type == "DiagnosticReport"


class RuleBasedGenerator:
    """Extractive summary used when no LLM is configured.

    It only copies text out of the records, so it cannot hallucinate, but it
    is not AI-generated and is always marked low confidence.
    """

    kind = "rule_based"
    model = "rule-based-extractor"

    def generate(
        self, patient: PatientRecord, patient_text: str, extra_instruction: str | None = None
    ) -> SummaryContent:
        narratives = [d for d in patient.documents if d.category in _NARRATIVE_CATEGORIES]
        reports = [d for d in patient.documents if _is_report(d)]

        chief_concern = _first_sentence(narratives[-1].text) if narratives else "Not documented"
        diagnoses: list[str] = []
        for document in patient.documents:
            for match in _DIAGNOSIS.findall(document.text):
                diagnosis = match.strip()
                if diagnosis.lower() not in {d.lower() for d in diagnoses}:
                    diagnoses.append(diagnosis[0].upper() + diagnosis[1:])

        return SummaryContent(
            chief_concern=chief_concern,
            key_diagnoses=diagnoses[:5] or ["Not documented"],
            recent_media_records=[
                MediaRecord(
                    date=d.record_date.isoformat() if d.record_date else "undated",
                    type=d.title,
                    finding=_first_sentence(d.text, max_words=14),
                )
                for d in reports[:4]
            ],
            flagged_anomalies=[f"{d.title}: flagged abnormal" for d in reports if d.abnormal][:5],
            confidence="low",
        )
