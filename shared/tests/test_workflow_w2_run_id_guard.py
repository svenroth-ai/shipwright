"""W2 run_id-resolution guard — symmetry with the S2/S3 guard.

When the resolved run_id is a sentinel (``""`` / ``"unknown"`` — emitted by
the phase-quality Stop audit when no iterate run resolves) AND no per-run
external-review marker is on disk, W2 must SKIP — the same way
``check_s2_iterate_spec`` does (see test_spec_checks_run_id_guard.py).

The bug this pins: in an audit context the W2 check ran with run_id=unknown
and either false-FAILed (no marker in a fresh worktree — the worktree case)
or false-PASSed on the run-agnostic ``external_review_state.json`` (the
main-tree case). Both are wrong: an unresolvable run is "not applicable in
this audit context", i.e. SKIP. A real run (exact iterate_history entry) or
a per-run marker on disk bypasses the guard and runs the normal logic.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

_SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from lib import phase_quality as pq  # noqa: E402
from tools.verifiers import iterate_compliance  # noqa: E402


@pytest.fixture
def proj(tmp_path: Path) -> Path:
    (tmp_path / ".shipwright" / "agent_docs").mkdir(parents=True, exist_ok=True)
    return tmp_path


def _write_run_config(proj: Path, **overrides: Any) -> None:
    data: dict[str, Any] = {
        "iterate_history": [{"run_id": "run-1", "complexity": "medium"}],
    }
    data.update(overrides)
    (proj / "shipwright_run_config.json").write_text(
        json.dumps(data), encoding="utf-8",
    )


def _iter_dir(proj: Path) -> Path:
    d = proj / ".shipwright" / "planning" / "iterate"
    d.mkdir(parents=True, exist_ok=True)
    return d


def test_w2_skips_on_unknown_run_id_no_marker(proj: Path) -> None:
    # AC-1: the run_id=unknown bug. With the iterate dir present (so the
    # missing-dir SKIP can't mask it), tail-fallback to the latest entry's
    # complexity previously produced an unsatisfiable FAIL. Now it SKIPs.
    _write_run_config(proj)  # history = [{run-1, medium}]; run_id != run-1
    _iter_dir(proj)
    f = iterate_compliance.check_w2_external_review_marker(proj, "unknown")
    assert f["status"] == pq.STATUS_SKIP
    assert "not a resolvable iterate run" in f["evidence"]


def test_w2_skips_on_unknown_run_id_even_with_completed_state(proj: Path) -> None:
    # AC-2: external_review_state.json is run-agnostic and must NOT keep an
    # unresolvable audit "live" (it previously false-PASSed in the main tree).
    _write_run_config(proj)
    (_iter_dir(proj) / "external_review_state.json").write_text(
        json.dumps({"status": "completed", "provider": "openrouter"}),
        encoding="utf-8",
    )
    f = iterate_compliance.check_w2_external_review_marker(proj, "unknown")
    assert f["status"] == pq.STATUS_SKIP


def test_w2_skips_on_empty_run_id(proj: Path) -> None:
    # An empty run_id also crashed the spec-glob (``**.md`` is an invalid
    # pathlib pattern); the guard runs first and SKIPs before reaching it.
    _write_run_config(proj)
    _iter_dir(proj)
    f = iterate_compliance.check_w2_external_review_marker(proj, "")
    assert f["status"] == pq.STATUS_SKIP


def test_w2_per_run_marker_overrides_guard_without_exact_entry(proj: Path) -> None:
    # AC-6 parity with S2: a per-run marker on disk bypasses the guard even
    # when run_id has no exact iterate_history entry → normal logic PASSes.
    _write_run_config(
        proj, iterate_history=[{"run_id": "other", "complexity": "medium"}])
    (_iter_dir(proj) / "myrun-external-review.json").write_text(
        "{}", encoding="utf-8")
    f = iterate_compliance.check_w2_external_review_marker(proj, "myrun")
    assert f["status"] == pq.STATUS_PASS
    assert f["provenance"] == "unverified_marker"


def test_w2_guard_does_not_fire_for_real_run_with_exact_entry(proj: Path) -> None:
    # Regression: a real run with an exact entry but no marker must still
    # FAIL — the guard must not mask a genuine missing external review.
    _write_run_config(proj)  # run-1 IS in history
    _iter_dir(proj)
    f = iterate_compliance.check_w2_external_review_marker(proj, "run-1")
    assert f["status"] == pq.STATUS_FAIL
    assert "not a resolvable" not in f["evidence"]
