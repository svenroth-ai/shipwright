#!/usr/bin/env bash
# Sync Shipwright marketplace from GitHub and refresh all plugin caches.
# Usage: bash scripts/update-marketplace.sh
#
# Works for:
#   - Developers: run after 'git push' to sync local install
#   - End-users: run any time to get latest updates
set -euo pipefail

MARKETPLACE_NAME="shipwright"

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
echo ""
echo "Fetching latest from GitHub..."
claude plugin marketplace update "$MARKETPLACE_NAME"
echo "[OK] Marketplace synced"

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
