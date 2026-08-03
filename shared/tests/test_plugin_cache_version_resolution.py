"""Regression: the sync and the check must pick the SAME cache version directory.

`update-marketplace.sh` writes into the directory named by `installed_plugins.json`
(`_install_path`), while `check_plugin_cache_sync.py` used to compare against the highest
SemVer directory present. Those answers coincide only because the sync's last step deletes
every version dir that is not the installed one. The moment one survives — a `rm -rf` that
lost to a Windows file lock, a `claude plugin install` that materialised the repo's newer
version, an aborted sync — the halves resolve different trees and the fleet gets the whole
P2.06 symptom: the sync reports "up to date" while `--strict` reports drift with every repo
file "missing". Measured 2026-08-01: all 14 plugins carry repo version 0.31.0 against
installed 0.2.x, so a survivor always sorts ABOVE the live one.

The version-resolution half of the same defect as
`test_marketplace_excludes_python_version.py` — one contract, two independent owners. That
module pins the exclusion; this one pins the target directory.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPTS = _REPO_ROOT / "scripts"
if str(_SCRIPTS) not in sys.path:
    # APPEND, matching the sibling cache modules: prepending would let scripts/'s
    # top-level names win resolution for the whole pytest process (ADR-045).
    sys.path.append(str(_SCRIPTS))

from cache_install_resolve import (  # noqa: E402
    PLUGINS_KEY,
    installed_version_name,
    plugin_key,
)
from check_plugin_cache_sync import check_sync  # noqa: E402

PLUGIN = "shipwright-foo"
FILES = {"skills/x/SKILL.md": "# x\n"}


def _write(root: Path, files: dict[str, str]) -> None:
    for rel, content in files.items():
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")


def _seed(tmp_path: Path, *, cache_versions: dict[str, dict[str, str]]) -> tuple[Path, Path]:
    """One repo plugin plus the given ``{version: files}`` cache directories.

    Created even when the file map is EMPTY — the exact shape a survived cleanup or a
    half-finished `claude plugin install` leaves behind. Letting `_write` skip the mkdir
    made these tests pass against a directory that did not exist (caught by the arm below).
    """
    repo, cache = tmp_path / "repo", tmp_path / "cache"
    _write(repo / "plugins" / PLUGIN, FILES)
    for version, files in cache_versions.items():
        (cache / PLUGIN / version).mkdir(parents=True, exist_ok=True)
        _write(cache / PLUGIN / version, files)
    cache.mkdir(parents=True, exist_ok=True)
    return repo, cache


def _installed(tmp_path: Path, cache: Path, version: str | None, *, raw: str | None = None) -> Path:
    """Write an ``installed_plugins.json`` naming ``<cache>/<plugin>/<version>``."""
    path = tmp_path / "installed_plugins.json"
    if raw is not None:
        path.write_text(raw, encoding="utf-8")
        return path
    entry = {"version": version, "installPath": str(cache / PLUGIN / version)}
    path.write_text(json.dumps({PLUGINS_KEY: {plugin_key(PLUGIN): [entry]}}), encoding="utf-8")
    return path


class TestFollowsTheSyncTarget:
    """The live directory is the one the sync writes, not the one that sorts highest."""

    def test_a_stale_higher_version_does_not_become_the_comparison_target(self, tmp_path: Path):
        """The regression in its observable form: 0.31.0 sorts above 0.2.1 and is empty,
        the shape a survived cleanup leaves behind. Resolving by highest SemVer reports
        every repo file missing while the sync it verifies reported "up to date".
        """
        repo, cache = _seed(tmp_path, cache_versions={"0.2.1": FILES, "0.31.0": {}})
        result = check_sync(
            repo_root=repo, cache_root=cache,
            installed_plugins=_installed(tmp_path, cache, "0.2.1"),
        )
        assert result["status"] == "ok", result["plugins"]
        assert result["plugins"][0]["cache_version"] == "0.2.1"
        assert result["plugins"][0]["missing_in_cache_count"] == 0

    def test_the_old_resolver_fails_the_very_same_fixture(self, tmp_path: Path):
        """Both resolvers over ONE fixture, so the fix is proven load-bearing.

        Without this arm the test above passes just as well against a checker that never
        consulted the manifest at all — 0.2.1 is in sync, so any rule that happens to pick
        it looks correct. Here the identical tree is resolved by the pre-change heuristic
        and must produce the opposite verdict: every repo file reported missing from a
        directory the sync had just declared up to date.
        """
        repo, cache = _seed(tmp_path, cache_versions={"0.2.1": FILES, "0.31.0": {}})
        old = check_sync(repo_root=repo, cache_root=cache, installed_plugins=None)
        assert old["status"] == "drift", "fixture no longer reproduces the defect"
        assert old["plugins"][0]["cache_version"] == "0.31.0"
        assert old["plugins"][0]["missing_in_cache_count"] == len(FILES)

    def test_it_follows_the_installed_dir_even_when_another_one_would_pass(self, tmp_path: Path):
        """The converse, so the test cannot pass by "pick whichever is in sync".

        Here the HIGHEST directory is the healthy one and the installed one has drifted.
        A real drift in the tree runtime actually loads must still be reported.
        """
        repo, cache = _seed(
            tmp_path, cache_versions={"0.2.1": {"skills/x/SKILL.md": "# stale\n"}, "0.31.0": FILES},
        )
        result = check_sync(
            repo_root=repo, cache_root=cache,
            installed_plugins=_installed(tmp_path, cache, "0.2.1"),
        )
        assert result["status"] == "drift", result["plugins"]
        assert result["plugins"][0]["cache_version"] == "0.2.1"

    def test_a_named_but_absent_install_dir_is_not_in_cache(self, tmp_path: Path):
        """Never silently fall back to a different tree.

        `installed_plugins.json` names 0.2.1 and only 0.31.0 exists. The sync would
        have skipped this plugin (`[ ! -d "$cache_target" ]`), so "not in cache" is the
        honest verdict; comparing 0.31.0 instead would report on a tree nothing writes.
        """
        repo, cache = _seed(tmp_path, cache_versions={"0.31.0": FILES})
        result = check_sync(
            repo_root=repo, cache_root=cache,
            installed_plugins=_installed(tmp_path, cache, "0.2.1"),
        )
        assert result["plugins"][0]["state"] == "not_in_cache", result["plugins"]


class TestFallbackIsHonest:
    """No authority available → the old heuristic, and the record says so."""

    def test_no_installed_plugins_file_falls_back_to_highest_version(self, tmp_path: Path):
        """Every pre-existing caller passes no authority, so this path must stay intact."""
        repo, cache = _seed(tmp_path, cache_versions={"0.2.0": {}, "0.10.0": FILES})
        result = check_sync(repo_root=repo, cache_root=cache, installed_plugins=None)
        assert result["status"] == "ok", result["plugins"]
        assert result["plugins"][0]["cache_version"] == "0.10.0"
        assert result["plugins"][0]["version_basis"].startswith("latest")

    def test_malformed_json_falls_back_instead_of_crashing(self, tmp_path: Path):
        """A detective check must never crash a session on someone else's file."""
        repo, cache = _seed(tmp_path, cache_versions={"0.2.1": FILES})
        result = check_sync(
            repo_root=repo, cache_root=cache,
            installed_plugins=_installed(tmp_path, cache, None, raw="{not json"),
        )
        assert result["status"] == "ok", result["plugins"]
        assert "unreadable" in result["plugins"][0]["version_basis"]

    def test_a_plugin_absent_from_the_manifest_falls_back(self, tmp_path: Path):
        """`_install_path` returns '' for an uninstalled plugin and the sync skips it."""
        repo, cache = _seed(tmp_path, cache_versions={"0.2.1": FILES})
        path = tmp_path / "installed_plugins.json"
        path.write_text(json.dumps({PLUGINS_KEY: {}}), encoding="utf-8")
        result = check_sync(repo_root=repo, cache_root=cache, installed_plugins=path)
        assert result["status"] == "ok", result["plugins"]
        assert result["plugins"][0]["version_basis"].startswith("latest")

    def test_every_plugin_record_carries_a_version_basis(self, tmp_path: Path):
        """Shape, on every record: a consumer must be able to tell HOW the dir was chosen.

        The same rule `basis` and `verified` already follow in this check — a verdict
        that does not say what it rests on cannot be audited.
        """
        repo, cache = _seed(tmp_path, cache_versions={"0.2.1": FILES})
        for authority in (None, _installed(tmp_path, cache, "0.2.1")):
            result = check_sync(repo_root=repo, cache_root=cache, installed_plugins=authority)
            assert all(p.get("version_basis") for p in result["plugins"]), result["plugins"]

    def test_a_manifest_naming_no_install_path_falls_back(self, tmp_path: Path):
        """Present-but-useless is not authority — the shell's `if entries else ''` branch."""
        repo, cache = _seed(tmp_path, cache_versions={"0.2.1": FILES})
        path = tmp_path / "installed_plugins.json"
        path.write_text(
            json.dumps({PLUGINS_KEY: {plugin_key(PLUGIN): [{"version": "0.2.1"}]}}),
            encoding="utf-8",
        )
        name, basis = installed_version_name(PLUGIN, path)
        assert name is None, basis
        assert basis.startswith("latest")
