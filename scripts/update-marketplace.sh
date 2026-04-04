#!/usr/bin/env bash
# Sync Shipwright marketplace from GitHub and refresh all plugin caches.
# Usage: bash scripts/update-marketplace.sh
#
# Works for:
#   - Developers: run after 'git push' to sync local install
#   - End-users: run any time to get latest updates
set -euo pipefail

MARKETPLACE_NAME="shipwright"
MARKETPLACE_DIR="$HOME/.claude/plugins/marketplaces/shipwright"
HTTPS_URL="https://github.com/svenroth-ai/shipwright.git"

# All plugins in the marketplace
PLUGINS=(
    shipwright-run shipwright-project shipwright-design shipwright-plan
    shipwright-build shipwright-test shipwright-deploy shipwright-changelog
    shipwright-compliance shipwright-security shipwright-iterate shipwright-preview
)

echo "=== Shipwright Marketplace Update ==="

# Check claude CLI is available
if ! command -v claude &>/dev/null; then
    echo "Error: 'claude' CLI not found. Install Claude Code first."
    exit 1
fi

# Step 1: Update marketplace clone from GitHub
# Try the built-in command first; fall back to manual git pull if SSH fails
echo ""
echo "Fetching latest from GitHub..."
if claude plugin marketplace update "$MARKETPLACE_NAME" 2>/dev/null; then
    echo "[OK] Marketplace synced via CLI"
else
    echo "[!!] CLI marketplace update failed (likely SSH issue), using git pull fallback..."
    if [ -d "$MARKETPLACE_DIR/.git" ]; then
        # Ensure remote uses HTTPS (not SSH)
        git -C "$MARKETPLACE_DIR" remote set-url origin "$HTTPS_URL" 2>/dev/null || true
        git -C "$MARKETPLACE_DIR" fetch origin main
        git -C "$MARKETPLACE_DIR" reset --hard origin/main
    else
        git clone "$HTTPS_URL" "$MARKETPLACE_DIR"
    fi
    echo "[OK] Marketplace synced via git"
fi

# Step 2: Update each installed plugin's cache
echo ""
echo "Updating plugin caches..."
for plugin in "${PLUGINS[@]}"; do
    if claude plugin update "${plugin}@${MARKETPLACE_NAME}" 2>/dev/null; then
        echo "  [OK] ${plugin}"
    else
        echo "  [--] ${plugin} (not installed, skipping)"
    fi
done

echo ""
echo "=== Done. Restart Claude Code session to activate changes ==="
