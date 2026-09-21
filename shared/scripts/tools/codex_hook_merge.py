"""Hook-command rewrite and order-preserving merge primitives, used by
``codex_hook_inventory.build_hook_inventory`` (which owns the actual
per-bucket dedup/ordering policy — see that module's docstring for the
real-repo shapes and known unchecked assumptions this exists to serve).

Split out of the builder (and later out of ``codex_hook_inventory.py`` in
turn) to keep every file under the project's 300-LOC source guideline.
"""

from __future__ import annotations

import shlex

_PLACEHOLDER = "${CLAUDE_PLUGIN_ROOT}"
_SHARED_INFIX = "/../../shared"


class BundleCollisionError(RuntimeError):
    """Raised when two plugins register conflicting hook commands for what
    the rewritten path shows is meant to be the same target script."""


def _rewrite_command(command: str, origin_plugin: str) -> str:
    """Rewrite every ``${CLAUDE_PLUGIN_ROOT}``-relative path in *command* to
    a bundle-relative path, keeping the SAME variable name,
    ``${CLAUDE_PLUGIN_ROOT}``. The merged bundle is installed as ONE Codex
    plugin, so Codex sets this compatibility variable (alongside its native
    ``PLUGIN_ROOT``) to the bundle's own root for every hook it invokes: "for
    plugin-bundled hooks, [Codex] sets both its native PLUGIN_ROOT/PLUGIN_DATA
    and compatibility variables CLAUDE_PLUGIN_ROOT/CLAUDE_PLUGIN_DATA"
    (``Spec/codex-runtime-integration-spec.md`` — quoted inline since that
    file is gitignored and a bare line-number citation would rot silently
    for any reader without the maintainer's own checkout). Targeting the
    application-level ``SHIPWRIGHT_PLUGIN_ROOT`` convention instead would be
    a real regression: nothing sets that name at shell-expansion time (it is
    resolved from inside already-running Python), so every bundled command
    would expand to a rootless path and fail outright (doubt-review,
    2026-09-20). Sequential, not short-circuited: a single command can
    contain BOTH an own-plugin token and shared-script arguments, and both
    must be rewritten in one pass — sharing one variable name means the
    shared-infix replacement goes through a sentinel first, else the
    generic replacement would re-match its own output and double-prefix
    shared paths with ``/origin/<plugin>`` too."""
    sentinel = "\x00SHIPWRIGHT_SHARED_ROOT\x00"
    rewritten = command.replace(f"{_PLACEHOLDER}{_SHARED_INFIX}", sentinel)
    rewritten = rewritten.replace(
        _PLACEHOLDER, f"${{CLAUDE_PLUGIN_ROOT}}/origin/{origin_plugin}"
    )
    rewritten = rewritten.replace(sentinel, "${CLAUDE_PLUGIN_ROOT}/shared")
    return rewritten


def _invoked_index(tokens: list[str]) -> int | None:
    """Index of the first token that references ``${CLAUDE_PLUGIN_ROOT}`` —
    the script actually being invoked (as opposed to the interpreter or a
    flag before it)."""
    for i, tok in enumerate(tokens):
        if _PLACEHOLDER in tok:
            return i
    return None


def _rel_after_placeholder(token: str) -> str:
    return token.split(_PLACEHOLDER, 1)[1]


def _merge_preserving_order(
    existing: list[str],
    new: list[str],
    *,
    origin: str,
    event: str,
    invoked_token: str,
    kind: str = "trailing-argument",
) -> list[str]:
    """Merge *new* into *existing*, preserving both sequences' relative
    order — used at TWO levels (see ``codex_hook_inventory.build_hook_inventory``'s
    docstring): a dispatcher's trailing sub-scripts (``kind="trailing-argument"``,
    run sequentially via ``subprocess.run``, so order is observable behavior),
    and distinct hook entries within one bucket (``kind="hook-entry"``). A
    newly-seen token is inserted right after the last token (from *new*)
    already present in *existing*. A token already present out of order
    relative to *new*'s declared order is a genuine conflict — refused via
    :class:`BundleCollisionError` rather than silently picked."""
    result = list(existing)
    last_pos = -1
    for tok in new:
        if tok in result:
            idx = result.index(tok)
            if idx < last_pos:
                raise BundleCollisionError(
                    f"Event {event!r}: conflicting {kind} order for "
                    f"{invoked_token!r}: {tok!r} is declared after a later "
                    f"one in {result!r} but before it in {new!r} (from {origin})"
                )
            last_pos = idx
        else:
            insert_pos = last_pos + 1
            result.insert(insert_pos, tok)
            last_pos = insert_pos
    return result


class _HookGroupEntry:
    """One (event, matcher, invoked-script) bucket being merged across
    plugins."""

    def __init__(self, prefix_shape: tuple[str, ...], hook_type: str) -> None:
        self.prefix_shape = prefix_shape
        self.hook_type = hook_type
        self.trailing_order: list[str] = []
        self.invoked_token: str | None = None

    def add(
        self,
        prefix_shape: tuple[str, ...],
        invoked_token: str,
        trailing: list[str],
        origin: str,
        *,
        event: str,
    ) -> None:
        if prefix_shape != self.prefix_shape:
            raise BundleCollisionError(
                f"Event {event!r}: conflicting invocation shape for {invoked_token!r}: "
                f"{' '.join(self.prefix_shape)!r} vs {' '.join(prefix_shape)!r} (from {origin})"
            )
        if self.invoked_token is None:
            self.invoked_token = invoked_token
        self.trailing_order = _merge_preserving_order(
            self.trailing_order, trailing, origin=origin, event=event, invoked_token=invoked_token
        )

    def to_command(self) -> str:
        tokens = list(self.prefix_shape) + [self.invoked_token, *self.trailing_order]
        return " ".join(shlex.quote(t) if " " in t else t for t in tokens)
