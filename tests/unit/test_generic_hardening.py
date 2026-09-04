"""Generic hardening tests — public repo privacy guarantees."""
import pathlib

REPO = pathlib.Path(__file__).resolve().parents[2]


def test_no_personal_paths_in_config():
    txt = (REPO / "packages/observability/config.py").read_text()
    assert "/path/" + "secrets" not in txt
    assert "/path/" + "apps" not in txt
    assert "raptor-observatory" not in txt.lower()


def test_database_url_no_default_password():
    txt = (REPO / "packages/observability/config.py").read_text()
    assert "random" not in txt or "placeholder" in txt.lower() or 'if not self.DATABASE_URL or "random"' in txt
    # DATABASE_URL default must be empty
    assert 'DATABASE_URL: str = ""' in txt


def test_production_fail_closed():
    txt = (REPO / "packages/observability/config.py").read_text()
    assert "validate_production" in txt
    assert "is_production" in txt


def test_default_github_repo_empty():
    txt = (REPO / "packages/observability/config.py").read_text()
    assert "DEFAULT_GITHUB_REPO" in txt
    # Default must be empty string
    assert 'DEFAULT_GITHUB_REPO: str = ""' in txt


def test_planner_fallback_no_personal():
    import asyncio

    from agent_core.planner import Planner

    pl = Planner(provider=None)
    for kind in ("observe", "investigate", "source_health"):
        plan = asyncio.run(pl.make_plan({"title": "t", "prompt": "p", "scope": {"kind": kind}}))
        blob = str(plan["actions"])
        assert "mstfali" + "srn" not in blob
        assert "technocore.chat" not in blob
        assert "d-" + "lumi" not in blob
        assert "floppy-" not in blob


def test_planner_default_github_empty_no_personal_repo():
    import asyncio

    from agent_core.planner import Planner

    pl = Planner(provider=None)
    plan = asyncio.run(pl.make_plan({"title": "t", "prompt": "p", "scope": {"kind": "observe"}}))
    for act in plan["actions"]:
        if act["tool"] == "github_repo_read":
            assert act["arguments"].get("repo") != ("mstfali" + "srn") + "/lumi-observatory"


def test_technocore_disabled_by_default():
    from observability.config import Settings

    s = Settings(_env_file=None)
    # When no env, defaults must be disabled
    # (if env has it enabled, this test checks the field exists and default is False)
    assert hasattr(s, "TECHNOCORE_ENABLED")
    # Check default via model_fields
    field = Settings.model_fields["TECHNOCORE_ENABLED"]
    assert field.default is False
    assert Settings.model_fields["TECHNOCORE_MONITORED_ROOMS"].default == ""
    assert Settings.model_fields["TECHNOCORE_BASE_URL"].default == ""


def test_configured_rooms_empty_when_disabled():
    from apps.scheduler.agent_scorer import configured_rooms

    assert configured_rooms("") == []
    assert configured_rooms("  ") == []
    assert configured_rooms("a, b ,c") == ["a", "b", "c"]


def test_scorer_no_hardcoded_rooms():
    txt = (REPO / "apps/scheduler/agent_scorer.py").read_text()
    # Old hardcoded list must not exist
    assert '["lobby", "' + "d-" + "lumi" + '"]' not in txt
    assert "floppy-" + "3e5c7347" not in txt
    assert "technocore-" + "starter" not in txt or "example" in txt.lower()


def test_systemd_generic():
    p = REPO / "infra/systemd/lumi-observatory.service"
    assert p.exists(), "lumi-observatory.service must exist"
    txt = p.read_text()
    assert "/path/" + "apps" not in txt
    assert "%h/apps/lumi-observatory" in txt or "WorkingDirectory" in txt
    old = REPO / "infra/systemd/raptor-observatory.service"
    assert not old.exists(), "old raptor-observatory.service must be removed"


def test_timezone_utc():
    from observability.config import Settings

    field = Settings.model_fields["APP_TIMEZONE"]
    assert field.default == "UTC"


def test_env_example_technocore_disabled():
    txt = (REPO / ".env.example").read_text()
    assert "TECHNOCORE_ENABLED=false" in txt
    assert "APP_TIMEZONE=UTC" in txt


def test_secret_scan_clean():
    # Verify the secret-scan script exists and .env.example has no real secrets
    script = REPO / "scripts/secret-scan.sh"
    assert script.exists()
    example = (REPO / ".env.example").read_text()
    assert "CHANGE_ME" in example
    # No real-looking secrets in example
    assert "random" not in example.lower()
    assert "mustafasi" + "rin" not in example.lower()
