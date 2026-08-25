"""``scripts/run_full_suite_evidence.py`` — validate-before-destroy ordering (Stage-3 review).

Split out of ``test_run_full_suite_evidence.py`` (300-LOC guideline) rather than grown
there — same convention as ``test_run_full_suite_evidence_head_commit.py``.

Pins the fix for a real bug: ``main()`` used to call ``clear_evidence_reports`` BEFORE
loading ``discover_test_roots`` from the target's own ``conftest.py``, so a missing or
broken conftest (e.g. a wrong ``--project-root``) destroyed the PREVIOUS valid evidence
and then crashed — fail-closed (never false-green), but needlessly irreversible. Root
discovery now runs first, so a crash there leaves prior evidence intact.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
_SUBJECT = REPO_ROOT / "scripts" / "run_full_suite_evidence.py"


def _load_subject(name: str = "_full_suite_evidence_ordering_probe"):
    spec = importlib.util.spec_from_file_location(name, _SUBJECT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module  # ADR-045: register BEFORE exec
    spec.loader.exec_module(module)
    return module


rfse = _load_subject()


class _FakeProc:
    def __init__(self, returncode: int) -> None:
        self.returncode = returncode


def test_main_does_not_destroy_prior_evidence_when_conftest_is_broken(tmp_path, monkeypatch):
    # Validate BEFORE destroy. A missing/broken conftest (e.g. a wrong --project-root)
    # must fail loud WITHOUT taking the previous run's still-valid evidence down with
    # it -- fail-closed either way, but a crash-after-clear is needlessly irreversible
    # when the crash can happen before the clear instead.
    # No conftest.py written at all -> _load_discover_test_roots raises.
    evidence_dir = tmp_path / ".shipwright" / "compliance" / "evidence"
    evidence_dir.mkdir(parents=True)
    survivor = evidence_dir / "junit.xml"
    survivor.write_text("PRIOR-RUN-STILL-VALID", encoding="utf-8")
    monkeypatch.setattr(rfse.subprocess, "run", lambda *a, **k: _FakeProc(0))
    with pytest.raises((AttributeError, FileNotFoundError)):
        rfse.main([
            "--project-root", str(tmp_path), "--run-id", "iterate-x", "--skip-sync",
            "--head-commit", "deadbeef",
        ])
    assert survivor.is_file()
    assert survivor.read_text(encoding="utf-8") == "PRIOR-RUN-STILL-VALID"
