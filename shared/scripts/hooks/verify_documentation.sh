#!/usr/bin/env bash
# Hook: Documentation Completeness (Stop event)
# Checks that critical agent_docs files exist.
# Exit 2 = block action (Claude Code hook convention).
#
# Checks:
#   1. agent_docs/decision_log.md exists
#   2. agent_docs/session_handoff.md exists
#   3. All shipwright_*_config.json files referenced are valid JSON

set -euo pipefail

PROJECT_ROOT="${PWD}"

MISSING=()

# Check decision log
if [[ ! -f "$PROJECT_ROOT/agent_docs/decision_log.md" ]]; then
    MISSING+=("agent_docs/decision_log.md")
fi

# Check session handoff
if [[ ! -f "$PROJECT_ROOT/agent_docs/session_handoff.md" ]]; then
    MISSING+=("agent_docs/session_handoff.md")
fi

# Validate JSON config files (only check ones that exist)
for config in shipwright_run_config.json shipwright_project_config.json shipwright_plan_config.json shipwright_build_config.json; do
    if [[ -f "$PROJECT_ROOT/$config" ]]; then
        if ! python3 -c "import json; json.load(open('$PROJECT_ROOT/$config'))" 2>/dev/null; then
            MISSING+=("$config (invalid JSON)")
        fi
    fi
done

if [[ ${#MISSING[@]} -gt 0 ]]; then
    echo "⚠️  Documentation completeness check failed:" >&2
    for item in "${MISSING[@]}"; do
        echo "  - Missing: $item" >&2
    done
    echo "" >&2
    echo "Please create these files before ending the session." >&2
    exit 2
fi

exit 0
