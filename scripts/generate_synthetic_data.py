"""Generate the synthetic EHR dataset used by the pipeline.

Every patient here is fictional. The clinical stories are hand-written so that
summaries and searches have something coherent to find; the data-quality
defects are injected on purpose and recorded in ``synthetic_manifest.json`` so tests can
assert that the cleaning stage caught each one.

The script is deterministic: running it twice produces byte-identical files.

Usage:
    python scripts/generate_synthetic_data.py [output_dir]
"""

from __future__ import annotations

import csv
import json
import sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"


# --------------------------------------------------------------------------- #
# Canonical (clean) description of the dataset
# --------------------------------------------------------------------------- #


@dataclass
class Record:
    """One clinical record, described cleanly, plus how it should be corrupted."""

    source: str  # "json" | "csv" | "txt"
    kind: str  # imaging | discharge_summary | progress_note | lab | scanned_note
    title: str
    on: date
    text: str
    encounter: str | None = None
    author: str = ""
    flag: str = ""  # lab abnormal flag: H, L, A, N
    raw: dict[str, str] = field(default_factory=dict)  # raw-value overrides
    defects: list[tuple[str, str]] = field(default_factory=list)  # (rule, note)
    repeat: int = 1  # >1 writes exact duplicates


@dataclass
class Patient:
    mrn: int
    first: str
    last: str
    dob: date | None
    sex: str  # canonical: male | female | unknown
    encounters: list[tuple[str, str, date, date]]  # id, class, start, end
    records: list[Record]
    raw: dict[str, dict[str, str]] = field(default_factory=dict)  # per-source overrides
    defects: list[tuple[str, str]] = field(default_factory=list)
    anomalies: list[str] = field(default_factory=list)  # terms a good summary flags


def d(year: int, month: int, day: int) -> date:
    return date(year, month, day)


PATIENTS: list[Patient] = [
    Patient(
        mrn=1234,
        first="Robert",
        last="Hayes",
        dob=d(1962, 3, 14),
        sex="male",
        encounters=[
            ("ENC-10001", "emergency", d(2025, 1, 8), d(2025, 1, 11)),
            ("ENC-10002", "outpatient", d(2025, 2, 12), d(2025, 2, 12)),
        ],
        raw={"csv": {"mrn": "1234"}, "txt": {"mrn": "mrn 001234", "dob": "14-Mar-62"}},
        defects=[
            ("mrn.canonicalized", "MRN written as '1234' and 'mrn 001234'"),
            ("date.two_digit_year", "DOB written as 14-Mar-62"),
        ],
        anomalies=["troponin"],
        records=[
            Record(
                "csv",
                "lab",
                "Troponin I, high sensitivity",
                d(2025, 1, 8),
                "Troponin I 842 ng/L (reference < 34 ng/L). Repeat at 3 hours 1,310 ng/L. "
                "Markedly elevated and rising, consistent with acute myocardial injury.",
                "ENC-10001",
                "Dr. Priya Raman",
                flag="H",
            ),
            Record(
                "json",
                "imaging",
                "Transthoracic echocardiogram",
                d(2025, 1, 9),
                "Left ventricular ejection fraction 45%. Hypokinesis of the inferior wall. "
                "No significant valvular disease. No pericardial effusion.",
                "ENC-10001",
                "Dr. Alan Whitfield",
            ),
            Record(
                "json",
                "discharge_summary",
                "Discharge summary",
                d(2025, 1, 11),
                "62-year-old man presented with two hours of crushing substernal chest pain "
                "radiating to the left arm. ECG showed ST depression in the inferior leads and "
                "troponin was elevated. Diagnosis: non-ST-elevation myocardial infarction. "
                "Coronary angiography showed 90% stenosis of the right coronary artery, "
                "treated with a drug-eluting stent. Discharged on aspirin, ticagrelor, "
                "atorvastatin and metoprolol.",
                "ENC-10001",
                "Dr. Priya Raman",
            ),
            Record(
                "txt",
                "scanned_note",
                "Cardiology follow-up note",
                d(2025, 2, 12),
                "Seen one month after NSTEMI with stent to the right coronary artery. "
                "No recurrent chest pain. Tolerating dual antiplatelet therapy. Blood pressure "
                "128/78. Plan: continue current medications, cardiac rehabilitation referral, "
                "repeat echocardiogram in three months.",
                "ENC-10002",
                "Dr. Alan Whitfield",
            ),
        ],
    ),
    Patient(
        mrn=1235,
        first="Maria",
        last="Gonzalez",
        dob=d(1978, 11, 2),
        sex="female",
        encounters=[
            ("ENC-10003", "inpatient", d(2025, 2, 3), d(2025, 2, 6)),
            ("ENC-10004", "outpatient", d(2025, 3, 17), d(2025, 3, 17)),
        ],
        raw={"json": {"sex": "F"}, "csv": {"dob": "11/02/1978"}},
        defects=[
            ("date.ambiguous_month_first", "DOB 11/02/1978 could be 2 Nov or 11 Feb"),
            ("gender.mapped", "sex written as 'F'"),
        ],
        anomalies=["consolidation", "white blood cell"],
        records=[
            Record(
                "json",
                "imaging",
                "Chest X-ray, two views",
                d(2025, 2, 3),
                "Dense consolidation in the right lower lobe with air bronchograms. "
                "Small right pleural effusion. Heart size normal. Findings consistent with "
                "lobar pneumonia.",
                "ENC-10003",
                "Dr. Helen Park",
            ),
            Record(
                "csv",
                "lab",
                "Complete blood count",
                d(2025, 2, 3),
                "White blood cell count 17.8 x10^9/L (reference 4.0-11.0), neutrophils 86%. "
                "Hemoglobin 13.1 g/dL. Platelets 310 x10^9/L. Leukocytosis with left shift.",
                "ENC-10003",
                "Dr. Samuel Ortiz",
                flag="H",
                repeat=2,
                defects=[("record.exact_duplicate_dropped", "CSV row appears twice")],
            ),
            Record(
                "json",
                "discharge_summary",
                "Discharge summary",
                d(2025, 2, 6),
                "46-year-old woman admitted with fever, productive cough and pleuritic chest "
                "pain for four days. Chest X-ray showed right lower lobe consolidation. "
                "Diagnosis: community-acquired pneumonia. Treated with intravenous ceftriaxone "
                "and azithromycin, switched to oral amoxicillin-clavulanate. Afebrile for 48 "
                "hours at discharge.",
                "ENC-10003",
                "Dr. Samuel Ortiz",
            ),
            Record(
                "json",
                "imaging",
                "Chest X-ray, follow-up",
                d(2025, 3, 17),
                "Interval resolution of the right lower lobe consolidation. No pleural "
                "effusion. No new focal opacity. Lungs are clear.",
                "ENC-10004",
                "Dr. Helen Park",
            ),
        ],
    ),
    Patient(
        mrn=1236,
        first="James",
        last="O'Connor",
        dob=d(1955, 7, 21),
        sex="male",
        encounters=[
            ("ENC-10005", "outpatient", d(2025, 1, 20), d(2025, 1, 20)),
            ("ENC-10006", "outpatient", d(2025, 4, 2), d(2025, 4, 2)),
        ],
        raw={"json": {"sex": "male"}, "csv": {"dob": "07/12/1955"}},
        defects=[
            (
                "demographics.conflict_resolved",
                "DOB is 1955-07-21 in the JSON export but 07/12/1955 in the lab CSV",
            )
        ],
        anomalies=["hba1c"],
        records=[
            Record(
                "csv",
                "lab",
                "Hemoglobin A1c",
                d(2025, 1, 20),
                "HbA1c 10.2% (target < 7.0%). Estimated average glucose 246 mg/dL. "
                "Poor glycemic control.",
                "ENC-10005",
                "Dr. Grace Okafor",
                flag="H",
            ),
            Record(
                "csv",
                "lab",
                "Lipid panel",
                d(2025, 1, 20),
                "Total cholesterol 238 mg/dL, LDL 156 mg/dL, HDL 38 mg/dL, triglycerides "
                "220 mg/dL. LDL above goal for a patient with diabetes.",
                "ENC-10005",
                "Dr. Grace Okafor",
                flag="H",
            ),
            Record(
                "json",
                "progress_note",
                "Primary care progress note",
                d(2025, 1, 20),
                "Type 2 diabetes mellitus for twelve years, poorly controlled. Reports "
                "increased thirst and nocturia. Missed metformin doses frequently. Numbness "
                "in both feet with reduced monofilament sensation, consistent with peripheral "
                "neuropathy. Plan: restart metformin, add empagliflozin, start atorvastatin, "
                "diabetes education referral.",
                "ENC-10005",
                "Dr. Grace Okafor",
            ),
            Record(
                "txt",
                "scanned_note",
                "Diabetic retinal examination",
                d(2025, 4, 2),
                "Dilated fundus examination. Right eye: scattered microaneurysms and dot "
                "hemorrhages. Left eye: microaneurysms, no macular edema. Impression: mild "
                "non-proliferative diabetic retinopathy in both eyes. Repeat examination in "
                "twelve months.",
                "ENC-10006",
                "Dr. Naomi Feld",
            ),
        ],
    ),
    Patient(
        mrn=1237,
        first="Aisha",
        last="Khan",
        dob=d(1990, 1, 30),
        sex="female",
        encounters=[("ENC-10007", "outpatient", d(2025, 3, 5), d(2025, 3, 5))],
        raw={"json": {"sex": ""}, "csv": {"sex": "Female", "mrn": "MRN1237"}},
        defects=[
            (
                "demographics.filled_from_other_source",
                "sex is blank in the JSON export and 'Female' in the lab CSV",
            )
        ],
        anomalies=["hemoglobin", "ferritin"],
        records=[
            Record(
                "csv",
                "lab",
                "Complete blood count",
                d(2025, 3, 5),
                "Hemoglobin 8.9 g/dL (reference 12.0-15.5). Mean corpuscular volume 71 fL. "
                "White blood cell count 6.2 x10^9/L. Platelets 402 x10^9/L. "
                "Microcytic anemia.",
                "ENC-10007",
                "Dr. Grace Okafor",
                flag="L",
            ),
            Record(
                "csv",
                "lab",
                "Iron studies",
                d(2025, 3, 5),
                "Ferritin 6 ng/mL (reference 15-150). Serum iron 22 mcg/dL. Transferrin "
                "saturation 5%. Findings consistent with iron deficiency.",
                "ENC-10007",
                "Dr. Grace Okafor",
                flag="L",
            ),
            Record(
                "json",
                "progress_note",
                "Primary care progress note",
                d(2025, 3, 5),
                "35-year-old woman with three months of fatigue, exertional dyspnea and heavy "
                "menstrual bleeding. Conjunctival pallor on examination. Diagnosis: iron "
                "deficiency anemia secondary to menorrhagia. Plan: oral ferrous sulfate, "
                "gynecology referral, repeat blood count in six weeks.",
                "ENC-10007",
                "Dr. Grace Okafor",
            ),
        ],
    ),
    Patient(
        mrn=1238,
        first="William",
        last="Chen",
        dob=d(1948, 9, 9),
        sex="male",
        encounters=[
            ("ENC-10008", "emergency", d(2025, 2, 20), d(2025, 2, 27)),
            ("ENC-10009", "outpatient", d(2025, 3, 25), d(2025, 3, 25)),
        ],
        raw={"json": {"name": "CHEN, WILLIAM"}},
        defects=[("name.normalized", "name written as 'CHEN, WILLIAM'")],
        anomalies=["infarct"],
        records=[
            Record(
                "json",
                "imaging",
                "CT head without contrast",
                d(2025, 2, 20),
                "No acute intracranial hemorrhage. Subtle loss of grey-white differentiation "
                "in the left insular cortex. Hyperdense left middle cerebral artery sign. "
                "Findings concerning for early left MCA territory ischemia.",
                "ENC-10008",
                "Dr. Helen Park",
            ),
            Record(
                "json",
                "imaging",
                "MRI brain with diffusion",
                d(2025, 2, 21),
                "Restricted diffusion in the left middle cerebral artery territory involving "
                "the insula and frontal operculum, consistent with acute infarct. No "
                "hemorrhagic transformation. Chronic small vessel ischemic changes.",
                "ENC-10008",
                "Dr. Helen Park",
            ),
            Record(
                "json",
                "discharge_summary",
                "Discharge summary",
                d(2025, 2, 27),
                "76-year-old man presented with sudden right-sided weakness and expressive "
                "aphasia. Received intravenous thrombolysis within the treatment window. "
                "Diagnosis: acute ischemic stroke, left middle cerebral artery territory. "
                "New atrial fibrillation found on telemetry; started apixaban. Discharged to "
                "inpatient rehabilitation with residual mild right arm weakness.",
                "ENC-10008",
                "Dr. Marcus Bell",
            ),
            # The same discharge summary was also scanned from paper.
            Record(
                "txt",
                "discharge_summary",
                "Discharge summary",
                d(2025, 2, 27),
                "76-year-old man presented with sudden right-sided weakness and expressive "
                "aphasia.  Received intravenous thrombolysis within the treatment window.\n"
                "DIAGNOSIS: acute ischemic stroke, left middle cerebral artery territory. "
                "New atrial fibrillation found on telemetry; started apixaban.   Discharged to "
                "inpatient rehabilitation with residual mild right arm weakness.",
                "ENC-10008",
                "Dr. Marcus Bell",
                defects=[
                    (
                        "record.near_duplicate_merged",
                        "discharge summary exists in the JSON export and as a scan",
                    )
                ],
            ),
            Record(
                "txt",
                "scanned_note",
                "Stroke rehabilitation note",
                d(2025, 3, 25),
                "Four weeks after left MCA stroke. Right arm strength improved to 4+/5. "
                "Speech fluent with occasional word-finding difficulty. Walking "
                "independently. Continue outpatient physiotherapy and speech therapy. "
                "Anticoagulation with apixaban continues for atrial fibrillation.",
                "ENC-10009",
                "Dr. Leila Haddad",
            ),
        ],
    ),
    Patient(
        mrn=1239,
        first="Linda",
        last="Baker",
        dob=d(1969, 5, 17),
        sex="unknown",
        encounters=[("ENC-10010", "outpatient", d(2025, 4, 8), d(2025, 4, 8))],
        raw={"json": {"sex": "U"}},
        defects=[("gender.mapped", "sex written as 'U'")],
        anomalies=["bi-rads", "carcinoma"],
        records=[
            Record(
                "json",
                "imaging",
                "Diagnostic mammogram, bilateral",
                d(2025, 4, 8),
                "Irregular spiculated mass in the upper outer quadrant of the left breast "
                "measuring 1.8 cm, with associated pleomorphic microcalcifications. Right "
                "breast unremarkable. BI-RADS category 4C: high suspicion for malignancy. "
                "Tissue sampling recommended.",
                "ENC-10010",
                "Dr. Ingrid Solberg",
            ),
            Record(
                "json",
                "imaging",
                "Breast ultrasound, left",
                d(2025, 4, 8),
                "Hypoechoic irregular mass at the 2 o'clock position, 1.7 x 1.4 cm, with "
                "posterior acoustic shadowing. No suspicious axillary lymph nodes. "
                "Ultrasound-guided core biopsy advised.",
                "ENC-10010",
                "Dr. Ingrid Solberg",
            ),
            Record(
                "txt",
                "scanned_note",
                "Surgical pathology report",
                d(2025, 4, 15),
                "Left breast core biopsy, 2 o'clock. Invasive ductal carcinoma, grade 2. "
                "Estrogen receptor positive, progesterone receptor positive, HER2 negative. "
                "Referred to the breast multidisciplinary team.",
                None,
                "Dr. Victor Adeyemi",
                raw={"date": "02/30/2025"},
                defects=[("date.unparseable", "date of service is 02/30/2025")],
            ),
        ],
    ),
    Patient(
        mrn=1240,
        first="David",
        last="Nguyen",
        dob=d(1983, 12, 5),
        sex="male",
        encounters=[("ENC-10011", "emergency", d(2025, 5, 2), d(2025, 5, 4))],
        raw={"json": {"mrn": "mrn#1240"}},
        defects=[("mrn.canonicalized", "MRN written as 'mrn#1240'")],
        anomalies=["appendicitis"],
        records=[
            Record(
                "json",
                "imaging",
                "CT abdomen and pelvis with contrast",
                d(2025, 5, 2),
                "Dilated appendix measuring 13 mm with wall enhancement and periappendiceal "
                "fat stranding. Appendicolith at the base. No abscess or free air. Findings "
                "consistent with acute uncomplicated appendicitis.",
                "ENC-10011",
                "Dr. Helen Park",
                repeat=2,
                defects=[("record.exact_duplicate_dropped", "JSON document appears twice")],
            ),
            Record(
                "csv",
                "lab",
                "Complete blood count",
                d(2025, 5, 2),
                "White blood cell count 15.4 x10^9/L (reference 4.0-11.0), neutrophils 82%. "
                "Hemoglobin 14.8 g/dL. Platelets 265 x10^9/L.",
                "ENC-10011",
                "Dr. Marcus Bell",
                flag="H",
            ),
            Record(
                "json",
                "discharge_summary",
                "Discharge summary",
                d(2025, 5, 4),
                "41-year-old man with 18 hours of periumbilical pain migrating to the right "
                "lower quadrant, nausea and low-grade fever. CT confirmed acute appendicitis. "
                "Underwent laparoscopic appendectomy without complication. Tolerating diet, "
                "pain controlled with oral analgesia. Wound review in two weeks.",
                "ENC-10011",
                "Dr. Yusuf Demir",
            ),
        ],
    ),
    Patient(
        mrn=1241,
        first="Patricia",
        last="Moore",
        dob=d(1941, 2, 27),
        sex="female",
        encounters=[("ENC-10012", "inpatient", d(2025, 3, 10), d(2025, 3, 15))],
        raw={"txt": {"dob": "27-Feb-1914"}},
        defects=[
            (
                "demographics.conflict_resolved",
                "DOB is 1941-02-27 in the JSON export but 27-Feb-1914 on a scanned note",
            )
        ],
        anomalies=["bnp", "ejection fraction"],
        records=[
            Record(
                "csv",
                "lab",
                "B-type natriuretic peptide",
                d(2025, 3, 10),
                "BNP 1,840 pg/mL (reference < 100). Markedly elevated, supporting acute "
                "decompensated heart failure.",
                "ENC-10012",
                "Dr. Priya Raman",
                flag="H",
            ),
            Record(
                "json",
                "imaging",
                "Chest X-ray, portable",
                d(2025, 3, 10),
                "Cardiomegaly. Bilateral perihilar interstitial opacities with Kerley B "
                "lines and small bilateral pleural effusions. Findings consistent with "
                "pulmonary edema.",
                "ENC-10012",
                "Dr. Helen Park",
            ),
            Record(
                "json",
                "imaging",
                "Transthoracic echocardiogram",
                d(2025, 3, 11),
                "Severely reduced left ventricular systolic function, ejection fraction 30%. "
                "Global hypokinesis. Moderate mitral regurgitation. Dilated left atrium.",
                "ENC-10012",
                "Dr. Alan Whitfield",
            ),
            Record(
                "txt",
                "discharge_summary",
                "Discharge summary",
                d(2025, 3, 15),
                "84-year-old woman admitted with one week of worsening breathlessness, "
                "orthopnea and leg swelling. Diagnosis: acute decompensated heart failure "
                "with reduced ejection fraction. Treated with intravenous furosemide with "
                "4.5 kg weight loss. Started sacubitril-valsartan and bisoprolol. Daily "
                "weights and fluid restriction advised.",
                "ENC-10012",
                "Dr. Priya Raman",
            ),
        ],
    ),
    Patient(
        mrn=1242,
        first="Michael",
        last="Johnson",
        dob=d(1975, 8, 13),
        sex="male",
        encounters=[
            ("ENC-10013", "outpatient", d(2025, 3, 10), d(2025, 3, 10)),
            ("ENC-10014", "outpatient", d(2025, 4, 22), d(2025, 4, 22)),
        ],
        raw={"csv": {"name": "JOHNSON, MICHAEL"}},
        anomalies=["creatinine", "albumin"],
        records=[
            Record(
                "csv",
                "lab",
                "Basic metabolic panel",
                d(2025, 3, 10),
                "Creatinine 1.9 mg/dL (reference 0.7-1.3). Estimated GFR 42 mL/min/1.73m2. "
                "Potassium 5.1 mmol/L. Sodium 139 mmol/L. Reduced kidney function.",
                "ENC-10013",
                "Dr. Farah Siddiqui",
                flag="H",
                raw={"date": "20250310"},
                defects=[("date.reformatted", "collection date written as 20250310")],
            ),
            Record(
                "csv",
                "lab",
                "Urine albumin-to-creatinine ratio",
                d(2025, 3, 10),
                "Urine albumin-to-creatinine ratio 410 mg/g (reference < 30). Severely "
                "increased albuminuria.",
                "ENC-99999",
                "Dr. Farah Siddiqui",
                flag="H",
                defects=[
                    (
                        "encounter.unknown_reference_removed",
                        "row references encounter ENC-99999, which does not exist",
                    )
                ],
            ),
            Record(
                "json",
                "imaging",
                "Renal ultrasound",
                d(2025, 4, 22),
                "Both kidneys are small with increased cortical echogenicity. Right kidney "
                "9.1 cm, left kidney 9.3 cm. No hydronephrosis, stones or masses. Findings "
                "consistent with chronic medical renal disease.",
                "ENC-10014",
                "Dr. Ingrid Solberg",
            ),
            Record(
                "txt",
                "scanned_note",
                "Nephrology consultation note",
                d(2025, 4, 22),
                "Chronic kidney disease stage 3b with severely increased albuminuria, most "
                "likely hypertensive nephropathy. Blood pressure 152/94. Plan: start "
                "lisinopril, avoid NSAIDs, low-sodium diet, repeat kidney function in three "
                "months.",
                "ENC-10014",
                "Dr. Farah Siddiqui",
            ),
        ],
    ),
    Patient(
        mrn=1243,
        first="Sarah",
        last="Thompson",
        dob=d(1996, 4, 22),
        sex="unknown",
        encounters=[("ENC-10015", "emergency", d(2025, 5, 19), d(2025, 5, 19))],
        raw={"json": {"sex": ""}, "txt": {"sex": "", "dob": ""}},
        defects=[("gender.defaulted_unknown", "sex is missing from every source")],
        anomalies=["peak flow"],
        records=[
            Record(
                "json",
                "imaging",
                "Chest X-ray, two views",
                d(2025, 5, 19),
                "Hyperinflated lungs with flattened diaphragms. No focal consolidation, "
                "pneumothorax or pleural effusion. Heart size normal.",
                "ENC-10015",
                "Dr. Helen Park",
            ),
            Record(
                "json",
                "progress_note",
                "Emergency department note",
                d(2025, 5, 19),
                "29-year-old with known asthma presenting with wheeze, chest tightness and "
                "breathlessness after a viral illness. Peak flow 45% of predicted on arrival. "
                "Diagnosis: moderate asthma exacerbation. Treated with nebulized salbutamol, "
                "ipratropium and oral prednisolone. Peak flow 78% of predicted after "
                "treatment. Discharged with a five-day steroid course.",
                "ENC-10015",
                "Dr. Marcus Bell",
            ),
            Record(
                "txt",
                "scanned_note",
                "Pulmonary function test report",
                d(2025, 6, 9),
                "Spirometry: FEV1 71% of predicted, FEV1/FVC ratio 0.66. FEV1 improved by 18% "
                "after bronchodilator. Impression: reversible airflow obstruction consistent "
                "with asthma. Recommend stepping up inhaled corticosteroid therapy.",
                None,
                "Dr. Oliver Grant",
            ),
        ],
    ),
    Patient(
        mrn=1244,
        first="Thomas",
        last="Wright",
        dob=None,
        sex="male",
        encounters=[("ENC-10016", "outpatient", d(2025, 4, 14), d(2025, 4, 14))],
        defects=[("demographics.missing", "DOB is missing from every source")],
        anomalies=["nodule"],
        records=[
            Record(
                "json",
                "imaging",
                "CT chest without contrast",
                d(2025, 4, 14),
                "Solid pulmonary nodule in the right upper lobe measuring 9 mm with "
                "spiculated margins. Moderate centrilobular emphysema. No mediastinal "
                "lymphadenopathy. Suspicious nodule; PET-CT or tissue sampling recommended.",
                "ENC-10016",
                "Dr. Ingrid Solberg",
            ),
            Record(
                "json",
                "progress_note",
                "Respiratory clinic note",
                d(2025, 4, 14),
                "Chronic obstructive pulmonary disease, 40 pack-year smoking history, still "
                "smoking ten cigarettes a day. Two exacerbations in the past year. New 9 mm "
                "right upper lobe nodule on CT. Plan: PET-CT, lung cancer multidisciplinary "
                "team referral, smoking cessation support, continue tiotropium.",
                "ENC-10016",
                "Dr. Oliver Grant",
            ),
            Record(
                "txt",
                "scanned_note",
                "Pulmonary function test report",
                d(2025, 4, 14),
                "Spirometry: FEV1 48% of predicted, FEV1/FVC ratio 0.52, no significant "
                "bronchodilator response. Impression: severe fixed airflow obstruction "
                "consistent with COPD, GOLD stage 3.",
                "ENC-10016",
                "Dr. Oliver Grant",
            ),
        ],
    ),
    Patient(
        mrn=1245,
        first="Emily",
        last="Davis",
        dob=d(1987, 6, 8),
        sex="female",
        encounters=[
            ("ENC-10017", "outpatient", d(2025, 1, 15), d(2025, 1, 15)),
            ("ENC-10018", "outpatient", d(2025, 3, 12), d(2025, 3, 12)),
        ],
        raw={"csv": {"sex": "f"}},
        anomalies=["tsh"],
        records=[
            Record(
                "csv",
                "lab",
                "Thyroid stimulating hormone",
                d(2025, 1, 15),
                "TSH 14.6 mIU/L (reference 0.4-4.0). Free T4 0.6 ng/dL (reference 0.8-1.8). "
                "Consistent with primary hypothyroidism.",
                "ENC-10017",
                "Dr. Grace Okafor",
                flag="H",
            ),
            # The same result re-keyed by hand: only case and spacing differ.
            Record(
                "csv",
                "lab",
                "Thyroid stimulating hormone",
                d(2025, 1, 15),
                "TSH 14.6 mIU/L (reference 0.4-4.0).  free T4 0.6 ng/dL (reference 0.8-1.8). "
                "CONSISTENT WITH PRIMARY HYPOTHYROIDISM. ",
                "ENC-10017",
                "Dr. Grace Okafor",
                flag="H",
                defects=[
                    (
                        "record.near_duplicate_merged",
                        "lab result re-entered with different case and spacing",
                    )
                ],
            ),
            Record(
                "json",
                "progress_note",
                "Primary care progress note",
                d(2025, 1, 15),
                "37-year-old woman with fatigue, weight gain of 6 kg, cold intolerance and "
                "constipation over six months. Dry skin and delayed reflex relaxation on "
                "examination. Diagnosis: primary hypothyroidism. Started levothyroxine "
                "50 micrograms daily.",
                "ENC-10017",
                "Dr. Grace Okafor",
            ),
            Record(
                "csv",
                "lab",
                "Thyroid stimulating hormone",
                d(2025, 3, 12),
                "TSH 3.1 mIU/L (reference 0.4-4.0). Within the reference range on levothyroxine.",
                "ENC-10018",
                "Dr. Grace Okafor",
                flag="N",
            ),
        ],
    ),
    Patient(
        mrn=1246,
        first="George",
        last="Martin",
        dob=d(1950, 12, 19),
        sex="male",
        encounters=[("ENC-10019", "emergency", d(2025, 6, 1), d(2025, 6, 7))],
        raw={"csv": {"dob": "19/12/1950"}},
        defects=[("date.reformatted", "DOB written day-first as 19/12/1950")],
        anomalies=["fracture"],
        records=[
            Record(
                "json",
                "imaging",
                "X-ray right hip and pelvis",
                d(2025, 6, 1),
                "Displaced intracapsular fracture of the right femoral neck. No dislocation. "
                "Generalized osteopenia. Left hip intact.",
                "ENC-10019",
                "Dr. Helen Park",
            ),
            Record(
                "csv",
                "lab",
                "Pre-operative blood panel",
                d(2025, 6, 1),
                "Hemoglobin 12.4 g/dL. White blood cell count 9.8 x10^9/L. Creatinine "
                "1.0 mg/dL. INR 1.0. No abnormality precluding surgery.",
                "ENC-10019",
                "Dr. Yusuf Demir",
                flag="N",
            ),
            Record(
                "json",
                "discharge_summary",
                "Discharge summary",
                d(2025, 6, 7),
                "74-year-old man fell at home and could not bear weight. X-ray showed a "
                "displaced right femoral neck fracture. Underwent right hip "
                "hemiarthroplasty the next day. Mobilizing with a frame. Started on "
                "alendronate and vitamin D for osteoporosis; thromboprophylaxis for 35 days.",
                "ENC-10019",
                "Dr. Yusuf Demir",
            ),
        ],
    ),
    Patient(
        mrn=1247,
        first="Fatima",
        last="Ali",
        dob=d(1972, 3, 3),
        sex="female",
        encounters=[("ENC-10020", "inpatient", d(2025, 5, 11), d(2025, 5, 14))],
        raw={"json": {"sex": "FEMALE", "dob": "March 3, 1972"}},
        defects=[("date.reformatted", "DOB written as 'March 3, 1972'")],
        anomalies=["e. coli", "hydronephrosis"],
        records=[
            Record(
                "csv",
                "lab",
                "Urinalysis",
                d(2025, 5, 11),
                "Leukocyte esterase 3+, nitrite positive, white blood cells > 50 per "
                "high-power field, bacteria many. Consistent with urinary tract infection.",
                "ENC-10020",
                "Dr. Samuel Ortiz",
                flag="A",
            ),
            Record(
                "csv",
                "lab",
                "Urine culture",
                d(2025, 5, 13),
                "Escherichia coli > 100,000 CFU/mL. Resistant to ampicillin and "
                "trimethoprim-sulfamethoxazole. Sensitive to ceftriaxone, ciprofloxacin and "
                "nitrofurantoin.",
                "ENC-10020",
                "Dr. Samuel Ortiz",
                flag="A",
            ),
            Record(
                "json",
                "imaging",
                "CT abdomen and pelvis with contrast",
                d(2025, 5, 11),
                "Enlarged right kidney with wedge-shaped areas of reduced enhancement and "
                "perinephric stranding. Mild right hydronephrosis. No renal abscess or "
                "obstructing stone. Findings consistent with acute right pyelonephritis.",
                "ENC-10020",
                "Dr. Ingrid Solberg",
            ),
            Record(
                "json",
                "discharge_summary",
                "Discharge summary",
                d(2025, 5, 14),
                "53-year-old woman admitted with fever, rigors, right flank pain and "
                "dysuria. Diagnosis: acute right pyelonephritis due to Escherichia coli. "
                "Treated with intravenous ceftriaxone, switched to oral ciprofloxacin to "
                "complete fourteen days. Afebrile and tolerating oral intake at discharge.",
                "ENC-10020",
                "Dr. Samuel Ortiz",
            ),
        ],
    ),
    Patient(
        mrn=1915,
        first="Daniel",
        last="Kim",
        dob=d(2001, 9, 15),
        sex="male",
        encounters=[("ENC-10021", "emergency", d(2025, 6, 14), d(2025, 6, 14))],
        defects=[
            (
                "patient.possible_duplicate",
                "Daniel Kim, born 2001-09-15, also exists under MRN 9915",
            )
        ],
        records=[
            Record(
                "json",
                "imaging",
                "CT head without contrast",
                d(2025, 6, 14),
                "No acute intracranial hemorrhage, mass effect or midline shift. No skull "
                "fracture. Normal study.",
                "ENC-10021",
                "Dr. Helen Park",
            ),
            Record(
                "json",
                "progress_note",
                "Emergency department note",
                d(2025, 6, 14),
                "23-year-old man with head injury during a football match, brief loss of "
                "consciousness, headache and nausea. Glasgow Coma Scale 15. Normal "
                "neurological examination. CT head normal. Diagnosis: concussion. Discharged "
                "with head injury advice and graded return to sport.",
                "ENC-10021",
                "Dr. Marcus Bell",
            ),
        ],
    ),
    # The same person registered a second time at another clinic under a new MRN.
    Patient(
        mrn=9915,
        first="Daniel",
        last="Kim",
        dob=d(2001, 9, 15),
        sex="male",
        encounters=[],
        defects=[
            (
                "patient.possible_duplicate",
                "Daniel Kim, born 2001-09-15, also exists under MRN 1915",
            )
        ],
        records=[
            Record(
                "txt",
                "scanned_note",
                "Sports medicine follow-up note",
                d(2025, 6, 28),
                "Two weeks after concussion. Headaches resolved, no dizziness, sleeping "
                "normally. Symptom-free at rest and with light exercise. Cleared to begin "
                "the graded return-to-play protocol.",
                None,
                "Dr. Leila Haddad",
            ),
        ],
    ),
]

# Records that cannot be attributed to a patient or have no content.
QUARANTINE_DEFECTS = [
    ("record.missing_patient_identifier", "lab_results.csv: one row has a blank MRN"),
    ("record.missing_patient_identifier", "scanned_notes: one note has no MRN line"),
    ("record.empty_content", "ehr_export.json: one document has an empty body"),
]


# --------------------------------------------------------------------------- #
# Raw formatting, per source
# --------------------------------------------------------------------------- #

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]  # fmt: skip
SEX_CODES = {"male": "M", "female": "F", "unknown": ""}
TXT_SEX = {"male": "Male", "female": "Female", "unknown": ""}
JSON_CATEGORY = {
    "imaging": "Imaging",
    "discharge_summary": "Discharge Summary",
    "progress_note": "Progress Note",
}


def iso(value: date | None) -> str:
    return value.isoformat() if value else ""


def us(value: date | None) -> str:
    return value.strftime("%m/%d/%Y") if value else ""


def dmy(value: date | None) -> str:
    return f"{value.day:02d}-{MONTHS[value.month - 1]}-{value.year}" if value else ""


def canonical_mrn(mrn: int) -> str:
    return f"MRN-{mrn:06d}"


def slug(patient: Patient, index: int) -> str:
    return f"{patient.last.lower().replace(chr(39), '')}_{patient.mrn}_{index:02d}"


def build_json(patients: list[Patient]) -> dict[str, Any]:
    exported = []
    doc_number = 5000
    for patient in patients:
        overrides = patient.raw.get("json", {})
        documents: list[dict[str, Any]] = []
        for record in (r for r in patient.records if r.source == "json"):
            doc_number += 1
            document = {
                "doc_id": f"DOC-{doc_number}",
                "encounter_id": record.encounter,
                "category": JSON_CATEGORY[record.kind],
                "title": record.title,
                "date": record.raw.get("date", iso(record.on)),
                "author": record.author,
                "text": record.text,
            }
            documents.extend([document] * record.repeat)
        if not documents and not patient.encounters:
            continue  # this patient is known only from other sources
        entry: dict[str, Any] = {"mrn": overrides.get("mrn", canonical_mrn(patient.mrn))}
        if "name" in overrides:
            entry["name"] = overrides["name"]
        else:
            entry["name"] = {"first": patient.first, "last": patient.last}
        entry["dob"] = overrides.get("dob", iso(patient.dob))
        entry["sex"] = overrides.get("sex", patient.sex)
        entry["encounters"] = [
            {"encounter_id": eid, "class": cls, "start": iso(start), "end": iso(end)}
            for eid, cls, start, end in patient.encounters
        ]
        entry["documents"] = documents
        exported.append(entry)

    # Defect: a document with no body.
    exported[0]["documents"].append(
        {
            "doc_id": "DOC-5999",
            "encounter_id": "ENC-10001",
            "category": "Progress Note",
            "title": "Telephone encounter",
            "date": "2025-01-13",
            "author": "Dr. Priya Raman",
            "text": "   ",
        }
    )
    return {
        "export_metadata": {
            "system": "Synthetic EHR export (fictional data)",
            "exported_at": "2025-07-01T09:00:00Z",
            "format_version": "1.2",
        },
        "patients": exported,
    }


CSV_COLUMNS = ["mrn", "patient_name", "dob", "sex", "collected", "panel",
               "result", "flag", "encounter_id", "ordered_by"]  # fmt: skip


def build_csv_rows(patients: list[Patient]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for patient in patients:
        overrides = patient.raw.get("csv", {})
        for record in (r for r in patient.records if r.source == "csv"):
            row = {
                "mrn": overrides.get("mrn", f"{patient.mrn:06d}"),
                "patient_name": overrides.get("name", f"{patient.last}, {patient.first}"),
                "dob": overrides.get("dob", us(patient.dob)),
                "sex": overrides.get("sex", SEX_CODES[patient.sex]),
                "collected": record.raw.get("date", us(record.on)),
                "panel": record.title,
                "result": record.text,
                "flag": record.flag,
                "encounter_id": record.encounter or "",
                "ordered_by": record.author,
            }
            rows.extend([row] * record.repeat)

    # Defect: a result that cannot be attributed to any patient.
    rows.append(
        {
            "mrn": "",
            "patient_name": "Unknown, Patient",
            "dob": "",
            "sex": "",
            "collected": "04/01/2025",
            "panel": "Complete blood count",
            "result": "Hemoglobin 13.9 g/dL. White blood cell count 7.1 x10^9/L.",
            "flag": "N",
            "encounter_id": "",
            "ordered_by": "Dr. Samuel Ortiz",
        }
    )
    return rows


def render_note(header: list[tuple[str, str]], body: str) -> str:
    lines = ["*** SCANNED DOCUMENT - OCR TEXT ***"]
    lines += [f"{key}: {value}" for key, value in header if value]
    return "\n".join(lines) + "\n\n" + body + "\n"


def build_notes(patients: list[Patient]) -> dict[str, str]:
    notes: dict[str, str] = {}
    for patient in patients:
        overrides = patient.raw.get("txt", {})
        text_records = [r for r in patient.records if r.source == "txt"]
        for index, record in enumerate(text_records, start=1):
            header = [
                ("Patient", f"{patient.first} {patient.last}"),
                ("MRN", overrides.get("mrn", canonical_mrn(patient.mrn))),
                ("DOB", overrides.get("dob", dmy(patient.dob))),
                ("Sex", overrides.get("sex", TXT_SEX[patient.sex])),
                ("Date of Service", record.raw.get("date", dmy(record.on))),
                ("Document Type", record.title),
                ("Encounter", record.encounter or ""),
                ("Author", record.author),
            ]
            notes[f"{slug(patient, index)}.txt"] = render_note(header, record.text)

    # Defect: a scan whose header lost the MRN line.
    notes["unidentified_scan_01.txt"] = render_note(
        [
            ("Patient", "R. Hayes"),
            ("Date of Service", "20-Feb-2025"),
            ("Document Type", "Dietitian note"),
            ("Author", "Dietitian Amara Nwosu"),
        ],
        "Reviewed cardiac diet. Advised reduced saturated fat and sodium intake.",
    )
    return notes


def build_manifest(patients: list[Patient]) -> dict[str, Any]:
    defects = []
    for patient in patients:
        mrn = canonical_mrn(patient.mrn)
        defects += [{"rule": rule, "mrn": mrn, "note": note} for rule, note in patient.defects]
        for record in patient.records:
            defects += [
                {"rule": rule, "mrn": mrn, "title": record.title, "note": note}
                for rule, note in record.defects
            ]
    defects += [{"rule": rule, "mrn": None, "note": note} for rule, note in QUARANTINE_DEFECTS]
    return {
        "description": "Defects injected on purpose into the synthetic dataset.",
        "expected_patients": len(patients),
        "expected_records": sum(
            1
            for p in patients
            for r in p.records
            if not any(rule == "record.near_duplicate_merged" for rule, _ in r.defects)
        ),
        "expected_quarantined": len(QUARANTINE_DEFECTS),
        "defects": defects,
        "planted_anomalies": {canonical_mrn(p.mrn): p.anomalies for p in patients if p.anomalies},
    }


def write_dataset(output_dir: Path) -> dict[str, Any]:
    notes_dir = output_dir / "scanned_notes"
    notes_dir.mkdir(parents=True, exist_ok=True)
    for stale in notes_dir.glob("*.txt"):
        stale.unlink()

    export = build_json(PATIENTS)
    (output_dir / "ehr_export.json").write_text(json.dumps(export, indent=2) + "\n")

    with (output_dir / "lab_results.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(build_csv_rows(PATIENTS))

    for name, content in build_notes(PATIENTS).items():
        (notes_dir / name).write_text(content)

    manifest = build_manifest(PATIENTS)
    (output_dir.parent / "synthetic_manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n"
    )
    return manifest


def main() -> None:
    output_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_OUTPUT_DIR
    manifest = write_dataset(output_dir)
    print(
        f"Wrote {manifest['expected_patients']} patients and "
        f"{manifest['expected_records']} unique records "
        f"({len(manifest['defects'])} injected defects) to {output_dir}"
    )


if __name__ == "__main__":
    main()
