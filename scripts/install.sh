#!/usr/bin/env bash
# Shipwright Installer
# Checks prerequisites, sets up shell alias, runs verification.

set -euo pipefail

echo "========================================"
echo " Shipwright SDLC Framework Installer"
echo "========================================"
echo ""

# ── Determine repo location ──

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

if [ ! -f "$REPO_ROOT/plugins/shipwright-run/.claude-plugin/plugin.json" ]; then
    echo "Error: Shipwright repo not found at $REPO_ROOT"
    echo "Run this script from the shipwright directory."
    exit 1
fi

echo "Shipwright repo: $REPO_ROOT"
echo ""

# ── Check prerequisites ──

echo "Checking prerequisites..."

missing=0

if ! command -v claude &>/dev/null; then
    echo "  [!!] Claude Code CLI not found."
    echo "       Install: https://docs.anthropic.com/en/docs/claude-code"
    ((missing++))
fi

if ! command -v python3 &>/dev/null; then
    echo "  [!!] Python 3 not found."
    ((missing++))
else
    py_minor=$(python3 -c "import sys; print(sys.version_info.minor)")
    if [ "$py_minor" -lt 11 ]; then
        echo "  [!!] Python 3.11+ required (found 3.$py_minor)"
        ((missing++))
    fi
fi

if ! command -v uv &>/dev/null; then
    echo "  [!!] uv not found. Installing..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.cargo/bin:$PATH"
fi

if ! command -v git &>/dev/null; then
    echo "  [!!] git not found."
    ((missing++))
fi

if ! command -v node &>/dev/null; then
    echo "  [!!] Node.js not found (optional — needed for WebUI)."
    echo "       Install Node.js 18+: https://nodejs.org/"
else
    node_major=$(node -e "console.log(process.versions.node.split('.')[0])")
    if [ "$node_major" -lt 18 ]; then
        echo "  [!!] Node.js 18+ recommended for WebUI (found $node_major)"
    fi
fi

if [ $missing -gt 0 ]; then
    echo ""
    echo "$missing prerequisite(s) missing. Install them and re-run."
    exit 1
fi

echo "  All prerequisites found."
echo ""

# ── Install Python dependencies ──

echo "Installing Python dependencies..."
cd "$REPO_ROOT" && uv sync --quiet
echo "  Done."
echo ""

# ── Install WebUI dependencies ──

echo "Installing WebUI dependencies..."
if [ -d "$REPO_ROOT/webui" ]; then
    if command -v npm &>/dev/null; then
        cd "$REPO_ROOT/webui/server" && npm install --silent 2>/dev/null
        cd "$REPO_ROOT/webui/client" && npm install --silent 2>/dev/null
        echo "  Done."
    else
        echo "  [!!] npm not found — WebUI dependencies not installed."
        echo "       Install Node.js 18+ to use the Command Center WebUI."
    fi
else
    echo "  WebUI directory not found — skipping."
fi
echo ""

# ── Create shell alias ──

echo "Setting up shell alias..."

ALIAS_BLOCK="
# Shipwright SDLC Framework
shipwright() {
  claude \\
    --plugin-dir $REPO_ROOT/plugins/shipwright-run \\
    --plugin-dir $REPO_ROOT/plugins/shipwright-project \\
    --plugin-dir $REPO_ROOT/plugins/shipwright-design \\
    --plugin-dir $REPO_ROOT/plugins/shipwright-iterate \\
    --plugin-dir $REPO_ROOT/plugins/shipwright-plan \\
    --plugin-dir $REPO_ROOT/plugins/shipwright-build \\
    --plugin-dir $REPO_ROOT/plugins/shipwright-test \\
    --plugin-dir $REPO_ROOT/plugins/shipwright-deploy \\
    --plugin-dir $REPO_ROOT/plugins/shipwright-changelog \\
    --plugin-dir $REPO_ROOT/plugins/shipwright-compliance \\
    --plugin-dir $REPO_ROOT/plugins/shipwright-security \\
    --plugin-dir $REPO_ROOT/plugins/shipwright-preview \\
    \"\$@\"
}
"

# Detect shell config file
if [ -n "${ZSH_VERSION:-}" ] || [ -f "$HOME/.zshrc" ]; then
    SHELL_RC="$HOME/.zshrc"
elif [ -f "$HOME/.bashrc" ]; then
    SHELL_RC="$HOME/.bashrc"
else
    SHELL_RC="$HOME/.bashrc"
fi

# Check if alias already exists
if grep -q "shipwright()" "$SHELL_RC" 2>/dev/null; then
    echo "  Shell alias already exists in $SHELL_RC"
else
    echo "$ALIAS_BLOCK" >> "$SHELL_RC"
    echo "  Added shipwright alias to $SHELL_RC"
fi

# Make it available in current session
eval "$ALIAS_BLOCK"

echo ""

# ── Run verification ──

echo "Running verification..."
echo ""
bash "$REPO_ROOT/scripts/verify-setup.sh" || true

echo ""
echo "========================================"
echo " Installation complete!"
echo ""
echo " Reload your shell:  source $SHELL_RC"
echo " Then run:           shipwright"
echo " Then type:          /shipwright-run"
echo ""
echo " WebUI (Command Center):"
echo "   cd webui && npm run dev"
echo "   Open http://localhost:5173"
echo "========================================"
