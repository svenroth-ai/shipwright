"""Decide the pre-build acceptance-criterion declaration of a feature/change iterate: ask or auto.

    uv run shared/scripts/tools/ac_decision.py --project-root . --from-json ac.json [--autonomous] [--out decided.json]

``ac.json`` (written with the Write tool; free text never goes through a shell command line)::

    {"items": [{"kind": "add|change|remove|restore|exempt", "ac": "FR-01.03.AC05", "owner_fr": "FR-01.03",
                "old_text": "...", "new_text": "...", "plain_new": "one outcome sentence", "plain_old": "...",
                "restores_ac": "FR-01.03.AC05", "exempt_kind": "no-observable-change|how-only",
                "exempt_reason": "what stays the same for users and operators", "request_open": false,
                "answer": {"choice": "yes|no|only-how", "text": "..."}}]}

Exit codes: 0 every item decided (``ac_decisions`` and ``frozen_hash`` printed - hand them to write_plan_stub);
10 a question must go to the operator (interactive: ask it; ``--autonomous``: the printed ``escalation`` is the
unit's stop - never auto-approve); 2 the declaration is invalid (``errors`` says what to fix).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_SCRIPTS_ROOT = Path(__file__).resolve().parent.parent
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from lib.ac_decision import decide, load_catalog_acs  # noqa: E402

EXIT_OK, EXIT_ASK, EXIT_INVALID = 0, 10, 2
REASON_CODE = "ac_question_requires_operator"


def _escalation(result: dict) -> dict:
    """The sub-iterate result.json body for an ask under ``--autonomous`` (a standalone run records an operator-only-decision blocker instead)."""
    return {"status": "escalated", "reason_code": REASON_CODE,
            "reason": f"{REASON_CODE}: the operator must answer {len(result['questions'])} question(s) about what the product promises before this unit is built",
            "ac_questions": [{"item": q["item"], "row": q["row"], "question": q["text"]} for q in result["questions"]]}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--project-root", default=".")
    ap.add_argument("--from-json", required=True)
    ap.add_argument("--autonomous", action="store_true")
    ap.add_argument("--out", default="", help="also write the decision JSON to this file")
    args = ap.parse_args()
    try:
        data = json.loads(Path(args.from_json).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        ap.error(f"--from-json unreadable: {exc}")
    if not isinstance(data, dict):
        ap.error("--from-json must hold a JSON object")
    result = decide(data.get("items"), load_catalog_acs(args.project_root), args.autonomous)
    if result["status"] == "ask" and args.autonomous:
        result["escalation"] = _escalation(result)
    text = json.dumps(result, indent=2, ensure_ascii=False)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8", newline="\n")
    print(text)
    return {"ok": EXIT_OK, "ask": EXIT_ASK}.get(result["status"], EXIT_INVALID)


if __name__ == "__main__":
    sys.exit(main())
