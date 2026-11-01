"""Decide the pre-build acceptance-criterion declaration of an iterate: ask or auto.

    uv run shared/scripts/tools/ac_decision.py --project-root . --from-json ac.json [--base-ref origin/main] \
        [--answers answers.json] [--autonomous --sub-iterate-id Q1] [--out decided.json]

    uv run shared/scripts/tools/ac_decision.py answer --decided decided.json --item 0 --choice yes|no \
        [--text-file wording.txt] --answers answers.json        # the OPERATOR's channel

``ac.json`` is written with the Write tool (free text never goes through a shell command line)::

    {"items": [{"kind": "add|change|remove|restore|exempt", "ac": "FR-01.03.AC05", "owner_fr": "FR-01.03",
                "old_text": "...", "new_text": "outcome wording", "restores_ac": "FR-01.03.AC05"}]}

Whether anything observable changes is computed from the diff (``--base-ref``, default ``origin/main``), never
declared. AC text must read as an outcome (exit 2 otherwise). The operator is asked only when an existing AC is
changed or removed, or no single FR owns a new AC.

Answers: interactively the agent may relay the user's reply inline (``"answer": {"choice", "text"}`` in the item).
Under ``--autonomous`` an inline answer is REFUSED; the operator runs the ``answer`` subcommand (it reads the
question text from ``decided.json`` and binds the answer to the sha256 of that exact text) and the unit is
re-run with ``--answers``. An answer for different question text is refused.

Exit codes: 0 every item decided; 10 a question must go to the operator (``--autonomous``: the printed
``escalation`` holds ONLY this unit); 2 the declaration is invalid (``errors`` says what to fix).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_SCRIPTS_ROOT = Path(__file__).resolve().parent.parent
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from lib.ac_decision import decide, load_catalog  # noqa: E402
from lib.ac_hold import AC_HOLD_REASON  # noqa: E402
from lib.ac_surface import git_changes, observable_files  # noqa: E402
from lib.ac_wording import diff_identifiers  # noqa: E402

EXIT_OK, EXIT_ASK, EXIT_INVALID = 0, 10, 2


def _escalation(result: dict, sub_iterate_id: str) -> dict:
    """The sub-iterate result.json body for an ask under ``--autonomous`` (a standalone run records an operator-only-decision blocker)."""
    return {"sub_iterate_id": sub_iterate_id, "status": "escalated", "reason_code": AC_HOLD_REASON,
            "reason": f"{AC_HOLD_REASON}: the operator must answer {len(result['questions'])} question(s) about what the product promises before this unit is built",
            "ac_questions": [{"item": q["item"], "row": q["row"], "question": q["question"], "question_sha256": q["question_sha256"]} for q in result["questions"]]}


def _read_json(path: str, ap: argparse.ArgumentParser, what: str) -> object:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        ap.error(f"{what} unreadable: {exc}")


def run_answer(argv: list[str]) -> int:
    """Record the operator's answer, bound to the sha256 of the question text it answers."""
    ap = argparse.ArgumentParser(prog="ac_decision.py answer")
    ap.add_argument("--decided", required=True, help="the decided.json an ask run wrote (--out)")
    ap.add_argument("--item", type=int, required=True)
    ap.add_argument("--choice", required=True, choices=["yes", "no"])
    ap.add_argument("--text-file", default="", help="the operator's wording / owning FR id (a file, never a command line)")
    ap.add_argument("--answers", required=True, help="answer file to create or extend")
    args = ap.parse_args(argv)
    decided = _read_json(args.decided, ap, "--decided")
    qs = [q for q in (decided.get("questions") if isinstance(decided, dict) else None) or [] if isinstance(q, dict) and q.get("item") == args.item]
    if not qs:
        ap.error(f"{args.decided} holds no open question for item {args.item}")
    text = Path(args.text_file).read_text(encoding="utf-8").strip() if args.text_file else ""
    path = Path(args.answers)
    prior = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"answers": []}
    kept = [a for a in prior.get("answers", []) if isinstance(a, dict) and a.get("item") != args.item]
    kept.append({"item": args.item, "question_sha256": qs[0]["question_sha256"], "choice": args.choice, "text": text})
    path.write_text(json.dumps({"answers": kept}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"recorded": True, "item": args.item, "question_sha256": qs[0]["question_sha256"]}))
    return EXIT_OK


def run_decide(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--project-root", default=".")
    ap.add_argument("--from-json", required=True)
    ap.add_argument("--base-ref", default="origin/main", help="the ref the change branches from (the observable surface is computed against it)")
    ap.add_argument("--answers", default="", help="the operator's answer file (ac_decision.py answer)")
    ap.add_argument("--autonomous", action="store_true")
    ap.add_argument("--sub-iterate-id", default="")
    ap.add_argument("--out", default="", help="also write the decision JSON to this file")
    args = ap.parse_args(argv)
    if args.autonomous and not args.sub_iterate_id:
        ap.error("--sub-iterate-id is required with --autonomous (the escalation names the unit it holds)")
    data = _read_json(args.from_json, ap, "--from-json")
    if not isinstance(data, dict):
        ap.error("--from-json must hold a JSON object")
    answers = _read_json(args.answers, ap, "--answers").get("answers") if args.answers else None
    surface, idents = None, None
    try:
        changes = git_changes(args.project_root, args.base_ref)
        surface, idents = observable_files(changes), diff_identifiers(changes)
    except (RuntimeError, OSError) as exc:
        print(f"ac_decision: diff unavailable ({exc}); exemption cannot be checked here, the F11 check recomputes it", file=sys.stderr)
    result = decide(data.get("items"), load_catalog(args.project_root), args.autonomous, surface, idents, answers)
    if surface is not None:
        result["surface"] = surface
    if result["status"] == "ask" and args.autonomous:
        result["escalation"] = _escalation(result, args.sub_iterate_id)
    text = json.dumps(result, indent=2, ensure_ascii=False)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8", newline="\n")
    print(text)
    return {"ok": EXIT_OK, "ask": EXIT_ASK}.get(result["status"], EXIT_INVALID)


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    argv = list(sys.argv[1:] if argv is None else argv)
    return run_answer(argv[1:]) if argv[:1] == ["answer"] else run_decide(argv)


if __name__ == "__main__":
    sys.exit(main())
