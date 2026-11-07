"""Decide the pre-build acceptance-criterion declaration of an iterate: ask or auto.

    uv run shared/scripts/tools/ac_decision.py --project-root . --from-json ac.json --base-ref {base_branch} \
        --run-id RID [--bind-id STABLE_ID] [--nonce CAMPAIGN_CREATED_AT] [--answers answers.json] [--autonomous --sub-iterate-id Q1] [--ac-mode ask|auto|off] [--out decided.json] [--no-suggest]

    uv run shared/scripts/tools/ac_decision.py answer --decided decided.json|result.json --item 0 --choice 1|2|3 \
        [--text-file wording.txt] --answers answers.json        # the OPERATOR's channel

    uv run shared/scripts/tools/ac_decision.py verify --project-root . --run-id RID --base-ref {base_branch}
        # the finalize-time compare against the working tree / diff: prints the same problems F11 warns about

``ac.json`` is written with the Write tool (free text never goes through a shell command line)::

    {"items": [{"kind": "add|change|remove|restore|unchanged|exempt", "ac": "FR-01.03.AC05", "owner_fr": "FR-01.03",
                "new_fr": {"id": "FR-01.30", "title": "one sentence"}, "old_text": "...", "new_text": "outcome wording",
                "restores_ac": "FR-01.03.AC05",
                "files": ["plugins/x/scripts/a.py"]}]}      # files: required for kind unchanged (observable files change, promise stays); for an add, the paths this
                                                                # work will change (before the build the diff is empty) - they only feed the question's "Part:" line

With ``--run-id`` the mode actually used (even ``off``) is written to ``.shipwright/planning/iterate/<run_id>/ac-mode.json`` for F11 - commit it with the run.

``--base-ref`` is required: it is resolved to merge-base(base-ref, HEAD) and the catalog is read there (git), never from
the working tree. ``--bind-id`` is the run's STABLE id (for a campaign unit ``{campaign_slug}--{unit_id}``, never an
attempt id), so a re-dispatched unit gets the same question hashes; it defaults to ``--run-id``. An answer is bound to that id (plus ``--nonce``, the campaign's created_at), the item index, the kind, the ORIGINAL promise text and the options map - never to the rendered question, so a moved base cannot invalidate it. The question shows your own AC wording unchanged and the requirement's name from the spec; a small model only proposes which requirement a new AC belongs to, one plain line about it and a draft of a new one (``--no-suggest`` skips it; code checks the id and every line). AC text must read as an outcome (exit 2
otherwise). The operator is asked only when an existing AC is changed or removed, no single FR owns a new AC,
or a new area (``new_fr``) is proposed. Before the build the diff is empty: ``exempt`` is then only a claim, and
F11 tests it against the committed diff (a warning).

Modes (``--ac-mode``, ``SHIPWRIGHT_AC_MODE``, ``ac_decision.mode`` in ``shipwright_iterate_config.json``): ``ask`` asks as above (default for an interactive iterate); ``auto`` asks nothing - Shipwright
takes its own pick (the model's requirement, else the best match, else a drafted new requirement), records it ``auto-assigned`` and ``unconfirmed``, and prints the short list "assignments made without you"
(``unconfirmed_assignments`` in the JSON, stderr), changed or removed criteria first - the DEFAULT when unattended; ``off`` does nothing (``skipped``).

Unattended runs (both campaign loop variables, or a per-unit campaign worktree, or ``--autonomous``) refuse inline
answers; answers come from the operator channel: ``answer`` refuses to run unattended unless
``SHIPWRIGHT_AC_OPERATOR_CHANNEL`` is set (the orchestrator shell needs it), binds the answer to the sha256 of the
stable id + item index + kind + original promise + options (not the question's wording), and signs it with a per-user key (``~/.shipwright/ac_operator.key``).
``answered_via`` and ``unattended`` are self-reported; the signature is a guard against accident and casual forgery,
not authentication: a determined agent with shell access can read the key. Re-run a held unit: ``loop_claim.py mark
--status pending --reason ... --operator ...``, then run the unit again with ``--answers`` and the same ``--bind-id``.

Exit codes: 0 every item decided; 10 a question must go to the operator (unattended: the printed ``escalation``
holds ONLY this unit); 11 the operator answered "I do not understand this": reword the promise in plainer words (``explain`` names the items) and run again - the new wording is asked again; 2 the declaration or an input is invalid (``errors`` / ``error`` says what to fix).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

_SCRIPTS_ROOT = Path(__file__).resolve().parent.parent
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from lib.ac_apply import ANSWERS  # noqa: E402
from lib.ac_catalog import load_catalog  # noqa: E402
from lib.ac_decision import decide  # noqa: E402
from lib.ac_mode import MODES, is_safe_run_id, resolve_mode, write_marker  # noqa: E402
from lib.ac_hold import AC_HOLD_REASON, OPERATOR_ENV, is_unattended, load_key, operator_channel_open, sign  # noqa: E402
from lib.ac_record import verify  # noqa: E402
from lib.ac_suggest import make_suggester  # noqa: E402
from lib.ac_surface import git_changes, merge_base, observable_files  # noqa: E402
from lib.ac_wording import diff_identifiers  # noqa: E402

EXIT_OK, EXIT_ASK, EXIT_EXPLAIN, EXIT_INVALID = 0, 10, 11, 2
_BAD_RUN_ID = "--run-id must be a plain run id (letters, digits, '_', '.', '-'; no '..')"


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


def _escalation(result: dict, sub_iterate_id: str, bind_id: str) -> dict:
    """The sub-iterate result.json body for an ask in an unattended run (a standalone run records an operator-only-decision blocker)."""
    return {"sub_iterate_id": sub_iterate_id, "status": "escalated", "reason_code": AC_HOLD_REASON, "bind_id": bind_id,
            "reason": f"{AC_HOLD_REASON}: the operator must answer {len(result['questions'])} question(s) about what the product promises before this unit is built",
            "ac_questions": [{"item": q["item"], "row": q["row"], "question": q["question"], "question_sha256": q["question_sha256"], "kind": q["kind"], "promise": q["promise"], "options": q["options"],
                             **({"suggestion_source": q["suggestion_source"]} if q.get("suggestion_source") else {})} for q in result["questions"]]}


def run_answer(argv: list[str]) -> int:
    """Record the operator's answer, bound to the sha256 of the question it answers."""
    ap = argparse.ArgumentParser(prog="ac_decision.py answer")
    ap.add_argument("--decided", required=True, help="decided.json (--out) or the held unit's result.json")
    ap.add_argument("--item", type=int, required=True)
    ap.add_argument("--choice", required=True, help="the option NUMBER the operator picked (1, 2, ...), or yes | no | new_fr | explain")
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
    choice = args.choice
    picked = (qs[0].get("options") or {}).get(choice)
    if isinstance(picked, dict):  # an option NUMBER of the question: the requirement id stays in the machine record, the operator never types it
        if not isinstance(picked.get("choice"), str):
            raise _Fail(f"option {choice} of the stored question has no usable choice")
        choice, text = picked["choice"], picked.get("text") or text
    elif choice not in ANSWERS:
        raise _Fail(f"--choice must be {', '.join(ANSWERS)} or an option number of the question, not {choice!r}")
    prior = _load(args.answers, "--answers") if Path(args.answers).exists() else {"answers": []}
    sha = qs[0]["question_sha256"]
    kept = [a for a in (prior.get("answers", []) if isinstance(prior, dict) else []) if isinstance(a, dict) and (a.get("item") != args.item or a.get("question_sha256") != sha)]
    try:
        key = load_key(create=True)
    except RuntimeError as exc:
        raise _Fail(str(exc)) from exc
    stored = {k: v for k, v in qs[0].items() if k.startswith("suggestion_")}  # the options come from the STORED question the operator saw, never from the caller
    kept.append({"item": args.item, "question_sha256": sha, "choice": choice, "text": text, "options": qs[0].get("options") or {}, **stored,
                 "via": "operator", "signature": sign(key, sha, choice, text)})
    target = Path(args.answers)
    tmp = target.with_name(target.name + ".tmp")  # temp file + replace: a crash never leaves half an answer file
    tmp.write_text(json.dumps({"answers": kept}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    os.replace(tmp, target)
    print(json.dumps({"recorded": True, "item": args.item, "question_sha256": qs[0]["question_sha256"]}))
    return EXIT_OK


def run_verify(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="ac_decision.py verify")
    ap.add_argument("--project-root", default=".")
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--base-ref", required=True, help="the ref the change branches from; resolved to merge-base(base-ref, HEAD)")
    args = ap.parse_args(argv)
    if not is_safe_run_id(args.run_id):
        raise _Fail(_BAD_RUN_ID)
    try:
        base = merge_base(args.project_root, args.base_ref)
        catalog = load_catalog(args.project_root, base)
        problems = verify(args.project_root, args.run_id, base, None, catalog)
    except (RuntimeError, OSError) as exc:
        raise _Fail(f"cannot compare against {args.base_ref}: {exc}") from exc
    note = "skipped: the requirement catalog has text but no FR heading this tool can read" if catalog["unparsed"] else ""
    print(json.dumps({"problems": problems, **({"note": note} if note else {})}, indent=2, ensure_ascii=False))
    return EXIT_OK


def run_decide(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--project-root", default=".")
    ap.add_argument("--from-json", required=True)
    ap.add_argument("--base-ref", required=True, help="the ref the change branches from; resolved to merge-base(base-ref, HEAD), where the catalog and the diff are read")
    ap.add_argument("--bind-id", default="", help="the run's STABLE id for answer binding (campaign unit: {campaign_slug}--{unit_id}); default --run-id")
    ap.add_argument("--run-id", default="", help="binds the operator's answers to this run (needed with --answers or when unattended)")
    ap.add_argument("--answers", default="", help="the operator's answer file (ac_decision.py answer)")
    ap.add_argument("--autonomous", action="store_true", help="only ever makes the run stricter; unattended is also read from the campaign environment")
    ap.add_argument("--nonce", default="", help="a campaign nonce (the campaign's created_at) added to the bind id, so a recreated campaign with the same slug cannot reuse an old signed answer")
    ap.add_argument("--sub-iterate-id", default="")
    ap.add_argument("--ac-mode", default="", choices=("", *MODES), help="ask | auto | off (the campaign's own setting, passed by the orchestrator); default: SHIPWRIGHT_AC_MODE, then shipwright_iterate_config.json ac_decision.mode, then auto when unattended, else ask")
    ap.add_argument("--no-suggest", action="store_true", help="do not call the model; the deterministic wording and candidates are used")
    ap.add_argument("--out", default="", help="also write the decision JSON to this file")
    args = ap.parse_args(argv)
    if args.run_id and not is_safe_run_id(args.run_id):
        raise _Fail(_BAD_RUN_ID)
    unattended = args.autonomous or is_unattended(Path(args.project_root))
    try:
        mode, mode_source = resolve_mode(args.project_root, args.ac_mode, unattended)
    except ValueError as exc:
        raise _Fail(str(exc)) from exc
    if unattended and mode != "off" and not args.sub_iterate_id:
        raise _Fail("--sub-iterate-id is required in an unattended run (the escalation names the unit it holds)")
    if (unattended or args.answers) and not args.run_id:
        raise _Fail("--run-id is required in an unattended run or with --answers (answers are bound to the run)")
    if args.run_id:  # the mode actually used is written for F11, whatever set it (flag, variable, config); off needs it, because off writes no record
        try:
            _, kept = write_marker(args.project_root, args.run_id, mode, mode_source)
            if kept:
                print(f"ac_decision: this run already has a mode marker; the first one is kept (this run used mode={mode})", file=sys.stderr)
        except OSError as exc:
            raise _Fail(f"cannot write the mode marker for {args.run_id}: {exc}") from exc
    if mode == "off":
        print(json.dumps({"status": "skipped", "unattended": unattended, "ac_mode": {"mode": mode, "source": mode_source},
                          "note": "the pre-build AC decision is switched off (ac mode off): nothing is asked, recorded or checked; do not pass --ac-decision to write_plan_stub.py"}, indent=2))
        return EXIT_OK
    data = _load(args.from_json, "--from-json")
    if not isinstance(data, dict):
        raise _Fail("--from-json must hold a JSON object")
    answers = None
    if args.answers:
        loaded = _load(args.answers, "--answers")
        answers = loaded.get("answers") if isinstance(loaded, dict) else None
    try:
        base = merge_base(args.project_root, args.base_ref)
        catalog = load_catalog(args.project_root, base)
    except (RuntimeError, OSError) as exc:
        raise _Fail(f"cannot read the catalog at {args.base_ref}: {exc}") from exc
    surface, idents, changes = None, None, {}
    try:
        changes = git_changes(args.project_root, base)
        surface, idents = observable_files(changes), diff_identifiers(changes)
    except (RuntimeError, OSError) as exc:
        print(f"ac_decision: diff unavailable ({exc}); the exemption can only be tested at F11", file=sys.stderr)
    bind_id = (args.bind_id or args.run_id) + (f"@{args.nonce}" if args.nonce else "")
    suggester = make_suggester(catalog, args.project_root, not args.no_suggest)
    result = decide(data.get("items"), catalog, unattended, surface, idents, answers, bind_id, suggester, list(changes), mode)
    result["ac_mode"] = {"mode": mode, "source": mode_source}
    result["run_id"], result["bind_id"] = args.run_id, bind_id  # write_plan_stub.py refuses a decided.json made for another run
    result["exemption_check"] = (f"tested against the current diff ({len(changes)} file(s), {surface['ignored']} not observable)" if surface and changes else
                                 "a claim only: the diff is empty before the build; F11 tests it against the committed diff (a warning)")
    if surface is not None:
        result["surface"] = surface
    if result["status"] == "ask" and unattended:
        result["escalation"] = _escalation(result, args.sub_iterate_id, bind_id)
    text = json.dumps(result, indent=2, ensure_ascii=False)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8", newline="\n")
    print(text)
    for line in result.get("unconfirmed_assignments", []):
        print(line, file=sys.stderr)
    return {"ok": EXIT_OK, "ask": EXIT_ASK, "explain": EXIT_EXPLAIN, "skipped": EXIT_OK}.get(result["status"], EXIT_INVALID)


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
