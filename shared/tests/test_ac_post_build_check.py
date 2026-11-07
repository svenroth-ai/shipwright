"""Q2 phase 1: the F11 check on the spec row's per-AC verdicts - warning-only, visible when no AC review ran, never a crash."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from lib import ac_decision as ad
from lib import ac_mode
from lib import ac_record as ar
from shared.tests.ac_test_helpers import BASE_SPEC, cat_of, git, repo
from tools.verifiers import _finalization_claims as registry
from tools.verifiers import post_build_ac_check as chk
from tools.verifiers.common import Severity

_RUN = "iterate-2026-11-07-q2-check"
_NEW = "Given a draft, when saved twice, then both versions are kept"
_ADD = {"kind": "add", "ac": "FR-01.03.AC06", "owner_fr": "FR-01.03", "new_text": _NEW}
_REVIEWS = f".shipwright/planning/iterate/{_RUN}/reviews.json"


@pytest.fixture
def branch(tmp_path, monkeypatch):
    root = repo(tmp_path)
    base = git(root, "rev-parse", "HEAD")
    monkeypatch.setattr(chk, "_work_event", lambda r, rid: {"source": "iterate", "intent": "feature"})
    monkeypatch.setattr(chk, "_branch_base_commit", lambda r, c: base)

    def commit(files: dict[str, str]) -> str:
        for rel, text in files.items():
            (root / rel).parent.mkdir(parents=True, exist_ok=True)
            (root / rel).write_text(text, encoding="utf-8")
        git(root, "add", "-A")
        git(root, "commit", "-qm", "work")
        return git(root, "rev-parse", "HEAD")
    return root, commit


def _record(root, **item) -> None:
    res = ad.decide([_ADD], cat_of(BASE_SPEC))
    res["resolved_items"][0].update(item)
    ar.append_record(root, _RUN, res)


def _spec_row(verdicts: list[dict] | None, status: str = "completed") -> str:
    row = {"review_type": "spec", "status": status, **({"ac_verdicts": verdicts} if verdicts is not None else {})}
    return json.dumps({"schema_version": 1, "run_id": _RUN, "reviews": {"spec": row}})


def _v(verdict: str = "matches", **kw) -> dict:
    return {"ac": "FR-01.03.AC06", "verdict": verdict, "diff_location": "src/a.py:12", "reason": "saved twice overwrites the first copy", **kw}


@pytest.mark.covers("FR-01.11/AC50")
def test_a_run_with_no_event_is_skipped_and_one_with_no_ac_item_passes(branch):
    root, commit = branch
    head = commit({"docs/a.md": "x\n"})
    assert chk.check_post_build_ac_review(root, _RUN, head).ok
    chk._work_event = lambda r, rid: None
    assert chk.check_post_build_ac_review(root, _RUN, head).severity == Severity.SKIPPED.value


@pytest.mark.covers("FR-01.11/AC50")
def test_no_spec_row_at_all_says_visibly_that_no_ac_review_ran(branch):
    root, commit = branch
    _record(root)
    res = chk.check_post_build_ac_review(root, _RUN, commit({}))
    assert not res.ok and res.severity == Severity.WARNING.value and res.strict_exempt
    assert "no AC review ran" in res.detail and "FR-01.03.AC06" in res.detail


@pytest.mark.covers("FR-01.11/AC50")
def test_a_spec_pass_that_did_not_run_or_carries_no_verdicts_reads_the_same_way(branch):
    root, commit = branch
    _record(root)
    for text in (_spec_row(None, "not_run"), _spec_row(None), _spec_row([_v()], "not_run")):
        head = commit({_REVIEWS: text})
        res = chk.check_post_build_ac_review(root, _RUN, head)
        assert "no AC review ran" in res.detail, text


@pytest.mark.covers("FR-01.11/AC50")
def test_every_claim_matching_passes(branch):
    root, commit = branch
    _record(root)
    res = chk.check_post_build_ac_review(root, _RUN, commit({_REVIEWS: _spec_row([_v("matches")])}))
    assert res.ok and "1 claim" in res.detail


@pytest.mark.covers("FR-01.11/AC50")
def test_a_divergence_on_an_operator_or_code_item_is_reject_grade_but_only_warns(branch):
    root, commit = branch
    _record(root)  # decided_by code
    res = chk.check_post_build_ac_review(root, _RUN, commit({_REVIEWS: _spec_row([_v("diverges")])}))
    assert not res.ok and res.severity == Severity.WARNING.value and res.strict_exempt
    assert "reject-grade" in res.detail and "src/a.py:12" in res.detail and "overwrites" in res.detail


@pytest.mark.covers("FR-01.11/AC50")
def test_a_divergence_on_an_unconfirmed_auto_item_is_warning_only(branch):
    root, commit = branch
    _record(root, decided_by="auto", confirmed=False)
    res = chk.check_post_build_ac_review(root, _RUN, commit({_REVIEWS: _spec_row([_v("diverges")])}))
    assert "warning only" in res.detail and "reject-grade" not in res.detail and res.severity == Severity.WARNING.value


@pytest.mark.covers("FR-01.11/AC50")
def test_a_claim_with_no_verdict_and_a_weakened_change_are_named(branch):
    root, commit = branch
    _record(root)
    res = chk.check_post_build_ac_review(root, _RUN, commit({_REVIEWS: _spec_row([_v("matches", ac="FR-01.03.AC99")])}))
    assert "FR-01.03.AC06 (add): the reviewer gave no verdict" in res.detail
    res = chk.check_post_build_ac_review(root, _RUN, commit({_REVIEWS: _spec_row([_v("matches", weakens=True)])}))
    assert "weakens" in res.detail


@pytest.mark.covers("FR-01.11/AC50")
def test_unreadable_reviews_json_is_a_warning_not_a_crash(branch):
    root, commit = branch
    _record(root)
    res = chk.check_post_build_ac_review(root, _RUN, commit({_REVIEWS: "{not json"}))
    assert not res.ok and res.severity == Severity.WARNING.value and "no AC review ran" in res.detail


@pytest.mark.covers("FR-01.11/AC50")
def test_mode_off_skips_visibly(branch):
    root, commit = branch
    _record(root)
    ac_mode.write_marker(root, _RUN, "off", "flag")
    res = chk.check_post_build_ac_review(root, _RUN, commit({}))  # the commit takes the marker with it
    assert res.severity == Severity.SKIPPED.value and "mode=off" in res.detail


@pytest.mark.covers("FR-01.11/AC50")
def test_the_check_is_registered_after_the_pre_build_check_and_named():
    names = [c.__name__ for c in registry.CLAIM_CHECKS]
    assert names.index("check_post_build_ac_review") == names.index("check_pre_build_ac_recorded") + 1
    assert chk.CHECK_NAME == "post-build AC review (per-AC verdicts)"
    assert Path(chk.__file__).name == "post_build_ac_check.py"
