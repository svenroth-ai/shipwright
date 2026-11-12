"""G2 scope parsing: a conventional-commit scope may name several parts.

``feat(daemon,lib): ...`` declares two scopes. G2 judges each part on its
own, so a known part never hides an unknown one and the evidence names only
the part that is unknown.
"""

from __future__ import annotations

from collections.abc import Collection


def scope_parts(scope: str) -> list[str]:
    """Split on commas, trim, drop empty parts (``"a, ,b,"`` -> ``["a", "b"]``)."""
    return [p for p in (part.strip() for part in scope.split(",")) if p]


def unknown_scope_parts(scope: str, known: Collection[str]) -> list[str]:
    """Return the parts of ``scope`` not in ``known``, in order of appearance.

    A scope with no usable part (``","``) is itself unknown: it names nothing.
    """
    parts = scope_parts(scope)
    if not parts:
        return [scope]
    return [p for p in parts if p not in known]
