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

# _atomic_sync_dir (below) holds at most one lock at a time — its calls are
# sequential, never parallel, within this script. A single tracked path is
# therefore enough for a script-wide EXIT trap to release whatever lock this
# process currently holds if it dies mid-sync (errexit, Ctrl-C, kill): without
# this, a lock acquired then never released via the function's own normal
# cleanup would deadlock every future sync of that $dst forever.
_CURRENT_SYNC_LOCK=""
trap '[ -n "$_CURRENT_SYNC_LOCK" ] && rm -rf "$_CURRENT_SYNC_LOCK" 2>/dev/null; true' EXIT

# True if $1 names a Windows/MSYS PID that is still alive — used to tell a
# leftover from a process that crashed mid-sync apart from one a CONCURRENT,
# still-running sync still owns (Tier-3 review, PR #796: blindly sweeping by
# name alone can delete another active sync's own staging/backup/lock dirs).
_pid_is_alive() {
    [ -n "$1" ] && kill -0 "$1" 2>/dev/null
}

MARKETPLACE_NAME="shipwright"
MARKETPLACE_DIR="$HOME/.claude/plugins/marketplaces/shipwright"
INSTALLED_PLUGINS="$HOME/.claude/plugins/installed_plugins.json"
HTTPS_URL="https://github.com/svenroth-ai/shipwright.git"

# All plugins in the marketplace
PLUGINS=(
    shipwright-run shipwright-project shipwright-design shipwright-plan
    shipwright-build shipwright-test shipwright-deploy shipwright-changelog
    shipwright-compliance shipwright-security shipwright-iterate shipwright-preview
    shipwright-adopt shipwright-grade
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

# Sync $src into $dst as an ATOMIC directory swap, not a file-by-file
# overwrite of the live target. A live Claude Code session's Stop hook can
# import from $dst (e.g. `lib.campaign_wave`) at any instant; the previous
# implementation copied newly-added files into $dst one at a time via a long
# -running `find | while read` loop, so a brand-new module was simply ABSENT
# from the live cache for the entire loop's duration, until `find`'s
# traversal reached it — a concurrent `import lib.campaign_wave` in that
# window raised ModuleNotFoundError even though the file existed in the repo
# and the marketplace clone (iterate-2026-09-24-stop-hook-cache-race).
# Building the merged tree in a staging dir first and swapping it in with two
# back-to-back `mv`s (each a single atomic rename syscall) shrinks that
# exposure from "however long the copy takes" to the gap between two
# syscalls — no reader ever observes a tree with some files updated and
# others still missing.
_atomic_sync_dir() {
    local src="$1" dst="$2" label="$3" prune="${4:-prune}"
    local staging="${dst}.sync-new.$$"
    local old="${dst}.sync-old.$$"
    local lock="${dst}.sync.lock"

    # Serialize concurrent syncs of the SAME $dst (Tier-3 review, PR #796):
    # without this, two runs race the final mv-swap below and can interleave
    # it, and the leftover sweep just below could delete an ACTIVE run's own
    # staging/old dirs, not just a dead one's. `mkdir` is atomic on POSIX and
    # NTFS-via-MSYS alike, so it doubles as a portable mutex with no `flock`
    # dependency. A PID file inside lets a later run tell a live holder apart
    # from one that crashed mid-sync and self-heal past the stale lock instead
    # of deadlocking every future sync of this $dst forever.
    local waited=0 holder_pid=""
    while ! mkdir "$lock" 2>/dev/null; do
        holder_pid=$(cat "$lock/pid" 2>/dev/null || echo "")
        if ! _pid_is_alive "$holder_pid"; then
            rm -rf "$lock" 2>/dev/null || true
            continue
        fi
        if [ "$waited" -ge 120 ]; then
            echo "  [!!] ${label}: timed out waiting for pid ${holder_pid} to finish syncing $dst" >&2
            return 1
        fi
        sleep 1
        waited=$((waited + 1))
    done
    echo "$$" > "$lock/pid"
    _CURRENT_SYNC_LOCK="$lock"

    # A prior run killed mid-swap (Ctrl-C, timeout) leaves its own PID-named
    # staging/old dirs behind forever — nothing else ever matches that PID
    # again to clean them up. Self-heal by sweeping DEAD-process leftovers for
    # this $dst before starting a fresh one; the lock above already rules out
    # a live concurrent holder, but a name-only match here would still be
    # blind to that distinction on its own.
    for leftover in "${dst}".sync-new.* "${dst}".sync-old.*; do
        [ -e "$leftover" ] || continue
        if ! _pid_is_alive "${leftover##*.}"; then
            rm -rf "$leftover" 2>/dev/null || true
        fi
    done
    rm -rf "$staging"
    mkdir -p "$staging"

    # Pre-create the directory skeleton from $src's own tree in ONE pass,
    # instead of a per-file `mkdir -p "$(dirname "$target")"` — that idiom
    # forks a subshell for the `$(...)`, an external `dirname`, AND `mkdir`,
    # i.e. up to 3 process spawns PER FILE. Over shared/'s ~1800 files that
    # measured as the dominant cost of a 180+ second hang on Windows Git
    # Bash, where each spawn is a full CreateProcess call. `${dir#$src/}` is
    # a bash builtin substitution — no subprocess at all.
    # Exclusions must match the file-copy loop below EXACTLY (`-name` for the
    # dir itself, `-path .../name/*` for anything nested under it) — a looser
    # pattern here (e.g. `*/.git*` without the trailing slash) also matches
    # unrelated names like `.github`, leaving a directory the file loop still
    # expects to exist uncreated (`cp: ... No such file or directory`).
    while IFS= read -r -d '' dir; do
        mkdir -p "$staging/${dir#$src/}"
    done < <(find "$src" -type d \
        -not -name "__pycache__" -not -path "*/__pycache__/*" \
        -not -name ".venv" -not -path "*/.venv/*" \
        -not -name ".pytest_cache" -not -path "*/.pytest_cache/*" \
        -not -name ".git" -not -path "*/.git/*" \
        -print0)

    # __pycache__/.venv/.pytest_cache: bulk `cp -r` per matched top-level dir
    # (found via `-prune`, so a nested one under `.venv` isn't independently
    # matched and double-copied) — these can be tens of thousands of tiny
    # files, far too slow to copy one at a time on Windows.
    if [ -d "$dst" ]; then
        while IFS= read -r -d '' cache_dir; do
            local rel="${cache_dir#$dst/}"
            mkdir -p "$(dirname "$staging/$rel")"
            cp -r "$cache_dir" "$staging/$rel"
        done < <(find "$dst" \( -name "__pycache__" -o -name ".venv" -o -name ".pytest_cache" \) -prune -print0)
    fi

    # Single pass over $src, comparing each file directly against the LIVE
    # $dst — NOT a staging seed copied in first. An earlier revision seeded
    # every existing file into staging, then diffed $src against that seed
    # here: a full second copy-and-compare pass over the entire tree, for
    # nothing, on top of the per-file mkdir cost above. Unchanged files are
    # linked (not copied) from $dst: content is already verified identical,
    # so `cp -l` skips the read+write I/O and just adds a directory entry.
    local added=0 changed=0 removed=0
    while IFS= read -r -d '' file; do
        local rel_path="${file#$src/}"
        local target_file="$staging/$rel_path"
        local dst_file="$dst/$rel_path"

        if [ ! -f "$dst_file" ]; then
            cp "$file" "$target_file"
            ((added++)) || true
        elif ! diff -q --strip-trailing-cr "$file" "$dst_file" > /dev/null 2>&1; then
            cp "$file" "$target_file"
            ((changed++)) || true
        else
            cp -l "$dst_file" "$target_file" 2>/dev/null || cp "$dst_file" "$target_file"
        fi
    done < <(find "$src" -type f \
        -not -path "*/__pycache__/*" \
        -not -path "*/.venv/*" \
        -not -path "*/.pytest_cache/*" \
        -not -path "*/.git/*" \
        -not -name "*.pyc" \
        -not -name ".python-version" \
        -print0)

    # Files present in the old target but absent from $src (renamed/deleted
    # upstream) were never copied into staging above, so nothing needs
    # deleting here — this just counts them for the summary line. For
    # $prune=noprune (the Windows real-dir plugin mirror, which must PRESERVE
    # mirror-owned files the old behavior always kept) they are instead
    # copied into staging now, since nothing seeded them earlier either.
    if [ -d "$dst" ]; then
        while IFS= read -r -d '' dst_file; do
            local rel="${dst_file#$dst/}"
            if [ ! -f "$src/$rel" ]; then
                if [ "$prune" = "prune" ]; then
                    ((removed++)) || true
                else
                    local target="$staging/$rel"
                    mkdir -p "$(dirname "$target")"
                    cp "$dst_file" "$target"
                fi
            fi
        done < <(find "$dst" -type f \
            -not -path "*/__pycache__/*" \
            -not -path "*/.venv/*" \
            -not -path "*/.pytest_cache/*" \
            -print0)
    fi

    rm -rf "$old" 2>/dev/null || true
    if [ -d "$dst" ]; then
        mv "$dst" "$old"
    fi
    mv "$staging" "$dst"
    rm -rf "$old" 2>/dev/null || true

    rm -rf "$lock" 2>/dev/null || true
    _CURRENT_SYNC_LOCK=""

    if [ "$changed" -gt 0 ] || [ "$added" -gt 0 ] || [ "$removed" -gt 0 ]; then
        echo "  [OK] ${label}: ${added} added, ${changed} updated, ${removed} removed"
    else
        echo "  [OK] ${label}: up to date"
    fi
}

# Resolve a plugin's installed cache path from installed_plugins.json (empty
# when the plugin is not installed). Single source of truth for the three
# lookups below. Uses $PYTHON_BIN (never a bare `python` — F37).
_install_path() {
    "$PYTHON_BIN" -c "
import json, sys, os
try:
    ip = os.path.expanduser('~/.claude/plugins/installed_plugins.json')
    data = json.load(open(ip))
    entries = data.get('plugins', {}).get(sys.argv[1], [])
    print(entries[0]['installPath'].replace(chr(92), '/') if entries else '')
except Exception:
    print('')
" "$1" 2>/dev/null
}

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

# Verify the clone actually reached origin/main's true tip. The CLI path
# above can exit 0 without a guaranteed fresh fetch (its internal update
# mechanism is opaque to this script) — trusting that blindly let a file that
# "landed on main just ahead of the sync run" go missing from the cache
# after a reported-successful sync, because Steps 2-3 below copy whatever is
# in $MARKETPLACE_DIR without ever checking it against the real remote.
# Cross-check regardless of which branch above ran, and force a hard sync
# when the clone lags, BEFORE any file is copied.
if [ -d "$MARKETPLACE_DIR/.git" ]; then
    # `|| true` on each: under `set -euo pipefail` an offline `ls-remote` (or a
    # `rev-parse` on a corrupt clone) would otherwise abort the whole sync here
    # instead of degrading to "skip this check" like every other advisory probe
    # in this script.
    remote_head=$( (git ls-remote "$HTTPS_URL" refs/heads/main 2>/dev/null | cut -f1) || true)
    local_head=$(git -C "$MARKETPLACE_DIR" rev-parse HEAD 2>/dev/null || echo "")
    if [ -n "$remote_head" ] && [ "$remote_head" != "$local_head" ]; then
        echo "[!!] Marketplace clone lagging origin/main (${local_head:-none} != $remote_head), forcing hard sync..."
        git -C "$MARKETPLACE_DIR" remote set-url origin "$HTTPS_URL" 2>/dev/null || true
        git -C "$MARKETPLACE_DIR" fetch origin main
        git -C "$MARKETPLACE_DIR" reset --hard origin/main
    fi
fi

# Step 2: Full file sync from marketplace into installed plugin caches
# Reads the installed cache path from installed_plugins.json so we always
# write to the correct version directory (e.g. 0.2.0), not whatever version
# is in the source plugin.json.
echo ""
echo "Full sync: marketplace → plugin caches..."

installed=0
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

    # Resolve the installed cache path; INSTALL the plugin first when it is
    # registered in the marketplace but not yet installed, so this script brings
    # EVERY registered plugin into the cache instead of silently skipping a
    # not-yet-installed one (the opt-in shipwright-grade lead magnet was left
    # `not_in_cache` forever otherwise). Install is non-fatal under `set -e`: an
    # offline / headless run that can't install just skips that plugin.
    cache_target=$(_install_path "$plugin_key")

    if [ -z "$cache_target" ] || [ ! -d "$cache_target" ]; then
        echo "  [..] ${plugin}: not installed — installing from marketplace..."
        if claude plugin install "$plugin_key" >/dev/null 2>&1; then
            cache_target=$(_install_path "$plugin_key")
            ((installed++)) || true
        fi
    fi

    if [ -z "$cache_target" ] || [ ! -d "$cache_target" ]; then
        echo "  [--] ${plugin}: install unavailable (offline/CLI), skipping"
        ((skipped++)) || true
        continue
    fi

    # `.python-version` is EXCLUDED on purpose (iterate-2026-08-01-pin-python-311).
    # Each plugin dir carries one so a contributor's `cd plugins/x && uv run pytest
    # tests/` uses the 3.11 this repo's CI judges pushes with. That is a MONOREPO
    # fact. Shipping it would make it an END-USER one: skills invoke `uv run --project
    # {plugin_root}` (shipwright-plan/skills/plan/SKILL.md, 5 sites), and uv honours a
    # version file in the --project dir - measured, 3.12.13 -> 3.11.15. Consumers
    # declare `>=3.11` and must keep resolving whatever satisfies that; forcing an
    # interpreter download on them, or failing where downloads are blocked, is not
    # this repo's call to make. (Enforced inside `_atomic_sync_dir`'s find call.)
    _atomic_sync_dir "$src_dir" "$cache_target" "$plugin"
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
    _atomic_sync_dir "$SHARED_SRC" "$SHARED_TARGET" "shared"
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

# Helper: atomic copy from $1 to $2, preserving directory structure.
# Used when $link_path exists as a real directory (e.g. Windows where ln -s
# silently degrades to copy/junction, or end-users on older script versions
# that mirrored via copy). Without this, runtime resolves stale code.
sync_dir_from_to() {
    _atomic_sync_dir "$1" "$2" "$(basename "$2")" noprune >/dev/null
}

for plugin in "${PLUGINS[@]}"; do
    plugin_key="${plugin}@${MARKETPLACE_NAME}"

    # Get the installed cache path (Step 2 installed any missing ones already).
    cache_target=$(_install_path "$plugin_key")

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
echo "=== Done. ${installed} installed, ${synced} synced, ${skipped} skipped, ${errors} errors ==="
echo "=== Restart Claude Code session to activate changes ==="
