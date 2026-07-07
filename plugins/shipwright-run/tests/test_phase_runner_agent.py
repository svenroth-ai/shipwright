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
