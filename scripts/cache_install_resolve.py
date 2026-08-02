#!/usr/bin/env python3
"""Which cache version directory is the live one — the sync's answer, not a guess.

`update-marketplace.sh` copies each plugin into the directory named by
`installed_plugins.json` (`_install_path`, used for the copy target, the cross-plugin
mirror and the stale-dir cleanup). `check_plugin_cache_sync.py` used to pick the highest
SemVer directory instead. Those agree only because the sync's last step deletes every
version dir that is not the installed one — so one survivor (a `rm -rf` that lost to a
Windows file lock, a `claude plugin install` that materialised the repo's newer version,
an aborted run) makes the producer and the checker describe different trees.

Measured 2026-08-01: all 14 plugins carry repo version 0.31.0 against installed 0.2.x, so
a survivor always sorts ABOVE the live directory. The sync then reports "up to date"
while `--strict` reports every repo file missing — the P2.06 symptom, both halves at once.

A separate module because `cache_tree_compare` is at 289 of its 300 lines; `cache_file_hash`
was split out of it for the same reason.

Deliberately as TOLERANT as the shell it mirrors, and no more. The real manifest carries a
top-level ``version: 2`` that `_install_path` never inspects; validating it here would make
this side reject files the producer happily writes — a NEW disagreement of exactly the kind
this module exists to end. Every failure path falls back to the caller's heuristic and says
so, because a detective check must never crash a session over another program's file.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path, PurePosixPath

# APPEND, never insert: this directory holds top-level module names, and winning
# resolution for the whole process is the ADR-045 collision class one dir over.
if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.append(str(Path(__file__).resolve().parent))

from cache_tree_compare import latest_cache_version_dir  # noqa: E402

#: The marketplace whose plugins this repo ships: half of the `<plugin>@<marketplace>`
#: lookup key, and the last component of the cache root — which is DERIVED from it below,
#: so that second half is a fact about the code rather than a claim in a comment.
#: `MARKETPLACE_NAME` in the shell, pinned to it by test_plugin_cache_version_resolution.py.
#: A second marketplace really is present in the live manifest (`openai-codex`), so a bare
#: plugin name would match the wrong entry.
MARKETPLACE_NAME = "shipwright"

#: The two manifest keys the shell reads: ``data['plugins'][key][0]['installPath']``.
PLUGINS_KEY = "plugins"
INSTALL_PATH_KEY = "installPath"


def default_installed_plugins_path() -> Path:
    """The manifest the sync reads, expressed against $HOME as the shell expresses it."""
    return Path.home() / ".claude" / "plugins" / "installed_plugins.json"


def default_cache_root() -> Path:
    """``~/.claude/plugins/cache/<marketplace>`` — the tree the sync writes into."""
    return Path.home() / ".claude" / "plugins" / "cache" / MARKETPLACE_NAME


def manifest_for(explicit: str | None, cache_root: Path) -> Path | None:
    """The manifest to trust for ``cache_root`` — explicit, implied, or none at all.

    ``installed_plugins.json`` describes the REAL cache. Handing it to every run regardless
    of ``--cache-root`` would make the check read this machine's state while measuring some
    other tree: a test seeding a real plugin name into a tmp cache would resolve a version
    dir that exists only in the developer's home, go red locally and stay green in CI, where
    ``~/.claude`` is absent. So it applies by default only to the root it describes — point
    the check elsewhere and the manifest has to be named explicitly to be used.
    """
    if explicit:
        return Path(explicit)
    return default_installed_plugins_path() if cache_root == default_cache_root() else None


def plugin_key(plugin_name: str, marketplace: str = MARKETPLACE_NAME) -> str:
    """``<plugin>@<marketplace>`` — the shell's ``"${plugin}@${MARKETPLACE_NAME}"``."""
    return f"{plugin_name}@{marketplace}"


def _probe_missing_dir(candidate: Path) -> str:
    """Why is ``candidate`` not a usable directory — ``absent`` or ``unreadable``?

    The caller keeps those apart: ``absent`` prints "run update-marketplace.sh",
    ``unreadable`` refuses to report a file count it never measured. Asked of the CANDIDATE;
    asking its parent instead answers "can I list the plugin dir?", so a denied or locked
    version dir under a perfectly listable parent would come back ``absent`` and every
    tracked file would be reported missing on the strength of no measurement at all.

    Scope, honestly: this classifies failures to STAT or OPEN the directory. A directory that
    opens but refuses to be walked is a different (pre-existing) path — ``compare_tree`` gets
    it, ``walk_tracked_files`` swallows the OSError, and the result is a drift whose
    ``missing_in_cache_count`` was never really measured. That is not fixed here.
    """
    try:
        with os.scandir(candidate) as entries:
            next(entries, None)
    except (FileNotFoundError, NotADirectoryError):
        return "absent"
    except OSError:
        return "unreadable"
    return "absent"  # listable now but not a dir a moment ago: it raced; treat as gone


def load_manifest(installed_plugins: Path | None) -> tuple[dict | None, str]:
    """Read and parse the manifest ONCE — ``(data, basis)``, ``None`` when unusable.

    Hoisted out of the per-plugin lookup so one verdict rests on one reading. Re-opening it
    inside the loop meant a rewrite by `claude plugin install` or the cache manager landing
    mid-run could produce a single report in which some plugins resolved from the old file,
    some from the new, and some from a half-written one.
    """
    if installed_plugins is None:
        return None, "latest (no installed_plugins.json given)"
    try:
        return json.loads(Path(installed_plugins).read_text(encoding="utf-8")), ""
    except FileNotFoundError:
        return None, "latest (no installed_plugins.json)"
    except (OSError, ValueError) as exc:
        # ValueError covers JSONDecodeError. Malformed is not a finding about the CACHE, so it
        # degrades rather than failing --strict on an unrelated file.
        return None, f"latest (installed_plugins.json unreadable: {type(exc).__name__})"


def installed_version_name(
    plugin_name: str, installed_plugins: Path | None, *, expected_parent: Path | None = None,
    manifest: tuple[dict | None, str] | None = None,
) -> tuple[str | None, str]:
    """Return ``(version_dir_name, basis)`` for one plugin.

    ``manifest`` is a pre-read :func:`load_manifest` result; omit it and the file is read
    here, which is convenient for a single lookup and wrong for a loop (see that function).

    ``version_dir_name`` is the FINAL COMPONENT of the manifest's ``installPath`` — not the
    absolute path — so the answer composes with whatever ``--cache-root`` the caller was
    given. In production the two are the same directory, because ``installPath`` is by
    construction ``<cache_root>/<plugin>/<version>``; under a test or an explicit
    ``--cache-root`` the basename keeps the caller's root authoritative instead of silently
    reading the real machine's cache.

    ``None`` means "no authority here, use your heuristic", and ``basis`` then begins with
    ``latest`` and names the reason. The caller records it, so a green verdict can always be
    audited for WHICH rule chose the tree it rests on.

    UNVERIFIED PREMISE, stated because nothing here can check it: that ``entries[0]`` is the
    entry Claude Code's runtime actually binds. This module proves only that the checker and
    ``update-marketplace.sh`` read the SAME entry — both take the first. The value is a list
    in a manifest carrying its own ``version: 2``, so if a second entry ever appears and
    runtime prefers a different one, producer and checker would be consistently wrong
    together and no gate in this repo would notice.
    """
    data, basis = load_manifest(installed_plugins) if manifest is None else manifest
    if data is None:
        return None, basis

    # Mirrors `_install_path`'s chain exactly, INCLUDING its blanket tolerance. A narrower
    # `except` was a real gap, not a style point: the manifest maps each key to a LIST, but
    # its shape is versioned (`version: 2`) and an object there makes `entries[0]` raise
    # KeyError — a LookupError, not an IndexError — crashing a check whose whole contract is
    # that it never crashes a session over another program's file.
    try:
        entries = data.get(PLUGINS_KEY, {}).get(plugin_key(plugin_name), [])
        raw = entries[0].get(INSTALL_PATH_KEY, "") if entries else ""
    except Exception:  # noqa: BLE001 — deliberate parity with the shell's `except Exception`
        return None, "latest (installed_plugins.json shape unexpected)"

    if not raw:
        # No plugin NAME in the reason: the per-plugin record already carries `plugin`, and
        # the human line joins the deduped SET of reasons — so naming each one would put up
        # to 13 near-identical strings on a single `ok` line on an offline/headless machine,
        # where no plugin is installed. That is the noise print_orphan_advisory argues against.
        return None, "latest (not installed per installed_plugins.json)"
    # The manifest stores a native Windows path; the shell normalises the same way.
    normalised = PurePosixPath(str(raw).replace("\\", "/"))
    if not normalised.name:
        return None, "latest (installPath names no directory)"
    # Only the FINAL component is used, so the caller's cache root stays authoritative. Where
    # that discards a real difference — a relocated cache, a second config dir, a hand-edited
    # manifest — the verdict says so rather than quietly measuring a directory the sync never
    # writes to. Tested on HAVING a parent, not on `is_absolute()`: a Windows installPath
    # (`C:\...`, the real shape) is not absolute once read as a PurePosixPath, so that check
    # silently never fired. `normcase` because the two sides come from different programs and
    # only Windows drive-letter/separator case can differ — a false "outside" on every green
    # would be worse than the gap it closes.
    if expected_parent is not None and str(normalised.parent) not in (".", ""):
        want = os.path.normcase(str(expected_parent).replace("\\", "/")).rstrip("/\\")
        got = os.path.normcase(str(normalised.parent)).rstrip("/\\")
        if want != got:
            return normalised.name, "installed_plugins (installPath outside this cache root)"
    return normalised.name, "installed_plugins"


def resolve_version_dir(
    plugin_cache: Path, plugin_name: str, installed_plugins: Path | None,
    *, manifest: tuple[dict | None, str] | None = None,
) -> tuple[Path | None, str, str]:
    """Pick the version dir the SYNC writes to, or fall back and say so.

    Returns ``(dir, reason, version_basis)`` with ``reason`` in
    :func:`latest_cache_version_dir`'s vocabulary (``""`` | ``absent`` | ``unreadable``) so
    the caller's existing branches are unchanged.

    The manifest is authoritative and is NOT cross-checked against what is on disk: when it
    names a directory that does not exist, that is ``absent``, never a quiet fallback to some
    other version. The sync skips a plugin in exactly that state (``[ ! -d "$cache_target" ]``),
    so comparing against a tree it never writes would restore the disagreement in the
    opposite direction — reporting `ok` about a directory runtime does not load.
    """
    name, basis = installed_version_name(
        plugin_name, installed_plugins, expected_parent=plugin_cache, manifest=manifest)
    if name is not None:
        candidate = plugin_cache / name
        # `os.path.isdir`, NOT `Path.is_dir()`: the latter only swallows ENOENT/ENOTDIR/
        # EBADF/ELOOP and RE-RAISES PermissionError, so a denied stat (parent traverse
        # removed, or a dir mid-reap on Windows) would escape check_sync, whose contract is
        # that no exception leaks out. `os.path.isdir` answers False for every OSError, which
        # routes all of them into the classifier below where they are told apart.
        if os.path.isdir(candidate):
            return candidate, "", basis
        # Never let the fallback promote a directory the manifest did not name.
        return None, _probe_missing_dir(candidate), basis
    version_dir, reason = latest_cache_version_dir(plugin_cache)
    return version_dir, reason, basis
