# Phase 1 — Ingestion

Turn an uploaded CSV / PDF / text file into persisted **tickets** and **issues**
(one issue per ticket for now — multi-issue fan-out is a later, AI phase). All
Phase 1 processing is AI-free.

## Where things live

Flat files, one concern each. The `POST /uploads` request path is two hops:
`api/routes/uploads.py` → `services/ingestion.py` (which uses `services/validation.py`,
`services/cleaning.py`, `models/`, `schemas/`).

| File | Holds |
| --- | --- |
| [src/app/api/routes/uploads.py](../src/app/api/routes/uploads.py) | `POST /uploads` endpoint; maps ingestion errors → 4xx |
| [src/app/api/deps.py](../src/app/api/deps.py) | `get_current_user` (dev-user stub via `X-User-Id`), `DbSession`/`CurrentUser` aliases |
| [src/app/services/ingestion.py](../src/app/services/ingestion.py) | parsers (`parse_csv`/`parse_pdf`/`parse_text` + `parse_file`), `detect_boundaries`, `run_pipeline`, `IngestionService` (persistence) |
| [src/app/services/validation.py](../src/app/services/validation.py) | ingestion error types, `decode_bytes` (encoding repair), `find_text_column`/`is_blank`, `classify_content` (empty/one-word/junk) |
| [src/app/services/cleaning.py](../src/app/services/cleaning.py) | `strip_boilerplate`, `redact_pii`, `detect_language`, `normalise_text`, `content_hash` |
| [src/app/schemas/upload.py](../src/app/schemas/upload.py) | `UploadSummary`, `UploadCounts`, `CreatedItem`, `SkippedItemOut`, `SkipReason` |
| [src/app/db/seed.py](../src/app/db/seed.py) | fixed dev user (`DEV_USER_ID`), `ensure_dev_user`, `python -m app.db.seed` |
| [src/app/models/enums.py](../src/app/models/enums.py) | adds `IssueFlag` (the per-issue flag strings) |
| [tests/](../tests/) | `test_cleaning.py`, `test_validation.py`, `test_ingestion.py`, `test_uploads_api.py` |

Layer separation is intact: `api/routes/` (HTTP) → `services/` (logic) → `models/`
+ `schemas/` (data). No sub-packages were added — everything is a flat file.

## Auth: dev-user stub

No OAuth in Phase 1. One fixed user is seeded
(`DEV_USER_ID = 00000000-0000-0000-0000-000000000001`) and requests select it via
the `X-User-Id` header:

- **No header** → the fixed dev user (created on demand, so a fresh DB never 404s).
- **Malformed UUID** → `400`.
- **Well-formed, unknown id** → `404`.

The dev user is also seeded best-effort on app startup (never fatal) and via
`python -m app.db.seed`.

## The pipeline, stage by stage

`IngestionService.ingest()` runs:

1. **parse** (`parse_file`) — pick a parser by extension/content-type:
   - `parse_csv` — pandas; decode + repair encoding, validate the text column,
     skip+count blank rows, one record per non-blank row (atomic; not split).
   - `parse_pdf` — pdfplumber; concatenate page text. **No extractable text → a
     scan**: emit an empty record flagged `scanned_pdf` + `needs_manual_review`
     (OCR is out of scope).
   - `parse_text` — decode + repair; whole document is one record.
2. **boundary** (`detect_boundaries`, text/PDF only) — split concatenated
   messages into per-customer segments.
3. **clean** (per segment) — `strip_boilerplate` → `redact_pii` →
   `detect_language` → `classify_content` → `normalise_text` → `content_hash`.
4. **dedup** — skip items whose `content_hash` was already seen (this batch or the
   DB, scoped to the user).
5. **persist** — one `Ticket` + one `Issue` per surviving item; commit.
6. **summarise** — return `UploadSummary` (counts + per-item detail).

## Edge-case handling (every case is unit-tested)

Because there was no separate Edge_Case doc in the repo, the edge cases are
derived directly from the Phase 1 spec. Each maps to a test.

### File-level validation (before any per-item work)

| Edge case | Behaviour | Test |
| --- | --- | --- |
| CSV missing a text column | `MissingTextColumnError` → **422**; message names expected vs. seen columns | `test_validation.py::test_missing_text_column_raises_named_error` |
| Blank rows | Skipped and counted (`counts.blanks`) | `test_ingestion.py::test_parse_csv_rows_and_skips_blanks` |
| Non-UTF-8 encoding (latin-1/cp1252) | Auto-repaired; `encoding_recovered=true`, `encoding_recovered` flag | `test_validation.py::test_latin1_is_auto_repaired`, `test_ingestion.py::test_parse_csv_latin1_recovered_and_flagged` |
| UTF-16 with BOM | Decoded via BOM | `test_validation.py::test_utf16_bom_decoded` |
| Truly unreadable / binary | `UndecodableFileError` → **400**: "re-save as UTF-8" | `test_validation.py::test_binary_data_asks_for_utf8` |
| Duplicate rows | Skipped as `duplicate` via `content_hash` | `test_ingestion.py::test_intra_file_duplicates_are_skipped` |
| Empty file | `EmptyFileError` → **400** | `test_ingestion.py::test_parse_csv_empty_file_raises` |

### Per-item cleaning

| Edge case | Behaviour | Test |
| --- | --- | --- |
| Email signatures / "Best regards" | Stripped; `boilerplate_stripped` flag | `test_cleaning.py::test_signature_*` |
| Quoted reply / "On … wrote:" / Original Message | Stripped | `test_cleaning.py::test_quoted_reply_block_stripped` |
| Credit-card numbers (Luhn-valid) | `[REDACTED_CARD]`; `pii_redacted` flag | `test_cleaning.py::test_luhn_valid_card_redacted` |
| Non-Luhn digit runs | Not redacted (avoids false positives) | `test_cleaning.py::test_non_luhn_digits_not_treated_as_card` |
| Emails / phone numbers | `[REDACTED_EMAIL]` / `[REDACTED_PHONE]` | `test_cleaning.py::test_email_redacted`, `test_phone_redacted` |
| Language | Tagged (`en`, `es`, …) or `unknown`; `language_unknown` flag | `test_cleaning.py::test_*_detected` |
| Empty after cleaning | Skipped as `empty_after_clean` | `test_ingestion.py::test_empty_after_cleaning_is_skipped` |
| One-word content | Created, flagged `one_word` + `junk`, `needs_manual_review` | `test_validation.py::test_one_word_flagged` |
| Junk / symbols-only | Created, flagged `junk`, low confidence | `test_validation.py::test_symbols_only_is_junk` |
| Dedup hash | `content_hash(user_id + normalised_text)`; same text+user dedups, different user does not | `test_cleaning.py::test_same_text_*` |

### Blob boundary detection

| Edge case | Behaviour | Test |
| --- | --- | --- |
| Single message | One ticket | `test_ingestion.py::test_single_message_stays_one_segment` |
| `From:` headers | Split into one ticket per sender | `test_ingestion.py::test_split_on_from_headers` |
| `-----Original Message-----` | Split | `test_ingestion.py::test_split_on_original_message_marker` |
| 2+ blank-line gap | Split (single blank line does **not** over-split) | `test_ingestion.py::test_split_on_double_blank_line`, `test_single_blank_line_does_not_oversplit` |
| Ambiguous forwarded thread (multiple senders + quoted markers) | **Not merged**: one ticket flagged `needs_manual_split` + `needs_manual_review` | `test_ingestion.py::test_ambiguous_thread_flags_needs_manual_split_not_merged` |

### PDF

| Edge case | Behaviour | Test |
| --- | --- | --- |
| Text PDF | Parsed normally | `test_ingestion.py::test_parse_pdf_with_text` |
| Scanned PDF (no text) | `scanned_pdf` + `needs_manual_review` placeholder ticket | `test_ingestion.py::test_scanned_pdf_flagged_needs_manual_review`, `test_scanned_pdf_becomes_review_placeholder` |

## The upload summary

`POST /uploads` returns **201** with an `UploadSummary`:

```jsonc
{
  "filename": "sample.csv", "content_type": "text/csv", "parser": "csv",
  "encoding_recovered": false,
  "counts": {
    "detected": 3,     // candidate items (excludes blank rows)
    "created": 3,      // tickets/issues persisted
    "skipped": 1,      // blank + empty_after_clean + duplicate
    "flagged": 2,      // created items with flags / needs_manual_review
    "duplicates": 0,
    "blanks": 1        // blank source rows dropped at parse time
  },
  "created_items": [ { "source_ref": "row 2", "ticket_id": "…", "issue_id": "…",
                       "title": "…", "language": "en", "confidence": 0.95,
                       "flags": [], "needs_manual_review": false }, … ],
  "skipped_items": [ { "source_ref": "row 7", "reason": "duplicate" }, … ]
}
```

Counting rules: an item is **created** or **skipped**, never both. **Flagged** is a
subset of created (non-empty `flags` or `needs_manual_review`). Blank rows are
counted (`counts.blanks`, folded into `counts.skipped`) but not listed
per-item in `skipped_items`.

Error responses use `{"detail": {"code", "message"}}`: `missing_text_column`
(422), `unsupported_file_type` (415), `undecodable_file` / `empty_file` (400).

## Per-function reference

### services/validation.py
- `IngestionError` (+ `code`) and subclasses `UnsupportedFileTypeError`,
  `UndecodableFileError`, `MissingTextColumnError`, `EmptyFileError`.
- `decode_bytes(data) -> DecodedText` — UTF-8 → BOM → cp1252 → latin-1; NUL bytes
  are rejected as binary. `recovered=True` when a fallback was used.
- `find_text_column(columns) -> str` — matches `TEXT_COLUMN_CANDIDATES`
  (case-insensitive); single-column CSVs use their one column; else raises.
- `is_blank(value) -> bool` — None / NaN-like / whitespace-only.
- `classify_content(text) -> ContentClass` — `is_junk`, `confidence` (0–1), `flags`
  for empty / one-word / low-letter-ratio junk.

### services/cleaning.py
- `strip_boilerplate(text) -> CleanResult` — drop signatures, quoted replies,
  original-message trailers; `.boilerplate_stripped` records whether anything went.
- `redact_pii(text) -> RedactResult` — cards (Luhn) → emails → phones, replaced
  with tokens; `.redacted` records whether anything matched.
- `detect_language(text) -> str` — seeded `langdetect`; `"unknown"` for short text.
- `normalise_text(text) -> str` — lowercase + whitespace-collapsed (hash input).
- `content_hash(user_id, normalised_text) -> str` — SHA-256, user-scoped.

### services/ingestion.py
- `parse_csv` / `parse_pdf` / `parse_text` `-> ParseResult`; `parse_file` dispatches.
- `ParsedRecord`, `ParseResult` (`.splittable` drives boundary detection).
- `detect_boundaries(text) -> BoundaryResult` (`segments`, `needs_manual_split`).
- `run_pipeline(parse_result, *, user_id, existing_hashes) -> PipelineResult`
  (`prepared`, `skipped`, `blank_skipped`, `.detected`) — pure, no DB.
- `iso_week(moment=None) -> str` — `YYYY-Www` bucket stored on each issue.
- `IngestionService(db)` — `.ingest(user, *, filename, content_type, data)
  -> UploadSummary` (parse → pipeline → persist Ticket + one Issue → summarise);
  `_existing_hashes`, `_persist` are internal.

### api/deps.py
- `get_current_user(db, x_user_id) -> User` — dev-user stub resolution.
- `DbSession`, `CurrentUser` — `Annotated` dependency aliases.

### api/routes/uploads.py
- `POST /uploads` (`create_upload`) — reads the multipart file, calls
  `IngestionService.ingest`, maps `IngestionError` → the right 4xx.

## Test it yourself

Prereqs: infra + migrations from Phase 0. **Note:** the host already runs Postgres
on 5432, so this project maps its container to **5433** (`PULSE_POSTGRES_PORT=5433`
in `.env`). Keep that value.

```bash
cd /Users/bhavya/Desktop/PulseAI
conda activate pulseai                 # Phase-0 env; deps already installed

# 1. Infra + schema + dev user
docker compose up -d                   # Postgres (pgvector, :5433) + Redis
alembic upgrade head
python -m app.db.seed                  # idempotent; creates the dev user

# 2. Static checks + full test suite (unit + DB-backed endpoint tests)
ruff check . && ruff format --check .
mypy
pytest -v                              # DB-backed /uploads tests run when Postgres is up,
                                       # and auto-skip if it isn't
```

### End-to-end against a running server

```bash
uvicorn app.main:app --reload --app-dir src        # http://localhost:8000
```

Create a sample CSV that exercises the edge cases (blank row, PII, one-word junk,
duplicate):

```bash
cat > /tmp/pulse_sample.csv <<'CSV'
text
App crashes when I click the login button on iOS
Please refund my order, email me at jane@acme.com or call +1 (555) 123-4567
My card 4111 1111 1111 1111 was charged twice

broken
App crashes when I click the login button on iOS
Hola, la aplicación se cierra cada vez que intento iniciar sesión
CSV

curl -s -X POST http://localhost:8000/uploads \
  -F "file=@/tmp/pulse_sample.csv;type=text/csv" | python -m json.tool
```

Expect (roughly): `created` 4, `blanks` 1 (the empty line), `duplicates` 1 (the
repeated crash line), `flagged` ≥ 2 (PII row → `pii_redacted`; `broken` →
`one_word`/`junk`/`needs_manual_review`); the Spanish row tagged `language: es`;
emails/phones/cards replaced with `[REDACTED_*]` in the stored title/body.

Boundary split on a pasted thread (plain text):

```bash
printf 'From: alice@acme.com\nMy order never arrived.\nFrom: bob@acme.com\nI was double charged.\n' > /tmp/pulse_thread.txt
curl -s -X POST http://localhost:8000/uploads \
  -F "file=@/tmp/pulse_thread.txt;type=text/plain" | python -m json.tool   # created: 2
```

Header behaviours:

```bash
# Explicit dev user (same fixed id) — works:
curl -s -X POST http://localhost:8000/uploads \
  -H "X-User-Id: 00000000-0000-0000-0000-000000000001" \
  -F "file=@/tmp/pulse_sample.csv;type=text/csv" -o /dev/null -w "%{http_code}\n"   # 201

# Malformed id → 400:
curl -s -X POST http://localhost:8000/uploads -H "X-User-Id: nope" \
  -F "file=@/tmp/pulse_sample.csv;type=text/csv" -o /dev/null -w "%{http_code}\n"   # 400
```

### Verify rows landed in the database

```bash
docker exec pulse-postgres psql -U pulse -d pulse -c \
  "select t.id as ticket, i.confidence, i.needs_manual_review, i.flags, i.week
     from tickets t join issues i on i.ticket_id = t.id
    order by t.created_at desc limit 10;"

# Confirm PII never reaches storage (should return 0 rows):
docker exec pulse-postgres psql -U pulse -d pulse -c \
  "select count(*) from issues where description ~ '@' or description ~ '[0-9]{13,16}';"
```

## Deferred to later phases
Multi-issue fan-out per ticket, real classification/severity/embeddings (the
`category`/`severity` default to `other`/`medium` and `embedding` is null for now),
and real auth replacing the `X-User-Id` stub.
