"""Drift guard for this monorepo's own ``shipwright_changelog_config.json``.

The config's whole point is dogfooding: every ``plugins/*/.claude-plugin/
plugin.json`` plus ``.claude-plugin/marketplace.json`` declared, so
``sync_release_manifests`` stops being a no-op for this repo's own releases
(the bug this config was added to fix — v0.33.0 shipped with every plugin
stranded at the prior version). A plugin added or removed without updating
the config would silently regress back to that bug; this test catches it.

Mirrors ``test_phase_plugin_hooks_consistency.py``'s pattern: read the real
repo's own manifests directly, no fixture — the SSoT is the files on disk.
"""

from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _declared_manifests() -> list[dict]:
    config = json.loads(
        (REPO_ROOT / "shipwright_changelog_config.json").read_text(encoding="utf-8")
    )
    return config["published_manifests"]


def test_every_plugin_json_on_disk_is_declared():
    declared_paths = {
        Path(entry["path"]).as_posix()
        for entry in _declared_manifests()
        if entry["format"] == "package_json"
    }
    on_disk = {
        p.relative_to(REPO_ROOT).as_posix()
        for p in REPO_ROOT.glob("plugins/*/.claude-plugin/plugin.json")
    }
    assert declared_paths == on_disk


def test_marketplace_json_is_declared_with_the_marketplace_format():
    declared = {entry["path"]: entry["format"] for entry in _declared_manifests()}
    assert declared.get(".claude-plugin/marketplace.json") == "marketplace_json"
