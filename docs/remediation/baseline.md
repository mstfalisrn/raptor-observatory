# RAPTOR — Remediation Baseline (Faz 0)
> Oluşturulma: 2026-08-25 · Kaynak: /root/apps/raptor-observatory (master, clean) · Yöntem: salt okunur kod incelemesi + canlı health/port/secret doğrulaması

## Özet
- **Repo:** `/root/apps/raptor-observatory`, branch `master`, dirty yok, 4 commit, remote `mstfalisrn/raptor-observatory` (private)
- **Stack:** 6 container healthy (api/worker/scheduler/postgres/redis/gateway), `127.0.0.1:3525`, compose config OK
- **Secret:** `/root/secrets/raptor-observatory/app.env` 0700/0600, 8 anahtar VAR (DB_PASSWORD,JWT_SECRET,SESSION_ENCRYPTION_MASTER_KEY,TELEGRAM_BOT_TOKEN,TELEGRAM_WEBHOOK_SECRET,LLM_API_KEY...), değerler gösterilmedi
- **Cloudflare:** tunnel `48a74dc3` active, `raptor.mustafasirin.me` henüz yok (çakışma yok)
- **Test:** 23 test collect (12 unit + 11 security), docs/remediation yoktu — bu dosya Faz 0 çıktısıdır

## P0 — Üretimi engelleyen (1-26) — kanıt özeti
> Her madde için dosya:line kanıtı subagent incelemesiyle doldurulacak; aşağıda hızlı tarama ile doğrulanmış çekirdek bulgular:

| # | Madde | Durum | Kanıt |
|---|-------|-------|-------|
| 1 | Coordinator LLM çağırmıyor, context kullanılmıyor | **DOĞRULANDI** | `packages/agent_core/coordinator.py:103-116` — `provider` arg alıyor ama `await provider.*` yok; `assembler.assemble()` prompt'u `prompt` değişkeninde kalıyor, modele gitmiyor |
| 2 | Planner sabit tool isimleri | **DOĞRULANDI** | `packages/agent_core/planner.py:8-24` — `_templates` sabit dict, `make_plan` yalnız `kind`'a göre sabit liste döndürüyor; LLM yok |
| 3 | Executor args'sız çağırıyor | **DOĞRULANDI** | `coordinator.py:142` `await executor.execute(tool)` — `tool` string yalnız, `**kw` yok; `executor.py:38` `registry.call(tool)` required arg sağlamıyor |
| 4 | Tool error'a rağmen COMPLETED | **DOĞRULANDI** | `coordinator.py:147-152` — `TOOL_ERROR` emit edip `record_failure` threshold aşılmadıkça `FAILED` olmuyor; sonra `VERIFYING→COMPLETED`'e gidiyor |
| 10 | API auth yok | **DOĞRULANDI** | `apps/api/app.py` — `CORSMiddleware allow_origins=[\"*\"]`, auth/RBAC middleware yok |
| 11 | CF Access JWT yok | **DOĞRULANDI** | `apps/api/app.py` — `Cf-Access-Jwt-Assertion` header kontrolü yok |
| 12 | Wildcard CORS | **DOĞRULANDI** | `apps/api/app.py: allow_origins=[\"*\"]` |
| 16 | Telegram başlatılmıyor | **DOĞRULANDI** | `packages/agent_core/telegram.py` var ama `apps/api/app.py` webhook'u yalnız `OK` dönüyor, `TelegramService` start edilmiyor |
| 21 | DID hex kullanıyor | **DOĞRULANDI** | `packages/connectors/technocore.py: did:key: + vk.encode().hex()` — multibase/base58btc değil |
| 24 | SSE yolu uyumsuz | **DOĞRULANDI** | `apps/api/app.py: /events/stream` vs `apps/web/src/api.ts: /api/v1/events/stream` (gateway rewrite ile kısmen çözülü ama canonical değil) |

*Kalan P0 (5-9,13-15,17-20,22-23,25-26) ve tüm P1-P3 için detaylı dosya:line kanıtları subagent raporlarıyla bu tabloya eklenecek.*

## P1 — Mimari/güvenlik (27-50)
> Subagent incelemesi bekleniyor — özet: memory retrieval yok, pgvector vector sütunu yok, context tek tür, redaction env ile başlatılmıyor, SSRF DNS pin yok, Redis Streams yok, scheduler pass, health bağımlılık ölçmüyor.

## P2 — Deployment/veri modeli (51-71)
> Subagent incelemesi bekleniyor — idempotency unique eksik, (run_id,seq) unique değil, configure-secrets.sh mevcut ama compose env map eksik, lockfile/hash yok, CSP/HSTS yok.

## P3 — Kalite/UX (72-82)
> Subagent incelemesi bekleniyor — coverage düşük, lint broad exception, UI error state yok, SSE cursor/Last-Event-ID yok.

## Değişecek dosya listesi (tahmini)
`packages/agent_core/{coordinator,planner,executor,verifier,telegram}.py`, `packages/{policy,context_engine,memory,connectors/*,observability/*}`, `apps/api/app.py`, `apps/worker/worker.py`, `apps/scheduler/scheduler.py`, `apps/web/src/*`, `migrations/*`, `docker-compose.yml`, `infra/caddy/Caddyfile`, `scripts/*`, `tests/**/*`, `docs/**`

## Migration riski & rollback
- Yeni migration'lar: unique constraint (tasks.idempotency_key, publication idempotency), (run_id,seq), FK/CHECK, BIGINT, vector sütunu
- Risk: mevcut DB'de 2 run var — unique eklerken çakışma testi gerekir
- Rollback: `alembic downgrade -1` + yedek restore (`scripts/backup-restore.sh restore`), önceki image tag `docker compose up -d --build` öncesi `docker images | grep raptor`

## Sonraki faz
**Faz 1 — Secret temizliği ve production güvenlik sınırı** (onay bekleniyor)

---
*Bu dosya Faz 0'ın canlı kanıtıdır; subagent detay raporları eklendikçe güncellenecek.*
