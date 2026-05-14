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
