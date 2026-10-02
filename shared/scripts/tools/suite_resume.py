#!/usr/bin/env python3
"""F0 cross-invocation resume - decide what a re-run after a fix can skip, and run the rest.

A unit that was red last time is re-run on its red tests only (`--lf` against the saved
`lastfailed`) and merged into the saved report; a unit that was green is not re-run at all.
`suite_resume_state` owns what is persisted and when it is refused; `suite_resume_cov`
owns the coverage restore. This module owns the per-unit decision and its execution.

OPERATOR DECISION 2026-10-02 (binding, not reopened in review): a resume is allowed even
when the fix changed NON-test source files. CI runs the full suite on every PR, so a
regression sitting in a reused result surfaces as a red CI run, never on `main`. The
residual risk is therefore accepted by the operator and disclosed on every resumed run
(`render_block`); it is not a scope cut.

What is NEVER traded away: a unit runs IN FULL whenever the saved state does not provably
describe it (no state, torn state, test files added/removed/renamed, rc 5 / short re-run /
unmergeable report, no trustworthy red ids, no coverage data), and a resumed result is
marked as such in the console, the retained manifest and the staged evidence - never
presented as a full green run.

ASCII-only operator strings (a cp1252 console raises UnicodeEncodeError, #244).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess  # nosec B404 - fixed argv, shell=False
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.tools.suite_failed_only import (  # noqa: E402
    LASTFAILED, failed_only_args, failed_only_count, merge_junit, read_lastfailed,
    same_tests, testcase_count,
)
from scripts.tools.suite_resume_cov import restore_coverage  # noqa: E402
from scripts.tools.suite_resume_state import (  # noqa: E402
    BASE_REF, MAX_REUSES, TreeSnapshot, changed_files, clear_state, load_state,
    save_state, tree_snapshot, unit_signature, unit_test_files,
)
from scripts.tools.suite_retry import FAILED_ONLY_MAX_TESTS  # noqa: E402
from scripts.tools.suite_units import INFRA, PASS, TEST_FAILURE  # noqa: E402

REUSE_GREEN = "reused-green"
FAILED_ONLY = "failed-only"
#: `SHIPWRIGHT_F0_RESUME=0` turns the whole feature off for one invocation
ENV_OFF = "SHIPWRIGHT_F0_RESUME"


@dataclass(frozen=True)
class ResumePlan:
    unit_id: str
    mode: str
    report: Path           # the saved final JUnit of this unit
    cov: Path | None       # the saved coverage data (None: unit is not instrumented)
    red_ids: tuple[str, ...]
    reuses: int


@dataclass(frozen=True)
class ResumeOps:
    """The runner's seams, handed in so this module never imports the runner."""

    exec_fn: Callable[..., tuple]
    clear_cov_fn: Callable[..., None]
    classify_fn: Callable[..., str]


@dataclass
class ResumeContext:
    """One invocation's view of the resume: the plans, and the honest account of them."""

    invocation: str = ""
    snapshot: TreeSnapshot | None = None
    plans: dict[str, ResumePlan] = field(default_factory=dict)
    chain: tuple[str, ...] = ()
    changed: list[str] = field(default_factory=list)
    overall: str = ""                       # why no resume at all (empty: state was used)
    notes: dict[str, str] = field(default_factory=dict)   # unit -> why it ran in full
    used: set[str] = field(default_factory=set)           # units actually served by it
    reran: dict[str, list[str]] = field(default_factory=dict)
    fallback: str | None = None             # set on the full re-run after a gate refusal

    @property
    def active(self) -> bool:
        return bool(self.used)

    def label(self, unit_id: str) -> str | None:
        if unit_id in self.used:
            return self.plans[unit_id].mode
        return f"full run ({self.notes[unit_id]})" if unit_id in self.notes else None


def _plan_unit(unit, state, snapshot: TreeSnapshot) -> ResumePlan | str:
    rec = state.manifest["units"].get(unit.id)
    if rec is None:
        return "no saved result for this unit"
    if rec["sig"] != unit_signature(unit, snapshot):
        return "the unit's definition changed"
    if rec["reuses"] >= MAX_REUSES:
        return f"its saved result was already reused {rec['reuses']} times"
    if rec["test_files"] != unit_test_files(snapshot, unit):
        return "test files were added, removed, renamed or edited"
    if rec["outcome"] not in (PASS, TEST_FAILURE) or not rec["report"]:
        return "the prior attempt left no usable report"
    report = state.directory / rec["report"]
    cov = state.directory / rec["cov"] if rec["cov"] else None
    if not report.is_file() or (unit.cov_file and (cov is None or not cov.is_file())):
        return "no saved report or coverage data"
    ids = tuple(rec["lastfailed"] or ())
    if rec["outcome"] == PASS:
        return ResumePlan(unit.id, REUSE_GREEN, report, cov, (), rec["reuses"])
    if not 0 < len(ids) <= FAILED_ONLY_MAX_TESTS:
        return "the red test ids are not trustworthy"
    return ResumePlan(unit.id, FAILED_ONLY, report, cov, ids, rec["reuses"])


def prepare_resume(project_root: Path, units, run_id: str | None, *, enabled: bool = True,
                   fallback: str | None = None, runner=subprocess.run,
                   base_ref: str = BASE_REF) -> ResumeContext:
    """Snapshot the tree, load the saved state and plan every unit. Never raises: any
    doubt is a unit (or the whole run) that simply runs in full."""
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    ctx = ResumeContext(invocation=f"{run_id or 'f0'}@{stamp}", fallback=fallback)
    root = Path(project_root).resolve()
    try:
        ctx.snapshot = tree_snapshot(root, runner, base_ref)
        if os.environ.get(ENV_OFF) == "0" or not enabled:
            ctx.overall = fallback or f"resume is switched off ({ENV_OFF}=0)"
        elif ctx.snapshot is None:
            ctx.overall = ("the tree could not be snapshotted (not a git checkout, or no "
                           f"merge base with {base_ref})")
        else:
            _plan_all(ctx, root, units, ctx.snapshot, run_id)
    except Exception as exc:  # noqa: BLE001 - the resume is an optimisation, never a gate
        ctx.plans.clear()
        ctx.overall = f"resume failed closed: {type(exc).__name__}: {exc}"
    return ctx


def _plan_all(ctx: ResumeContext, root: Path, units, snapshot: TreeSnapshot,
              run_id: str | None = None) -> None:
    state, why = load_state(root)
    if state is None:
        ctx.overall = why
        return
    if state.manifest["base_sha"] != snapshot.base_sha:
        ctx.overall = "the merge base with origin/main moved since the saved run"
        return
    if run_id and state.manifest.get("run_id") != run_id:
        ctx.overall = "the saved state belongs to another run"  # never a foreign change's token
        return
    ctx.chain = (*state.manifest["chain"], state.manifest["invocation"])
    ctx.changed = changed_files(state.tree, snapshot.files)
    for unit in units:
        plan = _plan_unit(unit, state, snapshot)
        if isinstance(plan, str):
            ctx.notes[unit.id] = plan
        elif unit.cov_file and not restore_coverage(
                plan.cov, Path(unit.cov_file), unit, root, state.tree, snapshot.files):
            ctx.notes[unit.id] = "its saved coverage data could not be restored"
        else:
            ctx.plans[unit.id] = plan


def try_resume(ctx: ResumeContext, unit, project_root: Path, attempt_dir: Path,
               ops: ResumeOps, *, timeout: int | None, cancel_event) -> tuple | None:
    """The unit's first attempt, served from the saved state; None = run it in full.

    Returns `_exec`'s 6-tuple. The report left at `attempt_dir/r.xml` is always the
    unit's WHOLE report (saved one with the red tests replaced), so everything downstream
    - the whole-unit total, the retention copy, a further failed-only retry - treats it
    as the ordinary first attempt it stands in for.
    """
    plan = ctx.plans.get(unit.id)
    if plan is None:
        return None
    attempt_dir.mkdir(parents=True, exist_ok=True)
    report = attempt_dir / "r.xml"
    if plan.mode == REUSE_GREEN:
        shutil.copyfile(plan.report, report)
        ctx.used.add(unit.id)
        return 0, "resumed: the prior run's green result was reused", 0.0, True, False, False
    cache = attempt_dir / "c"
    (cache / LASTFAILED).parent.mkdir(parents=True, exist_ok=True)
    (cache / LASTFAILED).write_text(json.dumps({i: True for i in plan.red_ids}),
                                    encoding="utf-8")
    got = ops.exec_fn(unit, project_root, None, attempt_dir, timeout, cancel_event,
                      cache_dir=cache, extra_args=failed_only_args(unit))
    rc, ran, cancelled = got[0], got[3], got[5]
    merged = attempt_dir / "merged.xml"
    # Same trust rule as the in-run narrow retry: pytest must have re-run EXACTLY the red
    # tests (fewer = a vanished id, more = `--lf` matched nothing and ran everything).
    if cancelled or (ops.classify_fn(rc, ran) != INFRA
                     and testcase_count(report) == len(plan.red_ids)
                     and same_tests(plan.report, report)
                     and merge_junit(plan.report, report, merged)):
        if cancelled:
            report.unlink(missing_ok=True)  # never leave the red-tests-only report as the unit's
        else:
            shutil.copyfile(merged, report)
            ctx.used.add(unit.id)
            ctx.reran[unit.id] = list(plan.red_ids)
        return got
    ctx.notes[unit.id] = "the red-tests-only run did not describe the unit"
    ops.clear_cov_fn(unit)
    report.unlink(missing_ok=True)
    shutil.rmtree(cache, ignore_errors=True)
    return None


def _red_ids(res, report: Path | None) -> list[str] | None:
    """The red ids a LATER resume may re-run: only when cache and report agree (the same
    cross-check the in-run narrow retry applies)."""
    if res.outcome != TEST_FAILURE or not res.cache_dir or report is None:
        return None
    cache = Path(res.cache_dir)
    count = failed_only_count(cache, report)
    ids = read_lastfailed(cache)
    return sorted(ids) if ids and 0 < count <= FAILED_ONLY_MAX_TESTS else None


def persist(ctx: ResumeContext, project_root: Path, run_id: str | None, units, results,
            retention) -> None:
    """Leave the next invocation its state - or spend it when nothing is red any more.
    Never raises."""
    snap = ctx.snapshot
    try:
        if all(r.outcome == PASS and not r.evidence_error for r in results):
            clear_state(project_root)  # spent even when the tree could not be snapshotted
            return
        if snap is None or retention is None:
            clear_state(project_root)  # a superseded token must not outlive a red run
            return
        by_id = {r.unit_id: r for r in results}
        entries: dict[str, dict] = {}
        for unit in units:
            res, plan = by_id.get(unit.id), ctx.plans.get(unit.id)
            reused = plan is not None and unit.id in ctx.used
            report = plan.report if reused and plan.mode == REUSE_GREEN \
                else retention.pending_report(unit.id)
            cov = Path(unit.cov_file) if unit.cov_file else None
            entries[unit.id] = {
                "sig": unit_signature(unit, snap), "outcome": res.outcome if res else INFRA,
                "lastfailed": _red_ids(res, report) if res else None,
                "test_files": unit_test_files(snap, unit),
                "reuses": plan.reuses + 1 if reused else 0, "report": report, "cov": cov}
        if not save_state(project_root, run_id=run_id or "f0", invocation=ctx.invocation,
                          snapshot=snap, chain=ctx.chain if ctx.used else (), entries=entries):
            clear_state(project_root)
    except Exception:  # noqa: BLE001 - losing a resume only costs a full run
        clear_state(project_root)
