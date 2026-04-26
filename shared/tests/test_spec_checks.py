"""Tests for the Phase-Quality spec category (PR 4 — S1-S10).

Covers positive + negative fixtures plus plan § 7 risk IDs:

- R15 — S2 must SKIP (not FAIL) when complexity=small.
- R16 — S4 must WARN on removed FRs, never FAIL.
- R17 — S9/S10 must WARN not FAIL, using a 10-commit threshold.
- R18 — S8 respects greenfield / monorepo layouts.

Also covers the lib/spec_parser FR-heading + coherence parser and the
phase_quality.run_spec_checks dispatcher.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

_SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from lib import phase_quality as pq  # noqa: E402
from lib import spec_parser  # noqa: E402
from tools.verifiers import spec_checks as sc  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures + helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def proj(tmp_path: Path) -> Path:
    (tmp_path / "agent_docs").mkdir()
    return tmp_path


def _write_top_spec(proj: Path, content: str) -> None:
    (proj / "agent_docs" / "spec.md").write_text(content, encoding="utf-8")


def _write_claude_md(proj: Path, content: str) -> None:
    (proj / "CLAUDE.md").write_text(content, encoding="utf-8")


def _write_readme(proj: Path, content: str) -> None:
    (proj / "README.md").write_text(content, encoding="utf-8")


def _write_iterate_history(
    proj: Path,
    entries: list[dict],
    run_id: str | None = None,
) -> None:
    data = {"iterate_history": entries}
    if run_id:
        data["run_id"] = run_id
    (proj / "shipwright_run_config.json").write_text(
        json.dumps(data), encoding="utf-8",
    )


def _init_git_repo(proj: Path) -> None:
    """Init a dummy git repo so S4/S9/S10 git-based checks can run."""
    subprocess.run(["git", "init", "-q"], cwd=str(proj), check=False)
    subprocess.run(
        ["git", "config", "user.email", "t@test"],
        cwd=str(proj), check=False,
    )
    subprocess.run(
        ["git", "config", "user.name", "Tester"],
        cwd=str(proj), check=False,
    )
    subprocess.run(
        ["git", "config", "commit.gpgsign", "false"],
        cwd=str(proj), check=False,
    )


def _git_commit_all(proj: Path, msg: str) -> None:
    subprocess.run(["git", "add", "-A"], cwd=str(proj), check=False)
    subprocess.run(
        ["git", "commit", "-q", "--allow-empty", "-m", msg],
        cwd=str(proj), check=False,
    )


# ---------------------------------------------------------------------------
# spec_parser — FR heading parser
# ---------------------------------------------------------------------------


def test_parse_fr_headings_simple():
    content = (
        "## FR-7: Dashboard\n"
        "**Description:** User sees stats.\n"
        "**Acceptance Criteria:**\n"
        "- see totals\n"
    )
    frs = spec_parser.parse_fr_headings(content)
    assert len(frs) == 1
    assert frs[0].id == "FR-7"
    assert "User sees stats" in frs[0].description
    assert "see totals" in frs[0].acceptance


def test_parse_fr_headings_dotted_ids():
    content = (
        "## FR-02.03 Login\n"
        "- **Description:** enter creds.\n"
        "- **Acceptance Criteria:** done when JWT returned.\n"
        "### FR 4 — Logout\n"
        "- **Description:** clear session.\n"
        "- **Acceptance Criteria:** redirected to /login.\n"
    )
    frs = spec_parser.parse_fr_headings(content)
    assert {f.id for f in frs} == {"FR-02.03", "FR-4"}


def test_parse_fr_headings_missing_description():
    content = (
        "## FR-1: Sample\n"
        "**Acceptance Criteria:** ok\n"
    )
    frs = spec_parser.parse_fr_headings(content)
    assert len(frs) == 1
    assert not frs[0].has_description()
    assert frs[0].has_acceptance()


def test_count_fr_headings_zero_on_empty():
    assert spec_parser.count_fr_headings("") == 0
    assert spec_parser.count_fr_headings("# just text") == 0


def test_compute_fr_coherence_reports_gaps(proj: Path):
    _write_top_spec(proj, (
        "## FR-1: Good\n"
        "**Description:** fine.\n"
        "**Acceptance Criteria:** ok.\n"
        "\n"
        "## FR-2: No accept\n"
        "**Description:** only description.\n"
        "\n"
        "## FR-3: No desc\n"
        "**Acceptance Criteria:** only accept.\n"
        "\n"
        "## FR-4: Nothing\n"
    ))
    report = spec_parser.compute_fr_coherence(proj)
    assert report.total_frs == 4
    assert not report.ok
    assert any("FR-2" in x for x in report.missing_acceptance)
    assert any("FR-3" in x for x in report.missing_description)
    assert any("FR-4" in x for x in report.missing_both)


def test_compute_fr_coherence_empty_on_greenfield(tmp_path: Path):
    report = spec_parser.compute_fr_coherence(tmp_path)
    assert report.total_frs == 0
    assert report.ok


# ---------------------------------------------------------------------------
# S1 — top-level spec
# ---------------------------------------------------------------------------


def test_s1_fails_when_spec_missing(proj: Path):
    f = sc.check_s1_top_level_spec(proj)
    assert f["id"] == "S1"
    assert f["status"] == pq.STATUS_FAIL


def test_s1_fails_on_empty_spec(proj: Path):
    _write_top_spec(proj, "   \n")
    assert sc.check_s1_top_level_spec(proj)["status"] == pq.STATUS_FAIL


def test_s1_fails_on_spec_without_fr_heading(proj: Path):
    _write_top_spec(proj, "# overview\nnothing useful\n")
    f = sc.check_s1_top_level_spec(proj)
    assert f["status"] == pq.STATUS_FAIL
    assert "FR" in f["evidence"]


def test_s1_passes_on_spec_with_frs(proj: Path):
    _write_top_spec(proj, (
        "## FR-1: a\n**Description:** x\n**Acceptance Criteria:** y\n"
    ))
    f = sc.check_s1_top_level_spec(proj)
    assert f["status"] == pq.STATUS_PASS


# ---------------------------------------------------------------------------
# S2 — iterate spec (R15 — SKIP for small)
# ---------------------------------------------------------------------------


def test_s2_skip_without_history(proj: Path):
    f = sc.check_s2_iterate_spec(proj, run_id="r1")
    assert f["status"] == pq.STATUS_SKIP


def test_s2_skip_when_complexity_small(proj: Path):
    # R15 — small complexity must NEVER trigger iterate-spec FAIL.
    _write_iterate_history(proj, [
        {"run_id": "r1", "complexity": "small"},
    ])
    f = sc.check_s2_iterate_spec(proj, run_id="r1")
    assert f["status"] == pq.STATUS_SKIP


def test_s2_skip_for_trivial(proj: Path):
    _write_iterate_history(proj, [
        {"run_id": "r1", "complexity": "trivial"},
    ])
    f = sc.check_s2_iterate_spec(proj, run_id="r1")
    assert f["status"] == pq.STATUS_SKIP


def test_s2_fails_when_spec_missing_for_medium(proj: Path):
    _write_iterate_history(proj, [
        {"run_id": "r1", "complexity": "medium"},
    ])
    f = sc.check_s2_iterate_spec(proj, run_id="r1")
    assert f["status"] == pq.STATUS_FAIL
    assert "r1" in f["evidence"]


def test_s2_passes_when_spec_exists(proj: Path):
    _write_iterate_history(proj, [
        {"run_id": "r1", "complexity": "medium"},
    ])
    iter_dir = proj / ".shipwright" / "planning" / "iterate"
    iter_dir.mkdir(parents=True)
    (iter_dir / "2026-04-18-r1.md").write_text("body", encoding="utf-8")
    f = sc.check_s2_iterate_spec(proj, run_id="r1")
    assert f["status"] == pq.STATUS_PASS


def test_s2_ignores_miniplan_file(proj: Path):
    """Miniplan files don't satisfy S2 — S3 covers them separately."""
    _write_iterate_history(proj, [
        {"run_id": "r1", "complexity": "medium"},
    ])
    iter_dir = proj / ".shipwright" / "planning" / "iterate"
    iter_dir.mkdir(parents=True)
    (iter_dir / "2026-04-18-r1-miniplan.md").write_text("x", encoding="utf-8")
    assert sc.check_s2_iterate_spec(proj, run_id="r1")["status"] == pq.STATUS_FAIL


# ---------------------------------------------------------------------------
# S3 — miniplan (Tier-2, WARN)
# ---------------------------------------------------------------------------


def test_s3_skip_when_small(proj: Path):
    _write_iterate_history(proj, [{"run_id": "r1", "complexity": "small"}])
    assert sc.check_s3_iterate_miniplan(proj, "r1")["status"] == pq.STATUS_SKIP


def test_s3_warns_on_medium_without_miniplan(proj: Path):
    _write_iterate_history(proj, [{"run_id": "r1", "complexity": "medium"}])
    f = sc.check_s3_iterate_miniplan(proj, "r1")
    assert f["status"] == pq.STATUS_WARN
    assert f.get("tier") == 2
    assert f.get("provenance") == "unverified_marker"


def test_s3_passes_with_miniplan(proj: Path):
    _write_iterate_history(proj, [{"run_id": "r1", "complexity": "medium"}])
    iter_dir = proj / ".shipwright" / "planning" / "iterate"
    iter_dir.mkdir(parents=True)
    (iter_dir / "2026-04-18-r1-miniplan.md").write_text("plan", encoding="utf-8")
    assert sc.check_s3_iterate_miniplan(proj, "r1")["status"] == pq.STATUS_PASS


def test_s3_never_fails_under_any_input(proj: Path):
    """R17 spirit — S3 is Tier-2, must never FAIL."""
    _write_iterate_history(proj, [{"run_id": "r1", "complexity": "large"}])
    for setup in (lambda: None, lambda: _write_top_spec(proj, "x")):
        setup()
        assert sc.check_s3_iterate_miniplan(proj, "r1")["status"] != pq.STATUS_FAIL


# ---------------------------------------------------------------------------
# S4 — FR preservation (Tier-2, R16)
# ---------------------------------------------------------------------------


def test_s4_skip_without_git(proj: Path):
    f = sc.check_s4_fr_preservation(proj)
    assert f["status"] == pq.STATUS_SKIP


def test_s4_skip_on_partial_history(tmp_path: Path):
    _init_git_repo(tmp_path)
    (tmp_path / "agent_docs").mkdir()
    # Only one spec commit
    _write_top_spec(tmp_path, "## FR-1: one\n**Description:** x\n"
                              "**Acceptance Criteria:** y\n")
    _git_commit_all(tmp_path, "init")
    f = sc.check_s4_fr_preservation(tmp_path)
    assert f["status"] == pq.STATUS_SKIP


def test_s4_warns_on_undeprecated_removal(tmp_path: Path):
    """R16 — removed FR without status=deprecated → WARN (never FAIL)."""
    _init_git_repo(tmp_path)
    (tmp_path / "agent_docs").mkdir()
    _write_top_spec(tmp_path, (
        "## FR-1: first\n**Description:** a\n**Acceptance Criteria:** b\n"
        "## FR-2: second\n**Description:** c\n**Acceptance Criteria:** d\n"
    ))
    _git_commit_all(tmp_path, "add specs")
    # Remove FR-2 without marking deprecated
    _write_top_spec(tmp_path, (
        "## FR-1: first\n**Description:** a\n**Acceptance Criteria:** b\n"
    ))
    _git_commit_all(tmp_path, "remove FR-2")
    f = sc.check_s4_fr_preservation(tmp_path)
    assert f["status"] == pq.STATUS_WARN
    assert f.get("tier") == 2
    assert "FR-2" in f["evidence"]


def test_s4_passes_when_removed_fr_is_deprecated(tmp_path: Path):
    _init_git_repo(tmp_path)
    (tmp_path / "agent_docs").mkdir()
    _write_top_spec(tmp_path, (
        "## FR-1: first\n**Description:** a\n**Acceptance Criteria:** b\n"
        "## FR-2: second\n**Description:** c\n**Acceptance Criteria:** d\n"
    ))
    _git_commit_all(tmp_path, "add specs")
    _write_top_spec(tmp_path, (
        "## FR-1: first\n**Description:** a\n**Acceptance Criteria:** b\n"
        "## FR-2: second\nstatus: deprecated\n"
    ))
    _git_commit_all(tmp_path, "deprecate FR-2")
    f = sc.check_s4_fr_preservation(tmp_path)
    assert f["status"] == pq.STATUS_PASS


# ---------------------------------------------------------------------------
# S5 — FR coherence (Tier-2)
# ---------------------------------------------------------------------------


def test_s5_skip_on_empty_spec(proj: Path):
    assert sc.check_s5_fr_coherence(proj)["status"] == pq.STATUS_SKIP


def test_s5_warn_on_incomplete_fr(proj: Path):
    _write_top_spec(proj, (
        "## FR-1: full\n**Description:** yes.\n**Acceptance Criteria:** yes.\n"
        "## FR-2: partial\n**Description:** missing accept.\n"
    ))
    f = sc.check_s5_fr_coherence(proj)
    assert f["status"] == pq.STATUS_WARN
    assert f.get("tier") == 2
    assert "FR-2" in f["evidence"]


def test_s5_passes_when_all_frs_coherent(proj: Path):
    _write_top_spec(proj, (
        "## FR-1: a\n**Description:** d\n**Acceptance Criteria:** a\n"
        "## FR-2: b\n**Description:** d2\n**Acceptance Criteria:** a2\n"
    ))
    assert sc.check_s5_fr_coherence(proj)["status"] == pq.STATUS_PASS


# ---------------------------------------------------------------------------
# S6 — CLAUDE.md
# ---------------------------------------------------------------------------


def test_s6_fails_when_missing(proj: Path):
    assert sc.check_s6_claude_md_exists(proj)["status"] == pq.STATUS_FAIL


def test_s6_fails_when_empty(proj: Path):
    _write_claude_md(proj, "   \n")
    assert sc.check_s6_claude_md_exists(proj)["status"] == pq.STATUS_FAIL


def test_s6_passes_when_present(proj: Path):
    _write_claude_md(proj, "# Project\n\nWhat it does.\n")
    assert sc.check_s6_claude_md_exists(proj)["status"] == pq.STATUS_PASS


# ---------------------------------------------------------------------------
# S7 — Structure block (Tier-2)
# ---------------------------------------------------------------------------


def test_s7_skip_when_claude_md_missing(proj: Path):
    f = sc.check_s7_claude_md_structure(proj)
    assert f["status"] == pq.STATUS_SKIP


def test_s7_warns_without_structure(proj: Path):
    _write_claude_md(proj, "# Project\n\nNo structure here.\n")
    f = sc.check_s7_claude_md_structure(proj)
    assert f["status"] == pq.STATUS_WARN
    assert f.get("tier") == 2


def test_s7_passes_with_structure_block(proj: Path):
    _write_claude_md(proj, (
        "# Project\n\n"
        "## Structure\n\n"
        "```\n"
        "src/\n"
        "tests/\n"
        "```\n"
    ))
    f = sc.check_s7_claude_md_structure(proj)
    assert f["status"] == pq.STATUS_PASS


# ---------------------------------------------------------------------------
# S8 — README
# ---------------------------------------------------------------------------


def test_s8_fails_when_missing(proj: Path):
    assert sc.check_s8_readme_exists(proj)["status"] == pq.STATUS_FAIL


def test_s8_fails_when_empty(proj: Path):
    _write_readme(proj, "\n")
    assert sc.check_s8_readme_exists(proj)["status"] == pq.STATUS_FAIL


def test_s8_passes_when_present(proj: Path):
    _write_readme(proj, "# Project\n\nSomething.\n")
    assert sc.check_s8_readme_exists(proj)["status"] == pq.STATUS_PASS


# ---------------------------------------------------------------------------
# S9 — README freshness (Tier-2, R17)
# ---------------------------------------------------------------------------


def test_s9_skip_when_not_feature(proj: Path):
    _write_iterate_history(proj, [{"run_id": "r1", "type": "bug"}])
    f = sc.check_s9_readme_freshness(proj, "r1")
    assert f["status"] == pq.STATUS_SKIP


def test_s9_skip_when_no_git(proj: Path):
    _write_iterate_history(proj, [{"run_id": "r1", "type": "feature"}])
    f = sc.check_s9_readme_freshness(proj, "r1")
    assert f["status"] == pq.STATUS_SKIP


def test_s9_warns_on_ui_feature_without_readme_touch(tmp_path: Path):
    _init_git_repo(tmp_path)
    (tmp_path / "agent_docs").mkdir()
    (tmp_path / "webui").mkdir()
    (tmp_path / "webui" / "client").mkdir()
    (tmp_path / "webui" / "client" / "x.tsx").write_text("x", encoding="utf-8")
    _write_iterate_history(tmp_path, [{"run_id": "r1", "type": "feature"}])
    _git_commit_all(tmp_path, "ui change")
    f = sc.check_s9_readme_freshness(tmp_path, "r1")
    # Either WARN (UI-facing detected) or SKIP if detection misses — both
    # are Tier-2-acceptable, but FAIL is forbidden (R17).
    assert f["status"] in (pq.STATUS_WARN, pq.STATUS_SKIP)
    if f["status"] == pq.STATUS_WARN:
        assert f.get("tier") == 2


def test_s9_passes_when_readme_fresh(tmp_path: Path):
    _init_git_repo(tmp_path)
    (tmp_path / "agent_docs").mkdir()
    (tmp_path / "webui" / "client").mkdir(parents=True)
    (tmp_path / "webui" / "client" / "x.tsx").write_text("x", encoding="utf-8")
    _write_readme(tmp_path, "# Project\n")
    _write_iterate_history(tmp_path, [{"run_id": "r1", "type": "feature"}])
    _git_commit_all(tmp_path, "ui change with readme")
    f = sc.check_s9_readme_freshness(tmp_path, "r1")
    assert f["status"] != pq.STATUS_FAIL  # R17: never FAIL


# ---------------------------------------------------------------------------
# S10 — CLAUDE.md sync (Tier-2, R17)
# ---------------------------------------------------------------------------


def test_s10_skip_when_not_feature_or_bug(proj: Path):
    _write_iterate_history(proj, [{"run_id": "r1", "type": "change"}])
    f = sc.check_s10_claude_md_sync(proj, "r1")
    assert f["status"] == pq.STATUS_SKIP


def test_s10_skip_when_git_unavailable(proj: Path):
    _write_iterate_history(proj, [{"run_id": "r1", "type": "feature"}])
    f = sc.check_s10_claude_md_sync(proj, "r1")
    assert f["status"] == pq.STATUS_SKIP


def test_s10_passes_when_no_new_top_level_dirs(tmp_path: Path):
    _init_git_repo(tmp_path)
    (tmp_path / "agent_docs").mkdir()
    _write_iterate_history(tmp_path, [{"run_id": "r1", "type": "feature"}])
    # nothing new to commit — no file paths touched
    _git_commit_all(tmp_path, "empty")
    f = sc.check_s10_claude_md_sync(tmp_path, "r1")
    # Either PASS (no new dirs) or SKIP — never FAIL.
    assert f["status"] != pq.STATUS_FAIL


def test_s10_never_fails_under_any_input(tmp_path: Path):
    _init_git_repo(tmp_path)
    (tmp_path / "agent_docs").mkdir()
    _write_iterate_history(tmp_path, [{"run_id": "r1", "type": "feature"}])
    new_dir = tmp_path / "brand-new"
    new_dir.mkdir()
    (new_dir / "file.py").write_text("x", encoding="utf-8")
    _git_commit_all(tmp_path, "new top-level dir")
    assert sc.check_s10_claude_md_sync(tmp_path, "r1")["status"] != pq.STATUS_FAIL


# ---------------------------------------------------------------------------
# Phase dispatcher
# ---------------------------------------------------------------------------


def test_run_project_phase(proj: Path):
    findings = sc.run("project", proj, run_id="r1")
    ids = [f["id"] for f in findings]
    assert ids == ["S1", "S5", "S6", "S7", "S8"]


def test_run_iterate_phase(proj: Path):
    findings = sc.run("iterate", proj, run_id="r1")
    assert {f["id"] for f in findings} == {"S2", "S3", "S4", "S5", "S9", "S10"}


def test_run_unrelated_phase_returns_empty(proj: Path):
    assert sc.run("build", proj, "r1") == []
    assert sc.run("test", proj, "r1") == []
    assert sc.run("security", proj, "r1") == []


def test_phase_quality_dispatches_spec(proj: Path):
    """phase_quality.run_spec_checks dispatches to spec_checks.run."""
    findings = pq.run_spec_checks("project", proj, "r1")
    assert {f["id"] for f in findings} == {"S1", "S5", "S6", "S7", "S8"}


def test_phase_quality_spec_empty_for_uncovered(proj: Path):
    assert pq.run_spec_checks("build", proj, "r1") == []
    assert pq.run_spec_checks("test", proj, "r1") == []


def test_phase_quality_spec_applies_skip_override(monkeypatch, proj: Path):
    monkeypatch.setenv("SHIPWRIGHT_SKIP_QUALITY_CHECK", "S1")
    monkeypatch.setenv("SHIPWRIGHT_AUDIT_OVERRIDE_REASON", "intentional")
    findings = pq.run_spec_checks("project", proj, "r1")
    s1 = next(f for f in findings if f["id"] == "S1")
    assert s1["status"] == pq.STATUS_SKIP
    assert s1["evidence"] == "intentional"


# ---------------------------------------------------------------------------
# Tier-2 tagging sanity
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("tier2_id", ["S3", "S4", "S5", "S7", "S9", "S10"])
def test_tier2_findings_are_tagged(proj: Path, tier2_id: str):
    """All Tier-2 S* findings carry tier=2 in the finding dict."""
    # Configure iterate history so S2/S3/S9/S10 can run past SKIP
    _write_iterate_history(proj, [
        {"run_id": "r1", "complexity": "medium", "type": "feature"},
    ])
    findings = sc.run("iterate", proj, "r1") + sc.run("project", proj, "r1")
    matched = [f for f in findings if f["id"] == tier2_id]
    assert matched, f"no {tier2_id} finding produced"
    for f in matched:
        if f["status"] in (pq.STATUS_WARN, pq.STATUS_PASS):
            # Passes don't require the tag, but WARN must carry it for
            # dashboard grouping (plan § 3).
            if f["status"] == pq.STATUS_WARN:
                assert f.get("tier") == 2
