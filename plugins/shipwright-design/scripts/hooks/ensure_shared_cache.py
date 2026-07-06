#!/usr/bin/env python3
"""SessionStart hook: self-heal the shared/ cache for marketplace installs.

Every Shipwright plugin hook invokes shared helpers as
``uv run "${CLAUDE_PLUGIN_ROOT}/../../shared/scripts/hooks/<x>.py"`` — i.e. it
expects a sibling ``shared/`` directory two levels above the plugin root
(``.../plugins/cache/shipwright/shared`` for a marketplace install). But a plain
``claude plugin install`` copies ONLY each plugin's own source into the cache;
``shared/`` is not a plugin, so it is never delivered. Only the dev script
``scripts/update-marketplace.sh`` creates it, so on a fresh end-user install
every ``../../shared/*`` hook 404s (fail-open, but noisy — the symptom that
prompted this hook was ``track_tool_calls.py`` "can't find its own path").

This hook self-heals: when the expected ``shared/`` is missing it mirrors it from
the marketplace full-clone (``~/.claude/plugins/marketplaces/<name>/shared``,
which a marketplace install DOES carry) into the cache. It is:

- **stdlib-only** — it can never depend on the very ``shared/`` it repairs;
- **fail-open** — any error exits 0 so a session is never blocked;
- **idempotent** — a fast sentinel check makes it a no-op once healed (and in the
  ``--plugin-dir`` dev model, where ``shared/`` is the real repo dir, always).

This file is the CANONICAL source vendored byte-identically into every
hook-bearing plugin's ``scripts/hooks/`` (a plugin-local hook is the only thing a
marketplace install reliably delivers). Drift between the canonical and the
vendored copies — and their registration in each plugin's SessionStart — is
gated by ``shared/tests/test_ensure_shared_cache_vendored.py``. Edit here, then
re-vendor to all copies (the test tells you which are stale).
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

# A file that always exists inside a healthy shared/ tree — used both as the
# "is shared/ present?" sentinel and to validate a discovered marketplace clone.
_SENTINEL = ("scripts", "lib", "project_root.py")
_IGNORE = shutil.ignore_patterns("__pycache__", "*.pyc", ".venv", ".pytest_cache", ".git")


def _healthy(shared_dir: Path) -> bool:
    """True when ``shared_dir`` looks like a real Shipwright shared/ tree."""
    return shared_dir.is_dir() and shared_dir.joinpath(*_SENTINEL).is_file()


def _find_marketplace_shared(cache_marketplace_root: Path) -> Path | None:
    """Locate the marketplace full-clone's shared/ dir, or None.

    ``cache_marketplace_root`` is ``.../.claude/plugins/cache/<name>``; the clone
    lives at ``.../.claude/plugins/marketplaces/<name>``. Try the same-name path
    first, then scan ``marketplaces/*/shared`` for any clone carrying the sentinel
    (covers a marketplace added under a non-default name).
    """
    plugins_root = cache_marketplace_root.parent.parent  # cache/<name> -> cache -> plugins
    marketplaces = plugins_root / "marketplaces"
    if not marketplaces.is_dir():
        return None
    same = marketplaces / cache_marketplace_root.name / "shared"
    if _healthy(same):
        return same
    for entry in sorted(marketplaces.iterdir()):
        candidate = entry / "shared"
        if _healthy(candidate):
            return candidate
    return None


def main() -> int:
    # Hook protocol: consume stdin, never fail on it.
    try:
        json.load(sys.stdin)
    except Exception:
        pass

    try:
        plugin_root = Path(__file__).resolve().parents[2]  # scripts/hooks/<f> -> plugin root
        shared_target = plugin_root.parent.parent / "shared"  # ${CLAUDE_PLUGIN_ROOT}/../../shared

        if _healthy(shared_target):
            return 0  # already present (dev repo dir, or a prior heal) — no-op

        source = _find_marketplace_shared(shared_target.parent)  # shared_target.parent == cache/<name>
        if source is None:
            print(
                "shipwright: shared/ is missing from the plugin cache and no "
                "marketplace clone was found to self-heal from. Run "
                "`bash scripts/update-marketplace.sh` from the shipwright repo "
                "to restore it.",
                file=sys.stderr,
            )
            return 0  # fail-open

        shutil.copytree(source, shared_target, ignore=_IGNORE, dirs_exist_ok=True)
        print(f"shipwright: self-healed the shared/ plugin cache from {source}", file=sys.stderr)
    except Exception as exc:  # never block a session
        print(f"shipwright: ensure_shared_cache skipped ({exc!r})", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
