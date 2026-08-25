# RAPTOR — Baseline Raporu (AŞAMA 1) — fix/production-readiness-v2

> Tarih: 2026-08-25 · Branch: `fix/production-readiness-v2` (master @ b908410'dan) · Yöntem: salt-okunur + ölçüm

## 1. Proje & Git
- Dizin: `/path/to/raptor-observatory` ✓
- Branch: `master` → **yeni `fix/production-readiness-v2`** ✓
- Durum: clean (0 dirty), HEAD `b908410`, remote `your-owner/raptor-observatory` (private)

## 2. Altyapı durumu (canlı)
- `docker ps` raptor: 6/6 — api/worker/scheduler/postgres/redis `healthy`, gateway up
- Port `3525` → `docker-proxy` `127.0.0.1:3525` (yalnız localhost) ✓
- Hermes `9119` ayrı (`hermes` process) — **çakışma yok** ✓
- Container mount'larında `/path/.hermes` **YOK** ✓

## 3. Cloudflare / DNS
- ⚠️ `raptor.your-domain.example` cloudflared ingress'te **YOK** (20 hostname, raptor yok)
- ⚠️ DNS çözülmüyor → **AŞAMA 11/13'te onayla eklenecek**

## 4. Test / kalite ölçümleri (baseline)
| Ölçüt | Sonuç | Hedef (AŞAMA 12) | Durum |
|---|---|---|---|
| pytest | 57 pass / **5 fail** | tümü pass | ❌ 5 fail (JSONB on SQLite) |
| coverage | **%24** (2767 satır) | ≥%70 | ❌ |
| ruff | **220 hata** (105 fixable) | 0 | ❌ |
| bandit | **0 High**, 1 Medium, 37 Low | 0 High | ✅ High |
| frontend build | ✓ 29 modül, 163.82 kB | build geçmeli | ✅ |
| alembic | head `7f2e9c1a3b4d` (3 migration) | up/down geçmeli | ✅ |
| docker compose config | OK | OK | ✅ |
| secret scan | ✅ temiz (66 dosya) | temiz | ✅ |

### 5 fail'in kök nedeni
`tests/unit/test_technocore_contract.py` — `TestNonceMonotonic` (2) + `TestCursorDB` (3):
`sqlalchemy.exc.CompileError: (in table 'agent_profiles', column 'tool_allowlist'): Compiler <SQLiteTypeCompiler> can't render element of type JSONB`
→ PostgreSQL-only `JSONB` modeli SQLite üzerinde oluşturulmaya çalışılıyor (dokümandaki "PostgreSQL modelleri SQLite testinde" sorunu).

## 5. Backup
- `/var/backups/raptor-observatory/baseline-20260825-134035.sql` (41K, 0600) ✓
- Mevcut: `raptor-20260825-105556.dump` (46K)

## 6. Araçlar
- `.venv`: pytest ✓, coverage ✓, ruff 0.16.4 ✓, bandit 1.9.4 ✓ (bu aşamada kuruldu)

## 7. Kilitlenen kararlar (AŞAMA 0)
- CF Access YOK → Tailscale + local session auth (admin your-email@example.com, roller admin/operator/viewer)
- LLM opencode-go + deepseek-v4-pro, embedding "aynısı" (AŞAMA 8'de doğrulanacak)
- Telegram @raptoragarnaccio_bot, DM-only, kullanıcı ID @userinfobot'tan beklemede
- Technocore mevcut key, oda dm-topic-observatory, 5dk okuma, public onay zorunlu
- Kaynak: yalnız raptor-observatory, allowlist technocore.chat+api.github.com
- 15dk run, 200K/$5, 30dk kontrol, backup 7 gün

## 8. Kalan riskler (sonraki aşamalarda)
1. JSONB→SQLite test uyumsuzluğu (AŞAMA 9/12)
2. coverage %24 → %70 (AŞAMA 12)
3. ruff 220 → 0 (AŞAMA 12)
4. raptor.your-domain.example DNS/ingress (AŞAMA 11/13, onaylı)
5. opencode-go base URL araştırması (AŞAMA 3)
6. Telegram kullanıcı ID (AŞAMA 5 öncesi)
