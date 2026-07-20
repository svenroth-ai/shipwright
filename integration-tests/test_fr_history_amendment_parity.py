"""Parity: the S7 query folds amendments exactly like the compliance collector.

``lib/_fr_history_events.apply_amendments`` and
``plugins/shipwright-compliance/.../collectors/change_history._apply_amendments``
are intentionally separate implementations — the compliance plugin is a
standalone distributable that cannot import ``shared/scripts/lib`` without a
cross-plugin path bootstrap (the same split ``test_events_log_parity.py``
guards for the log's location).

They must nevertheless agree. The RTM and the ``fr_history`` CLI both answer
"what happened to this requirement" from the same log; if one honoured an
amendment the other ignored, the two artifacts would report different histories
for the same requirement and neither would be wrong on its own terms. That is
precisely the class of divergence this campaign was called to end.

This test exists because ``apply_amendments``' docstring claims the parity. A
docstring asserting an invariant that nothing checks is how the previous
sub-iterate shipped four defects.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO / "shared" / "scripts"))

from lib._fr_history_events import apply_amendments  # noqa: E402

_COMPLIANCE_SCRIPTS = _REPO / "plugins" / "shipwright-compliance" / "scripts"

# Isolation is by SUBPROCESS, one import realm per process — the discipline the
# S1 golden corpus established. ``lib`` is an ambiguous top-level name: putting
# the compliance plugin's ``scripts`` on this process's sys.path would bind
# ``sys.modules['lib']`` to the compliance package and shadow shared's for every
# later test in the session (ADR-044/045). Loading the collector by file path
# instead does not work either — it uses relative imports and has no parent
# package that way, which is what made a first version of this test skip
# silently in all seven cases. A separate process is the only form that both
# runs and stays clean.
_CHILD = r"""
import json, sys
sys.path.insert(0, sys.argv[1])
from lib.collectors.change_history import _apply_amendments
print(json.dumps(_apply_amendments(json.loads(sys.argv[2]))))
"""


def _compliance_apply(events: list[dict]) -> list[dict]:
    if not (_COMPLIANCE_SCRIPTS / "lib" / "collectors" / "change_history.py").is_file():
        pytest.fail(
            f"compliance collector missing under {_COMPLIANCE_SCRIPTS}; the "
            f"parity this module asserts cannot be checked, and skipping would "
            f"report a green that means nothing."
        )
    proc = subprocess.run(
        [sys.executable, "-c", _CHILD, str(_COMPLIANCE_SCRIPTS), json.dumps(events)],
        capture_output=True, text=True, encoding="utf-8",
    )
    assert proc.returncode == 0, (
        f"could not run the compliance collector for comparison: {proc.stderr}"
    )
    return json.loads(proc.stdout)


def _work(**kw) -> dict:
    base = {"type": "work_completed", "id": kw.pop("id", "evt-1"),
            "ts": "2026-01-01T00:00:00+00:00"}
    base.update(kw)
    return base


CASES = {
    "adds an fr link": [
        _work(id="evt-1", affected_frs=[]),
        {"type": "event_amended", "amends": "evt-1",
         "fields": {"affected_frs": ["FR-01.01"]}},
    ],
    "removes an fr link": [
        _work(id="evt-1", affected_frs=["FR-01.01"]),
        {"type": "event_amended", "amends": "evt-1", "fields": {"affected_frs": []}},
    ],
    "rewrites a summary": [
        _work(id="evt-1", summary="before"),
        {"type": "event_amended", "amends": "evt-1", "fields": {"summary": "after"}},
    ],
    "amends an event that does not exist": [
        _work(id="evt-1", affected_frs=["FR-01.01"]),
        {"type": "event_amended", "amends": "evt-missing",
         "fields": {"affected_frs": []}},
    ],
    "two amendments to one event": [
        _work(id="evt-1", affected_frs=["FR-01.01"]),
        {"type": "event_amended", "amends": "evt-1", "fields": {"summary": "one"}},
        {"type": "event_amended", "amends": "evt-1", "fields": {"summary": "two"}},
    ],
    "amendment carrying no fields": [
        _work(id="evt-1", affected_frs=["FR-01.01"]),
        {"type": "event_amended", "amends": "evt-1"},
    ],
    "no amendments at all": [
        _work(id="evt-1", affected_frs=["FR-01.01"]),
        _work(id="evt-2", affected_frs=["FR-01.02"]),
    ],
}


@pytest.mark.parametrize("name", sorted(CASES))
def test_both_implementations_fold_amendments_identically(name):
    events = CASES[name]
    ours = apply_amendments([dict(e) for e in events])
    theirs = _compliance_apply([dict(e) for e in events])
    assert ours == theirs, (
        f"the S7 query and the compliance collector disagree on '{name}'; the "
        f"RTM and fr_history would report different histories for one requirement."
        f"\n  ours:   {ours}\n  theirs: {theirs}"
    )


def test_the_comparison_actually_ran_the_compliance_implementation():
    """Guard against this module going vacuous.

    Its first version skipped all seven cases because the collector could not be
    imported the way it tried — a green suite asserting nothing. If the child
    process ever stops producing a real answer, this fails loudly instead.
    """
    result = _compliance_apply([
        {"type": "work_completed", "id": "evt-1", "affected_frs": []},
        {"type": "event_amended", "amends": "evt-1",
         "fields": {"affected_frs": ["FR-01.01"]}},
    ])
    assert result == [
        {"type": "work_completed", "id": "evt-1", "affected_frs": ["FR-01.01"]}
    ], "the compliance collector did not fold a known amendment; comparison is moot"
