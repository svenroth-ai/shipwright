"""Missing-ancestor synthesis tests for iterate-timing spans (measurement only).

iterate-2026-08-05-iterate-timings-derived-parent: eight production runs
after P1.17 shipped, ZERO `work_completed` events carried `iterate_timings`.
The producer-owned spans (F0's queue/active, external_review, delivery's own
ladder) all wrote real data to the sidecar — but every one of them nests
under one of the 7 top-level groups, and 6 of those 7 are agent-emitted: no
process owns the boundary, so a session that never calls the mark leaves
every producer child an orphan with no containing parent instance at all.
`_fold_iterate_timings` folds an empty tree; the durable event gets nothing.

The fix: when a child names a parent with NO explicit record anywhere in the
run (not merely no CONTAINING record — see the impossible-ordering cases in
test_iterate_timings_hierarchy.py, which stay rejected, never synthesized
around), materialize that parent from the envelope (earliest start, latest
end) of the children that name it. Marked `source="derived"` so it is never
mistaken for a measured boundary; a real agent/producer record for the same
name, whenever one exists, is always used instead. Split from
test_iterate_timings_hierarchy.py at ~300 lines (file-size guideline).
"""

from __future__ import annotations

import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(_SCRIPTS))

from lib import iterate_timings_normalize as itn  # noqa: E402


def _span(name, parent, start, end, duration_ms, **extra):
    return {"event": "span", "name": name, "parent": parent, "attempt": 1,
           "source": "producer", "outcome": "completed", "start_utc": start,
           "end_utc": end, "duration_ms": duration_ms, "extra": extra}


def test_missing_top_level_parent_is_synthesized_from_children_envelope(tmp_path):
    """The exact production shape: 'verification' is never agent-marked, but
    F0's own producer spans (pre_f0_validation/f0_queue/canonical_f0_active)
    all declare it as their parent. Previously every one of these was
    orphaned and the run recorded ZERO iterate_timings; now 'verification'
    is reconstructed from their envelope and all attach successfully."""
    raw = [
        _span("pre_f0_validation", "verification", "2026-08-05T09:11:09.831448+00:00",
             "2026-08-05T09:11:09.878448+00:00", 47),
        _span("f0_queue", "verification", "2026-08-05T09:11:19.190214+00:00",
             "2026-08-05T09:11:19.205214+00:00", 15),
        _span("canonical_f0_active", "verification", "2026-08-05T09:11:20.199150+00:00",
             "2026-08-05T09:15:32.059392+00:00", 251860),
    ]
    valid, rejected = itn.normalize_iterate_timings(raw)
    assert not rejected
    by_name = {v["name"]: v for v in valid}
    assert set(by_name) == {"verification", "pre_f0_validation", "f0_queue", "canonical_f0_active"}
    verification = by_name["verification"]
    assert verification["source"] == "derived"
    assert verification["parent"] is None
    assert verification["outcome"] == "completed"
    assert verification["start_utc"] == "2026-08-05T09:11:09.831448+00:00"
    assert verification["end_utc"] == "2026-08-05T09:15:32.059392+00:00"
    # every real child still carries its own measured (non-derived) source
    assert all(by_name[n]["source"] == "producer" for n in
              ("pre_f0_validation", "f0_queue", "canonical_f0_active"))


def test_multiple_declared_parents_synthesize_independently(tmp_path):
    """external_review calls declare EITHER 'planning' or 'review' as their
    parent (Step 4 vs Step 8's cascade) — when both are absent, each gets
    its own derived ancestor from only the entries that named it, not one
    merged blob."""
    raw = [
        _span("external_review", "planning", "2026-08-05T08:49:08.493828+00:00",
             "2026-08-05T08:50:19.357904+00:00", 70859, provider="openrouter"),
        _span("external_review", "planning", "2026-08-05T08:51:28.490269+00:00",
             "2026-08-05T08:52:17.208227+00:00", 48718, provider="openrouter"),
        _span("external_review", "review", "2026-08-05T09:08:33.474483+00:00",
             "2026-08-05T09:09:23.644983+00:00", 50172, provider="openrouter"),
    ]
    valid, rejected = itn.normalize_iterate_timings(raw)
    assert not rejected
    by_name_parent = {(v["name"], v["parent"]): v for v in valid}
    planning = by_name_parent[("planning", None)]
    review = by_name_parent[("review", None)]
    assert planning["source"] == "derived" and review["source"] == "derived"
    # planning's envelope covers both its calls; review's covers only its own.
    assert planning["start_utc"] == "2026-08-05T08:49:08.493828+00:00"
    assert planning["end_utc"] == "2026-08-05T08:52:17.208227+00:00"
    assert review["start_utc"] == "2026-08-05T09:08:33.474483+00:00"
    assert review["end_utc"] == "2026-08-05T09:09:23.644983+00:00"


def test_a_real_but_irrelevant_sibling_parent_does_not_suppress_synthesis(tmp_path):
    """Found in review: external_review/reviewer_wait/ci_wait each allow TWO
    parent names (planning-or-review, delivery-or-delivery_wait). A real,
    temporally unrelated record under the SIBLING name (here 'planning',
    long closed before this child even starts) must not suppress synthesis
    of the name the child actually declared ('review', with zero records of
    its own) — that would silently reproduce the original orphaning for any
    run where the agent marked some but not all of the 6 agent-emitted
    top-level groups, exactly the historical norm this fix targets."""
    raw = [
        _span("planning", None, "2026-08-04T08:00:00+00:00",
             "2026-08-04T08:30:00+00:00", 1800000),
        _span("external_review", "review", "2026-08-04T10:00:00+00:00",
             "2026-08-04T10:05:00+00:00", 300000),
    ]
    valid, rejected = itn.normalize_iterate_timings(raw)
    assert not rejected
    by_name_parent = {(v["name"], v["parent"]): v for v in valid}
    review = by_name_parent[("review", None)]
    assert review["source"] == "derived"
    assert review["start_utc"] == "2026-08-04T10:00:00+00:00"
    assert review["end_utc"] == "2026-08-04T10:05:00+00:00"
    ext = by_name_parent[("external_review", "review")]
    assert ext["source"] == "producer"


def test_synthesized_ancestor_is_incomplete_when_a_referencing_child_is_still_open(tmp_path):
    """A derived envelope with an unclosed child has a genuinely unknown
    end — report that honestly as incomplete, never guess a boundary."""
    raw = [
        _span("f0_queue", "verification", "2026-08-04T10:00:00+00:00",
             "2026-08-04T10:00:05+00:00", 5000),
        {**_span("canonical_f0_active", "verification", "2026-08-04T10:00:05+00:00",
                None, None), "outcome": "incomplete"},
    ]
    valid, rejected = itn.normalize_iterate_timings(raw)
    assert not rejected
    verification = next(v for v in valid if v["name"] == "verification")
    assert verification["source"] == "derived"
    assert verification["outcome"] == "incomplete"
    assert verification["end_utc"] is None
    assert verification["duration_ms"] is None


def test_synthesized_ancestor_recurses_when_it_is_itself_nested(tmp_path):
    """Both 'delivery' and 'delivery_wait' are absent — only 'ci_wait'
    exists, declaring 'delivery_wait' as its parent. Synthesis must recurse:
    materialize 'delivery_wait' from ci_wait's envelope, notice THAT is
    itself nested (needs 'delivery'), and materialize 'delivery' too."""
    raw = [
        _span("ci_wait", "delivery_wait", "2026-08-04T10:10:00+00:00",
             "2026-08-04T10:20:00+00:00", 600000),
    ]
    valid, rejected = itn.normalize_iterate_timings(raw)
    assert not rejected
    by_name = {v["name"]: v for v in valid}
    assert set(by_name) == {"ci_wait", "delivery_wait", "delivery"}
    assert by_name["delivery_wait"]["source"] == "derived"
    assert by_name["delivery_wait"]["parent"] == "delivery"
    assert by_name["delivery"]["source"] == "derived"
    assert by_name["delivery"]["parent"] is None
    assert by_name["ci_wait"]["source"] == "producer"
    # both derived ancestors reconstruct to ci_wait's own bounds — nothing
    # to invent when there's only one child in the chain.
    assert by_name["delivery"]["start_utc"] == by_name["ci_wait"]["start_utc"]
    assert by_name["delivery"]["end_utc"] == by_name["ci_wait"]["end_utc"]


def test_real_agent_mark_wins_over_synthesis_even_when_incomplete(tmp_path):
    """A real agent boundary mark, even a still-open one, is a genuine
    (if partial) measurement — it must be used instead of synthesizing a
    derived ancestor around it."""
    raw = [
        {**_span("review", None, "2026-08-04T10:00:00+00:00", None, None),
         "outcome": "incomplete", "source": "agent"},
        _span("code_review", "review", "2026-08-04T10:01:00+00:00",
             "2026-08-04T10:05:00+00:00", 240000),
    ]
    valid, rejected = itn.normalize_iterate_timings(raw)
    assert not rejected
    review = next(v for v in valid if v["name"] == "review")
    assert review["source"] == "agent"
    assert review["outcome"] == "incomplete"
