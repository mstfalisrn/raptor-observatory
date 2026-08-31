# UI GUIDE — RAPTOR Observatory

> Her yerde aynı 3 adım — Kopyala: `cp .env.example .env — hiçbir gerçek token yazma` — gizli bilgi repo'da yok — `./scripts/secret-scan.sh` ile doğrula

## 🚀 3 Adımda Kurulum (her yerde aynı)

```bash
# 1) klonla
git clone https://github.com/your-owner/raptor-observatory.git && cd raptor-observatory

# 2) env — kopyala; mock ile anahtar gerekmez, openai_compatible için LLM_API_KEY doldur
cp .env.example .env  # içi CHANGE_ME — LLM_API_KEY gerekirse düzenle, mock works with no key

# 3) tek komut (idempotent) — CHANGE_ME'leri otomatik üretir ve ayağa kaldırır
./scripts/quickstart.sh
# veya: docker compose up -d --build

# → http://localhost:3525
# ilk giriş: ADMIN_EMAIL (your-email@example.com) + .env → ADMIN_PASSWORD_HASH
# gizli bilgi repo'da yok — ./scripts/secret-scan.sh ile doğrula
```

- **Önkoşullar:** Docker 24+, 4 GB RAM, port 3525 boş — detay: [INSTALL.md](INSTALL.md#prerequisites)
- **LLM:** `mock` (anahtarsız) · `openai_compatible` → OpenAI / OpenRouter / Ollama — bkz. [CONFIGURATION.md](CONFIGURATION.md)

Web UI is a single-origin React SPA served from `raptor-api` (same origin as `/api`).

## İlk Giriş

- **URL:** http://localhost:3525 → login ekranı
- **E-posta:** `ADMIN_EMAIL` (varsayılan `your-email@example.com` / `admin@raptor`)
- **Parola:** `.env` → `ADMIN_PASSWORD_HASH` — quickstart.sh ilk kurulumda üretir ve log'da gösterir (`→ Kaydet: admin e-posta=... parola=...`). Sonra `ADMIN_PASSWORD_HASH` üzerinden doğrulanır.
- **Doğrulama:** `curl -s http://localhost:3525/health/ready | jq` — UI Settings → LLM Test

> gizli bilgi repo'da yok — `./scripts/secret-scan.sh` ile doğrula — hiçbir gerçek token repo'ya commit edilmez.

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

1. **First visit** -> `GET /v1/auth/me` fails -> `LoginPage` (email + password) — ilk giriş: `ADMIN_EMAIL` / `ADMIN_PASSWORD_HASH` (bkz. yukarı).
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

## Troubleshooting & Logs

| Sorun | Çözüm |
|---|---|
| `3525 in use` | `ss -tlnp \| grep 3525` → `GATEWAY_PORT=3526 docker compose up -d` |
| Login başarısız | `grep ADMIN .env` — e-posta/hash uyumu; quickstart log'daki parola |
| UI boş / SSE `connecting` | `curl -s http://localhost:3525/health/ready \| jq` + `docker compose logs -f raptor-api` |
| LLM test 401 | `LLM_API_KEY` / `LLM_BASE_URL` kontrol — mock ile dene |

> Loglar: `docker compose logs -f` — Health: `http://localhost:3525/health/ready` — Secret taraması: `gizli bilgi repo'da yok — ./scripts/secret-scan.sh ile doğrula`

## Tips

- Collapse sidebar with chevron (`PanelLeft`) — icon-only mode preserves `title` tooltips.
- Mobile: hamburger (`Menu`) opens `Sheet` drawer; same `NAV` array, no duplication.
- Search/filter in Runs: client-side `statusFilter` + `q` over `limit/offset` page.
