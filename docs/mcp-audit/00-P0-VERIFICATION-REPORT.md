# RAPTOR — P0 + Kalan Doğrulama Raporu (MCP Audit)

> **Tarih:** 2026-08-27
> **Commit:** `6c03f9d` (head) — `fix(web): tsc — @types/react + string type`
> **Önceki P0 commit:** `3236037` — 6 madde kapalı
> **Amaç:** GPT'nin `read_project_file` ile canlı denetimi için tek kaynak rapor + kod indeksi

## 1) Özet — P0 6 Madde (Kapalı)

| # | Başlık | Durum |
|---|--------|-------|
| 1 | RUN 500 `completed_at → finished_at` | ✅ `apps/api/app.py:317` — `finished_at` + alias |
| 2 | Approval replay / exactly-once | ✅ `ApprovalService.consume()` + Outbox atomik |
| 3 | Redis 7 XAUTOCLAIM 3-elem | ✅ `packages/observability/queue.py` 2 ve 3 ayrıştırma |
| 4 | SSE yolu `/api/v1/events/stream` | ✅ Dockerfile düzeltildi, npm ci fail-closed |
| 5 | Technocore nonce drift | ✅ `d4e5f6a7b8c9_technocore_nonce.py` |
| 6 | RunEvent append-only + retry yeni Run | ✅ `apps/worker/worker.py:_append_run_event` |

**Kalan fix (bu commit):** `@types/react` + `App.tsx:85` `id: string` → tsc 0

## 2) Kanıtlar

### git log
```
6c03f9d fix(web): tsc — @types/react + App.tsx string type (P0 kalan)
3236037 P0: run finished_at alias, redis XAUTOCLAIM 3-elem, SSE /api/v1/events/stream, technocore_nonces migration, approval resume + retry new Run + event append-only
c7a732a fix: Web UI auth akışı (login + session token) + rate limiter gerçek IP
b41d03b chore: repo best-practice (CI fix + docs + SemVer)
556f283 AŞAMA 13: Technocore oda adı dm-topic-observatory → dm-topic (sunucu 10240 oda kap, eski isim açılamadı; dm-topic açıldı + topic set)
b49a223 AŞAMA 13 hazırlık: Vector(1536).with_variant() bug düzeltmesi (pgvector variant çakışması → import hatası); migration throwaway DB'de doğrulandı
39eae33 AŞAMA 12: CI kapıları (ruff 0 + bandit 0 Medium + coverage 70% + PG/Redis service containers) + 28 yeni test (LLM/auth/connectors/memory/queue/security)
3fdd8fd AŞAMA 11: ayrı one-shot migration servisi (API migration çalıştırmaz) + worker Technocore key mount + CF env
```

### git show HEAD
```
commit 6c03f9de07343f5fddf0cb727d6ad494e69eee7f
Author: Mustafa <your-email@example.com>
Date:   Thu Aug 27 08:51:27 2026 +0000

    fix(web): tsc — @types/react + App.tsx string type (P0 kalan)

 apps/web/package-lock.json | 37 +++++++++++++++++++++++++++++++++++++
 apps/web/package.json      |  2 ++
 apps/web/src/App.tsx       |  4 ++--
 3 files changed, 41 insertions(+), 2 deletions(-)
```

### ruff
```
All checks passed!
```

### bandit
```
Test results:
	No issues identified.

Code scanned:
	Total lines of code: 4160
	Total lines skipped (#nosec): 0
	Total potential issues skipped due to specifically being disabled (e.g., #nosec BXXX): 1

Run metrics:
	Total issues (by severity):
		Undefined: 0
		Low: 55
		Medium: 0
		High: 0
	Total issues (by confidence):
		Undefined: 0
		Low: 0
		Medium: 0
		High: 55
Files skipped (0):
```

### pytest + coverage (185 test)
```
........................................................................ [ 38%]
........................................................................ [ 77%]
.........................................                                [100%]

---------- coverage: platform linux, python 3.11.15-final-0 ----------
Name                                     Stmts   Miss  Cover   Missing
----------------------------------------------------------------------
packages/agent_core/__init__.py              0      0   100%
packages/agent_core/coordinator.py         183     54    70%   62-63, 66, 69, 73, 81, 83-84, 86-87, 89-90, 92-93, 95-96, 98-99, 105-108, 113-121, 149, 154, 159-161, 163-165, 167, 176-178, 181-187, 206-208, 212, 214, 224-225
packages/agent_core/executor.py             64     26    59%   24, 27, 31, 38-39, 42, 45, 47, 49, 68-114
packages/agent_core/llm.py                  92      6    93%   43, 129, 158-161
packages/agent_core/planner.py              61      8    87%   79-80, 87-90, 97, 101
packages/agent_core/reporter.py             11      0   100%
packages/agent_core/telegram.py            422    367    13%   37-42, 45-51, 58, 64-81, 84-101, 105-122, 126-142, 145, 148-156, 166-176, 179-200, 203-229, 232-263, 266-286, 289-324, 327-334, 337-344, 347-366, 369-401, 404-423, 426-440, 444-476, 480, 483-506, 510-516, 521-525
packages/agent_core/verifier.py             38      6    84%   33-38, 49
packages/connectors/__init__.py              0      0   100%
packages/connectors/github.py               86     12    86%   35-36, 43, 47-51, 67, 70-72
packages/connectors/http_json.py            62     14    77%   35-40, 57, 67, 79-81, 84, 87, 90
packages/connectors/internal_health.py      40      8    80%   52-53, 57-59, 62, 65, 68
packages/connectors/ssrf.py                 99     29    71%   64-66, 69-70, 75, 82-85, 91-92, 94, 97, 115, 119, 146, 149, 152, 158-165, 170-176
packages/connectors/technocore.py          351     99    72%   44, 54, 58, 78-79, 82-83, 86-87, 124, 133-134, 149-150, 157, 159, 165-166, 174-175, 202-214, 218, 232-235, 238-244, 257, 321, 342, 361-367, 371-383, 389, 391, 400-405, 416, 420, 423-425, 431-432, 434, 454, 456, 469, 474, 480-482, 484, 513-517, 522, 527-528, 533-535, 543, 547
packages/context_engine/__init__.py          0      0   100%
packages/context_engine/assembler.py       101     27    73%   37-38, 92-96, 100, 121, 169, 173, 176, 184-195, 201-202, 227-230
packages/memory/__init__.py                  0      0   100%
packages/memory/service.py                 125     23    82%   68, 71-74, 82, 113, 116, 128-129, 153, 193-198, 208-214
packages/observability/__init__.py           1      0   100%
packages/observability/auth.py              83     10    88%   73, 109-114, 125-127
packages/observability/config.py            71     11    85%   88-93, 97, 102-106
packages/observability/db.py                15      5    67%   28-29, 33-35
packages/observability/models.py           296      0   100%
packages/observability/queue.py             50      5    90%   59-62, 74-75
packages/observability/security.py          84     11    87%   75, 81-82, 94-95, 106-107, 116-117, 124, 132
packages/policy/__init__.py                  0      0   100%
packages/policy/approval.py                 58      5    91%   52-53, 64-65, 92
packages/policy/engine.py                   45      3    93%   50, 53, 57
----------------------------------------------------------------------
TOTAL                                     2438    729    70%

Required test coverage of 70% reached. Total coverage: 70.10%
```

### alembic history
```
c1d2e3f4a5b6 -> d4e5f6a7b8c9 (head), technocore_nonce
7f2e9c1a3b4d -> c1d2e3f4a5b6, faz2_auth_password_hash
b2c3d4e5f6a7b -> 7f2e9c1a3b4d, telegram_bigint_and_dedup
a1b2c3d4e5f6 -> b2c3d4e5f6a7b, faz4_pgvector_vector_column
5014bc0ab4ea -> a1b2c3d4e5f6, faz5_reliable_queue_scheduler
<base> -> 5014bc0ab4ea, raptor_initial
```

### secret-scan
```
✅ Secret scan temiz: repo'da gerçek credential yok. (taranan dosya: 87)
```

### compose
```
EXIT:0
```

### tsc
```
npm notice run raptor-web@1.0.0 npx
npm notice run 'tsc' --noEmit
TSC_EXIT:0
```

### web build
```
npm notice run raptor-web@1.0.0 build
npm notice run vite build
vite v6.4.3 building for production...
transforming...
✓ 29 modules transformed.
rendering chunks...
computing gzip size...
dist/index.html                   0.40 kB │ gzip:  0.27 kB
dist/assets/index-DcOv-Xvs.css    2.84 kB │ gzip:  1.02 kB
dist/assets/index-CpqW5wIi.js   167.76 kB │ gzip: 53.19 kB
✓ built in 804ms
```

## 3) Değişen Dosyalar (P0 + TSC fix)
```
apps/api/Dockerfile                                 |   2 +-
apps/api/app.py                                     |  64 +++++++++++--
apps/web/Dockerfile                                 |   6 +-
apps/web/package.json / package-lock.json / App.tsx |  41 ++ (TSC fix)
apps/worker/worker.py                               | 101 ++++++++++++++++++++-
migrations/versions/d4e5f6a7b8c9_technocore_nonce.py |  43 +++++++++
packages/observability/queue.py                     |  11 ++-
```

## 4) MCP ile GPT Denetimi

```
read_project_file(path="docs/mcp-audit/00-P0-VERIFICATION-REPORT.md")
read_project_file(path="docs/mcp-audit/01-INDEX.md")
read_project_file(path="docs/mcp-audit/02-CODE-CHUNK-001.md")
read_project_file(path="apps/api/app.py")
read_project_file(path="packages/observability/queue.py")
read_project_file(path="apps/worker/worker.py")
read_project_file(path="migrations/versions/d4e5f6a7b8c9_technocore_nonce.py")
```

Limit: her dosya 100KB, chunk'lar 90KB altında kesildi.

## 5) Kalan Riskler
- telegram.py coverage %13 — P0 dışı
- alembic current host'ta PG yok — CI'da pgvector service ile geçer
- coverage 70.10% sınırda

## 6) Sonraki Backlog (P0 dışı)
- P1: Hafıza onay + embedding varyant testleri
- P2: Technocore dm-topic canlı smoke
- P3: Rate limiter + SSE Last-Event-ID e2e
---
*Bu rapor MCP'de docs/mcp-audit/00-P0-VERIFICATION-REPORT.md olarak canlıdır.*
