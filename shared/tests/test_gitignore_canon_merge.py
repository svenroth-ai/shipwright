"""Tests for the canonical ``.shipwright/`` gitignore merge writer.

Covers the parse/merge logic AND empirical ``git check-ignore`` round-trips
that prove the merged rules actually do the right thing in a real repo —
this is the "fixed when empirically cleanly tested" bar for the propagation
gap (framework-added ``.shipwright/`` ignore rules never reached consuming
projects). The webui-regression probe (missing ``runtime/``) is the exact
case the manual webui patch f6e34a6 fixed.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

# conftest.py adds shared/scripts to sys.path; lib is a package under it.
from lib.gitignore_canon import (
    BEGIN_MARKER,
    END_MARKER,
    extract_marked_rules,
    merge_canonical_block,
    read_canonical_rules,
)

TEMPLATE = (
    Path(__file__).resolve().parents[1]
    / "templates"
    / "shipwright-gitignore.template"
)


def _git(*args: str, cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )


def _require_git() -> None:
    if shutil.which("git") is None:
        if os.environ.get("CI", "").lower() in ("true", "1"):
            pytest.fail(
                "git binary not found in CI — install git "
                "(the gitignore round-trip probes require it)"
            )
        pytest.skip("git binary not available")


def _init_repo(tmp_path: Path) -> Path:
    _require_git()
    _git("init", cwd=tmp_path)
    return tmp_path


# --------------------------------------------------------------------------
# Parsing
# --------------------------------------------------------------------------

def test_read_canonical_rules_includes_runtime() -> None:
    rules = read_canonical_rules(TEMPLATE)
    assert "/.shipwright/agent_docs/runtime/" in rules
    assert "/.shipwright/*" in rules
    assert "!/.shipwright/agent_docs/" in rules
    # No comments or blanks leaked in.
    assert all(r and not r.startswith("#") for r in rules)


def test_read_canonical_rules_orders_broad_before_negation() -> None:
    rules = read_canonical_rules(TEMPLATE)
    # The broad ignore must precede the re-include negations and re-excludes,
    # otherwise the whitelist semantics break.
    assert rules.index("/.shipwright/*") < rules.index("!/.shipwright/agent_docs/")
    assert rules.index("!/.shipwright/agent_docs/") < rules.index(
        "/.shipwright/agent_docs/runtime/"
    )


def test_extract_marked_rules_absent_markers_returns_empty() -> None:
    assert extract_marked_rules("# just a comment\n.env\nnode_modules/\n") == []


def test_read_canonical_rules_raises_on_markerless_template(tmp_path: Path) -> None:
    bad = tmp_path / "bad.template"
    bad.write_text("# no markers here\n/.shipwright/runs/\n", encoding="utf-8")
    with pytest.raises(ValueError, match="no canonical artifact-ignore rules"):
        read_canonical_rules(bad)


# --------------------------------------------------------------------------
# Merge — structural behavior
# --------------------------------------------------------------------------

def test_merge_creates_gitignore_when_absent(tmp_path: Path) -> None:
    result = merge_canonical_block(tmp_path, template_path=TEMPLATE)
    gi = tmp_path / ".gitignore"
    assert result["action"] == "created"
    assert gi.exists()
    text = gi.read_text(encoding="utf-8")
    assert BEGIN_MARKER in text and END_MARKER in text
    for rule in read_canonical_rules(TEMPLATE):
        assert rule in text
    assert result["added"] == read_canonical_rules(TEMPLATE)


def test_merge_is_idempotent(tmp_path: Path) -> None:
    merge_canonical_block(tmp_path, template_path=TEMPLATE)
    before = (tmp_path / ".gitignore").read_text(encoding="utf-8")
    result = merge_canonical_block(tmp_path, template_path=TEMPLATE)
    after = (tmp_path / ".gitignore").read_text(encoding="utf-8")
    assert result["action"] == "unchanged"
    assert result["added"] == []
    assert before == after  # byte-for-byte stable on re-run


def test_merge_preserves_existing_user_content(tmp_path: Path) -> None:
    gi = tmp_path / ".gitignore"
    user_content = "# my project\nnode_modules/\n.env.local\ndist/\n"
    gi.write_text(user_content, encoding="utf-8")
    merge_canonical_block(tmp_path, template_path=TEMPLATE)
    text = gi.read_text(encoding="utf-8")
    # User lines remain, untouched and in place.
    assert text.startswith(user_content)
    assert "node_modules/" in text and ".env.local" in text


def test_merge_backfills_only_missing_rule_webui_regression(tmp_path: Path) -> None:
    """The webui case: whitelist present but ``runtime/`` missing.

    Only the one missing rule is added; nothing pre-existing is duplicated.
    """
    canonical = read_canonical_rules(TEMPLATE)
    runtime_rule = "/.shipwright/agent_docs/runtime/"
    pre_existing = [r for r in canonical if r != runtime_rule]
    gi = tmp_path / ".gitignore"
    gi.write_text("\n".join(pre_existing) + "\n", encoding="utf-8")

    result = merge_canonical_block(tmp_path, template_path=TEMPLATE)
    text = gi.read_text(encoding="utf-8")

    assert result["action"] == "updated"
    assert result["added"] == [runtime_rule]
    # No rule appears more than once.
    for rule in canonical:
        occurrences = [ln.strip() for ln in text.splitlines()].count(rule)
        assert occurrences == 1, f"rule duplicated or missing: {rule!r} ({occurrences}x)"


def test_merge_no_duplicates_when_rules_present_unmarked(tmp_path: Path) -> None:
    """A project with the canonical rules but no managed-block markers.

    Re-running must NOT append a duplicate block.
    """
    canonical = read_canonical_rules(TEMPLATE)
    gi = tmp_path / ".gitignore"
    gi.write_text("\n".join(canonical) + "\n", encoding="utf-8")
    result = merge_canonical_block(tmp_path, template_path=TEMPLATE)
    assert result["action"] == "unchanged"
    assert BEGIN_MARKER not in gi.read_text(encoding="utf-8")


# --------------------------------------------------------------------------
# Empirical — git check-ignore round-trips (the real proof)
# --------------------------------------------------------------------------

def _check_ignored(repo: Path, rel: str) -> bool:
    """True if *rel* is ignored by the repo's .gitignore (exit 0)."""
    proc = _git("check-ignore", rel, cwd=repo)
    # 0 = ignored, 1 = not ignored, >1 = error
    assert proc.returncode in (0, 1), (
        f"check-ignore error rc={proc.returncode} stderr={proc.stderr!r}"
    )
    return proc.returncode == 0


def test_empirical_round_trip_fresh_repo(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    merge_canonical_block(repo, template_path=TEMPLATE)

    # Materialize the files so check-ignore is unambiguous.
    (repo / ".shipwright" / "agent_docs" / "runtime").mkdir(parents=True)
    (repo / ".shipwright" / "agent_docs" / "runtime" / "session_handoff.md").write_text("x")
    (repo / ".shipwright" / "agent_docs" / "architecture.md").write_text("x")
    (repo / ".shipwright" / "agent_docs" / "decision-drops").mkdir()
    (repo / ".shipwright" / "agent_docs" / "decision-drops" / "d.json").write_text("{}")
    (repo / ".shipwright" / "planning" / "iterate").mkdir(parents=True)
    (repo / ".shipwright" / "planning" / "iterate" / "x.md").write_text("x")

    # Transient / runtime artifacts ARE ignored.
    assert _check_ignored(repo, ".shipwright/agent_docs/runtime/session_handoff.md")
    assert _check_ignored(repo, ".shipwright/agent_docs/decision-drops/d.json")
    # Canonical SDLC docs are TRACKED (not ignored).
    assert not _check_ignored(repo, ".shipwright/agent_docs/architecture.md")
    assert not _check_ignored(repo, ".shipwright/planning/iterate/x.md")


def test_empirical_webui_regression_runtime_becomes_ignored(tmp_path: Path) -> None:
    """Before the fix runtime files showed as untracked clutter; after a
    back-fill merge they are ignored. Mirrors webui commit f6e34a6."""
    repo = _init_repo(tmp_path)
    canonical = read_canonical_rules(TEMPLATE)
    runtime_rule = "/.shipwright/agent_docs/runtime/"
    pre_existing = [r for r in canonical if r != runtime_rule]
    (repo / ".gitignore").write_text("\n".join(pre_existing) + "\n", encoding="utf-8")

    (repo / ".shipwright" / "agent_docs" / "runtime").mkdir(parents=True)
    probe = ".shipwright/agent_docs/runtime/session_handoff.md"
    (repo / ".shipwright" / "agent_docs" / "runtime" / "session_handoff.md").write_text("x")

    # Pre-merge: runtime file is NOT ignored (the bug).
    assert not _check_ignored(repo, probe)
    merge_canonical_block(repo, template_path=TEMPLATE)
    # Post-merge: runtime file IS ignored (the fix).
    assert _check_ignored(repo, probe)


# --------------------------------------------------------------------------
# Iterate-scoped external-review markers — transient, must NOT be tracked,
# while the durable plan-split markers (RTM evidence) MUST stay tracked.
# (iterate-2026-06-09-external-review-marker-gitignore.) The danger is a
# blanket ``**/external_*review_state.json`` near-miss that would also erase
# the plan-split RTM evidence; these probes pin both directions.
# --------------------------------------------------------------------------

_ITERATE_MARKER_REEXCLUDES = (
    "/.shipwright/planning/iterate/**/external_review_state.json",
    "/.shipwright/planning/iterate/**/external_code_review_state.json",
)


def test_read_canonical_rules_includes_iterate_external_marker_reexcludes() -> None:
    rules = read_canonical_rules(TEMPLATE)
    for rule in _ITERATE_MARKER_REEXCLUDES:
        assert rule in rules, f"canon missing iterate-marker re-exclude: {rule!r}"
    # The re-excludes must come AFTER the planning re-include, else the
    # whitelist semantics can't re-exclude inside the re-included dir.
    planning_idx = rules.index("!/.shipwright/planning/")
    for rule in _ITERATE_MARKER_REEXCLUDES:
        assert rules.index(rule) > planning_idx


def test_empirical_iterate_markers_ignored_plan_split_tracked(tmp_path: Path) -> None:
    """The near-miss guard, proven with real ``git check-ignore``.

    Iterate-scoped external-review markers (top-level AND deep campaign /
    sub-iterate copies) are run-scoped transient state and MUST be ignored.
    The plan-split markers under ``.shipwright/planning/<split>/`` are durable
    RTM evidence (``rtm.collect_external_review_states`` reads them; it skips
    ``.shipwright/planning/iterate/``) and MUST stay tracked. A non-iterate ``.md``
    must also stay tracked — the re-excludes target only the two state files.
    """
    repo = _init_repo(tmp_path)
    merge_canonical_block(repo, template_path=TEMPLATE)

    iterate = repo / ".shipwright" / "planning" / "iterate"
    deep = iterate / "campaigns" / "2026-05-25-demo" / "sub-iterates"
    split = repo / ".shipwright" / "planning" / "01-auth"
    deep.mkdir(parents=True)
    split.mkdir(parents=True)
    for d in (iterate, deep, split):
        (d / "external_review_state.json").write_text("{}")
        (d / "external_code_review_state.json").write_text("{}")
    (iterate / "2026-06-09-demo.md").write_text("# spec")

    # Transient iterate markers — top-level copies are ignored.
    assert _check_ignored(repo, ".shipwright/planning/iterate/external_review_state.json")
    assert _check_ignored(
        repo, ".shipwright/planning/iterate/external_code_review_state.json"
    )
    # ...and the deep campaign / sub-iterate copies are ignored too (`**/`).
    deep_rel = ".shipwright/planning/iterate/campaigns/2026-05-25-demo/sub-iterates"
    assert _check_ignored(repo, f"{deep_rel}/external_review_state.json")
    assert _check_ignored(repo, f"{deep_rel}/external_code_review_state.json")
    # Durable plan-split RTM evidence stays TRACKED (not ignored).
    assert not _check_ignored(
        repo, ".shipwright/planning/01-auth/external_review_state.json"
    )
    assert not _check_ignored(
        repo, ".shipwright/planning/01-auth/external_code_review_state.json"
    )
    # The re-excludes must not over-match: an iterate plan .md stays tracked.
    assert not _check_ignored(repo, ".shipwright/planning/iterate/2026-06-09-demo.md")
