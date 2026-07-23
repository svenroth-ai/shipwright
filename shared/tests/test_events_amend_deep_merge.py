"""iterate-2026-07-23-tests-skipped-tracking — opt-in deep-merge for
``events_amend.apply_amendments``.

An ``event_amended`` carrying ``fields.tests`` used to REPLACE the whole prior
``tests`` block under the shallow merge, silently dropping siblings such as
``tests.e2e_run`` (which the test-evidence layer classifier reads). ``deep=True``
merges nested dicts recursively; the default stays shallow so every existing
caller (config.py re-export, group_d, the change-history collector) is unchanged.
"""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SHARED_SCRIPTS = _REPO_ROOT / "shared" / "scripts"
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))

from lib.events_amend import apply_amendments  # noqa: E402


def _log(tests_overlay: dict) -> list[dict]:
    return [
        {"id": "e1", "type": "work_completed", "source": "iterate",
         "ts": "2026-07-23T00:00:00Z", "affected_frs": ["FR-01.10"],
         "tests": {"passed": 8, "total": 10, "e2e_run": True}},
        {"type": "event_amended", "amends": "e1", "fields": {"tests": tests_overlay}},
    ]


def test_shallow_default_replaces_whole_tests_block():
    """Default (deep=False) is the historical shallow merge — the sharp edge
    the write-surface warning documents: the sibling e2e_run is dropped."""
    [folded] = apply_amendments(_log({"passed": 10, "total": 10}))
    assert folded["tests"] == {"passed": 10, "total": 10}
    assert "e2e_run" not in folded["tests"]


def test_deep_merge_preserves_untouched_siblings():
    """deep=True keeps e2e_run while correcting passed."""
    [folded] = apply_amendments(_log({"passed": 10}), deep=True)
    assert folded["tests"] == {"passed": 10, "total": 10, "e2e_run": True}


def test_deep_merge_can_add_a_sibling_key():
    """A skipped correction folds in without dropping the rest of the block."""
    [folded] = apply_amendments(_log({"skipped": 2}), deep=True)
    assert folded["tests"] == {"passed": 8, "total": 10, "e2e_run": True, "skipped": 2}


def test_deep_merge_leaves_top_level_scalars_replacing():
    """Only dict values merge recursively; a scalar overlay still replaces."""
    events = [
        {"id": "e1", "type": "work_completed", "commit": "old",
         "tests": {"passed": 1, "total": 1}},
        {"type": "event_amended", "amends": "e1", "fields": {"commit": "new"}},
    ]
    [folded] = apply_amendments(events, deep=True)
    assert folded["commit"] == "new"
    assert folded["tests"] == {"passed": 1, "total": 1}


def test_deep_merge_does_not_mutate_inputs():
    """The original event dicts are untouched (a new dict is returned)."""
    events = _log({"passed": 10})
    original_tests = dict(events[0]["tests"])
    apply_amendments(events, deep=True)
    assert events[0]["tests"] == original_tests
