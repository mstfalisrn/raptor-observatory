# RAPTOR — AŞAMA 5 Telegram testleri (singleton, dedup helper, redact, allowlist)
from agent_core.telegram import TelegramService, get_service, webhook_opaque_path
from observability.security import redact


class TestSingleton:
    def test_get_service_returns_same_instance(self):
        a = get_service()
        b = get_service()
        assert a is b, "her çağrıda yeni instance oluşturulmamalı (singleton)"


class TestOpaquePath:
    def test_deterministic(self):
        p1 = webhook_opaque_path("my-secret")
        p2 = webhook_opaque_path("my-secret")
        assert p1 == p2
        assert len(p1) == 32  # sha256 hex ilk 32

    def test_different_secret_different_path(self):
        assert webhook_opaque_path("a") != webhook_opaque_path("b")

    def test_empty_secret_empty_path(self):
        assert webhook_opaque_path("") == ""


class TestRedactToken:
    def test_telegram_token_masked(self):
        token = "8820797359:AAGJ18u8OZgrHUxDlhYHy9dW5bXrmHyvA2o"
        out = redact(f"hata: {token} isteği başarısız")
        assert token not in out, "token log/metinde görünmemeli"
        assert "TG_TOKEN_REDACTED" in out

    def test_llm_key_masked(self):
        key = "sk-JgWZznvGKVXpsZRUBGHle8qXvXmWbeUiHbMToITn35WSvLAZ2dDOYnJCF61Nr4bf"
        out = redact(f"key={key}")
        assert key not in out
        assert "REDACTED" in out


class TestAllowlist:
    def test_empty_env_denies(self):
        svc = TelegramService.__new__(TelegramService)  # __init__'siz — settings token okumaz
        # env allowlist boşsa allowed() False döner (fail-closed)
        # Bu test yalnızca 'allowed' metodunun boş liste davranışını doğrular
        from observability.config import settings
        original = settings.allowed_user_ids
        settings.TELEGRAM_ALLOWED_USER_IDS = ""
        try:
            assert svc.allowed(123456789) is False
        finally:
            settings.TELEGRAM_ALLOWED_USER_IDS = ",".join(str(x) for x in original) if original else ""
