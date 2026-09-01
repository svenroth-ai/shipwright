"""Tests for lib/manifest_sync_core.py — config validation, path
containment, and manifest parsing/rendering primitives. CLI orchestration
(sync/verify-commit) is tested from shared/scripts/tools/tests/ instead,
since that is where the pytest-root boundary puts the CLI module.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib.manifest_sync_core import (  # noqa: E402
    ManifestSyncError,
    load_declared_manifests,
    read_manifest_version,
    render_manifest_write,
    resolve_contained_path,
    validate_version,
)


def _write_config(root: Path, entries: list[dict] | None) -> None:
    body = {} if entries is None else {"published_manifests": entries}
    (root / "shipwright_changelog_config.json").write_text(json.dumps(body), encoding="utf-8")


# --- validate_version --------------------------------------------------------


@pytest.mark.parametrize(
    "bad",
    [
        "v1.2.3", " 1.2.3", "1.2.3 ", "1.2.3\n", "1.2", "1.2.3.4", "",
        "01.2.3", "1.02.3", "1.2.03", "1.2.3-01", "1.2.3-01.beta",
    ],
)
def test_validate_version_rejects(bad):
    """Includes SemVer 2.0.0's leading-zero rule, not just shape: a looser
    digits-only check would wrongly accept `01.2.3` / `1.2.3-01`."""
    with pytest.raises(ManifestSyncError) as exc:
        validate_version(bad)
    assert exc.value.status == "invalid_version_argument"


@pytest.mark.parametrize(
    "good", ["1.2.3", "0.0.1", "1.2.3-beta.1", "1.2.3+build.5", "1.2.3-0", "1.2.3-alpha0"]
)
def test_validate_version_accepts(good):
    validate_version(good)  # does not raise


# --- load_declared_manifests / config shape ---------------------------------


def test_no_config_file_is_no_op(tmp_path):
    assert load_declared_manifests(tmp_path) == []


def test_empty_published_manifests_is_no_op(tmp_path):
    _write_config(tmp_path, [])
    assert load_declared_manifests(tmp_path) == []


def test_absent_published_manifests_key_is_no_op(tmp_path):
    (tmp_path / "shipwright_changelog_config.json").write_text("{}", encoding="utf-8")
    assert load_declared_manifests(tmp_path) == []


def test_malformed_json_is_invalid_config(tmp_path):
    (tmp_path / "shipwright_changelog_config.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(ManifestSyncError) as exc:
        load_declared_manifests(tmp_path)
    assert exc.value.status == "invalid_config"


@pytest.mark.parametrize(
    "body",
    [
        {"published_manifests": "not-a-list"},
        {"published_manifests": ["not-an-object"]},
        {"published_manifests": [{"format": "package_json"}]},  # missing path
        {"published_manifests": [{"path": "", "format": "package_json"}]},
        {"published_manifests": [{"path": "a/package.json"}]},  # missing format
    ],
)
def test_malformed_shape_is_invalid_config(tmp_path, body):
    (tmp_path / "shipwright_changelog_config.json").write_text(json.dumps(body), encoding="utf-8")
    with pytest.raises(ManifestSyncError) as exc:
        load_declared_manifests(tmp_path)
    assert exc.value.status == "invalid_config"


def test_duplicate_canonical_path_rejected(tmp_path):
    _write_config(
        tmp_path,
        [
            {"path": "a/package.json", "format": "package_json"},
            {"path": "./a/package.json", "format": "package_json"},
        ],
    )
    with pytest.raises(ManifestSyncError) as exc:
        load_declared_manifests(tmp_path)
    assert exc.value.status == "duplicate_manifest_path"


def test_duplicate_canonical_path_with_dotdot_segment_rejected(tmp_path):
    """`a/../package.json` and `package.json` point at the same file —
    canonicalization must fold the `..` segment, not compare spellings."""
    _write_config(
        tmp_path,
        [
            {"path": "package.json", "format": "package_json"},
            {"path": "a/../package.json", "format": "package_json"},
        ],
    )
    with pytest.raises(ManifestSyncError) as exc:
        load_declared_manifests(tmp_path)
    assert exc.value.status == "duplicate_manifest_path"


# --- resolve_contained_path --------------------------------------------------


def test_absolute_path_rejected(tmp_path):
    with pytest.raises(ManifestSyncError) as exc:
        resolve_contained_path(tmp_path, "/etc/passwd")
    assert exc.value.status == "path_outside_project"


def test_windows_drive_path_rejected(tmp_path):
    with pytest.raises(ManifestSyncError) as exc:
        resolve_contained_path(tmp_path, "C:/Windows/win.ini")
    assert exc.value.status == "path_outside_project"


def test_dotdot_escape_rejected(tmp_path):
    with pytest.raises(ManifestSyncError) as exc:
        resolve_contained_path(tmp_path, "../outside/package.json")
    assert exc.value.status == "path_outside_project"


def test_symlink_in_path_rejected(tmp_path):
    target_dir = tmp_path.parent / "elsewhere"
    target_dir.mkdir(exist_ok=True)
    (target_dir / "package.json").write_text("{}", encoding="utf-8")
    link = tmp_path / "linked"
    try:
        link.symlink_to(target_dir, target_is_directory=True)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"symlinks unsupported in this environment: {exc}")
    with pytest.raises(ManifestSyncError) as exc:
        resolve_contained_path(tmp_path, "linked/package.json")
    assert exc.value.status == "path_is_symlink"


@pytest.mark.skipif(sys.platform != "win32", reason="Windows junctions only")
def test_windows_junction_in_path_rejected(tmp_path):
    """Doubt-reviewer D4: ``Path.is_symlink()`` misses NTFS junctions
    (``IO_REPARSE_TAG_MOUNT_POINT``), and unlike a real symlink, `mklink /J`
    needs no admin/Developer Mode — so this is the one containment test that
    doesn't self-skip on a stock Windows dev machine."""
    target_dir = tmp_path.parent / "elsewhere_junction"
    target_dir.mkdir(exist_ok=True)
    (target_dir / "package.json").write_text("{}", encoding="utf-8")
    link = tmp_path / "linked"
    proc = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(link), str(target_dir)],
        capture_output=True, text=True, check=False,
    )
    if proc.returncode != 0:
        pytest.skip(f"junction creation unsupported in this environment: {proc.stderr}")
    with pytest.raises(ManifestSyncError) as exc:
        resolve_contained_path(tmp_path, "linked/package.json")
    assert exc.value.status == "path_is_symlink"


def test_in_root_symlink_also_rejected(tmp_path):
    """Not just an escape — an IN-ROOT symlink is refused too, since `git add`
    stages the symlink entry, not the resolved target's changed blob."""
    real = tmp_path / "real_pkg.json"
    real.write_text("{}", encoding="utf-8")
    link = tmp_path / "package.json"
    try:
        link.symlink_to(real)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"symlinks unsupported in this environment: {exc}")
    with pytest.raises(ManifestSyncError) as exc:
        resolve_contained_path(tmp_path, "package.json")
    assert exc.value.status == "path_is_symlink"


# --- read_manifest_version ----------------------------------------------------


def test_read_version_missing_key():
    with pytest.raises(ManifestSyncError) as exc:
        read_manifest_version('{"name": "pkg"}', "package_json")
    assert exc.value.status == "missing_version_field"


def test_read_version_non_string():
    with pytest.raises(ManifestSyncError) as exc:
        read_manifest_version('{"version": 123}', "package_json")
    assert exc.value.status == "invalid_version_type"


def test_read_version_parse_error():
    with pytest.raises(ManifestSyncError) as exc:
        read_manifest_version("{not json", "package_json")
    assert exc.value.status == "parse_error"


def test_read_version_unsupported_format():
    with pytest.raises(ManifestSyncError) as exc:
        read_manifest_version('{"version": "1.0.0"}', "cargo_toml")
    assert exc.value.status == "unsupported_format"


def test_read_version_duplicate_top_level_key_rejected():
    text = '{"name": "pkg", "version": "1.0.0", "version": "9.9.9"}'
    with pytest.raises(ManifestSyncError) as exc:
        read_manifest_version(text, "package_json")
    assert exc.value.status == "ambiguous_manifest_structure"


def test_read_version_nested_version_key_is_not_a_false_positive():
    """A NESTED "version" field under a different owner key must not be
    confused with a duplicate ROOT-level "version"."""
    text = '{"name": "pkg", "version": "1.0.0", "config": {"version": "9.9.9"}}'
    assert read_manifest_version(text, "package_json") == "1.0.0"


# --- render_manifest_write ----------------------------------------------------


def test_surgical_substitution_minimal_diff():
    original = '{\n  "name": "pkg",\n  "version": "1.2.3"\n}\n'
    new_text, reformatted = render_manifest_write(original, "package_json", "1.2.3", "1.3.0")
    assert reformatted is False
    assert new_text == '{\n  "name": "pkg",\n  "version": "1.3.0"\n}\n'


def test_surgical_substitution_escapes_regex_metacharacters():
    """An unescaped `.` in a semver value acts as a regex wildcard: without
    `re.escape`, the pattern for "1.2.3" would ALSO match the nested
    "1x2x3" (same length, dots landing on the 'x' positions), turning one
    genuine match into two and forcing an unwanted whole-file re-render.
    A prefix-anchored decoy field (e.g. "description") can never match
    regardless of escaping, since the pattern requires a literal
    `"version":` prefix — it would not actually exercise this bug."""
    original = (
        '{\n  "version": "1.2.3",\n  "peer": {"version": "1x2x3"}\n}\n'
    )
    new_text, reformatted = render_manifest_write(original, "package_json", "1.2.3", "2.0.0")
    assert reformatted is False  # exactly one match: the escaped root field
    assert '"version": "2.0.0"' in new_text
    assert '"version": "1x2x3"' in new_text  # nested decoy untouched


def test_surgical_substitution_ambiguous_falls_back_to_full_render():
    original = '{\n  "name": "pkg",\n  "version": "1.2.3",\n  "peer": {"version": "1.2.3"}\n}\n'
    new_text, reformatted = render_manifest_write(original, "package_json", "1.2.3", "2.0.0")
    assert reformatted is True
    parsed = json.loads(new_text)
    assert parsed["version"] == "2.0.0"


# marketplace_json coverage lives in test_manifest_sync_core_marketplace.py
