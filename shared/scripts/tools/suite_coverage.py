#!/usr/bin/env python3
"""F0 diff-coverage gate - the CI gate, mirrored locally.

Why it exists, what it costs and why `.github/` is untouched:
`references/F0.md` + `docs/hooks-and-pipeline.md`. In one line: the gate existed
only in CI, so it could only fail AFTER a push - 5 of 22 sampled CI failures,
landing after the iterate had already reported done.

**The failure mode this is written against is a FALSE GREEN**, not a false stop:
nobody investigates a pass. So every absence is refused except the one case that is
genuinely nothing to gate, and each way a measurement can silently evaporate is
CHECKED rather than assumed - stale state surviving the reset, an instrumented unit
writing no data, a `coverage.xml` this run did not produce, and (the one that is
structural rather than accidental) F0 running BEFORE F6, where every file the
iterate ADDS is still untracked. See `suite_coverage_rules.gate_argv` for that one.

This module owns the halves that touch the world; the decisions they consult are in
`suite_coverage_rules`, which is re-exported below so callers keep ONE import site.
The one function that spawns processes takes its `runner` as a parameter, so every
branch here is still reachable in-process.

There is exactly ONE combine implementation: `combine_argv` builds the same
`combine_coverage.py` invocation ci.yml's Combine step makes. It is SHELLED OUT
rather than imported because that module binds a top-level `tools`/`lib` package
and this one is loaded as `scripts.tools.suite_coverage` - importing it would put
two module objects behind one file (ADR-045).

ASCII-only: a cp1252 console raises UnicodeEncodeError on non-ASCII, and these
lines sit on the refusal paths.
"""

from __future__ import annotations

import shutil
import subprocess  # nosec B404 - fixed argv, shell=False; no user-supplied strings
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Callable

from scripts.tools.suite_coverage_rules import (  # noqa: F401  (re-export: one import site)
    COVERAGE_XML,
    DATA_DIR,
    DIFF_COVER_VERSION,
    FAIL_UNDER,
    GATE_FAILED,
    GATE_PASSED,
    GateResult,
    DIFF_COVER_BELOW_THRESHOLD,
    _FALLBACK_BRANCH,
    combine_argv,
    final_exit_code,
    gate_argv,
    missing_data,
    verdict,
)
from scripts.tools.suite_units import SuiteConfigError

#: A held file usually clears in milliseconds; a few short retries turn the common
#: transient into a no-op without letting a genuine leftover through.
_RESET_ATTEMPTS = 4
_RESET_BACKOFF = 0.25
#: Filesystem timestamp granularity (FAT / network shares are coarse), so a report
#: this run genuinely wrote is never mistaken for a leftover.
_MTIME_SLACK = 2.0


# --------------------------------------------------------------------------- #
# Compare-branch resolution
# --------------------------------------------------------------------------- #
def compare_branch(project_root: Path,
                   runner: Callable[..., Any] = subprocess.run) -> str | None:
    """The base to diff against: whatever `origin/HEAD` points at, else
    `origin/main` if that ref exists, else None.

    Resolved rather than hardcoded because the default branch is not `main`
    everywhere, and a wrong base silently measures the wrong lines. Deliberately
    NOT a search across remote names - this repo pushes to `origin` and
    `setup_iterate_worktree.py` branches off a freshly fetched `origin/<default>`,
    so `origin` is the evidence-backed case; guessing at `upstream` would be
    speculation.

    `errors="replace"` like every other subprocess here: a byte the console locale
    cannot decode would raise UnicodeDecodeError, which is NOT in the caught tuple
    and would turn this fail-closed `None` into a traceback out of F0.
    """
    def _git(*args: str) -> subprocess.CompletedProcess | None:
        try:
            return runner(  # nosec B603 - fixed argv, shell=False
                ["git", *args], cwd=str(project_root), capture_output=True,
                text=True, errors="replace", shell=False)
        except (OSError, subprocess.SubprocessError):
            return None

    def _resolves(ref: str) -> bool:
        probe = _git("rev-parse", "--verify", "--quiet", ref)
        return probe is not None and probe.returncode == 0

    # BOTH candidates are verified to resolve to an object. `symbolic-ref` prints its
    # target without checking it exists, so a narrowed refspec or a pruned default
    # branch would hand back a name diff-cover then fails on - fail-closed either way,
    # but reported as "add tests" instead of "fetch the base".
    head = _git("symbolic-ref", "--short", "refs/remotes/origin/HEAD")
    if head is not None and head.returncode == 0:
        target = (head.stdout or "").strip()
        if target and _resolves(target):
            return target
    return _FALLBACK_BRANCH if _resolves(_FALLBACK_BRANCH) else None


# --------------------------------------------------------------------------- #
# Side-effecting halves (thin, and injectable)
# --------------------------------------------------------------------------- #
def prepare_coverage(project_root: Path) -> Path:
    """Clear stale coverage state and return the data dir the units write into.

    Stale state is the quiet failure here, so the reset VERIFIES itself rather than
    ignoring errors. If a stale `coverage.xml` survived (a Windows file lock, a
    read-only leftover), `combine_coverage` would find no data, exit 0 reporting
    `n-a` WITHOUT touching the output, and the gate would then measure last run's
    report and could pass on it. Refusing loudly is the only safe reading, so this
    But refusing on the FIRST failure would turn a transient into a hard STOP on the
    platform where this repo has already been bitten by it: an editor, indexer or
    antivirus can hold a file for a moment, and `atomic_write` retries for exactly
    that reason. So this retries briefly, and only a survivor that OUTLASTS the
    retries raises `SuiteConfigError` - which `main` turns into a clean exit 2, not
    a traceback.

    A project that will measure NOTHING (no root `pyproject.toml`, the same test
    `instrument_for_coverage` applies) is left alone entirely: deleting files this
    run has no use for, and refusing when it cannot, would be pure downside.
    """
    data_dir = project_root / DATA_DIR
    if not (project_root / "pyproject.toml").is_file():
        return data_dir
    stale = [project_root / COVERAGE_XML, project_root / ".coverage"]
    survivors: list[str] = []
    for attempt in range(_RESET_ATTEMPTS):
        shutil.rmtree(data_dir, ignore_errors=True)
        for path in stale:
            try:
                path.unlink()
            except OSError:
                pass
        survivors = [p.name for p in (*stale, data_dir) if p.exists()]
        if not survivors:
            break
        if attempt + 1 < _RESET_ATTEMPTS:
            time.sleep(_RESET_BACKOFF)
    if survivors:
        raise SuiteConfigError(
            f"could not clear stale coverage state: {survivors}. A leftover report "
            "would be gated as if this run had produced it. Close any process "
            "holding these files (or delete them) and re-run.")
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir


def run_gate(project_root: Path, *, expected: Sequence[str], suite_green: bool,
             branch: str | None,
             runner: Callable[..., Any] = subprocess.run) -> GateResult:
    """Combine the per-unit data, then run the pinned diff-cover over it.

    `branch` is required, never defaulted: a default would hand a future call site
    a hardcoded base instead of the refusal path, quietly undoing the one guarantee
    that an unfindable base cannot green the gate.

    Skipped when the suite is red: coverage from a suite that did not finish is not
    a verdict, and the red units already STOP the run.
    """
    if not suite_green:
        return GateResult(GATE_PASSED, [
            "diff-coverage: skipped - the suite is red; fix the units first."])
    eligible = len(expected)
    if eligible == 0 or branch is None:
        return verdict(eligible=eligible, branch=branch,
                       no_config=not (project_root / "pyproject.toml").is_file())
    absent = missing_data(expected)
    if absent:
        return verdict(eligible=eligible, branch=branch, missing=absent)

    def _run(argv: list[str], phase: str) -> tuple[int | None, str]:
        try:
            proc = runner(  # nosec B603 - fixed argv, shell=False
                argv, cwd=str(project_root), capture_output=True, text=True,
                errors="replace", shell=False, timeout=600)
        except (OSError, subprocess.SubprocessError) as exc:
            return None, f"could not run {phase}: {exc}"
        return proc.returncode, ((proc.stdout or "") + (proc.stderr or "")).strip()

    started = time.time()
    combine_rc, combine_out = _run(combine_argv(), "coverage combine")
    if combine_rc is None:
        return GateResult(GATE_FAILED, [f"diff-coverage: FAILED - {combine_out}"])
    # Not merely "a coverage.xml exists" but "THIS combine wrote one". Otherwise a
    # concurrent writer (a second F0, a compliance regen) between the reset and here
    # re-opens the stale-report false green from another door - `combine_coverage`
    # returns 0 for "n/a, no data" WITHOUT touching the output.
    # One `stat` inside try/except, not `is_file()` then `stat()`: this module
    # explicitly contemplates a concurrent coverage writer, so between those two
    # calls the report can vanish - and an OSError escaping here would be a
    # traceback out of F0 on the one path whose entire job is to fail closed.
    xml = project_root / COVERAGE_XML
    try:
        xml_exists = xml.stat().st_mtime >= started - _MTIME_SLACK
    except OSError:
        xml_exists = False
    if combine_rc != 0 or not xml_exists:
        return verdict(eligible=eligible, branch=branch, combine_rc=combine_rc,
                       xml_exists=xml_exists, detail=combine_out[-400:])

    gate_rc, gate_out = _run(gate_argv(branch), "diff-cover")
    if gate_rc is None:
        return GateResult(GATE_FAILED, [f"diff-coverage: FAILED - {gate_out}"])
    res = verdict(eligible=eligible, branch=branch, combine_rc=0, xml_exists=True,
                  gate_rc=gate_rc)
    # ALWAYS surface diff-cover's own report: on a failure it names the files and
    # lines, and on a pass it is the evidence the gate actually ran.
    return GateResult(res.exit_code, [*gate_out.splitlines(), *res.lines])
