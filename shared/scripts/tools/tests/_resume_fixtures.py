"""Shared fixtures for the F0 resume tests (a git checkout, a unit, a saved state)."""

from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

import scripts.tools.suite_resume as rs  # noqa: E402
import scripts.tools.suite_resume_state as st  # noqa: E402
from scripts.tools.suite_units import TEST_FAILURE, Unit  # noqa: E402

_ENV = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
        "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
RED = ("plugins/p/tests/test_x.py::test_a", "plugins/p/tests/test_x.py::test_b")


def _junit(path: Path, cases: list[tuple[str, bool]]) -> None:
    body = "".join(
        f'<testcase classname="t.C" name="{n}">' + ('<failure message="x"/>' if bad else "")
        + "</testcase>" for n, bad in cases)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f'<testsuites><testsuite name="p" tests="{len(cases)}">{body}'
                    "</testsuite></testsuites>", encoding="utf-8")


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=str(root), env=_ENV, capture_output=True,
                   text=True, check=True)


@pytest.fixture
def repo(tmp_path):
    root = tmp_path / "repo"
    (root / "plugins" / "p" / "tests").mkdir(parents=True)
    (root / "plugins" / "p" / "tests" / "test_x.py").write_text("def test_a(): pass\n")
    (root / "plugins" / "p" / "scripts").mkdir()
    (root / "plugins" / "p" / "scripts" / "m.py").write_text("x = 1\n")
    (root / ".gitignore").write_text(".shipwright/\n.cov-data/\n")
    _git(root, "init", "-q")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "base")
    _git(root, "update-ref", "refs/remotes/origin/main", "HEAD")
    return root


@pytest.fixture
def unit(repo):
    data = repo / ".cov-data"
    data.mkdir()
    return Unit(id="p", cwd="plugins/p", target="tests", cov_args=("--cov=scripts",),
                cov_file=str(data / ".coverage.p"))


def _coverage_db(path: Path, files: dict[str, set[int]]) -> None:
    db = sqlite3.connect(path)
    db.executescript("create table file (id integer primary key, path text);"
                     "create table line_bits (file_id integer, context_id integer, numbits blob);"
                     "create table arc (file_id integer, context_id integer, fromno integer, tono integer);")
    for fid, (name, lines) in enumerate(files.items(), 1):
        bits = bytearray(4)
        for line in lines:
            bits[line // 8] |= 1 << (line % 8)
        db.execute("insert into file values (?, ?)", (fid, name))
        db.execute("insert into line_bits values (?, 0, ?)", (fid, bytes(bits)))
        db.execute("insert into arc values (?, 0, 1, 2)", (fid,))
    db.commit()
    db.close()


def _saved(repo: Path, unit: Unit, tmp_path: Path, *, outcome=TEST_FAILURE, lastfailed=RED,
           reuses=0, files=None, with_cov=True, snap=None, **over) -> st.TreeSnapshot:
    snap = snap or st.tree_snapshot(repo)
    report, cov_file = tmp_path / "saved.xml", tmp_path / "saved.cov"
    _junit(report, [("test_a", outcome == TEST_FAILURE), ("test_b", outcome == TEST_FAILURE),
                    ("test_ok", False)])
    _coverage_db(cov_file, files or {"scripts/m.py": {1}})
    entry = {"sig": st.unit_signature(unit, snap), "outcome": outcome,
             "lastfailed": list(lastfailed) if lastfailed else None,
             "test_files": st.unit_test_files(snap, unit), "reuses": reuses,
             "report": report, "cov": cov_file if with_cov else None, **over}
    assert st.save_state(repo, run_id="r", invocation="r@1", snapshot=snap, chain=("r@0",),
                         entries={unit.id: entry})
    return snap


def _prepare(repo, unit, **kw):
    return rs.prepare_resume(repo, [unit], "r", **kw)
