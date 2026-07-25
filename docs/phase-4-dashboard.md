# Phase 4 — Dashboard (Next.js frontend)

A modern, dark "control-room" dashboard that a **non-technical user can operate
without explanation**: drag a file to upload, read the week's summary in plain
English, and browse tickets with their issues. Built with **Next.js (App
Router) + TypeScript + Tailwind CSS v4 + shadcn/ui + Recharts**, talking to the
FastAPI backend through one small typed fetch helper that sends the `X-User-Id`
header.

**Look & feel:** a **true-black** canvas with one vivid accent (**electric
cyan**), glassmorphism throughout (frosted `backdrop-blur` surfaces over an
animated **aurora** gradient), motion via **framer-motion** (route fade-ups,
staggered card entrances, hover lifts, count-up numbers, chart draw-in, a gliding
active-nav pill), and **lucide-react** icons everywhere — no emojis. shadcn/ui
primitives (Button, Card, Select, Badge, Skeleton, Tooltip, Checkbox, Separator)
are copied into `src/components/ui/` and tuned to the dark glass theme.

**Smart, not just charts:** a hero **insight strip** states the week's headline
finding in plain language, stat tiles show **week-over-week deltas**, the most
urgent theme is highlighted, and charts are **interactive** (hover detail,
click-a-category-bar to filter Tickets) — all derived from the existing `/stats`
and `/summaries`, no new backend.

## Where things live

### Frontend (`frontend/`)

| File | Holds |
| --- | --- |
| [frontend/package.json](../frontend/package.json) | deps + scripts (`dev`, `build`, `lint`, `typecheck`) |
| [frontend/next.config.mjs](../frontend/next.config.mjs), [tsconfig.json](../frontend/tsconfig.json), [postcss.config.mjs](../frontend/postcss.config.mjs) | Next / TS / Tailwind-v4 config |
| [frontend/.env.local.example](../frontend/.env.local.example) | `NEXT_PUBLIC_API_BASE_URL`, `NEXT_PUBLIC_USER_ID` |
| [frontend/components.json](../frontend/components.json) | shadcn/ui config (new-york style, lucide icons, `@/` aliases) |
| [frontend/src/components/ui/](../frontend/src/components/ui/) | shadcn primitives: button, card, badge, select, checkbox, skeleton, tooltip, separator |
| [frontend/src/lib/utils.ts](../frontend/src/lib/utils.ts) | `cn()` class merger (clsx + tailwind-merge) |
| [frontend/src/lib/icons.ts](../frontend/src/lib/icons.ts) | domain→lucide icon maps (category/severity/skip-reason) + colour token |
| [frontend/src/lib/insight.ts](../frontend/src/lib/insight.ts) | **smart derivations**: `buildHeroInsight`, `delta`, `mostUrgentTheme` (pure) |
| [frontend/src/components/AuroraBackground.tsx](../frontend/src/components/AuroraBackground.tsx) | fixed animated aurora backdrop (z-0) + dot grid + vignette |
| [frontend/src/components/HeroInsight.tsx](../frontend/src/components/HeroInsight.tsx) | the hero insight strip (tone-glowing headline finding) |
| [frontend/src/components/CountUp.tsx](../frontend/src/components/CountUp.tsx) | number count-up on first render (reduced-motion aware) |
| [frontend/src/components/motion.tsx](../frontend/src/components/motion.tsx) | framer-motion helpers: PageTransition, MotionStagger/Item, MotionCard |
| [frontend/src/lib/api.ts](../frontend/src/lib/api.ts) | **the fetch helper** — `apiFetch` + typed endpoint calls + `ApiError` |
| [frontend/src/lib/types.ts](../frontend/src/lib/types.ts) | TS mirrors of the backend response schemas |
| [frontend/src/lib/format.ts](../frontend/src/lib/format.ts) | ISO-week + label/display helpers |
| [frontend/src/lib/useAsync.ts](../frontend/src/lib/useAsync.ts) | one hook driving loading/error/success everywhere |
| [frontend/src/app/globals.css](../frontend/src/app/globals.css) | shadcn tokens (dark), domain colours, glass utilities, animation keyframes |
| [frontend/src/components/TopNav.tsx](../frontend/src/components/TopNav.tsx) | **floating glass top navbar** (sticky, inset, slides down on mount) |
| [frontend/src/components/NavLink.tsx](../frontend/src/components/NavLink.tsx) | top-nav link + horizontally-gliding active pill (`layoutId`) |
| [frontend/src/app/layout.tsx](../frontend/src/app/layout.tsx) | shell: floating top nav + aurora background + full-width content below it |
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

## 0. Design system (shadcn + glass + motion + icons)

### Root-cause fix — why glass looked flat, and what fixed it

The infrastructure existed but didn't *render*. Diagnosis:

- **Theme & motion were fine.** `<html class="dark">` was present, `--background`
  resolved, the `.glass` rules compiled intact, framer-motion mounted in SSR
  (`opacity:0;transform:…`), and `prefers-reduced-motion` wasn't force-disabling
  in normal mode. None of these were the bug.
- **The bug: glass had no live backdrop to blur.** `<AuroraBackground>` was
  `position: fixed; z-index: -10` **and** carried `bg-background` (opaque
  near-black). A negative-z fixed layer renders *behind* the page's own
  background canvas, and its own opaque fill painted over the blobs. So every
  `.glass` panel's `backdrop-filter: blur()` sampled **uniform black** — blurring
  solid black yields solid black. Glass read as a flat card.

**Fix:**
1. Aurora moved to `z-0` (not `-z-10`), with **no opaque background** — it only
   paints the drifting blobs + dot grid + vignette.
2. `body` background set to **`transparent`**; the base near-black lives once on
   `<html>` (plus a faint cyan/violet radial lift so even "empty" areas aren't
   uniform).
3. App content wrapped in `relative z-10` so it sits above the aurora and every
   glass surface blurs the moving colour behind it.

Verified in the production build: compiled `.glass` carries
`backdrop-filter: blur(20px) saturate(180%)` over a ~55%-alpha gradient, `body`
is transparent, and the aurora layer is `fixed inset-0 z-0` with
`animate-aurora-*` blobs.

### Theme tokens (true-black, one vivid accent)

Dark-only. shadcn tokens are HSL triplets in `:root`, exposed to Tailwind v4 via
`@theme inline`; domain colours are hex (read directly by charts/badges).

| Token | Value | Role |
| --- | --- | --- |
| `--background` | `240 10% 3.5%` (#08080b) | true-black canvas |
| `--foreground` | `210 40% 98%` | high-contrast primary text |
| `--card` | `240 12% 8%` | glass base (used translucent) |
| `--primary` | `180 96% 50%` (#04f0f0) | **the one accent — electric cyan** |
| `--muted-foreground` | `220 14% 66%` | dimmed secondary text |
| `--border` | `240 10% 18%` | hairline borders |
| `--color-bug / _incident / _critical` | `#ff4d8d / #ff5a5f / #ff4d4d` | high-sat reds/pink |
| `--color-feature_request / _low` | `#22e39a` | vivid green |
| `--color-medium / _high` | `#ffc53d / #ff9838` | amber/orange |
| `--color-question` | `#38bdf8` | sky |
| `--color-other` | `#b57bff` | violet |

- **Glassmorphism** — `.glass` (blur 20px) / `.glass-strong` (blur 28px):
  translucent gradient + `backdrop-blur saturate(180%)` + hairline border + top
  inner-highlight + soft shadow; `.glass-hover` lifts on hover; `.ring-accent`
  adds a cyan glow ring for hero/highlight surfaces.
- **Aurora** — four big, saturated blobs (cyan/violet/blue/green) on three
  independent slow drifts (`aurora-1/2/3`, 26–38s) so the colour movement behind
  the blur is always visible.
- **Animations** — keyframes surface as `animate-*` utilities; **framer-motion**
  helpers in `motion.tsx`: route fade+slide (`PageTransition`, 24px), staggered
  card/tile reveals (`MotionStagger`/`MotionItem`, scale+slide), hover-lift+scale
  cards (`MotionCard`), gliding active-nav pill (`layoutId`). Numbers **count up**
  (`CountUp`), charts **draw in** (bars grow, the sentiment line + area animate).
  Buttons have `active:scale` press feedback. All respect
  `prefers-reduced-motion` (CountUp snaps to final value).
- **Navigation** — a **floating glass top navbar** (`TopNav.tsx`), not a
  sidebar or a full-width header. It is `sticky top-4`, inset (`mx-auto
  max-w-6xl px-4`) with `rounded-full`, so it hovers as a detached bar over the
  aurora — same `.glass-strong` treatment as the cards. Brand left · icon+label
  nav pills · actions right; on narrow widths the labels collapse to icon-only.
  It fades + **slides down** on mount, and the active pill glides **horizontally**
  between items via the shared `layoutId`. Content flows full-width below it
  (`main` has top padding to clear the bar; the old left sidebar and its
  `h-screen`/left-margin are gone, so there's no double scrollbar).
- **Icons** — **lucide-react** everywhere; no emojis. `lib/icons.ts` maps each
  category/severity/skip-reason to its icon.

> **Icons are passed as rendered elements, not components.** Presentational props
> take `icon={<Layers />}` (a ReactNode), never `icon={Layers}`. lucide icons are
> `forwardRef` objects, and passing one as a *component* prop trips Next's
> static-prerender serialization ("Functions cannot be passed to Client
> Components"). Passing an element sidesteps it and keeps all routes statically
> generated (no `force-dynamic`).

### Smart dashboard (derived from `/stats` + `/summaries`, no new backend)

`lib/insight.ts` holds the pure logic:

- **Hero insight strip** (`buildHeroInsight`) — the week's headline finding in
  plain language, rendered by `<HeroInsight>` with a tone-coloured glow. Priority:
  (1) a real week-over-week jump in the leading category ("Bug issues up 40% vs
  last week — now the #1 driver."), (2) a critical spike, (3) the generated
  summary's own headline, (4) a plain top-driver/sentiment statement. The
  previous week comes from a second `getStats({ week: previousIsoWeek })` call;
  the summary from `getSummary(week)` (404 → null, no error).
- **Week-over-week deltas** (`delta` + `<DeltaBadge>`) — ▲/▼ chips on the Total,
  Sentiment, and Critical tiles, coloured by whether the direction is *good*
  (more issues = red, higher sentiment = green).
- **Most urgent theme** (`mostUrgentTheme`) — highlighted with an accent chip
  above the themes chart; the #1 theme bar is drawn in cyan while the rest are
  muted, so the top driver pops.
- **Interactive charts** — glass tooltips with hover detail on every chart;
  **clicking a category bar** navigates to `/tickets?category=…`, which the
  Tickets route reads via `useSearchParams` (inside a `<Suspense>` boundary so it
  stays statically prerendered) to seed its filter.

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

## 2. Add-tickets route (`/upload`)

Two ways in, chosen by a glass pill toggle at the top:

- **Upload file** — drag-and-drop (or click) a CSV/PDF/text file → `POST /uploads`.
- **Paste a ticket** — type/paste one customer message (with an optional label) →
  `POST /uploads/text`. Runs the identical parse → clean → PII-redact → store →
  classify path as a one-message text file; handy for a quick single ticket.

Both render the same **upload summary**: six headline tiles (detected / created /
flagged / skipped / duplicates / blank rows), a list of created items (language +
confidence + any flags / needs-review), and a list of skipped items with the
reason. Busy and error states are inline; a clean batch gets a "nothing needed
flagging" note.

**Auto-classification.** Ingestion now classifies each created ticket in the same
request (`auto_analyze_on_upload`, on by default), so categories, sentiment, and
themes are on the dashboard immediately — no manual "Analyse" click. The summary
reports `analyzed` / `analyzed_count`, and the UI shows a "Auto-classified N
tickets" banner. If the AI service is unavailable the upload still succeeds with
an unclassified placeholder issue and the banner points the user at the manual
**Analyse** action instead — the failure degrades, it never blocks ingestion.

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
