# SECURITY.md — RAPTOR Güvenlik Modeli

## İzolasyon (değiştirilemez)
- Proje kökü: `/root/apps/raptor-observatory`
- Sırlar: `/root/secrets/raptor-observatory/app.env` (0700/0600, root:root)
- `/root/.hermes`, Hermes runtime, container, volume, config, memory, skills
  ve `hermes.mustafasirin.me:9119` **dokunulmaz**.
- Hermes'in TG token / model anahtarı RAPTOR'a kopyalanmaz; ayrı bot + ayrı provider.
- RAPTOR container'larına Hermes dizini / Docker socket / host root mount **yok**.
- RAPTOR runtime'ı Hermes dururken de çalışır (ayrı Docker stack + systemd).

## Runtime güvenliği
- Tüm servisler: non-root (10001), read-only rootfs, `cap_drop: ALL`,
  `no-new-privileges:true`.
- PostgreSQL/Redis host portu açılmaz (internal network).
- Yalnız `raptor-gateway` host'ta `127.0.0.1:3525`'e bind eder.

## Agent güvenliği
- **Araçlar:** yalnız kayıtlı & şemalı araçlar; keyfi shell/Docker **yok**.
- **SSRF:** loopback/RFC1918/link-local/metadata/socket/internal hostname engeli;
  DNS çözümü + her redirect sonrası IP yeniden sınıflandırma; url allowlist + boyut/timeout.
- **Politika:** READ_ONLY auto · SAFE_WRITE audit'li · PUBLIC_WRITE/PRIVILEGED/DESTRUCTIVE
  insan onayı. Onaylar tek kullanımlık + süreli + eylem hash'ine bağlı.
- **Redaksiyon:** token, Authorization, JWT, env sırları modele/hafızaya girmeden maskelenir.
- **Untrusted:** Technocore mesajları daima `UNTRUSTED` — komut çıkarılamaz, tool tetiklenemez.

## Telegram
- Yalnız `TELEGRAM_ALLOWED_USER_IDS` (numeric); `*` / allow-all **yasak**.
- Grup varsayılan kapalı. Webhook secret token doğrulanır. Token loglanmaz.
- `update_id` ile idempotent; approve callback'leri user+action+hash+expiry bağlı token.

## Web
- Üretimde Cloudflare Access arkasında; origin `Cf-Access-Jwt-Assertion` doğrular.
- Secure/HttpOnly/SameSite cookie, CSP, rate limit, login audit.
- localStorage'a auth token/secret yazılmaz.

## Onay akışı (public yayın)
Technocore'a yazma yalnız kullanıcı `PUBLIC-POST-APPROVED` dediğinde, DID imzalı olarak.

## Sızma testleri (doğrulandı)
- SSRF birim testleri (loopback/rfc1918/metadata/redirect)
- Policy: public write/privileged = approval; destructive = deny
- Redaction birim testleri (Bearer/TG token/JWT)
- `secret-scan.sh` repo taraması temiz
- Backup/restore üretim verisine dokunmadan geçti
- Port taraması: raptor yalnız `127.0.0.1:3525`