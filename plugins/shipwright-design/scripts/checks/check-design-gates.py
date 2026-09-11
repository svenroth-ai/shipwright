#!/usr/bin/env python3
"""Run the design phase's own gates, in session (FR-01.04).

`SKILL.md` Step 8.5's review-loop Option A lists an "FR-Coverage Gate" and a
visual-guidelines existence check as prose the agent should verify. An
instruction is not a gate — this is the command.

    uv run check-design-gates.py --project-root <path> \
        [--gate fr-coverage|tokens|flows|chrome|standalone|uploads|iteration|boundary|all] \
        [--round <path to design-feedback-roundN.md>]

``--gate fr-coverage`` (#1 / #4 — Option A's "FR-Coverage Gate")
    Every FR the project declares must be linked to >=1 screen (or exempted
    under ``## Non-UI FRs``), and every manifest screen row must point at a
    file that exists. Delegates to the compliance verifier's own
    ``check_design_fr_coverage`` / ``check_design_manifest_screens_exist`` —
    one implementation, run both post-hoc (compliance) and in-session (here).

``--gate tokens`` (#2 — design tokens exist as one definition)
``--gate flows`` (#3 — flows between journey screens are shown)
``--gate chrome`` (#5 — shared chrome from one definition)
``--gate standalone`` (#6 — mockups open standalone in a browser)
``--gate uploads`` (#8 — supplied mockups preserved, only missing generated)
``--gate iteration`` (#9 — feedback regenerates only that screen; needs ``--round``)
``--gate boundary`` (#11 — what design produces are review mockups, not production code)

Exit codes: ``0`` all gates passed · ``1`` a gate failed · ``2`` bad usage.
"""

import argparse
import importlib.util
import json
import sys
from pathlib import Path


def _load_own_lib_module(name: str):
    """Load ``scripts/lib/<name>.py`` directly by file path, WITHOUT binding
    ``sys.modules['lib']`` to this plugin's own ``lib`` package.

    ``tools.verifiers.common`` (imported below) does ``from lib.adr_headers
    import ...`` — a bare package-relative import that resolves against
    whichever ``lib`` package got bound first (ADR-045). A plain ``from
    lib.screen_registry import scan_designs_dir`` would win that race and
    permanently shadow the SHARED ``lib`` for the rest of this process, so
    ``tools.verifiers.design_checks`` would then fail to find
    ``lib.adr_headers`` inside this plugin's own (unrelated) ``lib/``
    folder. ``screen_registry.py`` has no intra-package imports of its own,
    so loading it under a private name sidesteps the collision entirely —
    ``design_gate_extras`` / ``phase_write_boundary`` / ``tools.verifiers.*``
    remain free to resolve ``lib`` against the shared package below.
    """
    path = Path(__file__).resolve().parent.parent / "lib" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"_shipwright_design_own_lib_{name}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


scan_designs_dir = _load_own_lib_module("screen_registry").scan_designs_dir

# parents[0]=checks, [1]=scripts, [2]=shipwright-design, [3]=plugins, [4]=repo root.
_REPO_ROOT = Path(__file__).resolve().parents[4]
_SHARED_LIB = _REPO_ROOT / "shared" / "scripts" / "lib"
_SHARED_SCRIPTS = _REPO_ROOT / "shared" / "scripts"
for _p in (_SHARED_LIB, _SHARED_SCRIPTS):
    if str(_p) not in sys.path:
        sys.path.append(str(_p))

from design_gate_extras import (  # noqa: E402
    chrome_nav_targets_consistent,
    flows_present_for_multi_screen_app,
    iteration_touched_flagged_screens,
    parse_feedback_round,
    screen_declares_nav,
    standalone_html_violations,
    uploads_preserved,
    visual_tokens_present,
)
from phase_write_boundary import find_boundary_violations, git_dirty_paths  # noqa: E402
from tools.verifiers.design_checks import (  # noqa: E402
    check_design_fr_coverage,
    check_design_manifest_screens_exist,
)

GATES = (
    "fr-coverage", "tokens", "flows", "chrome", "standalone",
    "uploads", "iteration", "boundary", "all",
)

DESIGNS_DIRNAME = ".shipwright/designs"

#: FR-01.04 #11 — a design session may write into these prefixes and nowhere
#: else. Mirrors FR-01.03 #7's plan-phase allowlist (`phase_write_boundary`);
#: `+ shared/scripts/lib` is deliberately not exempted — a design session
#: that patches shared plumbing has stopped producing mockups.
DESIGN_ALLOWED_PREFIXES = (
    ".shipwright/",
    "shipwright_run_config.json",
    "shipwright_project_config.json",
    "CHANGELOG-unreleased.d/",
)


def _gate(name: str, ok: bool, detail: str, problems: list[str] | None = None) -> dict:
    if not ok and not problems:
        problems = [detail]
    return {"gate": name, "ok": ok, "detail": detail, "problems": problems or []}


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""


def fr_coverage_gate(project_root: Path) -> dict:
    """FR-01.04 #1 / #4."""
    manifest = check_design_manifest_screens_exist(project_root)
    coverage = check_design_fr_coverage(project_root)
    problems = [
        r.detail for r in (manifest, coverage)
        if r.is_failure
    ]
    return _gate("fr-coverage", not problems, "; ".join(problems) or "manifest + coverage OK", problems)


def tokens_gate(designs_dir: Path) -> dict:
    """FR-01.04 #2."""
    result = visual_tokens_present(designs_dir / "visual-guidelines.md")
    return _gate("tokens", result.ok, result.detail)


def flows_gate(designs_dir: Path) -> dict:
    """FR-01.04 #3."""
    inventory = scan_designs_dir(designs_dir)
    result = flows_present_for_multi_screen_app(len(inventory["screens"]), len(inventory["flows"]))
    return _gate("flows", result.ok, result.detail)


def chrome_gate(designs_dir: Path) -> dict:
    """FR-01.04 #5. A missing ``chrome-definition.md`` is a pass ONLY when no
    screen actually shows nav markup — a project with genuinely no shared
    chrome (all auth/Layout-C screens) has nothing to define. A screen using
    nav markup with no definition to draw it from is exactly the "shared
    chrome from one definition" violation this criterion names (external
    code review, iterate-2026-09-11-e1-checks-plan-design)."""
    chrome_path = designs_dir / "chrome-definition.md"
    inventory = scan_designs_dir(designs_dir)
    if not chrome_path.exists():
        screens_with_nav = [
            s["file"] for s in inventory["screens"]
            if screen_declares_nav(_read(designs_dir / s["file"]))
        ]
        if screens_with_nav:
            return _gate(
                "chrome", False,
                f"no chrome-definition.md, but {len(screens_with_nav)} screen(s) use nav markup",
                [f"{f}: uses nav markup with no chrome-definition.md to draw it from" for f in screens_with_nav],
            )
        return _gate("chrome", True, "no chrome-definition.md and no screen uses nav markup — nothing to define")
    chrome_html = _read(chrome_path)
    problems = []
    for screen in inventory["screens"]:
        screen_html = _read(designs_dir / screen["file"])
        result = chrome_nav_targets_consistent(chrome_html, screen_html)
        if not result.ok:
            problems.append(f"{screen['file']}: {result.detail}")
    return _gate(
        "chrome", not problems,
        f"{len(inventory['screens'])} screen(s) checked, {len(problems)} inconsistent",
        problems,
    )


def standalone_gate(designs_dir: Path) -> dict:
    """FR-01.04 #6."""
    inventory = scan_designs_dir(designs_dir)
    problems = []
    files = [s["file"] for s in inventory["screens"]] + [f["file"] for f in inventory["flows"]]
    for rel in files:
        violations = standalone_html_violations(_read(designs_dir / rel))
        problems += [f"{rel}: external reference {v}" for v in violations]
    return _gate("standalone", not problems, f"{len(files)} file(s) checked, {len(problems)} external ref(s)", problems)


def uploads_gate(project_root: Path, designs_dir: Path) -> dict:
    """FR-01.04 #8."""
    result = uploads_preserved(project_root, designs_dir / "uploads")
    return _gate("uploads", result.ok, result.detail)


def iteration_gate(project_root: Path, designs_dir: Path, round_path: Path | None) -> dict:
    """FR-01.04 #9.

    **Known scope (external plan/code review, iterate-2026-09-11-e1-checks-
    plan-design):** evidence is `git_dirty_paths` — the WORKING TREE's
    current uncommitted state, not a snapshot from when this round began.
    Called right after Option B revises the flagged screens (before any
    commit), so in the intended call site "modified since the round began"
    and "currently dirty" coincide. If a caller commits the revision before
    running this gate, it would false-fail (evidence gone); if a caller ran
    it long after an unrelated earlier commit, it could false-pass (this
    round's own edit already landed in that commit, not in the working
    tree). A per-round baseline snapshot (mirroring
    `record_requirement_impact.py --snapshot-baseline`) would close this,
    but is out of scope for this bounded enforcement pass — call this gate
    promptly, before committing, same as `phase_write_boundary.py`'s
    documented assumption.
    """
    if round_path is None or not round_path.exists():
        return _gate("iteration", True, "no feedback round file given — nothing to check")
    entries = parse_feedback_round(_read(round_path))
    flagged = [f for f, status in entries if status in ("CHANGES", "REJECTED")]
    if not flagged:
        return _gate("iteration", True, "round file names no CHANGES/REJECTED screens")
    modified = git_dirty_paths(project_root)
    designs_rel = designs_dir.relative_to(project_root).as_posix()
    modified_screens = [
        p[len(designs_rel) + 1:] for p in modified if p.startswith(designs_rel + "/")
    ]
    result = iteration_touched_flagged_screens(flagged, modified_screens)
    gate = _gate("iteration", result.ok, result.detail)
    gate["warnings"] = list(result.warnings)
    return gate


def boundary_gate(project_root: Path) -> dict:
    """FR-01.04 #11."""
    changed = git_dirty_paths(project_root)
    violations = find_boundary_violations(changed, list(DESIGN_ALLOWED_PREFIXES))
    if violations:
        return _gate(
            "boundary", False,
            f"{len(violations)} change(s) outside the design phase's allowed paths",
            [f"outside allowed paths: {p}" for p in violations],
        )
    return _gate("boundary", True, f"{len(changed)} changed path(s), all within bounds")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the design phase's own gates")
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--gate", choices=GATES, default="all")
    parser.add_argument("--round", default=None, help="design-feedback-roundN.md for --gate iteration")
    args = parser.parse_args()

    project_root = Path(args.project_root).resolve()
    if not project_root.is_dir():
        print(json.dumps({
            "success": False, "error": "project_root_not_found",
            "message": f"not a directory: {project_root}",
        }, indent=2))
        return 2

    designs_dir = project_root / DESIGNS_DIRNAME
    round_path = (project_root / args.round).resolve() if args.round else None
    if round_path is None and args.gate == "iteration":
        print(json.dumps({
            "success": False, "error": "round_required",
            "message": "--round is required for an explicit --gate iteration "
                       "invocation — silently no-op'ing here would bypass the "
                       "flagged-screen check. --gate all still no-ops without "
                       "--round (Option A finalization has no round file yet).",
        }, indent=2))
        return 2

    results = []
    if args.gate in ("fr-coverage", "all"):
        results.append(fr_coverage_gate(project_root))
    if args.gate in ("tokens", "all"):
        results.append(tokens_gate(designs_dir))
    if args.gate in ("flows", "all"):
        results.append(flows_gate(designs_dir))
    if args.gate in ("chrome", "all"):
        results.append(chrome_gate(designs_dir))
    if args.gate in ("standalone", "all"):
        results.append(standalone_gate(designs_dir))
    if args.gate in ("uploads", "all"):
        results.append(uploads_gate(project_root, designs_dir))
    if args.gate in ("iteration", "all"):
        results.append(iteration_gate(project_root, designs_dir, round_path))
    if args.gate in ("boundary", "all"):
        results.append(boundary_gate(project_root))

    failed = [r["gate"] for r in results if not r["ok"]]
    print(json.dumps({
        "success": not failed,
        "project_root": str(project_root),
        "gates": results,
        "failed": failed,
    }, indent=2))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
