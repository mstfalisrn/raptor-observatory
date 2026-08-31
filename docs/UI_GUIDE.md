# UI GUIDE — RAPTOR Observatory

Web UI is a single-origin React SPA served from `raptor-api` (same origin as `/api`).

## Navigation Map — 11 tabs

| # | Tab | Key | Route / Purpose |
|---|---|---|---|
| 1 | **Dashboard** | `dashboard` | KPI cards, timeline of last 5 runs, approvals queue, SSE health |
| 2 | **Runs** | `runs` | Paginated table + search/filter, stepper, status badge |
| 3 | **Approvals** | `approvals` | `PENDING` queue, approve/reject, expiry + HMAC token |
| 4 | **Context** | `context` | Context Inspector — 7 layers, token budget, segments |
| 5 | **Memory** | `memory` | Candidate -> approved/active -> superseded/expired, auto-promote |
| 6 | **Sources** | `sources` | Source registry, enable/disable, last-access + error series |
| 7 | **Technocore** | `technocore` | Room `dm-topic`, cursors, signed write gating |
| 8 | **Telegram** | `telegram` | Bot status, webhook health, allowed IDs |
| 9 | **Settings** | `settings` | Non-secret settings, LLM Test (`POST /v1/settings/llm/test`) |
| 10 | **Reports** | `reports` | Evidence bundle, auditor packet |
| 11 | **Audit** | `audit` | Append-only run events, global_seq, verifier log |

> Detail view: **Run Detail** (`run-detail`) reachable from Dashboard/Runs -> stepper + events + controls (pause/resume/stop/retry).

## Design System

| Token | Value | Notes |
|---|---|---|
| Framework | **Tailwind CSS 4** + `@tailwindcss/vite` | Vite plugin, no PostCSS config |
| Components | **shadcn/ui** — `button, card, badge, input, sheet` | `cn()` via `clsx + tailwind-merge` |
| Colors | **oklch** tokens in `styles.css` | `--background`, `--primary`, `--sidebar-*`, light/dark via `.dark` |
| Spacing | **8pt grid** | `p-3`/`gap-3`/`h-14` topbar, `rounded-xl` cards |
| Icons | **lucide-react** | 1:1 mapped per tab (e.g. `Bird`, `LayoutDashboard`, `Satellite`) |
| Motion | **framer-motion** | `motion.div` for KPI pulse, timeline, toast, page transitions |
| Fonts | system sans, `tracking-tight`, `text-sm` body | `antialiased`, `backdrop-blur` topbar |
| Layout | Sidebar (collapsible) + Topbar (`sticky h-14`) + Drawer (`Sheet`) mobile | `md:hidden` breaker |

## Screenshots (placeholders)

> Replace `docs/screenshots/*.png` with real captures before release.

```
docs/screenshots/
  01-dashboard.png      — KPI grid + timeline + SSE badge
  02-runs.png           — table + pagination + filter
  03-run-detail.png     — stepper + event stream
  04-approvals.png      — pending card + approve action
  05-context.png        — 7-layer inspector
  06-memory.png         — status chips + promotion
  07-settings.png       — LLM Test button + result
```

Markdown embed (once images exist):
```md
![Dashboard](screenshots/01-dashboard.png)
```

## Onboarding Flow

1. **First visit** -> `GET /v1/auth/me` fails -> `LoginPage` (email + password).
2. **Onboarding wizard** (`pages/Onboarding.tsx`) — 3 steps: (a) env check, (b) LLM provider select (mock vs OpenAI-compatible), (c) first task prompt.
3. **Command Center** -> `POST /v1/tasks` -> `run_id` returned -> SSE `run:queued` event.
4. **Live follow** — SSE stream updates Dashboard KPI + timeline + Run Detail stepper in real time.
5. **Approval gate** (if `REQUIRE_APPROVAL`) -> Approvals tab -> approve -> `run:resumed`.

State persists in API token (`localStorage`); logout clears token.

## SSE Pulse & Live Updates

- Endpoint: `GET /api/v1/events/stream` — `text/event-stream`, `Last-Event-ID` + `global_seq` cursor.
- UI: `openSSE()` in `api.ts` — auto-reconnects; badge in Topbar + Dashboard shows `open|connecting|error|closed` with animated dot (`animate-ping`, `shadow-[0_0_8px_...]`).
- Health: `GET /health/live` (liveness) + `GET /health/ready` (DB) polled on Dashboard.
- Run events are append-only; `global_seq` is `IDENTITY` with partial index on `text()` for ordered fan-out.

## Tips

- Collapse sidebar with chevron (`PanelLeft`) — icon-only mode preserves `title` tooltips.
- Mobile: hamburger (`Menu`) opens `Sheet` drawer; same `NAV` array, no duplication.
- Search/filter in Runs: client-side `statusFilter` + `q` over `limit/offset` page.
