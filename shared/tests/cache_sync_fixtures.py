"""Fixture builders shared by the three cache-sync test modules.

Not a ``conftest.py`` addition: ``shared/tests/conftest.py`` sits at its
ADR-101 bloat exception (320 lines), so folding 26 lines in there would ratchet
a baseline entry. A module here is collected by nobody (the name does not match
``test_*``) and importable by all three, which is what the duplication needed.
"""

from __future__ import annotations

from pathlib import Path


def write_tree(root: Path, files: dict[str, str]) -> None:
    """Write ``{relative_path: content}`` under ``root``, creating parents."""
    for rel, content in files.items():
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")


def seed_repo_and_cache(
    tmp_path: Path,
    *,
    shared: dict[str, str] | None = None,
    cache_shared: dict[str, str] | None = None,
    mirror: dict[str, str] | None = None,
) -> tuple[Path, Path]:
    """Build a repo+cache pair with one in-sync plugin, plus optional trees.

    The plugin exists so ``check_sync`` gets past its ``no_repo_plugins`` early
    return; it is in sync on both sides, so any drift a test observes comes
    from the tree that test is actually about.

    ``mirror`` seeds ``cache/plugins/<name>/``, the cross-plugin mirror this
    check deliberately does not gate — pass it to prove the mirror stays out of
    a verdict, never to assert something about the mirror itself.
    """
    repo, cache = tmp_path / "repo", tmp_path / "cache"
    plugin_files = {"skills/x/SKILL.md": "# x\n"}
    write_tree(repo / "plugins" / "shipwright-foo", plugin_files)
    write_tree(cache / "shipwright-foo" / "0.1.0", plugin_files)
    if shared is not None:
        write_tree(repo / "shared", shared)
    if cache_shared is not None:
        write_tree(cache / "shared", cache_shared)
    if mirror is not None:
        write_tree(cache / "plugins" / "shipwright-foo", mirror)
    return repo, cache
