"""The ``Part:`` line of the operator's question: which part of the product the change is in, in the project's OWN words.

Never a name this code made up and never a fixed word such as "plugin" (a web app has screens, an API has services):

1. the grouping the spec already gives the requirement (the table's ``Area`` column, else the name of the split the spec lives in -
   :func:`lib.ac_catalog.load_catalog` ``groups``; the generic ``adopted`` that ``adopt`` writes names nothing and is skipped);
2. else the top-level directory of each changed path (a container directory such as ``plugins/`` or ``packages/`` holds the parts, so
   its child is named: ``plugins/shipwright-build``); documentation, test and tooling directories are not parts of the product;
3. else no line at all.

Stdlib only.
"""

from __future__ import annotations

__all__ = ["part_line", "part_names"]

_CONTAINERS = frozenset({"plugins", "packages", "apps", "services", "libs", "modules", "crates", "workspaces"})
_NOT_PARTS = frozenset({"docs", "doc", "tests", "test", "integration-tests", ".github", ".shipwright", ".claude", "scripts"})


def _from_paths(paths: object) -> list[str]:
    found: set[str] = set()
    for p in paths if isinstance(paths, (list, tuple, set)) else []:
        parts = [x for x in str(p).replace("\\", "/").strip("/").split("/") if x]
        if len(parts) < 2 or parts[0] in _NOT_PARTS or parts[0].lower().startswith("changelog"):  # a file at the root, or release-note drops, belong to no part
            continue
        found.add(f"{parts[0]}/{parts[1]}" if parts[0] in _CONTAINERS and len(parts) > 2 else parts[0])
    return sorted(found)


def part_names(frs: list[str], cat: dict, paths: object = None) -> list[str]:
    """The part names for the requirement(s) ``frs`` and the changed ``paths``: the spec's grouping first, else the paths' directories, else none."""
    groups = cat.get("groups") or {}
    named = sorted({groups[fr] for fr in frs if groups.get(fr)})
    return named or _from_paths(paths)


def part_line(frs: list[str], cat: dict, paths: object = None) -> str:
    names = part_names(frs, cat, paths)
    return "Part: " + ", ".join(names) if names else ""
