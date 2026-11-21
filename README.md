# EHR Media Intelligence Platform

A pipeline and search application for unstructured patient records. It ingests messy EHR exports,
cleans them, maps them to HL7 FHIR R4, summarizes each patient with a language model, and lets a
clinician search every record in plain language.

All patient data in this repository is synthetic.

A live deployment runs at [demo.yohannes-merga.et](https://demo.yohannes-merga.et).

```text
data/raw/                 JSON export, lab CSV, scanned-note text
   │  ehr ingest          clean, deduplicate, resolve conflicts, write an audit log
   ▼
SQLite: clean records ──► ehr fhir       map to FHIR R4 Bundles, validate
   ▼
SQLite: Bundles ────────► ehr summarize  structured LLM summaries, cached, evaluated
   ▼
SQLite: summaries ──────► ehr index      embed documents and summaries into ChromaDB
   ▼
FastAPI (POST /search, GET /patients/{id}) ──► React + Tailwind UI behind nginx
```

## Requirements

- Docker with the Compose plugin, to run the application.
- [uv](https://docs.astral.sh/uv/) and Python 3.11 or later, to run the tests and the pipeline
  outside Docker.
- Node.js 22, to work on the frontend outside Docker.

No API key is required. The repository includes the cleaned data, the FHIR Bundles and the
generated summaries, and search uses a local embedding model.

## Run the application

1. Clone the repository and change into its directory.

1. Build and start the containers:

   ```bash
   docker compose up --build
   ```

   The first build downloads PyTorch and the embedding model, and takes several minutes.

1. Open `http://localhost:8080`, then select one of the example queries.

To publish the UI on a different port, set `WEB_PORT`:

```bash
WEB_PORT=9000 docker compose up --build
```

Compose starts two containers. `web` is nginx: it serves the UI, proxies `/api` to the backend and
rate-limits requests. `api` is FastAPI and is not published on the host. The API is read-only and
never calls a language model, so a public deployment holds no API key.

## Configuration

Settings come from environment variables or a `.env` file. To create one, copy `.env.example`.

| Variable | Default | Description |
| --- | --- | --- |
| `WEB_PORT` | `8080` | Host port that Compose publishes the UI on. |
| `EHR_LLM_API_KEY` | empty | API key for the summarization model. Only `ehr summarize` uses it. |
| `EHR_LLM_BASE_URL` | `https://api.openai.com/v1` | Base URL of an OpenAI-compatible chat completions API. |
| `EHR_LLM_MODEL` | `gpt-4o-mini` | Model name sent to that API. |
| `EHR_EMBEDDING_MODEL` | `sentence-transformers/all-MiniLM-L6-v2` | Sentence-transformers model used for search. |
| `EHR_DATA_DIR` | `data` | Directory that holds the raw inputs, the SQLite store, the reports and the index. |
| `EHR_API_ROOT_PATH` | empty | Path prefix that a reverse proxy serves the API under. Compose sets it to `/api`. |

The summarizer works with OpenAI and with any provider that exposes the same API. To use Gemini,
set the base URL to `https://generativelanguage.googleapis.com/v1beta/openai/` and the model to a
Gemini model name.

## Run the pipeline

The pipeline is a command-line tool with one command per stage. Each stage reads what the previous
stage stored in SQLite, so you can run a stage on its own.

To run every stage in Docker against the `data` directory:

```bash
docker compose run --rm pipeline
```

To run stages without Docker:

```bash
uv sync
uv run ehr ingest       # data/raw -> clean records, audit log, quarantine
uv run ehr fhir         # clean records -> FHIR Bundles + validation report
uv run ehr summarize    # Bundles -> summaries + evaluation report
uv run ehr index        # documents and summaries -> vector index
uv run ehr run          # all four stages in order
```

If `EHR_LLM_API_KEY` is not set, `ehr summarize` reuses the cached summaries. A patient that has no
cached summary gets a rule-based extract, which the output and the UI label as not AI-generated.
To ignore the cache and call the model again for every patient, add `--refresh-summaries`.

Each run writes three reports to `data/reports`:

| Report | Contents |
| --- | --- |
| `ingestion_report.json` | Record counts, audit entries by rule and severity, and quarantined records. |
| `validation_report.json` | For each Bundle: resource counts and every validation issue with its validator, resource and field path. |
| `evaluation_report.json` | For each summary: word count, cited dates, unsupported numbers, term grounding and recall of planted anomalies. |

To regenerate the synthetic input files, run `uv run python scripts/generate_synthetic_data.py`.

## Use the API

When the stack runs, the API is available under `/api`. Interactive documentation is at
`http://localhost:8080/api/docs`.

Search takes the query in the request body and the filters as query parameters:

```bash
curl -X POST 'http://localhost:8080/api/search?resource_type=DiagnosticReport&date_from=2025-01-01&date_to=2025-03-31' \
  -H 'Content-Type: application/json' \
  -d '{"query": "heart attack blood test"}'
```

| Endpoint | Description |
| --- | --- |
| `POST /search` | Returns the five most relevant records with relevance scores. Optional query parameters: `resource_type` (`Patient`, `DiagnosticReport` or `DocumentReference`), `date_from` and `date_to` (`YYYY-MM-DD`, inclusive). |
| `GET /patients/{patient_id}` | Returns the patient's summary, data-quality notes and linked FHIR resources. |
| `GET /health` | Returns the number of patients and indexed entries. |

## Develop and test

```bash
uv sync
uv run pytest                 # all tests
uv run pytest -m "not slow"   # skip the tests that load the real embedding model
uv run ruff check . && uv run ruff format --check .
uv run mypy
```

The tests marked `slow` download the embedding model (about 90 MB) on first use.

To work on the frontend with hot reload, start the API and the Vite development server in two
terminals:

```bash
uv run uvicorn ehr_platform.api.app:app --port 8000
```

```bash
cd web && npm ci && npm run dev
```

## Project structure

| Path | Contents |
| --- | --- |
| `src/ehr_platform/ingestion` | Readers, normalizers and the cleaning policy (Task 1). |
| `src/ehr_platform/fhir` | FHIR mapping, validation and Bundle reading (Task 2). |
| `src/ehr_platform/summarization` | Prompt, LLM client, cache, fallback and evaluation (Task 3). |
| `src/ehr_platform/search` | Embedding, index entries and the ChromaDB index (Task 4). |
| `src/ehr_platform/api` | FastAPI application and response models (Task 4). |
| `web` | React, TypeScript and Tailwind UI, with its nginx configuration (Task 5). |
| `src/ehr_platform/storage.py` | SQLite store shared by every stage. |
| `data/raw` | Synthetic input files. `data/synthetic_manifest.json` lists the defects injected into them. |
| `data/store`, `data/reports` | Pipeline outputs, committed so that the application runs without a key. |
| `tests` | Unit and integration tests, laid out like the source tree. |

## Design decisions

### Ingestion and cleaning

- **Readers extract, the cleaner interprets.** Readers copy values verbatim from JSON, CSV and
  scanned-note text into raw models. All normalization happens in one place, so every change is
  logged once.
- **A patient is identified by canonical MRN only.** `1234`, `mrn 001234` and `mrn#1234` all become
  `MRN-001234`. Two patients with the same name and date of birth but different MRNs are flagged as
  a possible duplicate and never merged, because a wrong merge is a patient-safety problem.
- **Conflicts are resolved by source precedence.** When sources disagree on a demographic, the
  structured JSON export wins over the lab CSV, which wins over scanned text. The rejected value
  stays in the audit log, and the patient is tagged as having a conflict. "Most recent value wins"
  was rejected because scanned notes are both the least reliable source and often the most recent.
- **Ambiguous values are resolved by a stated convention.** `03/04/1962` is read month-first, the
  US convention. `14-Mar-62` becomes 1962, because a date of birth cannot be in the future. Both
  assumptions are logged.
- **Nothing is dropped silently.** A record with an impossible date keeps its content and loses the
  date. A record with no patient identifier or no content goes to a quarantine table with a reason.
  A test asserts that every raw record ends up in a clean record or in quarantine.
- **Duplicates are handled at two levels.** Exact duplicates are dropped. Records with the same
  patient, kind, date and text, ignoring case and spacing, are merged into the copy from the most
  trusted source.
- **The dataset proves the policy.** The generator records every defect that it injects, and a test
  asserts that the audit log contains the matching rule for each one.

### FHIR R4

- **Two libraries, because one cannot meet every requirement.** The `fhir.resources` releases
  that support Pydantic v2 provide R4B (4.3.0) and R5 models, not R4 (4.0.1). The pipeline builds
  resources with `fhir.resources` R4B models, then parses every resource again with `fhirclient` in
  strict mode. `fhirclient` models are generated from FHIR 4.0.1, so an element that exists only in
  R4B fails validation.
- **Two more checks cover what the libraries do not.** Neither library checks that references
  resolve or that codes with a required binding are valid. The validator checks both.
- **Four resource types.** `Patient`, `Encounter`, `DiagnosticReport` for labs and imaging, and
  `DocumentReference` for notes. `Encounter` is included so that `encounter` references point at a
  real resource. A reference to an encounter that does not exist is removed and logged.
- **Bundles are deterministic.** Resource IDs are UUIDv5 values derived from the MRN and record ID,
  and references use `urn:uuid:` URLs that resolve inside the Bundle. Mapping the same input twice
  produces identical JSON, which keeps the summary cache valid.
- **Lab values stay in the report text.** Each lab is one `DiagnosticReport` with its result in
  `conclusion` and an abnormal flag in `conclusionCode`. Modeling each analyte as an `Observation`
  is the more complete approach and is listed under limitations.

### Summarization

- **The model returns a schema, not prose.** The request uses structured output with a Pydantic
  model that holds the four required sections and a confidence level. The system adds the
  disclaimer, the model name and the timestamp, so the model cannot omit or alter them.
- **The 200-word limit is enforced in code.** An overlong summary is retried once with a stricter
  instruction. If it is still too long, it is not stored.
- **The cache key is the patient ID plus a hash of everything the model sees.** The hash covers the
  rendered records, the data-quality warnings and the prompt version. Any change to those
  regenerates the summary; nothing else does.
- **Data-quality warnings reach the model.** A demographic conflict found during cleaning appears
  in the prompt and is expected in the summary's flagged anomalies.
- **Summary quality is measured.** The evaluation checks that every cited record date exists, that
  every number in the summary appears in the source records, how many of the summary's clinical
  terms occur in the source, and whether abnormal findings planted in the dataset are mentioned.
- **Provider.** The summaries in `data/store/ehr.db` were generated with `gemini-3.5-flash-lite` through Gemini's
  OpenAI-compatible endpoint. The same code path works with an OpenAI key.

### Search

- **A search result is one FHIR resource.** Each `DiagnosticReport` and `DocumentReference` is one
  index entry, and each patient's AI summary is one entry of type `Patient`. This gives the resource
  type and date filters an exact meaning.
- **Filters run inside the vector query.** ChromaDB applies metadata filters during the search, so
  a filtered query still returns up to five results. Filtering after the search would return fewer.
- **Embeddings are computed explicitly** with `sentence-transformers`, not with ChromaDB's bundled
  embedder, and vectors are normalized for cosine similarity. The relevance score is the cosine
  similarity, clamped to the range 0 to 1.
- **The index is rebuilt only when its content changes.** A fingerprint of the entries and the
  embedding model name is stored with the index. The Docker image contains the model and a prebuilt
  index, so the API starts without network access.
- **Undated records are searchable, and a date filter excludes them.**

### Frontend

- **No component or state library.** The application is one screen. React hooks, the Fetch API and
  Tailwind cover it, and the TypeScript types mirror the API response models.
- **Search as you type.** Input is debounced by 300 ms, and a request that is still in flight is
  aborted when a newer one starts, so an old response cannot overwrite a newer one. The query is
  kept in the URL.
- **Accessibility.** Every control has a label. A live region announces result counts. Arrow keys
  move between results. The patient drawer is a modal dialog that traps focus, closes on
  <kbd>Escape</kbd> and returns focus to the result that opened it.
- **The drawer shows the evidence.** Each linked resource expands to its text and its stored FHIR
  JSON, so you can check a summary against its sources.

## Limitations

- The evaluation measures faithfulness to the source text. It does not measure clinical
  correctness, which needs review by a clinician.
- Records are embedded whole. Real discharge summaries are longer than the embedding model's input
  window and need to be split into chunks.
- Lab results are not modeled as `Observation` resources, and panels are not coded with specific
  LOINC codes.
- Scanned notes are read as text. The pipeline does not perform OCR on images or PDF files.
- The API has no authentication. It serves synthetic data only.
- The frontend has no automated tests.
