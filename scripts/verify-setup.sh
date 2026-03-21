#!/usr/bin/env bash
# Shipwright Setup Verification
# Checks all prerequisites, plugins, and environment variables.

set -euo pipefail

PASS="[OK]"
FAIL="[!!]"
SKIP="[--]"
WARN="[??]"

errors=0
warnings=0

echo "========================================"
echo " Shipwright Setup Verification"
echo "========================================"
echo ""

# ── Prerequisites ──

echo "Prerequisites:"

# Claude Code
if command -v claude &>/dev/null; then
    version=$(claude --version 2>/dev/null || echo "unknown")
    echo "  $PASS Claude Code: $version"
else
    echo "  $FAIL Claude Code: not found (install from docs.anthropic.com)"
    ((errors++))
fi

# Python
if command -v python3 &>/dev/null; then
    py_version=$(python3 --version 2>&1 | awk '{print $2}')
    py_major=$(echo "$py_version" | cut -d. -f1)
    py_minor=$(echo "$py_version" | cut -d. -f2)
    if [ "$py_major" -ge 3 ] && [ "$py_minor" -ge 11 ]; then
        echo "  $PASS Python: $py_version"
    else
        echo "  $FAIL Python: $py_version (need 3.11+)"
        ((errors++))
    fi
else
    echo "  $FAIL Python: not found"
    ((errors++))
fi

# uv
if command -v uv &>/dev/null; then
    uv_version=$(uv --version 2>&1 | head -1)
    echo "  $PASS uv: $uv_version"
else
    echo "  $FAIL uv: not found (curl -LsSf https://astral.sh/uv/install.sh | sh)"
    ((errors++))
fi

# Git
if command -v git &>/dev/null; then
    git_version=$(git --version | awk '{print $3}')
    echo "  $PASS Git: $git_version"
else
    echo "  $FAIL Git: not found"
    ((errors++))
fi

# gh (optional)
if command -v gh &>/dev/null; then
    gh_version=$(gh --version 2>&1 | head -1 | awk '{print $3}')
    echo "  $PASS GitHub CLI: $gh_version"
else
    echo "  $WARN GitHub CLI: not found (optional, needed for PRs)"
    ((warnings++))
fi

# Node (optional)
if command -v node &>/dev/null; then
    node_version=$(node --version)
    echo "  $PASS Node.js: $node_version"
else
    echo "  $SKIP Node.js: not found (needed for supabase-nextjs profile)"
fi

echo ""

# ── Shipwright Repo ──

echo "Shipwright:"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

if [ -f "$REPO_ROOT/plugins/shipwright-run/.claude-plugin/plugin.json" ]; then
    echo "  $PASS Repo: $REPO_ROOT"

    # Count plugins
    plugin_count=$(ls -d "$REPO_ROOT"/plugins/shipwright-*/  2>/dev/null | wc -l | tr -d ' ')
    echo "  $PASS Plugins: $plugin_count found"

    # List plugins
    for plugin_dir in "$REPO_ROOT"/plugins/shipwright-*/; do
        name=$(basename "$plugin_dir")
        if [ -f "$plugin_dir/.claude-plugin/plugin.json" ]; then
            echo "    $PASS $name"
        else
            echo "    $FAIL $name (missing plugin.json)"
            ((errors++))
        fi
    done
else
    echo "  $FAIL Repo not found at $REPO_ROOT"
    ((errors++))
fi

echo ""

# ── Environment Variables ──

echo "Environment Variables:"

if [ -n "${OPENROUTER_API_KEY:-}" ]; then
    echo "  $PASS OPENROUTER_API_KEY: set (external review via OpenRouter)"
elif [ -n "${GEMINI_API_KEY:-}" ] || [ -n "${GOOGLE_API_KEY:-}" ]; then
    echo "  $PASS GEMINI_API_KEY: set (external review via Gemini)"
elif [ -n "${OPENAI_API_KEY:-}" ]; then
    echo "  $PASS OPENAI_API_KEY: set (external review via OpenAI)"
else
    echo "  $SKIP External review: no API keys set (optional)"
fi

if [ -n "${JELASTIC_TOKEN:-}" ]; then
    echo "  $PASS JELASTIC_TOKEN: set (deployment enabled)"
else
    echo "  $SKIP JELASTIC_TOKEN: not set (deployment disabled)"
fi

if [ -n "${SUPABASE_ACCESS_TOKEN:-}" ]; then
    echo "  $PASS SUPABASE_ACCESS_TOKEN: set (migrations enabled)"
else
    echo "  $SKIP SUPABASE_ACCESS_TOKEN: not set (migrations disabled)"
fi

echo ""

# ── Summary ──

echo "========================================"
if [ $errors -eq 0 ]; then
    echo " Ready to go! Run: shipwright"
    if [ $warnings -gt 0 ]; then
        echo " ($warnings optional warnings)"
    fi
else
    echo " $errors error(s) found. Fix them before running Shipwright."
fi
echo "========================================"

exit $errors
