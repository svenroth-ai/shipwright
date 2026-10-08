"""The finalization-claims registry: one extension point for every later F11 gate.

``iterate_checks.run_all_checks`` is at its size cap, so gates register in
``verifiers/_finalization_claims.CLAIM_CHECKS`` and are spliced in once. These
tests pin the splice and fail in BOTH directions between the registry and the
"Finalization claim checks" table in ``docs/hooks-and-pipeline.md``.
"""

from __future__ import annotations

import inspect
import re
from pathlib import Path

import pytest

from tools.verifiers import _finalization_claims as claims
from tools.verifiers import iterate_checks
from tools.verifiers.common import CheckResult

_REPO = Path(__file__).resolve().parents[2]
_DOC = _REPO / "docs" / "hooks-and-pipeline.md"
_TABLE = re.compile(r"<!-- claim-checks:start -->(.*?)<!-- claim-checks:end -->", re.DOTALL)
_ROW = re.compile(r"^\|\s*`(check_\w+)`\s*\|", re.MULTILINE)


def _documented() -> set[str]:
    match = _TABLE.search(_DOC.read_text(encoding="utf-8"))
    assert match, "docs/hooks-and-pipeline.md lost its claim-checks table markers"
    return set(_ROW.findall(match.group(1)))


@pytest.mark.covers("FR-01.11")
def test_every_registered_check_resolves_to_a_three_argument_callable():
    assert claims.CLAIM_CHECKS, "the registry must ship with at least its first tenant"
    for check in claims.CLAIM_CHECKS:
        assert callable(check)
        params = list(inspect.signature(check).parameters.values())
        assert [p.name for p in params][:2] == ["project_root", "run_id"], check
        assert len(params) == 3, f"{check.__name__} must take (project_root, run_id, commit_hash)"


@pytest.mark.covers("FR-01.11")
def test_registered_checks_live_in_their_own_module_not_in_iterate_checks():
    for check in claims.CLAIM_CHECKS:
        assert check.__module__ != iterate_checks.__name__, (
            f"{check.__name__} must keep its code in its own verifiers/ module: "
            "iterate_checks.py is at its bloat cap"
        )
        assert check.__module__.startswith("tools.verifiers."), check.__module__


@pytest.mark.covers("FR-01.11")
def test_registry_has_no_duplicates():
    names = [c.__name__ for c in claims.CLAIM_CHECKS]
    assert len(names) == len(set(names))


@pytest.mark.covers("FR-01.11")
def test_every_registered_check_is_documented():
    missing = {c.__name__ for c in claims.CLAIM_CHECKS} - _documented()
    assert not missing, f"registered but not in the docs claim-checks table: {sorted(missing)}"


@pytest.mark.covers("FR-01.11")
def test_every_documented_check_is_registered():
    ghosts = _documented() - {c.__name__ for c in claims.CLAIM_CHECKS}
    assert not ghosts, f"documented in the claim-checks table but not registered: {sorted(ghosts)}"


@pytest.mark.covers("FR-01.11")
def test_every_check_runs_on_an_empty_project_and_returns_a_check_result(tmp_path):
    results = claims.run_claim_checks(tmp_path, "iterate-2026-10-08-none", "")
    assert len(results) == len(claims.CLAIM_CHECKS)
    assert all(isinstance(r, CheckResult) for r in results)


@pytest.mark.covers("FR-01.11")
def test_run_all_checks_splices_the_registry_in_once(tmp_path):
    names = [r.name for r in iterate_checks.run_all_checks(tmp_path, "iterate-2026-10-08-none", "")]
    expected = [r.name for r in claims.run_claim_checks(tmp_path, "iterate-2026-10-08-none", "")]
    assert expected and all(names.count(n) == 1 for n in expected)
    assert names[-len(expected):] == expected, "claim checks must trail the historical list in registry order"


@pytest.mark.covers("FR-01.11")
def test_a_crashing_check_reads_red_and_does_not_hide_its_siblings(tmp_path, monkeypatch):
    def boom(project_root, run_id, commit_hash=""):
        raise RuntimeError("kaput")

    ok = claims.CLAIM_CHECKS[0]
    monkeypatch.setattr(claims, "CLAIM_CHECKS", [boom, ok])
    results = claims.run_claim_checks(tmp_path, "iterate-2026-10-08-none", "")
    assert len(results) == 2
    assert results[0].ok is False and "kaput" in results[0].detail and results[0].name == "boom"
    assert results[1].name == ok(tmp_path, "iterate-2026-10-08-none", "").name


@pytest.mark.covers("FR-01.11")
def test_iterate_checks_did_not_grow():
    """The cap is the reason this registry exists: a regression here re-opens the problem."""
    lines = len((_REPO / "shared/scripts/tools/verifiers/iterate_checks.py").read_text(encoding="utf-8").splitlines())
    assert lines <= 1086, f"iterate_checks.py grew to {lines} lines (1086 before the registry landed; cap ADR-125)"
