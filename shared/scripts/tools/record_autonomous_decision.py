#!/usr/bin/env python3
"""Record a decision an autonomous run takes by rule instead of asking a person.

    uv run record_autonomous_decision.py --project-root <dir> --kind <kind> [options]

Kinds (rules: ``shared/scripts/lib/autonomous_rules.py``):

``approved-links``   Design: the ``standalone`` gate kept external links the approved package
                     mockups carry; logs that once (idempotent by title).
``brief-wins``       Design/Plan/Build: an explicit brief value wins over plan text and over
                     screens that do not show it. ``--what``, ``--brief-quote`` (must occur in the
                     package's brief.md), optional ``--fr``/``--screens``. Logs it and adds a
                     known difference: screens stay as approved, Build adds the value.
``hard-constraint``  Build: two stated constraints cannot both hold; the hard one (no layout
                     shift, no height change) is kept over a visible extra. ``--what``, ``--keep``,
                     ``--yields``, ``--measurements`` (at least one ``NNN px``). Logs it and adds a
                     known difference.
``dev-tooling``      Plan/Build: ``--command`` (repeatable) installs only tooling the project
                     declares (``autonomous_rules.dev_tooling_verdict``; JavaScript installs with
                     ``--ignore-scripts``) AND only while its manifest is unchanged since the phase
                     started (``phase_boundary_baseline.path_unchanged``; ``--scope``: the split for
                     Plan, the section for Build). Logs one ADR.

An interactive run (no brief package, autonomy guided) records nothing: ``action: ask``.
Prints JSON ``{autonomous, kind, action, adr, kd, why, ...}``. Exit ``0`` decided (or nothing to
decide), ``1`` ask the person, ``2`` cannot run.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parents[1]
_ADDED = str(_SCRIPTS) not in sys.path
if _ADDED:
    sys.path.append(str(_SCRIPTS))
from shared_lib_loader import load_shared_lib  # noqa: E402

rules = load_shared_lib("autonomous_rules", prefer_private=True)
pbb = load_shared_lib("phase_boundary_baseline", prefer_private=True)
if _ADDED:  # leave sys.path as found: shared/scripts holds a `tools` package
    sys.path.remove(str(_SCRIPTS))

KINDS = ("approved-links", "brief-wins", "hard-constraint", "dev-tooling")
_BASELINES = {"Design": pbb.DESIGN_BASELINE_REL, "Plan": pbb.PLAN_BASELINE_REL, "Build": pbb.BUILD_BASELINE_REL}
LINKS_TITLE = "Approved package links stay in the screens"
_MAX = 500  # write_decision_log.py field cap
_DECISION_LOG = ".shipwright/agent_docs/decision_log.md"


def _log(root: Path, section: str, title: str, context: str, decision: str, consequences: str,
         rejected: str) -> str | None:
    fields = {"--context": context, "--decision": decision, "--consequences": consequences, "--rejected": rejected}
    args = [sys.executable, str(_SCRIPTS / "tools" / "write_decision_log.py"), "--project-root", str(root),
            "--section", section, "--commit", "n/a", "--title", title[:60]]
    for flag, value in fields.items():
        args += [flag, value[:_MAX]]
    proc = subprocess.run(args, capture_output=True, text=True, encoding="utf-8", check=False)
    m = re.search(r"ADR-\d+", proc.stdout or "")
    return m.group(0) if proc.returncode == 0 and m else None


def _ask(kind: str, why: str, **extra) -> tuple[dict, int]:
    return {"autonomous": True, "kind": kind, "action": "ask", "adr": None, "kd": None, "why": why, **extra}, 1


def _already(kind: str) -> tuple[dict, int]:
    return {"autonomous": True, "kind": kind, "action": "already_recorded", "adr": None, "kd": None,
            "why": "known-differences.md already holds an entry with this title"}, 0


def _approved_links(root: Path) -> tuple[dict, int]:
    designs = root / ".shipwright" / "designs"
    files = [p.relative_to(designs).as_posix() for d in ("screens", "flows") for p in sorted((designs / d).glob("*.html"))]
    problems, kept, unverified = rules.standalone_findings(root, files)
    if unverified:
        return _ask("approved-links", f"approved links are trusted only from a verified package: {unverified}",
                    problems=problems)
    if not kept:
        return {"autonomous": True, "kind": "approved-links", "action": "nothing", "adr": None, "kd": None,
                "why": "no screen keeps an approved package link", "problems": problems}, 0
    try:
        logged = LINKS_TITLE in (root / _DECISION_LOG).read_text(encoding="utf-8")
    except OSError:
        logged = False
    if logged:
        return {"autonomous": True, "kind": "approved-links", "action": "already_recorded", "adr": None, "kd": None,
                "why": "the decision log already holds this decision", "kept": kept, "problems": problems}, 0
    adr = _log(root, "Design (autonomous rule)", LINKS_TITLE,
               f"The standalone gate found {len(kept)} external link(s) in the screens that the approved package mockups carry.",
               "Autonomous rule: links that are in the approved package mockups stay in the screens; the standalone gate "
               "keeps them and fails on every other external reference.",
               "The screens keep approved functionality (for example Open thread). A loaded external asset still fails.",
               "Asking the person; removing approved links to pass the gate.")
    if adr is None:
        return {"error": "the decision-log entry could not be written"}, 2
    return {"autonomous": True, "kind": "approved-links", "action": "recorded", "adr": adr, "kd": None,
            "why": "approved package links kept", "kept": kept, "problems": problems}, 0


def _brief_wins(root: Path, a: argparse.Namespace) -> tuple[dict, int]:
    if not (a.what and a.brief_quote):
        return {"error": "--what and --brief-quote are required"}, 2
    if not rules.brief_states(root, a.brief_quote):
        return _ask("brief-wins", "the quote is not in the package's brief.md, so it is no explicit brief value")
    if rules.known_difference_exists(root, a.what):
        return _already("brief-wins")
    adr = _log(root, f"{a.phase} (autonomous rule)", f"Brief wins: {a.what}",
               f"The brief states \"{a.brief_quote}\"; {a.screens or 'no approved screen'} shows otherwise or nothing.",
               f"Autonomous rule: the explicit brief value wins over plan text and screens. Screens stay as approved; "
               f"Build adds {a.what} as the brief says. Recorded as a known difference.",
               "The built app differs from the approved screens here; the screenshot check may report it.",
               "Asking the person; changing the approved package; dropping the brief requirement.")
    if adr is None:
        return {"error": "the decision-log entry could not be written"}, 2
    kd = rules.append_known_difference(root, a.what, [
        ("Difference", f"the built app shows {a.what}; the approved screens do not"),
        ("Requirement", a.fr or ""), ("Screens affected", a.screens or ""),
        ("Source", f"brief.md: \"{a.brief_quote}\""),
        ("Decision", f"autonomous rule ({adr}): screens stay as approved, Build adds it from the brief")])
    return {"autonomous": True, "kind": "brief-wins", "action": "recorded", "adr": adr, "kd": kd,
            "why": "explicit brief value"}, 0


def _hard_constraint(root: Path, a: argparse.Namespace) -> tuple[dict, int]:
    if not (a.what and a.keep and a.yields):
        return {"error": "--what, --keep and --yields are required"}, 2
    if not rules.has_measurements(a.measurements):
        return _ask("hard-constraint", "no measurement (NNN px) recorded; measure on the built page first")
    if rules.known_difference_exists(root, a.what):
        return _already("hard-constraint")
    adr = _log(root, f"{a.phase} (autonomous rule)", f"Hard requirement kept: {a.what}",
               f"Two stated constraints cannot both hold: \"{a.keep}\" and \"{a.yields}\".",
               f"Autonomous rule: the hard requirement is kept ({a.keep}); the visible extra gives way ({a.yields}). "
               f"Measured: {a.measurements}",
               "Where the extra gives way the built app shows less than the brief; recorded as a known difference.",
               "Asking the person; breaking the hard requirement to show the extra.")
    if adr is None:
        return {"error": "the decision-log entry could not be written"}, 2
    kd = rules.append_known_difference(root, a.what, [
        ("Kept", a.keep), ("Gives way", a.yields), ("Measurements", a.measurements),
        ("Decision", f"autonomous rule ({adr}): a hard requirement outranks a visible extra")])
    return {"autonomous": True, "kind": "hard-constraint", "action": "recorded", "adr": adr, "kd": kd,
            "why": "hard requirement kept"}, 0


def _profile(root: Path) -> dict | None:
    """The run's stack profile; ``None`` when the run config names none. A profile the config names but
    the resolver refuses (unknown, corrupt, too new) raises -- the caller fails loud (exit 2)."""
    try:
        name = json.loads((root / "shipwright_run_config.json").read_text(encoding="utf-8")).get("profile")
    except (OSError, ValueError, AttributeError):  # no readable run config: no profile declares anything
        return None
    if not isinstance(name, str) or not name:
        return None
    added = str(_SCRIPTS) not in sys.path
    if added:
        sys.path.append(str(_SCRIPTS))
    try:
        from profile_resolver import resolve_profile
    finally:
        if added:
            sys.path.remove(str(_SCRIPTS))
    return resolve_profile(name, root).data


def _profile_error(exc: ValueError) -> tuple[dict, int]:
    return {"error": f"the run's stack profile cannot be resolved: {exc}"}, 2


def _manifest_moved(root: Path, a: argparse.Namespace) -> str:
    """Why the declaring manifest cannot be trusted ("" = unchanged since the phase started)."""
    baseline = _BASELINES.get(a.phase)
    scope = None if a.phase == "Design" else (a.scope or None)
    names = sorted({m for c in a.command for m in (pbb.PY_MANIFESTS if c.split()[:1] == ["uv"] else pbb.JS_MANIFESTS)})
    state = {m: pbb.path_unchanged(root, baseline, scope, m) if baseline else None for m in names}
    if any(v is None for v in state.values()):
        return ("no phase-start baseline of this run to compare the manifest with (--phase, and --scope: "
                "the split for Plan, the section for Build)")
    moved = [m for m, same in state.items() if not same]
    return (f"changed since the phase started: {', '.join(moved)}; a manifest edited in this phase cannot "
            "authorise its own install") if moved else ""


def _dev_tooling(root: Path, a: argparse.Namespace) -> tuple[dict, int]:
    if not a.command:
        return {"error": "at least one --command is required"}, 2
    try:
        profile = _profile(root)
    except ValueError as exc:  # the named stack profile is unknown, corrupt or too new
        return _profile_error(exc)
    verdicts = [{"command": c, "allowed": ok, "why": why}
                for c in a.command for ok, why in [rules.dev_tooling_verdict(c, root, profile)]]
    if not all(v["allowed"] for v in verdicts):
        return _ask("dev-tooling", "a command installs something the project does not declare", verdicts=verdicts)
    if why := _manifest_moved(root, a):
        return _ask("dev-tooling", why, verdicts=verdicts)
    shown = "; ".join(a.command)
    adr = _log(root, f"{a.phase} (autonomous rule)", "Declared dev tooling installed",
               f"The work needs {shown} to run its tests.",
               "Autonomous rule: installing dev tooling the project already declares (package manifest or stack "
               "profile) needs no question. " + "; ".join(f"{v['command']}: {v['why']}" for v in verdicts),
               "The tests run in this phase. Nothing undeclared is added, no lifecycle script runs "
               "(--ignore-scripts), and the manifest is unchanged since the phase started.",
               "Asking the person; leaving the tests unrun.")
    if adr is None:
        return {"error": "the decision-log entry could not be written"}, 2
    return {"autonomous": True, "kind": "dev-tooling", "action": "recorded", "adr": adr, "kd": None,
            "why": "declared dev tooling", "verdicts": verdicts}, 0


def run(root: Path, a: argparse.Namespace) -> tuple[dict, int]:
    if not rules.is_autonomous_run(root):
        return {"autonomous": False, "kind": a.kind, "action": "ask", "adr": None, "kd": None,
                "why": "interactive run: the person decides"}, 1
    if a.kind == "approved-links":
        return _approved_links(root)
    if a.kind == "brief-wins":
        return _brief_wins(root, a)
    if a.kind == "hard-constraint":
        return _hard_constraint(root, a)
    return _dev_tooling(root, a)


def parse(argv: list[str] | None = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Record an autonomous run's rule decision")
    ap.add_argument("--project-root", required=True)
    ap.add_argument("--kind", required=True, choices=KINDS)
    ap.add_argument("--phase", default="Build", choices=("Design", "Plan", "Build", "Test"))
    ap.add_argument("--what", default="")
    ap.add_argument("--brief-quote", default="")
    ap.add_argument("--fr", default="")
    ap.add_argument("--screens", default="")
    ap.add_argument("--keep", default="")
    ap.add_argument("--yields", default="")
    ap.add_argument("--measurements", default="")
    ap.add_argument("--command", action="append", default=[])
    ap.add_argument("--scope", default="", help="dev-tooling: the split (Plan) or section (Build) of the baseline")
    return ap.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    a = parse(argv)
    root = Path(a.project_root).resolve()
    if not root.is_dir():
        out, code = {"error": f"not a directory: {root}"}, 2
    else:
        out, code = run(root, a)
    print(json.dumps(out, indent=2))
    return code


if __name__ == "__main__":
    sys.exit(main())
