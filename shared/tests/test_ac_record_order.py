"""The AC record's order check on a branch with several commits: the record must come no later than the first code commit."""

from __future__ import annotations

import pytest

from shared.tests.ac_test_helpers import BASE_SPEC as _BASE_SPEC
from shared.tests.ac_test_helpers import PROMISE as _PROMISE
from shared.tests.ac_test_helpers import SPEC as _SPEC
from shared.tests.ac_test_helpers import commit as _commit, decided as _decided, git as _git, repo as _repo
from lib import ac_record as ar
from tools.verifiers import pre_build_ac_check as chk

_RUN = "iterate-2026-11-09-q1-order-check"
_LATE = "committed after the first code commit"


def _branch(tmp_path, monkeypatch):
    root = _repo(tmp_path)
    base = _git(root, "rev-parse", "HEAD")
    monkeypatch.setattr(chk, "_work_event", lambda r, rid: {"source": "iterate"})
    monkeypatch.setattr(chk, "_branch_base_commit", lambda r, c: base)
    return root, base


def _record(root):
    ar.append_record(root, _RUN, _decided([{"kind": "add", "owner_fr": "FR-01.03", "new_text": _PROMISE}]))
    return _commit(root, {})


def _code(root):
    return _commit(root, {"shared/scripts/a.py": "x = 1\n", _SPEC: _BASE_SPEC + f"- (E) [AC06] {_PROMISE}\n"})


def _order(root, base, head):
    return ar._order_problem(root, ar._rel(_RUN), base, head)


@pytest.mark.covers("FR-01.11/AC49")
def test_a_record_after_a_docs_only_commit_and_before_the_code_is_in_order(tmp_path, monkeypatch):
    # Regression: git separates a commit's hash from its file names with an empty line, and the
    # check counted that empty name as code, so every multi-commit branch looked like code came first.
    root, base = _branch(tmp_path, monkeypatch)
    _commit(root, {"docs/notes.md": "plan\n"})
    _record(root)
    head = _code(root)
    assert _order(root, base, head) == ""
    assert _LATE not in chk.check_pre_build_ac_recorded(root, _RUN, head).detail


@pytest.mark.covers("FR-01.11/AC49")
def test_a_record_committed_after_the_code_on_a_multi_commit_branch_is_still_flagged(tmp_path, monkeypatch):
    root, base = _branch(tmp_path, monkeypatch)
    _commit(root, {"docs/notes.md": "plan\n"})
    _code(root)
    head = _record(root)
    assert _LATE in _order(root, base, head)
    assert _LATE in chk.check_pre_build_ac_recorded(root, _RUN, head).detail


@pytest.mark.covers("FR-01.11/AC49")
def test_code_brought_in_by_merging_the_default_branch_is_not_this_runs_code(tmp_path, monkeypatch):
    root, base = _branch(tmp_path, monkeypatch)
    _git(root, "checkout", "-q", "-b", "work")
    _commit(root, {"docs/notes.md": "plan\n"})                      # this run: docs first
    _git(root, "checkout", "-q", "main")
    _commit(root, {"shared/scripts/other.py": "y = 2\n"})            # someone else's code lands on main
    _git(root, "checkout", "-q", "work")
    _git(root, "merge", "-q", "--no-edit", "main")                   # the run brings main in
    _record(root)
    head = _code(root)
    assert _order(root, base, head) == ""


@pytest.mark.covers("FR-01.11/AC49")
def test_a_record_the_branch_leaves_untouched_is_not_order_checked(tmp_path, monkeypatch):
    root, _ = _branch(tmp_path, monkeypatch)
    base = _record(root)                                             # a stacked unit: the record predates this branch
    head = _code(root)                                               # the branch never touches the record file
    _, problems = ar._record_problems(root, _RUN, base, head)
    assert not any(_LATE in p for p in problems)


@pytest.mark.covers("FR-01.11/AC49")
def test_a_record_appended_after_the_code_to_one_already_at_the_base_is_flagged(tmp_path, monkeypatch):
    root, _ = _branch(tmp_path, monkeypatch)
    base = _record(root)
    _code(root)
    head = _record(root)                                             # this branch's own record lands after its code
    _, problems = ar._record_problems(root, _RUN, base, head)
    assert any(_LATE in p for p in problems)
