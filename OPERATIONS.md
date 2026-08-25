# OPERATIONS.md — RAPTOR Operasyon / Runbook

## Servisler
| Servis | Durum komutu | Log |
|---|---|---|
| Stack (systemd) | `systemctl status raptor-observatory` | `journalctl -u raptor-observatory` |
| API | `docker logs raptor-api` | internal 8000 |
| Worker | `docker logs raptor-worker` | internal 8001 |
| Scheduler | `docker logs raptor-scheduler` | internal 8002 |
| Gateway | `docker logs raptor-gateway` | 127.0.0.1:3525 |
| PostgreSQL | `docker logs raptor-postgres` | internal |
| Redis | `docker logs raptor-redis` | internal |

## Health
- `curl http://127.0.0.1:3525/health/live`  → liveness
- `curl http://127.0.0.1:3525/health/ready` → DB bağlantısı

## Yedek / Geri yükleme
```bash
export $(grep '^DB_PASSWORD=' ./secrets/raptor-observatory/app.env)
./scripts/backup-restore.sh backup
./scripts/backup-restore.sh restore /var/backups/raptor-observatory/raptor-<ts>.dump
```
Restore **ayrı** `raptor_restore_test` DB'sine yazar; üretim verisine dokunmaz.

## Deployment / Güncelleme
```bash
cd /path/to/raptor-observatory
docker compose up -d --build
./scripts/secret-scan.sh .
```

## Incident
- **Worker takıldı:** `docker restart raptor-worker` — Redis queue'den aynen devam.
- **API unhealthy:** `docker logs raptor-api` — migration/import hatası kontrol.
- **Data kaybı:** yedekten restore (`backup-restore.sh restore`).
- **Circuit breaker açıldı:** cooldown 30sn sonra otomatik sıfırlanır; kalıcısa tool revisiew.

## Sırlar
- Değiştirme: `./scripts/configure-secrets.sh --gen` veya interaktif; ardından `docker compose up -d`.
- Asla ekrana/loga/commit'e yazma.

## Erişim
- Localhost: `http://127.0.0.1:3525`
- Tailscale: sunucu IP `100.122.82.116` üzerinden erişilebilir.
- Public hostname: Cloudflare Access kurulunca `raptor.your-domain.example`.