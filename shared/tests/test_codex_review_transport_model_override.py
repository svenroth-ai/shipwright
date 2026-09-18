"""`lib/codex_review_transport.run_codex_review`'s `model` override (AC33/
AC35, supersedes AC2) — split from `test_codex_review_transport.py` to stay
under the 300-line source cap (iterate-2026-09-18-codex-review-tier-config).
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

VALID_CODE_REVIEW = {"section": "s1", "review": []}


def _patch_available(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(transport, "is_codex_available", lambda **kw: (True, ""))
    monkeypatch.setattr(transport, "_resolve_codex_binary", lambda: "codex")


def _fake_run_writing(payload: dict, *, returncode: int = 0) -> Mock:
    def _run(argv, input, capture_output, encoding, errors, timeout, env):  # noqa: A002
        out_path = Path(argv[argv.index("-o") + 1])
        if returncode == 0:
            out_path.write_text(json.dumps(payload), encoding="utf-8")
        return subprocess.CompletedProcess(argv, returncode, stdout="", stderr="")
    return Mock(side_effect=_run)


def test_default_model_is_the_hardcoded_constant(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_available(monkeypatch)
    fake_run = _fake_run_writing(VALID_CODE_REVIEW)
    monkeypatch.setattr(transport.subprocess, "run", fake_run)

    result = transport.run_codex_review("code", tmp_path, "prompt", tmp_path)

    assert result["model"] == transport.CODEX_REVIEW_MODEL
    argv = fake_run.call_args.args[0] if fake_run.call_args.args else fake_run.call_args.kwargs["argv"]
    assert argv[argv.index("-m") + 1] == transport.CODEX_REVIEW_MODEL


def test_model_override_is_used_and_returned(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_available(monkeypatch)
    fake_run = _fake_run_writing(VALID_CODE_REVIEW)
    monkeypatch.setattr(transport.subprocess, "run", fake_run)

    result = transport.run_codex_review("code", tmp_path, "prompt", tmp_path, model="gpt-5.6-terra")

    assert result["status"] == "completed"
    assert result["model"] == "gpt-5.6-terra"
    argv = fake_run.call_args.args[0] if fake_run.call_args.args else fake_run.call_args.kwargs["argv"]
    assert argv[argv.index("-m") + 1] == "gpt-5.6-terra"


@pytest.mark.parametrize("hostile", [
    "gpt-5 && rm -rf /", "gpt-5|whoami", 'gpt-5"', "gpt 5", "",
    "gpt-5.6-sol\n",  # trailing newline: `$` matches before it under .match() (code-reviewer MEDIUM, 2026-09-18)
    "gpt-5\r\n",
])
def test_hostile_model_slug_raises_before_any_launch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, hostile: str
) -> None:
    fake_run = Mock()
    monkeypatch.setattr(transport.subprocess, "run", fake_run)

    with pytest.raises(transport.CodexReviewTransportError):
        transport.run_codex_review("code", tmp_path, "prompt", tmp_path, model=hostile)

    fake_run.assert_not_called()


@pytest.mark.parametrize("non_string", [5, 5.0, b"gpt-5.6-sol", ["gpt-5.6-sol"], {"model": "x"}])
def test_non_string_model_raises_transport_error_not_typeerror(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, non_string: object
) -> None:
    """`str | None` is not runtime-enforced -- a direct caller violating it
    must still get the documented `CodexReviewTransportError`, never an
    undocumented `TypeError` from `.fullmatch()` (external code review,
    MEDIUM, 2026-09-18)."""
    fake_run = Mock()
    monkeypatch.setattr(transport.subprocess, "run", fake_run)

    with pytest.raises(transport.CodexReviewTransportError):
        transport.run_codex_review("code", tmp_path, "prompt", tmp_path, model=non_string)  # type: ignore[arg-type]

    fake_run.assert_not_called()


@pytest.mark.parametrize("real_slug", [
    "gpt-5.6-sol", "gpt-5.6-terra", "gpt-5.6-luna", "gpt-6-astra", transport.CODEX_REVIEW_MODEL,
])
def test_real_codex_model_slugs_pass_the_allowlist(real_slug: str) -> None:
    # `.fullmatch()`, matching the only call form the transport itself uses
    # (`\A`/`\Z` makes `.match()` equivalent here, but the test characterising
    # the pattern must not model the unsafe form — doubt-reviewer MEDIUM,
    # 2026-09-18). `CODEX_REVIEW_MODEL` itself is included so editing the
    # constant — the documented stale-default residual gap — can fail this
    # test, not just coincidentally match it by spelling.
    assert transport._CODEX_MODEL_SLUG_PATTERN.fullmatch(real_slug)


def test_error_result_also_carries_the_effective_model(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_available(monkeypatch)
    fake_run = _fake_run_writing(VALID_CODE_REVIEW, returncode=1)
    monkeypatch.setattr(transport.subprocess, "run", fake_run)

    result = transport.run_codex_review("code", tmp_path, "prompt", tmp_path, model="gpt-5.6-luna")

    assert result["status"] == "error"
    assert result["model"] == "gpt-5.6-luna"
