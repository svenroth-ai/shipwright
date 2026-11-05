"""Tests for lib/manifest_sync_core.py's ``package_lock_json`` format."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.manifest_sync_core import (  # noqa: E402
    ManifestSyncError,
    SUPPORTED_FORMATS,
    describe_version_state,
    read_manifest_version,
    render_manifest_write,
)

FMT = "package_lock_json"


def _lock(top="1.2.3", root="1.2.3", dep="1.2.3", nl="\n", indent=2) -> str:
    body = {
        "name": "acme", "version": top, "lockfileVersion": 3, "requires": True,
        "packages": {
            "": {"name": "acme", "version": root},
            "node_modules/dep": {"version": dep},
        },
    }
    return json.dumps(body, indent=indent).replace("\n", nl) + nl


@pytest.mark.covers("FR-01.09/AC13")
def test_format_is_supported():
    assert FMT in SUPPORTED_FORMATS


@pytest.mark.covers("FR-01.09/AC13")
def test_read_returns_top_level_version():
    assert read_manifest_version(_lock(), FMT) == "1.2.3"


@pytest.mark.covers("FR-01.09/AC13")
def test_read_tolerates_missing_packages_lockfile_v1():
    assert read_manifest_version('{"version": "1.2.3", "lockfileVersion": 1}', FMT) == "1.2.3"


@pytest.mark.covers("FR-01.09/AC13")
def test_read_tolerates_missing_root_package_entry():
    text = '{"version": "1.2.3", "packages": {"node_modules/x": {"version": "9.9.9"}}}'
    assert read_manifest_version(text, FMT) == "1.2.3"
    assert describe_version_state(text, FMT, "1.2.3") == (True, "")


@pytest.mark.covers("FR-01.09/AC13")
@pytest.mark.parametrize("text", [
    '{"version": "1.2.3", "packages": []}',
    '{"version": "1.2.3", "packages": {"": []}}',
    '{"version": "1.2.3", "packages": {"": {"version": 5}}}',
])
def test_read_rejects_malformed_packages(text):
    with pytest.raises(ManifestSyncError) as exc:
        read_manifest_version(text, FMT)
    assert exc.value.status == "invalid_manifest_structure"


@pytest.mark.covers("FR-01.09/AC13")
def test_describe_flags_diverged_root_package():
    matches, detail = describe_version_state(_lock(top="2.0.0", root="1.9.0"), FMT, "2.0.0")
    assert not matches and "packages" in detail


@pytest.mark.covers("FR-01.09/AC13")
def test_describe_flags_top_level_mismatch():
    assert describe_version_state(_lock(), FMT, "2.0.0")[0] is False


@pytest.mark.covers("FR-01.09/AC13")
def test_describe_ok_when_both_match():
    assert describe_version_state(_lock("2.0.0", "2.0.0"), FMT, "2.0.0") == (True, "")


@pytest.mark.covers("FR-01.09/AC13")
def test_render_updates_both_fields_and_not_dependencies():
    out, reformatted = render_manifest_write(_lock(), FMT, "1.2.3", "2.0.0")
    assert reformatted is False
    parsed = json.loads(out)
    assert parsed["version"] == "2.0.0"
    assert parsed["packages"][""]["version"] == "2.0.0"
    assert parsed["packages"]["node_modules/dep"]["version"] == "1.2.3"


@pytest.mark.covers("FR-01.09/AC13")
def test_render_heals_diverged_versions():
    out, _ = render_manifest_write(_lock("1.2.3", "1.0.0"), FMT, "1.2.3", "2.0.0")
    parsed = json.loads(out)
    assert parsed["version"] == parsed["packages"][""]["version"] == "2.0.0"


@pytest.mark.covers("FR-01.09/AC13")
@pytest.mark.parametrize("nl", ["\n", "\r\n"])
@pytest.mark.parametrize("indent", [2, 4])
def test_render_is_surgical_and_preserves_newlines_and_indent(nl, indent):
    src = _lock(nl=nl, indent=indent)
    out, _ = render_manifest_write(src, FMT, "1.2.3", "2.0.0")
    assert ("\r\n" in out) == (nl == "\r\n")
    # Dependency keeps 1.2.3, so swap only the two root occurrences back.
    assert out.replace("2.0.0", "1.2.3") == src


@pytest.mark.covers("FR-01.09/AC13")
def test_render_without_packages_updates_top_only():
    out, _ = render_manifest_write(
        '{"version": "1.2.3", "lockfileVersion": 1}', FMT, "1.2.3", "2.0.0"
    )
    assert json.loads(out) == {"version": "2.0.0", "lockfileVersion": 1}


@pytest.mark.covers("FR-01.09/AC13")
def test_render_handles_escaped_strings_and_key_order():
    src = '{"packages": {"": {"name": "a\\"b", "version": "1.2.3"}}, "version": "1.2.3"}'
    out, _ = render_manifest_write(src, FMT, "1.2.3", "2.0.0")
    parsed = json.loads(out)
    assert parsed["version"] == parsed["packages"][""]["version"] == "2.0.0"
    assert parsed["packages"][""]["name"] == 'a"b'


@pytest.mark.covers("FR-01.09/AC13")
def test_render_duplicate_root_package_version_is_ambiguous():
    src = '{"version": "1.2.3", "packages": {"": {"version": "1.2.3", "version": "1.2.3"}}}'
    with pytest.raises(ManifestSyncError) as exc:
        render_manifest_write(src, FMT, "1.2.3", "2.0.0")
    assert exc.value.status == "ambiguous_manifest_structure"


@pytest.mark.covers("FR-01.09/AC13")
@pytest.mark.parametrize("src", [
    r'{"name": "a\\", "version": "1.2.3", "packages": {"": {"version": "1.2.3"}}}',
    '{"name": "x{[,]}", "version": "1.2.3", "packages": {"": {"version": "1.2.3"}}}',
    '{"workspaces": ["a", "b"], "version": "1.2.3", "packages": {"": {"workspaces": ["a"], "bin": {"v": "1"}, "version": "1.2.3"}}}',
    r'{"version": "1.2.3", "packages": {"": {"version": "1.2.3"}}}',
    '{"k,{": 1, "version": "1.2.3", "packages": {"": {"version": "1.2.3"}}}',
])
def test_render_scanner_edge_shapes(src):
    out, _ = render_manifest_write(src, FMT, "1.2.3", "2.0.0")
    assert out.replace("2.0.0", "1.2.3") == src
    parsed = json.loads(out)
    assert parsed["packages"][""]["version"] == "2.0.0"
    assert parsed["version"] == "2.0.0"


@pytest.mark.covers("FR-01.09/AC13")
def test_read_rejects_duplicate_root_package_version():
    src = '{"version": "1.2.3", "packages": {"": {"version": "0.1.0", "version": "1.2.3"}}}'
    with pytest.raises(ManifestSyncError) as exc:
        read_manifest_version(src, FMT)
    assert exc.value.status == "ambiguous_manifest_structure"
    assert 'packages[""].version' in exc.value.detail


@pytest.mark.covers("FR-01.09/AC13")
def test_render_rejects_malformed_json_as_parse_error():
    with pytest.raises(ManifestSyncError) as exc:
        render_manifest_write('{"version": "1.2.3', FMT, "1.2.3", "2.0.0")
    assert exc.value.status == "parse_error"
