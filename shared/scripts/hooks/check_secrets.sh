#!/usr/bin/env bash
# PostToolUse hook: Detect hardcoded secrets in written/edited files.
#
# Reads JSON payload from stdin. Scans the file for secret patterns
# (API keys, tokens, passwords, private keys) and soft-blocks.
# Exit 0 = allow, Exit 2 = soft block.
#
# Detected patterns:
#   - AWS Access Key IDs (AKIA...)
#   - API keys (sk-, xoxb-, ghp_, gho_, glpat-, etc.)
#   - Private keys (PEM format)
#   - Hardcoded passwords/secrets in assignment
#   - Generic high-entropy hex tokens (40+ chars)
#   - Connection strings with credentials
#
# Ignored:
#   - Test fixtures, example files, .env.example
#   - Lock files, node_modules, vendor dirs

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

# Skip non-existent files
if [ ! -f "$FILE_PATH" ]; then
    exit 0
fi

# Skip files that legitimately contain secret-like patterns
SKIP_PATTERNS='(\.env\.example|\.env\.template|fixtures?[/\\]|test_data[/\\]|__snapshots__|node_modules[/\\]|vendor[/\\]|\.lock$|package-lock\.json|check_secrets\.sh|check_secrets_test)'
if echo "$FILE_PATH" | grep -qiE "$SKIP_PATTERNS"; then
    exit 0
fi

FINDINGS=""

# AWS Access Key ID (always starts with AKIA + 16 alphanumeric chars)
if grep -qE 'AKIA[0-9A-Z]{16}' "$FILE_PATH"; then
    FINDINGS="${FINDINGS}- AWS Access Key ID detected\n"
fi

# OpenAI / Anthropic API keys (sk-...)
if grep -qE "['\"]sk-[a-zA-Z0-9]{20,}['\"]" "$FILE_PATH"; then
    FINDINGS="${FINDINGS}- API key (sk-...) detected\n"
fi

# Slack tokens (xoxb-, xoxp-, xoxa-)
if grep -qE "xox[bpoa]-[a-zA-Z0-9-]+" "$FILE_PATH"; then
    FINDINGS="${FINDINGS}- Slack token detected\n"
fi

# GitHub tokens (ghp_, gho_, ghs_, github_pat_)
if grep -qE "(ghp_|gho_|ghs_|github_pat_)[a-zA-Z0-9_]+" "$FILE_PATH"; then
    FINDINGS="${FINDINGS}- GitHub token detected\n"
fi

# GitLab tokens (glpat-)
if grep -qE "glpat-[a-zA-Z0-9_-]+" "$FILE_PATH"; then
    FINDINGS="${FINDINGS}- GitLab token detected\n"
fi

# PEM private keys
if grep -q -- '-----BEGIN.*PRIVATE KEY-----' "$FILE_PATH"; then
    FINDINGS="${FINDINGS}- Private key (PEM) detected\n"
fi

# Hardcoded password/secret assignments (password = "...", secret = '...')
if grep -qiE "(password|passwd|secret|api_key|apikey|access_token|auth_token)\s*[=:]\s*['\"][^'\"]{8,}['\"]" "$FILE_PATH"; then
    # Exclude common false positives (placeholder values)
    if ! grep -qiE "(password|secret|api_key)\s*[=:]\s*['\"](\$\{|process\.env|os\.environ|YOUR_|CHANGE_ME|xxx|placeholder|example)" "$FILE_PATH"; then
        FINDINGS="${FINDINGS}- Hardcoded password/secret assignment detected\n"
    fi
fi

# Connection strings with embedded credentials
if grep -qiE "(postgres|mysql|mongodb|redis)://[^:]+:[^@]+@" "$FILE_PATH"; then
    # Exclude localhost/example connections
    if ! grep -qiE "(localhost|127\.0\.0\.1|example\.com|your-host)" "$FILE_PATH"; then
        FINDINGS="${FINDINGS}- Connection string with embedded credentials detected\n"
    fi
fi

if [ -n "$FINDINGS" ]; then
    FINDINGS_ESCAPED=$(echo -e "$FINDINGS" | sed 's/"/\\"/g' | tr '\n' ' ')
    echo "{\"hookSpecificOutput\":{\"hookEventName\":\"PostToolUse\",\"additionalContext\":\"BLOCKED: Potential secrets detected in ${FILE_PATH}:\\n${FINDINGS_ESCAPED}\\nDo NOT commit files with hardcoded secrets. Use environment variables instead.\\n\\nThe user may say 'Continue anyway' to override. If they do, log the override to agent_docs/compliance_overrides.log.\",\"blocked\":true,\"reason\":\"Secret pattern detected in ${FILE_PATH}\"}}"
    exit 2
fi

exit 0
