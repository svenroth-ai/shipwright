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

INPUT=$(cat)

# Extract file path from the tool output
FILE_PATH=$(echo "$INPUT" | python3 -c "
import json, sys
try:
    data = json.load(sys.stdin)
    # PostToolUse: tool_input has file_path for Write/Edit
    path = data.get('tool_input', {}).get('file_path', '')
    print(path)
except:
    print('')
" 2>/dev/null || echo "")

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
    # Escape for JSON
    WARNINGS_ESCAPED=$(echo "$WARNINGS" | sed 's/"/\\"/g')
    echo "{\"hookSpecificOutput\":{\"hookEventName\":\"PostToolUse\",\"additionalContext\":\"WARNING: Destructive migration in ${FILE_PATH}: ${WARNINGS_ESCAPED}This will permanently affect data. You MUST ask the user for explicit confirmation before proceeding.\"}}"
    exit 2
fi

exit 0
