#!/usr/bin/env bash
# PostToolUse hook: Warn when source files exceed line count threshold.
#
# Reads JSON payload from stdin. Checks written/edited file line count
# against configurable threshold (default: 300 lines).
# Exit 0 = allow (with warning), Exit 2 = soft block.
#
# Rationale: Large files degrade AI agent performance by consuming
# excessive context window space. Anthropic Best Practices confirm:
# "LLM performance degrades as context fills."
#
# Configuration: shipwright_build_config.json → enforcement.max_file_lines
# Default: 300 lines
#
# Ignored:
#   - Non-source files (lock files, generated, vendor, node_modules)
#   - Markdown, JSON, YAML, TOML, CSV (config/docs)
#   - Migration files (SQL can be long by nature)

set -euo pipefail

INPUT=$(cat)

# Extract file path from PostToolUse payload
FILE_PATH=$(echo "$INPUT" | python3 -c "
import json, sys
try:
    data = json.load(sys.stdin)
    path = data.get('tool_input', {}).get('file_path', '')
    print(path)
except:
    print('')
" 2>/dev/null || echo "")

if [ -z "$FILE_PATH" ]; then
    exit 0
fi

if [ ! -f "$FILE_PATH" ]; then
    exit 0
fi

# Skip non-source files that are legitimately long
SKIP_PATTERNS='(\.lock$|package-lock|node_modules[/\\]|vendor[/\\]|dist[/\\]|build[/\\]|\.min\.|__pycache__|\.pyc$|\.generated\.|migrations?[/\\].*\.sql)'
if echo "$FILE_PATH" | grep -qiE "$SKIP_PATTERNS"; then
    exit 0
fi

# Skip config/docs files (often long but fine)
SKIP_EXTENSIONS='(\.(md|json|yaml|yml|toml|csv|svg|xml|html|css)$)'
if echo "$FILE_PATH" | grep -qiE "$SKIP_EXTENSIONS"; then
    exit 0
fi

# Read threshold from config (default 300)
MAX_LINES=300
CONFIG_FILE="shipwright_build_config.json"
if [ -f "$CONFIG_FILE" ]; then
    CONFIGURED=$(python3 -c "
import json, sys
try:
    with open('$CONFIG_FILE') as f:
        c = json.load(f)
    print(c.get('enforcement', {}).get('max_file_lines', 300))
except:
    print(300)
" 2>/dev/null || echo "300")
    MAX_LINES="$CONFIGURED"
fi

# Count lines
LINE_COUNT=$(wc -l < "$FILE_PATH" | tr -d ' ')

if [ "$LINE_COUNT" -gt "$MAX_LINES" ]; then
    echo "{\"hookSpecificOutput\":{\"hookEventName\":\"PostToolUse\",\"additionalContext\":\"WARNING: ${FILE_PATH} has ${LINE_COUNT} lines (threshold: ${MAX_LINES}).\\n\\nLarge files degrade AI agent performance by consuming excessive context window space. Consider refactoring into smaller modules.\\n\\nThe user may say 'Continue anyway' to override. If they do, log the override to agent_docs/compliance_overrides.log.\",\"blocked\":true,\"reason\":\"File exceeds ${MAX_LINES} line limit: ${LINE_COUNT} lines\"}}"
    exit 2
fi

exit 0
