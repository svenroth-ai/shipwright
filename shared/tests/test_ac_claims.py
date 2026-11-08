"""Q2 phase 1: the claims file is built by code from the committed AC record and the base catalog (no AI, no agent-written fields)."""

from __future__ import annotations

import json

import pytest

from lib import ac_claims as cl
from lib import ac_decision as ad
from lib import ac_record as ar
from shared.tests.ac_test_helpers import BASE_SPEC, cat_of, commit, git, repo

_RUN = "iterate-2026-11-07-q2-test"
_NEW = "Given a draft, when saved twice, then both versions are kept"
_ADD = {"kind": "add", "ac": "FR-01.03.AC06", "owner_fr": "FR-01.03", "new_text": _NEW}


def _result(items: list[dict], **kw) -> dict:
    return ad.decide(items, cat_of(BASE_SPEC), **kw)


def _hand(**item) -> dict:
    """A decided result as ``decide`` would hand it over, with the item fields set directly (an asked change needs an operator answer)."""
    return {"resolved_items": [item], "ac_decisions": [{"ac": item.get("ac"), "mode": "asked", "answer": "1", "kind": item["kind"]}]}


def _branch(tmp_path):
    root = repo(tmp_path)
    return root, git(root, "rev-parse", "HEAD")


@pytest.mark.covers("FR-01.11/AC50")
def test_an_add_claim_carries_the_recorded_text_and_no_old_text(tmp_path):
    root, base = _branch(tmp_path)
    ar.append_record(root, _RUN, _result([_ADD]))
    (c,) = cl.build_claims(root, _RUN, base)["claims"]
    assert (c["ac"], c["kind"], c["new_text"], c["old_text"]) == ("FR-01.03.AC06", "add", _NEW, None)
    assert c["decided_by"] == "code" and c["confirmed"] is False and c["grade"] == "reject"


@pytest.mark.covers("FR-01.11/AC50")
def test_a_change_claim_takes_old_text_from_the_base_catalog_not_the_record(tmp_path):
    root, base = _branch(tmp_path)
    old = cat_of(BASE_SPEC)["acs"]["FR-01.03.AC05"]
    ar.append_record(root, _RUN, _hand(kind="change", ac="FR-01.03.AC05", old_text="a claim the record makes up", new_text=_NEW, decided_by="operator", confirmed=True))
    (c,) = cl.build_claims(root, _RUN, base)["claims"]
    assert c["kind"] == "change" and c["old_text"] == old and c["new_text"] == _NEW


@pytest.mark.covers("FR-01.11/AC50")
def test_restore_and_unchanged_claims_promise_the_base_text(tmp_path):
    root, base = _branch(tmp_path)
    base_text = cat_of(BASE_SPEC)["acs"]["FR-01.03.AC05"]
    ar.append_record(root, _RUN, _result([{"kind": "restore", "restores_ac": "FR-01.03.AC05"}]))
    (c,) = cl.build_claims(root, _RUN, base)["claims"]
    assert (c["ac"], c["kind"], c["new_text"], c["old_text"]) == ("FR-01.03.AC05", "restore", base_text, base_text)


@pytest.mark.covers("FR-01.11/AC50")
def test_an_exempt_claim_gets_a_stable_item_reference_and_the_files(tmp_path):
    root, base = _branch(tmp_path)
    ar.append_record(root, _RUN, _result([{"kind": "exempt", "reason": "only how", "files": ["b.py", "a.py"]}]))
    (c,) = cl.build_claims(root, _RUN, base)["claims"]
    assert c["ac"] == "item-1" and c["kind"] == "exempt" and c["files"] == ["a.py", "b.py"]


@pytest.mark.covers("FR-01.11/AC50")
def test_only_an_unconfirmed_auto_item_is_warning_grade(tmp_path):
    root, base = _branch(tmp_path)
    ar.append_record(root, _RUN, _hand(**_ADD, decided_by="auto", confirmed=False))
    (c,) = cl.build_claims(root, _RUN, base)["claims"]
    assert c["decided_by"] == "auto" and c["confirmed"] is False and c["grade"] == "warn"


@pytest.mark.covers("FR-01.11/AC50")
def test_a_record_item_with_no_decided_by_is_never_reject_grade(tmp_path):
    root, base = _branch(tmp_path)
    res = _result([_ADD])
    del res["resolved_items"][0]["decided_by"], res["resolved_items"][0]["confirmed"]
    ar.append_record(root, _RUN, res)
    (c,) = cl.build_claims(root, _RUN, base)["claims"]
    assert c["decided_by"] is None and c["confirmed"] is None and c["grade"] == "warn"


@pytest.mark.covers("FR-01.11/AC50")
def test_the_committed_record_is_what_a_head_ref_reads(tmp_path):
    root, base = _branch(tmp_path)
    ar.append_record(root, _RUN, _result([_ADD]))
    head = commit(root, {})
    ar.append_record(root, _RUN, _result([{"kind": "exempt", "reason": "later"}]))  # uncommitted
    doc = cl.build_claims(root, _RUN, base, head)
    assert [c["kind"] for c in doc["claims"]] == ["add"] and doc["head"] == head
    assert [c["kind"] for c in cl.build_claims(root, _RUN, base)["claims"]] == ["exempt"]  # head None = working tree: the last line wins


@pytest.mark.covers("FR-01.11/AC50")
def test_no_record_means_no_claims_and_malformed_items_are_skipped(tmp_path):
    root, base = _branch(tmp_path)
    assert cl.build_claims(root, _RUN, base)["claims"] == []
    path = ar.record_path(root, _RUN)
    path.parent.mkdir(parents=True)
    line = json.dumps({"seq": 1, "kind": "frozen", "items": ["junk", {"kind": "add", "ac": "FR-01.03.AC06", "new_text": _NEW}]})
    path.write_text(line + "\nnot json\n", encoding="utf-8")
    assert [c["ac"] for c in cl.build_claims(root, _RUN, base)["claims"]] == ["FR-01.03.AC06"]


@pytest.mark.covers("FR-01.11/AC50")
def test_write_claims_lands_next_to_the_record_and_is_deterministic(tmp_path):
    root, base = _branch(tmp_path)
    ar.append_record(root, _RUN, _result([_ADD]))
    doc = cl.write_claims(root, _RUN, base)
    path = cl.claims_path(root, _RUN)
    assert path == ar.record_path(root, _RUN).with_name("ac-claims.json")
    assert doc["claims"][0]["ac"] == "FR-01.03.AC06"
    first = path.read_bytes()
    cl.write_claims(root, _RUN, base)
    assert path.read_bytes() == first and json.loads(first)["claims"][0]["ac"] == "FR-01.03.AC06"


@pytest.mark.covers("FR-01.11/AC50")
def test_a_restore_without_restores_ac_never_becomes_the_text_none(tmp_path):
    root, base = _branch(tmp_path)
    ar.append_record(root, _RUN, _hand(kind="restore", ac="FR-01.03.AC05", decided_by="code", confirmed=False))
    ar.append_record(root, _RUN, _hand(kind="restore", decided_by="code", confirmed=False))
    assert cl.build_claims(root, _RUN, base)["claims"][0]["ac"] == "item-1"


@pytest.mark.covers("FR-01.11/AC50")
def test_a_repeated_ac_reference_merges_diverges_and_weakens_from_every_entry():
    claims = [{"ac": "A", "kind": "change", "grade": "reject"}]
    twice = [{"ac": "A", "verdict": "matches", "weakens": True}, {"ac": "A", "verdict": "diverges", "diff_location": "x.py:1", "reason": "r"}]
    for rows in (twice, twice[::-1]):
        out = " | ".join(cl.judge(claims, rows))
        assert "diverges" in out and "x.py:1" in out and "weakens" in out
    assert cl.judge(claims, [{"ac": "A", "verdict": "matches"}, {"ac": "A", "verdict": "matches"}]) == []


@pytest.mark.covers("FR-01.11/AC50")
def test_an_unknown_or_missing_verdict_value_counts_as_no_verdict_not_as_a_match():
    claims = [{"ac": "A", "kind": "add", "grade": "warn"}]
    for rows in ([{"ac": "A", "verdict": "maybe"}], [{"ac": "A"}], [{"ac": "A", "verdict": None}]):
        assert "no AC review ran" in " ".join(cl.judge(claims, rows)), rows
    assert "gave no verdict" in " ".join(cl.judge(claims + [{"ac": "B", "kind": "add", "grade": "warn"}], [{"ac": "B", "verdict": "matches"}, {"ac": "A", "verdict": "maybe"}]))
    assert cl.judge(claims, [{"ac": "A", "verdict": "maybe"}, {"ac": "A", "verdict": "matches"}]) == []


@pytest.mark.covers("FR-01.11/AC50")
def test_weakens_is_only_reported_for_a_changed_promise():
    rows = [{"ac": "A", "verdict": "matches", "weakens": True}]
    assert cl.judge([{"ac": "A", "kind": "add", "grade": "warn"}], rows) == []
    assert "weakens" in " ".join(cl.judge([{"ac": "A", "kind": "change", "grade": "warn"}], rows))
