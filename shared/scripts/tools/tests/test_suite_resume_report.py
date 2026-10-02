"""`suite_resume_cov` / `suite_resume_report` / the runner's fallback loop.

Coverage purge rules, the console block + manifest marking of a resumed run, and the one
re-run in full after the diff-coverage gate refuses a resume. The decisions and the
execution are in `test_suite_resume`; real pytest in `test_f0_resume_real_pytest`.
"""

from __future__ import annotations

import sqlite3
import sys
import types
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

import scripts.tools.run_test_suite as runner  # noqa: E402
import scripts.tools.suite_resume as rs  # noqa: E402
import scripts.tools.suite_resume_cov as cov  # noqa: E402
import scripts.tools.suite_resume_report as rep  # noqa: E402
import scripts.tools.suite_resume_state as st  # noqa: E402
from scripts.tools.tests._resume_fixtures import RED, _coverage_db  # noqa: E402
from scripts.tools.suite_units import Unit  # noqa: E402



# --------------------------------------------------------------- coverage

def _purge(tmp_path, files, unit, prior, now, root=None):
    src, dest = tmp_path / "s", tmp_path / "d"
    _coverage_db(src, files)
    ok = cov.restore_coverage(src, dest, unit, root or tmp_path, prior, now)
    db = sqlite3.connect(dest)
    kept = sorted(p for (p,) in db.execute(
        "select distinct f.path from line_bits l join file f on f.id = l.file_id"))
    arcs = db.execute("select count(*) from arc").fetchone()[0]
    db.close()
    return ok, kept, arcs


def test_only_files_the_fix_edited_lose_their_coverage(tmp_path):
    unit = Unit(id="p", cwd="plugins/p", target="tests")
    prior = {"plugins/p/scripts/same.py": "a", "plugins/p/scripts/edited.py": "b"}
    now = {"plugins/p/scripts/same.py": "a", "plugins/p/scripts/edited.py": "CHANGED"}
    ok, kept, arcs = _purge(tmp_path, {"scripts/same.py": {1}, "scripts/edited.py": {1}}, unit, prior, now)
    assert ok and kept == ["scripts/same.py"] and arcs == 1


def test_a_plugin_path_is_never_matched_against_the_repo_root_scripts_dir(tmp_path):
    unit = Unit(id="p", cwd="plugins/p", target="tests")
    same = {"scripts/m.py": "a"}  # a ROOT file of the same relative name, unchanged
    ok, kept, _ = _purge(tmp_path, {"scripts/m.py": {1}}, unit, same, same)
    assert ok and kept == []  # unknown for this unit = stale


def test_unknown_unreadable_deleted_and_foreign_paths_are_stale(tmp_path):
    unit = Unit(id="shared/tests", cwd=".", target="shared/tests")
    prior = {"shared/a.py": "1", "shared/gone.py": "2", "shared/unread.py": "3"}
    now = {"shared/a.py": "1", "shared/unread.py": "-"}
    files = {"shared/a.py": {1}, "shared/gone.py": {1}, "shared/unread.py": {1},
             "shared/unknown.py": {1}, "C:/elsewhere/x.py": {1}}
    ok, kept, _ = _purge(tmp_path, files, unit, prior, now)
    assert ok and kept == ["shared/a.py"]


def test_an_absolute_path_inside_the_project_is_mapped(tmp_path):
    unit = Unit(id="shared/tests", cwd=".", target="shared/tests")
    absolute = (tmp_path / "shared" / "a.py").as_posix()
    ok, kept, _ = _purge(tmp_path, {absolute: {1}}, unit, {"shared/a.py": "1"},
                         {"shared/a.py": "1"}, root=tmp_path.resolve())
    assert ok and kept == [absolute]


def test_a_coverage_file_that_is_not_a_database_is_refused(tmp_path):
    src = tmp_path / "s"
    src.write_bytes(b"garbage")
    assert cov.restore_coverage(src, tmp_path / "d", Unit("p", ".", "t"), tmp_path, {}, {}) is False
    assert cov.restore_coverage(tmp_path / "missing", tmp_path / "d2", Unit("p", ".", "t"),
                                tmp_path, {}, {}) is False


def test_a_database_without_an_arc_table_still_restores(tmp_path):
    src = tmp_path / "s"
    db = sqlite3.connect(src)
    db.executescript("create table file (id integer primary key, path text);"
                     "create table line_bits (file_id integer, context_id integer, numbits blob);")
    db.execute("insert into file values (1, 'shared/a.py')")
    db.execute("insert into line_bits values (1, 0, x'01')")
    db.commit()
    db.close()
    unit = Unit("s", ".", "shared/tests")
    assert cov.restore_coverage(src, tmp_path / "d", unit, tmp_path, {"shared/a.py": "1"},
                                {"shared/a.py": "1"})


# --------------------------------------------------------------- reporting

def _result(ctx):
    return types.SimpleNamespace(resume=ctx)


def _used_ctx():
    plan = rs.ResumePlan("p", rs.FAILED_ONLY, Path("r"), None, RED, 0)
    green = rs.ResumePlan("q", rs.REUSE_GREEN, Path("r"), None, (), 0)
    return rs.ResumeContext(
        invocation="run@1", plans={"p": plan, "q": green}, chain=("a@0",), changed=["f"],
        used={"p", "q"}, reran={"p": [f"t::{i}" for i in range(7)]}, notes={"z": "no saved result"})


def test_the_block_names_a_resumed_run_for_what_it_is():
    text = "\n".join(rep.render_block(_result(_used_ctx())))
    assert "RESUMED F0 RUN - NOT a full run" in text and "CI re-runs everything" in text
    assert "this invocation: run@1; continues: a@0" in text and "files changed since that run: 1" in text
    assert "q: green result REUSED, not re-run" in text
    assert "p: re-ran only 7 red test(s): t::0, t::1, t::2, t::3, t::4 (+2 more)" in text
    assert "z: ran in FULL - no saved result" in text and "resumed-local evidence" in text
    text.encode("ascii")


def test_every_full_run_says_why_and_a_runner_without_resume_says_nothing():
    assert rep.render_block(types.SimpleNamespace()) == []
    assert rep.render_block(_result(rs.ResumeContext(overall=st.NO_STATE))) == [
        f"F0 resume: not used - {st.NO_STATE}"]
    # a state WAS loaded but every unit refused: the per-unit reasons are still printed
    all_refused = rs.ResumeContext(notes={"p": "test files were added, removed, renamed or edited"})
    assert rep.render_block(_result(all_refused)) == [
        "  p: ran in FULL - test files were added, removed, renamed or edited"]
    refused = rep.render_block(_result(rs.ResumeContext(overall="the merge base moved")))
    assert refused == ["F0 resume: not used - the merge base moved"]
    fb = "\n".join(rep.render_block(_result(rs.ResumeContext(fallback="gate said no"))))
    assert "FULL RE-RUN after a resume fallback: gate said no" in fb


def test_the_manifest_marking_is_only_present_for_a_resume():
    assert rep.manifest_extra(rs.ResumeContext(), "r") == {}
    assert rep.manifest_extra(rs.ResumeContext(fallback="why"), "r") == {"resume_fallback": "why"}
    extra = rep.manifest_extra(_used_ctx(), "run")["resumed"]
    assert extra["prior_invocations"] == ["a@0"] and extra["tree_changed_files"] == 1
    assert extra["units"]["q"] == {"mode": "reused-green", "rerun_tests": []}
    assert len(extra["units"]["p"]["rerun_tests"]) == 7


def test_only_a_gate_refusal_of_an_active_resume_triggers_the_fallback():
    active = _result(_used_ctx())
    assert rep.gate_refused_resume(active, 4)
    assert not rep.gate_refused_resume(active, 1) and not rep.gate_refused_resume(active, 0)
    assert not rep.gate_refused_resume(_result(rs.ResumeContext()), 4)
    assert not rep.gate_refused_resume(types.SimpleNamespace(), 4)


# --------------------------------------------------------------- the fallback loop

def _loop(monkeypatch, rcs, active=True):
    seen: list = []

    def leased(root, run_id, *args):
        seen.append(args)
        from contextlib import contextmanager

        @contextmanager
        def cm():
            ctx = _used_ctx() if active and not args else rs.ResumeContext()
            yield types.SimpleNamespace(resume=ctx), None, None
        return cm()
    monkeypatch.setattr(runner, "_run_host_leased_suite", leased)
    answers = iter(rcs)
    monkeypatch.setattr(runner, "_finish_locked", lambda *a: next(answers))
    monkeypatch.setattr(runner, "print_console", lambda *_a: None)
    return seen


def test_a_gate_refused_resume_is_rerun_in_full_once(monkeypatch):
    seen = _loop(monkeypatch, [4, 0])
    assert runner._run_locked(Path("."), "r") == 0
    assert seen == [(), (runner._RESUME_GATE_REFUSED,)]


def test_the_fallback_run_is_never_looped_again(monkeypatch):
    seen = _loop(monkeypatch, [4, 4])
    assert runner._run_locked(Path("."), "r") == 4 and len(seen) == 2


@pytest.mark.parametrize("rc, active", [(0, True), (1, True), (4, False)])
def test_everything_else_returns_its_own_code_after_one_run(monkeypatch, rc, active):
    seen = _loop(monkeypatch, [rc], active=active)
    assert runner._run_locked(Path("."), "r") == rc and len(seen) == 1
