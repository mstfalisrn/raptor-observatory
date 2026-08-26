# RAPTOR Agentic Observatory — merkezi yapılandırma
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../../.env"),
        extra="ignore",
        case_sensitive=False,
    )

    APP_ENV: str = "development"
    APP_TIMEZONE: str = "Europe/Istanbul"
    SCHEMA_VERSION: int = 1

    # DB (production: raptor_postgres internal host)
    DATABASE_URL: str = (
        "postgresql+asyncpg://raptor:rastgele@localhost:5432/raptor"
    )
    REDIS_URL: str = "redis://localhost:6379/0"

    # Güvenlik (dev-only placeholder; production'da app.env ile override edilir)
    JWT_SECRET: str = "dev-only-change-me"  # noqa: S105
    SESSION_ENCRYPTION_MASTER_KEY: str = "dev-only-32-byte-master-key-0000000000"
    TELEGRAM_WEBHOOK_SECRET: str = "dev-webhook-secret"  # noqa: S105
    CLOUDFLARE_ACCESS_AUD: str = ""
    CLOUDFLARE_ACCESS_CERT_PEM_PATH: str = ""

    # Local auth (CF Access kullanılmıyor)
    ADMIN_EMAIL: str = "alisirin44@gmail.com"
    ADMIN_PASSWORD_HASH: str = ""
    SESSION_TTL_SECONDS: int = 12 * 3600
    RATE_LIMIT_PER_MINUTE: int = 120
    RATE_LIMIT_TASK_PER_MINUTE: int = 20
    MAX_REQUEST_BODY_BYTES: int = 1_048_576

    # Telegram
    TELEGRAM_BOT_TOKEN: str = ""
    TELEGRAM_ALLOWED_USER_IDS: str = ""
    TELEGRAM_GROUP_ENABLED: bool = False

    # LLM
    LLM_PROVIDER: str = "mock"
    LLM_BASE_URL: str = ""
    LLM_MODEL: str = ""
    LLM_API_KEY: str = ""

    # Guardrail
    RUN_MAX_ITERATIONS: int = 40
    RUN_MAX_TOOL_CALLS: int = 80
    RUN_MAX_WALL_SECONDS: int = 900
    RUN_MAX_TOKEN_BUDGET: int = 200_000
    RUN_MAX_COST_BUDGET: float = 5.0

    # Connector / SSRF
    CONNECTOR_ALLOWED_HOSTS: str = ""
    CONNECTOR_MAX_RESPONSE_BYTES: int = 1_048_576
    CONNECTOR_MAX_REDIRECTS: int = 3

    # Embedding (memory semantic retrieval)
    EMBEDDING_MODEL: str = ""  # boşsa LLM_MODEL kullanılır
    EMBEDDING_DIM: int = 1536  # modele göre yapılandırılabilir (sabit varsayım değil)

    # Technocore
    TECHNOCORE_BASE_URL: str = "https://technocore.chat"
    TECHNOCORE_ROOM_CLAIM: str = "d-raptor"
    TECHNOCORE_ED25519_KEY_PATH: str = ""

    # API host/port (0.0.0.0 container İÇİ bind; host'ta 127.0.0.1'e Docker port mapping ile kısıtlanır)
    API_HOST: str = "0.0.0.0"  # nosec B104
    API_PORT: int = 8000
    WORKER_PORT: int = 8001
    SCHEDULER_PORT: int = 8002

    # UI
    VITE_API_BASE: str = "/api"

    @property
    def allowed_user_ids(self) -> set[int]:
        raw = self.TELEGRAM_ALLOWED_USER_IDS.strip()
        if not raw or raw == "*":
            return set()
        out: set[int] = set()
        for part in raw.split(","):
            part = part.strip()
            if part and part.lstrip("-").isdigit():
                out.add(int(part))
        return out

    @property
    def is_production(self) -> bool:
        return self.APP_ENV == "production"

    @property
    def secrets_file(self) -> Path:
        # Üretim secret'ları /root/secrets/raptor-observatory/app.env
        p = Path("/root/secrets/raptor-observatory/app.env")
        if p.exists():
            return p
        # dev: docker-compose env / .env yeterli
        return Path(".env")


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()