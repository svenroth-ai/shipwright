#!/usr/bin/env python3
"""UserPromptSubmit hook: suggest /shipwright-iterate when code changes are detected.

Installed in project .claude/settings.json by /shipwright-project.
Only fires for completed Shipwright projects.
"""

import json
import sys
from pathlib import Path


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

    # Guard 2: Is the pipeline complete?
    try:
        run_config = json.loads(run_config_path.read_text())
    except (json.JSONDecodeError, FileNotFoundError):
        sys.exit(0)

    if run_config.get("status") != "complete":
        sys.exit(0)

    # Guard 3: Skip slash commands (user already using structured command)
    if prompt.startswith("/"):
        sys.exit(0)

    # Guard 4: Skip very short messages (greetings, acknowledgments)
    if len(prompt) < 10:
        sys.exit(0)

    # Classify intent
    # Import from plugin scripts (resolve relative to this file's location)
    script_dir = Path(__file__).resolve().parent.parent.parent
    sys.path.insert(0, str(script_dir / "plugins" / "shipwright-iterate" / "scripts" / "lib"))

    try:
        from classify_intent import classify
    except ImportError:
        # Plugin not installed — skip silently
        sys.exit(0)

    sync_config_path = project_root / "shipwright_sync_config.json"
    result = classify(
        prompt,
        str(sync_config_path) if sync_config_path.exists() else None,
    )

    # Only suggest if confident
    if result["type"] == "none" or result["confidence"] < 0.7:
        sys.exit(0)

    # Build suggestion message
    intent_type = result["type"].upper()
    frs = ", ".join(result["affected_frs"]) if result["affected_frs"] else "TBD"
    summary = result["summary"]

    context = (
        f"[Shipwright] Detected: {intent_type} — {summary}\n"
        f"Affected FRs: {frs}\n"
        f"Before making code changes, invoke /shipwright-iterate --type {result['type']} "
        f"to keep specs, tests, and ADRs in sync."
    )

    # Output as hookSpecificOutput
    output = {
        "hookSpecificOutput": {
            "additionalContext": context,
        }
    }

    print(json.dumps(output))
    sys.exit(0)


if __name__ == "__main__":
    main()
