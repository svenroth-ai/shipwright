"""`lib/codex_review_transport.py` — the Codex-CLI internal-review transport.

Covers the Internal Plan Review findings that are load-bearing here: env
allowlisting (finding #2), the stripped/adapted prompt (finding #9), the
validate-then-copy-to-canonical-basename sequencing (finding #8), and the
single-attempt default (finding #10).
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import Mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from lib import codex_review_transport as transport  # noqa: E402
from lib.review_payloads import CANONICAL_PAYLOAD_BASENAMES  # noqa: E402

VALID_CODE_REVIEW = {"section": "s1", "review": []}


def test_role_schemas_and_canonical_basenames_have_the_same_keys() -> None:
    """Regression for code-reviewer REJECT 2026-09-17: a role present in one
    dict but not the other silently made `canonical_path` collapse onto the
    temp file (the plan_review defect) — this must fail LOUDLY, not silently,
    the moment a role is added to one dict without the other."""
    assert transport.ROLE_SCHEMAS.keys() == transport.ROLE_CANONICAL_BASENAMES.keys()


def test_shared_canonical_basenames_match_record_review_pass(
) -> None:
    """`ROLE_CANONICAL_BASENAMES` is a second, hand-maintained copy of the
    names `record_review_pass.py` enforces via `CANONICAL_PAYLOAD_BASENAMES`
    for spec/code/doubt — a silent drift between the two would make this
    transport write a name the recorder then refuses, discovered only after
    a paid-for codex call (doubt-reviewer, LOW, 2026-09-17)."""
    for role in ("spec", "code", "doubt"):
        assert transport.ROLE_CANONICAL_BASENAMES[role] == CANONICAL_PAYLOAD_BASENAMES[role]


# --- run_codex_review --------------------------------------------------------


def test_unknown_role_raises(tmp_path: Path) -> None:
    with pytest.raises(transport.CodexReviewTransportError):
        transport.run_codex_review("nonsense-role", tmp_path, "prompt", tmp_path)


def test_codex_unavailable_returns_error_not_raise(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(transport, "is_codex_available", lambda **kw: (False, "not authenticated"))
    result = transport.run_codex_review("code", tmp_path, "prompt", tmp_path)
    assert result == {"status": "error", "transport": "codex", "model": transport.CODEX_REVIEW_MODEL,
                       "reason": "not authenticated"}


def test_binary_missing_returns_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(transport, "is_codex_available", lambda **kw: (True, ""))
    monkeypatch.setattr(transport, "_resolve_codex_binary", lambda: None)
    result = transport.run_codex_review("code", tmp_path, "prompt", tmp_path)
    assert result["status"] == "error"
    assert "not found on PATH" in result["reason"]


def _fake_run_writing(payload: dict, *, returncode: int = 0) -> Mock:
    def _run(argv, input, capture_output, encoding, errors, timeout, env):  # noqa: A002
        out_path = Path(argv[argv.index("-o") + 1])
        if returncode == 0:
            out_path.write_text(json.dumps(payload), encoding="utf-8")
        return subprocess.CompletedProcess(argv, returncode, stdout="", stderr="")
    return Mock(side_effect=_run)


def _patch_available(monkeypatch: pytest.MonkeyPatch, codex_bin: str = "codex") -> None:
    monkeypatch.setattr(transport, "is_codex_available", lambda **kw: (True, ""))
    monkeypatch.setattr(transport, "_resolve_codex_binary", lambda: codex_bin)


def test_success_copies_validated_output_to_canonical_basename(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_available(monkeypatch)
    fake_run = _fake_run_writing(VALID_CODE_REVIEW)
    monkeypatch.setattr(transport.subprocess, "run", fake_run)

    result = transport.run_codex_review("code", tmp_path, "prompt", tmp_path)

    assert result["status"] == "completed"
    canonical = tmp_path / "code_review_reply.json"
    assert canonical.exists()
    assert json.loads(canonical.read_text(encoding="utf-8")) == VALID_CODE_REVIEW
    assert fake_run.call_count == 1


def test_plan_review_role_survives_the_finally_unlink(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Regression for spec-reviewer REJECT 2026-09-17: `plan_review` was
    missing from `ROLE_CANONICAL_BASENAMES`, so its canonical path fell back
    to the temp file's own name — the `finally` unlink then deleted the very
    file the caller was told to read."""
    _patch_available(monkeypatch)
    valid_plan_review = {
        "reviewer": "opus-plan-reviewer", "severity": "low", "findings": [], "summary": "ok",
    }
    fake_run = _fake_run_writing(valid_plan_review)
    monkeypatch.setattr(transport.subprocess, "run", fake_run)

    result = transport.run_codex_review("plan_review", tmp_path, "prompt", tmp_path)

    assert result["status"] == "completed"
    canonical = Path(result["canonical_path"])
    assert canonical.name == "plan_review_reply.json"
    assert canonical.exists()
    assert json.loads(canonical.read_text(encoding="utf-8")) == valid_plan_review


def test_env_passed_to_subprocess_is_scrubbed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_available(monkeypatch)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-leak-me-not")
    captured = {}

    def _run(argv, input, capture_output, encoding, errors, timeout, env):  # noqa: A002
        captured["env"] = env
        out_path = Path(argv[argv.index("-o") + 1])
        out_path.write_text(json.dumps(VALID_CODE_REVIEW), encoding="utf-8")
        return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

    monkeypatch.setattr(transport.subprocess, "run", Mock(side_effect=_run))

    transport.run_codex_review("code", tmp_path, "prompt", tmp_path)

    assert "ANTHROPIC_API_KEY" not in captured["env"]


def test_schema_invalid_output_is_error_and_not_copied(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_available(monkeypatch)
    fake_run = _fake_run_writing({"section": "s1"})  # missing required "review"
    monkeypatch.setattr(transport.subprocess, "run", fake_run)

    result = transport.run_codex_review("code", tmp_path, "prompt", tmp_path)

    assert result["status"] == "error"
    assert "schema validation" in result["reason"]
    assert not (tmp_path / "code_review_reply.json").exists()


def test_non_json_output_is_error_and_not_copied(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_available(monkeypatch)

    def _run(argv, input, capture_output, encoding, errors, timeout, env):  # noqa: A002
        out_path = Path(argv[argv.index("-o") + 1])
        out_path.write_text("not json at all {{{", encoding="utf-8")
        return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

    monkeypatch.setattr(transport.subprocess, "run", Mock(side_effect=_run))

    result = transport.run_codex_review("code", tmp_path, "prompt", tmp_path)

    assert result["status"] == "error"
    assert "not valid JSON" in result["reason"]
    assert not (tmp_path / "code_review_reply.json").exists()


def test_empty_output_is_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_available(monkeypatch)

    def _run(argv, input, capture_output, encoding, errors, timeout, env):  # noqa: A002
        return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

    monkeypatch.setattr(transport.subprocess, "run", Mock(side_effect=_run))

    result = transport.run_codex_review("code", tmp_path, "prompt", tmp_path)

    assert result["status"] == "error"
    assert "no output" in result["reason"]


def test_nonzero_exit_is_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_available(monkeypatch)
    fake_run = _fake_run_writing(VALID_CODE_REVIEW, returncode=1)
    monkeypatch.setattr(transport.subprocess, "run", fake_run)

    result = transport.run_codex_review("code", tmp_path, "prompt", tmp_path)

    assert result["status"] == "error"
    assert "exited 1" in result["reason"]


def test_default_max_retries_is_a_single_attempt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_available(monkeypatch)
    fake_run = _fake_run_writing(VALID_CODE_REVIEW, returncode=1)
    monkeypatch.setattr(transport.subprocess, "run", fake_run)

    transport.run_codex_review("code", tmp_path, "prompt", tmp_path)

    assert fake_run.call_count == 1
    assert transport.CODEX_REVIEW_MAX_RETRIES == 0


def test_timeout_is_reported(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_available(monkeypatch)

    def _timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd="codex", timeout=1)

    monkeypatch.setattr(transport.subprocess, "run", Mock(side_effect=_timeout))

    result = transport.run_codex_review("code", tmp_path, "prompt", tmp_path, timeout=1)

    assert result["status"] == "error"
    assert "timed out" in result["reason"]


def test_temp_file_is_removed_after_use(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_available(monkeypatch)
    fake_run = _fake_run_writing(VALID_CODE_REVIEW)
    monkeypatch.setattr(transport.subprocess, "run", fake_run)

    transport.run_codex_review("code", tmp_path, "prompt", tmp_path)

    leftovers = [p for p in tmp_path.iterdir() if p.name != "code_review_reply.json"]
    assert leftovers == []


def test_retry_does_not_reuse_a_stale_output_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Regression for doubt-reviewer HIGH, 2026-09-17: attempt 1's harness
    writes a complete, valid `-o` file and then exits nonzero; attempt 2
    exits 0 but writes nothing of its own. A shared temp dir across attempts
    would read attempt 1's stale valid file back as attempt 2's answer,
    recording a completed pass over a run that never actually produced one."""
    _patch_available(monkeypatch)
    calls = {"n": 0}

    def _run(argv, input, capture_output, encoding, errors, timeout, env):  # noqa: A002
        calls["n"] += 1
        if calls["n"] == 1:
            Path(argv[argv.index("-o") + 1]).write_text(json.dumps(VALID_CODE_REVIEW), encoding="utf-8")
            return subprocess.CompletedProcess(argv, 1, stdout="", stderr="")
        return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

    monkeypatch.setattr(transport.subprocess, "run", Mock(side_effect=_run))

    result = transport.run_codex_review("code", tmp_path, "prompt", tmp_path, max_retries=1)

    assert calls["n"] == 2
    assert result["status"] == "error"
    assert "no output" in result["reason"]
    assert not (tmp_path / "code_review_reply.json").exists()
