"""`suite_resume` planning - when a unit may be served from the saved state, and when not.

Every refusal branch is pinned here: a resume must run a unit in FULL whenever the saved
state does not provably describe it. Execution + persistence: `test_suite_resume_exec`;
real pytest: `test_f0_resume_real_pytest`.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

import scripts.tools.suite_resume as rs  # noqa: E402
import scripts.tools.suite_resume_state as st  # noqa: E402
from scripts.tools.tests._resume_fixtures import (  # noqa: E402,F401  (fixtures are injected by name)
    RED, _git, _junit, _prepare, _saved,
)
from scripts.tools.suite_units import INFRA, PASS, TEST_FAILURE  # noqa: E402


# --------------------------------------------------------------- planning

def test_a_red_unit_is_planned_failed_only_with_its_coverage_restored(repo, unit, tmp_path):
    _saved(repo, unit, tmp_path)
    ctx = _prepare(repo, unit)

    plan = ctx.plans["p"]
    assert (plan.mode, plan.red_ids, plan.reuses) == (rs.FAILED_ONLY, RED, 0)
    assert Path(unit.cov_file).is_file() and ctx.chain == ("r@0", "r@1")
    assert ctx.snapshot is not None and ctx.overall == ""

pytest_plugins = ("scripts.tools.tests._resume_fixtures",)  # the `repo` / `unit` fixtures


def test_a_green_unit_is_planned_for_reuse(repo, unit, tmp_path):
    _saved(repo, unit, tmp_path, outcome=PASS, lastfailed=None)
    assert _prepare(repo, unit).plans["p"].mode == rs.REUSE_GREEN


@pytest.mark.parametrize("kw, why", [
    ({"reuses": rs.MAX_REUSES}, "already reused"),
    ({"outcome": INFRA, "lastfailed": None}, "no usable report"),
    ({"lastfailed": None}, "not trustworthy"),
    ({"lastfailed": tuple(f"t::{i}" for i in range(11))}, "not trustworthy"),
    ({"with_cov": False}, "no saved report or coverage"),
    ({"sig": "other"}, "definition changed"),
    ({"report": None}, "no usable report"),
])
def test_every_doubt_about_a_unit_runs_it_in_full(repo, unit, tmp_path, kw, why):
    _saved(repo, unit, tmp_path, **kw)
    ctx = _prepare(repo, unit)
    assert "p" not in ctx.plans and why in ctx.notes["p"], ctx.notes
    assert ctx.label("p").startswith("full run (")


@pytest.mark.parametrize("change", ["add", "remove", "rename", "edit", "conftest"])
def test_added_removed_or_renamed_test_files_run_the_unit_in_full(repo, unit, tmp_path, change):
    _saved(repo, unit, tmp_path)
    tests = repo / "plugins" / "p" / "tests"
    if change == "add":
        (tests / "test_new.py").write_text("def test_n(): pass\n")
    elif change == "remove":
        (tests / "test_x.py").unlink()
    elif change == "edit":
        (tests / "test_x.py").write_text("def test_x(): assert True\n")
    elif change == "conftest":
        (tests / "conftest.py").write_text("X = 2\n")
    else:
        (tests / "test_x.py").rename(tests / "test_y.py")
    ctx = _prepare(repo, unit)
    assert "test files were added, removed, renamed or edited" in ctx.notes["p"]


def test_a_source_edit_is_NOT_a_refusal_by_operator_decision(repo, unit, tmp_path):
    _saved(repo, unit, tmp_path)
    (repo / "plugins" / "p" / "scripts" / "m.py").write_text("x = 2\n")
    ctx = _prepare(repo, unit)
    assert "p" in ctx.plans and ctx.changed == ["plugins/p/scripts/m.py"]


def test_a_moved_merge_base_refuses_everything(repo, unit, tmp_path):
    _saved(repo, unit, tmp_path)
    (repo / "plugins" / "p" / "scripts" / "n.py").write_text("y = 1\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "main moved")
    _git(repo, "update-ref", "refs/remotes/origin/main", "HEAD")
    ctx = _prepare(repo, unit)
    assert not ctx.plans and "merge base" in ctx.overall


def test_a_torn_state_or_none_at_all_refuses(repo, unit, tmp_path):
    assert _prepare(repo, unit).overall == st.NO_STATE
    _saved(repo, unit, tmp_path)
    (st.load_state(repo)[0].directory / "tree.json").write_text("{}")
    assert "torn" in _prepare(repo, unit).overall


def test_unrestorable_coverage_runs_the_unit_in_full(repo, unit, tmp_path):
    snap = _saved(repo, unit, tmp_path)
    (st.load_state(repo)[0].directory / "cov" / "p").write_bytes(b"not sqlite")  # torn
    assert not _prepare(repo, unit).plans
    # a VALID hash over a non-sqlite file reaches the restore step itself
    junk = tmp_path / "junk"
    junk.write_bytes(b"not a database")
    entry = {"sig": st.unit_signature(unit, snap), "outcome": TEST_FAILURE, "lastfailed": list(RED),
             "reuses": 0, "test_files": st.unit_test_files(snap, unit),
             "report": tmp_path / "saved.xml", "cov": junk}
    st.save_state(repo, run_id="r", invocation="r@1", snapshot=snap, chain=(), entries={"p": entry})
    assert "could not be restored" in _prepare(repo, unit).notes["p"]


def test_switch_off_fallback_and_not_a_checkout_all_disable(repo, unit, tmp_path, monkeypatch):
    _saved(repo, unit, tmp_path)
    monkeypatch.setenv(rs.ENV_OFF, "0")
    assert "switched off" in _prepare(repo, unit).overall and not _prepare(repo, unit).plans
    monkeypatch.delenv(rs.ENV_OFF)
    assert _prepare(repo, unit, enabled=False, fallback="gate said no").overall == "gate said no"
    assert "could not be snapshotted" in rs.prepare_resume(tmp_path, [unit], "r").overall


def test_any_unexpected_fault_fails_closed(repo, unit, monkeypatch):
    def boom(*_a, **_k):
        raise RuntimeError("kaboom")
    monkeypatch.setattr(rs, "load_state", boom)
    ctx = _prepare(repo, unit)
    assert not ctx.plans and "failed closed" in ctx.overall and "kaboom" in ctx.overall


def test_a_token_from_another_run_is_never_served(repo, unit, tmp_path):
    _saved(repo, unit, tmp_path)
    ctx = rs.prepare_resume(repo, [unit], "some-other-iterate")
    assert not ctx.plans and ctx.overall == "the saved state belongs to another run"


def test_an_edited_fixture_under_the_test_target_runs_the_unit_in_full(repo, unit, tmp_path):
    (repo / "plugins" / "p" / "tests" / "golden.json").write_text("{}")
    _git(repo, "add", "-A")
    _saved(repo, unit, tmp_path)
    (repo / "plugins" / "p" / "tests" / "golden.json").write_text('{"a": 1}')
    assert "edited" in _prepare(repo, unit).notes["p"]


@pytest.mark.parametrize("path", ["plugins/p/pyproject.toml", "uv.lock", "pytest.ini"])
def test_a_changed_test_environment_input_runs_the_unit_in_full(repo, unit, tmp_path, path):
    _saved(repo, unit, tmp_path)
    (repo / path).write_text("changed\n")
    assert "definition changed" in _prepare(repo, unit).notes["p"]
