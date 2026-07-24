# Phase 4 — Dashboard (Next.js frontend)

A modern, dark "control-room" dashboard that a **non-technical user can operate
without explanation**: drag a file to upload, read the week's summary in plain
English, and browse tickets with their issues. Built with **Next.js (App
Router) + TypeScript + Tailwind CSS v4 + Recharts**, talking to the FastAPI
backend through one small typed fetch helper that sends the `X-User-Id` header.

## Where things live

### Frontend (`frontend/`)

| File | Holds |
| --- | --- |
| [frontend/package.json](../frontend/package.json) | deps + scripts (`dev`, `build`, `lint`, `typecheck`) |
| [frontend/next.config.mjs](../frontend/next.config.mjs), [tsconfig.json](../frontend/tsconfig.json), [postcss.config.mjs](../frontend/postcss.config.mjs) | Next / TS / Tailwind-v4 config |
| [frontend/.env.local.example](../frontend/.env.local.example) | `NEXT_PUBLIC_API_BASE_URL`, `NEXT_PUBLIC_USER_ID` |
| [frontend/src/lib/api.ts](../frontend/src/lib/api.ts) | **the fetch helper** — `apiFetch` + typed endpoint calls + `ApiError` |
| [frontend/src/lib/types.ts](../frontend/src/lib/types.ts) | TS mirrors of the backend response schemas |
| [frontend/src/lib/format.ts](../frontend/src/lib/format.ts) | ISO-week + label/display helpers |
| [frontend/src/lib/useAsync.ts](../frontend/src/lib/useAsync.ts) | one hook driving loading/error/success everywhere |
| [frontend/src/app/layout.tsx](../frontend/src/app/layout.tsx) | shell: sidebar nav + responsive frame |
| [frontend/src/app/page.tsx](../frontend/src/app/page.tsx) | **Overview** route (charts + weekly summary + week selector) |
| [frontend/src/app/tickets/page.tsx](../frontend/src/app/tickets/page.tsx) | **Tickets** route (issues grouped by ticket + filters) |
| [frontend/src/app/upload/page.tsx](../frontend/src/app/upload/page.tsx) | **Upload** route (drag/drop → upload summary) |
| [frontend/src/components/charts.tsx](../frontend/src/components/charts.tsx) | Recharts: category / urgency / sentiment-trend / themes |
| [frontend/src/components/WeeklySummaryPanel.tsx](../frontend/src/components/WeeklySummaryPanel.tsx) | prominent narrative + one-click generate |
| [frontend/src/components/TicketCard.tsx](../frontend/src/components/TicketCard.tsx) | one ticket, its issues, multi-issue badge, inline Analyse |
| [frontend/src/components/TicketFilters.tsx](../frontend/src/components/TicketFilters.tsx) | category / sentiment / confidence / needs-review filter bar |
| [frontend/src/components/WeekSelector.tsx](../frontend/src/components/WeekSelector.tsx) | recent-ISO-week dropdown |
| [frontend/src/components/{Card,Badge,StatTile,States,NavLink}.tsx](../frontend/src/components/) | shared UI: panels, pills, tiles, loading/error/empty, nav |

### Backend additions (to serve the browser)

| File | Holds |
| --- | --- |
| [src/app/api/routes/tickets.py](../src/app/api/routes/tickets.py) | **`GET /tickets`** — browse tickets with nested issues, filterable |
| [src/app/services/tickets.py](../src/app/services/tickets.py) | `list_tickets` — SQL fetch + issue-level filters + grouping |
| [src/app/schemas/ticket.py](../src/app/schemas/ticket.py) | `IssueOut`, `TicketOut`, `TicketListResponse` |
| [src/app/main.py](../src/app/main.py) | `CORSMiddleware` for the dashboard origin |
| [src/app/core/config.py](../src/app/core/config.py) | `cors_origins` (comma-separated `PULSE_CORS_ORIGINS`) |
| [tests/test_tickets_api.py](../tests/test_tickets_api.py) | grouping, filters, 422, empty-user (5 tests) |

## 1. The fetch helper (`src/lib/api.ts`)

Everything the browser sends to FastAPI goes through **one** function,
`apiFetch<T>`, so the auth header and error handling can never be forgotten:

- **Base URL** — `NEXT_PUBLIC_API_BASE_URL` (defaults to `http://localhost:8000/api`,
  already including the backend's `/api` prefix).
- **Identity** — attaches `X-User-Id` from `NEXT_PUBLIC_USER_ID`. Leave it blank
  and the backend falls back to its seeded dev user (Phase 1 stub), so local use
  "just works" with zero config.
- **Backend down vs. HTTP error** — `fetch` only rejects on a network-level
  failure, so a rejection becomes an `ApiError { kind: "network" }` → the UI
  shows a friendly "can't reach the server" state, never a blank screen. A non-2xx
  response is read as the backend's `{ detail: { code, message } }` shape and
  becomes an `ApiError { kind: "http", status, code }`.

Typed wrappers on top: `uploadFile`, `getStats`, `getSummary`, `generateSummary`,
`getTickets`, `analyzeTicket`. Components never call `fetch` directly.

`useAsync(loader, deps)` wraps any of these in a `{data, loading, error,
backendDown, reload}` state so all three routes render loading/error/success the
same way and can refetch after an action (generate summary, analyse ticket).

## 2. Upload route (`/upload`)

Drag-and-drop (or click) a CSV/PDF/text file → `POST /uploads` → renders the
**upload summary**: six headline tiles (detected / created / flagged / skipped /
duplicates / blank rows), a list of created items (language + confidence + any
flags / needs-review), and a list of skipped items with the reason. Busy and
error states are inline; a clean batch gets a "nothing needed flagging" note.

## 3. Overview route (`/`)

- **Week selector** (recent ISO weeks, or "All time") drives every query.
- **Weekly summary panel, front and centre** — fetches `GET /summaries/{week}`.
  If none exists yet (404) it shows a one-click **Generate summary** button that
  `POST`s and reloads. The headline, narrative, and recommended next steps are
  shown in plain language; a footer chip row shows avg sentiment / needs-review /
  top themes.
- **Charts from `GET /stats`** (Recharts), each with a one-line plain-English
  hint so a non-technical viewer knows what they're seeing:
  - **Category distribution** — coloured bar per category.
  - **Urgency breakdown** — severity low→critical.
  - **Sentiment over time** — avg sentiment (−1..1) and urgency per week.
  - **Top themes** — horizontal bars, biggest driver first.
- Headline tiles (total issues, most common category, sentiment, critical count)
  and an empty state that points at Upload/Tickets when there's no data.

Chart colours are read from the CSS design tokens in `globals.css`, so a category
is the same colour in a chart, a badge, and a tile.

## 4. Tickets route (`/tickets`)

- **Filter bar** — category / sentiment / confidence / needs-manual-review, with
  a Clear button. Changing a filter refetches `GET /tickets` with the params.
- **Issues grouped by ticket** — each ticket is a card; issues nest inside. A
  ticket with more than one issue shows an **"N issues" badge** (the multi-issue
  fan-out). Each issue shows category + severity badges, sentiment/urgency/
  confidence, its **themes** as `#tags`, and a needs-review flag when set.
- **Inline Analyse** — a ticket whose issues haven't been through the AI pipeline
  yet (no `analyzed_at`) shows an **Analyse** button that calls
  `POST /tickets/{id}/analyze` and reloads, so the whole flow is operable from the
  UI without touching Swagger.

The filters narrow the *issues*: a ticket appears only if ≥1 of its issues match,
and only the matching issues are nested (so the badge count reflects what's shown).

## 5. Backend `GET /tickets`

`list_tickets(db, user_id, *, category, sentiment, min_confidence,
needs_manual_review, limit, offset)` — pure SQL, no LLM:

1. Find ticket ids owning ≥1 issue that passes the filters (`EXISTS` subquery),
   scoped to the acting user, newest first; count for `total`.
2. Fetch that page of tickets with their issues.
3. Attach only the issues that match the filters; `issue_count` = shown issues.

`sentiment` is a label mapped to a score band (`negative` ≤ −0.2, `neutral`
−0.2..0.2, `positive` ≥ 0.2). An unknown `category`/`sentiment` → **422**
`invalid_filter` (never a 500).

## 6. CORS

`app.main` adds `CORSMiddleware` for `settings.cors_origins` (default the Next.js
dev server on `:3000`; override with comma-separated `PULSE_CORS_ORIGINS`). The
`X-User-Id` header is allowed via `allow_headers=["*"]`.

## Per-file reference (frontend)

### lib/api.ts
- `ApiError` — typed failure; `.isBackendDown` when the server is unreachable.
- `apiFetch<T>(path, init)` — base URL + `X-User-Id` + error mapping.
- `uploadFile`, `getStats`, `getSummary`, `generateSummary`, `getTickets`,
  `analyzeTicket` — typed endpoint calls.

### lib/useAsync.ts
- `useAsync(loader, deps)` → `{data, loading, error, backendDown, reload}`.

### lib/format.ts
- `currentIsoWeek()` / `recentIsoWeeks(n)` — ISO week strings matching the
  backend's `iso_week`. `humanize`, `sentimentWord`, `pct` — display helpers.

### components
- `Card` — titled panel with a plain-language `hint`.
- `Badge` / `CountChip` / `ReviewFlag` — colour-coded category/severity pill,
  "N issues" chip, amber needs-review flag.
- `StatTile` — one big-number tile.
- `States` — `Skeleton`, `LoadingCard`, `ErrorState` (friendly backend-down copy
  + retry), `EmptyState`.
- `charts` — `CategoryChart`, `UrgencyChart`, `SentimentTrendChart`, `ThemesChart`.
- `WeekSelector`, `WeeklySummaryPanel`, `TicketFilters`, `TicketCard`, `NavLink`.

## Test it yourself (manual)

### Prereqs

Backend running (Phases 0–3): Postgres on your configured port, Redis, migrations
applied, and — for live analysis/summaries — `PULSE_OPENAI_API_KEY` set. `/stats`,
`GET /tickets`, and `GET /summaries` are pure reads and work without a key.

### Step 1 — start the backend

```bash
cd /Users/bhavya/Desktop/PulseAI
conda activate pulseai
docker compose up -d
alembic upgrade head
uvicorn app.main:app --reload --app-dir src   # http://localhost:8000
```

### Step 2 — start the frontend

```bash
cd frontend
cp .env.local.example .env.local     # defaults are fine for local use
npm install
npm run dev                          # http://localhost:3000
```

Open **http://localhost:3000**.

> **One command for both:** from the repo root, `./scripts/start-dev.sh` starts
> the backend *and* the dashboard together (Ctrl-C stops both) — it installs
> frontend deps and creates `frontend/.env.local` on first run. Flags:
> `--backend-only`, `--frontend-only`; ports via `BACKEND_PORT` / `FRONTEND_PORT`.
> It assumes infra is up (`docker compose up -d`).

### Step 3 — exercise all three routes

1. **Upload** (`/upload`): drag `../sample_tickets.csv` (or any CSV/PDF/txt) onto
   the drop zone. You should see the upload summary: created / skipped / flagged
   counts, plus per-item detail.
2. **Tickets** (`/tickets`): the uploaded tickets appear. Click **Analyse** on a
   ticket to run the AI pipeline (needs an OpenAI key); multi-issue tickets get an
   "N issues" badge. Try the category / sentiment / confidence / needs-review
   filters.
3. **Overview** (`/`): pick the current week. If no summary exists, click
   **Generate summary** (needs a key). The narrative shows at the top; the charts
   (category, urgency, sentiment-over-time, top themes) render below.

### Step 4 — verify the friendly failure state

Stop the backend (`Ctrl-C`) and reload any page. Instead of a blank screen or a
stack trace you get the **"can't reach the server"** state with a Try-again
button. Restart the backend and retry — it recovers.

### Automated checks

```bash
# Backend (still green after the /tickets endpoint + CORS):
pytest -q                      # 114 passing (auto-skips DB tests if Postgres is down)

# Frontend:
cd frontend
npm run typecheck              # tsc --noEmit — clean
npm run build                  # production build: all routes compile + lint
```

## Notes / known items
- `npm audit` reports transitive advisories from `sharp`'s bundled libvips
  (Next's image optimizer). The dashboard doesn't process untrusted images and
  the direct `next` advisory is patched (15.5.x). `npm audit fix --force` would
  downgrade Next to 9.x, so it's intentionally not applied.
- The frontend never imports server code or secrets; it only reads the two
  `NEXT_PUBLIC_*` values. Auth is still the Phase 1 dev stub (`X-User-Id`).
