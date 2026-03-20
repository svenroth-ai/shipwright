#!/usr/bin/env bash
# Hook: Dangerous Command Guard (PreToolUse — Bash)
# Blocks dangerous shell commands before execution.
# Exit 2 = block action (Claude Code hook convention).
#
# Blocked commands:
#   - git push --force / -f (can overwrite remote history)
#   - rm -rf (can delete entire directories)
#   - supabase db push without --dry-run on PROD

set -euo pipefail

# Read the tool input from stdin
INPUT=$(cat)

# Extract the command from hook input (portable, no grep -P)
COMMAND=$(echo "$INPUT" | sed -n 's/.*"command"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -1)

if [[ -z "$COMMAND" ]]; then
    exit 0
fi

# Check for git push --force
if echo "$COMMAND" | grep -qE 'git\s+push\s+.*(-f|--force)'; then
    echo "BLOCKED: git push --force is not allowed." >&2
    echo "Force-pushing can overwrite remote history and cause data loss." >&2
    echo "Use a regular push or rebase instead." >&2
    exit 2
fi

# Check for rm -rf (with any path)
if echo "$COMMAND" | grep -qE 'rm\s+(-[a-zA-Z]*r[a-zA-Z]*f|--recursive\s+--force|-[a-zA-Z]*f[a-zA-Z]*r)\s'; then
    echo "BLOCKED: rm -rf is not allowed." >&2
    echo "Recursive forced deletion can cause irreversible data loss." >&2
    echo "Delete specific files instead." >&2
    exit 2
fi

# Check for unguarded PROD supabase db push
if echo "$COMMAND" | grep -qE 'supabase\s+db\s+push' && \
   echo "$COMMAND" | grep -qiE '(prod|production)' && \
   ! echo "$COMMAND" | grep -q '\-\-dry-run'; then
    echo "BLOCKED: supabase db push to PROD without --dry-run." >&2
    echo "Always run with --dry-run first to validate changes." >&2
    exit 2
fi

exit 0
