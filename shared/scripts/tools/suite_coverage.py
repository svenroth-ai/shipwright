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

import os
import shutil
import subprocess  # nosec B404 - fixed argv, shell=False; no user-supplied strings
import time
from collections.abc import Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

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
from scripts.tools.suite_worktree_diff import (  # noqa: F401
    build_worktree_diff,
    controlled_git_env,
)

#: A held file usually clears in milliseconds; a few short retries turn the common
#: transient into a no-op without letting a genuine leftover through.
_RESET_ATTEMPTS = 4
_RESET_BACKOFF = 0.25


def _lock_coverage_handle(handle: Any) -> None:
    """Acquire the platform lock without leaking a branch-local import."""
    if os.name == "nt":
        import msvcrt
        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
    else:
        import fcntl
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)


def _unlock_coverage_handle(handle: Any) -> None:
    """Release the platform lock using an import owned by this call."""
    if os.name == "nt":
        import msvcrt
        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        import fcntl
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


@contextmanager
def coverage_run_lock(project_root: Path):
    """Exclude a second F0 from reset through gate without leaving stale locks.

    The persistent zero-byte-ish file is only the OS lock's rendezvous point; the
    lock belongs to the open handle, so a crashed process releases it automatically.
    Its ``.coverage*`` name is already ignored by this repository.
    """
    path = Path(project_root) / ".coverage.f0.lock"
    try:
        handle = path.open("a+b")
        handle.seek(0)
        if handle.read(1) == b"":
            handle.write(b"0")
            handle.flush()
        handle.seek(0)
        _lock_coverage_handle(handle)
    except (ImportError, OSError) as exc:
        try:
            handle.close()
        except (NameError, OSError):
            pass
        raise SuiteConfigError(
            "could not acquire the F0 coverage lock; another F0 may be running "
            f"in {project_root} ({exc})") from exc
    try:
        yield
    finally:
        try:
            handle.seek(0)
            _unlock_coverage_handle(handle)
        finally:
            handle.close()


# --------------------------------------------------------------------------- #
# Compare-branch resolution
# --------------------------------------------------------------------------- #
def compare_branch(project_root: Path,
                   runner: Callable[..., Any] = subprocess.run) -> str | None:
    """Return CI's declared compare ref when it resolves, otherwise fail closed.

    The composite action defaults to ``origin/main``. Preferring ``origin/HEAD``
    locally would stop being a mirror as soon as that symref pointed elsewhere:
    local F0 and CI would measure different merge-base line sets. The fixed ref is
    therefore the contract, not a guess at the remote's current default branch.

    `errors="replace"` like every other subprocess here: a byte the console locale
    cannot decode would raise UnicodeDecodeError, which is NOT in the caught tuple
    and would turn this fail-closed `None` into a traceback out of F0.
    """
    def _git(*args: str) -> subprocess.CompletedProcess | None:
        root = Path(project_root).resolve()
        try:
            return runner(  # nosec B603 - fixed argv, shell=False
                ["git", "-C", str(root), *args], cwd=str(root), capture_output=True,
                text=True, errors="replace", shell=False, timeout=120,
                env=controlled_git_env())
        except (OSError, subprocess.SubprocessError):
            return None

    def _resolves(ref: str) -> bool:
        probe = _git("rev-parse", "--verify", "--quiet", ref)
        return probe is not None and probe.returncode == 0

    # Mirror the action before trusting the remote-tracking ref. A resolving but
    # stale origin/main can select another merge base and silently certify a line
    # set CI never sees. The action uses this exact targeted fetch shape.
    fetched = _git("fetch", "--no-tags", "origin", "main")
    if fetched is None or fetched.returncode != 0:
        return None
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
             branch: str | None, diff_file: Path | None,
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
    if diff_file is None:
        return GateResult(GATE_FAILED, [
            "diff-coverage: FAILED - no coherent working-tree diff was produced."])
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

    # The candidate is owned by THIS invocation. Root coverage.xml is a public
    # artefact and another tool may write it concurrently; it is never trusted as
    # combine evidence or used as this run's diff-cover input.
    candidate = (project_root / DATA_DIR / f"combined-{uuid4().hex}.xml").resolve()
    combine_rc, combine_out = _run(
        combine_argv(output=str(candidate)), "coverage combine")
    if combine_rc is None:
        return GateResult(GATE_FAILED, [f"diff-coverage: FAILED - {combine_out}"])
    try:
        candidate.stat()
        xml_exists = True
    except OSError:
        xml_exists = False
    if combine_rc != 0 or not xml_exists:
        return verdict(eligible=eligible, branch=branch, combine_rc=combine_rc,
                       xml_exists=xml_exists, detail=combine_out[-400:])

    gate_rc, gate_out = _run(gate_argv(
        branch, coverage_file=str(candidate), diff_file=str(diff_file)), "diff-cover")
    if gate_rc is None:
        return GateResult(GATE_FAILED, [f"diff-coverage: FAILED - {gate_out}"])
    try:
        os.replace(candidate, project_root / COVERAGE_XML)
    except OSError as exc:
        return GateResult(GATE_FAILED, [
            f"diff-coverage: FAILED - could not publish this run's coverage.xml: {exc}"])
    res = verdict(eligible=eligible, branch=branch, combine_rc=0, xml_exists=True,
                  gate_rc=gate_rc, detail=gate_out[-400:])
    # ALWAYS surface diff-cover's own report: on a failure it names the files and
    # lines, and on a pass it is the evidence the gate actually ran.
    return GateResult(res.exit_code, [*gate_out.splitlines(), *res.lines])
