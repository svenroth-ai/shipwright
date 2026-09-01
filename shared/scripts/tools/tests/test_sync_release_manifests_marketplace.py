"""sync()'s ``marketplace_json`` orchestration coverage — split out of
test_sync_release_manifests.py, which keeps the format-agnostic orchestration
and the original package_json coverage, so neither file grows past the
project's 300-line guideline.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))  # shared/

from scripts.tools.sync_release_manifests import sync  # noqa: E402


def _write_config(root: Path, entries: list[dict]) -> None:
    (root / "shipwright_changelog_config.json").write_text(
        json.dumps({"published_manifests": entries}), encoding="utf-8"
    )


def _write_manifest(path: Path, version: str = "0.1.0") -> None:
    body = {"name": "pkg", "version": version}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(body, indent=2) + "\n", encoding="utf-8")


def _write_marketplace_manifest(path: Path, version: str = "0.1.0") -> None:
    body = {
        "name": "acme", "version": version,
        "plugins": [{"name": "a", "version": version}, {"name": "b", "version": version}],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(body, indent=2) + "\n", encoding="utf-8")


def test_sync_marketplace_manifest_bumps_root_and_nested_entries(tmp_path):
    """A project declaring one package_json AND one marketplace_json entry
    together — the shape this monorepo's own config uses (14 plugin.json +
    one marketplace.json) — bumps both formats in one sync() call."""
    _write_config(
        tmp_path,
        [
            {"path": "plugins/a/plugin.json", "format": "package_json"},
            {"path": "marketplace.json", "format": "marketplace_json"},
        ],
    )
    _write_manifest(tmp_path / "plugins" / "a" / "plugin.json", version="0.1.0")
    _write_marketplace_manifest(tmp_path / "marketplace.json", version="0.1.0")

    result = sync(tmp_path, "0.2.0", dry_run=False, stage=False)

    assert result["status"] == "ok"
    by_path = {m["path"]: m for m in result["manifests"]}
    assert by_path["plugins/a/plugin.json"]["changed"] is True
    assert by_path["marketplace.json"] == {
        "path": "marketplace.json", "format": "marketplace_json",
        "changed": True, "reformatted": False,
    }
    marketplace = json.loads((tmp_path / "marketplace.json").read_text())
    assert marketplace["version"] == "0.2.0"
    assert [p["version"] for p in marketplace["plugins"]] == ["0.2.0", "0.2.0"]


def test_sync_still_writes_when_root_matches_but_a_plugin_entry_is_stale(tmp_path):
    """Regression: a manifest whose ROOT already equals the target version
    but carries a stale nested plugins[] entry (a partial earlier sync, or a
    hand-edit) must NOT be skipped — comparing only the root would leave the
    stranded entry in place forever, exactly the bug this format exists to
    prevent."""
    _write_config(tmp_path, [{"path": "marketplace.json", "format": "marketplace_json"}])
    body = {
        "name": "acme", "version": "0.2.0",
        "plugins": [{"name": "a", "version": "0.2.0"}, {"name": "b", "version": "0.1.0"}],
    }
    (tmp_path / "marketplace.json").write_text(json.dumps(body, indent=2) + "\n", encoding="utf-8")

    result = sync(tmp_path, "0.2.0", dry_run=False, stage=False)

    assert result["status"] == "ok"
    entry = result["manifests"][0]
    assert entry["changed"] is True
    marketplace = json.loads((tmp_path / "marketplace.json").read_text())
    assert marketplace["version"] == "0.2.0"
    assert [p["version"] for p in marketplace["plugins"]] == ["0.2.0", "0.2.0"]
