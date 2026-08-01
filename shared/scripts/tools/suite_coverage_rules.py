#!/usr/bin/env python3
"""F0 diff-coverage gate - the pure rules: what to run, and what the result means.

Split from `suite_coverage.py` the way `lib/diff_coverage_gate.py` is split from
`measure_diff_coverage.py`, and for the same reason: the DECISION must be
unit-testable without a subprocess. Here that reason is sharper than usual - the
gate these rules implement scores the percentage of CHANGED lines that tests
EXECUTE, and code that only ever runs in a spawned process is invisible to it. A
design whose decisions could only be reached by shelling out would score itself 0%
and red-flag its own diff.

So: no I/O in this module beyond `Path.exists`/`glob` in `missing_data`, and no
subprocess at all. `suite_coverage.py` holds the halves that touch the world and
re-exports everything here, so callers keep ONE import site.

ASCII-only: a cp1252 console raises UnicodeEncodeError on non-ASCII, and these
lines sit on the refusal paths.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from scripts.tools.suite_units import UV_RUN


#: Pinned so a diff-cover release cannot silently change the flags or exit codes
#: this gate reads. MUST equal the `diff-cover-version` default in
#: `.github/actions/diff-coverage-gate/action.yml` - pinned by test_f0_ci_parity.
DIFF_COVER_VERSION = "10.3.0"
#: MUST equal that action's `fail-under` default (and
#: `control_grade._DIFF_COV_WARN_THRESHOLD`). Same guard.
FAIL_UNDER = 80.0
#: Per-tier coverage data lands here; `combine_coverage.py` folds it into one
#: repo-relative XML. Both are gitignored, so F0 never dirties the tree.
DATA_DIR = ".cov-data"
COVERAGE_XML = "coverage.xml"
_COMBINER = "shared/scripts/tools/combine_coverage.py"
_FALLBACK_BRANCH = "origin/main"

#: diff-cover returns 1 for EXACTLY "below threshold" and other non-zero codes for
#: its own failures (unresolvable ref, unreadable XML, a package it could not
#: resolve). Conflating them tells an operator to write tests for a git or network
#: problem, so the two get different messages.
DIFF_COVER_BELOW_THRESHOLD = 1

#: The gate's own verdict codes. `run_test_suite` maps GATE_FAILED onto its exit
#: code 4; 0/1/2/3 are already spoken for (green / red unit / bad config / a race
#: that could not be recorded).
GATE_PASSED = 0
GATE_FAILED = 4


@dataclass(frozen=True)
class GateResult:
    exit_code: int
    lines: list[str]


# --------------------------------------------------------------------------- #
# Pure argv builders
# --------------------------------------------------------------------------- #
def gate_argv(branch: str) -> list[str]:
    """The composite action's command, plus ONE deliberate divergence.

    Same pinned uvx, same combined XML, same threshold, and diff-cover's default
    `--diff-range-notation` of `...` makes this a MERGE-BASE diff, so a moved trunk
    cannot inflate the changed-line set. Relative paths, resolved by `cwd=`.

    **`--include-untracked` is the divergence, and it is what makes the two agree.**
    diff-cover reads git, and F0 runs BEFORE F6 - the commit - so every file the
    iterate ADDS is untracked and, by default, INVISIBLE to it. Without this flag a
    diff consisting largely of new modules is scored over the few tracked lines it
    happens to touch, and a diff of only new files measures nothing at all and
    reports a confident 100%: precisely the under-covered case the gate exists for,
    passing locally and reddening CI. The CI action needs no such flag because it
    runs on a committed PR head where nothing is untracked. Diverging here is
    therefore not drift - it is what makes the LINE SETS equal, which is the thing
    parity is actually about. `.gitignore` is honoured (diff-cover shells
    `git ls-files --exclude-standard --others`), so `.cov-data/` and `coverage.xml`
    exclude themselves.
    """
    return [
        "uvx", f"diff-cover@{DIFF_COVER_VERSION}", COVERAGE_XML,
        f"--compare-branch={branch}", f"--fail-under={FAIL_UNDER:g}",
        "--include-untracked",
    ]


def combine_argv() -> list[str]:
    """ci.yml's Combine step, with F0's interpreter pin. Not a second combiner:
    `combine_coverage.py` remains the only implementation, because a plugin unit
    records `scripts/...` relative to its own CWD and only that tool knows which
    plugin to remap it onto."""
    return [
        *UV_RUN, "--with", "coverage", _COMBINER,
        "--project-root", ".", "--data-dir", DATA_DIR, "--output", COVERAGE_XML,
    ]


# --------------------------------------------------------------------------- #
# Pure verdict
# --------------------------------------------------------------------------- #
def verdict(*, eligible: int, branch: str | None, combine_rc: int | None = None,
            xml_exists: bool = False, gate_rc: int | None = None,
            missing: Sequence[str] = (), no_config: bool = False,
            detail: str = "") -> GateResult:
    """Turn the measured facts into an exit code. Fails CLOSED everywhere except
    the one case that is genuinely nothing to gate.

    `eligible == 0` means no unit was instrumented, so there is no diff coverage to
    speak of -> pass. Every OTHER absence is a measurement that was attempted and
    did not arrive, which must not be confused with it. That distinction is the one
    place this is deliberately STRICTER than ci.yml, whose
    `if: hashFiles('coverage.xml') != ''` guard would skip the gate in both cases
    alike.
    """
    if eligible == 0:
        why = ("no root pyproject.toml, so coverage config could not be honoured"
               if no_config else "no unit had a measurable source root")
        return GateResult(GATE_PASSED, [f"diff-coverage: n/a - {why}."])
    if branch is None:
        return GateResult(GATE_FAILED, [
            "diff-coverage: FAILED - no compare branch found (looked for "
            f"origin/HEAD, then {_FALLBACK_BRANCH}).",
            "  Fix: git fetch origin, or push the default branch, then re-run."])
    if missing:
        # `eligible` counts UNITS and the combiner counts DATA FILES, so a unit that
        # wrote nothing is invisible to both: the combine succeeds, the XML omits
        # that tier, and diff-cover then excludes its changed lines from the
        # DENOMINATOR and reports a comfortable pass over what is left.
        return GateResult(GATE_FAILED, [
            f"diff-coverage: FAILED - {len(missing)} of {eligible} instrumented "
            f"unit(s) wrote no coverage data: {', '.join(sorted(missing)[:6])}.",
            "  Their changed lines would be silently excluded, not counted as 0."])
    if combine_rc not in (0, None):
        return GateResult(GATE_FAILED, [
            f"diff-coverage: FAILED - coverage combine exited {combine_rc}.",
            f"  {detail}".rstrip()])
    if not xml_exists:
        return GateResult(GATE_FAILED, [
            f"diff-coverage: FAILED - {eligible} unit(s) were instrumented but "
            "no combined coverage.xml was produced.", f"  {detail}".rstrip()])
    if gate_rc == DIFF_COVER_BELOW_THRESHOLD:
        return GateResult(GATE_FAILED, [
            f"diff-coverage: FAILED - changed lines below {FAIL_UNDER:g}% covered.",
            "  Add tests for the changed lines named above; do not lower the "
            "threshold.",
            "  If those lines ARE covered by tests that SKIP on this machine "
            "(missing bash/npm/docker/gh, a platform guard), that is the cause: "
            "this gate can be stricter than CI, which runs them."])
    if gate_rc != 0:
        return GateResult(GATE_FAILED, [
            f"diff-coverage: FAILED - diff-cover itself failed (exit {gate_rc}); "
            "the coverage number is unknown, so this is not a threshold verdict.",
            "  First run offline or behind a proxy? Pre-fetch with: "
            f"uvx diff-cover@{DIFF_COVER_VERSION} --version",
            f"  {detail}".rstrip()])
    return GateResult(GATE_PASSED, [
        f"diff-coverage: PASS - changed lines >= {FAIL_UNDER:g}% covered "
        f"(vs {branch})."])


def final_exit_code(suite_rc: int, race_failed: bool, gate: GateResult) -> int:
    """Compose the three verdicts. A red suite keeps its own rc - it STOPs either
    way, and reporting the coverage code would misdescribe why. An unrecorded race
    outranks the gate for the same reason."""
    if suite_rc:
        return suite_rc
    if race_failed:
        return 3
    return gate.exit_code


def missing_data(expected: Sequence[str]) -> list[str]:
    """Instrumented units that wrote no coverage data file.

    pytest-cov's parallel/xdist mode appends `.<host>.<pid>.<rand>` to
    COVERAGE_FILE, so a label counts as present when its own file exists OR any
    suffixed sibling does - the same rule `combine_coverage.resolve_plugin_label`
    reads them back with.
    """
    out: list[str] = []
    for path in expected:
        p = Path(path)
        if not p.exists() and not any(p.parent.glob(p.name + ".*")):
            out.append(p.name)
    return out
