"""Unit tests for the Codex CLI review leg (`external_review_default_legs.py`).

Covers `review_codex` (subprocess dispatch, identity lock, retry-on-degraded,
failure classes) and `resolve_openai_route` / `api_route` (route selection +
fallback). Binary resolution and availability detection are covered in the
sibling `test_external_review_codex_availability.py`.
"""

import json
import subprocess
import sys
from pathlib import Path

_LIB_DIR = Path(__file__).resolve().parents[1] / "scripts" / "lib"
_TOOLS_DIR = Path(__file__).resolve().parents[1] / "scripts" / "tools"
for _d in (_LIB_DIR, _TOOLS_DIR):
    if str(_d) not in sys.path:
        sys.path.insert(0, str(_d))

import external_review_default_legs as legs  # noqa: E402

_CONFIG = {"models": {"codex": "gpt-5.6-terra"}, "codex": {"max_retries": 1}}


class _FakeCompleted:
    def __init__(self, returncode=0, stderr=""):
        self.returncode = returncode
        self.stderr = stderr


# --- review_codex ------------------------------------------------------------

def test_review_codex_errors_when_unavailable_at_toctou_recheck(monkeypatch):
    """resolve_openai_route already committed to codex before calling review_codex, so a TOCTOU
    failure here is attempted-and-failed ("error"), not not-attempted ("skipped") — "skipped" would
    drop it from _attempted() and hide the loss from partial-degradation reporting."""
    monkeypatch.setattr(legs, "is_codex_available", lambda: (False, "codex CLI not found on PATH"))
    result = legs.review_codex("u DIFF CONTEXT", "sys", _CONFIG)
    assert result == {"status": "error", "via": "codex", "reason": "codex CLI not found on PATH"}


def test_review_codex_rejects_a_model_identity_mismatch(monkeypatch):
    monkeypatch.setattr(legs, "is_codex_available", lambda: (True, ""))
    bad_config = {"models": {"codex": "not-the-locked-model"}}
    result = legs.review_codex("u", "sys", bad_config)
    assert result["status"] == "error"
    assert "must use" in result["reason"]


def test_review_codex_sends_the_rendered_prompt_with_no_residual_placeholder(monkeypatch, tmp_path):
    """The caller renders its own placeholders BEFORE calling review_codex —
    this is the regression test for the silent-no-op bug where review_codex's
    own {CONTENT}/{CONTEXT} substitution never matched the CLI's {SPEC}/{DIFF}
    template, and Codex reviewed literal placeholder text as a passing review."""
    monkeypatch.setattr(legs, "is_codex_available", lambda: (True, ""))
    monkeypatch.setattr(legs.shutil, "which", lambda _name: "/usr/bin/codex")
    monkeypatch.setattr(legs.tempfile, "TemporaryDirectory", lambda prefix="", ignore_cleanup_errors=False: _DirCtx(tmp_path))
    captured = {}

    def _fake_run(cmd, input, **_kwargs):  # noqa: A002
        captured["stdin"] = input
        out_path = Path(cmd[cmd.index("-o") + 1])
        out_path.write_text("SHIPWRIGHT_VERDICT: approve", encoding="utf-8")
        assert "--sandbox" in cmd and "read-only" in cmd
        assert "--ignore-user-config" in cmd and "--ignore-rules" in cmd
        return _FakeCompleted(returncode=0)

    monkeypatch.setattr(legs.subprocess, "run", _fake_run)
    result = legs.review_codex("Diff:\nreal diff text\n\nSpec:\nreal spec text", "sys prompt", _CONFIG)
    assert result["status"] == "success"
    assert result["via"] == "codex"
    assert result["feedback"] == "SHIPWRIGHT_VERDICT: approve"
    assert "sys prompt" in captured["stdin"]
    assert "real diff text" in captured["stdin"]
    assert "real spec text" in captured["stdin"]
    assert "{CONTENT}" not in captured["stdin"] and "{CONTEXT}" not in captured["stdin"]
    assert "{DIFF}" not in captured["stdin"] and "{SPEC}" not in captured["stdin"]


def test_review_codex_retries_once_on_a_degraded_empty_reply(monkeypatch, tmp_path):
    monkeypatch.setattr(legs, "is_codex_available", lambda: (True, ""))
    monkeypatch.setattr(legs.shutil, "which", lambda _name: "/usr/bin/codex")
    monkeypatch.setattr(legs.tempfile, "TemporaryDirectory", lambda prefix="", ignore_cleanup_errors=False: _DirCtx(tmp_path))
    attempts = {"n": 0}

    def _fake_run(cmd, input, **_kwargs):  # noqa: A002
        out_path = Path(cmd[cmd.index("-o") + 1])
        attempts["n"] += 1
        out_path.write_text("" if attempts["n"] == 1 else "SHIPWRIGHT_VERDICT: revise", encoding="utf-8")
        return _FakeCompleted(returncode=0)

    monkeypatch.setattr(legs.subprocess, "run", _fake_run)
    result = legs.review_codex("u", "sys", _CONFIG)
    assert attempts["n"] == 2
    assert result["status"] == "success"


def test_review_codex_reports_a_nonzero_exit_as_error_without_retrying(monkeypatch, tmp_path):
    monkeypatch.setattr(legs, "is_codex_available", lambda: (True, ""))
    monkeypatch.setattr(legs.shutil, "which", lambda _name: "/usr/bin/codex")
    monkeypatch.setattr(legs.tempfile, "TemporaryDirectory", lambda prefix="", ignore_cleanup_errors=False: _DirCtx(tmp_path))
    config_with_retries = {"models": {"codex": "gpt-5.6-terra"}, "codex": {"max_retries": 2}}
    attempts = {"n": 0}

    def _fake_run(*_a, **_k):
        attempts["n"] += 1
        return _FakeCompleted(returncode=2, stderr="line one\nauth expired\n")

    monkeypatch.setattr(legs.subprocess, "run", _fake_run)
    result = legs.review_codex("u", "sys", config_with_retries)
    assert result["status"] == "error"
    assert "auth expired" in result["reason"]
    assert attempts["n"] == 1  # nonzero exit is terminal, not retried — matches retrying_completion's scope


def test_review_codex_timeout_is_error_and_not_retried(monkeypatch, tmp_path):
    monkeypatch.setattr(legs, "is_codex_available", lambda: (True, ""))
    monkeypatch.setattr(legs.shutil, "which", lambda _name: "/usr/bin/codex")
    monkeypatch.setattr(legs.tempfile, "TemporaryDirectory", lambda prefix="", ignore_cleanup_errors=False: _DirCtx(tmp_path))
    config_with_retries = {"models": {"codex": "gpt-5.6-terra"}, "codex": {"max_retries": 2, "timeout_seconds": 1}}
    attempts = {"n": 0}

    def _raise(*_a, **_k):
        attempts["n"] += 1
        raise subprocess.TimeoutExpired(cmd="codex", timeout=1)

    monkeypatch.setattr(legs.subprocess, "run", _raise)
    result = legs.review_codex("u", "sys", config_with_retries)
    assert result["status"] == "error"
    assert "timed out" in result["reason"]
    assert attempts["n"] == 1  # a timeout is a transport failure, terminal — not retried


def test_codex_settings_clamps_a_negative_max_retries():
    assert legs.codex_settings({"codex": {"max_retries": -3}}) == (legs.CODEX_DEFAULT_TIMEOUT_SECONDS, 0)


def test_codex_settings_defaults_when_unconfigured():
    assert legs.codex_settings({}) == (legs.CODEX_DEFAULT_TIMEOUT_SECONDS, legs.CODEX_DEFAULT_MAX_RETRIES)


class _DirCtx:
    """Fake TemporaryDirectory that reuses a pytest tmp_path (no real cleanup
    races) but still supports the `with ... as tmp:` protocol under test."""

    def __init__(self, path):
        self._path = str(path)

    def __enter__(self):
        return self._path

    def __exit__(self, *_exc):
        return False


# --- resolve_openai_route / api_route ---------------------------------------

def test_api_route_prefers_openrouter_over_direct():
    assert legs.api_route(True, True) == "openrouter"
    assert legs.api_route(False, True) == "direct"
    assert legs.api_route(False, False) == "none"


def test_resolve_openai_route_default_config_matches_legacy_api_chain():
    config = {"external_review": {"gpt_leg": {"provider": "api"}}}
    assert legs.resolve_openai_route(config, has_openrouter_key=True, has_openai_key=False) == ("openrouter", "")
    assert legs.resolve_openai_route(config, has_openrouter_key=False, has_openai_key=True) == ("direct", "")
    assert legs.resolve_openai_route(config, has_openrouter_key=False, has_openai_key=False) == ("none", "")


def test_resolve_openai_route_uses_codex_when_configured_and_available(monkeypatch):
    monkeypatch.setattr(legs, "is_codex_available", lambda: (True, ""))
    config = {"external_review": {"gpt_leg": {"provider": "codex"}}}
    route, note = legs.resolve_openai_route(config, has_openrouter_key=False, has_openai_key=False)
    assert route == "codex"
    assert note == ""


def test_resolve_openai_route_falls_back_to_api_when_codex_unavailable(monkeypatch):
    monkeypatch.setattr(legs, "is_codex_available", lambda: (False, "codex CLI not found on PATH"))
    config = {"external_review": {"gpt_leg": {"provider": "codex"}}}
    route, note = legs.resolve_openai_route(config, has_openrouter_key=True, has_openai_key=False)
    assert route == "openrouter"
    assert "codex unavailable" in note and "falling back to openrouter" in note


def test_resolve_openai_route_falls_back_to_skip_when_neither_is_usable(monkeypatch):
    monkeypatch.setattr(legs, "is_codex_available", lambda: (False, "codex CLI not found on PATH"))
    config = {"external_review": {"gpt_leg": {"provider": "codex"}}}
    route, note = legs.resolve_openai_route(config, has_openrouter_key=False, has_openai_key=False)
    assert route == "none"
    assert "skipping this leg" in note


# --- CLI-level regression: real render path, only subprocess.run stubbed ----

def test_cli_codex_route_actually_sends_the_spec_and_plan_not_the_raw_template(monkeypatch, tmp_path):
    """Regression for the placeholder-mismatch bug: drives the REAL CLI
    dispatch — only subprocess.run is stubbed (review_codex itself is NOT),
    so a broken render would leak the literal {SPEC}/{PLAN} template into
    codex's stdin instead of the real spec/plan text."""
    for key in ("OPENROUTER_API_KEY", "OPENAI_API_KEY", "SHIPWRIGHT_REVIEW_MODEL_CODEX"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.chdir(tmp_path)
    import external_review

    plugin_root = tmp_path / "fake-plan"
    (plugin_root / "prompts" / "plan_reviewer").mkdir(parents=True)
    (plugin_root / "prompts" / "plan_reviewer" / "system").write_text("sys prompt", encoding="utf-8")
    (plugin_root / "prompts" / "plan_reviewer" / "user").write_text(
        "Review:\n## Spec\n{SPEC}\n## Plan\n{PLAN}\n", encoding="utf-8"
    )
    spec = tmp_path / "spec.md"
    plan = tmp_path / "plan.md"
    spec.write_text("# Spec\nDo X.", encoding="utf-8")
    plan.write_text("# Plan\nStep 1.", encoding="utf-8")
    (tmp_path / "shipwright_iterate_config.json").write_text(
        json.dumps({"external_review": {"gpt_leg": {"provider": "codex"}}}), encoding="utf-8"
    )

    monkeypatch.setattr(legs, "is_codex_available", lambda: (True, ""))
    monkeypatch.setattr(legs.shutil, "which", lambda _name: "/usr/bin/codex")
    captured = {}

    def _fake_run(cmd, input, **_kwargs):  # noqa: A002
        captured["stdin"] = input
        out_path = Path(cmd[cmd.index("-o") + 1])
        out_path.write_text("SHIPWRIGHT_VERDICT: approve", encoding="utf-8")
        return type("R", (), {"returncode": 0, "stderr": ""})()

    monkeypatch.setattr(legs.subprocess, "run", _fake_run)
    monkeypatch.setattr(
        "sys.argv",
        ["external_review.py", "--mode", "plan", "--spec-file", str(spec),
         "--plan-file", str(plan), "--plugin-root", str(plugin_root),
         "--project-root", str(tmp_path)],
    )
    rc = external_review.main()

    assert rc == 0
    assert "Do X" in captured["stdin"]  # spec.md content
    assert "Step 1" in captured["stdin"]  # plan.md content
    assert "{SPEC}" not in captured["stdin"] and "{PLAN}" not in captured["stdin"]
