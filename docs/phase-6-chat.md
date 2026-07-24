# Phase 6 — Chat over pgvector (hybrid retrieval + cross-session memory)

A grounded data assistant: the user asks about their tickets in natural language
and gets an answer built from **exact SQL facts + semantically-relevant issue
examples**, streamed token-by-token. Postgres holds the transcript (source of
truth); pgvector holds the issue-text embeddings (Phase 3, on `issues.embedding`)
and a new per-session **memory** embedding. Everything is scoped to the
authenticated user — chat can only ever read that user's own data.

## Where things live

| File | Holds |
| --- | --- |
| [src/app/models/session_summary.py](../src/app/models/session_summary.py) | `SessionSummary` — embedded per-session memory note (pgvector) |
| [alembic/versions/0006_session_summaries.py](../alembic/versions/0006_session_summaries.py) | migration for the memory table |
| [src/app/services/chat_retrieval.py](../src/app/services/chat_retrieval.py) | `retrieve_context` — hybrid: SQL facts (`compute_stats`) + pgvector issue examples |
| [src/app/services/chat_memory.py](../src/app/services/chat_memory.py) | `summarize_session` (write memory) + `recall_summaries` (read) |
| [src/app/services/chat.py](../src/app/services/chat.py) | orchestration: sessions, `stream_turn`, `end_session`, `sweep_idle_sessions` |
| [src/app/services/llm.py](../src/app/services/llm.py) | + `stream_chat_answer`/`answer_chat` (grounded), `summarize_chat_session` |
| [src/app/api/routes/chat.py](../src/app/api/routes/chat.py) | `/chat/sessions*`, SSE `messages`, `end`, `sweep` |
| [src/app/schemas/chat.py](../src/app/schemas/chat.py) | request/response models |
| [src/app/core/config.py](../src/app/core/config.py) | `chat_retrieval_k`, `chat_memory_k`, `chat_history_window`, `chat_idle_minutes` |
| [tests/test_chat.py](../tests/test_chat.py) | retrieval, memory write/recall, isolation, streamed session flow (7 tests) |
| [frontend/src/app/chat/page.tsx](../frontend/src/app/chat/page.tsx) | threaded chat UI: session list, streaming bubbles, states |
| [frontend/src/lib/api.ts](../frontend/src/lib/api.ts) | `streamMessage` (SSE reader) + session helpers |
| [frontend/src/components/TopNav.tsx](../frontend/src/components/TopNav.tsx) | Chat nav link |

## How it works

### 1. Hybrid retrieval (`chat_retrieval.retrieve_context`)

For each question we assemble two grounded, **user-scoped** blocks:

- **Facts** — `compute_stats(db, user_id, week=…)`: totals, category distribution,
  severity counts, sentiment/urgency trend, top themes. Exact SQL numbers the
  model must use verbatim.
- **Examples** — embed the question, then `Issue.embedding.cosine_distance(...)`
  ordered nearest-first, filtered by `Ticket.owner_id == user` (+ optional
  `week`/`category`). These are real tickets the model can cite.

Facts are always computed (pure SQL). Examples are best-effort: no key /
embeddings → `semantic_ok=False` and the chat degrades to facts-only rather than
failing.

### 2. Transcript (source of truth)

Every turn is persisted to `chat_messages` (role/content), ordered by
`created_at`, under a `chat_sessions` row. `stream_turn` writes the user message,
then the assistant message once the stream completes. The prompt only carries the
last `chat_history_window` turns; older turns fall out of the window but their
durable facts survive via memory (below).

### 3. Grounded generation (`llm.stream_chat_answer`)

The system prompt (`_CHAT_RULES`) hard-codes the guardrails: answer **only** from
the `<context>` block, never invent numbers/tickets, never claim access to other
users' data, say "not in your data" when unknown. Context (facts + examples +
memory) is wrapped in `<context>` tags and treated as DATA. Tokens stream out;
the route relays them as SSE. If the stream returns zero tokens (rare), it falls
back once to the non-streaming `answer_chat`.

### 4. Cross-session memory (the design)

**Write** — when a session ends (`POST /chat/sessions/{id}/end`) or is swept for
idleness (`POST /chat/sweep`, sessions older than `chat_idle_minutes`),
`summarize_session`:
1. renders the transcript,
2. `llm.summarize_chat_session` distils it into 1–4 sentences of **durable facts
   and preferences** (not numbers, not chit-chat),
3. embeds that note and upserts one `SessionSummary` row per session, tagged by
   `user_id`.

We deliberately **embed the summary, never the raw messages**: it keeps memory
compact, avoids re-embedding transcript noise, and stores what's worth
remembering. The full transcript still lives in `chat_messages`.

**Read** — on any turn, `recall_summaries(user_id, question)` returns the user's
top `chat_memory_k` prior notes by pgvector similarity to the question (excluding
the current session), falling back to most-recent when embeddings are
unavailable. Those notes go into the `<context>` block, so a brand-new session
remembers earlier ones.

**Isolation** — both the write (`user_id` stamped) and read (`WHERE user_id =`)
are user-scoped, so one user's memory can never surface for another.

### 5. Streaming API + frontend

`POST /chat/sessions/{id}/messages` returns `text/event-stream`; each token is a
`data: {"token": "..."}` line, closed by `event: done`. The frontend
`streamMessage` reads the body with a `ReadableStream` reader, parses SSE frames,
and calls `onToken` so the chat bubble fills in live. The `/chat` page shows the
session list, threaded bubbles (user right, assistant left with a typing
indicator), suggestion chips, and loading/error states. Leaving the page calls
`end` so the session is summarised into memory.

### 6. Guardrails & degradation
- **Own data only** — every SQL query filters by the authenticated `user_id`; the
  prompt forbids outside knowledge and cross-user claims.
- **LLM/DB failure** — a grounded-answer failure streams a friendly "assistant
  unavailable" sentence (still 200, still persisted), never a 500. Missing
  embeddings → facts-only. Stats failure → memory/examples still answer.
- **Prompt injection** — retrieved data lives inside `<context>` tags and is
  declared DATA, mirroring the Phase 2 defence.

## Per-function reference

### services/chat_retrieval.py
- `retrieve_context(db, user_id, question, *, week, category, vector_store)` →
  `ChatContext{stats, examples, semantic_ok}`.
- `_semantic_examples(...)` — pgvector nearest issues, user/week/category-scoped.

### services/chat_memory.py
- `summarize_session(db, session, *, vector_store, summarizer)` → upserted
  `SessionSummary | None`.
- `recall_summaries(db, user_id, query, *, exclude_session_id, vector_store)` →
  `list[str]`.

### services/chat.py
- `create_session` / `get_session` / `list_sessions` / `list_messages`.
- `stream_turn(db, user, session, question, *, week, category, vector_store)` →
  token iterator (persists both messages; degrades gracefully).
- `end_session(db, user, session)` — archive + write memory.
- `sweep_idle_sessions(db, user, *, now)` → count swept.

### services/llm.py (added)
- `stream_chat_answer(system_context, history)` → token `Iterator[str]`.
- `answer_chat(...)` — non-streaming variant (zero-token fallback).
- `summarize_chat_session(transcript)` → memory note string.

### api/routes/chat.py
- `create_session`, `list_sessions`, `get_session`, `send_message` (SSE),
  `end_session`, `sweep`.

## Test it yourself (manual)

Prereqs: signed in (Phase 5) and an `PULSE_OPENAI_API_KEY` set (chat needs the
model + embeddings). Migrations up (`alembic upgrade head` applies 0006).

```bash
docker compose up -d && alembic upgrade head
uvicorn app.main:app --reload --app-dir src      # :8000
cd frontend && npm run dev                          # :3000
```

### Ask a data question (cites real issues)

1. Sign in (e.g. **dev@pulseai.local** / **pulseai-dev** — this account owns the
   existing tickets) and open **Chat**.
2. Ask: *"What are my most common categories and how many critical issues do I
   have?"*
3. The answer **streams in** and cites your real numbers (e.g. "other 116,
   incident 13 … 10 critical") and a real ticket example. It won't invent data —
   ask about something you don't have and it says so.

### Confirm cross-session memory

1. In one chat say: *"I mostly care about billing and duplicate-charge problems.
   Remember that."* Then leave the page (or `POST /chat/sessions/{id}/end`) — this
   writes an embedded session summary.
2. Start a **New chat** and ask: *"Based on what you know I care about, what
   should I look at first?"*
3. It recalls the preference from the previous session and points you at the
   billing / duplicate-charge tickets first.

### Automated

```bash
pytest -q                 # 138 passing (chat: retrieval, memory, isolation, SSE flow)
cd frontend && npm run build && npm run lint    # green, all routes static
```

Isolation is covered by `test_memory_is_user_scoped` and
`test_chat_other_users_session_404`; graceful degradation by
`test_chat_degrades_when_llm_unavailable`.
