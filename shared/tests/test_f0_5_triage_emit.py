"""AC-4 producer test: F0.5 fail-closed exits land in triage.jsonl.

Unit-tests the `_emit_failure_to_triage` helper in
``shared/scripts/surface_verification.py``. The helper accepts the
mapped condition string + surface + run_id and emits exactly one triage
item with severity="critical", kind="bug".

Scope: only the 3 runtime fail-closed conditions emitted by
`surface_verification.py` itself. The "missing_block" condition is
detected post-commit in `iterate_checks.py` and is out of scope for
this iterate (see iterate ADR + spec AC-4).
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_WORKTREE = Path(__file__).resolve().parents[2]
_SHARED_SCRIPTS = _WORKTREE / "shared" / "scripts"
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))

_SV_PATH = _SHARED_SCRIPTS / "surface_verification.py"
_spec = importlib.util.spec_from_file_location(
    "surface_verification_for_test", _SV_PATH,
)
assert _spec is not None and _spec.loader is not None
sv = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sv)

from triage import read_all_items  # noqa: E402


@pytest.fixture
def project(tmp_path: Path) -> Path:
    return tmp_path


# --- Each condition emits exactly one item -------------------------------

def test_tests_zero_emits_critical_bug(project: Path) -> None:
    item_id = sv._emit_failure_to_triage(
        project,
        run_id="iterate-2026-05-14-foo",
        surface="web",
        condition="tests_zero",
        detail="Playwright matched zero specs — greedy filter trap",
        evidence_path=".shipwright/runs/iterate-2026-05-14-foo/surface_verification.log",
    )
    assert item_id is not None
    [item] = read_all_items(project)
    assert item["source"] == "f0.5"
    assert item["severity"] == "critical"
    assert item["kind"] == "bug"
    assert item["suggestedPriority"] == "P0"
    assert item["suggestedDomain"] == "engineering"
    assert item["status"] == "triage"


def test_exit_nonzero_emits(project: Path) -> None:
    sv._emit_failure_to_triage(
        project, run_id="r1", surface="cli",
        condition="exit_nonzero", detail="pytest exit 1 after 3 retries",
        evidence_path=None,
    )
    [item] = read_all_items(project)
    assert item["source"] == "f0.5"
    assert "exit_nonzero" in item["dedupKey"]


def test_surface_none_no_just_emits(project: Path) -> None:
    sv._emit_failure_to_triage(
        project, run_id="r1", surface="none",
        condition="surface_none_no_just",
        detail="surface=none requires justification",
        evidence_path=None,
    )
    [item] = read_all_items(project)
    assert "surface_none_no_just" in item["dedupKey"]


# --- Dedup key shape -----------------------------------------------------

def test_dedup_key_includes_run_surface_condition(project: Path) -> None:
    sv._emit_failure_to_triage(
        project, run_id="iterate-2026-05-14-foo",
        surface="web", condition="tests_zero",
        detail="...", evidence_path=None,
    )
    [item] = read_all_items(project)
    assert item["dedupKey"] == "f0.5:iterate-2026-05-14-foo:web:tests_zero"


# --- Dedup behavior ------------------------------------------------------

def test_same_run_same_condition_dedups(project: Path) -> None:
    sv._emit_failure_to_triage(
        project, run_id="r1", surface="cli",
        condition="tests_zero", detail="d1", evidence_path=None,
    )
    second = sv._emit_failure_to_triage(
        project, run_id="r1", surface="cli",
        condition="tests_zero", detail="d2", evidence_path=None,
    )
    assert second is None
    assert len(read_all_items(project)) == 1


def test_different_run_id_creates_distinct_item(project: Path) -> None:
    sv._emit_failure_to_triage(
        project, run_id="r1", surface="cli",
        condition="tests_zero", detail="d", evidence_path=None,
    )
    sv._emit_failure_to_triage(
        project, run_id="r2", surface="cli",
        condition="tests_zero", detail="d", evidence_path=None,
    )
    keys = {it["dedupKey"] for it in read_all_items(project)}
    assert len(keys) == 2


def test_different_surface_creates_distinct_item(project: Path) -> None:
    sv._emit_failure_to_triage(
        project, run_id="r1", surface="cli",
        condition="exit_nonzero", detail="d", evidence_path=None,
    )
    sv._emit_failure_to_triage(
        project, run_id="r1", surface="web",
        condition="exit_nonzero", detail="d", evidence_path=None,
    )
    keys = {it["dedupKey"] for it in read_all_items(project)}
    assert len(keys) == 2


# --- Evidence path -------------------------------------------------------

def test_evidence_path_recorded_when_given(project: Path) -> None:
    log = project / ".shipwright" / "runs" / "r1" / "surface_verification.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text("attempt log", encoding="utf-8")
    sv._emit_failure_to_triage(
        project, run_id="r1", surface="cli",
        condition="exit_nonzero", detail="d",
        evidence_path=str(log),
    )
    [item] = read_all_items(project)
    assert item["evidencePath"] is not None
    assert "surface_verification.log" in item["evidencePath"]


def test_evidence_path_none_is_accepted(project: Path) -> None:
    sv._emit_failure_to_triage(
        project, run_id="r1", surface="api",
        condition="exit_nonzero", detail="d",
        evidence_path=None,
    )
    [item] = read_all_items(project)
    assert item["evidencePath"] is None


# --- Bug 2: resolve pass auto-dismisses cleared F0.5 items ---------------

def test_f05_dedup_key_shape(project: Path) -> None:
    """The dedup-key helper produces the exact wire shape the producer
    emits — one definition guards producer/resolver drift."""
    assert sv._f05_dedup_key("r1", "web", "tests_zero") == "f0.5:r1:web:tests_zero"
    sv._emit_failure_to_triage(
        project, run_id="r1", surface="web",
        condition="tests_zero", detail="d", evidence_path=None,
    )
    [item] = read_all_items(project)
    assert item["dedupKey"] == sv._f05_dedup_key("r1", "web", "tests_zero")


def test_resolve_dismisses_item_when_condition_clears(project: Path) -> None:
    """Bug 2: an F0.5 item whose condition cleared on a green re-run of the
    same run_id flips to dismissed with reason=f05Resolved.

    Mirrors the observed bug: a P0 item from a runner that failed with
    exit 127 was never retracted when the SAME run re-ran green.
    """
    sv._emit_failure_to_triage(
        project, run_id="r1", surface="web",
        condition="exit_nonzero", detail="exit 127", evidence_path=None,
    )
    [item] = read_all_items(project)
    assert item["status"] == "triage"

    # Re-run of r1 passed — empty finding set.
    dismissed = sv._resolve_stale_f05_items(
        project, run_id="r1", surface="web", current_keys=set(),
    )
    assert dismissed == 1
    [item] = read_all_items(project)
    assert item["status"] == "dismissed"
    assert item["statusReason"] == "f05Resolved"
    assert item["statusBy"] == "f05Detector"


def test_resolve_keeps_item_when_condition_persists(project: Path) -> None:
    """An F0.5 item whose condition is still in the current finding set
    stays open."""
    sv._emit_failure_to_triage(
        project, run_id="r1", surface="web",
        condition="tests_zero", detail="d", evidence_path=None,
    )
    key = sv._f05_dedup_key("r1", "web", "tests_zero")
    dismissed = sv._resolve_stale_f05_items(
        project, run_id="r1", surface="web", current_keys={key},
    )
    assert dismissed == 0
    [item] = read_all_items(project)
    assert item["status"] == "triage"


def test_resolve_scoped_to_run_id(project: Path) -> None:
    """Resolving run r2 must NOT dismiss an open item from run r1 — a
    later iterate's pass says nothing about an earlier iterate's failure.
    """
    sv._emit_failure_to_triage(
        project, run_id="r1", surface="cli",
        condition="exit_nonzero", detail="d", evidence_path=None,
    )
    dismissed = sv._resolve_stale_f05_items(
        project, run_id="r2", surface="cli", current_keys=set(),
    )
    assert dismissed == 0
    [item] = read_all_items(project)
    assert item["status"] == "triage"


def test_resolve_scoped_to_surface(project: Path) -> None:
    """A re-run of the same run_id on a DIFFERENT surface must NOT dismiss
    a genuine still-open failure from the original surface."""
    sv._emit_failure_to_triage(
        project, run_id="r1", surface="web",
        condition="exit_nonzero", detail="web broke", evidence_path=None,
    )
    dismissed = sv._resolve_stale_f05_items(
        project, run_id="r1", surface="cli", current_keys=set(),
    )
    assert dismissed == 0
    [item] = read_all_items(project)
    assert item["status"] == "triage"
    assert item["dedupKey"] == sv._f05_dedup_key("r1", "web", "exit_nonzero")


def test_resolve_dismisses_old_condition_keeps_new(project: Path) -> None:
    """Same run_id re-fails on a different condition: the old item is
    retracted, the new one stays open."""
    sv._emit_failure_to_triage(
        project, run_id="r1", surface="web",
        condition="tests_zero", detail="d", evidence_path=None,
    )
    sv._emit_failure_to_triage(
        project, run_id="r1", surface="web",
        condition="exit_nonzero", detail="d", evidence_path=None,
    )
    new_key = sv._f05_dedup_key("r1", "web", "exit_nonzero")
    dismissed = sv._resolve_stale_f05_items(
        project, run_id="r1", surface="web", current_keys={new_key},
    )
    assert dismissed == 1
    by_key = {it["dedupKey"]: it for it in read_all_items(project)}
    old_key = sv._f05_dedup_key("r1", "web", "tests_zero")
    assert by_key[old_key]["status"] == "dismissed"
    assert by_key[new_key]["status"] == "triage"


def test_resolve_leaves_terminal_items(project: Path) -> None:
    """Operator-promoted F0.5 items stay terminal — resolve only touches
    status=='triage' items."""
    from triage import mark_status

    sv._emit_failure_to_triage(
        project, run_id="r1", surface="cli",
        condition="tests_zero", detail="d", evidence_path=None,
    )
    [item] = read_all_items(project)
    mark_status(project, item["id"], new_status="promoted", by="operator",
                promoted_task_id="EXT:1")
    dismissed = sv._resolve_stale_f05_items(
        project, run_id="r1", surface="cli", current_keys=set(),
    )
    assert dismissed == 0
    [item] = read_all_items(project)
    assert item["status"] == "promoted"


def test_resolve_no_items_no_op(project: Path) -> None:
    """Resolve pass on an empty/missing triage store is a clean no-op."""
    assert sv._resolve_stale_f05_items(
        project, run_id="r1", surface="web", current_keys=set(),
    ) == 0
    assert read_all_items(project) == []
