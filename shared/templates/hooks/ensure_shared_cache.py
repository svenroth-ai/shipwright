#!/usr/bin/env python3
"""SessionStart hook: self-heal the plugin cache for marketplace installs.

Plugins reach shared and sibling-plugin code two levels above the plugin root
(``${CLAUDE_PLUGIN_ROOT}/../../{shared,plugins}/...``), but a plain
``claude plugin install`` delivers neither tree — only the dev script
``scripts/update-marketplace.sh`` creates them, so on a fresh install those refs
404. Full account: ``docs/hooks-and-pipeline.md`` § "Shared Hook:
ensure_shared_cache.py".

This hook self-heals both, stdlib-only + fail-open + idempotent: ``shared/`` from
the marketplace full-clone (``marketplaces/<name>/shared``, which an install DOES
carry), and ``plugins/`` from the already-installed versioned plugin dirs
(``cache/<name>/shipwright-X/<version>``) — no clone needed for that half.

Any error exits 0 (a session is never blocked); a per-tree COMPLETENESS check
makes it a no-op once healed, and always in the ``--plugin-dir`` dev model. This
file is the CANONICAL source vendored byte-identically into every hook-bearing
plugin's ``scripts/hooks/`` (a plugin-local file is the only reliable marketplace
delivery), gated by ``shared/tests/test_ensure_shared_cache_vendored.py``. Edit
here, then re-vendor.

**Completeness, not liveness.** Until 2026-08-01 each tree was judged from ONE
sentinel file, which answers "was this tree ever created?" but never "is it
whole?" — so the *partial* reap this hook exists to survive read as healthy and
was never repaired (measured: ADR-120). Both trees are now compared file-set
against their repair source. Presence only, never content: clone and cache
differ in line endings (24 of 1015 files, measured), so a content rule here
would re-copy them every session; staleness is ``check_plugin_cache_sync.py``'s
job and it CRLF-normalizes before hashing.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import sys
from pathlib import Path

# A cheap liveness probe for shared/ — "was it ever delivered?" only.
_SHARED_SENTINEL = ("scripts", "lib", "project_root.py")

# What a copy never delivers. MUST stay a superset of what the PRODUCERS of
# these trees exclude — ``update-marketplace.sh`` (writes them) and
# ``cache_tree_compare.SKIP_DIRS`` (checks them). Duplicated on purpose
# (stdlib-only) and pinned both ways by
# ``shared/tests/test_ensure_shared_cache_ssot_pins.py``.
#
# A name a producer excludes but this set counts is a PERMANENT phantom gap: the
# tree can never satisfy the check, so the hook re-copies every session forever.
# ``.in_use/<pid>`` (the cache manager's volatile refcount, in the INSTALLED
# plugin dirs) showed a gap on all 14 mirrors — measured; ``.python-version`` is
# tracked in all 14 plugins but withheld from the cache on purpose
# (iterate-2026-08-01-pin-python-311), latent until an install delivers one.
_IGNORE_NAMES = ("__pycache__", "*.pyc", "*.pyo", ".venv", ".pytest_cache",
                 ".git", "node_modules", ".in_use", ".orphaned_at",
                 ".python-version")

#: The ONE ignore callable — the walk below and every copytree() share it, so
#: the walk can never demand a file the copy would not write.
_IGNORE = shutil.ignore_patterns(*_IGNORE_NAMES)


def _shared_healthy(shared_dir: Path) -> bool:
    return shared_dir.is_dir() and shared_dir.joinpath(*_SHARED_SENTINEL).is_file()


def _delivered(root: Path) -> set[str] | None:
    """Relative posix paths of the files ``copytree(root, …, ignore=_IGNORE)``
    would deliver — or ``None`` if the tree could not be fully enumerated.

    Top-down exactly like copytree: ``_IGNORE`` is asked about each directory's
    OWN child names and ignored directories are pruned BEFORE descending (an
    ``rglob()`` would walk into ``.in_use`` and only then discard it).

    ``None`` is the whole point of the return type. Swallowing an ``OSError``
    and returning a SHORT set would under-count the source and so manufacture a
    false "complete" verdict — this hook's original bug, re-entered through the
    error path. Unknown must stay distinguishable from empty. It also makes a
    symlink/junction LOOP safe without a costly visited-set: a loop ends in an
    ``OSError`` and lands here as unknown — bounded, never a hang.
    """
    if not root.is_dir():
        return None
    out: set[str] = set()
    stack = [root]
    while stack:
        current = stack.pop()
        try:
            entries = list(current.iterdir())
        except OSError:
            return None
        ignored = _IGNORE(str(current), [e.name for e in entries])
        for entry in entries:
            if entry.name in ignored:
                continue
            try:
                if entry.is_dir():
                    stack.append(entry)
                elif entry.is_file():
                    # Case-fold on Windows only: its filesystem is case-
                    # INSENSITIVE, so a case-only difference is a gap copytree
                    # could never close. NOT os.path.normcase — that also rewrites
                    # separators, breaking these posix keys.
                    rel = entry.relative_to(root).as_posix()
                    out.add(rel.lower() if os.name == "nt" else rel)
                # anything else (a broken symlink) is deliberately unrecorded:
                # on the destination side it must read MISSING, not present.
            except OSError:
                return None
    return out


def _incomplete(src: Path, dst: Path) -> bool | None:
    """Is ``dst`` missing any file a copy of ``src`` would deliver?

    ``None`` means "cannot tell" — the caller must then neither claim health nor
    copy. Comparing two file-only SETS (never ``dst.exists()``) makes the check
    type-aware for free: a directory or broken symlink standing where a file
    belongs is simply absent from ``dst``'s set.
    """
    want = _delivered(src)
    if want is None:
        return None
    if not dst.is_dir():
        return True
    have = _delivered(dst)
    if have is None:
        return None
    return bool(want - have)


def _same_name_shared(cache_marketplace_root: Path) -> Path | None:
    """The clone that belongs to THIS cache: ``marketplaces/<same name>/shared``.

    The only clone allowed to answer "is the cached tree complete?". A foreign
    marketplace's ``shared/`` is a fine last resort when ours is missing outright,
    but never authoritative about ours: judging completeness against a stranger's
    tree reports its extra files as our gaps and copies its code in every session.
    """
    same = cache_marketplace_root.parent.parent / "marketplaces" / \
        cache_marketplace_root.name / "shared"
    return same if _shared_healthy(same) else None


def _find_marketplace_shared(cache_marketplace_root: Path) -> Path | None:
    """Locate a marketplace full-clone's shared/ dir to restore from, or None.

    Same-name clone first, then any ``marketplaces/*/shared`` carrying the
    sentinel. Used only when the cached ``shared/`` is ABSENT — see
    :func:`_same_name_shared` for why a scan cannot decide completeness.
    """
    plugins_root = cache_marketplace_root.parent.parent  # cache/<name> -> cache -> plugins
    marketplaces = plugins_root / "marketplaces"
    if not marketplaces.is_dir():
        return None
    same = _same_name_shared(cache_marketplace_root)
    if same is not None:
        return same
    try:
        entries = sorted(marketplaces.iterdir())
    except OSError:
        return None
    for entry in entries:
        candidate = entry / "shared"
        if _shared_healthy(candidate):
            return candidate
    return None


_SEMVER_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)(.*)$")


def _version_key(name: str) -> tuple:
    """Numeric-tuple sort key for SemVer-shaped dir names.

    A pure lexical sort puts ``0.10.0`` BEFORE ``0.2.0`` (``'1' < '2'``). That
    was harmless while the loop skipped on ``dst.exists()`` — the wrong pick was
    never read. Now the pick is the *authority* on whether the mirror is
    complete, so choosing an older version would compare against stale content
    and copy it over a perfectly good mirror. Mirrors
    ``cache_tree_compare.version_key`` (not importable here — stdlib-only), and
    pinned equal to it by a test; non-SemVer names sort before any version.
    """
    m = _SEMVER_RE.match(name)
    if not m:
        return (-1, -1, -1, name)
    return (int(m.group(1)), int(m.group(2)), int(m.group(3)), m.group(4) or "")


def _plugin_mirrors(cache_marketplace_root: Path, plugins_target: Path):
    """Yield ``(newest_installed_version_dir, mirror_dir)`` per installed plugin.

    The ``shipwright-`` name filter keeps this safe in the dev model (a repo root
    has no ``shipwright-*`` top-level dirs, so nothing is yielded)."""
    try:
        candidates = sorted(cache_marketplace_root.iterdir())
    except OSError:
        return
    for plugin_dir in candidates:
        if not plugin_dir.is_dir() or not plugin_dir.name.startswith("shipwright-"):
            continue
        try:
            versions = sorted((v for v in plugin_dir.iterdir() if v.is_dir()),
                              key=lambda v: _version_key(v.name))
        except OSError:
            continue
        if versions:
            yield versions[-1], plugins_target / plugin_dir.name


def _heal_plugins(cache_marketplace_root: Path, plugins_target: Path) -> bool:
    """Mirror each installed plugin (``cache/<name>/shipwright-X/<version>``) into
    ``cache/<name>/plugins/shipwright-X`` so ``../../plugins/shipwright-X`` refs
    resolve. Needs no marketplace clone.

    Self-no-op'ing, which is why ``main()`` can call it unconditionally: a mirror
    that is already complete is skipped. It used to skip on ``dst.exists()``,
    which meant a mirror that existed but had been half-reaped was never
    repaired even on the rare path that reached this loop at all.
    """
    healed = False
    for src, dst in _plugin_mirrors(cache_marketplace_root, plugins_target):
        # update-marketplace.sh makes the mirror a SYMLINK to the installed
        # version dir on POSIX. The syncer owns it, and copying THROUGH a stale
        # link would write into an OLDER installed version's directory — a tree
        # this hook neither owns nor can put back. The old `dst.exists()` skip
        # hid this by accident; a completeness check reaches it, so say it.
        if dst.is_symlink():
            continue
        if _incomplete(src, dst) is not True:
            continue  # complete, or unknowable — never claim, never copy
        try:
            shutil.copytree(src, dst, ignore=_IGNORE, dirs_exist_ok=True)
        except OSError:
            continue  # one unwritable mirror must not block the other thirteen
        healed = True
    return healed


def main() -> int:
    # Hook protocol: consume stdin, never fail on it.
    try:
        json.load(sys.stdin)
    except Exception:
        pass

    try:
        plugin_root = Path(__file__).resolve().parents[2]  # scripts/hooks/<f> -> plugin root
        cache_root = plugin_root.parent.parent             # cache/<name> (or the repo, in dev)
        shared_target = cache_root / "shared"
        plugins_target = cache_root / "plugins"

        healed: list[str] = []

        # shared/ — restore when it was never delivered (any clone will do), or
        # top it up when OUR OWN clone proves the delivered copy is incomplete.
        # There is no combined early return any more: it let a surviving sentinel
        # on EITHER tree suppress the repair of BOTH. Completeness is asserted
        # only when a comparison basis exists, so the dev model — which has no
        # marketplace clone — stays silent instead of alarming every session.
        if not _shared_healthy(shared_target):
            source = _find_marketplace_shared(cache_root)
        else:
            own = _same_name_shared(cache_root)
            source = own if own is not None and _incomplete(own, shared_target) is True else None
        if source is not None:
            try:
                shutil.copytree(source, shared_target, ignore=_IGNORE, dirs_exist_ok=True)
                healed.append("shared")
            except OSError:
                pass  # isolated: a failed shared/ copy must not skip plugins/

        # plugins/ — unconditional; _heal_plugins is a no-op when every mirror
        # is whole, so it needs no gate of its own (and the gate it used to have
        # was the bug: one sentinel file standing for all fourteen mirrors).
        if _heal_plugins(cache_root, plugins_target):
            healed.append("plugins")

        if healed:
            print(f"shipwright: self-healed the plugin cache ({', '.join(healed)})", file=sys.stderr)
        if not _shared_healthy(shared_target):
            print(
                "shipwright: shared/ is missing from the plugin cache and no "
                "marketplace clone was found to self-heal from. Run "
                "`bash scripts/update-marketplace.sh` from the shipwright repo "
                "to restore it.",
                file=sys.stderr,
            )
    except Exception as exc:  # never block a session
        print(f"shipwright: ensure_shared_cache skipped ({exc!r})", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
