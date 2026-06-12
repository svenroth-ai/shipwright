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

# Resolve ONE working Python interpreter for the whole script (the prerequisite
# check below and the .env.local parser further down both need it). Probe by
# TEST-RUNNING ``--version``, not just ``command -v``: on Windows ``python3`` is
# usually the Microsoft Store App-Execution-Alias stub that ``command -v`` finds
# but that exits 49 on invocation (deep-audit F37 follow-up). Requiring a
# successful ``--version`` makes the stub fall through to the real interpreter.
SW_PYTHON=""
for _candidate in python3 python py; do
    if command -v "$_candidate" &>/dev/null && "$_candidate" --version >/dev/null 2>&1; then
        SW_PYTHON="$_candidate"
        break
    fi
done

# ── Prerequisites ──

echo "Prerequisites:"

# Claude Code
if command -v claude &>/dev/null; then
    version=$(claude --version 2>/dev/null || echo "unknown")
    echo "  $PASS Claude Code: $version"
else
    echo "  $FAIL Claude Code: not found (install from docs.anthropic.com)"
    errors=$((errors+1))
fi

# Python (uses the test-run-resolved SW_PYTHON; a Microsoft Store python3 stub
# is found by `command -v` but reports no usable version — SW_PYTHON skipped it).
if [ -n "$SW_PYTHON" ]; then
    py_version=$("$SW_PYTHON" --version 2>&1 | awk '{print $2}')
    py_major=$(echo "$py_version" | cut -d. -f1)
    py_minor=$(echo "$py_version" | cut -d. -f2)
    if [ "$py_major" -ge 3 ] && [ "$py_minor" -ge 11 ]; then
        echo "  $PASS Python: $py_version ($SW_PYTHON)"
    else
        echo "  $FAIL Python: $py_version (need 3.11+)"
        errors=$((errors+1))
    fi
else
    echo "  $FAIL Python: not found (tried python3, python, py)"
    errors=$((errors+1))
fi

# uv
if command -v uv &>/dev/null; then
    uv_version=$(uv --version 2>&1 | head -1)
    echo "  $PASS uv: $uv_version"
else
    echo "  $FAIL uv: not found (curl -LsSf https://astral.sh/uv/install.sh | sh)"
    errors=$((errors+1))
fi

# Git
if command -v git &>/dev/null; then
    git_version=$(git --version | awk '{print $3}')
    echo "  $PASS Git: $git_version"
else
    echo "  $FAIL Git: not found"
    errors=$((errors+1))
fi

# gh (optional)
if command -v gh &>/dev/null; then
    gh_version=$(gh --version 2>&1 | head -1 | awk '{print $3}')
    echo "  $PASS GitHub CLI: $gh_version"
else
    echo "  $WARN GitHub CLI: not found (optional, needed for PRs)"
    warnings=$((warnings+1))
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
            errors=$((errors+1))
        fi
    done
else
    echo "  $FAIL Repo not found at $REPO_ROOT"
    errors=$((errors+1))
fi

echo ""

# ── Environment Variables ──

echo "Environment Variables:"

# Read .env.local from CWD (project root) using the SAME canonical dotenv
# parser the Python plugins use (shared/scripts/lib/env.py:parse_env_file).
# We must NOT `source` the file: dotenv is a data format, not a shell script,
# so a spaced/quoted value (e.g. `KEY=a b $(cmd)`) would be executed as a
# command under `source` (deep-audit F38). Instead we ask Python for the
# newline-separated list of keys that carry a non-empty value, then test
# membership — no eval, no injection. A key already present in the live
# environment also counts as set.
PROJECT_ROOT="$(pwd)"

# Reuse the single test-run-resolved interpreter from the top of the script
# (python3 → python → py, with the Microsoft Store stub skipped); the canonical
# .env.local parser is Python.

# Newline-separated list of dotenv keys with a non-empty value (may be empty).
DOTENV_KEYS=""
if [ -f "$PROJECT_ROOT/.env.local" ]; then
    echo "  $PASS .env.local: found at $PROJECT_ROOT/.env.local"
    if [ -n "$SW_PYTHON" ]; then
        DOTENV_KEYS="$("$SW_PYTHON" - "$REPO_ROOT" "$PROJECT_ROOT/.env.local" <<'PYEOF' 2>/dev/null || true
import re
import sys
from pathlib import Path
sys.path.insert(0, str(Path(sys.argv[1]) / "shared" / "scripts" / "lib"))
from env import parse_env_file  # canonical dotenv reader (no `source`)
# Emit ONLY conservative identifier keys with a non-empty value. Restricting
# to ^[A-Za-z_][A-Za-z0-9_]*$ ensures a malformed key cannot influence the
# shell's fixed-string membership test (external-review).
for key, value in parse_env_file(Path(sys.argv[2])).items():
    if value and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
        print(key)
PYEOF
)"
    else
        echo "  $WARN .env.local: no Python interpreter to parse it (keys read from environment only)"
    fi
else
    echo "  $SKIP .env.local: not found in project (run validate_env.py --init --phase all)"
fi

# env_has KEY → 0 if KEY is set in the live environment OR present-with-value
# in the parsed .env.local list.
env_has() {
    local key="$1"
    # Bash indirect expansion (${!key}) reads the variable named by $key WITHOUT
    # `eval` — no shell syntax in the value is ever evaluated (code-review HIGH:
    # `eval` reintroduces the exact dotenv/shell boundary F38 removes).
    if [ -n "${!key:-}" ]; then
        return 0
    fi
    # Fixed-string, whole-line match (-F): the parsed key list is data, never a
    # regex/glob (external-review — exact match, not pattern match).
    printf '%s\n' "$DOTENV_KEYS" | grep -Fxq -- "$key"
}

if env_has OPENROUTER_API_KEY; then
    echo "  $PASS OPENROUTER_API_KEY: set (external review via OpenRouter)"
elif env_has GEMINI_API_KEY || env_has GOOGLE_API_KEY; then
    echo "  $PASS GEMINI_API_KEY: set (external review via Gemini)"
elif env_has OPENAI_API_KEY; then
    echo "  $PASS OPENAI_API_KEY: set (external review via OpenAI)"
else
    echo "  $SKIP External review: no API keys set (optional)"
fi

if env_has JELASTIC_TOKEN; then
    echo "  $PASS JELASTIC_TOKEN: set (deployment enabled)"
else
    echo "  $SKIP JELASTIC_TOKEN: not set (deployment disabled)"
fi

if env_has SUPABASE_ACCESS_TOKEN; then
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
