#!/usr/bin/env bash
# PostToolUse hook: Detect destructive SQL operations in migration files.
#
# Reads JSON payload from stdin. If the written/edited file is a SQL migration,
# scans for destructive patterns and warns.
# Exit 0 = allow (with warning in context), Exit 2 = soft block.
#
# Detected patterns:
#   - DROP TABLE
#   - DROP COLUMN
#   - ALTER TYPE (lossy)
#   - TRUNCATE
#   - DELETE FROM (without WHERE)

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

INPUT=$(cat)

# Extract file path from the tool output
FILE_PATH=$(echo "$INPUT" | "$PYTHON" -c "
import json, sys
try:
    data = json.load(sys.stdin)
    # PostToolUse: tool_input has file_path for Write/Edit
    path = data.get('tool_input', {}).get('file_path', '')
    print(path)
except:
    print('')
" 2>/dev/null | tr -d '\r' || echo "")

if [ -z "$FILE_PATH" ]; then
    exit 0
fi

# Only check SQL files in migration directories
if ! echo "$FILE_PATH" | grep -qiE '(migration|supabase).*\.sql$'; then
    exit 0
fi

# Check if the file exists and scan for destructive patterns
if [ ! -f "$FILE_PATH" ]; then
    exit 0
fi

WARNINGS=""

if grep -qiE 'DROP\s+TABLE' "$FILE_PATH"; then
    WARNINGS="${WARNINGS}DROP TABLE detected. "
fi

if grep -qiE 'DROP\s+COLUMN' "$FILE_PATH"; then
    WARNINGS="${WARNINGS}DROP COLUMN detected. "
fi

if grep -qiE 'ALTER\s+.*\s+TYPE\s' "$FILE_PATH"; then
    WARNINGS="${WARNINGS}ALTER TYPE detected (possible lossy conversion). "
fi

if grep -qiE 'TRUNCATE\s' "$FILE_PATH"; then
    WARNINGS="${WARNINGS}TRUNCATE detected. "
fi

if grep -qiE 'DELETE\s+FROM' "$FILE_PATH" && ! grep -qiE 'DELETE\s+FROM.*WHERE' "$FILE_PATH"; then
    WARNINGS="${WARNINGS}DELETE FROM without WHERE detected. "
fi

if [ -n "$WARNINGS" ]; then
    # Deliver the block reason on STDERR — the channel Claude Code reads on a
    # PostToolUse exit-2 soft block. (Emitting JSON on stdout + exit 2 is the
    # bug WP4 fixed: Claude Code discards stdout on exit 2, so the warning
    # never reached the model.) Reports the matched DDL classes only.
    {
        printf 'WARNING: DESTRUCTIVE migration detected in %s: %s\n' "$FILE_PATH" "$WARNINGS"
        printf 'This will permanently affect data. You MUST ask the user for explicit confirmation before proceeding.\n'
    } >&2
    exit 2
fi

exit 0
