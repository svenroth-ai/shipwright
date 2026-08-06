"""GC membership by CANONICAL FORM — audit findings 14 and 27.

Both findings are one defect seen from two sides. ``is_delivered`` used to ask two
different questions: an ``append`` was delivered **iff its id was in origin** (content
ignored → F14: a refreshed record is GC'd from the outbox although only the OLD version
reached origin, and the outbox is gitignored, so the new content exists nowhere), while
every other line was delivered **iff its raw text was in origin** (→ F27: any
re-serialization makes a status line permanently un-GC-able, so the buffer grows with no
bound and no signal).

Canonical-form membership answers both with one rule and keeps FIX B's original goal —
immunity to key-order / whitespace re-serialization — which is what the FIX B docstring
always claimed and its fixtures never actually exercised (see
``test_sweep_outbox_review_cascade.py``).

F14's premise is not hypothetical: ``.shipwright/triage.jsonl`` line 285 (``trg-60ef91fb``)
carries a ``ts`` ending ``+00:00``, which ``triage._now_z()`` can never emit because it
always ``.replace("+00:00", "Z")``. A foreign producer re-serializes same-id records.

Pure membership units, then REAL-git end-to-end coverage through
``sweep_outbox_to_branch`` — the behaviour at risk is the sweep's decision under
its canonical lock, not the pure helper (external plan review, openai finding 3).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_SHARED_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))
sys.path.insert(0, str(Path(__file__).resolve().parent))  # for _sweep_helpers

import _sweep_helpers as h  # noqa: E402
from lib import sweep_canon, sweep_gc  # noqa: E402
from lib.sweep_outbox import sweep_outbox_to_branch  # noqa: E402


# --------------------------------------------------------------------------
# Helper units
# --------------------------------------------------------------------------

def test_same_id_changed_content_survives() -> None:
    """AC-1 (F14): same id, DIFFERENT content → not delivered → survives the GC."""
    origin_line = h.item("trg-1", title="original")
    canonical, text = sweep_gc.parse_delivered({origin_line})
    refreshed = h.item("trg-1", title="REFRESHED")
    assert sweep_gc.is_delivered(refreshed, delivered_canonical=canonical, delivered_text=text) is False


def test_reserialized_append_is_delivered() -> None:
    """AC-3: FIX B's real goal — key order / whitespace immunity — still holds."""
    origin_line = h.item("trg-1")
    canonical, text = sweep_gc.parse_delivered({origin_line})
    assert sweep_gc.is_delivered(h.reserialize(origin_line), delivered_canonical=canonical, delivered_text=text) is True


def test_reserialized_status_line_is_delivered() -> None:
    """AC-2 (F27): a status line re-serialized differently is now GC-able."""
    origin_status = h.status("trg-1")
    canonical, text = sweep_gc.parse_delivered({origin_status})
    assert sweep_gc.is_delivered(h.reserialize(origin_status), delivered_canonical=canonical, delivered_text=text) is True


def test_undelivered_id_survives() -> None:
    """Fail-safe: an id origin never saw is never dropped."""
    canonical, text = sweep_gc.parse_delivered({h.item("trg-1")})
    assert sweep_gc.is_delivered(h.item("trg-9"), delivered_canonical=canonical, delivered_text=text) is False


def test_unparseable_line_keeps_text_membership() -> None:
    """An unparseable line has no canonical form, so raw text stays its anchor."""
    canonical, text = sweep_gc.parse_delivered({"garbage-not-json", h.item("trg-1")})
    assert sweep_gc.is_delivered("garbage-not-json", delivered_canonical=canonical, delivered_text=text) is True
    assert sweep_gc.is_delivered("other-garbage", delivered_canonical=canonical, delivered_text=text) is False


def test_bare_scalar_routes_through_text_path() -> None:
    """Valid JSON, wrong shape: a scalar is not a record — text path, as before."""
    canonical, text = sweep_gc.parse_delivered({"3", '"a string"'})
    assert "3" in text and '"a string"' in text
    assert canonical == set()
    assert sweep_gc.is_delivered("3", delivered_canonical=canonical, delivered_text=text) is True
    assert sweep_gc.is_delivered("4", delivered_canonical=canonical, delivered_text=text) is False


def test_duplicate_keys_do_not_cross_match() -> None:
    """External plan review, openai finding 1 (high).

    ``json.loads`` keeps only the LAST duplicate key, so a duplicate-key document
    would otherwise canonicalize identically to a materially different single-key
    one and be dropped — exactly the loss AC-1 exists to prevent. A duplicate-key
    line is therefore NOT canonicalizable and falls back to raw-text membership.
    """
    dup = '{"event":"append","id":"trg-1","ts":"T1","ts":"T2"}'
    single = '{"event":"append","id":"trg-1","ts":"T2"}'
    canonical, text = sweep_gc.parse_delivered({single})
    assert sweep_gc.is_delivered(dup, delivered_canonical=canonical, delivered_text=text) is False
    # ...and symmetrically, origin carrying the duplicate does not deliver the single.
    canonical2, text2 = sweep_gc.parse_delivered({dup})
    assert sweep_gc.is_delivered(single, delivered_canonical=canonical2, delivered_text=text2) is False
    # The duplicate-key line is still deliverable by exact text.
    assert sweep_gc.is_delivered(dup, delivered_canonical=canonical2, delivered_text=text2) is True


@pytest.mark.parametrize(
    "a, b",
    [
        ('{"n":1e400}', '{"n":1e999}'),    # overflow: both parse to inf
        ('{"n":1e-400}', '{"n":0.0}'),     # underflow: both parse to 0.0
        ('{"n":1.0}', '{"n":1.0000000000000000001}'),  # rounding: same double
        ('{"n":NaN}', '{"n":Infinity}'),   # non-standard constants
    ],
)
def test_float_literals_never_cross_match(a: str, b: str) -> None:
    """Floats are excluded from the equivalence class entirely — Stage-3 doubt review.

    Binary floats are many-to-one from source text and every collision lands in the
    DROP direction. A first fix closed only the overflow tail (``allow_nan=False``)
    and left underflow and rounding open; the earlier test sampled the boundary only
    where it happened to be safe and then asserted the general property — the same
    failure mode as the FIX B fixture this run exists to correct.

    Each pair below parses to the SAME Python value, so canonicalizing either would
    make them interchangeable. Rejecting the float type means neither gets a
    canonical form, so both fall back to exact raw-text membership.
    """
    assert sweep_canon.canonical_form(a) is None
    assert sweep_canon.canonical_form(b) is None
    canonical, text = sweep_gc.parse_delivered({a})
    assert sweep_gc.is_delivered(b, delivered_canonical=canonical, delivered_text=text) is False  # no cross-match
    assert sweep_gc.is_delivered(a, delivered_canonical=canonical, delivered_text=text) is True   # exact text still works


def test_integers_remain_canonicalizable() -> None:
    """Only FLOAT literals are rejected — integers are exact and stay in the class."""
    canonical, text = sweep_gc.parse_delivered({'{"a":1,"n":2}'})
    assert canonical == {'{"a":1,"n":2}'}
    assert sweep_gc.is_delivered(
        '{ "n":2, "a":1 }', delivered_canonical=canonical, delivered_text=text) is True


def test_unicode_escaping_is_inside_the_equivalence_boundary() -> None:
    """Escaped vs literal non-ASCII is the same record."""
    canonical, text = sweep_gc.parse_delivered({'{"t":"caf\\u00e9"}'})
    assert sweep_gc.is_delivered('{"t":"café"}', delivered_canonical=canonical, delivered_text=text) is True


def test_empty_origin_delivers_nothing() -> None:
    """Fail-safe preserved: unreadable/missing origin → every line survives."""
    canonical, text = sweep_gc.parse_delivered(set())
    assert (canonical, text) == (set(), set())
    assert sweep_gc.is_delivered(h.item("trg-1"), delivered_canonical=canonical, delivered_text=text) is False
    assert sweep_gc.is_delivered("garbage", delivered_canonical=canonical, delivered_text=text) is False


def test_non_dict_json_routes_to_text_membership() -> None:
    """A JSON array is valid JSON but not a record — text path, like a scalar.

    This was previously mis-labelled as the recursion test. It never reached the
    encoder at all, because ``canonical_form`` returns ``None`` on any non-dict
    before ``json.dumps`` runs (Stage-2 code review).
    """
    arr = "[" * 400 + "]" * 400
    canonical, text = sweep_gc.parse_delivered({arr})
    assert canonical == set() and arr in text
    assert sweep_gc.is_delivered(arr, delivered_canonical=canonical, delivered_text=text) is True
    assert sweep_gc.is_delivered("[" * 400 + "]" * 399, delivered_canonical=canonical, delivered_text=text) is False


def test_unparseably_deep_object_degrades_instead_of_raising() -> None:
    """The CANONICALIZATION LEAF is total — degrade to text membership, never raise.

    The input is a nested OBJECT deep enough to actually defeat the parser
    (``RecursionError`` out of ``json.loads``), so this genuinely exercises the
    handler rather than short-circuiting on the non-dict guard.

    **Scope, deliberately narrow (Stage-3 review).** This pins ``sweep_canon`` ONLY.
    It is NOT end-to-end survivability of that input: ``churn_merge._append_id``
    catches only ``(JSONDecodeError, ValueError)``, so the same line still raises
    ``RecursionError`` out of ``dedup_triage_lines`` — inside the lock, on the
    ``setup_iterate_worktree`` step-5 path — before the GC is ever reached. That gap
    is pre-existing and is carried by card ``trg-ed774f03`` (P2.19g). Reading this
    green test as "the sweep survives deep nesting" would be exactly wrong.
    """
    deep = '{"a":' * 20000 + "1" + "}" * 20000
    with pytest.raises(RecursionError):  # precondition: the parser really does fail
        json.loads(deep)

    assert sweep_canon.canonical_form(deep) is None  # ...and we absorb it
    canonical, text = sweep_gc.parse_delivered({deep})
    assert sweep_gc.is_delivered(deep, delivered_canonical=canonical, delivered_text=text) is True
    assert sweep_gc.is_delivered('{"a":1}', delivered_canonical=canonical, delivered_text=text) is False


# --------------------------------------------------------------------------
# REAL-git end-to-end through the sweep
# --------------------------------------------------------------------------

@pytest.fixture
def repo(git_origin_repo):
    work, origin = git_origin_repo
    h.set_identity(work)
    return work, origin


def test_e2e_same_id_changed_append_stays_in_outbox(repo) -> None:
    """AC-1 end-to-end: the refreshed version must NOT be GC'd while only the
    original is in origin.

    **Precise loss condition** (Stage-3 doubt review D4): the sweep commits the
    refreshed line onto the iterate BRANCH before the GC runs, so under the id-only
    rule the content was not 'nowhere' — it was on a branch and nowhere else. Real
    loss therefore required that branch to be abandoned or reset before merging,
    which is a routine outcome (this repo carries dozens of stale iterate branches),
    but it is a weaker claim than 'destroyed outright'. The assertion below pins
    where the content actually is at the moment of the drop decision, so the test
    can no longer be read as proving more than it does."""
    work, _ = repo
    h.seed_tracked(work, h.item("trg-1", title="original"))
    refreshed = h.item("trg-1", title="REFRESHED")
    h.write_outbox(work, refreshed)
    wt = h.make_worktree(work, "canon-changed")

    result = sweep_outbox_to_branch(work, wt, default_branch="main")

    assert result.gc_dropped == 0, result.to_dict()
    assert refreshed in h.outbox_lines(work), "refreshed content was destroyed"
    # It is ALSO on the branch — the branch is the copy the old rule relied on.
    assert refreshed in h.branch_triage_lines(wt)


def test_e2e_reserialized_status_line_is_gcd(repo) -> None:
    """AC-2 end-to-end: origin holds the status line in one serialization, the
    outbox in another — the GC may now drop it instead of buffering it forever."""
    work, _ = repo
    origin_status = h.status("trg-1")
    h.seed_tracked(work, h.item("trg-1"), origin_status)
    h.write_outbox(work, h.reserialize(origin_status))
    wt = h.make_worktree(work, "canon-status")

    result = sweep_outbox_to_branch(work, wt, default_branch="main")

    assert result.gc_dropped == 1, result.to_dict()
    assert not h.outbox_lines(work), h.outbox_lines(work)
