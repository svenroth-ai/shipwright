"""Tests for lib/manifest_sync_core.py's ``marketplace_json`` format —
split out of test_manifest_sync_core.py (which keeps the format-agnostic
primitives plus the original ``package_json`` coverage) so neither file
grows past the project's 300-line guideline.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.manifest_sync_core import (  # noqa: E402
    ManifestSyncError,
    read_manifest_version,
    render_manifest_write,
)

_MARKETPLACE_TEXT = (
    '{\n'
    '  "name": "acme",\n'
    '  "version": "1.2.3",\n'
    '  "plugins": [\n'
    '    {"name": "a", "version": "1.2.3", "tags": ["x", "y"]},\n'
    '    {"name": "b", "version": "1.2.3"}\n'
    '  ]\n'
    '}\n'
)


# --- read_manifest_version ----------------------------------------------------


def test_read_marketplace_version_happy_path():
    assert read_manifest_version(_MARKETPLACE_TEXT, "marketplace_json") == "1.2.3"


def test_read_marketplace_version_missing_plugins_key():
    text = '{"name": "acme", "version": "1.2.3"}'
    with pytest.raises(ManifestSyncError) as exc:
        read_manifest_version(text, "marketplace_json")
    assert exc.value.status == "invalid_manifest_structure"


def test_read_marketplace_version_plugins_not_a_list():
    text = '{"name": "acme", "version": "1.2.3", "plugins": "not-a-list"}'
    with pytest.raises(ManifestSyncError) as exc:
        read_manifest_version(text, "marketplace_json")
    assert exc.value.status == "invalid_manifest_structure"


def test_read_marketplace_version_plugin_entry_not_an_object():
    text = '{"name": "acme", "version": "1.2.3", "plugins": ["not-an-object"]}'
    with pytest.raises(ManifestSyncError) as exc:
        read_manifest_version(text, "marketplace_json")
    assert exc.value.status == "invalid_manifest_structure"


def test_read_marketplace_version_missing_top_level_version():
    text = '{"name": "acme", "plugins": []}'
    with pytest.raises(ManifestSyncError) as exc:
        read_manifest_version(text, "marketplace_json")
    assert exc.value.status == "missing_version_field"


def test_read_marketplace_version_empty_plugins_list_ok():
    """An empty catalog is a legitimate (if degenerate) marketplace file —
    the format requires ``plugins`` to be a list, not a non-empty one."""
    text = '{"name": "acme", "version": "1.2.3", "plugins": []}'
    assert read_manifest_version(text, "marketplace_json") == "1.2.3"


# --- render_manifest_write ----------------------------------------------------


def test_render_marketplace_write_surgical_when_all_in_lockstep():
    """Every occurrence (root + both plugin entries) currently reads
    "1.2.3" — the steady-state case — so the byte-preserving surgical path
    fires: every other byte, including the "tags" array's compact
    formatting, survives untouched."""
    new_text, reformatted = render_manifest_write(
        _MARKETPLACE_TEXT, "marketplace_json", "1.2.3", "1.3.0"
    )
    assert reformatted is False
    assert new_text == _MARKETPLACE_TEXT.replace('"1.2.3"', '"1.3.0"')
    parsed = json.loads(new_text)
    assert parsed["version"] == "1.3.0"
    assert [p["version"] for p in parsed["plugins"]] == ["1.3.0", "1.3.0"]
    assert parsed["plugins"][0]["tags"] == ["x", "y"]


def test_render_marketplace_write_drifted_entry_falls_back_to_full_render():
    """One plugin entry is already ahead of "current_version" (a partial
    prior sync, or a hand-edit) — the surgical multi-occurrence replace
    cannot touch it, so this is the self-heal path: parse, force EVERY
    version (root + every plugin entry) to the new value, and accept the
    one-time whole-file reformat as the cost of correctness."""
    original = (
        '{\n'
        '  "name": "acme",\n'
        '  "version": "1.2.3",\n'
        '  "plugins": [\n'
        '    {"name": "a", "version": "1.2.3"},\n'
        '    {"name": "b", "version": "1.2.4"}\n'
        '  ]\n'
        '}\n'
    )
    new_text, reformatted = render_manifest_write(
        original, "marketplace_json", "1.2.3", "1.3.0"
    )
    assert reformatted is True
    parsed = json.loads(new_text)
    assert parsed["version"] == "1.3.0"
    assert [p["version"] for p in parsed["plugins"]] == ["1.3.0", "1.3.0"]


def test_render_marketplace_write_round_trips_through_read():
    """Boundary Probe: write via render_manifest_write, read the result back
    via read_manifest_version — the producer/consumer pair this format adds."""
    new_text, _ = render_manifest_write(_MARKETPLACE_TEXT, "marketplace_json", "1.2.3", "2.0.0")
    assert read_manifest_version(new_text, "marketplace_json") == "2.0.0"
    parsed = json.loads(new_text)
    assert all(p["version"] == "2.0.0" for p in parsed["plugins"])
