"""Apply-time guard for a by-rule screenshot override: the rule itself is re-run under the lock (ADR-045: loaded by path)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_SHOT = "Screenshot check did not pass"
_RULE = Path(__file__).resolve().parent.parent / "autonomous_override.py"


def by_rule_refusal(project_root, ask_issues) -> str | None:
    """Why an ``autonomous rule:`` override must not proceed (None = the rule allows it for exactly this gate verdict)."""
    messages = [str(i.get("message", "")) for i in ask_issues]
    stray = [m for m in messages if not m.startswith(_SHOT)]
    if stray or not messages:
        return f"an 'autonomous rule' override may only cover the screenshot finding; the gate also holds {stray[:2]}"
    if project_root is None:
        return "an 'autonomous rule' override needs the project root to re-run the rule"
    try:
        spec = importlib.util.spec_from_file_location("_shipwright_apply_autonomous_override", _RULE)
        rule = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = rule
        spec.loader.exec_module(rule)
        out = rule.decide_screenshot_override(Path(project_root), gate=messages)
    except Exception as exc:  # noqa: BLE001 - the guard fails closed
        return f"the autonomous override rule could not be re-run ({type(exc).__name__})"
    return None if out.get("allowed") else "the autonomous override rule no longer allows it: " + "; ".join(out.get("reasons", []))[:500]
