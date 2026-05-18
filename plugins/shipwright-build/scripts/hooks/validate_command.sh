#!/usr/bin/env bash
# PreToolUse hook: Block dangerous commands.
#
# Reads JSON payload from stdin, checks Bash command for dangerous patterns.
# Exit 0 = allow, Exit 2 = block (soft block with message).
#
# Blocked patterns:
#   - git push --force (or -f to non-feature branches)
#   - rm -rf / (root deletion)
#   - DROP DATABASE (raw SQL execution)

set -euo pipefail

# Resolve a working Python interpreter. On Windows `python3` is frequently the
# Microsoft Store App-Execution-Alias stub: it prints "Python was not found"
# and exits non-zero without running anything. Probe each candidate by
# actually executing it so the stub is rejected.
_resolve_python() {
    local candidate
    for candidate in python3 python py; do
        if command -v "$candidate" >/dev/null 2>&1 \
           && "$candidate" -c "import sys" >/dev/null 2>&1; then
            printf '%s\n' "$candidate"
            return 0
        fi
    done
    return 1
}
PYTHON=$(_resolve_python) || exit 0  # no interpreter -> cannot inspect -> allow

# Read the tool input from stdin
INPUT=$(cat)

# Extract the command from the JSON payload
COMMAND=$(echo "$INPUT" | "$PYTHON" -c "
import json, sys
try:
    data = json.load(sys.stdin)
    # PreToolUse payload has tool_input.command for Bash
    cmd = data.get('tool_input', {}).get('command', '')
    print(cmd)
except:
    print('')
" 2>/dev/null | tr -d '\r' || echo "")

if [ -z "$COMMAND" ]; then
    exit 0  # No command found, allow
fi

# Check for dangerous patterns
# 1. git push --force (only allowed on feature branches, not main/master)
if echo "$COMMAND" | grep -qE 'git\s+push\s+.*(-f|--force)'; then
    if echo "$COMMAND" | grep -qE '\s(main|master)\b'; then
        echo '{"hookSpecificOutput":{"hookEventName":"PreToolUse","additionalContext":"BLOCKED: git push --force to main/master is not allowed."}}'
        exit 2
    fi
fi

# 2. rm -rf with root or home
if echo "$COMMAND" | grep -qE 'rm\s+-rf\s+(/|~|\$HOME)'; then
    echo '{"hookSpecificOutput":{"hookEventName":"PreToolUse","additionalContext":"BLOCKED: rm -rf on root/home directory is not allowed."}}'
    exit 2
fi

# 3. DROP DATABASE
if echo "$COMMAND" | grep -qiE 'DROP\s+DATABASE'; then
    echo '{"hookSpecificOutput":{"hookEventName":"PreToolUse","additionalContext":"BLOCKED: DROP DATABASE detected. This requires manual execution."}}'
    exit 2
fi

exit 0
