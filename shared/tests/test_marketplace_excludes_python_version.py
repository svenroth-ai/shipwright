"""Regression: the interpreter pin is a MONOREPO fact and must not be distributed.

`iterate-2026-08-01-pin-python-311` put a `.python-version` in each plugin directory
so a contributor's `cd plugins/<name> && uv run pytest tests/` runs the 3.11 this
repo's CI judges pushes with. `update-marketplace.sh` copies plugin trees into
`~/.claude/plugins/cache/shipwright/` with a `find -type f` that includes dotfiles, and
skills invoke `uv run --project {plugin_root}` (shipwright-plan/skills/plan/SKILL.md,
five call sites). uv honours a version file in the `--project` directory — measured
3.12.13 -> 3.11.15 — so shipping those files would force 3.11 onto every end user of
the plugins, who only ever agreed to `requires-python = ">=3.11"`, and would break them
outright where interpreter downloads are blocked.

Raised by the Stage-3 doubt reviewer: the adopted-project objection failed against the
F0 runner (monorepo-shaped, opt-in) and landed here instead, through the plugin payload.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
UPDATE_SH = REPO_ROOT / "scripts" / "update-marketplace.sh"

_FIND_BLOCK = re.compile(r"find \"\$(\w+)\" -type f(.*?)-print0", re.DOTALL)
#: The shell vars naming a SOURCE tree that gets copied into the cache. The sibling
#: blocks scan a TARGET tree to prune what source no longer has — those must NOT carry
#: the exclusion, or a `.python-version` synced before this change would be immortal in
#: every existing cache.
_COPY_SOURCES = {"src_dir", "SHARED_SRC", "src"}


def test_every_copy_path_excludes_the_version_file():
    """Asserted per BLOCK, not once over the file.

    A single `".python-version" in text` check passes while one of the three copy paths
    still ships it — which is the only way this regression can actually occur.
    """
    blocks = _FIND_BLOCK.findall(UPDATE_SH.read_text(encoding="utf-8"))
    assert blocks, "no `find -type f ... -print0` block found — has the sync been rewritten?"
    copies = [(var, body) for var, body in blocks if var in _COPY_SOURCES]
    assert len(copies) == len(_COPY_SOURCES), (
        f"expected a copy block for each of {sorted(_COPY_SOURCES)}, found "
        f"{sorted(v for v, _ in copies)} — the sync's shape changed, re-check this guard")
    leaky = [var for var, body in copies if '-not -name ".python-version"' not in body]
    assert not leaky, (
        f"copy path(s) {leaky} would sync .python-version into the plugin cache. Skills "
        "run `uv run --project {plugin_root}`, and uv honours a version file there, so "
        "this forces the monorepo's 3.11 pin onto end users who only declared >=3.11 — "
        "and hard-fails them where uv cannot download 3.11.")


def test_the_prune_paths_do_not_exclude_it():
    """The other half of the contract, and the reason this is not a whole-file check.

    The target-side scans are how a `.python-version` copied into a cache BEFORE this
    change gets removed. Excluding it there too would leave every already-synced cache
    permanently pinned, with no code path able to clean it up.
    """
    blocks = _FIND_BLOCK.findall(UPDATE_SH.read_text(encoding="utf-8"))
    prunes = [(var, body) for var, body in blocks if var not in _COPY_SOURCES]
    assert prunes, "no target-side prune block found — stale cache entries would never be removed"
    over_excluded = [var for var, body in prunes if '-not -name ".python-version"' in body]
    assert not over_excluded, (
        f"prune path(s) {over_excluded} skip .python-version, so a copy synced before "
        "iterate-2026-08-01-pin-python-311 can never be cleaned out of an existing cache")
