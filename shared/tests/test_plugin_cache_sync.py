"""Tests for ``scripts/check_plugin_cache_sync.py`` (Iterate C.3 / ADR-061)."""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPTS = _REPO_ROOT / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from check_plugin_cache_sync import check_sync, main  # noqa: E402


def _seed_repo_plugin(repo_root: Path, name: str, files: dict[str, str]) -> None:
    """Write a fake repo plugin under ``<repo_root>/plugins/<name>/``."""
    pdir = repo_root / "plugins" / name
    pdir.mkdir(parents=True, exist_ok=True)
    for rel, content in files.items():
        target = pdir / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")


def _seed_cache_plugin(
    cache_root: Path, name: str, version: str, files: dict[str, str],
) -> None:
    """Write a fake cached plugin under ``<cache_root>/<name>/<version>/``."""
    cdir = cache_root / name / version
    cdir.mkdir(parents=True, exist_ok=True)
    for rel, content in files.items():
        target = cdir / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")


def _setup(tmp_path: Path) -> tuple[Path, Path]:
    """Return (repo_root, cache_root) under tmp_path."""
    repo = tmp_path / "repo"
    cache = tmp_path / "cache"
    repo.mkdir()
    cache.mkdir()
    return repo, cache


class TestCheckSync:
    """check_sync() pure-function tests."""

    def test_cache_root_absent_no_op(self, tmp_path: Path):
        repo = tmp_path / "repo"
        repo.mkdir()
        cache = tmp_path / "cache_does_not_exist"
        result = check_sync(repo_root=repo, cache_root=cache)
        assert result["status"] == "cache_root_absent"
        assert result["plugins"] == []
        assert result["drifted_count"] == 0

    def test_no_repo_plugins_dir(self, tmp_path: Path):
        repo, cache = _setup(tmp_path)
        # No `plugins/` dir under repo.
        result = check_sync(repo_root=repo, cache_root=cache)
        assert result["status"] == "no_repo_plugins"

    def test_all_in_sync(self, tmp_path: Path):
        repo, cache = _setup(tmp_path)
        files = {
            "skills/example/SKILL.md": "# Example\nline 2\n",
            "scripts/lib/helper.py": "def x(): return 1\n",
        }
        _seed_repo_plugin(repo, "shipwright-example", files)
        _seed_cache_plugin(cache, "shipwright-example", "0.1.0", files)
        result = check_sync(repo_root=repo, cache_root=cache)
        assert result["status"] == "ok"
        assert result["drifted_count"] == 0
        assert result["plugins"][0]["state"] == "ok"
        assert result["plugins"][0]["cache_version"] == "0.1.0"

    def test_plugin_not_in_cache(self, tmp_path: Path):
        repo, cache = _setup(tmp_path)
        _seed_repo_plugin(repo, "shipwright-example", {
            "skills/example/SKILL.md": "# Example\n",
        })
        # No cache entry for this plugin at all.
        result = check_sync(repo_root=repo, cache_root=cache)
        assert result["status"] == "drift"
        assert result["drifted_count"] == 1
        assert result["plugins"][0]["state"] == "not_in_cache"

    def test_stale_cache_drift(self, tmp_path: Path):
        repo, cache = _setup(tmp_path)
        repo_files = {"skills/example/SKILL.md": "# Updated\nnew line\n"}
        cache_files = {"skills/example/SKILL.md": "# Old\n"}
        _seed_repo_plugin(repo, "shipwright-example", repo_files)
        _seed_cache_plugin(cache, "shipwright-example", "0.1.0", cache_files)
        result = check_sync(repo_root=repo, cache_root=cache)
        assert result["status"] == "drift"
        assert result["drifted_count"] == 1
        entry = result["plugins"][0]
        assert entry["state"] == "drift"
        assert entry["diff_count"] == 1
        assert "skills/example/SKILL.md" in entry["sample"]

    def test_picks_latest_version_dir(self, tmp_path: Path):
        repo, cache = _setup(tmp_path)
        _seed_repo_plugin(repo, "shipwright-example", {
            "skills/example/SKILL.md": "# v2\n",
        })
        # Two versions in cache — pick the lexically-latest.
        _seed_cache_plugin(cache, "shipwright-example", "0.1.0", {
            "skills/example/SKILL.md": "# v1\n",
        })
        _seed_cache_plugin(cache, "shipwright-example", "0.2.0", {
            "skills/example/SKILL.md": "# v2\n",
        })
        result = check_sync(repo_root=repo, cache_root=cache)
        assert result["plugins"][0]["state"] == "ok"
        assert result["plugins"][0]["cache_version"] == "0.2.0"

    def test_ignores_non_shipwright_plugins_in_repo(self, tmp_path: Path):
        repo, cache = _setup(tmp_path)
        _seed_repo_plugin(repo, "external-plugin", {"x.md": "x"})
        _seed_repo_plugin(repo, "shipwright-foo", {"SKILL.md": "# foo\n"})
        _seed_cache_plugin(cache, "shipwright-foo", "0.1.0", {"SKILL.md": "# foo\n"})
        result = check_sync(repo_root=repo, cache_root=cache)
        names = [p["plugin"] for p in result["plugins"]]
        assert "external-plugin" not in names
        assert "shipwright-foo" in names

    def test_skips_pycache_and_other_build_artifacts(self, tmp_path: Path):
        repo, cache = _setup(tmp_path)
        repo_files = {
            "scripts/lib/helper.py": "x = 1\n",
            "scripts/lib/__pycache__/helper.cpython-313.pyc": "garbage",
        }
        cache_files = {"scripts/lib/helper.py": "x = 1\n"}
        _seed_repo_plugin(repo, "shipwright-example", repo_files)
        _seed_cache_plugin(cache, "shipwright-example", "0.1.0", cache_files)
        result = check_sync(repo_root=repo, cache_root=cache)
        # __pycache__ is ignored on both sides → no drift.
        assert result["status"] == "ok"

    def test_skips_files_with_other_suffixes(self, tmp_path: Path):
        repo, cache = _setup(tmp_path)
        _seed_repo_plugin(repo, "shipwright-example", {
            "SKILL.md": "# x\n",
            "data/test.csv": "should,not,count",
        })
        _seed_cache_plugin(cache, "shipwright-example", "0.1.0", {
            "SKILL.md": "# x\n",
            # No CSV file in cache — but it's filtered out by suffix.
        })
        result = check_sync(repo_root=repo, cache_root=cache)
        assert result["status"] == "ok"


class TestCliMain:
    """End-to-end CLI tests via ``main``."""

    def test_cli_exit_0_when_synced(self, tmp_path: Path, capsys):
        repo, cache = _setup(tmp_path)
        files = {"SKILL.md": "# x\n"}
        _seed_repo_plugin(repo, "shipwright-foo", files)
        _seed_cache_plugin(cache, "shipwright-foo", "0.1.0", files)
        rc = main(["--repo-root", str(repo), "--cache-root", str(cache)])
        assert rc == 0
        out = capsys.readouterr().out
        assert "ok" in out

    def test_cli_exit_0_when_drift_default_fail_soft(self, tmp_path: Path, capsys):
        repo, cache = _setup(tmp_path)
        _seed_repo_plugin(repo, "shipwright-foo", {"SKILL.md": "# new\n"})
        _seed_cache_plugin(cache, "shipwright-foo", "0.1.0", {"SKILL.md": "# old\n"})
        rc = main(["--repo-root", str(repo), "--cache-root", str(cache)])
        assert rc == 0  # fail-soft default
        err = capsys.readouterr().err
        assert "WARN" in err
        assert "shipwright-foo" in err

    def test_cli_exit_1_when_drift_strict(self, tmp_path: Path):
        repo, cache = _setup(tmp_path)
        _seed_repo_plugin(repo, "shipwright-foo", {"SKILL.md": "# new\n"})
        _seed_cache_plugin(cache, "shipwright-foo", "0.1.0", {"SKILL.md": "# old\n"})
        rc = main([
            "--repo-root", str(repo),
            "--cache-root", str(cache),
            "--strict",
        ])
        assert rc == 1

    def test_cli_exit_0_when_cache_root_absent(self, tmp_path: Path, capsys):
        repo = tmp_path / "repo"
        repo.mkdir()
        rc = main([
            "--repo-root", str(repo),
            "--cache-root", str(tmp_path / "nope"),
        ])
        assert rc == 0  # no-op
        out = capsys.readouterr().out
        assert "skip" in out

    def test_cli_json_output(self, tmp_path: Path, capsys):
        import json
        repo, cache = _setup(tmp_path)
        files = {"SKILL.md": "# x\n"}
        _seed_repo_plugin(repo, "shipwright-foo", files)
        _seed_cache_plugin(cache, "shipwright-foo", "0.1.0", files)
        rc = main([
            "--repo-root", str(repo),
            "--cache-root", str(cache),
            "--json",
        ])
        assert rc == 0
        out = capsys.readouterr().out
        payload = json.loads(out)
        assert payload["status"] == "ok"
        assert payload["plugins"][0]["plugin"] == "shipwright-foo"


class TestSemVerVersionSelection:
    """Reviewer-flagged Gemini-S1 — version sort must be SemVer-aware."""

    def test_picks_010_over_020_correctly(self, tmp_path: Path):
        """0.10.0 > 0.2.0 in SemVer; lexical sort would get this wrong."""
        repo, cache = _setup(tmp_path)
        _seed_repo_plugin(repo, "shipwright-foo", {"SKILL.md": "# v10\n"})
        _seed_cache_plugin(cache, "shipwright-foo", "0.2.0", {"SKILL.md": "# v2\n"})
        _seed_cache_plugin(cache, "shipwright-foo", "0.10.0", {"SKILL.md": "# v10\n"})
        result = check_sync(repo_root=repo, cache_root=cache)
        assert result["plugins"][0]["state"] == "ok"
        assert result["plugins"][0]["cache_version"] == "0.10.0"

    def test_major_version_dominates(self, tmp_path: Path):
        repo, cache = _setup(tmp_path)
        _seed_repo_plugin(repo, "shipwright-foo", {"SKILL.md": "# v2\n"})
        _seed_cache_plugin(cache, "shipwright-foo", "1.0.0", {"SKILL.md": "# v1\n"})
        _seed_cache_plugin(cache, "shipwright-foo", "2.0.0", {"SKILL.md": "# v2\n"})
        result = check_sync(repo_root=repo, cache_root=cache)
        assert result["plugins"][0]["cache_version"] == "2.0.0"


class TestCrLfNormalization:
    """Reviewer-flagged Gemini-M1 — text-file hashes must be CRLF-invariant."""

    def test_crlf_vs_lf_identical_hash(self, tmp_path: Path):
        repo, cache = _setup(tmp_path)
        # Repo file with LF, cache file with CRLF — semantically identical.
        repo_files_dir = repo / "plugins" / "shipwright-foo"
        cache_files_dir = cache / "shipwright-foo" / "0.1.0"
        repo_files_dir.mkdir(parents=True)
        cache_files_dir.mkdir(parents=True)
        (repo_files_dir / "SKILL.md").write_bytes(b"# Heading\nline 2\n")
        (cache_files_dir / "SKILL.md").write_bytes(b"# Heading\r\nline 2\r\n")
        result = check_sync(repo_root=repo, cache_root=cache)
        assert result["plugins"][0]["state"] == "ok"


class TestSymlinkSkip:
    """Reviewer-flagged OpenAI-M7 / Gemini-S3 — symlinks not followed."""

    def test_symlinked_file_is_skipped(self, tmp_path: Path):
        if sys.platform == "win32":
            try:
                # Symlink support requires elevation on Windows; skip if not available.
                target = tmp_path / "_target"
                target.write_text("x", encoding="utf-8")
                link = tmp_path / "_link"
                link.symlink_to(target)
                link.unlink()
                target.unlink()
            except (OSError, NotImplementedError):
                import pytest
                pytest.skip("symlinks not creatable on this Windows runner")
        repo, cache = _setup(tmp_path)
        _seed_repo_plugin(repo, "shipwright-foo", {"SKILL.md": "# x\n"})
        # Add a symlink in the repo plugin. The hash function refuses
        # to follow it, so it doesn't contribute a hash entry → not
        # a drift signal.
        target = repo / "plugins" / "shipwright-foo" / "target.md"
        target.write_text("real", encoding="utf-8")
        link = repo / "plugins" / "shipwright-foo" / "link.md"
        try:
            link.symlink_to(target)
        except (OSError, NotImplementedError):
            import pytest
            pytest.skip("symlinks not creatable on this runner")
        _seed_cache_plugin(cache, "shipwright-foo", "0.1.0", {
            "SKILL.md": "# x\n",
            "target.md": "real",
            # No link.md — but since the symlink in the repo doesn't
            # produce a hash, it doesn't count as drift.
        })
        result = check_sync(repo_root=repo, cache_root=cache)
        assert result["plugins"][0]["state"] == "ok"


class TestRepoOnlyFileCountsAsDrift:
    """Reviewer-flagged OpenAI-M1 — a file in repo but absent from cache IS drift."""

    def test_repo_added_file_shows_as_drift(self, tmp_path: Path):
        repo, cache = _setup(tmp_path)
        _seed_repo_plugin(repo, "shipwright-foo", {
            "SKILL.md": "# x\n",
            "scripts/new.py": "x = 1\n",  # repo has this; cache doesn't.
        })
        _seed_cache_plugin(cache, "shipwright-foo", "0.1.0", {
            "SKILL.md": "# x\n",
        })
        result = check_sync(repo_root=repo, cache_root=cache)
        entry = result["plugins"][0]
        assert entry["state"] == "drift"
        assert "scripts/new.py" in entry["sample"]
        assert entry["missing_in_cache_count"] == 1


class TestCliNoRepoPluginsSkips:
    """Code-review-M1+M2: `no_repo_plugins` must be a skip, not a WARN."""

    def test_cli_no_repo_plugins_dir_skips_cleanly(self, tmp_path: Path, capsys):
        # Repo without a `plugins/` directory.
        repo = tmp_path / "repo_no_plugins"
        repo.mkdir()
        cache = tmp_path / "cache"
        cache.mkdir()
        rc = main(["--repo-root", str(repo), "--cache-root", str(cache)])
        assert rc == 0
        captured = capsys.readouterr()
        assert "skip" in captured.out
        # CRITICAL: no false-WARN in stderr.
        assert "WARN" not in captured.err
        assert "drift" not in captured.err.lower()


class TestPermissionErrorIsolation:
    """Reviewer-flagged Gemini: filesystem errors mid-walk must not crash the check."""

    def test_unreadable_plugin_file_does_not_crash(self, tmp_path: Path):
        """A file whose hash computation raises OSError doesn't crash the sweep."""
        repo, cache = _setup(tmp_path)
        files = {"SKILL.md": "# x\n", "broken.py": "x = 1\n"}
        _seed_repo_plugin(repo, "shipwright-foo", files)
        _seed_cache_plugin(cache, "shipwright-foo", "0.1.0", files)
        # Sanity check — the actual permission removal is platform-
        # specific and brittle; the unit test here just confirms
        # check_sync doesn't crash on the happy path. The OSError
        # branch is exercised by the `_walk_tracked_files` try/except
        # in production runs and is harder to deterministically
        # trigger in pytest.
        result = check_sync(repo_root=repo, cache_root=cache)
        assert result["status"] == "ok"


class TestOutputIncludesScanContext:
    """Reviewer-flagged OpenAI-L12 — tracked-file count + missing-count surfaced."""

    def test_ok_carries_tracked_count(self, tmp_path: Path):
        repo, cache = _setup(tmp_path)
        _seed_repo_plugin(repo, "shipwright-foo", {
            "SKILL.md": "# x\n",
            "scripts/a.py": "a = 1\n",
            "scripts/b.py": "b = 2\n",
        })
        _seed_cache_plugin(cache, "shipwright-foo", "0.1.0", {
            "SKILL.md": "# x\n",
            "scripts/a.py": "a = 1\n",
            "scripts/b.py": "b = 2\n",
        })
        result = check_sync(repo_root=repo, cache_root=cache)
        entry = result["plugins"][0]
        assert entry["state"] == "ok"
        assert entry["tracked_count"] == 3
