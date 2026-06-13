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

# NOTE: ``((missing++))`` post-increments and, when the prior value is 0,
# evaluates to 0 → exit status 1. Under ``set -e`` that aborts the whole
# script at the FIRST missing prerequisite (deep-audit F33). Use the
# arithmetic-assignment form, which always returns success.
if ! command -v claude &>/dev/null; then
    echo "  [!!] Claude Code CLI not found."
    echo "       Install: https://docs.anthropic.com/en/docs/claude-code"
    missing=$((missing + 1))
fi

if ! command -v python3 &>/dev/null; then
    echo "  [!!] Python 3 not found."
    missing=$((missing + 1))
else
    py_minor=$(python3 -c "import sys; print(sys.version_info.minor)")
    if [ "$py_minor" -lt 11 ]; then
        echo "  [!!] Python 3.11+ required (found 3.$py_minor)"
        missing=$((missing + 1))
    fi
fi

if ! command -v uv &>/dev/null; then
    echo "  [!!] uv not found. Installing..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    # The astral installer writes the ``uv`` binary to ~/.local/bin (XDG),
    # NOT ~/.cargo/bin (that path is a cargo-era leftover). Prepend the real
    # install dir so the ``uv sync`` below is on PATH (deep-audit F34). We
    # PREPEND (not replace PATH) and keep ~/.cargo/bin too, so an older install
    # that landed uv under ~/.cargo/bin still resolves (external-review).
    export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
fi

if ! command -v git &>/dev/null; then
    echo "  [!!] git not found."
    missing=$((missing + 1))
fi

if ! command -v node &>/dev/null; then
    echo "  [!!] Node.js not found (optional — needed for WebUI)."
    echo "       Install Node.js 20+: https://nodejs.org/"
else
    node_major=$(node -e "console.log(process.versions.node.split('.')[0])")
    if [ "$node_major" -lt 20 ]; then
        echo "  [!!] Node.js 20+ recommended for WebUI (found $node_major)"
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

# ── Command Center WebUI (separate repo since v0.4.0) ──

echo "Command Center WebUI:"
echo "  The WebUI lives in its own repository since v0.4.0:"
echo "    https://github.com/svenroth-ai/shipwright-webui"
echo ""
echo "  To install it alongside Shipwright:"
echo "    git clone https://github.com/svenroth-ai/shipwright-webui.git ~/shipwright-webui"
echo "    cd ~/shipwright-webui && make install"
echo "    make dev-server   # Terminal 1 (Hono :3847)"
echo "    make dev-client   # Terminal 2 (Vite :5173)"
echo ""

# ── Create shell alias ──

echo "Setting up shell alias..."

# Every ``--plugin-dir`` path is double-quoted so a space-containing clone
# path (e.g. OneDrive 'dinovo GmbH', 'Sven Roth') stays a single argument
# (deep-audit F36). All 13 plugins are listed, incl. shipwright-adopt
# (deep-audit F35).
ALIAS_BLOCK="
# Shipwright SDLC Framework
shipwright() {
  claude \\
    --plugin-dir \"$REPO_ROOT/plugins/shipwright-run\" \\
    --plugin-dir \"$REPO_ROOT/plugins/shipwright-project\" \\
    --plugin-dir \"$REPO_ROOT/plugins/shipwright-design\" \\
    --plugin-dir \"$REPO_ROOT/plugins/shipwright-iterate\" \\
    --plugin-dir \"$REPO_ROOT/plugins/shipwright-plan\" \\
    --plugin-dir \"$REPO_ROOT/plugins/shipwright-build\" \\
    --plugin-dir \"$REPO_ROOT/plugins/shipwright-test\" \\
    --plugin-dir \"$REPO_ROOT/plugins/shipwright-deploy\" \\
    --plugin-dir \"$REPO_ROOT/plugins/shipwright-changelog\" \\
    --plugin-dir \"$REPO_ROOT/plugins/shipwright-compliance\" \\
    --plugin-dir \"$REPO_ROOT/plugins/shipwright-security\" \\
    --plugin-dir \"$REPO_ROOT/plugins/shipwright-preview\" \\
    --plugin-dir \"$REPO_ROOT/plugins/shipwright-adopt\" \\
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

# Refresh the alias in place. A grep "already exists → skip" guard would
# permanently pin a stale alias (e.g. an old 12-plugin block missing
# shipwright-adopt — deep-audit F35), so we strip any prior Shipwright block
# and append the current one. The marker comments delimit our block; older
# installs wrote only the "# Shipwright SDLC Framework" header + function, so
# we also tolerate a marker-less prior block by removing from that header
# through its closing brace.
if [ -f "$SHELL_RC" ] && grep -q "shipwright()" "$SHELL_RC" 2>/dev/null; then
    # Delete the existing block: from the "# Shipwright SDLC Framework" comment
    # up to and including the function's closing "}" line.
    #
    # SAFETY (external-review HIGH): overwriting a user's shell rc is
    # destructive. Back it up first, write to a temp file, and only move the
    # temp over the rc if the strip produced NON-EMPTY output — an awk failure
    # or empty result must never blow away the user's profile.
    cp "$SHELL_RC" "${SHELL_RC}.shipwright.bak"
    tmp_rc="$(mktemp)"
    awk '
        /^# Shipwright SDLC Framework$/ { skip=1; next }
        skip && /^}$/                   { skip=0; next }
        skip                            { next }
        { print }
    ' "$SHELL_RC" > "$tmp_rc"
    if [ -s "$tmp_rc" ]; then
        mv "$tmp_rc" "$SHELL_RC"
        echo "$ALIAS_BLOCK" >> "$SHELL_RC"
        echo "  Refreshed shipwright alias in $SHELL_RC (backup: ${SHELL_RC}.shipwright.bak)"
    else
        # Strip produced nothing — leave the original untouched and append.
        rm -f "$tmp_rc"
        echo "$ALIAS_BLOCK" >> "$SHELL_RC"
        echo "  [??] alias strip yielded empty output; left $SHELL_RC intact and appended fresh block"
    fi
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
echo "   Lives at https://github.com/svenroth-ai/shipwright-webui"
echo "   See above for standalone install commands."
echo "========================================"
