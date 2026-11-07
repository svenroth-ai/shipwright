#!/usr/bin/env python3
"""Record a choice an autonomous run takes by rule instead of asking a person (run 23, S08).

    uv run record_autonomous_choice.py --project-root <dir> --kind precedence|routine [options]

Siblings of ``record_autonomous_decision.py``; same contract: an interactive run records nothing
(``action: ask``, exit 1); autonomous exit ``0`` decided, ``1`` ask the person, ``2`` cannot run.

``precedence``  Two sources disagree (plan text vs brief, the brief against itself, an approved screen
                vs a brief line). The higher source wins: hard-requirement > brief > approved-screen >
                plan. ``--winner``, ``--loser``, ``--what``; a ``hard-requirement`` or ``brief`` winner
                needs ``--quote`` (a clause that occurs in the package's brief.md). A winner that does
                not outrank the loser is a question. A screen that loses is recorded as a known difference.
``routine``     A wrap-up question with one documented safe default (``--topic``): changelog-entry
                (readable list), tag-uncommitted (commit the pipeline records, then tag), test-screenshots
                (ignore in git), decision-log-entry (add the missing entry, then re-check).
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
if _ADDED:  # leave sys.path as found: shared/scripts holds a `tools` package
    sys.path.remove(str(_SCRIPTS))

RANK = {"hard-requirement": 4, "brief": 3, "approved-screen": 2, "plan": 1}
ROUTINE = {
    "changelog-entry": ("readable-list", "The 0.1.0 changelog entry is a readable list, not the pipeline's progress lines."),
    "tag-uncommitted": ("commit-then-tag", "The pipeline's own records are committed, then the version is tagged."),
    "test-screenshots": ("ignore-in-git", "Screenshots of the test run are ignored in git, not committed."),
    "decision-log-entry": ("add-entry-and-recheck", "The missing decision-log entry is written, then the check runs again."),
}
_MAX = 500  # write_decision_log.py field cap
_DECISION_LOG = ".shipwright/agent_docs/decision_log.md"


def _ask(kind: str, why: str) -> tuple[dict, int]:
    return {"autonomous": True, "kind": kind, "action": "ask", "adr": None, "kd": None, "why": why}, 1


def _log(root: Path, section: str, title: str, context: str, decision: str, consequences: str, rejected: str) -> str | None:
    args = [sys.executable, str(_SCRIPTS / "tools" / "write_decision_log.py"), "--project-root", str(root),
            "--section", section, "--commit", "n/a", "--title", title[:60]]
    for flag, value in {"--context": context, "--decision": decision, "--consequences": consequences,
                        "--rejected": rejected}.items():
        args += [flag, value[:_MAX]]
    proc = subprocess.run(args, capture_output=True, text=True, encoding="utf-8", check=False)
    m = re.search(r"ADR-\d+", proc.stdout or "")
    return m.group(0) if proc.returncode == 0 and m else None


def _logged(root: Path, title: str) -> bool:
    try:
        return title[:60] in (root / _DECISION_LOG).read_text(encoding="utf-8")
    except OSError:
        return False


def _done(kind: str, action: str, adr: str | None, kd: str | None, why: str, **extra) -> tuple[dict, int]:
    return {"autonomous": True, "kind": kind, "action": action, "adr": adr, "kd": kd, "why": why, **extra}, 0


def _precedence(root: Path, a: argparse.Namespace) -> tuple[dict, int]:
    if not (a.winner and a.loser and a.what):
        return {"error": "--winner, --loser and --what are required"}, 2
    if RANK[a.winner] <= RANK[a.loser]:
        return _ask("precedence", f"{a.winner} does not outrank {a.loser} (hard-requirement > brief > approved-screen > plan)")
    if a.winner in ("hard-requirement", "brief") and not rules.brief_states(root, a.quote):
        return _ask("precedence", "the quote is not in the package's brief.md, so no stated brief value or hard requirement")
    title = f"{a.winner} over {a.loser}: {a.what}"
    if _logged(root, title):
        return _done("precedence", "already_recorded", None, None, "the decision log already holds this decision")
    adr = _log(root, f"{a.phase} (autonomous rule)", title,
               f"{a.winner} and {a.loser} disagree on {a.what}." + (f" Brief: \"{a.quote}\"." if a.quote else ""),
               f"Autonomous rule: the {a.winner} wins over the {a.loser}.",
               "The losing source gives way here" + ("; recorded as a known difference." if a.loser == "approved-screen" else "."),
               "Asking the person; leaving the two sources in conflict.")
    if adr is None:
        return {"error": "the decision-log entry could not be written"}, 2
    kd = None
    if a.loser == "approved-screen":
        kd = rules.append_known_difference(root, a.what, [
            ("Difference", f"the built app follows the {a.winner}; the approved screens differ"),
            ("Source", f"brief.md: \"{a.quote}\"" if a.quote else a.winner),
            ("Decision", f"autonomous rule ({adr}): {a.winner} outranks the approved screen")])
    return _done("precedence", "recorded", adr, kd, f"{a.winner} outranks {a.loser}")


def _routine(root: Path, a: argparse.Namespace) -> tuple[dict, int]:
    if a.topic not in ROUTINE:
        return {"error": f"--topic must be one of {', '.join(ROUTINE)}"}, 2
    choice, why = ROUTINE[a.topic]
    title = f"Routine default: {a.topic}"
    if _logged(root, title):
        return _done("routine", "already_recorded", None, None, why, topic=a.topic, choice=choice)
    adr = _log(root, f"{a.phase} (autonomous rule)", title, f"A wrap-up step asked about {a.topic}.",
               f"Autonomous rule: {why}", "Nothing about the product changes; the step goes on.", "Asking the person.")
    if adr is None:
        return {"error": "the decision-log entry could not be written"}, 2
    return _done("routine", "recorded", adr, None, why, topic=a.topic, choice=choice)


def run(root: Path, a: argparse.Namespace) -> tuple[dict, int]:
    if not rules.is_autonomous_run(root):
        return {"autonomous": False, "kind": a.kind, "action": "ask", "adr": None, "kd": None,
                "why": "interactive run: the person decides"}, 1
    return _precedence(root, a) if a.kind == "precedence" else _routine(root, a)


def parse(argv: list[str] | None = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Record an autonomous run's rule choice")
    ap.add_argument("--project-root", required=True)
    ap.add_argument("--kind", required=True, choices=("precedence", "routine"))
    ap.add_argument("--phase", default="Build", choices=("Design", "Plan", "Build", "Test", "Changelog"))
    ap.add_argument("--winner", default="", choices=("", *RANK))
    ap.add_argument("--loser", default="", choices=("", *RANK))
    ap.add_argument("--what", default="")
    ap.add_argument("--quote", default="", help="a clause of the package's brief.md (brief / hard-requirement winner)")
    ap.add_argument("--topic", default="")
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
