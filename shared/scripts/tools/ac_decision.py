"""Decide the pre-build acceptance-criterion declaration of an iterate: ask or auto.

    uv run shared/scripts/tools/ac_decision.py --project-root . --from-json ac.json --base-ref {base_branch} \
        --run-id RID [--answers answers.json] [--autonomous --sub-iterate-id Q1] [--out decided.json]

    uv run shared/scripts/tools/ac_decision.py answer --decided decided.json|result.json --item 0 --choice yes|no \
        [--text-file wording.txt] --answers answers.json        # the OPERATOR's channel

    uv run shared/scripts/tools/ac_decision.py verify --project-root . --run-id RID --base-ref {base_branch}
        # the finalize-time compare against the working tree / diff: prints the same problems F11 warns about

``ac.json`` is written with the Write tool (free text never goes through a shell command line)::

    {"items": [{"kind": "add|change|remove|restore|exempt", "ac": "FR-01.03.AC05", "owner_fr": "FR-01.03",
                "new_fr": {"id": "FR-01.30", "title": "one sentence"}, "old_text": "...", "new_text": "outcome wording",
                "restores_ac": "FR-01.03.AC05"}]}

The catalog is read from ``--base-ref`` (git), never the working tree. AC text must read as an outcome (exit 2
otherwise). The operator is asked only when an existing AC is changed or removed, no single FR owns a new AC,
or a new area (``new_fr``) is proposed. Before the build the diff is empty: ``exempt`` is then only a claim, and
F11 tests it against the committed diff (a warning).

Unattended runs (campaign environment or worktree, or ``--autonomous``) refuse inline answers; answers come from
the operator channel: ``answer`` refuses to run unattended unless ``SHIPWRIGHT_AC_OPERATOR_CHANNEL`` is set (a
guard, not authentication), and binds the answer to the sha256 of run id + item index + question text. Re-run a
held unit: ``loop_claim.py mark --status pending``, then run the unit again with ``--answers``.

Exit codes: 0 every item decided; 10 a question must go to the operator (unattended: the printed ``escalation``
holds ONLY this unit); 2 the declaration or an input is invalid (``errors`` / ``error`` says what to fix).
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
from lib.ac_hold import AC_HOLD_REASON, OPERATOR_ENV, is_unattended, operator_channel_open  # noqa: E402
from lib.ac_record import verify  # noqa: E402
from lib.ac_surface import git_changes, observable_files  # noqa: E402
from lib.ac_wording import diff_identifiers  # noqa: E402

EXIT_OK, EXIT_ASK, EXIT_INVALID = 0, 10, 2


class _Fail(Exception):
    """An input problem: reported as one JSON line on stderr, exit 2, never a traceback."""


def read_text(path: str) -> str:
    """Read a text file that may carry a UTF-8 or UTF-16 byte-order mark (PowerShell writes both)."""
    try:
        raw = Path(path).read_bytes()
    except OSError as exc:
        raise _Fail(f"{path} unreadable: {exc}") from exc
    if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
        enc = "utf-16"
    elif raw[:3] == b"\xef\xbb\xbf":
        enc = "utf-8-sig"
    else:
        enc = "utf-8"
    try:
        return raw.decode(enc)
    except UnicodeDecodeError as exc:
        raise _Fail(f"{path} is not valid {enc} text: {exc}") from exc


def _load(path: str, what: str) -> object:
    try:
        return json.loads(read_text(path))
    except ValueError as exc:
        raise _Fail(f"{what} ({path}) is not valid JSON: {exc}") from exc


def _escalation(result: dict, sub_iterate_id: str) -> dict:
    """The sub-iterate result.json body for an ask in an unattended run (a standalone run records an operator-only-decision blocker)."""
    return {"sub_iterate_id": sub_iterate_id, "status": "escalated", "reason_code": AC_HOLD_REASON,
            "reason": f"{AC_HOLD_REASON}: the operator must answer {len(result['questions'])} question(s) about what the product promises before this unit is built",
            "ac_questions": [{"item": q["item"], "row": q["row"], "question": q["question"], "question_sha256": q["question_sha256"]} for q in result["questions"]]}


def run_answer(argv: list[str]) -> int:
    """Record the operator's answer, bound to the sha256 of the question it answers."""
    ap = argparse.ArgumentParser(prog="ac_decision.py answer")
    ap.add_argument("--decided", required=True, help="decided.json (--out) or the held unit's result.json")
    ap.add_argument("--item", type=int, required=True)
    ap.add_argument("--choice", required=True, choices=["yes", "no"])
    ap.add_argument("--text-file", default="", help="the operator's wording / owning FR id (a file, never a command line)")
    ap.add_argument("--answers", required=True, help="answer file to create or extend")
    args = ap.parse_args(argv)
    if is_unattended(Path.cwd()) and not operator_channel_open():
        raise _Fail(f"this is an unattended run: only the operator answers, from their own session or with {OPERATOR_ENV} set (a guard, not authentication)")
    data = _load(args.decided, "--decided")
    pool = (data.get("questions") or data.get("ac_questions") or (data.get("escalation") or {}).get("ac_questions")) if isinstance(data, dict) else None
    qs = [q for q in pool if isinstance(q, dict) and q.get("item") == args.item and q.get("question_sha256")] if isinstance(pool, list) else []
    if not qs:
        raise _Fail(f"{args.decided} holds no open question for item {args.item}")
    text = read_text(args.text_file).strip() if args.text_file else ""
    prior = _load(args.answers, "--answers") if Path(args.answers).exists() else {"answers": []}
    kept = [a for a in (prior.get("answers", []) if isinstance(prior, dict) else []) if isinstance(a, dict) and a.get("item") != args.item]
    kept.append({"item": args.item, "question_sha256": qs[0]["question_sha256"], "choice": args.choice, "text": text, "via": "operator"})
    Path(args.answers).write_text(json.dumps({"answers": kept}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"recorded": True, "item": args.item, "question_sha256": qs[0]["question_sha256"]}))
    return EXIT_OK


def run_verify(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="ac_decision.py verify")
    ap.add_argument("--project-root", default=".")
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--base-ref", required=True)
    args = ap.parse_args(argv)
    try:
        problems = verify(args.project_root, args.run_id, args.base_ref, None)
    except (RuntimeError, OSError) as exc:
        raise _Fail(f"cannot compare against {args.base_ref}: {exc}") from exc
    print(json.dumps({"problems": problems}, indent=2, ensure_ascii=False))
    return EXIT_OK


def run_decide(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--project-root", default=".")
    ap.add_argument("--from-json", required=True)
    ap.add_argument("--base-ref", default="origin/main", help="the ref the change branches from (catalog and observable surface are read against it)")
    ap.add_argument("--run-id", default="", help="binds the operator's answers to this run (needed with --answers or when unattended)")
    ap.add_argument("--answers", default="", help="the operator's answer file (ac_decision.py answer)")
    ap.add_argument("--autonomous", action="store_true", help="only ever makes the run stricter; unattended is also read from the campaign environment")
    ap.add_argument("--sub-iterate-id", default="")
    ap.add_argument("--out", default="", help="also write the decision JSON to this file")
    args = ap.parse_args(argv)
    unattended = args.autonomous or is_unattended(Path(args.project_root))
    if unattended and not args.sub_iterate_id:
        raise _Fail("--sub-iterate-id is required in an unattended run (the escalation names the unit it holds)")
    if (unattended or args.answers) and not args.run_id:
        raise _Fail("--run-id is required in an unattended run or with --answers (answers are bound to the run)")
    data = _load(args.from_json, "--from-json")
    if not isinstance(data, dict):
        raise _Fail("--from-json must hold a JSON object")
    answers = None
    if args.answers:
        loaded = _load(args.answers, "--answers")
        answers = loaded.get("answers") if isinstance(loaded, dict) else None
    try:
        catalog = load_catalog(args.project_root, args.base_ref)
    except (RuntimeError, OSError) as exc:
        raise _Fail(str(exc)) from exc
    surface, idents = None, None
    try:
        changes = git_changes(args.project_root, args.base_ref)
        surface, idents = observable_files(changes), diff_identifiers(changes)
    except (RuntimeError, OSError) as exc:
        print(f"ac_decision: diff unavailable ({exc}); the exemption can only be tested at F11", file=sys.stderr)
    result = decide(data.get("items"), catalog, unattended, surface, idents, answers, args.run_id)
    result["exemption_check"] = ("tested against the current diff" if surface and (surface["observable"] or surface["ignored"]) else
                                 "a claim only: the diff is empty before the build; F11 tests it against the committed diff (a warning)")
    if surface is not None:
        result["surface"] = surface
    if result["status"] == "ask" and unattended:
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
    sub = {"answer": run_answer, "verify": run_verify}.get(argv[0]) if argv else None
    try:
        return sub(argv[1:]) if sub else run_decide(argv)
    except _Fail as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return EXIT_INVALID


if __name__ == "__main__":
    sys.exit(main())
