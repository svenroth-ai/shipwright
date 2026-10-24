"""Phase-runner subagent contract tests (Campaign 2026-07-07, SS4).

AC1 — the phase-runner persists artifacts reliably. The agent DEFINITION must
carry a write path (so it persists its OWN outputs — the direct fix for the
section-writer no-write-tool bug), and the persistence contract must hold
end-to-end: a phase-runner that writes its artifacts to disk and reports them in
the RESULT CONTRACT passes the orchestrator's on-disk guard, while a
claimed-but-unwritten artifact is caught.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts" / "lib"))

from single_session.orchestrator_context import verify_artifacts_exist  # noqa: E402
from single_session.result_contract import (  # noqa: E402
    MAX_SUMMARY_CHARS,
    build_phase_runner_result,
    is_valid_result,
)

AGENT_MD = Path(__file__).resolve().parent.parent / "agents" / "phase-runner.md"


def _frontmatter(md: str) -> dict[str, str]:
    """Parse the leading --- ... --- frontmatter into a flat dict."""
    assert md.startswith("---"), "agent file must open with frontmatter"
    _, fm, _body = md.split("---", 2)
    out: dict[str, str] = {}
    for line in fm.strip().splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            out[k.strip()] = v.strip()
    return out


def test_phase_runner_agent_exists():
    assert AGENT_MD.exists(), f"missing phase-runner agent def at {AGENT_MD}"


def test_phase_runner_has_write_path():
    fm = _frontmatter(AGENT_MD.read_text(encoding="utf-8"))
    assert fm.get("name") == "phase-runner"
    tools = {t.strip() for t in fm.get("tools", "").split(",")}
    # The write path is THE fix for the section-writer bug (it had no write tool).
    assert "Write" in tools, f"phase-runner must have a write path, got {tools}"
    assert "Edit" in tools
    assert "Bash" in tools


def test_phase_runner_briefs_disk_persistence_not_hook():
    text = AGENT_MD.read_text(encoding="utf-8")
    low = text.lower()
    # Concrete required behaviours (not just word presence): write BEFORE return,
    # do NOT rely on a Stop/SubagentStop hook, artifacts are repo-relative on disk.
    assert "before you return" in low
    assert "do not rely on any stop" in low or "do not rely on a" in low
    assert "subagentstop" in low or "stop hook" in low or "stop / subagentstop" in low
    assert "repo-relative" in low
    assert "result contract" in low
    # The compact-summary ceiling is documented so the summary stays bounded.
    assert str(MAX_SUMMARY_CHARS) in text


def test_phase_runner_persistence_fixture_proof(tmp_path):
    """A phase-runner that WRITES its artifacts to disk and reports them yields a
    valid, on-disk-verified result — the AC1 persistence proof."""
    project = tmp_path / "proj"
    (project / "artifacts").mkdir(parents=True)
    (project / "artifacts" / "plan.md").write_text("# plan\n", encoding="utf-8")

    result = build_phase_runner_result(
        ok=True, phase="plan", summary="planned; wrote sections",
        artifacts=["artifacts/plan.md"], split_id="01-core",
    )
    assert is_valid_result(result)
    assert verify_artifacts_exist(project, result["artifacts"]) == []


def test_phase_runner_unpersisted_artifact_is_caught(tmp_path):
    """A phase-runner that CLAIMS an artifact without writing it is caught by the
    on-disk guard — the section-writer silent-loss failure mode, now detected."""
    project = tmp_path / "proj"
    project.mkdir()
    result = build_phase_runner_result(
        ok=True, phase="plan", summary="claimed but never wrote it",
        artifacts=["artifacts/plan.md"],
    )
    assert verify_artifacts_exist(project, result["artifacts"]) == ["artifacts/plan.md"]


@pytest.mark.covers("FR-01.01/AC01")
def test_phase_runner_has_agent_tool_for_reviewers_only():
    text = AGENT_MD.read_text(encoding="utf-8")
    tools = {t.strip() for t in _frontmatter(text).get("tools", "").split(",")}
    assert "Agent" in tools
    low = text.lower()
    # Fan-out stays the operator's call; the prompt (not an allowlist) enforces it.
    assert "must not spawn anything else" in low
    assert "section-builder" in low
    assert "delegated-to-orchestrator" in text
    assert "review_status" in text


@pytest.mark.covers("FR-01.01/AC01")
def test_build_code_review_has_not_run_branch():
    cr = AGENT_MD.parents[2] / "shipwright-build" / "skills" / "build" / "references" / "code-review.md"
    text = cr.read_text(encoding="utf-8")
    assert "--reason-code delegated-to-orchestrator" in text
    assert "never a silent skip" in text


@pytest.mark.covers("FR-01.01/AC01")
def test_review_status_is_backward_compatible_and_validated():
    base = dict(ok=True, phase="build", summary="built", artifacts=[])
    assert is_valid_result(build_phase_runner_result(**base))  # absent = valid
    deferred = {"state": "deferred", "reason_code": "delegated-to-orchestrator",
                "passes": {"spec": "not_run"}}
    assert build_phase_runner_result(**base, review_status=deferred)["review_status"] == deferred
    assert is_valid_result(build_phase_runner_result(**base, review_status={"state": "completed"}))
    for bad in ({"state": "deferred"}, {"state": "bogus"}, "x",
                {"state": "completed", "passes": {"spec": 1}}):
        assert not is_valid_result({**base, "review_status": bad}), bad
