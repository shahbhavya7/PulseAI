# Phase 3 — Insights (embeddings, themes, weekly summary, dashboard)

The final phase turns analyzed issues into insight: vector embeddings, merged
themes with example quotes, a VP-actionable weekly summary, and a SQL dashboard.

**Embedding model:** OpenAI **`text-embedding-3-small`** (1536 dims — matches
`app.models.issue.EMBEDDING_DIM`), configurable via `PULSE_OPENAI_EMBEDDING_MODEL`.

## Where things live

| File | Holds |
| --- | --- |
| [src/app/services/vector_store.py](../src/app/services/vector_store.py) | `VectorStore` interface + `OpenAIVectorStore` (embeddings) + `get_vector_store` |
| [src/app/services/insights.py](../src/app/services/insights.py) | `aggregate_themes` — normalise/merge themes → ranked `{theme,count,examples}` |
| [src/app/services/summaries.py](../src/app/services/summaries.py) | weekly summariser: metrics + themes + LLM narrative, upsert per `(user, week)` |
| [src/app/services/stats.py](../src/app/services/stats.py) | `compute_stats` — dashboard aggregates, all SQL, filterable |
| [src/app/services/llm.py](../src/app/services/llm.py) | + `summarize_week` (structured weekly-brief call) |
| [src/app/services/pipeline.py](../src/app/services/pipeline.py) | + `_embed_issues` — embed on write, mark `needs_reembed` on failure |
| [src/app/schemas/summary.py](../src/app/schemas/summary.py) | `ThemeCount`, `SummaryMetrics`, `WeeklySummaryContent` (LLM), `SummaryResponse` |
| [src/app/schemas/stats.py](../src/app/schemas/stats.py) | `StatsResponse`, `SentimentPoint`, `StatsFilters` |
| [src/app/api/routes/summaries.py](../src/app/api/routes/summaries.py) | `POST /summaries/{week}`, `GET /summaries/{week}` |
| [src/app/api/routes/stats.py](../src/app/api/routes/stats.py) | `GET /stats` |
| [src/app/models/issue.py](../src/app/models/issue.py) | + `needs_reembed` (the embedding column existed since 0001) |
| [src/app/models/weekly_summary.py](../src/app/models/weekly_summary.py) | + `user_id`, unique `(user_id, week)` |
| [alembic/versions/0003_embeddings_and_user_week.py](../alembic/versions/0003_embeddings_and_user_week.py) | migration for the above |
| [tests/](../tests/) | `test_vector_store.py`, `test_insights.py`, `test_insights_api.py` |

## 1. Embeddings behind a VectorStore interface

`VectorStore` is a `Protocol` with `embed(texts)` / `embed_one(text)`.
`OpenAIVectorStore` implements it against `text-embedding-3-small` and validates
the returned dimension. Callers depend on the Protocol, so tests inject a fake.

**Embed on write, never lose a row.** `analyze_and_persist` (Phase 2) now calls
`_embed_issues` in the *same flow* as the row write:

- success → each issue gets its `embedding`, `needs_reembed=False`.
- any `LLMError` (missing key, API error, dim mismatch) → the issues are **kept**
  with `embedding=None` and `needs_reembed=True`, logged, so a later job can
  retry. A transient embedding failure never drops an issue.

`ix_issues_needs_reembed` indexes that flag so "find rows to re-embed" is cheap.

## 2. Theme aggregation (`aggregate_themes`)

Given the free-text `themes` stored on each issue for a period:

1. **normalise** — lowercase, trim, collapse whitespace, strip edge punctuation.
2. **merge near-identical** — labels with a `difflib` similarity ≥ 0.82 collapse
   into one group (e.g. "photo-upload crash" ≈ "photo upload crashes"); the
   highest-count label becomes canonical.
3. **rank** — by total issue count, take the top `limit`.
4. **example quotes** — embed the canonical theme and pull the nearest issues by
   **pgvector cosine distance** (`Issue.embedding.cosine_distance(...)`); if no
   vector store / key / embeddings, fall back to quotes from the group's issues.

Returns `list[ThemeCount]` = `{theme, count, examples}`.

## 3. Weekly summariser

`generate_summary(db, user, week)`:

1. selects **only** that ISO week's issues for the user,
2. computes `SummaryMetrics` from them (category/severity counts, needs-review,
   avg sentiment/urgency),
3. aggregates themes (grounded with pgvector examples),
4. builds a text context (issues are DATA, capped) and calls `llm.summarize_week`
   → structured `WeeklySummaryContent` (headline, narrative, recommendations),
5. **upserts one `WeeklySummary` row per `(user, week)`** — regenerating updates
   the same row. Narrative is stored in `content`; headline/recommendations/
   themes/metrics in `stats` (JSONB), so `GET` rebuilds the response with no
   recompute.

`NoIssuesForWeekError` → 404; `LLMError` → 503 (graceful). `GET /summaries/{week}`
returns the stored row (404 if never generated).

## 4. Dashboard `GET /stats`

`compute_stats` is **pure SQL** (no LLM), filterable by any combination of
`week`, `min_confidence`, `needs_manual_review`:

- `category_distribution` — `GROUP BY category`.
- `urgency_counts` — `GROUP BY severity` (low/medium/high/critical).
- `sentiment_over_time` — `avg(sentiment)`, `avg(urgency)`, count `GROUP BY week`.
- `top_themes` — reuses `aggregate_themes` (fallback quotes; no key needed).

Every query is scoped to the acting user via a shared `_base_filters` join.

## Per-function reference

### services/vector_store.py
- `VectorStore` (Protocol) — `embed(texts)`, `embed_one(text)`.
- `OpenAIVectorStore.embed` — batch embed; raises `LLMConfigError` (no key) or
  `LLMCallError` (API error / dim mismatch). `.embed_one` wraps it.
- `get_vector_store()` — cached default store.

### services/insights.py
- `_normalise_theme(label)` — canonicalise a label.
- `issues_for_period(db, user_id, week)` — the user's issues, optional week.
- `_example_quotes(...)` — pgvector-nearest quotes, else fallbacks.
- `aggregate_themes(db, user_id, *, week, limit, vector_store, issues)` →
  `list[ThemeCount]`.

### services/summaries.py
- `NoIssuesForWeekError` — raised when a week is empty.
- `_metrics(issues)` → `SummaryMetrics`.
- `_build_context(issues, metrics, themes)` — LLM input text (issues as DATA).
- `generate_summary(db, user, week, *, summarizer, vector_store)` → upserted
  `WeeklySummary`.
- `get_summary(db, user, week)` → row or None.
- `to_response(summary)` → `SummaryResponse` from the stored row.

### services/stats.py
- `_base_filters(stmt, user_id, *, week, min_confidence, needs_manual_review)` —
  shared WHERE clauses.
- `compute_stats(db, user_id, *, week, min_confidence, needs_manual_review,
  vector_store)` → `StatsResponse`.

### services/llm.py (added)
- `summarize_week(context, *, client)` → `WeeklySummaryContent` (structured;
  data-delimited `<week_data>`; typed errors).

### services/pipeline.py (added)
- `_embed_issues(vector_store, issues)` — embed-on-write with re-embed fallback;
  `analyze_and_persist(..., vector_store=None)` calls it after building rows.

### api/routes
- `POST /summaries/{week}` (`create_summary`), `GET /summaries/{week}`
  (`read_summary`), `GET /stats` (`get_stats`).

## Test it yourself (manual)

Prereqs: Postgres on **5433** (see Phase 1 note), conda env, migrations up, and an
OpenAI key for the real model/embeddings.

```bash
cd /Users/bhavya/Desktop/PulseAI
conda activate pulseai
docker compose up -d
alembic upgrade head          # applies 0003
export PULSE_OPENAI_API_KEY=sk-...
uvicorn app.main:app --reload --app-dir src
```

### Step 1 — upload a realistic multi-issue batch

```bash
cat > /tmp/pulse_batch.csv <<'CSV'
text
The app crashes every time I upload a photo, and I was also charged twice this month.
Export button does nothing since the last update. Not urgent but annoying.
No rush, but I can see another customer's saved card in my account.
La app se cierra al subir una foto. Please fix, it crashes every time.
CSV

curl -s -X POST localhost:8000/uploads -F 'file=@/tmp/pulse_batch.csv;type=text/csv' \
  | python -m json.tool
```

### Step 2 — analyze each ticket (fan-out + embed on write)

```bash
# Analyze every ticket the upload created:
curl -s localhost:8000/stats >/dev/null   # warms nothing; just here for clarity
for TID in $(curl -s -X POST localhost:8000/uploads -F 'file=@/tmp/pulse_batch.csv;type=text/csv' \
             | python -c "import sys,json;[print(i['ticket_id']) for i in json.load(sys.stdin)['created_items']]"); do
  curl -s -X POST "localhost:8000/tickets/$TID/analyze" | python -c "import sys,json;d=json.load(sys.stdin);print('ticket',d['ticket_id'],'->',d['created'],'issues')"
done
```

### Step 3 — generate the weekly summary, then read it back

```bash
WEEK=$(python -c "from datetime import datetime,timezone;y,w,_=datetime.now(timezone.utc).isocalendar();print(f'{y}-W{w:02d}')")
echo "week=$WEEK"
curl -s -X POST "localhost:8000/summaries/$WEEK" | python -m json.tool   # generate
curl -s "localhost:8000/summaries/$WEEK" | python -m json.tool           # read back
```

### Step 4 — hit the dashboard

```bash
curl -s "localhost:8000/stats?week=$WEEK" | python -m json.tool
# Filters:
curl -s "localhost:8000/stats?week=$WEEK&needs_manual_review=true" | python -m json.tool
curl -s "localhost:8000/stats?min_confidence=0.8" | python -m json.tool
```

### Verify embeddings landed (and re-embed marker)

```bash
docker exec pulse-postgres psql -U pulse -d pulse -c \
  "select count(*) filter (where embedding is not null) as embedded,
          count(*) filter (where needs_reembed) as to_reembed,
          count(*) as total from issues;"
```

### Headless confirmation (no server, no key)

`upload → analyze → summary → read-back → stats` is proven headless in-process
with the model/embedder faked — see the automated end-to-end test:

```bash
pytest tests/test_insights_api.py -q      # requires Postgres; auto-skips if down
pytest -q                                 # whole suite: 109 passing
```

## Graceful degradation recap
- No key / API error during **analysis** or **summary** → **503** `ai_unavailable`.
- Embedding failure during write → row kept, `needs_reembed=True` (no 5xx).
- `/stats` and `GET /summaries/{week}` are pure SQL/stored-row reads → always work.
