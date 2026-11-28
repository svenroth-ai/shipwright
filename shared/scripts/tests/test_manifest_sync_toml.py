"""Tests for the ``pyproject_toml`` and ``uv_lock`` formats (lib/manifest_sync_toml.py, FINDINGS D111)."""

from __future__ import annotations

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

REPO_ROOT = Path(__file__).resolve().parents[3]

PYPROJECT = """\
[tool.before]
version = "1.2.3"

[project]
name = "acme"
version = "1.2.3"  # the release version
dependencies = ["a>=1"]

[project.optional-dependencies]
dev = ["b"]

[tool.after]
version = "1.2.3"
"""

LOCK = """\
version = 1
revision = 3
requires-python = ">=3.11"

[[package]]
name = "dep"
version = "1.2.3"
source = { registry = "https://pypi.org/simple" }

[[package]]
name = "acme"
version = "1.2.3"
source = { virtual = "." }
dependencies = [
    { name = "dep" },
]

[package.metadata]
requires-dist = [{ name = "dep", specifier = ">=1.2.3" }]

[[package]]
name = "other"
version = "1.2.3"
source = { registry = "https://pypi.org/simple" }
"""


def _changed_lines(before: str, after: str) -> list[tuple[str, str]]:
    a, b = before.split("\n"), after.split("\n")
    assert len(a) == len(b)
    return [(x, y) for x, y in zip(a, b) if x != y]


def _bump(text: str, fmt: str, new: str = "2.0.0") -> str:
    out, reformatted = render_manifest_write(text, fmt, read_manifest_version(text, fmt), new)
    assert reformatted is False
    return out


@pytest.mark.covers("FR-01.09/AC12")
@pytest.mark.parametrize("fmt", ["pyproject_toml", "uv_lock"])
def test_formats_are_supported(fmt):
    assert fmt in SUPPORTED_FORMATS


@pytest.mark.covers("FR-01.09/AC12")
@pytest.mark.parametrize(("name", "fmt"), [("pyproject.toml", "pyproject_toml"), ("uv.lock", "uv_lock")])
def test_a_copy_of_the_real_root_file_changes_only_its_version_line(name, fmt):
    original = (REPO_ROOT / name).read_bytes().decode("utf-8")
    assert "9.9.9" not in original  # the byte check below undoes the first 9.9.9
    current = read_manifest_version(original, fmt)
    bumped = _bump(original, fmt, "9.9.9")
    changed = _changed_lines(original, bumped)
    assert len(changed) == 1
    old_line, new_line = changed[0]
    assert old_line.replace(current, "9.9.9") == new_line
    assert bumped.encode("utf-8").replace(b"9.9.9", current.encode(), 1) == original.encode("utf-8")
    assert read_manifest_version(bumped, fmt) == "9.9.9"


@pytest.mark.covers("FR-01.09/AC12")
def test_pyproject_edit_never_touches_a_version_of_another_table():
    bumped = _bump(PYPROJECT, "pyproject_toml")
    assert _changed_lines(PYPROJECT, bumped) == [
        ('version = "1.2.3"  # the release version', 'version = "2.0.0"  # the release version')
    ]


@pytest.mark.covers("FR-01.09/AC12")
def test_lock_edit_touches_only_the_root_package_not_the_lock_version_or_dependencies():
    bumped = _bump(LOCK, "uv_lock")
    changed = _changed_lines(LOCK, bumped)
    assert changed == [('version = "1.2.3"', 'version = "2.0.0"')]
    assert bumped.index('version = "2.0.0"') > bumped.index('name = "acme"')
    assert bumped.startswith("version = 1\n")
    assert bumped.count('version = "1.2.3"') == 2


@pytest.mark.covers("FR-01.09/AC12")
def test_editable_root_source_is_the_root_package_too():
    lock = LOCK.replace('{ virtual = "." }', '{ editable = "." }')
    assert read_manifest_version(lock, "uv_lock") == "1.2.3"
    assert len(_changed_lines(lock, _bump(lock, "uv_lock"))) == 1


@pytest.mark.covers("FR-01.09/AC12")
def test_crlf_single_quotes_and_comment_survive():
    text = "[project]\r\nname = 'acme'\r\nversion = '1.2.3' # keep\r\n"
    assert _bump(text, "pyproject_toml") == "[project]\r\nname = 'acme'\r\nversion = '2.0.0' # keep\r\n"


@pytest.mark.covers("FR-01.09/AC12")
@pytest.mark.parametrize(("text", "status"), [
    ('[tool.x]\nversion = "1.2.3"\n', "missing_version_field"),
    ('[project]\nname = "acme"\n', "missing_version_field"),
    ('[project]\nname = "acme"\ndynamic = ["version"]\n', "missing_version_field"),
    ('[project]\nversion = 1\n', "invalid_version_type"),
    ('[project\nversion = "1.2.3"\n', "parse_error"),
])
def test_pyproject_without_a_usable_project_version_is_refused_by_name(text, status):
    with pytest.raises(ManifestSyncError) as exc:
        read_manifest_version(text, "pyproject_toml")
    assert exc.value.status == status


@pytest.mark.covers("FR-01.09/AC12")
@pytest.mark.parametrize(("text", "status"), [
    ('version = 1\n', "missing_root_package"),
    (LOCK.replace('source = { virtual = "." }', 'source = { registry = "x" }'), "missing_root_package"),
    (LOCK.replace('{ registry = "https://pypi.org/simple" }', '{ virtual = "." }'), "ambiguous_manifest_structure"),
    ('[[package]]\nname = "acme"\nsource = { virtual = "." }\n', "missing_version_field"),
    ('[[package]]\nname = "acme"\nversion = 1\nsource = { virtual = "." }\n', "invalid_version_type"),
    ('[package]\nname = "acme"\nversion = "1.2.3"\nsource = { virtual = "." }\n', "missing_root_package"),
])
def test_lock_without_one_root_package_version_is_refused_by_name(text, status):
    with pytest.raises(ManifestSyncError) as exc:
        read_manifest_version(text, "uv_lock")
    assert exc.value.status == status


@pytest.mark.covers("FR-01.09/AC12")
@pytest.mark.parametrize("text", [
    'project.version = "1.2.3"\nproject.name = "acme"\n',  # dotted key: no [project] line to edit
    '[project]\nname = "acme"\n"version" = "1.2.3"\n',  # quoted key: the scan does not place it
])
def test_a_version_line_the_scan_cannot_place_alone_is_refused_not_guessed(text):
    assert read_manifest_version(text, "pyproject_toml") == "1.2.3"
    with pytest.raises(ManifestSyncError) as exc:
        render_manifest_write(text, "pyproject_toml", "1.2.3", "2.0.0")
    assert exc.value.status == "ambiguous_manifest_structure"


@pytest.mark.covers("FR-01.09/AC12")
@pytest.mark.parametrize(("text", "fmt"), [(PYPROJECT, "pyproject_toml"), (LOCK, "uv_lock")])
def test_describe_version_state(text, fmt):
    assert describe_version_state(text, fmt, "1.2.3") == (True, "")
    matches, detail = describe_version_state(text, fmt, "2.0.0")
    assert not matches and "1.2.3" in detail


@pytest.mark.covers("FR-01.09/AC12")
@pytest.mark.parametrize("quote", ['"""', "'''"])
def test_a_multi_line_string_is_text_not_a_header_or_a_version_line(quote):
    text = (f'[project]\nname = "acme"\ndescription = {quote}\n[Overview]\nversion = "1.2.3"\n{quote}\n'
            'version = "1.2.3"\n\n[tool.x]\nversion = "1.2.3"\n')
    bumped = _bump(text, "pyproject_toml")
    assert _changed_lines(text, bumped) == [('version = "1.2.3"', 'version = "2.0.0"')]
    assert bumped.index('version = "2.0.0"') > bumped.index(f"{quote}\nversion")


@pytest.mark.covers("FR-01.09/AC12")
def test_an_array_row_that_starts_with_a_bracket_does_not_end_the_table():
    text = '[project]\nname = "acme"\nmatrix = [\n  [1, 2],\n  ["a"],\n]\nversion = "1.2.3"\n[tool.x]\nversion = "1.2.3"\n'
    assert _changed_lines(text, _bump(text, "pyproject_toml")) == [('version = "1.2.3"', 'version = "2.0.0"')]


@pytest.mark.covers("FR-01.09/AC12")
@pytest.mark.parametrize("fmt", ["pyproject_toml", "uv_lock"])
@pytest.mark.parametrize("version", ["2.0.0-rc.1", "2.0.0+build.5", "1.0.0-alpha.beta"])
def test_a_prerelease_or_build_version_is_refused_before_a_write(fmt, version):
    text = PYPROJECT if fmt == "pyproject_toml" else LOCK
    with pytest.raises(ManifestSyncError) as exc:
        render_manifest_write(text, fmt, "1.2.3", version)
    assert exc.value.status == "unsupported_version_for_format"
