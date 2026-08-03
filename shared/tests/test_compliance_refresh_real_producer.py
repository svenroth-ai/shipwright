"""The compliance refresh, driven through its REAL producer for once.

Subject: ``shared/scripts/tools/compliance_refresh_produce.converge`` composed with
the real ``regenerate_tracked_snapshots`` → ``finalize_iterate._update_compliance``
→ ``update_compliance.py`` chain.

Its sibling ``test_compliance_refresh_produce.py`` injects ``regenerate`` or stubs
``converge`` in every case, and says so: what is under test there is the LOOP and
the refusals. That left one behaviour named-but-untested in
``iterate-2026-07-31-derived-docs-at-release`` — *"the real
``regenerate_tracked_snapshots`` → ``_update_compliance`` producer is driven
nowhere in this diff"*. Not a theoretical gap: its Stage-3 doubt review found D6
(the compliance config was never rewound, because the append-only prefix guard
cannot apply to a file the producer **rewrites**), invisible for exactly this
reason. This module closes it.

**One real ``converge`` run, module-scoped, shared by every test below.**
~2.3 s measured, three passes shelling out to ``update_compliance.py`` against
its own 30 s timeout — and **per xdist worker**, not per session: the F0 suite
runner gives ``shared/tests`` ``-n 8`` with the default per-test distribution, so
each worker holding one of these cases builds its own fixture (Stage-3 doubt D3).
The ``regenerate`` hook is used to *observe* — a bare pass-through to
``produce_mod.regenerate`` that snapshots the producer's own inputs after each
pass, which is the only moment the mid-run rewrite is visible. It never
substitutes, and ``test_converge_still_defaults_to_the_real_producer`` pins that
the default remains the real chain.

**The run is made hermetic on purpose** (``hermetic_gh_env``): the producer's
subprocess inherits this process's cwd, so on an authenticated machine its
ci-security leg reached the REAL shipwright repository over the network, while CI
— which exports no token — skipped it. Same code, two results. Seeding, that
guard and the fixture preconditions live in ``_real_producer_fixtures``; the one
ambient input still NOT neutralised is a hostile global git config
(``commit.gpgsign``, ``GIT_DIR``), which would fail the seed loudly in
``seed_repo`` rather than skew a result.

**No marker, and both omissions are deliberate.** ``_update_compliance`` reaches
the compliance plugin by path constant and shells out with ``sys.executable``, so
the boundary crossed is a SUBPROCESS, not ``sys.path`` — ADR-044's collision
never arises and ``cross_plugin`` would be a lie. And CI runs ``-m 'not slow and
not cross_plugin'``, so either marker would delete this from the run that matters.
"""

from __future__ import annotations

import inspect
import json
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
# Order matters and the inserts are UNCONDITIONAL — see the note in
# `test_compliance_refresh_produce.py` (ADR-045).
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))

from _compliance_refresh_fixtures import RUN  # noqa: E402
from _real_producer_fixtures import (  # noqa: E402
    CHANGE_HISTORY,
    CHANGE_HISTORY_MARKER,
    COMPLIANCE_CONFIG,
    FAILING_LAYER_DEDUP_KEY,
    FR_IDS,
    MANIFEST,
    RTM,
    SBOM,
    SBOM_MARKER,
    added_records,
    assert_seed_is_sound,
    hermetic_gh_env,
    is_ordered_subsequence,
    read_lines,
    seed_project,
)
from lib.churn_merge import CI_SECURITY_SUMMARY, EVENTS_LOG, TRIAGE_LOG  # noqa: E402
from lib.compliance_refresh import (  # noqa: E402
    REFRESH_SET, SUCCESS_OUTCOMES, TREE_DERIVED,
)
from tools import compliance_refresh_produce as produce_mod  # noqa: E402
from tools.compliance_input_state import PRODUCER_STATE, snapshot  # noqa: E402


@pytest.fixture(scope="module")
def real_run(tmp_path_factory) -> SimpleNamespace:
    """ONE real ``converge`` over a seeded project.

    ``tmp_path_factory`` rather than ``tmp_path``: the fixture is module-scoped,
    and the function-scoped one would be a ``ScopeMismatch``.
    """
    root = seed_project(tmp_path_factory.mktemp("real_producer") / "repo")

    docs_before = {rel: (root / rel).read_bytes() for rel in sorted(REFRESH_SET)}
    per_pass: list[dict[str, bytes | None]] = []

    def recording(*args, **kwargs):
        """A bare pass-through — no argument, return value or exception is
        transformed. It reads the producer's inputs at the one moment the mid-run
        rewrite is observable: after the producer returns, before ``converge``
        rewinds them at the top of the next pass."""
        outcomes = produce_mod.regenerate(*args, **kwargs)
        per_pass.append(snapshot(root, PRODUCER_STATE))
        return outcomes

    # `MonkeyPatch.context()`, not the `monkeypatch` fixture, which is
    # function-scoped. The env must be set BEFORE converge: the producer's
    # subprocess inherits it, and that is the only way to reach the child.
    with pytest.MonkeyPatch.context() as mp:
        hermetic_gh_env(mp, tmp_path_factory.mktemp("gh_config"))
        assert_seed_is_sound(root)
        inputs_before = snapshot(root, PRODUCER_STATE)
        started = time.monotonic()
        reached, passes, outcomes = produce_mod.converge(
            root, RUN, regenerate=recording)
        elapsed = time.monotonic() - started

    return SimpleNamespace(
        root=root, reached=reached, passes=passes, outcomes=outcomes,
        elapsed=elapsed, per_pass=per_pass,
        left_alone=list(getattr(produce_mod.converge, "left_alone", [])),
        docs_before=docs_before,
        docs_after={rel: (root / rel).read_bytes() if (root / rel).is_file() else None
                    for rel in sorted(REFRESH_SET)},
        inputs_before=inputs_before, inputs_after=snapshot(root, PRODUCER_STATE),
    )


# --- the chain runs at all ---------------------------------------------------


def test_the_real_producer_reports_success_for_all_seven(real_run):
    """No leg errored. ``_update_compliance`` swallows a non-zero exit, its own
    30 s timeout and every exception into ``[]``, which becomes an all-``error``
    pass that writes nothing — so the diagnosis is spelled out here rather than
    left to the reader of some downstream failure."""
    assert set(real_run.outcomes) == set(REFRESH_SET)
    bad = {rel: out for rel, out in real_run.outcomes.items()
           if out not in SUCCESS_OUTCOMES}
    assert not bad, (
        f"the real producer leg failed: {bad}. Either `update_compliance.py` "
        f"exceeded its 30 s timeout (this run took {real_run.elapsed:.1f}s over "
        f"{real_run.passes} passes), or the compliance plugin was unreachable "
        f"and `_update_compliance` returned []."
    )


def test_the_real_producer_rewrites_every_tree_derived_document(real_run):
    """The six that are a function of the TREE; ci-security has its own case."""
    # `is None` is kept separate from "unchanged": a DELETED document also
    # compares unequal to its seed, so folding the two together would read a
    # disappearance as a successful rewrite (Stage-1 review, N4).
    missing = [rel for rel in sorted(TREE_DERIVED) if real_run.docs_after[rel] is None]
    assert not missing, f"the producer removed these documents outright: {missing}"
    unchanged = [rel for rel in sorted(TREE_DERIVED)
                 if real_run.docs_after[rel] == real_run.docs_before[rel]]
    assert not unchanged, (
        f"the producer left these seeded documents untouched: {unchanged}"
    )


def test_ci_security_is_left_frozen_when_its_source_is_unreachable(real_run):
    """AC-6's carve-out, driven end to end rather than assumed.

    ``ci-security.json`` is ``DERIVES_FROM_CI_HISTORY``: its only writer is
    ``refresh_ci_security``, gated on an authenticated ``gh``, which the fixture
    removes deliberately. So the leg is ``skipped``, the committed copy stands,
    and — the load-bearing half — the run still reports success and still
    converges. Asserting the opposite ("it changed") is what an earlier draft
    did, and it was green only on a machine with a logged-in ``gh``.
    """
    assert real_run.docs_after[CI_SECURITY_SUMMARY] == \
        real_run.docs_before[CI_SECURITY_SUMMARY]
    assert real_run.outcomes[CI_SECURITY_SUMMARY] in SUCCESS_OUTCOMES


def test_the_regenerated_documents_carry_real_derived_content(real_run):
    """Bytes changing is not content arriving — a well-formed EMPTY document is
    the exact failure ``CONTENT_FLOOR_RATIO`` exists for, and it changes bytes
    too. So each assertion reads back something only the SEED accounts for."""
    rtm = (real_run.root / RTM).read_text(encoding="utf-8")
    assert all(fr in rtm for fr in FR_IDS), "the RTM does not name the seeded FRs"

    history = (real_run.root / CHANGE_HISTORY).read_text(encoding="utf-8")
    assert CHANGE_HISTORY_MARKER in history, (
        "change-history.md does not carry the seeded work_completed event — the "
        "canonical shape of the empty-but-well-formed document the floor guards"
    )
    assert SBOM_MARKER in (real_run.root / SBOM).read_text(encoding="utf-8"), (
        "sbom.md does not carry the seeded dependency"
    )

    manifest = json.loads((real_run.root / MANIFEST).read_text(encoding="utf-8"))
    assert manifest["schema_version"] == 3
    # By ID, not by COUNT: two stale or unrelated nodes would satisfy a count
    # while the RTM independently listed the seeded FRs (external code review).
    assert {n["id"] for n in manifest["requirements"].values()} == set(FR_IDS)
    assert manifest["untagged_tests"] == [], (
        "the seeded @covers tags did not reach the manifest — the fixture would "
        "look like it exercises the tag→FR join without doing so"
    )


# --- the fixpoint ------------------------------------------------------------


def test_the_real_producer_needs_three_passes_to_settle(real_run):
    """The measured shape behind ``converge``'s existence, on a real project.

    ``PHASE_REPORTS["iterate"]`` runs ``rtm`` BEFORE ``test_links``, so pass 2's
    RTM renders its layer-coverage cells from the ``test-traceability.json`` that
    pass 1 wrote: pass 1 ≠ pass 2, pass 2 == pass 3. Neither direction of a
    change here is a flake — see the failure message.
    """
    assert real_run.reached is True
    assert real_run.passes == 3, (
        "expected the rtm←test-traceability ordering coupling to need 3 passes, "
        f"got {real_run.passes}. FEWER: either that ordering was fixed (update "
        "converge()'s docstring) or the SEEDED manifest became readable, which "
        "assert_seed_is_sound should have caught. MORE: a new producer coupling "
        f"was introduced and MAX_PASSES ({produce_mod.MAX_PASSES}) has no "
        "headroom left."
    )
    # Not implied by the line above: it fails if MAX_PASSES is ever lowered to 3,
    # which would leave the measured behaviour sitting exactly on the cap.
    assert real_run.passes < produce_mod.MAX_PASSES, (
        "the real producer has no spare pass left under the cap"
    )


# --- what the run does to the producer's own inputs --------------------------


def test_the_rewritten_config_ends_exactly_where_it_started(real_run):
    """D6, pinned: a whole-file-rewritten input is rewound, unlike an append-only
    log. The mid-pass capture is what makes this non-vacuous — without it a
    producer that never touched the file would pass identically."""
    seeded = real_run.inputs_before[COMPLIANCE_CONFIG]
    rewritten = [state[COMPLIANCE_CONFIG] for state in real_run.per_pass
                 if state[COMPLIANCE_CONFIG] != seeded]
    assert rewritten, "the producer never rewrote the config — the rewind proves nothing"
    assert "iterate" in json.loads(rewritten[0])["phases_covered"], (
        "the mid-run rewrite is not the one this asserts about"
    )
    assert real_run.inputs_after[COMPLIANCE_CONFIG] == seeded


def test_the_append_only_logs_keep_every_line_they_started_with(real_run):
    """Never destroy an appended line — the one outcome the whole rewind rule
    exists to prevent."""
    for rel in (EVENTS_LOG, TRIAGE_LOG):
        before = real_run.inputs_before[rel].decode("utf-8").splitlines()
        assert is_ordered_subsequence(before, read_lines(real_run.root / rel)), (
            f"{rel} lost or reordered a line the run found there"
        )
        # RECORDS, not a line-count delta: the triage store prepends a schema
        # header, so "the file got longer" is also satisfied by a run that
        # appended nothing (Stage-3 doubt D4).
        assert added_records(real_run.inputs_before[rel], real_run.root / rel), (
            f"{rel} gained no record, so its append-only handling was not exercised"
        )


def test_the_inputs_left_alone_are_exactly_the_two_logs_that_moved(real_run):
    """Exactly — a rewritten input surfacing here fails as loudly as a lost log."""
    assert real_run.left_alone == sorted([EVENTS_LOG, TRIAGE_LOG])


def test_the_producers_own_appends_do_not_break_the_fixpoint(real_run):
    """``APPEND_ONLY_INPUTS`` argues that the fixpoint survives its own carve-out:
    unchanged ``grade_snapshot`` events and triage appends carrying a
    ``dedupKey`` both land once and are absorbed from pass 2 on. Both halves are
    driven here rather than reasoned about."""
    added = {rel: added_records(real_run.inputs_before[rel], real_run.root / rel)
             for rel in (EVENTS_LOG, TRIAGE_LOG)}
    grades = [e for e in added[EVENTS_LOG] if e.get("type") == "grade_snapshot"]

    def grade_snapshots(raw: bytes | None) -> list[dict]:
        assert raw is not None
        events = [json.loads(line) for line in raw.decode("utf-8").splitlines()]
        return [event for event in events
                if isinstance(event, dict)
                and event.get("type") == "grade_snapshot"]

    assert grade_snapshots(real_run.inputs_before[EVENTS_LOG]) == []
    per_pass_grades = [grade_snapshots(state[EVENTS_LOG])
                       for state in real_run.per_pass]
    assert per_pass_grades == [grades] * real_run.passes, (
        "the first pass must append one grade_snapshot and unchanged later "
        f"passes must preserve that exact event; observed {per_pass_grades}"
    )
    assert len(grades) == 1, (
        f"the unchanged grade_snapshot landed {len(grades)} times over "
        f"{real_run.passes} passes; it must be absorbed from pass 2 on"
    )
    failures = [t for t in added[TRIAGE_LOG]
                if t.get("dedupKey") == FAILING_LAYER_DEDUP_KEY]
    assert len(failures) == 1, (
        f"the dedupKey'd triage append landed {len(failures)} times over "
        f"{real_run.passes} passes; it must be absorbed from pass 2 on"
    )
    assert real_run.reached is True, "the fixpoint did not survive the moving inputs"


# --- the injection point is observation, not substitution --------------------


def test_converge_still_defaults_to_the_real_producer():
    """The ``regenerate`` hook above observes; it must never become the tested
    path by default (external review, openai/low)."""
    default = inspect.signature(produce_mod.converge).parameters["regenerate"].default
    assert default is produce_mod.regenerate
