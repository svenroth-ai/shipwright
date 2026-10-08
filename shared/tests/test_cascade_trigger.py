"""F11 gate ``check_cascade_trigger``: at small, a risk flag or a diff > 100 lines needs a code-review answer.

Every case runs against a real git repo built in ``tmp_path``. The gate measures
``merge-base..commit`` itself, so a monkeypatched diff would test nothing. The
trunk is both ``main`` and ``origin/main`` because ``_branch_base_commit`` needs
two names that agree before it trusts a base.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from lib.review_record_core import make_entry, new_record, upsert_review
from lib.review_record_schema import RECORDABLE_TYPES
from tools.verifiers import _finalization_claims as claims
from tools.verifiers.cascade_trigger import check_cascade_trigger

RUN = "iterate-2026-10-08-cascade-probe"


def _git(root: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(root), *args], check=True,
                          capture_output=True, text=True).stdout.strip()


def _repo(tmp_path: Path, files: dict[str, str], removed: list[str] = (),
          moved: dict[str, str] | None = None) -> tuple[Path, str]:
    """Trunk with ``base.txt`` (200 lines) + a branch commit applying ``files``/``removed``/``moved``."""
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q", "-b", "main")
    _git(root, "config", "user.email", "t@example.com")
    _git(root, "config", "user.name", "t")
    _git(root, "config", "core.autocrlf", "false")
    (root / "base.txt").write_text("".join(f"b{i}\n" for i in range(200)), encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "base")
    _git(root, "update-ref", "refs/remotes/origin/main", "HEAD")
    _git(root, "checkout", "-q", "-b", "iterate/probe")
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    for rel in removed:
        (root / rel).unlink()
    for old, new in (moved or {}).items():
        _git(root, "mv", old, new)
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "change")
    return root, _git(root, "rev-parse", "HEAD")


def _lines(n: int) -> str:
    return "".join(f"line {i}\n" for i in range(n))


def _run(root: Path, *, complexity: str = "small", code: dict | None = None,
         plan_flags: list[str] | None = None, recheck_flags: list[str] | None = None) -> None:
    """Untracked bookkeeping for the run: F5c entry, review record, optional flag sources."""
    iterates = root / ".shipwright" / "agent_docs" / "iterates"
    iterates.mkdir(parents=True, exist_ok=True)
    (iterates / f"{RUN}.json").write_text(json.dumps({"run_id": RUN, "complexity": complexity}),
                                          encoding="utf-8")
    if plan_flags is not None:
        (iterates / f"{RUN}.plan.json").write_text(json.dumps({"run_id": RUN, "risk_flags": plan_flags}),
                                                   encoding="utf-8")
    run_dir = root / ".shipwright" / "planning" / "iterate" / RUN
    run_dir.mkdir(parents=True, exist_ok=True)
    if recheck_flags is not None:
        (run_dir / "risk_recheck.json").write_text(json.dumps({
            "schema_version": 1, "run_id": RUN,
            "risk_recheck": {"risk_flags": recheck_flags, "effective_complexity": "small"},
        }), encoding="utf-8")
    code = code or {"status": "not_run", "disposition": "the rule that applies"}
    record = new_record(RUN)
    for review_type in RECORDABLE_TYPES:
        spec = code if review_type == "code" else {"status": "not_run", "disposition": "not part of this probe"}
        entry = make_entry(review_type, spec["status"], disposition=spec.get("disposition"),
                           recorded_by=spec.get("recorded_by"))
        if spec.get("reason_code"):
            entry["reason_code"] = spec["reason_code"]
        record = upsert_review(record, entry, force=True)
    (run_dir / "reviews.json").write_text(json.dumps(record, indent=2), encoding="utf-8")


def _check(root: Path, commit: str):
    return check_cascade_trigger(root, RUN, commit)


@pytest.mark.covers("FR-01.11")
def test_quiet_small_run_is_not_triggered(tmp_path):
    root, sha = _repo(tmp_path, {"src/a.py": _lines(10)})
    _run(root)
    result = _check(root, sha)
    assert result.ok and "not triggered" in result.detail and "10 changed lines" in result.detail


@pytest.mark.covers("FR-01.11")
def test_101_lines_with_free_text_not_run_fails_naming_the_count(tmp_path):
    root, sha = _repo(tmp_path, {"src/a.py": _lines(101)})
    _run(root)
    result = _check(root, sha)
    assert not result.ok
    assert "101 changed lines > 100" in result.detail
    assert "reason_code" in result.detail


@pytest.mark.covers("FR-01.11")
def test_exactly_100_lines_does_not_trigger(tmp_path):
    root, sha = _repo(tmp_path, {"src/a.py": _lines(100)})
    _run(root)
    assert _check(root, sha).ok


@pytest.mark.covers("FR-01.11")
def test_removed_lines_count_too(tmp_path):
    """Added + removed: deleting the 200-line base file is a 200-line change."""
    root, sha = _repo(tmp_path, {}, removed=["base.txt"])
    _run(root)
    result = _check(root, sha)
    assert not result.ok and "200 changed lines" in result.detail


@pytest.mark.covers("FR-01.11")
@pytest.mark.parametrize("code", ["unavailable", "delegated-to-orchestrator", "user-opt-out"])
def test_closed_vocab_not_run_passes(tmp_path, code):
    root, sha = _repo(tmp_path, {"src/a.py": _lines(150)})
    _run(root, code={"status": "not_run", "disposition": "the rule that applies", "reason_code": code})
    result = _check(root, sha)
    assert result.ok and code in result.detail


@pytest.mark.covers("FR-01.11")
@pytest.mark.parametrize("code", ["diff-below-threshold", "complexity-below-threshold", "trivial-auto"])
def test_a_code_that_denies_the_trigger_is_refused(tmp_path, code):
    root, sha = _repo(tmp_path, {"src/a.py": _lines(150)})
    _run(root, code={"status": "not_run", "disposition": "the rule that applies", "reason_code": code})
    result = _check(root, sha)
    assert not result.ok and "says the trigger did not fire" in result.detail


@pytest.mark.covers("FR-01.11")
def test_completed_code_with_evidence_passes_and_without_fails(tmp_path):
    root, sha = _repo(tmp_path, {"src/a.py": _lines(150)})
    _run(root, code={"status": "completed", "recorded_by": "code-reviewer"})
    assert _check(root, sha).ok
    _run(root, code={"status": "completed"})
    result = _check(root, sha)
    assert not result.ok and "no evidence" in result.detail


@pytest.mark.covers("FR-01.11")
def test_recorded_risk_flag_triggers_on_a_tiny_diff(tmp_path):
    root, sha = _repo(tmp_path, {"src/a.py": _lines(3)})
    _run(root, plan_flags=["touches_auth"])
    result = _check(root, sha)
    assert not result.ok and "touches_auth" in result.detail


@pytest.mark.covers("FR-01.11")
def test_campaign_recheck_flag_with_delegation_code_passes(tmp_path):
    root, sha = _repo(tmp_path, {"src/a.py": _lines(3)})
    _run(root, recheck_flags=["touches_io_boundary"],
         code={"status": "not_run", "disposition": "no Agent tool here",
               "reason_code": "delegated-to-orchestrator"})
    result = _check(root, sha)
    assert result.ok and "touches_io_boundary" in result.detail


@pytest.mark.covers("FR-01.11")
def test_cross_component_is_recomputed_from_the_diff(tmp_path):
    """No flag recorded anywhere: the diff itself still raises cross_component."""
    root, sha = _repo(tmp_path, {"plugins/x/hooks/hooks.json": "{}\n"})
    _run(root)
    result = _check(root, sha)
    assert not result.ok and "cross_component" in result.detail


@pytest.mark.covers("FR-01.11")
def test_finalization_records_are_not_counted(tmp_path):
    root, sha = _repo(tmp_path, {
        ".shipwright/agent_docs/iterates/x.test-results.json": _lines(300),
        "CHANGELOG-unreleased.d/added/x.md": _lines(50),
        "shipwright_test_results.json": _lines(80),
        "src/a.py": _lines(5),
    })
    _run(root)
    result = _check(root, sha)
    assert result.ok and "5 changed lines" in result.detail


@pytest.mark.covers("FR-01.11")
@pytest.mark.parametrize("complexity", ["trivial", "medium", "large"])
def test_other_complexities_are_skipped(tmp_path, complexity):
    root, sha = _repo(tmp_path, {"src/a.py": _lines(150)})
    _run(root, complexity=complexity)
    result = _check(root, sha)
    assert result.ok and result.detail.startswith("skipped")


@pytest.mark.covers("FR-01.11")
def test_corrupt_session_plan_fails_closed(tmp_path):
    root, sha = _repo(tmp_path, {"src/a.py": _lines(3)})
    _run(root)
    (root / ".shipwright" / "agent_docs" / "iterates" / f"{RUN}.plan.json").write_text("{", encoding="utf-8")
    result = _check(root, sha)
    assert not result.ok and "unreadable" in result.detail


@pytest.mark.covers("FR-01.11")
def test_not_applicable_is_refused_even_with_a_closed_code(tmp_path):
    root, sha = _repo(tmp_path, {"src/a.py": _lines(150)})
    _run(root, code={"status": "not_applicable", "disposition": "the rule that applies",
                     "reason_code": "unavailable"})
    result = _check(root, sha)
    assert not result.ok and "applicable" in result.detail


@pytest.mark.covers("FR-01.11")
def test_a_pure_rename_counts_both_sides(tmp_path):
    """Rename detection is off, so moving the 200-line file is 200 removed + 200 added."""
    root, sha = _repo(tmp_path, {}, moved={"base.txt": "moved.txt"})
    _run(root)
    result = _check(root, sha)
    assert not result.ok and "400 changed lines" in result.detail


@pytest.mark.covers("FR-01.11")
def test_a_foreign_risk_recheck_record_fails_closed(tmp_path):
    root, sha = _repo(tmp_path, {"src/a.py": _lines(3)})
    _run(root, recheck_flags=[])
    path = root / ".shipwright" / "planning" / "iterate" / RUN / "risk_recheck.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["run_id"] = "iterate-2026-01-01-someone-else"
    path.write_text(json.dumps(data), encoding="utf-8")
    result = _check(root, sha)
    assert not result.ok and "another run" in result.detail


@pytest.mark.covers("FR-01.11")
def test_a_multi_commit_branch_is_measured_whole_not_by_its_tip(tmp_path):
    root, _ = _repo(tmp_path, {"src/a.py": _lines(150)})
    (root / "src" / "b.py").write_text("x\n", encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "tiny tip")
    _run(root)
    result = _check(root, _git(root, "rev-parse", "HEAD"))
    assert not result.ok and "151 changed lines" in result.detail


@pytest.mark.covers("FR-01.11")
def test_no_trustworthy_trunk_base_is_unknown_not_the_tip(tmp_path):
    """Only one trunk name resolves: the base is uncorroborated, so the size is unknown."""
    root, sha = _repo(tmp_path, {"src/a.py": _lines(5)})
    _git(root, "update-ref", "-d", "refs/remotes/origin/main")
    _run(root)
    result = _check(root, sha)
    assert not result.ok and "cannot measure the diff" in result.detail


@pytest.mark.covers("FR-01.11")
def test_a_merge_commit_on_the_trunk_is_unknown(tmp_path):
    root, _ = _repo(tmp_path, {"src/a.py": _lines(150)})
    _git(root, "checkout", "-q", "main")
    _git(root, "merge", "-q", "--no-ff", "-m", "merge", "iterate/probe")
    _git(root, "update-ref", "refs/remotes/origin/main", "HEAD")
    _run(root)
    result = _check(root, _git(root, "rev-parse", "HEAD"))
    assert not result.ok and "merge commit" in result.detail


@pytest.mark.covers("FR-01.11")
def test_gate_is_registered_in_the_claim_registry():
    assert check_cascade_trigger in claims.CLAIM_CHECKS
