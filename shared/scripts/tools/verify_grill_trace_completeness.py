"""The grill-trace completeness gate (design:
``.shipwright/planning/campaigns/2026-07-24-req3-grill-trace-enforcement-DESIGN.md``).

Mirrors the shape/convention of ``verify_iterate_finalization.py``'s
``check_*`` verifier pattern: pure ``CheckResult``-returning functions,
aggregated by ``run_all_checks``, reported by the shared
``tools.verifiers.common.format_report``.

Enforces exactly the **four closed-vocabulary STOP conditions** the design
names, per grill-trace record (``shared/grill-trace-format.md``):

1. **Blank dimension** — a dimension neither ``answered`` nor an explicit
   ``assumed:<reason>`` / ``n/a:<reason>``.
2. **Greenfield ``assumed``** — in ``/shipwright-project``'s surface, ANY
   ``assumed:`` value at all (no exceptions — Adopt's "iff a work item was
   raised" permission does not apply here; Adopt is out of scope for P4.2).
3. **Undefined term** — a term the trace declares it used
   (``terms_used``) that is in neither ``shared/glossary.md`` nor the
   target project's ``CONTEXT.md`` (read via
   ``context_md_format.read_terms`` — the sanctioned reader, never a
   forked parser).
4. **Outcome without a fit criterion** — the ``outcome`` dimension is
   ``answered`` with no ``fit_criterion`` recorded.

Plus structural checks that are NOT part of the four (each kept under its
own, separately-named result so none is ever confused with the closed
vocabulary above — every one is a presence/consistency check, never a
prose judgment, same honesty guard as the four):

- ``grill_trace_coverage`` — an interview transcript exists but ZERO
  grill-trace records were written at all. The exact failure mode the
  design opens with (three times, dogfooded, zero traces).
- ``fr_trace_coverage`` (``grill_trace_fr_coverage.py``, external plan
  review, P4.2) — a spec.md FR row has no matching grill-trace at all.
  Catches a PARTIALLY recorded interview the coverage check above cannot
  see (some requirements traced, others not) — only meaningful once
  Step 6 has minted FR ids, so SKIPPED before any spec.md exists.
- ``glossary_source_available`` (``grill_trace_glossary.py``, external code
  review, P4.2) — ``shared/glossary.md`` itself is missing (a broken
  install, never a legitimate state, unlike an absent ``CONTEXT.md``).
- ``glossary_delta_declared`` (external code review, P4.2) — a term the
  trace recorded sharpening (``glossary_delta``) but never listed in
  ``terms_used`` — narrows (does not eliminate) the declared-list honesty
  guard's residual under-declaration bypass.
- ``malformed_trace`` — a grill-trace JSON file could not be parsed/
  validated at all; reported as a red result instead of crashing the CLI.

**Honesty guard:** none of these checks read ``evidence``, ``fit_criterion``,
or ``confirmed_by`` for *quality* — only for presence/shape. See
``shared/grill-trace-format.md`` §3 and
``shared/tests/test_verify_grill_trace_completeness_integration.py``'s
low-quality-but-complete-trace tests.

CLI usage:
    uv run verify_grill_trace_completeness.py --project-root <target-project>

Exit code 0 = all green (or warnings only). Exit code 1 = one or more
hard failures. ``--strict`` promotes WARNING to a hard failure too.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

_SCRIPTS_ROOT = Path(__file__).resolve().parent.parent
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from tools.verifiers.common import CheckResult, Severity, format_report  # noqa: E402
from tools.verifiers.stdio import ensure_utf8_stdout  # noqa: E402

from tools.grill_trace_format import (  # noqa: E402
    DIMENSIONS, GrillTrace, GrillTraceError, grill_traces_dir, read_trace_dir,
)
from tools.grill_trace_fr_coverage import check_fr_trace_coverage  # noqa: E402
from tools.grill_trace_glossary import (  # noqa: E402
    DEFAULT_GLOSSARY_PATH, check_glossary_source_available, collect_known_terms,
)

# A dimension value must be exactly "answered", or "assumed:<reason>" / "n/a:<reason>"
# with a non-blank reason after the colon.
_DIMENSION_VALUE_RE = re.compile(r"^(answered)$|^(assumed|n/a):(.+)$")


def check_blank_dimension(trace: GrillTrace) -> CheckResult:
    name = f"blank_dimension[{trace.requirement_key}]"
    problems: list[str] = []
    for dim in DIMENSIONS:
        value = trace.dimensions.get(dim)
        if value is None:
            problems.append(f"{dim}: missing")
            continue
        m = _DIMENSION_VALUE_RE.match(value)
        if not m:
            problems.append(
                f"{dim}: {value!r} is not 'answered' / 'assumed:<reason>' / 'n/a:<reason>'"
            )
            continue
        reason = m.group(3)
        if reason is not None and not reason.strip():
            problems.append(f"{dim}: reason after ':' is blank")
    if problems:
        return CheckResult(name, False, "; ".join(problems))
    return CheckResult(name, True, "all seven dimensions answered / assumed / n-a")


def check_greenfield_assumed(trace: GrillTrace) -> CheckResult:
    """This gate is wired ONLY into ``/shipwright-project``'s Step 8, and
    nothing else writes into a project's ``grill-traces/`` directory — so a
    trace claiming ``surface != "project"`` there is a data-integrity fault,
    never a legitimate exemption. Trusting a payload-declared field to skip
    this rule is exactly the bypass external code review (P4.2) found: a
    trace could opt itself out of the no-'assumed' rule just by writing
    ``"surface": "adopt"``. FAIL, don't skip."""
    name = f"greenfield_assumed[{trace.requirement_key}]"
    if trace.surface != "project":
        return CheckResult(
            name, False,
            f"surface={trace.surface!r} but this gate only evaluates "
            "/shipwright-project's traces — a non-'project' surface trace "
            "found in a project's planning tree is a data-integrity error, "
            "not an exemption from the no-'assumed' rule",
        )
    assumed_dims = sorted(d for d, v in trace.dimensions.items() if v.startswith("assumed:"))
    if assumed_dims:
        return CheckResult(
            name, False,
            f"'assumed' present in /shipwright-project's surface for: {assumed_dims} "
            "(no exceptions in this surface)",
        )
    return CheckResult(name, True, "no 'assumed' dimension in project surface")


def check_outcome_fit_criterion(trace: GrillTrace) -> CheckResult:
    name = f"outcome_without_fit_criterion[{trace.requirement_key}]"
    outcome = trace.dimensions.get("outcome", "")
    if outcome != "answered":
        return CheckResult(
            name, True, f"outcome dimension is {outcome!r}, not 'answered' — rule not triggered",
        )
    if not trace.fit_criterion or not trace.fit_criterion.strip():
        return CheckResult(name, False, "outcome is 'answered' but no fit_criterion was recorded")
    return CheckResult(name, True, "fit_criterion recorded")


def check_undefined_term(trace: GrillTrace, known_terms: set[str]) -> CheckResult:
    name = f"undefined_term[{trace.requirement_key}]"
    missing = [t for t in trace.terms_used if t not in known_terms]
    if missing:
        return CheckResult(
            name, False,
            f"term(s) in neither shared/glossary.md nor CONTEXT.md: {missing}",
        )
    return CheckResult(
        name, True, f"{len(trace.terms_used)} declared term(s), all defined",
    )


def check_glossary_delta_declared(trace: GrillTrace) -> CheckResult:
    """Structural (not a prose judgment) narrowing of the ``terms_used``
    declared-list honesty-guard's residual bypass (external code review,
    P4.2): a term the trace itself recorded sharpening
    (``glossary_delta``) but never listed in ``terms_used`` is an
    objective, checkable inconsistency — the interviewer declared writing
    the definition down without declaring the requirement depends on it.
    Does not close the bypass entirely (an interviewer can still omit a
    term from BOTH lists — see ``shared/grill-trace-format.md`` §3, the
    honesty guard is a deliberate, documented limit, not a bug), only the
    self-contradictory half of it."""
    name = f"glossary_delta_declared[{trace.requirement_key}]"
    delta_terms = {entry["term"] for entry in trace.glossary_delta}
    undeclared = sorted(delta_terms - set(trace.terms_used))
    if undeclared:
        return CheckResult(
            name, False,
            f"glossary_delta records sharpening {undeclared} but terms_used "
            "does not list them — declare every glossary_delta term in terms_used",
        )
    return CheckResult(name, True, f"{len(delta_terms)} glossary_delta term(s), all declared")


def check_grill_trace_coverage(planning_dir: Path, traces: list[GrillTrace]) -> CheckResult:
    """Not one of the four closed-vocabulary STOP conditions — a distinct
    structural guard against the exact bypass the design opens with:
    an interview ran and produced no trace at all. Kept under its own,
    differently-named result so it is never mistaken for one of the four."""
    name = "grill_trace_coverage"
    if traces:
        return CheckResult(name, True, f"{len(traces)} grill-trace record(s) found")
    transcript = planning_dir / "shipwright_project_interview.md"
    if transcript.exists():
        return CheckResult(
            name, False,
            f"{transcript} exists (an interview ran) but no grill-trace records "
            f"were written under {grill_traces_dir(planning_dir)}",
        )
    return CheckResult(
        name, None, "no interview transcript yet — nothing to check",
        severity=Severity.SKIPPED.value,
    )


def run_all_checks(
    project_root: Path,
    *,
    planning_dir: Path | None = None,
    glossary_path: Path | None = None,
    context_path: Path | None = None,
) -> list[CheckResult]:
    project_root = Path(project_root)
    planning_dir = Path(planning_dir) if planning_dir else project_root / ".shipwright" / "planning"
    glossary_path = Path(glossary_path) if glossary_path else DEFAULT_GLOSSARY_PATH
    context_path = Path(context_path) if context_path else project_root / "CONTEXT.md"

    # A malformed trace file (bad JSON, a GrillTraceError) must report as a
    # red CheckResult like every other STOP — never crash the CLI with a raw
    # traceback (external code review, P4.2). Still blocks (the caller sees
    # an ERROR-severity failure), only the reporting path changes.
    try:
        traces = read_trace_dir(planning_dir)
    except (GrillTraceError, OSError, ValueError) as exc:
        return [CheckResult(
            "malformed_trace", False,
            f"could not read grill-trace records under {grill_traces_dir(planning_dir)}: "
            f"{type(exc).__name__}: {exc}",
        )]

    trace_keys = {t.requirement_key for t in traces}
    spec_paths = sorted(planning_dir.glob("*/spec.md"))

    results: list[CheckResult] = [
        check_grill_trace_coverage(planning_dir, traces),
        check_fr_trace_coverage(spec_paths, trace_keys),
        check_glossary_source_available(glossary_path),
    ]
    if not traces:
        return results

    known_terms = collect_known_terms(glossary_path, context_path)
    for trace in traces:
        results.append(check_blank_dimension(trace))
        results.append(check_greenfield_assumed(trace))
        results.append(check_outcome_fit_criterion(trace))
        results.append(check_undefined_term(trace, known_terms))
        results.append(check_glossary_delta_declared(trace))
    return results


def main() -> int:
    ensure_utf8_stdout()
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--project-root", default=".", help="Target project directory")
    parser.add_argument("--planning-dir", default="", help="Override the planning dir")
    parser.add_argument("--glossary-path", default="", help="Override shared/glossary.md path")
    parser.add_argument("--context-path", default="", help="Override CONTEXT.md path")
    parser.add_argument("--strict", action="store_true", help="Treat warnings as errors")
    args = parser.parse_args()

    project_root = Path(args.project_root).resolve()
    results = run_all_checks(
        project_root,
        planning_dir=Path(args.planning_dir).resolve() if args.planning_dir else None,
        glossary_path=Path(args.glossary_path).resolve() if args.glossary_path else None,
        context_path=Path(args.context_path).resolve() if args.context_path else None,
    )
    print(format_report("grill-trace completeness", results))

    errors = sum(1 for r in results if r.is_failure and r.severity == Severity.ERROR.value)
    warnings = sum(1 for r in results if r.is_failure and r.severity == Severity.WARNING.value)
    if errors > 0 or (args.strict and warnings > 0):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
