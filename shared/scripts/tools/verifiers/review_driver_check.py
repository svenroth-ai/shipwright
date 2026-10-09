"""F11 evidence check: a Codextender run's external review used the codex roster.

Under Codextender a GPT-family model authors the diff, so a ``driver=claude``
external review (glm + openai) is the author's own vendor reviewing it. The tool
(``external_review.py``) now coerces the typed flag; this gate is the
after-the-fact evidence that no raw review record says otherwise.

Evidence, strongest first:
  * the raw JSON itself carries ``codextender_active: true`` (written by the
    enforcing tool) yet ``driver == "claude"`` — contradictory, hand-edited or
    produced by a bypass;
  * the raw JSON has ``driver == "claude"`` while this F11 process runs under
    ``CODEXTENDER_ACTIVE`` — whatever the record's own flag says (no key: it
    predates the enforcement; ``false``: the review shell lost the env, the most
    likely real bypass, so the session signal wins).

Not covered (stated, not implied): ``llm_review.run_review`` envelopes (adopt
Layer-3) are not persisted per run, and a raw file that does not parse is
skipped — payload integrity belongs to the review-record gate.

Skipped when the run left no raw record or the session is not Codextender and no
record claims it. Unreadable raw JSON is not this gate's concern (the review
record gate owns payload integrity).
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

_SCRIPTS_ROOT = Path(__file__).resolve().parents[2]
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from lib.external_review_routing import codextender_active  # noqa: E402
from lib.review_record import is_safe_run_id  # noqa: E402

from .common import CheckResult, Severity  # noqa: E402

CHECK_NAME = "external review driver matches Codextender session"
RAW_NAMES = ("external-plan-review-raw.json", "external-code-review-raw.json")


def _load(path: Path) -> dict | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def check_review_driver(
    project_root: Path, run_id: str, environ: dict[str, str] | None = None,
) -> CheckResult:
    if not is_safe_run_id(run_id):
        return CheckResult(CHECK_NAME, None, "skipped (unsafe run id)", severity=Severity.SKIPPED.value)
    run_dir = project_root / ".shipwright" / "planning" / "iterate" / run_id
    session_active = codextender_active(environ if environ is not None else os.environ)
    seen = 0
    bad: list[str] = []
    for name in RAW_NAMES:
        raw = _load(run_dir / name)
        if raw is None:
            if session_active and (run_dir / name).is_file():
                bad.append(f"{name}: unreadable (not JSON/UTF-8) while this session is Codextender")
            continue
        if raw.get("provider") == "gateway":
            continue  # operator-chosen models: vendor independence is not attested here
        seen += 1
        driver = raw.get("driver")
        if driver == "codex" or (driver != "claude" and not session_active):
            continue
        if driver == "claude" and raw.get("codextender_active") is True:
            bad.append(f"{name}: driver=claude but the record itself says codextender_active")
        elif session_active:  # also when the record says "inactive": its shell lost the env
            bad.append(f"{name}: driver={driver or 'missing'} while this session is Codextender")
    if bad:
        return CheckResult(
            CHECK_NAME, False,
            "; ".join(bad) + " — a GPT-built diff was externally reviewed by the same "
            "vendor. Re-run `external_review.py` (it coerces to driver=codex, glm + opus) "
            "and re-record the pass. (If the review truly ran outside Codextender, re-run "
            "F11 outside Codextender.)",
        )
    if not seen:
        return CheckResult(CHECK_NAME, None, "skipped (no raw external review record)",
                           severity=Severity.SKIPPED.value)
    return CheckResult(CHECK_NAME, True, f"{seen} raw review record(s) consistent with the session driver")
