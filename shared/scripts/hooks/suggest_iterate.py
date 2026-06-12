#!/usr/bin/env python3
"""UserPromptSubmit hook: phase-aware skill router for Shipwright projects.

Detects user intent and suggests the appropriate Shipwright skill.
Registered in plugins/shipwright-iterate/hooks/hooks.json (UserPromptSubmit)
since iterate-20260505-plugin-hook-registration. Fires for every prompt
in any project carrying shipwright_run_config.json when the
shipwright-iterate@shipwright plugin is enabled.

Routing logic:
- For completed pipelines: matches phase-specific keywords first (test, deploy, etc.),
  falls back to /shipwright-iterate for code changes.
- For in-progress pipelines: warns when user intent doesn't match current pipeline step.
"""

import json
import re
import sys
from pathlib import Path

# Multilingual pattern registry — en + de now, extensible for fr/it later
PHASE_PATTERNS: dict[str, dict[str, str]] = {
    "test": {
        "en": r"\b(run|execute|check|verify)\s+(\w+\s+)?(tests?|test suite|unit tests?|e2e|visual|design fidelity)\b",
        "de": r"\b(tests?\s+(laufen|ausführen|machen|starten|prüfen|nochmal)|teste\b|nochmal\s+\w*\s*tests?)",
    },
    "deploy": {
        "en": r"\b(deploy\w*|push to prod|go live|publish|rollback)\b",
        "de": r"\b(deploy\w*|veröffentlich\w*|ausroll\w*|live\s+stell\w*|rollback)\b",
    },
    "compliance": {
        "en": r"\b(compliance|audit|traceability|SBOM|evidence)\b",
        "de": r"\b(compliance|audit|nachverfolgbarkeit|SBOM|nachweis)\b",
    },
    "changelog": {
        "en": r"\b(changelog|release notes|version bump|tag release)\b",
        "de": r"\b(changelog|release notes|version|release erstellen)\b",
    },
    "design": {
        "en": r"\b(design|mockup|wireframe|screen|UI design|layout)\s+(change|update|create|iterate)\b",
        "de": r"\b(design|mockup|wireframe|layout)\s+(ändern|anpassen|erstellen|überarbeiten)\b",
    },
    "plan": {
        "en": r"\b(replan|implementation plan|technical design)\b",
        "de": r"\b(umplanen|neu planen|technisches design|implementierungsplan)\b",
    },
}

SKILL_NAMES: dict[str, str] = {
    "test": "/shipwright-test",
    "deploy": "/shipwright-deploy",
    "compliance": "/shipwright-compliance",
    "changelog": "/shipwright-changelog",
    "design": "/shipwright-design",
    "plan": "/shipwright-plan",
}


def matches_phase(prompt: str, phase: str) -> bool:
    """Match against ALL configured languages for a given phase."""
    return any(
        re.search(pat, prompt, re.IGNORECASE)
        for pat in PHASE_PATTERNS[phase].values()
    )


def detect_phase_intent(prompt: str) -> str | None:
    """Return the first matching phase name, or None."""
    for phase in PHASE_PATTERNS:
        if matches_phase(prompt, phase):
            return phase
    return None


def handle_completed_pipeline(
    prompt: str, project_root: Path, run_config: dict
) -> dict | None:
    """Route intent for completed pipelines. Returns hook output or None."""
    # Phase-specific routing first
    phase = detect_phase_intent(prompt)
    if phase:
        skill = SKILL_NAMES[phase]
        return {
            "hookSpecificOutput": {
                "hookEventName": "UserPromptSubmit",
                "additionalContext": (
                    f"[Shipwright] Detected intent: {phase}\n"
                    f"Pipeline is complete. Suggested skill: {skill}\n"
                    f"Invoke {skill} to handle this request."
                ),
            }
        }

    # Fall back to iterate classification for code changes
    return classify_for_iterate(prompt, project_root)


def handle_in_progress_pipeline(
    prompt: str, project_root: Path, run_config: dict
) -> dict | None:
    """Route intent for in-progress pipelines.

    After test completion, non-phase prompts fall through to iterate so
    code-change requests don't get dropped while changelog/deploy/compliance
    remain pending.
    """
    current_step = run_config.get("current_step", "unknown")
    completed_steps = set(run_config.get("completed_steps", []))
    phase = detect_phase_intent(prompt)

    if phase and phase != current_step:
        skill = SKILL_NAMES[phase]
        return {
            "hookSpecificOutput": {
                "hookEventName": "UserPromptSubmit",
                "additionalContext": (
                    f"[Shipwright] Intent mismatch: you asked about '{phase}' "
                    f"but the pipeline is at step '{current_step}'.\n"
                    f"To run {skill} standalone, invoke it directly. "
                    f"To continue the pipeline, use /shipwright-run."
                ),
            }
        }

    if phase is None and "test" in completed_steps:
        return classify_for_iterate(prompt, project_root)

    return None


def classify_for_iterate(prompt: str, project_root: Path) -> dict | None:
    """Existing iterate classification logic."""
    repo_root = Path(__file__).resolve().parent.parent.parent.parent
    sys.path.insert(
        0,
        str(repo_root / "plugins" / "shipwright-iterate" / "scripts" / "lib"),
    )

    try:
        from classify_intent import classify
    except ImportError:
        return None

    sync_config_path = project_root / "shipwright_sync_config.json"
    result = classify(
        prompt,
        str(sync_config_path) if sync_config_path.exists() else None,
    )

    if result["type"] == "none" or result["confidence"] < 0.7:
        return None

    intent_type = result["type"].upper()
    frs = ", ".join(result["affected_frs"]) if result["affected_frs"] else "TBD"
    summary = result["summary"]

    return {
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": (
                f"[Shipwright] Detected: {intent_type} — {summary}\n"
                f"Affected FRs: {frs}\n"
                f"Before making code changes, invoke /shipwright-iterate "
                f"--type {result['type']} to keep specs, tests, and ADRs in sync."
            ),
        }
    }


def main():
    # Read hook input from stdin
    try:
        hook_input = json.loads(sys.stdin.read())
    except (json.JSONDecodeError, EOFError):
        sys.exit(0)

    prompt = hook_input.get("prompt", "").strip()
    cwd = hook_input.get("cwd", ".")

    project_root = Path(cwd)

    # Guard 1: Is this a Shipwright project?
    run_config_path = project_root / "shipwright_run_config.json"
    if not run_config_path.exists():
        sys.exit(0)

    # Guard 2: Read config
    # WP8/F24: explicit UTF-8 (utf-8-sig tolerates an optional BOM from a
    # hand-edited config) — a CJK / Cyrillic project description (written
    # ensure_ascii=False) otherwise crashes this hook on the cp1252 Windows
    # dev platform for every prompt. A truly malformed config fails soft
    # (the hook is advisory; sys.exit(0) lets the prompt through).
    try:
        run_config = json.loads(run_config_path.read_text(encoding="utf-8-sig"))
    except (json.JSONDecodeError, FileNotFoundError, UnicodeDecodeError):
        sys.exit(0)

    # Guard 3: Skip slash commands (user already chose a skill)
    if prompt.startswith("/"):
        sys.exit(0)

    # Guard 4: Skip very short messages (greetings, acknowledgments)
    if len(prompt) < 10:
        sys.exit(0)

    status = run_config.get("status")

    # Route based on pipeline status
    if status == "complete":
        output = handle_completed_pipeline(prompt, project_root, run_config)
    elif status == "in_progress":
        output = handle_in_progress_pipeline(prompt, project_root, run_config)
    else:
        sys.exit(0)

    if output:
        print(json.dumps(output))

    sys.exit(0)


if __name__ == "__main__":
    main()
