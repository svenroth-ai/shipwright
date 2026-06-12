#!/usr/bin/env bash
# Sync Shipwright marketplace from GitHub and refresh all plugin caches.
# Usage: bash scripts/update-marketplace.sh
#
# Works for:
#   - Developers: run after 'git push' to sync local install (full file sync)
#   - End-users: run any time to get latest updates
#
# The script does a FULL FILE SYNC from the marketplace clone into each
# plugin's installed cache directory. This ensures local development changes
# are always reflected, regardless of version number changes.
set -euo pipefail

MARKETPLACE_NAME="shipwright"
MARKETPLACE_DIR="$HOME/.claude/plugins/marketplaces/shipwright"
INSTALLED_PLUGINS="$HOME/.claude/plugins/installed_plugins.json"
HTTPS_URL="https://github.com/svenroth-ai/shipwright.git"

# All plugins in the marketplace
PLUGINS=(
    shipwright-run shipwright-project shipwright-design shipwright-plan
    shipwright-build shipwright-test shipwright-deploy shipwright-changelog
    shipwright-compliance shipwright-security shipwright-iterate shipwright-preview
    shipwright-adopt
)

echo "=== Shipwright Marketplace Update ==="

# Check claude CLI is available
if ! command -v claude &>/dev/null; then
    echo "Error: 'claude' CLI not found. Install Claude Code first."
    exit 1
fi

# Resolve a Python interpreter. A bare ``python`` does not exist on
# Ubuntu/Debian/macOS (only ``python3``); under ``set -e`` the command
# substitutions below would then resolve to nothing and abort the entire
# sync silently (deep-audit F37). Probe python3 → python → py, in order.
#
# Probe by TEST-RUNNING ``--version``, not just ``command -v``: on Windows
# ``python3`` is usually the Microsoft Store App-Execution-Alias *stub* —
# ``command -v`` finds it, but invoking it prints "Python was not found" and
# exits 49, so a ``command -v``-only probe selects a non-working interpreter
# and the first ``$(python3 -c …)`` below then aborts the whole sync under
# ``set -euo pipefail`` (F37 fixed POSIX but regressed Windows). Requiring a
# successful ``--version`` makes the stub fall through to the real interpreter.
PYTHON_BIN=""
for _candidate in python3 python py; do
    if command -v "$_candidate" &>/dev/null && "$_candidate" --version >/dev/null 2>&1; then
        PYTHON_BIN="$_candidate"
        break
    fi
done
if [ -z "$PYTHON_BIN" ]; then
    echo "Error: no Python interpreter found (tried python3, python, py)."
    echo "       Install Python 3.11+ and re-run."
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

# Step 2: Full file sync from marketplace into installed plugin caches
# Reads the installed cache path from installed_plugins.json so we always
# write to the correct version directory (e.g. 0.2.0), not whatever version
# is in the source plugin.json.
echo ""
echo "Full sync: marketplace → plugin caches..."

synced=0
skipped=0
errors=0

for plugin in "${PLUGINS[@]}"; do
    src_dir="$MARKETPLACE_DIR/plugins/$plugin"
    plugin_key="${plugin}@${MARKETPLACE_NAME}"

    # Check if plugin source exists in marketplace
    if [ ! -d "$src_dir" ]; then
        echo "  [!!] ${plugin}: source not found in marketplace, skipping"
        ((errors++)) || true
        continue
    fi

    # Get the installed cache path from installed_plugins.json
    cache_target=$("$PYTHON_BIN" -c "
import json, sys, os
try:
    ip = os.path.expanduser('~/.claude/plugins/installed_plugins.json')
    data = json.load(open(ip))
    key = sys.argv[1]
    entries = data.get('plugins', {}).get(key, [])
    if entries:
        print(entries[0]['installPath'].replace(chr(92), '/'))
    else:
        print('')
except Exception as e:
    print('', file=sys.stderr)
    print('')
" "$plugin_key" 2>/dev/null)

    if [ -z "$cache_target" ] || [ ! -d "$cache_target" ]; then
        echo "  [--] ${plugin}: not installed, skipping"
        ((skipped++)) || true
        continue
    fi

    # Full sync: copy all files from source to installed cache
    changed=0
    added=0

    # Sync all files, preserving directory structure
    # Exclude: __pycache__, .venv, .pytest_cache, .git, *.pyc
    while IFS= read -r -d '' file; do
        rel_path="${file#$src_dir/}"
        target_file="$cache_target/$rel_path"
        target_dir="$(dirname "$target_file")"

        mkdir -p "$target_dir"

        if [ ! -f "$target_file" ]; then
            cp "$file" "$target_file"
            ((added++)) || true
        elif ! diff -q --strip-trailing-cr "$file" "$target_file" > /dev/null 2>&1; then
            cp "$file" "$target_file"
            ((changed++)) || true
        fi
    done < <(find "$src_dir" -type f \
        -not -path "*/__pycache__/*" \
        -not -path "*/.venv/*" \
        -not -path "*/.pytest_cache/*" \
        -not -path "*/.git/*" \
        -not -name "*.pyc" \
        -print0)

    # Remove files in cache that no longer exist in source
    removed=0
    while IFS= read -r -d '' cached_file; do
        rel_path="${cached_file#$cache_target/}"
        src_file="$src_dir/$rel_path"
        if [ ! -f "$src_file" ]; then
            rm "$cached_file"
            ((removed++)) || true
        fi
    done < <(find "$cache_target" -type f \
        -not -path "*/__pycache__/*" \
        -not -path "*/.venv/*" \
        -not -path "*/.pytest_cache/*" \
        -print0)

    if [ "$changed" -gt 0 ] || [ "$added" -gt 0 ] || [ "$removed" -gt 0 ]; then
        echo "  [OK] ${plugin}: ${added} added, ${changed} updated, ${removed} removed"
    else
        echo "  [OK] ${plugin}: up to date"
    fi
    ((synced++)) || true
done

# Step 3: Sync shared/ directory into cache root
# Plugins reference {plugin_root}/../../shared/ which resolves to cache/shipwright/shared/
# Without this, all finalization scripts (record_event, artifact_sync, etc.) are unreachable.
echo ""
echo "Syncing shared/ directory..."
SHARED_SRC="$MARKETPLACE_DIR/shared"
SHARED_TARGET="$HOME/.claude/plugins/cache/shipwright/shared"

if [ -d "$SHARED_SRC" ]; then
    mkdir -p "$SHARED_TARGET"

    shared_changed=0
    shared_added=0

    while IFS= read -r -d '' file; do
        rel_path="${file#$SHARED_SRC/}"
        target_file="$SHARED_TARGET/$rel_path"
        target_dir="$(dirname "$target_file")"

        mkdir -p "$target_dir"

        if [ ! -f "$target_file" ]; then
            cp "$file" "$target_file"
            ((shared_added++)) || true
        elif ! diff -q --strip-trailing-cr "$file" "$target_file" > /dev/null 2>&1; then
            cp "$file" "$target_file"
            ((shared_changed++)) || true
        fi
    done < <(find "$SHARED_SRC" -type f \
        -not -path "*/__pycache__/*" \
        -not -path "*/.venv/*" \
        -not -path "*/.pytest_cache/*" \
        -not -name "*.pyc" \
        -print0)

    # Remove files in cache that no longer exist in source
    shared_removed=0
    while IFS= read -r -d '' cached_file; do
        rel_path="${cached_file#$SHARED_TARGET/}"
        src_file="$SHARED_SRC/$rel_path"
        if [ ! -f "$src_file" ]; then
            rm "$cached_file"
            ((shared_removed++)) || true
        fi
    done < <(find "$SHARED_TARGET" -type f \
        -not -path "*/__pycache__/*" \
        -not -path "*/.venv/*" \
        -not -path "*/.pytest_cache/*" \
        -print0)

    if [ "$shared_changed" -gt 0 ] || [ "$shared_added" -gt 0 ] || [ "$shared_removed" -gt 0 ]; then
        echo "  [OK] shared: ${shared_added} added, ${shared_changed} updated, ${shared_removed} removed"
    else
        echo "  [OK] shared: up to date"
    fi
else
    echo "  [!!] shared/ not found in marketplace"
fi

# Step 4: Create plugins/ directory with symlinks for cross-plugin references
# Several plugins reference siblings via {plugin_root}/../../plugins/shipwright-run/
# In the cache, plugins live at cache/shipwright/shipwright-run/0.2.0/ (flat, no plugins/ subdir).
# We create cache/shipwright/plugins/shipwright-X -> ../shipwright-X/<version>/ symlinks
# so that ../../plugins/shipwright-run resolves correctly.
echo ""
echo "Creating cross-plugin symlinks..."
PLUGINS_LINK_DIR="$HOME/.claude/plugins/cache/shipwright/plugins"
mkdir -p "$PLUGINS_LINK_DIR"

links_created=0
links_updated=0
dirs_synced=0

# Helper: file-by-file copy from $1 to $2, preserving directory structure.
# Used when $link_path exists as a real directory (e.g. Windows where ln -s
# silently degrades to copy/junction, or end-users on older script versions
# that mirrored via copy). Without this, runtime resolves stale code.
sync_dir_from_to() {
    local src="$1" dst="$2"
    mkdir -p "$dst"
    while IFS= read -r -d '' file; do
        local rel="${file#$src/}"
        local target="$dst/$rel"
        mkdir -p "$(dirname "$target")"
        if [ ! -f "$target" ] || ! diff -q --strip-trailing-cr "$file" "$target" > /dev/null 2>&1; then
            cp "$file" "$target"
        fi
    done < <(find "$src" -type f \
        -not -path "*/__pycache__/*" \
        -not -path "*/.venv/*" \
        -not -path "*/.pytest_cache/*" \
        -not -path "*/.git/*" \
        -not -name "*.pyc" \
        -print0)
}

for plugin in "${PLUGINS[@]}"; do
    plugin_key="${plugin}@${MARKETPLACE_NAME}"

    # Get the installed cache path
    cache_target=$("$PYTHON_BIN" -c "
import json, sys, os
try:
    ip = os.path.expanduser('~/.claude/plugins/installed_plugins.json')
    data = json.load(open(ip))
    key = sys.argv[1]
    entries = data.get('plugins', {}).get(key, [])
    if entries:
        print(entries[0]['installPath'].replace(chr(92), '/'))
    else:
        print('')
except Exception:
    print('')
" "$plugin_key" 2>/dev/null)

    if [ -z "$cache_target" ] || [ ! -d "$cache_target" ]; then
        continue
    fi

    link_path="$PLUGINS_LINK_DIR/$plugin"

    # Three cases: existing symlink (re-point if wrong), existing real dir
    # (file-copy fallback), or missing (try symlink, fall back to copy).
    if [ -L "$link_path" ]; then
        current_target=$(readlink "$link_path")
        if [ "$current_target" != "$cache_target" ]; then
            rm "$link_path"
            ln -s "$cache_target" "$link_path"
            ((links_updated++)) || true
        fi
    elif [ -d "$link_path" ]; then
        # Real directory (Windows or legacy install) — file-copy sync.
        sync_dir_from_to "$cache_target" "$link_path"
        ((dirs_synced++)) || true
    elif [ ! -e "$link_path" ]; then
        if ln -s "$cache_target" "$link_path" 2>/dev/null; then
            ((links_created++)) || true
        else
            # Symlink creation failed (likely Windows non-admin) — copy instead.
            sync_dir_from_to "$cache_target" "$link_path"
            ((dirs_synced++)) || true
        fi
    fi
done

if [ "$links_created" -gt 0 ] || [ "$links_updated" -gt 0 ] || [ "$dirs_synced" -gt 0 ]; then
    echo "  [OK] ${links_created} symlinks created, ${links_updated} updated, ${dirs_synced} dirs file-synced"
else
    echo "  [OK] all plugin mirrors up to date"
fi

# Clean up stale version dirs (e.g. 0.0.0 from failed syncs)
echo ""
echo "Cleaning stale cache directories..."
cleaned=0
for plugin in "${PLUGINS[@]}"; do
    plugin_key="${plugin}@${MARKETPLACE_NAME}"
    cache_base="$HOME/.claude/plugins/cache/shipwright/$plugin"

    if [ ! -d "$cache_base" ]; then
        continue
    fi

    # Get installed version
    installed_version=$("$PYTHON_BIN" -c "
import json, sys, os
try:
    ip = os.path.expanduser('~/.claude/plugins/installed_plugins.json')
    data = json.load(open(ip))
    key = sys.argv[1]
    entries = data.get('plugins', {}).get(key, [])
    print(entries[0]['version'] if entries else '')
except Exception:
    print('')
" "$plugin_key" 2>/dev/null)

    if [ -z "$installed_version" ]; then
        continue
    fi

    # Remove version dirs that aren't the installed version
    for version_dir in "$cache_base"/*/; do
        version_name="$(basename "$version_dir")"
        if [ "$version_name" != "$installed_version" ]; then
            rm -rf "$version_dir"
            echo "  Removed stale: ${plugin}/${version_name}"
            ((cleaned++)) || true
        fi
    done
done

if [ "$cleaned" -eq 0 ]; then
    echo "  No stale directories found"
fi

echo ""
echo "=== Done. ${synced} synced, ${skipped} skipped, ${errors} errors ==="
echo "=== Restart Claude Code session to activate changes ==="
