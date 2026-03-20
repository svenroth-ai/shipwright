#!/usr/bin/env bash
# Hook: Migration Safety Gate (PostToolUse — Write|Edit)
# Scans migration SQL files for destructive changes.
# Exit 2 = block action (Claude Code hook convention).
#
# Destructive patterns: DROP TABLE, DROP COLUMN, ALTER TYPE (lossy)
# These ALWAYS require explicit user confirmation, regardless of autonomy level.

set -euo pipefail

# Read the tool result from stdin (JSON with file path)
INPUT=$(cat)

# Extract file path from hook input (portable, no grep -P)
FILE_PATH=$(echo "$INPUT" | sed -n 's/.*"filePath"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -1)

# Normalize path separators for cross-platform support
FILE_PATH="${FILE_PATH//\\//}"

# Only check files in supabase/migrations/
if [[ -z "$FILE_PATH" ]] || [[ "$FILE_PATH" != *supabase/migrations/*.sql ]]; then
    exit 0
fi

# Check for destructive patterns (case-insensitive)
DESTRUCTIVE_PATTERNS="DROP[[:space:]]+TABLE|DROP[[:space:]]+COLUMN|ALTER[[:space:]]+TYPE"

if grep -qiE "$DESTRUCTIVE_PATTERNS" "$FILE_PATH" 2>/dev/null; then
    echo "WARNING: DESTRUCTIVE MIGRATION DETECTED in $FILE_PATH" >&2
    echo "" >&2
    echo "Found one or more destructive operations:" >&2
    grep -niE "$DESTRUCTIVE_PATTERNS" "$FILE_PATH" >&2
    echo "" >&2
    echo "These changes may cause DATA LOSS. User confirmation required." >&2
    exit 2
fi

exit 0
