"""Unit tests for `external_review_opus_leg.review_claude_cli`'s subprocess
dispatch: argv/stdin content isolation, identity lock, retry-on-degraded,
failure classes, and the Codextender-conditional Anthropic env scrub. Split
out of `test_external_review_opus_leg.py` (binary resolution, availability,
settings, route selection) to keep both files under the 300-line limit.
"""

import json
import subprocess
import sys
from pathlib import Path

_LIB_DIR = Path(__file__).resolve().parents[1] / "scripts" / "lib"
if str(_LIB_DIR) not in sys.path:
    sys.path.insert(0, str(_LIB_DIR))

import external_review_opus_leg as legs  # noqa: E402

_CONFIG = {"models": {"claude_cli": "claude-opus-5"}, "claude_cli": {"max_retries": 1}}


class _FakeCompleted:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def _json_ok(text: str) -> str:
    return json.dumps({"result": text})


def test_review_claude_cli_errors_when_unavailable_at_toctou_recheck(monkeypatch):
    monkeypatch.setattr(legs, "is_claude_cli_available", lambda: (False, "claude CLI not found on PATH"))
    result = legs.review_claude_cli("content", "context", "sys", "user {DIFF} {SPEC}", _CONFIG)
    assert result == {"status": "error", "via": "claude_cli", "reason": "claude CLI not found on PATH"}


def test_review_claude_cli_rejects_a_model_identity_mismatch(monkeypatch):
    monkeypatch.setattr(legs, "is_claude_cli_available", lambda: (True, ""))
    bad_config = {"models": {"claude_cli": "not-the-locked-model"}}
    result = legs.review_claude_cli("c", "x", "sys", "user", bad_config)
    assert result["status"] == "error"
    assert "must use" in result["reason"]


def test_review_claude_cli_sends_content_via_stdin_not_argv(monkeypatch):
    """The diff/spec must never land in argv — only in the stdin payload —
    since a hostile shim that slipped past _resolve_claude_binary would
    otherwise see untrusted content as a shell-interpretable argument."""
    monkeypatch.setattr(legs, "is_claude_cli_available", lambda: (True, ""))
    monkeypatch.setattr(legs.shutil, "which", lambda _name: "/usr/bin/claude")
    captured = {}

    def _fake_run(cmd, input, **_kwargs):  # noqa: A002
        captured["argv"] = cmd
        captured["stdin"] = input
        return _FakeCompleted(returncode=0, stdout=_json_ok("SHIPWRIGHT_VERDICT: approve"))

    monkeypatch.setattr(legs.subprocess, "run", _fake_run)
    result = legs.review_claude_cli(
        "real diff text", "real context text", "sys prompt", "Review {DIFF} against {SPEC}", _CONFIG,
    )
    assert result["status"] == "success"
    assert result["via"] == "claude_cli"
    assert result["feedback"] == "SHIPWRIGHT_VERDICT: approve"
    assert "real diff text" in captured["stdin"]
    assert "real context text" in captured["stdin"]
    assert "real diff text" not in captured["argv"]
    assert "real context text" not in captured["argv"]
    argv_text = " ".join(captured["argv"])
    assert "{DIFF}" not in argv_text and "{SPEC}" not in argv_text, (
        "the real placeholder vocabulary ({DIFF}/{PLAN}/{BRIEF}/{SPEC}) must "
        "be substituted, not left literal — a mismatched placeholder set "
        "(e.g. {CONTENT}/{CONTEXT}, which no shipped template uses) would "
        "reach the model unsubstituted"
    )
    assert "(see the <content> block on stdin)" in argv_text
    assert "(see the <context> block on stdin)" in argv_text
    argv = captured["argv"]
    mcp_config_idx = argv.index("--mcp-config")
    assert argv[mcp_config_idx + 1].endswith("claude_cli_empty_mcp.json"), (
        "--mcp-config takes the empty-mcpServers file path as its argument"
    )
    strict_idx = argv.index("--strict-mcp-config")
    assert strict_idx == len(argv) - 1 or argv[strict_idx + 1].startswith("--"), (
        "--strict-mcp-config is a boolean flag with no argument of its own — "
        "the real CLI rejects a bare path passed directly after it"
    )
    assert "--permission-mode" in captured["argv"] and "dontAsk" in captured["argv"]
    argv = captured["argv"]
    assert "--model" in argv and "claude-opus-5" in argv, (
        "the pinned model from config must reach argv — dropping --model "
        "would silently fall back to the CLI's own default model"
    )
    assert "--allowedTools" in argv and argv[argv.index("--allowedTools") + 1] == "", (
        "an empty --allowedTools closes the tool-denial sandbox gap; "
        "dropping this flag would let the reviewer invoke tools"
    )
    assert "--bare" in argv
    assert "--max-turns" in argv and argv[argv.index("--max-turns") + 1] == "1"
    assert "--output-format" in argv and argv[argv.index("--output-format") + 1] == "json"


def test_review_claude_cli_retries_once_on_a_degraded_empty_reply(monkeypatch):
    monkeypatch.setattr(legs, "is_claude_cli_available", lambda: (True, ""))
    monkeypatch.setattr(legs.shutil, "which", lambda _name: "/usr/bin/claude")
    attempts = {"n": 0}

    def _fake_run(cmd, input, **_kwargs):  # noqa: A002
        attempts["n"] += 1
        text = "" if attempts["n"] == 1 else "SHIPWRIGHT_VERDICT: revise"
        return _FakeCompleted(returncode=0, stdout=_json_ok(text))

    monkeypatch.setattr(legs.subprocess, "run", _fake_run)
    result = legs.review_claude_cli("c", "x", "sys", "user", _CONFIG)
    assert attempts["n"] == 2
    assert result["status"] == "success"


def test_review_claude_cli_reports_a_nonzero_exit_as_error_without_retrying(monkeypatch):
    monkeypatch.setattr(legs, "is_claude_cli_available", lambda: (True, ""))
    monkeypatch.setattr(legs.shutil, "which", lambda _name: "/usr/bin/claude")
    config_with_retries = {"models": {"claude_cli": "claude-opus-5"}, "claude_cli": {"max_retries": 2}}
    attempts = {"n": 0}

    def _fake_run(*_a, **_k):
        attempts["n"] += 1
        return _FakeCompleted(returncode=2, stderr="line one\nauth expired\n")

    monkeypatch.setattr(legs.subprocess, "run", _fake_run)
    result = legs.review_claude_cli("c", "x", "sys", "user", config_with_retries)
    assert result["status"] == "error"
    assert "auth expired" in result["reason"]
    assert attempts["n"] == 1


def test_review_claude_cli_timeout_is_error_and_not_retried(monkeypatch):
    monkeypatch.setattr(legs, "is_claude_cli_available", lambda: (True, ""))
    monkeypatch.setattr(legs.shutil, "which", lambda _name: "/usr/bin/claude")
    config_with_retries = {"models": {"claude_cli": "claude-opus-5"}, "claude_cli": {"max_retries": 2, "timeout_seconds": 1}}
    attempts = {"n": 0}

    def _raise(*_a, **_k):
        attempts["n"] += 1
        raise subprocess.TimeoutExpired(cmd="claude", timeout=1)

    monkeypatch.setattr(legs.subprocess, "run", _raise)
    result = legs.review_claude_cli("c", "x", "sys", "user", config_with_retries)
    assert result["status"] == "error"
    assert "timed out" in result["reason"]
    assert attempts["n"] == 1


def test_review_claude_cli_unparseable_json_output_is_an_error(monkeypatch):
    monkeypatch.setattr(legs, "is_claude_cli_available", lambda: (True, ""))
    monkeypatch.setattr(legs.shutil, "which", lambda _name: "/usr/bin/claude")
    monkeypatch.setattr(legs.subprocess, "run", lambda *a, **k: _FakeCompleted(returncode=0, stdout="not json"))
    result = legs.review_claude_cli("c", "x", "sys", "user", _CONFIG)
    assert result["status"] == "error"
    assert "could not parse" in result["reason"]


def test_review_claude_cli_scrubs_anthropic_routing_env_vars_under_codextender(monkeypatch):
    """A Codextender-routed parent process (ANTHROPIC_BASE_URL pointed at the
    local Codex-backed proxy) must not leak into this leg's subprocess — it
    must always reach real Anthropic regardless of the caller's own routing.
    A bare `subprocess.run(argv, ...)` with no `env=` would inherit these
    verbatim. Only scrubbed when CODEXTENDER_ACTIVE proves these vars are a
    proxy override (see test below for the non-Codextender case)."""
    monkeypatch.setattr(legs, "is_claude_cli_available", lambda: (True, ""))
    monkeypatch.setattr(legs.shutil, "which", lambda _name: "/usr/bin/claude")
    monkeypatch.setenv("CODEXTENDER_ACTIVE", "1")
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "http://127.0.0.1:4000")
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "codextender-token")
    monkeypatch.setenv("ANTHROPIC_MODEL", "sol")
    monkeypatch.setenv("SOME_UNRELATED_VAR", "keep-me")
    captured = {}

    def _fake_run(cmd, input, **kwargs):  # noqa: A002
        captured["env"] = kwargs.get("env")
        return _FakeCompleted(returncode=0, stdout=_json_ok("SHIPWRIGHT_VERDICT: approve"))

    monkeypatch.setattr(legs.subprocess, "run", _fake_run)
    result = legs.review_claude_cli("c", "x", "sys", "user", _CONFIG)
    assert result["status"] == "success"
    env = captured["env"]
    assert env is not None, "review_claude_cli must pass an explicit env= to subprocess.run under Codextender"
    assert "ANTHROPIC_BASE_URL" not in env
    assert "ANTHROPIC_AUTH_TOKEN" not in env
    assert "ANTHROPIC_MODEL" not in env
    assert env.get("SOME_UNRELATED_VAR") == "keep-me"


def test_review_claude_cli_preserves_anthropic_auth_token_outside_codextender(monkeypatch):
    """ANTHROPIC_AUTH_TOKEN is also a legitimate way to authenticate directly
    with real Anthropic outside any proxy setup (e.g. an enterprise
    bearer-token credential with no separate ANTHROPIC_API_KEY) — a CI
    PR-review pass found the original unconditional scrub would have
    silently broken that installation's auth entirely
    (iterate-2026-09-23-codextender-monorepo-part-c). Outside Codextender
    (CODEXTENDER_ACTIVE unset), the caller's own env must reach the
    subprocess untouched."""
    monkeypatch.setattr(legs, "is_claude_cli_available", lambda: (True, ""))
    monkeypatch.setattr(legs.shutil, "which", lambda _name: "/usr/bin/claude")
    monkeypatch.delenv("CODEXTENDER_ACTIVE", raising=False)
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "my-real-anthropic-bearer-token")
    captured = {}

    def _fake_run(cmd, input, **kwargs):  # noqa: A002
        captured["env"] = kwargs.get("env")
        return _FakeCompleted(returncode=0, stdout=_json_ok("SHIPWRIGHT_VERDICT: approve"))

    monkeypatch.setattr(legs.subprocess, "run", _fake_run)
    result = legs.review_claude_cli("c", "x", "sys", "user", _CONFIG)
    assert result["status"] == "success"
    env = captured["env"]
    assert env is None, (
        "outside Codextender, review_claude_cli must pass env=None (inherit "
        "unchanged) so a legitimate ANTHROPIC_AUTH_TOKEN-only installation "
        "keeps its own real Anthropic authentication"
    )
