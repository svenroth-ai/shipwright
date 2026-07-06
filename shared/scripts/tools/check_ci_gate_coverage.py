#!/usr/bin/env python3
"""CI gate-coverage guard — stops CI quality gates from silently going loose.

``ci.yml`` was authored "dormant" (commit 4107a6b) with ``|| true`` +
``continue-on-error`` baked in, then only partially hardened. This guard runs
in CI (``ci.yml`` -> "Run CI-gate guard") and fails when:

  (a) a test dir (``plugins/*/tests``, ``shared/**/tests``,
      ``integration-tests/``) is NOT referenced by any CI pytest invocation;
  (b) a quality-gate step (test/lint/type/scan/analyze) carries ``|| true`` or
      ``continue-on-error: true`` and is NOT in the documented allowlist;
  (c) the security.yml critical-gate lacks a fail-closed guard, so an absent
      ``findings.json`` (scanner crash) would read 0 criticals -> silent green.

``LOOSE_GATE_ALLOWLIST`` (in ``lib/ci_gate_allowlist.py``) is the SSoT for
intentionally non-gating steps, with both-direction drift protection: forward
(``stale_allowlist_entries``) + reverse (check (b)).
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# Resolve sibling ``lib`` package whether invoked as a script or imported.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from lib.ci_gate_allowlist import (  # noqa: E402
    AllowEntry,
    LOOSE_GATE_ALLOWLIST,
)
from lib.ci_gate_scan import (  # noqa: E402  (re-exported for callers/tests)
    Step,
    discover_test_dirs,
    parse_workflows,
)

# Gate-command tokens (matched in a step's ``run:`` body) and gate actions
# (matched in a step's ``uses:``). A step is a "quality gate" if it invokes
# one of these, or its name carries a gate keyword. Only LOOSE gate steps are
# ever flagged, so install steps that merely mention a scanner are harmless.
GATE_COMMANDS = (
    "pytest", "ruff", "mypy", "pyright", "tsc", "eslint", "flake8",
    "vitest", "jest", "semgrep", "trivy", "gitleaks",
    # diff-cover: the diff-coverage roadmap's gate tool. Phase 4's HARD FLIP made
    # the ci.yml step a gating `--fail-under 80` gate and REMOVED its allowlist
    # entry, so the guard's reverse-drift + stale-entry checks now enforce it
    # stays gating — a future silent-loosening (re-adding continue-on-error) is
    # caught as a loose gate with no allowlist entry.
    "diff-cover",
    # measure_diff_coverage: the tested wrapper the ci.yml gate step invokes
    # instead of raw `diff-cover` (the gate DECISION lives in this Python
    # entrypoint). `diff-cover` (hyphen) would NOT match this underscore token, so
    # register it explicitly — else the step would stop being classified as a gate.
    "measure_diff_coverage",
)
GATE_NAME_KEYWORDS = (
    "lint", "type-check", "typecheck", "type check", "test", "scan",
    "sarif", "codeql", "analy",
)
GATE_USES = ("codeql-action/analyze", "codeql-action/upload-sarif")

# Fail-open suppression on a gate command line: ``|| true`` / ``|| :`` /
# ``|| exit 0``.
_PIPE_SUPPRESS = re.compile(r"\|\|\s*(true|:|exit\s+0)")


# --------------------------------------------------------------------------- #
# Classification
# --------------------------------------------------------------------------- #
def is_gate_step(step: Step) -> bool:
    name_l = step.name.lower()
    # Provisioning steps are not quality gates even if they name a scanner
    # (e.g. "Install Semgrep" runs `pip install semgrep`).
    if name_l.startswith(("install", "set up", "setup", "checkout")):
        return False
    if any(cmd in step.run.lower() for cmd in GATE_COMMANDS):
        return True
    if any(act in step.uses for act in GATE_USES):
        return True
    # Artifact upload/download steps that merely mention "scan" are not gates.
    if "artifact" in name_l:
        return False
    return any(kw in name_l for kw in GATE_NAME_KEYWORDS)


def _line_has_gate_cmd(line: str) -> bool:
    return any(cmd in line.lower() for cmd in GATE_COMMANDS)


def is_loose(step: Step) -> bool:
    """A gate step is loose if it sets continue-on-error, or suppresses its
    gate command with ``|| true`` / ``|| :`` / ``|| exit 0``. Comment and
    ``echo`` lines are ignored so an explanatory comment that quotes a loose
    form is not a false positive."""
    if not is_gate_step(step):
        return False
    if step.continue_on_error:
        return True
    for line in step.run.splitlines():
        stripped = line.strip()
        if stripped.startswith("#") or stripped.startswith("echo"):
            continue
        if _PIPE_SUPPRESS.search(line) and _line_has_gate_cmd(line):
            return True
    return False


def _in_allowlist(step: Step, allowlist: list[AllowEntry]) -> bool:
    return any(e.workflow == step.workflow and e.step == step.name for e in allowlist)


# --------------------------------------------------------------------------- #
# Checks
# --------------------------------------------------------------------------- #
def check_test_dir_coverage(dirs: list[str], steps: list[Step]) -> list[str]:
    """Return test dirs not referenced by any pytest-bearing CI run body."""
    blob = "\n".join(s.run for s in steps if "pytest" in s.run)
    has_plugins_loop = "plugins/*" in blob
    uncovered: list[str] = []
    for d in dirs:
        if re.fullmatch(r"plugins/[^/]+/tests", d) and has_plugins_loop:
            continue
        if d in blob:
            continue
        uncovered.append(d)
    return uncovered


def check_loose_gates(steps: list[Step], allowlist: list[AllowEntry]) -> list[Step]:
    """Return loose gate steps that are NOT allowlisted (reverse drift)."""
    return [s for s in steps if is_loose(s) and not _in_allowlist(s, allowlist)]


def stale_allowlist_entries(steps: list[Step], allowlist: list[AllowEntry]) -> list[AllowEntry]:
    """Return allowlist entries that match no real loose step (forward drift)."""
    stale: list[AllowEntry] = []
    for e in allowlist:
        if not any(
            s.workflow == e.workflow and s.name == e.step and is_loose(s)
            for s in steps
        ):
            stale.append(e)
    return stale


def _has_coupled_missing_guard(run: str) -> bool:
    """True iff a ``! -f findings.json`` (or ``! test -f``) test is coupled to a
    non-zero ``exit`` within the next few lines — a *warning-only* missing
    branch (no exit) does NOT count."""
    lines = run.splitlines()
    for i, line in enumerate(lines):
        if re.search(r"!\s*(?:test\s+)?-f\s+\S*findings\.json", line):
            for j in range(i, min(i + 5, len(lines))):
                if re.search(r"\bexit\s+[1-9]", lines[j]):
                    return True
    return False


def _has_silent_findings_default(run: str) -> bool:
    """True iff the critical COUNT is assigned from ``jq ... findings.json`` with
    a silent fallback (``2>/dev/null`` or ``|| echo``) — the fail-open pattern
    that reads 0 criticals on a missing/broken scan."""
    for line in run.splitlines():
        if (re.search(r"=\s*\$\(.*jq.*findings\.json", line)
                and re.search(r"2>\s*/dev/null|\|\|\s*echo", line)):
            return True
    return False


def check_security_findings_gate(steps: list[Step]) -> list[str]:
    """The security.yml critical-gate must fail-closed on a missing/invalid
    findings.json. Return human-readable problems (empty == compliant)."""
    problems: list[str] = []
    gates = [
        s for s in steps
        if s.workflow == "security.yml"
        and "critical" in s.name.lower()
        and "findings.json" in s.run
    ]
    if not gates:
        problems.append(
            "security.yml: no critical-findings gate step references findings.json "
            "(expected a step named like 'Check for critical findings')."
        )
    for s in gates:
        if _has_silent_findings_default(s.run):
            problems.append(
                f"security.yml step {s.name!r}: the critical count is derived "
                f"from findings.json with a silent fallback (2>/dev/null / "
                f"|| echo) — a missing/broken scan reads 0 criticals and passes "
                f"green. Remove the fallback and fail closed."
            )
        elif not _has_coupled_missing_guard(s.run):
            problems.append(
                f"security.yml step {s.name!r}: missing a fail-closed guard "
                f"coupled to `exit 1` for an absent findings.json (add "
                f"`if [ ! -f findings.json ]; then ...; exit 1; fi`). A "
                f"warning-only branch still lets a scanner crash pass green."
            )
    return problems


def launch_gates(allowlist: list[AllowEntry]) -> list[AllowEntry]:
    return [e for e in allowlist if e.launch_gate]


# --------------------------------------------------------------------------- #
# Orchestration / CLI
# --------------------------------------------------------------------------- #
def run_all(root: Path, allowlist: list[AllowEntry] | None = None) -> dict:
    allowlist = LOOSE_GATE_ALLOWLIST if allowlist is None else allowlist
    steps = parse_workflows(root)
    dirs = discover_test_dirs(root)
    return {
        "uncovered_dirs": check_test_dir_coverage(dirs, steps),
        "loose_gates": check_loose_gates(steps, allowlist),
        "stale_allowlist": stale_allowlist_entries(steps, allowlist),
        "security_problems": check_security_findings_gate(steps),
        "launch_gates": launch_gates(allowlist),
        "discovered_dirs": dirs,
    }


def _format(result: dict) -> tuple[str, bool]:
    lines: list[str] = []
    ok = True
    if result["uncovered_dirs"]:
        ok = False
        lines.append("FAIL (a) test dirs NOT referenced by any CI pytest invocation:")
        lines += [f"       - {d}" for d in result["uncovered_dirs"]]
    if result["loose_gates"]:
        ok = False
        lines.append("FAIL (b) loose quality-gate steps NOT in the allowlist:")
        lines += [f"       - {s.workflow}: {s.name!r}" for s in result["loose_gates"]]
    if result["stale_allowlist"]:
        ok = False
        lines.append("FAIL stale allowlist entries (match no real loose step):")
        lines += [f"       - {e.workflow}: {e.step!r}" for e in result["stale_allowlist"]]
    if result["security_problems"]:
        ok = False
        lines.append("FAIL (c) security findings-gate problems:")
        lines += [f"       - {p}" for p in result["security_problems"]]
    if ok:
        lines.append("OK   CI gate-coverage guard passed.")
        lines.append(f"     Covered test dirs: {len(result['discovered_dirs'])}")
    lg = result["launch_gates"]
    if lg:
        lines.append(f"INFO launch gates to remove at public launch ({len(lg)}):")
        lines += [f"       - {e.workflow}: {e.step!r}" for e in lg]
    return "\n".join(lines), ok


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="CI gate-coverage guard")
    ap.add_argument("--project-root", default=".", help="repo root (default: cwd)")
    ap.add_argument("--list-launch-gates", action="store_true",
                    help="print launch gates and exit 0")
    args = ap.parse_args(argv)
    root = Path(args.project_root).resolve()
    if args.list_launch_gates:
        for e in launch_gates(LOOSE_GATE_ALLOWLIST):
            print(f"{e.workflow}: {e.step}")
        return 0
    result = run_all(root)
    text, ok = _format(result)
    print(text)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
