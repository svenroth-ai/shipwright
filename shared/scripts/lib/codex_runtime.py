"""Codex-bundle detection (R1b — AC1).

``is_codex_runtime()`` answers one narrow question: is the resolved plugin
root a real, on-disk Codex bundle produced by ``build_codex_plugin.py``?
Never a bare env-var presence check — an ordinary Claude plugin-cache root
also sets ``CLAUDE_PLUGIN_ROOT``, and a stray unrelated value could point
anywhere. Both of the builder's own root markers must be present:
``BUILD_MANIFEST.json`` (the bundle's own sha256 manifest) and
``.codex-plugin/plugin.json`` (the umbrella manifest with the inline
``hooks`` key ``codex_hooks_sync.py`` reads). Either alone is not enough —
a Claude plugin-cache directory has neither, but a future partial/corrupted
Codex output directory could plausibly have one without the other.

``BUILD_MANIFEST.json`` presence is checked for genuine *shape*, not just
parsed as JSON: an empty/placeholder marker file would otherwise pass, and
whatever ``sync_codex_hooks()`` finds in ``plugin.json["hooks"]["hooks"]``
gets installed as globally-executing hooks for every Codex session on the
machine (external code review, both legs, medium). ``plugin.json`` itself
stays a bare presence check here on purpose: it is `_read_bundle_hooks()`'s
job to parse it and raise :class:`CodexHooksSyncError` loudly on genuine
corruption of a real bundle — shape-checking it here too would instead
silently no-op a genuinely malformed bundle, the opposite of the "surface
loudly" design this module already commits to."""

from __future__ import annotations

import json
from pathlib import Path

try:  # loaded as ``lib.codex_runtime``
    from .plugin_root import PluginRootUnresolvedError, resolve_plugin_root
except ImportError:  # loaded as top-level ``codex_runtime`` (lib/ is on sys.path)
    from plugin_root import PluginRootUnresolvedError, resolve_plugin_root


def _has_genuine_build_manifest(path: Path) -> bool:
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return False
    return isinstance(doc, dict) and isinstance(doc.get("files"), dict) and bool(doc["files"])


def is_codex_runtime(plugin_root: Path | None = None) -> bool:
    """True only when ``plugin_root`` (or the env-resolved plugin root, if
    not given) is a real Codex bundle directory: ``BUILD_MANIFEST.json``
    shaped like `build_codex_plugin.py`'s own real output, and
    ``.codex-plugin/plugin.json`` present."""
    if plugin_root is None:
        try:
            plugin_root = resolve_plugin_root()
        except PluginRootUnresolvedError:
            return False

    return _has_genuine_build_manifest(plugin_root / "BUILD_MANIFEST.json") and (
        plugin_root / ".codex-plugin" / "plugin.json"
    ).is_file()
