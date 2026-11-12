"""Finding text for a recorded event that cannot be repaired in this run."""

from __future__ import annotations

import json

import pytest

from tools.verifiers.plan_stub_check import check_plan_stub_recorded

_RUN = "iterate-2026-11-12-x"


@pytest.mark.covers("FR-01.11")
def test_missing_plan_path_text_says_the_warning_cannot_be_cleared(tmp_path):
    evt = {"type": "work_completed", "source": "iterate", "commit": "", "adr_id": _RUN, "intent": "change",
           "changed_files": ["shared/scripts/lib/x.py"]}
    (tmp_path / "shipwright_events.jsonl").write_text(json.dumps(evt) + "\n", encoding="utf-8")
    detail = check_plan_stub_recorded(tmp_path, _RUN, "").detail
    assert "cannot be cleared" in detail and "cannot be rewritten" in detail and "Next time" in detail


@pytest.mark.covers("FR-01.11")
def test_late_ac_record_text_says_the_warning_cannot_be_cleared(tmp_path):
    from lib import ac_record as ar
    from shared.tests.ac_test_helpers import PROMISE, SPEC, BASE_SPEC
    from shared.tests.ac_test_helpers import commit, decided, git, repo

    root = repo(tmp_path)
    base = git(root, "rev-parse", "HEAD")
    commit(root, {"shared/scripts/a.py": "x = 1" + chr(10), SPEC: BASE_SPEC + f"- (E) [AC06] {PROMISE}" + chr(10)})
    ar.append_record(root, _RUN, decided([{"kind": "add", "owner_fr": "FR-01.03", "new_text": PROMISE}]))
    head = commit(root, {})
    detail = ar._order_problem(root, ar._rel(_RUN), base, head)
    assert "committed after the first code commit" in detail
    assert "cannot be cleared" in detail and "Next time" in detail
