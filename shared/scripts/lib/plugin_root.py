"""Canonical plugin-root resolver (M2 — one plugin-root contract).

``SHIPWRIGHT_PLUGIN_ROOT`` is the framework-owned variable every hook and
skill-launched script should read. It is not always set directly — Claude and
Codex each set their own provider variable, and provider packaging (or a thin
launcher) is expected to derive ``SHIPWRIGHT_PLUGIN_ROOT`` from it. This
module is that one derivation, so application scripts never guess cache
topology themselves (``Spec/codex-runtime-integration-spec.md`` §7, M2).

Precedence, checked in order:

1. ``SHIPWRIGHT_PLUGIN_ROOT`` — already resolved by something upstream (a
   SessionStart hook, a launcher). Wins outright.
2. ``CLAUDE_PLUGIN_ROOT`` — Claude's variable, and Codex's compatibility
   alias for it (parent spec §2: Codex sets both its native and this
   compatibility variable, to the SAME value, for a plugin-bundled hook).
3. ``PLUGIN_ROOT`` — Codex's own native variable. Checked LAST, not first:
   it is a generic enough name that an unrelated ambient tool (a version
   manager, another CLI's own "plugin root" convention) could set it in a
   plain Claude session, where it carries no meaning at all — outranking
   ``CLAUDE_PLUGIN_ROOT`` would let that stray value silently win over the
   one Claude itself sets, correctly, for every hook invocation. Under
   Codex this ordering costs nothing: both variables name the same
   directory, so whichever is checked first resolves identically (doubt-
   review, 2026-09-20 — the original SHIPWRIGHT > PLUGIN_ROOT > CLAUDE
   order bought a real hijack risk under Claude for zero Codex-side
   benefit).

Raises :class:`PluginRootUnresolvedError` when none are set, instead of
falling back to ``cwd`` or another guess — a silent wrong root is worse than
a loud failure for a script about to read its own plugin's files.
"""

from __future__ import annotations

import os
from pathlib import Path

_ENV_PRECEDENCE: tuple[str, ...] = (
    "SHIPWRIGHT_PLUGIN_ROOT",
    "CLAUDE_PLUGIN_ROOT",
    "PLUGIN_ROOT",
)


class PluginRootUnresolvedError(RuntimeError):
    """Raised when none of the known plugin-root env vars are set."""


def resolve_plugin_root_str() -> str:
    """Return the active plugin's root directory as the exact, unmodified
    string a caller set it to — no ``Path`` round-trip, so a consumer that
    only ever re-emits the value (e.g. into another process's environment)
    does not have its separator style silently rewritten. Same precedence
    and error as :func:`resolve_plugin_root`."""
    for var in _ENV_PRECEDENCE:
        value = os.environ.get(var)
        if value:
            return value
    raise PluginRootUnresolvedError(
        "None of "
        + ", ".join(_ENV_PRECEDENCE)
        + " is set — cannot resolve the active plugin's root directory."
    )


def resolve_plugin_root() -> Path:
    """Return the active plugin's root directory as a :class:`Path`, from
    whichever of ``SHIPWRIGHT_PLUGIN_ROOT`` / ``CLAUDE_PLUGIN_ROOT`` /
    ``PLUGIN_ROOT`` is set first, in that order. Raises
    :class:`PluginRootUnresolvedError` if none are set."""
    return Path(resolve_plugin_root_str())
