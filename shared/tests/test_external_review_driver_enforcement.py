"""Under Codextender the tool coerces ``--driver claude`` to ``codex`` and records
why; the F11 evidence check rejects a raw review record that says otherwise."""

import json
import sys
from pathlib import Path

import pytest

_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
for _p in (_SCRIPTS, _SCRIPTS / "tools"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from lib.external_review_routing import resolve_effective_driver  # noqa: E402
from tools.verifiers.review_driver_check import check_review_driver  # noqa: E402

RUN = "iterate-2026-10-01-driver-enforcement"


def _no_claude_cli(monkeypatch):
    """Stub the CLI probe on BOTH module objects: llm_review binds the bare
    ``external_review_opus_leg`` when lib/ is on sys.path and ``lib.``-qualified
    otherwise, so which one is live depends on test import order."""
    import lib.external_review_opus_leg as qualified

    for mod in (qualified, sys.modules.get("external_review_opus_leg")):
        if mod is not None:
            monkeypatch.setattr(mod, "is_claude_cli_available", lambda: (False, "stub"))


def test_claude_is_coerced_under_codextender():
    eff, rec = resolve_effective_driver("claude", {"CODEXTENDER_ACTIVE": "1"})
    assert eff == "codex"
    assert rec["driver_requested"] == "claude" and rec["codextender_active"] is True
    assert "CODEXTENDER_ACTIVE" in rec["driver_enforced_reason"]


def test_codex_unchanged_under_codextender_and_claude_unchanged_outside():
    eff, rec = resolve_effective_driver("codex", {"CODEXTENDER_ACTIVE": "1"})
    assert eff == "codex" and "driver_enforced_reason" not in rec
    eff, rec = resolve_effective_driver("claude", {})
    assert eff == "claude" and rec["codextender_active"] is False
    assert "driver_enforced_reason" not in rec


def test_cli_empty_diff_records_effective_driver(monkeypatch, tmp_path, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CODEXTENDER_ACTIVE", "1")
    diff, spec = tmp_path / "d.patch", tmp_path / "s.md"
    diff.write_text("  \n", encoding="utf-8")
    spec.write_text("# s\n", encoding="utf-8")
    import external_review

    monkeypatch.setattr("sys.argv", [
        "external_review.py", "--mode", "code", "--spec-file", str(spec),
        "--diff-file", str(diff), "--plugin-root", str(tmp_path), "--driver", "claude",
    ])
    assert external_review.main() == 0
    out = capsys.readouterr()
    payload = json.loads(out.out)
    assert payload["driver"] == "codex"
    assert payload["driver_requested"] == "claude"
    assert set(payload["reviews"]) == {"glm", "opus"}
    assert "coerced to codex" in out.err


def test_success_path_envelope_carries_driver_record(monkeypatch, tmp_path, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CODEXTENDER_ACTIVE", "1")
    for key in ("OPENROUTER_API_KEY", "OPENAI_API_KEY"):
        monkeypatch.delenv(key, raising=False)
    diff, spec = tmp_path / "d.patch", tmp_path / "s.md"
    diff.write_text("diff --git a/x b/x\n-a\n+b\n", encoding="utf-8")
    spec.write_text("# s\n", encoding="utf-8")
    import external_review

    _no_claude_cli(monkeypatch)
    monkeypatch.setattr("sys.argv", [
        "external_review.py", "--mode", "code", "--spec-file", str(spec),
        "--diff-file", str(diff), "--plugin-root", str(tmp_path), "--driver", "claude",
    ])
    external_review.main()  # no provider reachable: exit code is irrelevant here
    payload = json.loads(capsys.readouterr().out)
    assert payload["driver"] == "codex" and payload["driver_requested"] == "claude"
    assert payload["codextender_active"] is True and "driver_enforced_reason" in payload


def _raw(tmp_path, name, body):
    d = tmp_path / ".shipwright" / "planning" / "iterate" / RUN
    d.mkdir(parents=True, exist_ok=True)
    (d / name).write_text(json.dumps(body), encoding="utf-8")


@pytest.mark.parametrize("body,env,ok", [
    ({"driver": "claude", "codextender_active": True}, {}, False),
    ({"driver": "claude"}, {"CODEXTENDER_ACTIVE": "1"}, False),
    ({"driver": "claude", "codextender_active": False}, {"CODEXTENDER_ACTIVE": "1"}, False),
    ({"summary": "no driver key"}, {"CODEXTENDER_ACTIVE": "1"}, False),
    ({"driver": "claude"}, {}, True),
    ({"driver": "codex", "codextender_active": True}, {"CODEXTENDER_ACTIVE": "1"}, True),
])
def test_verifier(tmp_path, body, env, ok):
    _raw(tmp_path, "external-code-review-raw.json", body)
    assert check_review_driver(tmp_path, RUN, environ=env).ok is ok


def test_verifier_flags_unreadable_raw_only_under_codextender(tmp_path):
    d = tmp_path / ".shipwright" / "planning" / "iterate" / RUN
    d.mkdir(parents=True)
    (d / "external-code-review-raw.json").write_text("", encoding="utf-8")
    assert check_review_driver(tmp_path, RUN, environ={"CODEXTENDER_ACTIVE": "1"}).ok is False
    assert check_review_driver(tmp_path, RUN, environ={}).ok is None


def test_verifier_skips_without_records(tmp_path):
    assert check_review_driver(tmp_path, RUN, environ={}).ok is None


def test_failure_envelope_carries_driver_record(monkeypatch, tmp_path, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CODEXTENDER_ACTIVE", "1")
    spec = tmp_path / "s.md"
    spec.write_text("# s\n", encoding="utf-8")
    import external_review

    monkeypatch.setattr("sys.argv", [
        "external_review.py", "--mode", "code", "--spec-file", str(spec),
        "--diff-file", str(tmp_path / "missing.patch"), "--plugin-root", str(tmp_path),
        "--driver", "claude",
    ])
    assert external_review.main() == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["success"] is False
    assert payload["driver"] == "codex" and payload["driver_requested"] == "claude"


def test_run_review_coerces_and_announces(monkeypatch, capsys):
    monkeypatch.setenv("CODEXTENDER_ACTIVE", "1")
    for key in ("OPENROUTER_API_KEY", "OPENAI_API_KEY"):
        monkeypatch.delenv(key, raising=False)
    import lib.llm_review as llm_review
    from lib.llm_review import run_review

    _no_claude_cli(monkeypatch)
    monkeypatch.setattr(llm_review, "detect_provider", lambda: "none")

    out = run_review("diff", "spec", driver="claude")
    assert out["driver"] == "codex" and set(out["reviews"]) == {"glm", "opus"}
    assert out["reviews"]["opus"]["status"] == "skipped"  # proves no real CLI call
    assert "coerced to codex" in capsys.readouterr().err


def test_mode_validation_error_is_an_argparse_exit_not_an_envelope(monkeypatch, tmp_path, capsys):
    """Pins why AC-2 does not cover it: `parser.error` exits 2 with usage text."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CODEXTENDER_ACTIVE", "1")
    spec = tmp_path / "s.md"
    spec.write_text("# s\n", encoding="utf-8")
    import external_review

    monkeypatch.setattr("sys.argv", [
        "external_review.py", "--mode", "code", "--spec-file", str(spec),
        "--plugin-root", str(tmp_path), "--driver", "claude",
    ])
    with pytest.raises(SystemExit) as exc:
        external_review.main()
    assert exc.value.code == 2 and capsys.readouterr().out == ""
