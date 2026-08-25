# DECISIONS.md — Karar Kaydı

Bu dosya mimari ve ürün kararlarını, gerekçeleriyle birlikte tutar (append-only niyetli).

## D1 — Tek origin mimarisi (UI + API aynı origin)
- **Karar:** Web UI statik build'i `raptor-api` image'ına gömdük; `raptor-web` ayrı servis kaldırıldı.
- **Gerekçe:** Şartname "tek origin altında API ile sun" der. Tek origin CORS/CSRF/cookie
  risklerini azaltır, SSO/Cloudflare Access tek noktada doğrulanır.
- **Alternatif **: ayrı static server. Reddedildi (çift origin).

## D2 — Quartz/Celery yerine Redis listesi
- **Karar:** Job queue Redis list (`raptor:queue`); worker bloş poll eder.
- **Gerekçe:** Bağımlılık az, istemci-sürücülü, yeterli. Üretimde RQ/arq'ya geçilebilir.
- **Not:** Faz 3'te sabitlendi; soyut arayüz üzerinden değiştirilebilir.

## D3 — `runs.plan_id`'de FK döngüsü kırıldı
- **Karar:** `runs.plan_id` düz UUID kolonu; `plans.run_id -> runs` tek yönlü FK.
- **Gerekçe:** plan↔run çift yönlü FK Alembic autogenerate'i bozuyordu (tables order).
- **Etki:** referans doğruluğunu uygulama katmanı sağlar.

## D4 — Alembic async (asyncpg)
- **Karar:** Datab basis `postgresql+asyncpg`; Alembic env async çalışır.
- **Gerekçe:** App async; senkron psycopg şeması iki farklı URL gerektiriyordu.

## D5 — Technocore public yazı varsayılan kapalı
- **Karar:** `technocore_signed_write` policy'de `REQUIRE_APPROVAL`; `PUBLIC-POST-APPROVED`
  gate'i. DID key yine de üretildi, imza doğrulandı.
- **Gerekçe:** "kullanıcı onayı olmadan yazma yok" — airdrop/spam karşıtı.

## D6 — Cloudflare Access şimdi kurulmadı
- **Karar:** Public hostname şimdilik aktive edilmedi; yalnız localhost/Tailscale.
- **Gerekçe:** Şartnamedeki "Access hazır değilse public hostname'i aktive etme" kuralı.
  Access kurulunca ingress + DNS + origin JWT doğrulaması eklenir.

## D7 — Verb/LLM key'ler sıfırdan gelir
- **Karar:** Telegram bot ve LLM provider ayrı (Hermes'ten kopyalanmaz); secret script
  ile girilir. Mock provider varsayılan dev/test için.
- **Gerekçe:** İzolasyon kuralı; Hermes sırları paylaşılmaz.