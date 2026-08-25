# RAPTOR — policy motoru + redaction birim testleri (workflow-agnostic)
import pytest

from policy.engine import PolicyEngine, TOOL_TO_ACTION, action_hash
from observability.security import redact


class TestPolicy:
    def test_read_only_auto(self):
        e = PolicyEngine()
        d = e.decide("technocore_read")
        assert d.decision == "ALLOW"
        assert d.action_class == "READ_ONLY"

    def test_safe_write_auto(self):
        e = PolicyEngine()
        d = e.decide("db_self_write")
        assert d.decision == "ALLOW"

    def test_public_write_needs_approval(self):
        e = PolicyEngine()
        d = e.decide("technocore_signed_write")
        assert d.decision == "REQUIRE_APPROVAL"

    def test_privileged_needs_approval(self):
        e = PolicyEngine()
        d = e.decide("apply_privileged")
        assert d.decision == "REQUIRE_APPROVAL"

    def test_destructive_denied(self):
        e = PolicyEngine()
        d = e.decide("destructive_op")
        assert d.decision == "DENY"

    def test_unknown_tool_defaults_read_only_allow(self):
        e = PolicyEngine()
        assert e.decide("unknown_tool").decision == "ALLOW"


class TestRedaction:
    def test_bearer_redacted(self):
        out = redact("Authorization: Bearer abc123XYZsecret")
        assert "abc123XYZsecret" not in out
        assert "<REDACTED>" in out

    def test_telegram_token_redacted(self):
        out = redact("token=123456789:AAHthisIsAReallyLongTelegramTokenString")
        assert "<TG_TOKEN_REDACTED>" in out

    def test_jwt_redacted(self):
        out = redact("bearer eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c")
        assert "<JWT_REDACTED>" in out

    def test_explicit_env_assignment_redacted(self):
        out = redact("TELEGRAM_BOT_TOKEN=123456789:AAHSecretTokenValue")
        assert "<REDACTED>" in out

    def test_action_hash_binds_content(self):
        h1 = action_hash("PUBLIC_WRITE", "/r/lobby", {"x": 1})
        h2 = action_hash("PUBLIC_WRITE", "/r/lobby", {"x": 2})
        assert h1 != h2  # onay başka içeriğe taşınamaz