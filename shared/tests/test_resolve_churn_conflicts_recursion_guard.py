"""AC-5 — integration coverage for the ``dedup_event_lines`` RecursionError fix
(card trg-57d0d6d3 / P2.19g, TEIL 2; found by the internal Opus plan review).

``cross_component`` fires for this run because the fix touches
``churn_merge.py`` (see the iterate spec's re-measurement table), so a
``category:"integration"`` behavior proving the fix composes with its REAL
caller — not just the pure unit-level ``dedup_event_lines`` — is owed. This
drives ``resolve_churn_conflicts._reconcile_events`` directly against a real
file on disk, mirroring the "direct integration test" the spec names as
equivalent to a full git-merge-conflict scaffold for a fix this narrow.

Split into its own module (rather than added to ``test_resolve_churn_conflicts.py``,
already at the 300-LOC guideline) for the same reason as
``test_churn_merge_recursion_guard.py``.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))

from lib.churn_merge import (  # noqa: E402
    EVENTS_LOG,
    TRIAGE_LOG,
    validate_events_text,
    validate_triage_text,
)
from tools import resolve_churn_conflicts as rcc  # noqa: E402


def _deep_event_line(iid: str) -> str:
    nested = '{"a":' * 20000 + "1" + "}" * 20000
    return f'{{"id":"{iid}","type":"note","val":{nested}}}'


def _init_repo(root: Path) -> None:
    """_reconcile_events stages its rewrite with a real ``git add`` — a bare
    tmp_path is not a repo, so give it one, matching the fixture shape
    test_resolve_churn_conflicts.py's own git-integration tests use."""
    subprocess.run(["git", "init", "-b", "main"], cwd=root, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "churn@test.invalid"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.name", "Churn Test"], cwd=root, check=True)


def test_reconcile_events_survives_a_deeply_nested_line(tmp_path: Path) -> None:
    """AC-5(a)+(b). Pre-fix, this raised ``RecursionError`` out of
    ``dedup_event_lines`` via its real caller ``_reconcile_events``. Post-fix,
    it completes, and the pathological line survives byte-identical in the
    rewritten file — ``dedup_event_lines``'s "never drops a distinct line"
    contract, composed with the real disk-write path."""
    _init_repo(tmp_path)
    deep = _deep_event_line("trg-evtdeep")
    normal = '{"id":"trg-evtnormal","type":"note"}'
    log = tmp_path / EVENTS_LOG
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text(normal + "\n" + deep + "\n" + normal + "\n", encoding="utf-8")
    resolved: list[str] = []

    errors, warnings = rcc._reconcile_events(tmp_path, None, resolved)

    assert EVENTS_LOG in resolved, "the rewrite branch never ran"
    survived = log.read_text(encoding="utf-8")
    assert deep in survived, "the deeply-nested line was dropped or mutated"
    assert survived.count(normal) == 1, "the duplicate normal line was not deduped"
    assert "trg-evtdeep" not in "".join(warnings)
    # _reconcile_events validates its own rewrite, so the deep line's fragment
    # report already surfaces here — the same path AC-5(c) confirms directly.
    assert any("unrecoverable fragment" in e for e in errors), errors


def test_reconcile_events_deep_line_reported_as_unrecoverable_fragment(tmp_path: Path) -> None:
    """AC-5(c). ``validate_events_text`` run against the reconciled result
    reports the deeply-nested line via the SAME "not valid JSON (unrecoverable
    fragment)" path an ordinary corrupt line already takes — verified directly
    (this is the build-time probe external review round 2b asked for) rather
    than assumed."""
    deep = _deep_event_line("trg-evtfragment")
    log = tmp_path / EVENTS_LOG
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text(deep + "\n", encoding="utf-8")

    rcc._reconcile_events(tmp_path, None, [])
    errors = validate_events_text(log.read_text(encoding="utf-8"))

    assert any("not valid JSON (unrecoverable fragment)" in e for e in errors), errors


def test_reconcile_triage_survives_a_deeply_nested_line(tmp_path: Path) -> None:
    """Doubt-reviewer finding 3 (Stage 3): AC-5 covered ``_reconcile_events``
    only, leaving the OTHER real caller of a fixed function —
    ``_reconcile_triage`` (calls ``dedup_triage_lines``) — with no integration
    coverage, even though it is the same 'fix at the parse boundary protects
    every caller' claim the spec makes for ``cross_component``. Composed
    concern this pins: ``_reconcile_triage`` writes and ``git add``s its
    rewrite BEFORE validating, so a real regression here would leave a
    modified+staged log inside a half-resolved merge — not just fail an
    assertion."""
    _init_repo(tmp_path)
    deep = _deep_event_line("trg-triagedeep")
    normal = '{"id":"trg-triagenormal","type":"note"}'
    log = tmp_path / TRIAGE_LOG
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text(normal + "\n" + deep + "\n" + normal + "\n", encoding="utf-8")
    resolved: list[str] = []

    errors, warnings = rcc._reconcile_triage(tmp_path, resolved)

    assert TRIAGE_LOG in resolved, "the rewrite branch never ran"
    survived = log.read_text(encoding="utf-8")
    assert deep in survived, "the deeply-nested line was dropped or mutated"
    assert survived.count(normal) == 1, "the duplicate normal line was not deduped"
    assert "trg-triagedeep" not in "".join(warnings)
    assert any("unrecoverable fragment" in e for e in errors), errors
    # The doubt-reviewer's specific worry: the log was rewritten before
    # validation, so confirm the on-disk rewrite is what got staged, not a
    # crash mid-write that would leave a stale git index pointing at nothing.
    staged = subprocess.run(
        ["git", "-C", str(tmp_path), "diff", "--cached", "--name-only"],
        capture_output=True, text=True, check=True,
    ).stdout
    assert TRIAGE_LOG in staged, "the rewrite was never staged"


def test_reconcile_triage_deep_line_reported_as_unrecoverable_fragment(tmp_path: Path) -> None:
    """Sibling of the events-side AC-5(c) probe, for the third caller."""
    deep = _deep_event_line("trg-triagefragment")
    log = tmp_path / TRIAGE_LOG
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text(deep + "\n", encoding="utf-8")

    rcc._reconcile_triage(tmp_path, [])
    errors = validate_triage_text(log.read_text(encoding="utf-8"))

    assert any("not valid JSON (unrecoverable fragment)" in e for e in errors), errors
