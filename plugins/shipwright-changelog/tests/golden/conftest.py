"""Fixtures and constants of the changelog golden-trace tests (harness: ``shared/testkit``).

Scenarios (unit P2b) and the promise tests (P2p) get a scratch project here and drive it
through the per-step driver interface of ``golden_trace`` - never through a module path or a
``SKILL.md`` block. The replay driver (today's prose) and, later, the CLI driver implement it.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[4]
GOLDEN_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO_ROOT / "shared" / "testkit"))

import release_scratch  # noqa: E402

# The steps of today's release flow, in prose order. A driver implements a subset; the replay
# driver all of them, a CLI driver the steps it moved (P3: prepare, aggregate; P4: sync,
# commit-and-tag, record-event, close-phase), through ``golden_trace.CompositeDriver``.
STEPS = (
    "prepare",         # A-D, Step 0-3: banner, mode, setup script, history, commit types, version
    "aggregate",       # Step 4: render the section from the drops, number the ADRs
    "preview",         # Step 5: preview, accept, cancel or edit
    "fold-events",     # Step 5.3
    "sync",            # Step 5.4: published package manifests
    "evidence",        # Step 5.5: the compliance evidence documents
    "commit-and-tag",  # Step 6
    "open-pr",         # Step 7: the release pull request
    "record-event",    # Step 7: the changelog event, before the merge
    "merge-pr",        # Step 7: autonomous and unattended only
    "push-tags",       # Step 7
    "release-page",    # Step 7: best-effort release page
    "close-phase",     # the phase-complete block
)

LOCK_PATH = GOLDEN_DIR / "golden.lock.json"
DELTAS_PATH = GOLDEN_DIR / "approved_deltas.json"


@pytest.fixture(params=["legacy", "drops"])
def events_layout(request) -> str:
    """Scenarios pin the event layout and run under both (brief, start condition 3)."""
    return request.param


@pytest.fixture
def make_scratch(tmp_path):
    """``make_scratch(tagged=True, default_branch="main", events_layout=None)`` -> a new scratch project."""
    count = 0

    def build(**kwargs):
        nonlocal count
        count += 1
        return release_scratch.build_scratch(tmp_path / f"scratch{count}", **kwargs)

    return build


@pytest.fixture
def scratch(make_scratch):
    return make_scratch()
