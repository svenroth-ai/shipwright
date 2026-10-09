#!/usr/bin/env bash
# PreToolUse hook: Block dangerous commands.
#
# Reads JSON payload from stdin, checks Bash command for dangerous patterns.
# Exit 0 = allow, Exit 2 = block (soft block with message).
#
# Blocked patterns:
#   - git push with a real force flag aimed at main/master (or, with no branch
#     named, at the checked-out branch) — see force_push_guard.py
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
# No interpreter is NOT a reason to allow: the checks below degrade to the
# coarse grep forms (they never needed Python), so a missing interpreter can
# never silently switch the guards off.
PYTHON=$(_resolve_python) || PYTHON=""

# Read the tool input from stdin
INPUT=$(cat)

# Extract the command from the JSON payload
# Interpreter-free extraction (portable ERE): keeps JSON escapes, which is fine
# for grep; \n and \t become spaces so a multi-line command stays one string.
_extract_with_sed() {
    printf '%s' "$INPUT" \
        | sed -nE 's/.*"command"[[:space:]]*:[[:space:]]*"(([^"\\]|\\.)*)".*/\1/p' \
        | head -1 | sed -E 's/\\[nt]/ /g' | tr -d '\r'
}

COMMAND=""
if [ -n "$PYTHON" ]; then
    COMMAND=$(echo "$INPUT" | "$PYTHON" -c "
import json, sys
try:
    # Bytes in/out: the locale code page (cp1252 on Windows) cannot encode
    # every character, which would otherwise blank the command and allow it.
    data = json.load(sys.stdin.buffer)
    # PreToolUse payload has tool_input.command for Bash
    cmd = data.get('tool_input', {}).get('command', '')
    sys.stdout.buffer.write((cmd + '\n').encode('utf-8', 'replace'))
except Exception:
    print('')
" 2>/dev/null | tr -d '\r' || echo "")
fi
# Empty: no interpreter, or its extractor failed on this payload. Try sed before
# concluding there is no command — only both finding nothing means allow.
if [ -z "$COMMAND" ]; then
    COMMAND=$(_extract_with_sed || echo "")
fi

if [ -z "$COMMAND" ]; then
    exit 0  # No command found, allow
fi

# Check for dangerous patterns
# 1. force-push to main/master (allowed on feature branches). The precise
#    inspection lives in force_push_guard.py (unit-testable): exit 3 = block,
#    0 = allow. Anything else (no interpreter, missing/crashed guard, exit 4
#    "cannot decide") degrades to a deliberately coarse, over-blocking check — a
#    push, a force flag (-f cluster, --force, +refspec) and the word main/master
#    anywhere in the string — so a broken guard produces a false alarm rather
#    than a silent pass.
GUARD_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
GUARD_RC=127
if [ -n "$PYTHON" ] && [ -f "$GUARD_DIR/force_push_guard.py" ]; then
    GUARD_RC=0
    printf '%s' "$COMMAND" | "$PYTHON" "$GUARD_DIR/force_push_guard.py" 2>/dev/null || GUARD_RC=$?
fi
if [ "$GUARD_RC" -ne 0 ] && [ "$GUARD_RC" -ne 3 ]; then
    GUARD_RC=0
    if echo "$COMMAND" | grep -qE 'git\b.*\bpush\b' \
       && echo "$COMMAND" | grep -qE '([[:space:]]-[A-Za-z]*f|--force|[[:space:]:]\+)' \
       && echo "$COMMAND" | grep -qE '[[:space:]:+/](main|master)\b'; then
        GUARD_RC=3
    fi
    echo "validate_command: force-push guard unavailable, used the coarse fallback check" >&2 || true
fi
if [ "$GUARD_RC" -eq 3 ]; then
    echo '{"hookSpecificOutput":{"hookEventName":"PreToolUse","additionalContext":"BLOCKED: git push --force to main/master is not allowed."}}'
    exit 2
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
