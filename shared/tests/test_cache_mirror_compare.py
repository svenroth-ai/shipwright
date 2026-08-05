"""Unit tests for ``scripts/cache_mirror_compare.py`` at its own boundary.

``test_plugin_cache_sync_verdict.py`` pins the integration route (through
``check_sync``); this file pins the module's own state vocabulary directly,
including edges the integration route reaches only incidentally.
"""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPTS = _REPO_ROOT / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.append(str(_SCRIPTS))

from cache_mirror_compare import compare_mirror_tree  # noqa: E402


def _write(root: Path, files: dict[str, str]) -> None:
    for rel, content in files.items():
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")


class TestNoSource:
    def test_absent_source_dir_is_no_source(self, tmp_path: Path):
        result = compare_mirror_tree(tmp_path / "absent", tmp_path / "mirror")
        assert result["state"] == "no_source"
        assert result["basis"] == "cache"

    def test_empty_source_dir_is_no_source_not_ok(self, tmp_path: Path):
        source = tmp_path / "source"
        source.mkdir()
        result = compare_mirror_tree(source, tmp_path / "mirror")
        assert result["state"] == "no_source"

    def test_no_source_records_do_not_share_the_sample_list(self, tmp_path: Path):
        """Each call must return its OWN list — a shared one would let one
        caller's mutation corrupt every other no_source record."""
        a = compare_mirror_tree(None, tmp_path / "mirror")
        b = compare_mirror_tree(None, tmp_path / "mirror")
        a["sample"].append("mutated")
        assert b["sample"] == []


class TestNotMirrored:
    def test_absent_mirror_dir_is_not_mirrored(self, tmp_path: Path):
        source = tmp_path / "source"
        _write(source, {"skills/x/SKILL.md": "# x\n"})
        result = compare_mirror_tree(source, tmp_path / "mirror")
        assert result["state"] == "not_mirrored"
        assert result["diff_count"] == 1
        assert result["missing_in_cache_count"] == 1

    def test_empty_mirror_dir_is_also_not_mirrored(self, tmp_path: Path):
        """An EXISTING but empty mirror dir must not fall through to a
        generic drift compare — the docstring's vocabulary covers both."""
        source = tmp_path / "source"
        _write(source, {"skills/x/SKILL.md": "# x\n"})
        mirror = tmp_path / "mirror"
        mirror.mkdir()
        result = compare_mirror_tree(source, mirror)
        assert result["state"] == "not_mirrored"


class TestDriftAndOk:
    def test_matching_content_is_ok(self, tmp_path: Path):
        source, mirror = tmp_path / "source", tmp_path / "mirror"
        _write(source, {"skills/x/SKILL.md": "# x\n"})
        _write(mirror, {"skills/x/SKILL.md": "# x\n"})
        result = compare_mirror_tree(source, mirror)
        assert result["state"] == "ok"
        assert result["basis"] == "cache"

    def test_stale_content_is_drift(self, tmp_path: Path):
        source, mirror = tmp_path / "source", tmp_path / "mirror"
        _write(source, {"skills/x/SKILL.md": "# fresh\n"})
        _write(mirror, {"skills/x/SKILL.md": "# stale\n"})
        result = compare_mirror_tree(source, mirror)
        assert result["state"] == "drift"
        assert "skills/x/SKILL.md" in result["sample"]

    def test_a_mirror_only_file_is_cache_only_not_drift(self, tmp_path: Path):
        source, mirror = tmp_path / "source", tmp_path / "mirror"
        _write(source, {"skills/x/SKILL.md": "# x\n"})
        _write(mirror, {"skills/x/SKILL.md": "# x\n", "extra.py": "x = 1\n"})
        result = compare_mirror_tree(source, mirror)
        assert result["state"] == "ok"
        assert result["cache_only_count"] == 1
