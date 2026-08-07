#!/usr/bin/env python3
"""Readiness check: is context checkpointing actually configured to fire?

Same report shape as ``verify_local.py`` (a list of named checks, each
``pass``/``warn`` with a message) but for two settings this feature cannot
measure after the fact: ``autoCompactWindow`` and the reasoning-effort
level. A context-cost meter that reports a big number after the window
already blew out helps nobody — this exists to catch that BEFORE it
happens, not after.

**Both checks are honest about what a plain script can and cannot see.**
Claude Code does not expose the currently-active model or effort level to
a subprocess — no settings key, no environment variable, nothing a script
can read. Guessing one (e.g. "assume Sonnet 5") would be the exact kind of
unfounded inference this feature's own pricing code (``model_pricing.py``)
refuses to do for an unrecognized model id — silently wrong is worse than
visibly unknown. So ``--model``/``--effort`` are accepted as EXPLICIT,
un-defaulted inputs: when given, the check is precise; when omitted, the
report says so and still surfaces what IS knowable without them (whether
``autoCompactWindow`` is set at all).

``autoCompactWindow`` is read from Claude Code's real settings hierarchy —
user (``~/.claude/settings.json``), shared-project (``.claude/settings.json``),
local-project (``.claude/settings.local.json``, git-ignored) — later files
override earlier ones, each read defensively (missing or malformed JSON is
treated as absent, never crashes the check).

Usage:
    uv run context_cost_readiness.py [--model <id>] [--effort <level>]

Output (JSON): {"checks": [{"name", "status": "pass"|"warn", "message"}]}
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from lib import model_pricing  # noqa: E402

# Context windows, same authoritative source as model_pricing.py's $/MTok
# table (claude-api skill, cached 2026-06-24) — not re-derived, not guessed.
# Keyed identically to model_pricing.MODEL_PRICING so model_pricing.
# resolve_model_id's exact-then-date-stripped policy applies here unchanged
# (external-review finding, iterate-2026-08-07-context-cost-meter: a real
# dated snapshot id like "claude-sonnet-5-20260612" was read back as "not a
# known model" by this table's own bare MODEL_CONTEXT_WINDOWS.get(model)).
MODEL_CONTEXT_WINDOWS = {
    "claude-opus-5": 1_000_000,
    "claude-sonnet-5": 1_000_000,
    "claude-haiku-4-5": 200_000,
}

_VALID_EFFORT_LEVELS = {"low", "medium", "high", "xhigh", "max"}

_SETTINGS_LOCATIONS = (
    "user",
    "shared-project",
    "local-project",
)


def _read_json_defensively(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


def read_settings_hierarchy(project_root: Path, home: Path | None = None) -> dict:
    """Merge Claude Code's real settings files, later overriding earlier.

    Order: user (``~/.claude/settings.json``) < shared-project
    (``.claude/settings.json``) < local-project
    (``.claude/settings.local.json``) — matches Claude Code's own
    documented precedence for these three file-based layers.
    """
    home = home or Path.home()
    merged: dict = {}
    for path in (
        home / ".claude" / "settings.json",
        project_root / ".claude" / "settings.json",
        project_root / ".claude" / "settings.local.json",
    ):
        merged.update(_read_json_defensively(path))
    return merged


def _resolve_project_root() -> Path:
    try:
        from lib.project_root import resolve_project_root  # noqa: PLC0415

        return resolve_project_root()
    except (ImportError, ValueError):
        env_root = os.environ.get("SHIPWRIGHT_PROJECT_ROOT")
        return Path(env_root) if env_root else Path.cwd()


def check_autocompact_window(value, model: str | None) -> dict:
    """One check: is ``autoCompactWindow`` set, and does it fit the model?"""
    if value is None:
        return {
            "name": "autoCompactWindow",
            "status": "warn",
            "message": "not set in any settings file — Claude Code falls back to its "
                       "own default; set it explicitly for deterministic checkpointing.",
        }
    if not isinstance(value, (int, float)) or value <= 0:
        return {
            "name": "autoCompactWindow",
            "status": "warn",
            "message": f"set to a non-positive or non-numeric value ({value!r}) — ignored.",
        }
    if model is None:
        return {
            "name": "autoCompactWindow",
            "status": "warn",
            "message": f"set to {int(value):,} tokens, but no --model was given — cannot "
                       "verify it fits the active model's context window.",
        }
    canonical = model_pricing.resolve_model_id(model)
    context_window = MODEL_CONTEXT_WINDOWS.get(canonical) if canonical else None
    if context_window is None:
        return {
            "name": "autoCompactWindow",
            "status": "warn",
            "message": f"set to {int(value):,} tokens, but '{model}' is not a known model "
                       "— cannot verify it fits that model's context window.",
        }
    if value > context_window:
        return {
            "name": "autoCompactWindow",
            "status": "warn",
            "message": f"set to {int(value):,} tokens, which EXCEEDS {model}'s "
                       f"{context_window:,}-token context window — auto-compaction "
                       "would never trigger before the window is exhausted.",
        }
    return {
        "name": "autoCompactWindow",
        "status": "pass",
        "message": f"set to {int(value):,} tokens, within {model}'s {context_window:,}-token "
                   "context window.",
    }


def check_effort_level(effort: str | None) -> dict:
    """One check: is a reasoning-effort level known and recognized?"""
    if effort is None:
        return {
            "name": "effort level",
            "status": "warn",
            "message": "not specified — Claude Code does not expose the active session's "
                       "effort level to a script; pass --effort to check it.",
        }
    if effort not in _VALID_EFFORT_LEVELS:
        return {
            "name": "effort level",
            "status": "warn",
            "message": f"'{effort}' is not a recognized effort level "
                       f"({', '.join(sorted(_VALID_EFFORT_LEVELS))}).",
        }
    return {
        "name": "effort level",
        "status": "pass",
        "message": f"'{effort}' in force.",
    }


def run_readiness_checks(settings: dict, model: str | None, effort: str | None) -> list[dict]:
    return [
        check_autocompact_window(settings.get("autoCompactWindow"), model),
        check_effort_level(effort),
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default=None, help="Active model id (no default — see docstring)")
    parser.add_argument("--effort", default=None, help="Active effort level (no default — see docstring)")
    args = parser.parse_args(argv)

    project_root = _resolve_project_root()
    settings = read_settings_hierarchy(project_root)
    checks = run_readiness_checks(settings, args.model, args.effort)

    print(json.dumps({"checks": checks}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
