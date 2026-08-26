# RAPTOR — AŞAMA 12 security redact/DLP/env-secret testleri
from observability.security import (
    Redactor,
    contains_secret,
    load_secrets_from_env,
    redact,
    scrub_and_flag,
)


def test_redact_tg_token():
    out = redact("token: 123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnop")
    assert "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnop" not in out
    assert "REDACT" in out


def test_redact_password_assignment():
    out = redact("config: password=supersecretvalue123")
    assert "supersecretvalue123" not in out


def test_redact_aws_key():
    out = redact("key AKIAIOSFODNN7EXAMPLE")
    assert "AKIAIOSFODNN7EXAMPLE" not in out


def test_redact_empty_and_none():
    assert redact("") == ""
    assert redact("temiz metin") == "temiz metin"


def test_contains_secret():
    assert contains_secret("token: 123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnop")
    assert not contains_secret("sıradan bir metin")


def test_scrub_and_flag():
    txt = "password=hunter2secret"
    scrubbed, had = scrub_and_flag(txt)
    assert had is True
    assert "hunter2secret" not in scrubbed
    clean, clean_had = scrub_and_flag("merhaba dünya")
    assert clean_had is False
    assert clean == "merhaba dünya"


def test_load_secrets_from_env_redacts_literal():
    env = {"LLM_API_KEY": "sk-test-0123456789abcdef", "UNRELATED": "merhaba dünya"}
    added = load_secrets_from_env(environ=env)
    assert added >= 1
    # literal değer artık redakte edilmeli
    assert "sk-test-0123456789abcdef" not in redact("anahtar sk-test-0123456789abcdef burada")


def test_load_secrets_from_env_skips():
    env = {
        "LLM_API_KEY": "CHANGE_ME",
        "SHORT": "kisa",
        "PATH_LIKE": "/usr/bin/python",
        "USERNAME": "bu-bir-uzun-deger-ama-key-ismi-gizli-degil",
    }
    assert load_secrets_from_env(environ=env) == 0


def test_redactor_class():
    r = Redactor()
    r.add_literal("gizlibirdeger123")
    out = r.scrub("parola gizlibirdeger123 burada")
    assert "gizlibirdeger123" not in out
    assert r.contains_secret("gizlibirdeger123") is True
    scrubbed, had = r.scrub_and_flag("x gizlibirdeger123 y")
    assert had is True and "gizlibirdeger123" not in scrubbed
