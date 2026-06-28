"""Realistic data-preservation test mirroring the trigger scenario (sub-iterate F).

The original sub-iterate-C tests used `"x" * 200` to fake a 16 KB CLAUDE.md.
This test uses content shaped like the actual user scenario: a real
multi-section CLAUDE.md with regression-guard rules, and a decision_log
with 58 ADRs spanning 6 weeks. Verifies the full preservation pipeline
end-to-end via subprocess.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest


pytestmark = pytest.mark.slow


REPO_ROOT = Path(__file__).resolve().parents[3]
GENERATE = REPO_ROOT / "plugins" / "shipwright-adopt" / "scripts" / "tools" / "generate_adoption_artifacts.py"


def _git_init(root: Path) -> None:
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=root, check=True)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t",
                    "commit", "--allow-empty", "-m", "init", "-q"], cwd=root, check=True)


def _realistic_claude_md() -> str:
    """A ~16 KB CLAUDE.md shaped like the trigger scenario — sectioned, prose-heavy,
    with explicit DO-NOT regression guards that adopt's scaffold would destroy."""
    sections = [
        "# Webui Project — load-bearing rules\n\n",
        "## WHAT\n\nAssistant-UI based chat for Shipwright pipelines.\n\n",
        "## DO NOT\n\n"
        + "- Do not introduce CLI subprocess in the chat path — see ADR-019.\n"
        + "- Do not regress on the assistant-ui pivot decided in iterate 7.\n"
        + "- Do not stage webui/* paths when committing framework work.\n"
        + "- Do not auto-amend commits — use new commits instead.\n\n",
    ]
    # Pad with realistic-shape prose to reach ~16 KB
    paragraph = (
        "This rule exists because the previous implementation conflated chat lifecycle "
        "with subprocess lifecycle, which made graceful shutdown impossible and led to "
        "orphaned tool_result messages that broke the assistant-ui rendering. The fix "
        "is documented in ADR-019 and the hotfix is commit 8186165.\n\n"
    )
    body = "".join(sections) + (paragraph * 60)  # ~17 KB
    return body


def _realistic_decision_log(n_adrs: int = 58) -> str:
    """A decision_log with N ADRs, dated across multiple weeks, with realistic body."""
    body = "# Decision Log\n\n"
    for i in range(1, n_adrs + 1):
        date_day = 1 + (i - 1) % 30  # spread across April
        body += (
            f"## ADR-{i:04d}: Decision number {i}\n\n"
            f"- **Status**: accepted\n"
            f"- **Date**: 2026-04-{date_day:02d}\n\n"
            f"### Context\n\nDecision {i} addresses a real concern from the iterate "
            f"that introduced it.\n\n"
            f"### Decision\n\nWe chose option B over A because of cost/benefit.\n\n"
            f"### Consequences\n\nFuture work in this area must respect this decision; "
            f"backwards-compat is maintained via shim.\n\n---\n\n"
        )
    return body


def _write_snapshot(project_root: Path) -> None:
    snap_dir = project_root / ".shipwright" / "adopt"
    snap_dir.mkdir(parents=True)
    (snap_dir / "snapshot.json").write_text(json.dumps({
        "stack": {"primary_language": "typescript", "multi_service": {"detected": False}},
        "profile": {"matched": "generic"},
        "commands": {"dev": None, "build": None, "test": None},
        "features": [{"route": "/", "source_file": "src/index.ts"}],
        "git": {"commits_total": 230, "contributors_total": 5, "major_refactor_commits": []},
        "folders": {"layers": [], "loc_by_layer": {}},
        "conventions": {},
        "ci_pipeline": {"provider": "github-actions"},
        "excludes": [],
    }), encoding="utf-8")


def test_realistic_claude_and_decision_log_preserved_e2e(tmp_path: Path) -> None:
    _git_init(tmp_path)
    _write_snapshot(tmp_path)

    big_claude = _realistic_claude_md()
    rich_log = _realistic_decision_log(58)

    # Plant the at-risk files before adopt runs
    (tmp_path / "CLAUDE.md").write_text(big_claude, encoding="utf-8")
    (tmp_path / ".shipwright" / "agent_docs").mkdir(parents=True)
    (tmp_path / ".shipwright" / "agent_docs" / "decision_log.md").write_text(rich_log, encoding="utf-8")

    claude_size = (tmp_path / "CLAUDE.md").stat().st_size
    log_size = (tmp_path / ".shipwright" / "agent_docs" / "decision_log.md").stat().st_size
    # Sanity: we built realistic-shape content. The user trigger scenario was
    # 137 KB — our synthetic 58 ADRs land closer to 20 KB. The shape (number of
    # ADRs + multi-section structure) is what matters for the preservation test.
    assert claude_size > 10_000, f"test fixture not big enough: {claude_size}"
    assert log_size > 15_000, f"test fixture not big enough: {log_size}"

    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"

    r = subprocess.run(
        ["uv", "run", "python", str(GENERATE), "--project-root", str(tmp_path)],
        capture_output=True, text=True, env=env, timeout=120, check=False,
    )
    assert r.returncode == 0, f"adopt failed: stdout={r.stdout[-1000:]}\nstderr={r.stderr[-1000:]}"

    # CLAUDE.md must be UNTOUCHED (load-bearing)
    final_claude = (tmp_path / "CLAUDE.md").read_text(encoding="utf-8")
    assert final_claude == big_claude, "load-bearing CLAUDE.md was overwritten"

    # Adopt's suggested side-file must exist
    suggested = tmp_path / ".shipwright" / "adopt" / "CLAUDE.md.adopt-suggested"
    assert suggested.exists()

    # decision_log was MERGED — every original ADR must still be findable verbatim
    final_log = (tmp_path / ".shipwright" / "agent_docs" / "decision_log.md").read_text(encoding="utf-8")
    for i in (1, 7, 23, 42, 58):
        assert f"ADR-{i:04d}: Decision number {i}" in final_log, (
            f"original ADR-{i:04d} lost from merged decision_log"
        )
    # And the new adoption ADR should appear (prepended). With max
    # existing id = 58 the adoption ADR is ADR-059 — adopt no longer
    # silently collides on ADR-001 / ADR-0001 with the existing log.
    assert "Adopt this repository into the Shipwright SDLC" in final_log
    assert "ADR-059: Adopt this repository into the Shipwright SDLC" in final_log
    # Defensive: the old 4-digit ADR-0001 form must not show up in
    # adopt-written output (existing user ADRs still use 4-digit by
    # convention; that's their text and is preserved verbatim).
    assert "ADR-0059" not in final_log

    # Backups must contain the originals
    claude_backup = tmp_path / ".shipwright" / "adopt" / "backups" / "CLAUDE.md.preserved"
    log_backup = tmp_path / ".shipwright" / "adopt" / "backups" / ".shipwright" / "agent_docs" / "decision_log.md.preserved"
    assert claude_backup.read_text(encoding="utf-8") == big_claude
    assert log_backup.read_text(encoding="utf-8") == rich_log

    # preservation_log.json captured both actions
    plog = json.loads(
        (tmp_path / ".shipwright" / "adopt" / "preservation_log.json").read_text(encoding="utf-8")
    )
    by_file = {e["file"]: e for e in plog["entries"]}
    assert by_file["CLAUDE.md"]["action"] == "skipped_loadbearing"
    assert by_file[".shipwright/agent_docs/decision_log.md"]["action"] == "merged"
    # Note records the original ADR count
    assert "58" in by_file[".shipwright/agent_docs/decision_log.md"].get("note", "")
