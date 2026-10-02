"""`model_reasoning_effort` in `run_codex_review`'s argv — split out of
`test_codex_review_transport.py` to stay under its 300-line cap (mirrors
that file's own precedent, `test_codex_review_transport_model_override.py`).

AGENTS.md has claimed "high reasoning for required review subagents" since
before this transport existed; nothing ever actually passed it to
`codex exec` until iterate-2026-09-20-m4-codex-subagent-dispatch.
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
#: One schema-valid payload per role -- a single shared `VALID_CODE_REVIEW`
#: shape written regardless of role would make `spec`/`doubt`/`plan_review`
#: calls fail schema validation and return `status: "error"` silently, since
#: none of the tests using it inspect `result["status"]` (External Review,
#: GLM leg, low, 2026-09-20).
_VALID_PAYLOADS: dict[str, dict] = {
    "spec": {"stage": "spec-compliance", "verdict": "PASS", "spec_citations": [], "summary": "ok"},
    "code": VALID_CODE_REVIEW,
    "doubt": {"stage": "doubt", "gating": "advisory-must-address", "trigger": "io-boundary", "doubts": [], "summary": "ok"},
    "plan_review": {"reviewer": "opus-plan-reviewer", "severity": "none", "findings": [], "summary": "ok"},
    "architecture_internal": {
        "reviewer": "architecture-internal-reviewer", "severity": "low", "findings": [], "summary": "ok",
    },
}


def _stub_resolve(role: str, worktree_root: Path, model: str | None, default: str) -> tuple[str, str]:
    if model is not None:
        return model, "the explicit model= argument"
    return default, "the hardcoded default"


def _patch_available(monkeypatch: pytest.MonkeyPatch, payload: dict = VALID_CODE_REVIEW) -> Mock:
    monkeypatch.setattr(transport, "is_codex_available", lambda **kw: (True, ""))
    monkeypatch.setattr(transport, "_resolve_codex_binary", lambda: "codex")
    monkeypatch.setattr(transport, "resolve_codex_review_model", _stub_resolve)

    def _run(argv, input, capture_output, encoding, errors, timeout, env):  # noqa: A002
        Path(argv[argv.index("-o") + 1]).write_text(json.dumps(payload), encoding="utf-8")
        return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

    fake_run = Mock(side_effect=_run)
    monkeypatch.setattr(transport.subprocess, "run", fake_run)
    return fake_run


def test_review_cascade_role_gets_reasoning_effort_flag(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake_run = _patch_available(monkeypatch)
    transport.run_codex_review("code", tmp_path, "prompt", tmp_path)
    argv = fake_run.call_args.args[0]
    idx = argv.index("-c")
    assert argv[idx + 1] == f"model_reasoning_effort={transport.CODEX_REVIEW_REASONING_EFFORT}"


@pytest.mark.parametrize("role", ["plan_review", "architecture_internal"])
def test_plan_side_roles_get_reasoning_effort_flag(
    role: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`plan_review` (trg-0a3c4edb) and `architecture_internal` carry the same
    `-c model_reasoning_effort=high` as the review cascade, and the rest of
    argv is exactly the pre-existing shape, with the flag appended after `-o`."""
    assert transport.CODEX_REVIEW_SANDBOX_MODE == "read-only"
    fake_run = _patch_available(monkeypatch, payload=_VALID_PAYLOADS[role])
    result = transport.run_codex_review(role, tmp_path, "prompt", tmp_path)
    assert result["status"] == "completed", result
    argv = fake_run.call_args.args[0]
    schema_path = str(transport.ROLE_SCHEMAS[role])
    assert argv == [
        "codex", "exec", "-m", transport.CODEX_REVIEW_MODEL, "--skip-git-repo-check",
        "--sandbox", "read-only", "--ignore-user-config", "--ignore-rules",
        "--ephemeral", "--cd", str(tmp_path),
        "--output-schema", schema_path, "-o", argv[argv.index("-o") + 1],
        "-c", f"model_reasoning_effort={transport.CODEX_REVIEW_REASONING_EFFORT}",
    ]


def test_reasoning_effort_roles_is_exactly_every_dispatched_role(monkeypatch: pytest.MonkeyPatch) -> None:
    """A future role added to `ROLE_SCHEMAS` without a deliberate call on its
    effort membership must fail this exact-set check rather than silently
    falling into the no-flag branch unremarked (External Review, GLM leg,
    low, 2026-09-20)."""
    assert transport.REASONING_EFFORT_ROLES == frozenset(
        {"spec", "code", "doubt", "plan_review", "architecture_internal"}
    )
    assert transport.REASONING_EFFORT_ROLES == transport.ROLE_SCHEMAS.keys()


def test_all_three_review_cascade_roles_get_the_flag(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    for role in ("spec", "code", "doubt"):
        with monkeypatch.context() as m:
            fake_run = _patch_available(m, payload=_VALID_PAYLOADS[role])
            result = transport.run_codex_review(role, tmp_path, "prompt", tmp_path)
        assert result["status"] == "completed", result
        argv = fake_run.call_args.args[0]
        assert f"model_reasoning_effort={transport.CODEX_REVIEW_REASONING_EFFORT}" in argv


def test_reasoning_effort_flag_still_added_under_an_explicit_model_override(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`model_reasoning_effort` injection is keyed on ROLE
    (`REASONING_EFFORT_ROLES` membership), never on which model answers —
    tested independently of the model-override axis (Internal Plan Review,
    medium, 2026-09-20). NOTE: this docstring previously claimed an override
    to a model that rejects the flag makes `codex exec` fail at launch --
    two live probes on 2026-09-20 (see `codex_review_roles.py`'s own
    comment) showed real `codex exec` silently IGNORES an unrecognized `-c`
    key instead of erroring, so that claim was wrong; this test only proves
    the flag reaches argv under an override, not what happens if the
    resolved model rejects it (doubt-reviewer, high, 2026-09-20)."""
    fake_run = _patch_available(monkeypatch)
    result = transport.run_codex_review("code", tmp_path, "prompt", tmp_path, model="gpt-9.9-nonexistent")
    assert result["status"] == "completed", result
    argv = fake_run.call_args.args[0]
    assert "-m" in argv and argv[argv.index("-m") + 1] == "gpt-9.9-nonexistent"
    assert f"model_reasoning_effort={transport.CODEX_REVIEW_REASONING_EFFORT}" in argv
    # `transport_note` names the RESOLVED (overridden) model, never the
    # hardcoded default -- an overridden run recording the wrong model in
    # `reviews.json` would be a worse defect than recording none at all
    # (External Review, GLM leg, low, 2026-09-20). Asserted as the exact
    # string, not just a prefix -- a `startswith` check alone would still
    # pass an override that dropped `effort=`/`sandbox=` entirely (External
    # Review, OpenAI leg, low, 2026-09-20).
    assert result["transport_note"] == (
        f"gpt-9.9-nonexistent effort={transport.CODEX_REVIEW_REASONING_EFFORT} "
        f"sandbox={transport.CODEX_REVIEW_SANDBOX_MODE}"
    )


@pytest.mark.parametrize("role", ["plan_review", "architecture_internal"])
def test_plan_side_transport_note_names_effort_and_sandbox(
    role: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_run = _patch_available(monkeypatch, payload=_VALID_PAYLOADS[role])
    result = transport.run_codex_review(role, tmp_path, "prompt", tmp_path)
    assert result["status"] == "completed", result
    assert f"model_reasoning_effort={transport.CODEX_REVIEW_REASONING_EFFORT}" in fake_run.call_args.args[0]
    assert result["transport_note"] == (
        f"{transport.CODEX_REVIEW_MODEL} effort={transport.CODEX_REVIEW_REASONING_EFFORT} "
        f"sandbox={transport.CODEX_REVIEW_SANDBOX_MODE}"
    )


def test_architecture_internal_has_its_own_canonical_reply(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Never `plan_review_reply.json`: Internal Plan Review writes that name in
    the same out_dir, and a shared name would let one pass clobber the other."""
    with monkeypatch.context() as m:
        _patch_available(m, payload=_VALID_PAYLOADS["plan_review"])
        plan = transport.run_codex_review("plan_review", tmp_path, "prompt", tmp_path)
    with monkeypatch.context() as m:
        _patch_available(m, payload=_VALID_PAYLOADS["architecture_internal"])
        arch = transport.run_codex_review("architecture_internal", tmp_path, "prompt", tmp_path)
    assert plan["status"] == "completed", plan
    assert arch["status"] == "completed", arch
    assert Path(arch["canonical_path"]).name == "architecture_internal_reply.json"
    assert (tmp_path / "plan_review_reply.json").is_file()
    assert (tmp_path / "architecture_internal_reply.json").is_file()
    assert json.loads((tmp_path / "plan_review_reply.json").read_text(encoding="utf-8"))["reviewer"] == "opus-plan-reviewer"


def test_architecture_internal_rejects_a_plan_review_shaped_reply(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Own schema: the reviewer const and category enum differ from plan_review's."""
    _patch_available(monkeypatch, payload=_VALID_PAYLOADS["plan_review"])
    result = transport.run_codex_review("architecture_internal", tmp_path, "prompt", tmp_path)
    assert result["status"] == "error", result
    assert "schema validation" in result["reason"]


def test_argv_reasoning_effort_flag_and_transport_note_effort_agree_for_every_role(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """argv gating (`codex_review_transport.py`'s own `role in
    REASONING_EFFORT_ROLES` check) and evidence gating (`transport_note_for`'s
    identical check, now living in a different module) are two independent
    evaluations of the same set membership with nothing tying them together --
    deleting the argv branch entirely would leave `transport_note` claiming
    an effort that was never requested, undetected by any other test
    (doubt-reviewer, high, 2026-09-20)."""
    for role in transport.ROLE_SCHEMAS:
        with monkeypatch.context() as m:
            fake_run = _patch_available(m, payload=_VALID_PAYLOADS[role])
            result = transport.run_codex_review(role, tmp_path, "prompt", tmp_path)
        assert result["status"] == "completed", result
        argv = fake_run.call_args.args[0]
        argv_has_effort = "-c" in argv and any("model_reasoning_effort" in p for p in argv)
        note_has_effort = "effort=" in result["transport_note"]
        assert argv_has_effort == note_has_effort, (role, argv, result["transport_note"])
