"""Hook-inventory merge logic for build_codex_plugin.py (M1).

Split out of the builder (and out of ``codex_hook_merge.py`` in turn, which
now holds only the rewrite/order-merge primitives this module calls) to
keep every file under the project's 300-LOC source guideline. See
build_codex_plugin.py's own docstring for the overall bundle shape; this
module owns only "normalize N Claude hooks.json files into one deduplicated
Codex hook inventory."

Real-repo shapes this must handle (found reading the monorepo's own 14
``hooks.json`` files while building this):

1. **Exact duplicates.** ~11-12 of 14 plugins register the identical
   ``shared/``-referencing command on the same event (by convention — see
   ``shared/prompts/writing-plugin.md``, "a hook registered in one plugin
   must usually be registered in all 12"). Dedupe to one entry.
2. **Matcher-distinguished variants.** The *same* own-plugin script
   (``write-review-payload-on-stop.py``) is registered 3x under
   ``SubagentStop`` with 3 different ``matcher`` values (one per reviewer
   role) and 3 different trailing flags. These are genuinely different
   hooks — the matcher is part of the identity, not noise.
3. **Dispatcher-style union, order-preserving.** ``run_if_cache_ready.py``
   (byte-identical own-plugin script in every plugin that has it) is
   invoked with a *different list* of trailing shared-script path arguments
   per plugin. Collapsing 14 firings into one merged Codex hook must
   preserve that union — dropping to one plugin's shorter list would
   silently drop real checks. Order matters too: ``_merge_preserving_order``
   inserts a newly-seen token at the position implied by the origin that
   introduced it rather than appending to the tail — a plugin missing one
   middle script must not reorder a later, fuller plugin's list.
4. **Real collisions.** Same event + matcher + invoked script, but a
   genuinely different invocation shape, OR two plugins declaring
   conflicting relative order for the same pair of trailing arguments.
   Refuse rather than guess (M1: "collision refusal when two definitions
   share a key but disagree").

Order is preserved at TWO levels, both via ``_merge_preserving_order``:
within one dispatcher's trailing arguments (``_HookGroupEntry.trailing_order``,
shape 3 above), and across DISTINCT hook entries within one
``(event, matcher)`` bucket (``bucket_order`` below). The second level
exists because plugins are walked alphabetically and a bare dict would
otherwise order entries by "whichever alphabetically-first plugin happened
to declare this script" — e.g. ``shipwright-iterate`` requires
``iterate_stop_finalize.py`` to run BEFORE, and ``aggregate_triage_on_stop.py``
AFTER, ``shipwright-adopt``'s Stop hooks: a real cross-plugin ordering
requirement, not just a dedup key (caught by doubt-review, 2026-09-20).

Known unchecked assumptions:

* ``_invoked_index`` treats the FIRST ``${CLAUDE_PLUGIN_ROOT}``-referencing
  token as the invoked script (as opposed to the interpreter or a flag
  before it). True for every command in the 14 real ``hooks.json`` files
  today but not structurally enforced — a future hook shaped like
  ``uv run --project "${CLAUDE_PLUGIN_ROOT}" ...`` would misidentify the
  flag value as the invoked script.
* This module keys a dispatcher's own-plugin script (e.g.
  ``run_if_cache_ready.py``) by its ``${CLAUDE_PLUGIN_ROOT}``-relative path
  (``rel_key``) and assumes every origin's copy at that path is byte-identical
  — true today by convention (``shared/prompts/writing-plugin.md``), but not
  verified: only the first origin's rewritten path is kept as
  ``invoked_token``, so a divergent local copy would be silently discarded in
  favor of an arbitrary other origin's, with no drift signal from
  ``verify_codex_plugin_bundle.py`` (which diffs the bundle against a fresh
  rebuild of the *same* sources, not sources against each other).
* ``_merge_preserving_order``'s head-insertion rule can produce a spurious
  refusal when processing order interacts with a genuinely-consistent but
  partially-overlapping declaration (e.g. o1=[A], o2=[B], o3=[A,B]) — never a
  silent wrong order, only an over-eager ``BundleCollisionError``. Runs at
  both merge levels now (trailing args, bucket-entry order); no instance
  triggers it on the real 14-plugin tree today at either level.
"""

from __future__ import annotations

import json
import shlex
from pathlib import Path

from codex_hook_merge import (
    BundleCollisionError,
    _HookGroupEntry,
    _invoked_index,
    _merge_preserving_order,
    _rel_after_placeholder,
    _rewrite_command,
)

__all__ = ["BundleCollisionError", "build_hook_inventory"]


def _load_hooks(plugin_dir: Path) -> dict:
    """Merge a plugin's Claude-visible ``hooks/hooks.json`` with its
    Codex-only ``hooks-codex/hooks.json`` (R2, runtime-scoped registration)
    into one raw hook map. The Codex-only file is never read by Claude Code
    itself (a fixed convention outside Shipwright's control: Claude only
    ever loads ``hooks/hooks.json``), so an entry declared there costs
    Claude sessions nothing -- it exists purely as build input for this
    Codex bundle. Codex-only groups are appended after the shared ones for
    a given event, so the existing bucket_order/dedup logic below sees them
    exactly like any other origin's late-arriving entry."""
    merged: dict = {}
    hooks_file = plugin_dir / "hooks" / "hooks.json"
    if hooks_file.is_file():
        data = json.loads(hooks_file.read_text(encoding="utf-8"))
        merged = dict(data.get("hooks", {}))
    codex_only_file = plugin_dir / "hooks-codex" / "hooks.json"
    if codex_only_file.is_file():
        codex_only = json.loads(codex_only_file.read_text(encoding="utf-8")).get("hooks", {})
        for event, groups in codex_only.items():
            merged.setdefault(event, [])
            merged[event] = merged[event] + list(groups)
    return merged


def build_hook_inventory(plugin_dirs: list[Path]) -> dict:
    """Merge every plugin's ``hooks.json`` into one deduplicated, ordered
    Codex hook inventory shaped like ``{"hooks": {<event>: [<group>, ...]}}``.
    Raises :class:`BundleCollisionError` on a real, unresolvable conflict."""
    # (event, matcher) -> ordered dict of rel_key -> _HookGroupEntry
    buckets: dict[tuple[str, str | None], dict[str, _HookGroupEntry]] = {}
    bucket_order: dict[tuple[str, str | None], list[str]] = {}
    literal_passthrough: dict[tuple[str, str | None], list[dict]] = {}

    for plugin_dir in sorted(plugin_dirs):
        origin = plugin_dir.name
        raw_hooks = _load_hooks(plugin_dir)
        # Per-PLUGIN, not per group object: two hooks.json groups sharing one
        # bucket must be validated as ONE sequence, else a later group could
        # be silently head-inserted before an earlier one (doubt-review r3).
        plugin_rel_keys: dict[tuple[str, str | None], list[str]] = {}
        for event, groups in raw_hooks.items():
            for group in groups:
                matcher = group.get("matcher")
                gkey = (event, matcher)
                buckets.setdefault(gkey, {})
                # A passthrough-only bucket (e.g. mcp_tool) never reaches
                # plugin_rel_keys below, so seed bucket_order here too, else
                # the render loop's lookup raises KeyError (doubt-review r4).
                bucket_order.setdefault(gkey, [])
                for hook in group.get("hooks", []):
                    if hook.get("type") != "command":
                        literal_passthrough.setdefault(gkey, []).append(dict(hook))
                        continue
                    raw_command = hook["command"]
                    raw_tokens = shlex.split(raw_command, posix=False)
                    idx = _invoked_index(raw_tokens)
                    rewritten = _rewrite_command(raw_command, origin)
                    if idx is None:
                        literal_passthrough.setdefault(gkey, []).append({**hook, "command": rewritten})
                        continue
                    # rel_key comes from the RAW (pre-rewrite) token: it is the
                    # invoked script's path relative to each plugin's own
                    # root, which is what makes a byte-identical own-plugin
                    # script (e.g. run_if_cache_ready.py, copied into every
                    # plugin that uses it) key the SAME across origins even
                    # though the rewritten/bundled path differs per origin.
                    rel_key = _rel_after_placeholder(raw_tokens[idx])
                    prefix_shape = tuple(raw_tokens[:idx])
                    rewritten_tokens = shlex.split(rewritten, posix=False)
                    invoked_token = rewritten_tokens[idx]
                    trailing = rewritten_tokens[idx + 1 :]
                    entry = buckets[gkey].setdefault(
                        rel_key, _HookGroupEntry(prefix_shape, hook["type"])
                    )
                    entry.add(prefix_shape, invoked_token, trailing, origin, event=event)
                    plugin_rel_keys.setdefault(gkey, []).append(rel_key)
        for gkey, rel_keys in plugin_rel_keys.items():
            event = gkey[0]
            bucket_order[gkey] = _merge_preserving_order(
                bucket_order.get(gkey, []),
                rel_keys,
                origin=origin,
                event=event,
                invoked_token="<hook entry order>",
                kind="hook-entry",
            )

    merged: dict[str, list[dict]] = {}
    for (event, matcher), entries in buckets.items():
        group: dict = {"hooks": []}
        if matcher is not None:
            group["matcher"] = matcher
        for rel_key in bucket_order[(event, matcher)]:
            entry = entries[rel_key]
            group["hooks"].append({"type": entry.hook_type, "command": entry.to_command()})
        group["hooks"].extend(literal_passthrough.get((event, matcher), []))
        merged.setdefault(event, []).append(group)

    for gkey, extra in literal_passthrough.items():
        if gkey not in buckets:
            event, matcher = gkey
            group = {"hooks": extra}
            if matcher is not None:
                group["matcher"] = matcher
            merged.setdefault(event, []).append(group)

    return {"hooks": merged}
