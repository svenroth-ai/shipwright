"""Tests for manifest parsing."""

from lib.manifest import parse_manifest


def test_parse_valid_manifest(tmp_path):
    manifest = tmp_path / "project-manifest.md"
    manifest.write_text(
        "<!-- SPLIT_MANIFEST\n01-auth\n02-dashboard\n03-api\nEND_MANIFEST -->\n\n# Manifest\n"
    )
    result = parse_manifest(manifest)
    assert result.is_valid
    assert result.splits == ["01-auth", "02-dashboard", "03-api"]
    assert result.errors == []


def test_parse_missing_manifest(tmp_path):
    result = parse_manifest(tmp_path / "nonexistent.md")
    assert not result.is_valid
    assert "not found" in result.errors[0]


def test_parse_no_manifest_block(tmp_path):
    manifest = tmp_path / "project-manifest.md"
    manifest.write_text("# Just a regular markdown file\n")
    result = parse_manifest(manifest)
    assert not result.is_valid
    assert "No SPLIT_MANIFEST" in result.errors[0]


def test_parse_invalid_split_name(tmp_path):
    manifest = tmp_path / "project-manifest.md"
    manifest.write_text("<!-- SPLIT_MANIFEST\n01-auth\nInvalid Name\nEND_MANIFEST -->\n")
    result = parse_manifest(manifest)
    assert not result.is_valid
    assert any("Invalid split name" in e for e in result.errors)


def test_parse_empty_manifest_block(tmp_path):
    manifest = tmp_path / "project-manifest.md"
    manifest.write_text("<!-- SPLIT_MANIFEST\nEND_MANIFEST -->\n")
    result = parse_manifest(manifest)
    assert not result.is_valid


def test_parse_duplicate_numbers(tmp_path):
    manifest = tmp_path / "project-manifest.md"
    manifest.write_text("<!-- SPLIT_MANIFEST\n01-auth\n01-other\nEND_MANIFEST -->\n")
    result = parse_manifest(manifest)
    assert not result.is_valid
    assert any("Duplicate" in e for e in result.errors)
