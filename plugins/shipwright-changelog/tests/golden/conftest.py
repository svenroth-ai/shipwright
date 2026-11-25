"""Fixtures and constants of the changelog golden-trace tests (harness: ``shared/testkit``).

Scenarios (unit P2b) and the promise tests (P2p) get a scratch project here and drive it
through the per-step driver interface of ``golden_trace`` - never through a module path or a
``SKILL.md`` block. The replay driver (today's prose) and, later, the CLI driver implement it.
"""

from __future__ import annotations

import os
import subprocess
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
    "aggregate",       # Step 4 (the dry run) and Step 5 (the real run after Accept, P8a F2): render the section, number the ADRs
    "preview",         # Step 5: the dry run's result, accept, cancel or edit
    "fold-events",     # Step 5.3
    "sync",            # Step 5.4: published package manifests
    "evidence",        # Step 5.5: the compliance evidence documents
    "commit-and-tag",  # Step 6
    "push-branch",     # Step 7: the head is pushed right before the PR is opened (P8a F3, D7)
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


_DEAD_PROXY = "http://127.0.0.1:9"


def _provision_uv(tmp: Path) -> str | None:
    """One online resolve fills uv's cache; the scenarios then run with ``UV_OFFLINE=1`` (as ``test_release_offline_proof``)."""
    probes = (["uv", "run", "--with", "pyyaml", "python", "-c", "import yaml"],
              ["uv", "run", str(REPO_ROOT / "shared" / "scripts" / "tools" / "publish_release_notes.py"), "--help"])
    env = {k: v for k, v in os.environ.items() if k != "UV_OFFLINE"}
    for cmd in probes:
        try:
            done = subprocess.run(cmd, env=env, cwd=str(tmp), capture_output=True, text=True, timeout=300)
        except (OSError, subprocess.TimeoutExpired) as exc:
            return f"{cmd[:3]}: {exc}"
        if done.returncode != 0:
            return f"{' '.join(cmd[:4])}: {done.stderr.strip()[-200:]}"
    return None


@pytest.fixture(scope="session")
def warm_uv(tmp_path_factory) -> None:
    problem = _provision_uv(tmp_path_factory.mktemp("uvwarm"))
    if problem:
        if os.environ.get("CI", "").lower() in ("true", "1"):
            raise AssertionError(f"the scenarios need uv's cache warm: {problem}")  # never a silent skip in CI
        pytest.skip(f"uv could not provision the scenario dependencies: {problem}")


@pytest.fixture
def make_project(make_scratch, warm_uv):
    """``make_project(tagged=True, default_branch="main", events_layout="drops")``: a scaffolded scratch project.

    The scenario environment adds ``UV_OFFLINE=1`` and a dead proxy (nothing may reach the network) and the
    condensation fixture model (``ok``), which ``create_github_release`` only accepts together with the ``gh`` seam.
    """
    from . import scenario_support as support

    def build(events_layout: str = "drops", **kwargs):
        scratch = make_scratch(events_layout=events_layout, **kwargs)
        scratch.env.update(UV_OFFLINE="1", HTTP_PROXY=_DEAD_PROXY, HTTPS_PROXY=_DEAD_PROXY, http_proxy=_DEAD_PROXY,
                           https_proxy=_DEAD_PROXY, SHIPWRIGHT_TEST_CONDENSE_FIXTURE_MODEL="ok")
        support.scaffold(scratch)
        return scratch

    return build
