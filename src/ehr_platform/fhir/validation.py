"""Validate Bundles against FHIR R4 and report every problem found.

Four independent checks run on each Bundle:

``fhir.resources``
    Pydantic v2 models (R4B subpackage). Catches wrong types, bad primitive
    formats, unknown elements and missing required elements.
``fhirclient``
    Models generated from FHIR 4.0.1, parsed in strict mode. This is the
    literal R4 check: an element that exists only in R4B would fail here.
``references``
    Every reference resolves to an entry in the same Bundle, each entry's
    ``fullUrl`` matches its resource ID, and every clinical resource points at
    the Bundle's single Patient.
``terminology``
    Codes with a *required* binding (statuses, gender, Bundle type), which
    neither library enforces.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterator
from typing import Any, Literal

from fhir.resources.R4B import get_fhir_model_class
from fhirclient.models.fhirabstractbase import FHIRValidationError
from fhirclient.models.fhirelementfactory import FHIRElementFactory
from pydantic import BaseModel, ValidationError

from ehr_platform.fhir.codes import FHIR_VERSION, REQUIRED_BINDINGS

Validator = Literal["fhir.resources", "fhirclient", "references", "terminology"]

_SUBJECT_REQUIRED = {"Encounter", "DocumentReference", "DiagnosticReport"}


class ValidationIssue(BaseModel):
    validator: Validator
    resource_type: str
    resource_id: str | None
    path: str
    message: str


class BundleValidation(BaseModel):
    patient_mrn: str
    bundle_id: str | None
    resource_counts: dict[str, int]
    issues: list[ValidationIssue]

    @property
    def is_valid(self) -> bool:
        return not self.issues


class ValidationReport(BaseModel):
    fhir_version: str = FHIR_VERSION
    bundle_count: int
    valid_bundle_count: int
    issue_count: int
    bundles: list[BundleValidation]

    @classmethod
    def from_bundles(cls, validations: list[BundleValidation]) -> ValidationReport:
        return cls(
            bundle_count=len(validations),
            valid_bundle_count=sum(v.is_valid for v in validations),
            issue_count=sum(len(v.issues) for v in validations),
            bundles=validations,
        )

    def render_text(self) -> str:
        """A short human-readable version of the report."""
        lines = [
            f"FHIR R4 ({self.fhir_version}) validation: "
            f"{self.valid_bundle_count}/{self.bundle_count} bundles valid, "
            f"{self.issue_count} issue(s)"
        ]
        for bundle in self.bundles:
            if bundle.is_valid:
                continue
            lines.append(f"  {bundle.patient_mrn}")
            for issue in bundle.issues:
                target = f"{issue.resource_type}/{issue.resource_id or '?'}"
                lines.append(f"    [{issue.validator}] {target} {issue.path}: {issue.message}")
        return "\n".join(lines)


def validate_bundle(patient_mrn: str, bundle: dict[str, Any]) -> BundleValidation:
    entries = [entry for entry in bundle.get("entry", []) if isinstance(entry, dict)]
    resources = [entry.get("resource") or {} for entry in entries]

    # The envelope is checked without its resources so that each problem is
    # reported once, against the resource it belongs to.
    envelope = {
        **bundle,
        "entry": [{k: v for k, v in e.items() if k != "resource"} for e in entries],
    }

    issues: list[ValidationIssue] = []
    for resource in [envelope, *resources]:
        issues += _check_with_fhir_resources(resource)
        issues += _check_with_fhirclient(resource)
        issues += _check_required_bindings(resource)
    issues += _check_references(entries)

    return BundleValidation(
        patient_mrn=patient_mrn,
        bundle_id=bundle.get("id"),
        resource_counts=dict(Counter(r.get("resourceType", "unknown") for r in resources)),
        issues=issues,
    )


def validate_bundles(bundles: dict[str, dict[str, Any]]) -> ValidationReport:
    return ValidationReport.from_bundles(
        [validate_bundle(mrn, bundle) for mrn, bundle in bundles.items()]
    )


# --------------------------------------------------------------------------- #
# Individual checks
# --------------------------------------------------------------------------- #


def _issue(
    validator: Validator, resource: dict[str, Any], path: str, message: str
) -> ValidationIssue:
    return ValidationIssue(
        validator=validator,
        resource_type=str(resource.get("resourceType", "unknown")),
        resource_id=resource.get("id"),
        path=path or "(resource)",
        message=message,
    )


def _check_with_fhir_resources(resource: dict[str, Any]) -> list[ValidationIssue]:
    try:
        model = get_fhir_model_class(str(resource.get("resourceType")))
    except (KeyError, ValueError):
        return [_issue("fhir.resources", resource, "resourceType", "Unknown resource type")]
    try:
        model.model_validate(resource)
    except ValidationError as error:
        return [
            _issue(
                "fhir.resources",
                resource,
                ".".join(str(part) for part in detail["loc"]),
                detail["msg"],
            )
            for detail in error.errors()
        ]
    return []


def _check_with_fhirclient(resource: dict[str, Any]) -> list[ValidationIssue]:
    try:
        FHIRElementFactory.instantiate(str(resource.get("resourceType")), resource)
    except FHIRValidationError as error:
        return [
            _issue("fhirclient", resource, path, message)
            for path, message in _flatten_fhirclient_errors(error)
        ]
    except Exception as error:  # unknown resource types raise library-specific errors
        return [_issue("fhirclient", resource, "resourceType", str(error))]
    return []


def _flatten_fhirclient_errors(
    error: BaseException, path: tuple[str, ...] = ()
) -> Iterator[tuple[str, str]]:
    """fhirclient nests errors by element; flatten them to (path, message) pairs."""
    if isinstance(error, FHIRValidationError):
        here = (*path, error.path) if error.path else path
        for nested in error.errors or []:
            yield from _flatten_fhirclient_errors(nested, here)
    else:
        yield ".".join(path), str(error).strip("'\"")


def _check_required_bindings(resource: dict[str, Any]) -> list[ValidationIssue]:
    resource_type = str(resource.get("resourceType"))
    issues = []
    for (bound_type, element), allowed in REQUIRED_BINDINGS.items():
        value = resource.get(element)
        if bound_type == resource_type and value is not None and value not in allowed:
            issues.append(
                _issue(
                    "terminology",
                    resource,
                    element,
                    f"'{value}' is not in the required value set",
                )
            )
    return issues


def _find_references(node: Any, path: str = "") -> Iterator[tuple[str, str]]:
    if isinstance(node, dict):
        reference = node.get("reference")
        if isinstance(reference, str):
            yield path, reference
        for key, value in node.items():
            yield from _find_references(value, f"{path}.{key}" if path else key)
    elif isinstance(node, list):
        for index, value in enumerate(node):
            yield from _find_references(value, f"{path}.{index}")


def _check_references(entries: list[dict[str, Any]]) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    full_urls = {entry.get("fullUrl") for entry in entries}
    patients = [e for e in entries if (e.get("resource") or {}).get("resourceType") == "Patient"]
    patient_url = patients[0].get("fullUrl") if len(patients) == 1 else None

    if len(patients) != 1:
        issues.append(
            ValidationIssue(
                validator="references",
                resource_type="Bundle",
                resource_id=None,
                path="entry",
                message=f"Expected exactly one Patient in the Bundle, found {len(patients)}",
            )
        )

    for entry in entries:
        resource = entry.get("resource") or {}
        if entry.get("fullUrl") != f"urn:uuid:{resource.get('id')}":
            issues.append(
                _issue("references", resource, "fullUrl", "fullUrl does not match the resource ID")
            )
        for path, reference in _find_references(resource):
            if reference not in full_urls:
                issues.append(
                    _issue(
                        "references",
                        resource,
                        path,
                        f"Reference '{reference}' does not resolve to an entry in this Bundle",
                    )
                )
        if resource.get("resourceType") in _SUBJECT_REQUIRED and patient_url is not None:
            subject = (resource.get("subject") or {}).get("reference")
            if subject != patient_url:
                issues.append(
                    _issue(
                        "references",
                        resource,
                        "subject",
                        "Resource is not linked to the Bundle's Patient",
                    )
                )
    return issues
