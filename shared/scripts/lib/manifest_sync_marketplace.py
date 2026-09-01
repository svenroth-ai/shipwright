"""``marketplace_json`` format support for ``manifest_sync_core`` — split
into its own module to keep ``manifest_sync_core.py`` under the project's
300-line guideline.

A ``marketplace_json`` manifest (e.g. ``.claude-plugin/marketplace.json``)
carries its version twice: once at the top level, and again inside a
``plugins`` array of catalog entries. Bumping only the top level — what
``package_json``'s single-field format already handles — leaves every
catalog entry stranded; this module is what closes that.
"""

from __future__ import annotations

import json
import re

from .manifest_sync_errors import ManifestSyncError

__all__ = ["find_stale_plugin_entries", "render_marketplace_write", "validate_marketplace_structure"]


def validate_marketplace_structure(parsed: dict) -> None:
    """Raise :class:`ManifestSyncError` (``invalid_manifest_structure``)
    unless ``parsed["plugins"]`` is a JSON array of JSON objects. Called
    from ``manifest_sync_core.read_manifest_version`` after the
    format-agnostic top-level ``"version"`` checks already passed.
    """
    plugins = parsed.get("plugins")
    if not isinstance(plugins, list):
        raise ManifestSyncError(
            "invalid_manifest_structure", '"plugins" must be a JSON array'
        )
    for i, item in enumerate(plugins):
        if not isinstance(item, dict):
            raise ManifestSyncError(
                "invalid_manifest_structure", f"plugins[{i}] must be a JSON object"
            )


def find_stale_plugin_entries(parsed: dict, target_version: str) -> list[str]:
    """Names (or ``plugins[i]`` positions, when a name is missing/not a
    string) of every ``plugins[]`` entry whose own ``version`` does not
    equal ``target_version``. An entry with no ``version`` key is not
    stale — there is nothing on it to compare. Assumes ``parsed`` already
    passed :func:`validate_marketplace_structure` (a JSON object with a
    ``plugins`` array of JSON objects).
    """
    stale = []
    for i, item in enumerate(parsed.get("plugins") or []):
        if not isinstance(item, dict) or "version" not in item:
            continue
        if item.get("version") != target_version:
            name = item.get("name")
            stale.append(name if isinstance(name, str) and name else f"plugins[{i}]")
    return stale


def render_marketplace_write(
    original_text: str, current_version: str, new_version: str
) -> tuple[str, bool]:
    """``marketplace_json`` bumps the root ``version`` AND every
    ``plugins[].version`` entry together — that is the whole point of the
    format. Prefers the same byte-preserving substitution as
    ``package_json``, extended to every occurrence (root plus each plugin
    entry), but only when ALL of them currently equal ``current_version`` —
    the steady-state case, everything already in lockstep from the prior
    release. Any entry already at a different value (a partial earlier
    sync, or a hand-edit) falls back to a full JSON re-render that
    force-syncs root + every plugin entry to ``new_version``
    unconditionally — the self-heal path this format exists for, at the
    cost of a one-time whole-file reformat.

    Assumes ``original_text`` already passed
    :func:`validate_marketplace_structure` via ``read_manifest_version`` —
    the root is a JSON object with a ``plugins`` array of JSON objects.
    """
    parsed = json.loads(original_text)
    plugin_list = parsed.get("plugins") or []

    all_in_lockstep = (
        parsed.get("version") == current_version
        and not find_stale_plugin_entries(parsed, current_version)
    )

    if all_in_lockstep:
        pattern = re.compile(r'("version"\s*:\s*")' + re.escape(current_version) + r'(")')
        # Only entries carrying a "version" key contribute an occurrence —
        # find_stale_plugin_entries above already treats a version-less
        # entry as non-stale, so it must not be counted here either.
        expected_count = 1 + sum(
            1 for item in plugin_list if isinstance(item, dict) and "version" in item
        )
        matches = list(pattern.finditer(original_text))
        if len(matches) == expected_count:
            new_text = pattern.sub(
                lambda m: m.group(1) + new_version + m.group(2), original_text
            )
            return new_text, False

    parsed["version"] = new_version
    for item in plugin_list:
        if isinstance(item, dict) and "version" in item:
            item["version"] = new_version
    rendered = json.dumps(parsed, indent=2, ensure_ascii=False)
    if not rendered.endswith("\n"):
        rendered += "\n"
    return rendered, True
