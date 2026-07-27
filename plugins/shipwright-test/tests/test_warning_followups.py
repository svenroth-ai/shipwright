"""Warning-only layers leave a follow-up that outlives the session.

Four layers report a failure without stopping the run: browser tests,
cross-page consistency, screen-vs-mockup fidelity, and the performance budget.
Only the last one filed anything durable — the other three warned to stdout and
were gone at session end, so a suite failing for six weeks was
indistinguishable from one that started failing this morning.

iterate-2026-07-27-test-phase-record-honesty, FR-01.06.
"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts" / "lib"))
from warning_followups import emit_warning_followups  # noqa: E402


def _results(tmp_path: Path, payload: dict) -> Path:
    path = tmp_path / "shipwright_test_results.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _items(project: Path) -> list[dict]:
    path = project / ".shipwright" / "triage.jsonl"
    if not path.exists():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


def _appends(project: Path) -> list[dict]:
    return [i for i in _items(project) if i.get("event") == "append"]


# ---------------------------------------------------------------------------
# AC3 — each warning-only layer leaves something behind
# ---------------------------------------------------------------------------

@pytest.mark.covers("FR-01.06")
def test_a_failing_browser_test_leaves_a_follow_up_per_spec_file(tmp_path):
    _results(tmp_path, {"e2e": {
        "passed": 3, "total": 5,
        "failures": [
            {"title": "logs in", "file": "e2e/flows/01-auth.spec.ts"},
            {"title": "logs out", "file": "e2e/flows/01-auth.spec.ts"},
            {"title": "pays", "file": "e2e/flows/04-pay.spec.ts"},
        ],
    }})
    count = emit_warning_followups(tmp_path)

    assert count == 2  # grouped by spec file, not one per assertion
    keys = {i["dedupKey"] for i in _appends(tmp_path)}
    assert keys == {
        "test-warning:e2e:e2e/flows/01-auth.spec.ts",
        "test-warning:e2e:e2e/flows/04-pay.spec.ts",
    }


@pytest.mark.covers("FR-01.06")
def test_a_failing_consistency_category_leaves_a_follow_up(tmp_path):
    _results(tmp_path, {"consistency": {
        "passed": 4, "total": 6,
        "categories": {
            "spacing": {"status": "INCONSISTENT"},
            "colors": {"status": "INCONSISTENT"},
            "typography": {"status": "CONSISTENT"},
        },
    }})
    emit_warning_followups(tmp_path)

    keys = {i["dedupKey"] for i in _appends(tmp_path)}
    assert keys == {
        "test-warning:consistency:spacing", "test-warning:consistency:colors",
    }


@pytest.mark.covers("FR-01.06")
def test_a_diverging_screen_leaves_a_follow_up(tmp_path):
    _results(tmp_path, {"design_fidelity": {
        "passed": 1, "total": 3,
        "screens": [
            {"mockup": "home.html", "route": "/", "status": "pass"},
            {"mockup": "pricing.html", "route": "/pricing", "status": "needs_review"},
            {"mockup": "gone.html", "route": "/gone", "status": "error"},
        ],
    }})
    emit_warning_followups(tmp_path)

    keys = {i["dedupKey"] for i in _appends(tmp_path)}
    assert keys == {
        "test-warning:fidelity:pricing.html", "test-warning:fidelity:gone.html",
    }


@pytest.mark.covers("FR-01.06")
def test_all_three_layers_emit_in_one_pass(tmp_path):
    _results(tmp_path, {
        "e2e": {"passed": 0, "total": 1,
                "failures": [{"title": "x", "file": "e2e/a.spec.ts"}]},
        "consistency": {"passed": 0, "total": 1,
                        "categories": {"spacing": {"status": "INCONSISTENT"}}},
        "design_fidelity": {"passed": 0, "total": 1,
                            "screens": [{"mockup": "a.html", "status": "needs_review"}]},
    })
    assert emit_warning_followups(tmp_path) == 3


# ---------------------------------------------------------------------------
# Silence when there is nothing to say
# ---------------------------------------------------------------------------

@pytest.mark.covers("FR-01.06")
def test_a_green_run_files_nothing(tmp_path):
    _results(tmp_path, {
        "e2e": {"passed": 5, "total": 5, "failures": []},
        "consistency": {"passed": 6, "total": 6, "categories": {}},
        "design_fidelity": {"passed": 3, "total": 3, "screens": []},
    })
    assert emit_warning_followups(tmp_path) == 0
    assert _appends(tmp_path) == []


@pytest.mark.covers("FR-01.06")
def test_a_skipped_layer_files_nothing(tmp_path):
    _results(tmp_path, {
        "e2e": {"passed": 0, "total": 0, "skipped": True, "reason": "no DEV URL"},
        "consistency": {"passed": 0, "total": 0, "skipped": True},
        "design_fidelity": {"passed": 0, "total": 0, "skipped": True},
    })
    assert emit_warning_followups(tmp_path) == 0


@pytest.mark.covers("FR-01.06")
def test_a_truthy_skip_COUNT_does_not_read_as_a_skipped_layer(tmp_path):
    """`skipped` means two things in this record and they must not be conflated.

    Boolean `skipped: true` = the layer never ran. Integer `skipped: 3` = a
    count inside a layer that DID run. Reading the count as the flag silently
    discarded a layer that ran and failed.
    """
    _results(tmp_path, {"e2e": {"passed": 0, "skipped": 2, "total": 3, "failures": [
        {"title": "pays", "file": "e2e/pay.spec.ts"},
    ]}})
    assert emit_warning_followups(tmp_path) == 1


@pytest.mark.covers("FR-01.06")
def test_a_missing_results_file_is_a_no_op_not_a_crash(tmp_path):
    assert emit_warning_followups(tmp_path) == 0


@pytest.mark.covers("FR-01.06")
def test_a_malformed_results_file_is_a_no_op_not_a_crash(tmp_path):
    (tmp_path / "shipwright_test_results.json").write_text("{broken", encoding="utf-8")
    assert emit_warning_followups(tmp_path) == 0


# ---------------------------------------------------------------------------
# A layer that reports a failure it cannot itemize still leaves a follow-up
#
# External code review on the delivered head: the identity emitters only see
# `failures` / `categories` / `screens`. A record that truthfully reports a
# warning-layer failure through counts alone emitted NOTHING, so AC3 held only
# for records that happened to carry the optional detail.
# ---------------------------------------------------------------------------

@pytest.mark.covers("FR-01.06")
@pytest.mark.parametrize(("layer", "key"), [
    ("e2e", "test-warning:e2e:layer"),
    ("consistency", "test-warning:consistency:layer"),
    ("design_fidelity", "test-warning:design_fidelity:layer"),
])
def test_a_failure_reported_only_as_counts_still_leaves_a_follow_up(tmp_path, layer, key):
    _results(tmp_path, {layer: {"passed": 0, "total": 3}})
    assert emit_warning_followups(tmp_path) == 1
    assert {i["dedupKey"] for i in _appends(tmp_path)} == {key}


@pytest.mark.covers("FR-01.06")
def test_an_explicit_failed_count_with_no_detail_also_emits(tmp_path):
    _results(tmp_path, {"e2e": {"passed": 5, "total": 5, "failed": 2}})
    assert emit_warning_followups(tmp_path) == 1


@pytest.mark.covers("FR-01.06")
def test_the_aggregate_item_does_not_claim_anything_was_matched(tmp_path):
    # It cannot know which failures these were, so it must not imply it does.
    _results(tmp_path, {"e2e": {"passed": 0, "total": 3}})
    emit_warning_followups(tmp_path)

    detail = _appends(tmp_path)[0]["detail"]
    assert "no per-finding detail" in detail
    assert "nothing was matched against the accepted-failure list" in detail


@pytest.mark.covers("FR-01.06")
def test_the_fallback_does_not_fire_when_the_layer_was_itemized(tmp_path):
    # Identities present → per-finding items only, no duplicate aggregate.
    _results(tmp_path, {"e2e": {"passed": 0, "total": 1, "failures": [
        {"title": "x", "file": "e2e/a.spec.ts"},
    ]}})
    emit_warning_followups(tmp_path)

    assert {i["dedupKey"] for i in _appends(tmp_path)} == {
        "test-warning:e2e:e2e/a.spec.ts",
    }


@pytest.mark.covers("FR-01.06")
def test_the_fallback_does_not_fire_on_a_green_or_skipped_layer(tmp_path):
    _results(tmp_path, {
        "e2e": {"passed": 3, "total": 3},
        "consistency": {"passed": 0, "total": 0, "skipped": True},
        "design_fidelity": {"passed": 2, "total": 2},
    })
    assert emit_warning_followups(tmp_path) == 0


@pytest.mark.covers("FR-01.06")
@pytest.mark.parametrize("layer", ["e2e", "consistency", "design_fidelity"])
def test_a_fully_skipped_count_bearing_layer_is_not_a_failure(tmp_path, layer):
    """A skipped test is not a failure — the same rule as the validator's.

    `{"passed": 0, "skipped": 3, "total": 3}` satisfies `passed < total` but
    nothing failed. Filing a persistent follow-up for it would be worse than
    the gap the fallback closes: it teaches the operator to ignore triage.
    """
    _results(tmp_path, {layer: {"passed": 0, "skipped": 3, "total": 3}})
    assert emit_warning_followups(tmp_path) == 0
    assert _appends(tmp_path) == []


@pytest.mark.covers("FR-01.06")
def test_skips_plus_a_real_failure_still_emits(tmp_path):
    _results(tmp_path, {"e2e": {"passed": 0, "skipped": 2, "total": 3}})
    assert emit_warning_followups(tmp_path) == 1


@pytest.mark.covers("FR-01.06")
def test_an_explicit_zero_failed_beats_a_bare_gap(tmp_path):
    _results(tmp_path, {"e2e": {"passed": 1, "total": 4, "failed": 0}})
    assert emit_warning_followups(tmp_path) == 0


@pytest.mark.covers("FR-01.06")
def test_a_count_only_failure_stays_one_item_across_commits(tmp_path):
    _results(tmp_path, {"e2e": {"passed": 0, "total": 3}})
    first = emit_warning_followups(tmp_path, commit="aaaaaaa")
    second = emit_warning_followups(tmp_path, commit="bbbbbbb")
    assert (first, second) == (1, 0)


# ---------------------------------------------------------------------------
# External review R2 — a persistent failure must not multiply
# ---------------------------------------------------------------------------

@pytest.mark.covers("FR-01.06")
def test_the_same_failure_across_two_commits_stays_one_follow_up(tmp_path):
    payload = {"e2e": {"passed": 0, "total": 1,
                       "failures": [{"title": "x", "file": "e2e/a.spec.ts"}]}}
    _results(tmp_path, payload)

    first = emit_warning_followups(tmp_path, commit="aaaaaaa")
    second = emit_warning_followups(tmp_path, commit="bbbbbbb")

    assert (first, second) == (1, 0)
    assert len(_appends(tmp_path)) == 1


@pytest.mark.covers("FR-01.06")
def test_a_second_broken_spec_still_gets_its_own_follow_up(tmp_path):
    _results(tmp_path, {"e2e": {"passed": 0, "total": 1,
                                "failures": [{"title": "x", "file": "e2e/a.spec.ts"}]}})
    emit_warning_followups(tmp_path)

    _results(tmp_path, {"e2e": {"passed": 0, "total": 2, "failures": [
        {"title": "x", "file": "e2e/a.spec.ts"},
        {"title": "y", "file": "e2e/b.spec.ts"},
    ]}})
    assert emit_warning_followups(tmp_path) == 1


# ---------------------------------------------------------------------------
# Retry-passes are visible, and never blocking
# ---------------------------------------------------------------------------

@pytest.mark.covers("FR-01.06")
def test_a_test_that_only_passes_on_retry_leaves_a_low_severity_follow_up(tmp_path):
    _results(tmp_path, {"e2e": {
        "passed": 5, "total": 5, "failures": [], "flaky": 1,
        "flaky_tests": [{"title": "checkout", "file": "e2e/pay.spec.ts", "retries": 2}],
    }})
    assert emit_warning_followups(tmp_path) == 1

    item = _appends(tmp_path)[0]
    assert item["dedupKey"] == "test-warning:flaky:e2e/pay.spec.ts::checkout"
    assert item["severity"] == "low"
    assert "retr" in item["detail"].lower()


# ---------------------------------------------------------------------------
# AC4 — known-and-accepted failures are reported separately, not as backlog
# ---------------------------------------------------------------------------

@pytest.mark.covers("FR-01.06")
def test_an_accepted_baseline_failure_does_not_become_a_follow_up(tmp_path):
    (tmp_path / "shipwright_known_failures.json").write_text(json.dumps({
        "known_failures": [{"test": "e2e/flows/01-auth.spec.ts",
                            "description": "broken before onboarding"}],
    }), encoding="utf-8")
    _results(tmp_path, {"e2e": {"passed": 0, "total": 2, "failures": [
        {"title": "logs in", "file": "e2e/flows/01-auth.spec.ts"},
        {"title": "pays", "file": "e2e/flows/04-pay.spec.ts"},
    ]}})

    assert emit_warning_followups(tmp_path) == 1
    keys = {i["dedupKey"] for i in _appends(tmp_path)}
    assert keys == {"test-warning:e2e:e2e/flows/04-pay.spec.ts"}


@pytest.mark.covers("FR-01.06")
def test_the_returned_summary_names_accepted_and_genuine_separately(tmp_path):
    from warning_followups import summarize_warning_layers  # noqa: PLC0415

    (tmp_path / "shipwright_known_failures.json").write_text(json.dumps({
        "known_failures": [{"test": "e2e/flows/01-auth.spec.ts"}],
    }), encoding="utf-8")
    _results(tmp_path, {"e2e": {"passed": 0, "total": 2, "failures": [
        {"title": "logs in", "file": "e2e/flows/01-auth.spec.ts"},
        {"title": "pays", "file": "e2e/flows/04-pay.spec.ts"},
    ], "flaky": 1, "flaky_tests": [{"title": "c", "file": "e2e/pay.spec.ts",
                                    "retries": 1}]}})

    summary = summarize_warning_layers(tmp_path)

    assert summary["e2e"]["known_accepted"] == ["e2e/flows/01-auth.spec.ts › logs in"]
    assert summary["e2e"]["genuine"] == ["e2e/flows/04-pay.spec.ts › pays"]
    assert summary["e2e"]["flaky"] == 1
    assert summary["accepted_baseline"]["present"] is True


@pytest.mark.covers("FR-01.06")
def test_the_summary_says_when_the_accepted_list_could_not_be_read(tmp_path):
    from warning_followups import summarize_warning_layers  # noqa: PLC0415

    (tmp_path / "shipwright_known_failures.json").write_text("{broken", encoding="utf-8")
    _results(tmp_path, {"e2e": {"passed": 0, "total": 1,
                                "failures": [{"title": "x", "file": "a.spec.ts"}]}})

    summary = summarize_warning_layers(tmp_path)
    assert summary["accepted_baseline"]["malformed"] is True
    # ...and nothing is excused on the strength of an unreadable list
    assert summary["e2e"]["known_accepted"] == []


# ---------------------------------------------------------------------------
# Emission never turns a warning layer into a blocking one
# ---------------------------------------------------------------------------

@pytest.mark.covers("FR-01.06")
def test_a_broken_triage_writer_does_not_raise_into_the_phase(tmp_path, monkeypatch):
    import warning_followups

    def boom(*a, **k):
        raise RuntimeError("triage store is on fire")

    monkeypatch.setattr(warning_followups, "_append", boom)
    _results(tmp_path, {"e2e": {"passed": 0, "total": 1,
                                "failures": [{"title": "x", "file": "a.spec.ts"}]}})

    assert emit_warning_followups(tmp_path) == 0


@pytest.mark.covers("FR-01.06")
def test_long_titles_are_bounded(tmp_path):
    _results(tmp_path, {"e2e": {"passed": 0, "total": 1, "failures": [
        {"title": "x" * 500, "file": "e2e/a.spec.ts"},
    ]}})
    emit_warning_followups(tmp_path)

    item = _appends(tmp_path)[0]
    assert len(item["title"]) <= 160
    assert len(item["detail"]) <= 2000
