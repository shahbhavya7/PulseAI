# Phase 7 — Hardening & evidence

Final polish: prove every external call fails **gracefully** (never a crash),
prove the classifier's accuracy on **blind inputs**, and make the repo a clean
**cold start**. Nothing here changes product behaviour — it makes the failure
modes explicit and the quality measurable.

## Where things live

| File | What |
| --- | --- |
| [src/app/api/errors.py](../src/app/api/errors.py) | global exception handlers: DB error → 503, catch-all → 500 (no leak) |
| [src/app/main.py](../src/app/main.py) | registers the handlers |
| [tests/test_hardening.py](../tests/test_hardening.py) | `/ready` degradation + DB-error-on-route + probes-never-raise |
| [scripts/eval_accuracy.py](../scripts/eval_accuracy.py) | accuracy harness → `docs/accuracy.md` |
| [tests/data/accuracy_set.jsonl](../tests/data/accuracy_set.jsonl) | 18 labelled blind tickets (disjoint from few-shot) |
| [tests/test_accuracy_harness.py](../tests/test_accuracy_harness.py) | CI guards: dataset valid, blind, covers every category |
| [docs/accuracy.md](accuracy.md) | generated accuracy report + confusion matrix |
| [DEMO.md](../DEMO.md) | mentor click-path mapped to rubric M5A–M5S |

## 1. API-failure hardening

The principle: **a dependency being down degrades the response; it never crashes
the request.** Each external call is handled at the layer that knows how to
degrade it.

| Dependency | Failure | Behaviour | Where |
| --- | --- | --- | --- |
| **OpenAI** (analysis) | no key / API error | `LLMError` → **503 `ai_unavailable`** | `pipeline` → `routes/analyze`,`summaries` |
| **OpenAI** (chat) | no key / API error | streams a friendly "assistant unavailable" line; turn still persisted | `services/chat.stream_turn` |
| **OpenAI** (embeddings) | no key / API error | issue kept, flagged `needs_reembed`; retrieval degrades to facts-only | `pipeline._embed_issues`, `chat_retrieval` |
| **Redis** (AI cache) | unreachable | best-effort: read misses, write dropped; request proceeds | `services/ai_cache` |
| **Database** (readiness) | unreachable | `/ready` → **503** with per-dependency breakdown; probe returns False, never raises | `services/health`, `db.ping_db` |
| **Database** (domain request) | error mid-request | **503 `database_unavailable`** via global handler (no leaked 500/stack) | `api/errors._handle_db_error` |
| **anything else** | unhandled | **500 `internal_error`**, detail logged not leaked | `api/errors._handle_unexpected` |

Key addition this phase: the **global `SQLAlchemyError` handler**. Before it, a
DB that dropped mid-request surfaced as a bare 500 with a traceback; now it's a
small typed JSON body. The health probes were already non-raising (Phase 0);
Phase 7 adds the test evidence.

### Test it yourself

```bash
# Automated (no live deps needed — uses fakes):
pytest tests/test_hardening.py -q
```

- `test_ready_degrades_to_503_when_db_down` / `…redis_down` — `/ready` returns
  503 with the failing dependency marked, status 200 when both up.
- `test_ping_probes_never_raise` — the probes swallow a thrown client and return
  False, so readiness can't crash.
- `test_db_error_on_domain_route_returns_503` — a request whose session factory
  raises `OperationalError` gets a clean `503 database_unavailable`.

Manual — watch it degrade live:

```bash
uvicorn app.main:app --app-dir src        # backend up
docker stop pulse-postgres                 # kill the DB
curl -s -o /dev/null -w "%{http_code}\n" localhost:8000/ready      # → 503
docker start pulse-postgres                # readiness recovers → 200
# LLM off (no key): POST /api/analyze → 503 ai_unavailable, never a 500.
```

## 2. Classifier accuracy on blind inputs

`scripts/eval_accuracy.py` runs `tests/data/accuracy_set.jsonl` — **18 labelled
tickets** spanning all five categories — through the real classification pipeline
and writes [docs/accuracy.md](accuracy.md) (accuracy, per-class precision/recall,
confusion matrix, misclassifications).

**Why it's a fair test.** The set was authored to be diverse and realistic
(distinct from the sample data), and the harness **asserts it is disjoint from
the four few-shot examples** baked into the prompt before scoring — so a high
score reflects generalisation, not memorisation. `test_accuracy_harness.py`
enforces this disjointness (and full-category coverage) in CI, even though the
eval itself needs a live key.

Latest run: **18/18 = 100%** (see [docs/accuracy.md](accuracy.md)). Reproduce:

```bash
export PULSE_OPENAI_API_KEY=sk-...
python scripts/eval_accuracy.py            # prints per-item + rewrites docs/accuracy.md
python scripts/eval_accuracy.py --dry-run  # inspect the set without calling the model
```

> The labelled set is intended to be generated/expanded with a **separate** model
> (e.g. a local Qwen3) so the labels are independent of the GPT classifier under
> test. Add lines to the JSONL and re-run; the harness re-checks disjointness.

## 3. Cold start & repo hygiene

- **Clone → running in ~5 min** — see the README "Cold start" section: `cp
  .env.example .env` → `docker compose up -d` → `pip install -e ".[dev]"` →
  `alembic upgrade head` → `./scripts/start-dev.sh`. Email sign-in
  (`dev@pulseai.local` / `pulseai-dev`) works with zero OAuth setup.
- **`.env.example` complete** — every tunable setting has an entry; secrets are
  commented placeholders. Verified against `core/config.py`.
- **No secrets in the repo** — `.env` / `*.env` / `.p8` are git-ignored (only
  `.env.example` is tracked); a scan for key patterns (`sk-…`, private keys)
  finds nothing in tracked non-example files.
- **Green suite** — `ruff check .` ✓, `ruff format --check .` ✓, `mypy` ✓,
  `pytest` → **145 passing** (unit + edge-case + integration; DB-backed tests
  auto-skip when Postgres is absent, so the suite is hermetic).
- **Consistent history** — commits map to phases (`Phase 1 …` → `phase 6 …`).

### Full check block (matches the README)

```bash
ruff check . && ruff format --check .
mypy
pytest
```
