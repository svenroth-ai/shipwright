#!/usr/bin/env bash
# Install the shipwright pre-commit gates by pointing git at
# scripts/hooks/.  Idempotent.  Non-destructive: refuses to replace an
# existing different `core.hooksPath` without `--force`.
#
# Usage:
#   bash scripts/install-hooks.sh           # install / verify
#   bash scripts/install-hooks.sh --force   # override existing path

set -euo pipefail

target_path="scripts/hooks"
force=0
if [ "${1:-}" = "--force" ]; then
    force=1
fi

repo_root="$(git rev-parse --show-toplevel)"
cd "$repo_root"

current="$(git config --local --default '' core.hooksPath || true)"

if [ "$current" = "$target_path" ]; then
    echo "install-hooks: core.hooksPath already set to '$target_path' — ok"
    exit 0
fi

if [ -n "$current" ] && [ "$force" -eq 0 ]; then
    cat >&2 <<EOF
install-hooks: refused to overwrite existing core.hooksPath.

  current value:   $current
  shipwright wants: $target_path

To replace it run:
  bash scripts/install-hooks.sh --force

To restore the previous value later:
  git config --local core.hooksPath '$current'
EOF
    exit 1
fi

git config --local core.hooksPath "$target_path"
echo "install-hooks: core.hooksPath -> $target_path"

# Belt-and-suspenders — make the hook executable on POSIX-style file
# systems.  On Windows Git these mode bits are mostly cosmetic but
# harmless.
chmod +x "$target_path"/* 2>/dev/null || true
