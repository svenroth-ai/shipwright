"""Step E.18 end-to-end, through the real CLI (FR-01.13, trg-1aa5a8ab).

Run as a SUBPROCESS, not by import. The tool's ADR-045 property — that the only
``lib`` package binding in its interpreter is the shared one, so the lazily
imported ``triage`` can reach ``lib.file_lock`` — is a property of a *process*,
and importing the module into this test session would not exercise it. The two
plugin modules it imports bare would also shadow the ``lib`` package this file
already binds. Both reasons point the same way.

`slow` because each case spawns an interpreter and writes a real triage store.

@FR-01.13
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.slow

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT = (REPO_ROOT / "plugins" / "shipwright-adopt" / "scripts" / "tools"
          / "record_inherited_baseline.py")

CATALOGUE = {
    "schema_version": 1,
    "generated_by": "shipwright-adopt",
    "split_name": "01-adopted",
    "total": 3, "confirmed": 0, "unconfirmed": 3,
    "by_basis": {"code": 3},
    "requirements": [
        {"fr_id": "FR-01.01", "name": "Sign in", "basis": "code", "confirmed": False},
        {"fr_id": "FR-01.02", "name": "Dashboard", "basis": "code", "confirmed": False},
        {"fr_id": "FR-01.03", "name": "Export", "basis": "code", "confirmed": False},
    ],
}


def _catalogue_of(n: int) -> dict:
    """A catalogue whose stated counts agree with its entries.

    Needed because the reader REJECTS a document that contradicts itself — so a
    fixture cannot just slice `requirements` and leave the old totals in place.
    (That guard caught this very fixture while it was being written.)
    """
    rows = CATALOGUE["requirements"][:n]
    return {**CATALOGUE, "requirements": rows,
            "total": len(rows), "confirmed": 0, "unconfirmed": len(rows)}


def _seed(root: Path, *, catalogue: dict | None = CATALOGUE,
          backfill: dict | None = None, skips: list | None = None) -> None:
    (root / ".shipwright" / "adopt").mkdir(parents=True, exist_ok=True)
    if catalogue is not None:
        (root / ".shipwright" / "adopt" / "derived-catalogue.json").write_text(
            json.dumps(catalogue), encoding="utf-8")
    if backfill is not None:
        (root / ".shipwright" / "backfill").mkdir(parents=True, exist_ok=True)
        (root / ".shipwright" / "backfill" / "backfill-report.json").write_text(
            json.dumps(backfill), encoding="utf-8")
    if skips is not None:
        (root / ".shipwright" / "adopt" / "traceability-baseline.json").write_text(
            json.dumps({"skip_inventory": {"count": len(skips), "findings": skips}}),
            encoding="utf-8")


def _run(root: Path, *extra: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--project-root", str(root), *extra],
        capture_output=True, text=True, check=False,
    )


def _ok(root: Path, *extra: str) -> dict:
    proc = _run(root, *extra)
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def _triage_titles(root: Path) -> list[str]:
    path = root / ".shipwright" / "triage.jsonl"
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        if rec.get("event") == "append":
            out.append(rec.get("title", ""))
    return out


def _dedup_keys(root: Path) -> list[str]:
    path = root / ".shipwright" / "triage.jsonl"
    keys = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        if rec.get("event") == "append" and rec.get("dedupKey"):
            keys.append(rec["dedupKey"])
    return keys


# --------------------------------------------------------------------------- #
# The happy path
# --------------------------------------------------------------------------- #

def test_it_writes_the_register_the_audit_phase_reads(tmp_path: Path) -> None:
    _seed(tmp_path, backfill={"auto_written": [{"test": "t", "fr": "FR-01.01"}]},
          skips=[{"file": "a.py", "line": 1, "pattern": "pytest.mark.skip"}])
    out = _ok(tmp_path)

    register = json.loads(
        (tmp_path / "shipwright_known_failures.json").read_text(encoding="utf-8"))
    assert register["known_failures"] == []
    assert register["baseline_failure_count"] == 0
    assert register["baseline_observed"] is False
    assert register["inherited_coverage_gaps"]["requirements_without_tests"] == [
        "FR-01.02", "FR-01.03",
    ]
    assert out["written"] == "shipwright_known_failures.json"


def test_onboarding_leaves_exactly_one_confirmation_follow_up(tmp_path: Path) -> None:
    """The card this whole run exists for: reading the code is a start, and
    onboarding must ask for the rest."""
    _seed(tmp_path)
    _ok(tmp_path)
    keys = _dedup_keys(tmp_path)
    assert keys.count("adopt-derived-catalogue-confirmation") == 1
    (title,) = [t for t in _triage_titles(tmp_path) if "Confirm the derived" in t]
    assert "3 unconfirmed" in title


def test_each_inherited_gap_class_leaves_its_own_follow_up(tmp_path: Path) -> None:
    _seed(tmp_path, skips=[{"file": "a.py", "line": 1, "pattern": "pytest.mark.skip"}])
    _ok(tmp_path)
    keys = set(_dedup_keys(tmp_path))
    assert "adopt-inherited-gaps::requirements_without_tests" in keys
    assert "adopt-inherited-gaps::disabled_tests" in keys


def test_a_re_adopt_duplicates_nothing(tmp_path: Path) -> None:
    """Idempotency is what makes it safe to re-run onboarding on a repo that has
    already been onboarded — the Inbox must not grow a second copy of every card."""
    _seed(tmp_path, skips=[{"file": "a.py", "line": 1, "pattern": "js.only"}])
    _ok(tmp_path)
    first = sorted(_dedup_keys(tmp_path))
    second_run = _ok(tmp_path)
    assert sorted(_dedup_keys(tmp_path)) == first
    assert second_run["triage"]["appended"] == 0


def test_a_clean_repo_records_a_register_and_no_gap_cards(tmp_path: Path) -> None:
    """External review G2: no backfill report, no skip inventory, everything
    covered — the normal cleanest case, not a crash."""
    _seed(tmp_path, catalogue=_catalogue_of(1),
          backfill={"already_tagged": [{"test": "t", "frs": ["FR-01.01"]}]})
    out = _ok(tmp_path)
    assert out["inherited_coverage_gaps"] == {
        "requirements_without_tests": 0, "disabled_tests": 0,
    }
    assert not [k for k in _dedup_keys(tmp_path) if k.startswith("adopt-inherited-gaps")]
    assert (tmp_path / "shipwright_known_failures.json").exists()


# --------------------------------------------------------------------------- #
# An observed baseline
# --------------------------------------------------------------------------- #

def test_an_observed_red_baseline_lands_as_inherited_failures(tmp_path: Path) -> None:
    _seed(tmp_path)
    payload = tmp_path / "baseline.json"
    payload.write_text(json.dumps({
        "source": "adopt", "command": "pytest -q",
        "failing_tests": [{"test": "a::b", "description": "was already red"}],
    }), encoding="utf-8")

    out = _ok(tmp_path, "--failures-json", str(payload))
    assert out["baseline_observed"] is True
    assert out["baseline_failure_count"] == 1
    register = json.loads(
        (tmp_path / "shipwright_known_failures.json").read_text(encoding="utf-8"))
    assert register["known_failures"][0]["test"] == "a::b"


def test_an_untrustworthy_baseline_stops_the_step(tmp_path: Path) -> None:
    """Fails closed. The degraded reading of a broken payload is an empty
    register, and empty is indistinguishable from a clean inheritance."""
    _seed(tmp_path)
    payload = tmp_path / "baseline.json"
    payload.write_text(json.dumps({"failing_tests": [{"test": "a"}]}), encoding="utf-8")

    proc = _run(tmp_path, "--failures-json", str(payload))
    assert proc.returncode != 0
    assert "not a usable baseline" in proc.stderr
    assert not (tmp_path / "shipwright_known_failures.json").exists()


# --------------------------------------------------------------------------- #
# Preconditions and preview
# --------------------------------------------------------------------------- #

def test_a_missing_catalogue_stops_the_step_and_names_the_step_that_writes_it(
    tmp_path: Path,
) -> None:
    """Without the catalogue every reported gap would be a guess, so this fails
    closed rather than writing a confident, empty register."""
    _seed(tmp_path, catalogue=None)
    proc = _run(tmp_path)
    assert proc.returncode != 0
    assert "generate_adoption_artifacts.py" in proc.stderr
    assert not (tmp_path / "shipwright_known_failures.json").exists()


def test_dry_run_touches_nothing(tmp_path: Path) -> None:
    _seed(tmp_path, skips=[{"file": "a.py", "line": 1, "pattern": "pytest.mark.skip"}])
    out = _ok(tmp_path, "--dry-run")
    assert out["dry_run"] is True
    assert out["triage"]["would_append"] == 3
    assert not (tmp_path / "shipwright_known_failures.json").exists()
    assert not (tmp_path / ".shipwright" / "triage.jsonl").exists()


# --------------------------------------------------------------------------- #
# A corrupt prerequisite stops the step (external code review)
# --------------------------------------------------------------------------- #

def test_a_corrupt_upstream_artifact_stops_rather_than_inventing_gaps(
    tmp_path: Path,
) -> None:
    """Absent is fine; present-and-broken is not. Reading a corrupt backfill
    report as "no coverage" would file triage cards asserting an inherited state
    the step never actually read."""
    _seed(tmp_path)
    (tmp_path / ".shipwright" / "backfill").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".shipwright" / "backfill" / "backfill-report.json").write_text(
        "{not json", encoding="utf-8")

    proc = _run(tmp_path)
    assert proc.returncode != 0
    assert "seed_traceability_baseline.py" in proc.stderr
    assert not (tmp_path / "shipwright_known_failures.json").exists()


def test_a_catalogue_that_lies_about_confirmation_stops_the_step(tmp_path: Path) -> None:
    """The high-severity finding, end to end: a hand-edited catalogue must not be
    able to suppress the confirmation follow-up."""
    doc = _catalogue_of(1)
    doc["requirements"][0] = {**doc["requirements"][0], "confirmed": "false"}
    _seed(tmp_path, catalogue=doc)
    proc = _run(tmp_path)
    assert proc.returncode != 0
    assert "not a usable catalogue" in proc.stderr
    assert not (tmp_path / ".shipwright" / "triage.jsonl").exists()
