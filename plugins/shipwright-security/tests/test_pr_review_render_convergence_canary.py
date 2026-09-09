"""Drift canary for `shared/scripts/lib/pr_review_convergence.py` (trg-ac24ec5b).

That module lives in a different plugin/pytest root (ADR-044 blocks a direct
cross-root import) and matches this renderer's output on FOUR hard-coded
literals/shapes — the `Shipwright PR Review` marker, the `🔴 BLOCK` badge, the
`Blocking issues` heading, and the `- {bullet}` list-item form
`extract_blocking_findings`'s `_BULLET_RE` parses. A silent format change to
any of the four would make the non-converging-halt predicate fail open
forever, with no other test to catch it (code-reviewer, Stage 2 — the
original canary pinned only the first three). Split into its own file
(rather than folded into `test_pr_review_render.py`) to keep that file under
the source-size guideline while this one-test canary stays easy to find from
either side.
"""

from __future__ import annotations

import sys
from pathlib import Path

PLUGIN_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PLUGIN_ROOT / "scripts" / "lib"))

import pr_review_lib as L  # noqa: E402


def test_block_verdict_marker_and_heading_are_the_literals_convergence_depends_on():
    body = L.render_comment(
        {"decision": "block", "summary": "s", "blocking": ["a.py:1 — x"], "comments": []},
        model="m", truncated=False)
    assert "Shipwright PR Review" in body
    assert "🔴 BLOCK" in body
    assert "Blocking issues" in body
    assert "\n- a.py:1 — x" in body  # the `- {bullet}` shape _BULLET_RE parses
