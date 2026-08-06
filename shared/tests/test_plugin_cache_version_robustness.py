"""Never crash on the manifest, and never overclaim about a directory that was guessed.

`installed_plugins.json` belongs to Claude Code, not to this repo. It is versioned
(`version: 2`), so its shape can change under us, and `check_plugin_cache_sync.py` is a
DETECTIVE check that CLAUDE.md tells operators to run after every plugin-side change — it may
never crash a session over another program's file, and a false green in it is worse than a
false red, because the fleet uses it to decide the cache can be trusted.

Two rules follow, and both are asserted here rather than merely commented:

* every unexpected shape degrades to the documented fallback, matching the blanket
  `except Exception` in the shell half (`update-marketplace.sh:71`);
* whenever the compared directory was chosen by the fallback rather than looked up, BOTH the
  green and the drift line say so — the remedy they print ("re-run update-marketplace.sh")
  is otherwise wrong, since re-syncing writes to the installed directory and cannot change
  the one being compared.

Companion to `test_plugin_cache_version_resolution.py` (which directory is chosen) and
`test_plugin_cache_version_pin.py` (the shell/Python literals that must not drift apart).
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPTS = _REPO_ROOT / "scripts"
if str(_SCRIPTS) not in sys.path:
    # APPEND, matching the sibling cache modules (ADR-045).
    sys.path.append(str(_SCRIPTS))

from cache_install_resolve import (  # noqa: E402
    INSTALL_PATH_KEY,
    PLUGINS_KEY,
    default_cache_root,
    default_installed_plugins_path,
    installed_version_name,
    manifest_for,
    plugin_key,
)
from check_plugin_cache_sync import main  # noqa: E402

PLUGIN = "shipwright-foo"
FILES = {"skills/x/SKILL.md": "# x\n"}


def _seed(tmp_path: Path, cache_files: dict[str, str]) -> tuple[Path, Path]:
    """A repo plugin plus one cached 0.2.1 whose contents the caller decides.

    Mirrors ``cache_files`` into the now-gated ``cache/plugins/<name>/`` too —
    the single cached version is also this mirror's own repair source.
    """
    repo, cache = tmp_path / "repo", tmp_path / "cache"
    for root, files in ((repo / "plugins" / PLUGIN, FILES),
                        (cache / PLUGIN / "0.2.1", cache_files),
                        (cache / "plugins" / PLUGIN, cache_files)):
        for rel, content in files.items():
            (root / rel).parent.mkdir(parents=True, exist_ok=True)
            (root / rel).write_text(content, encoding="utf-8")
    return repo, cache


def _run(repo: Path, cache: Path, manifest: Path) -> int:
    return main(["--repo-root", str(repo), "--cache-root", str(cache),
                 "--installed-plugins", str(manifest), "--strict"])


class TestTheVerdictNamesAGuess:
    """A directory picked by the fallback must never be reported as if it were looked up."""

    def test_the_drift_line_names_it(self, tmp_path: Path, capsys):
        repo, cache = _seed(tmp_path, {"skills/x/SKILL.md": "# stale\n"})
        assert _run(repo, cache, tmp_path / "absent.json") == 1
        err = capsys.readouterr().err
        assert "version dir chosen by latest" in err, err

    def test_the_green_line_names_it_too(self, tmp_path: Path, capsys):
        """The false-green half, and the more dangerous one.

        A drift at least sends the operator looking. A GREEN over a guessed directory — a
        fresh higher version dir that happens to match the repo, while the tree runtime
        actually loads is the stale installed one — reports "in sync" about a directory
        nobody runs, which is the exact symptom this change exists to end.
        """
        repo, cache = _seed(tmp_path, FILES)
        assert _run(repo, cache, tmp_path / "absent.json") == 0
        out = capsys.readouterr().out
        assert "version dir chosen by latest" in out, out

    def test_a_real_lookup_stays_silent(self, tmp_path: Path, capsys):
        """A note printed on every run is a note nobody reads (the orphan-advisory rule)."""
        repo, cache = _seed(tmp_path, {"skills/x/SKILL.md": "# stale\n"})
        manifest = tmp_path / "installed_plugins.json"
        manifest.write_text(json.dumps({PLUGINS_KEY: {plugin_key(PLUGIN): [
            {INSTALL_PATH_KEY: str(cache / PLUGIN / "0.2.1")}]}}), encoding="utf-8")
        _run(repo, cache, manifest)
        captured = capsys.readouterr()
        assert "version dir chosen by" not in captured.err + captured.out


class TestTheManifestOnlyAppliesToTheCacheItDescribes:
    """It describes the REAL cache, so it must not be handed to a run measuring another."""

    def test_a_foreign_cache_root_gets_no_implied_manifest(self, tmp_path: Path):
        """Otherwise a run against a tmp cache silently reads the developer's machine: a
        test seeding a real plugin name would go red locally and stay green in CI, where
        ``~/.claude`` does not exist."""
        assert manifest_for(None, tmp_path) is None
        assert manifest_for(None, default_cache_root()) == default_installed_plugins_path()

    def test_an_explicit_manifest_always_wins(self, tmp_path: Path):
        assert manifest_for(str(tmp_path / "m.json"), tmp_path) == tmp_path / "m.json"

    def test_one_verdict_rests_on_one_reading_of_the_manifest(self, tmp_path: Path, monkeypatch):
        """Read once for the whole run, not once per plugin.

        `claude plugin install` and the cache manager rewrite this file. Re-opening it inside
        the loop let a rewrite land mid-verdict, so one report could mix plugins resolved
        from the old manifest, the new one, and a half-written parse.
        """
        import cache_install_resolve as cir
        import check_plugin_cache_sync as cpcs

        repo, cache = _seed(tmp_path, FILES)
        for extra in ("shipwright-bar", "shipwright-baz"):
            (repo / "plugins" / extra).mkdir(parents=True)
            (repo / "plugins" / extra / "SKILL.md").write_text("# x\n", encoding="utf-8")
        manifest = tmp_path / "installed_plugins.json"
        manifest.write_text(json.dumps({PLUGINS_KEY: {}}), encoding="utf-8")

        reads = []
        real = cir.load_manifest
        monkeypatch.setattr(cir, "load_manifest", lambda p: (reads.append(p), real(p))[1])
        monkeypatch.setattr(cpcs, "load_manifest", cir.load_manifest)

        cpcs.check_sync(repo_root=repo, cache_root=cache, installed_plugins=manifest)
        assert len(reads) == 1, f"read the manifest {len(reads)}x for 3 plugins"


class TestItSurvivesAForeignFile:
    """Every unexpected shape degrades to the fallback and says which one it hit."""

    def test_a_plugin_entry_that_is_an_object_falls_back(self, tmp_path: Path):
        """`entries[0]` on a dict raises KeyError — a LookupError, NOT an IndexError.

        The shell uses a blanket `except Exception`, so anything narrower here makes the two
        halves disagree about what is survivable and crashes a check that promises not to.
        """
        path = tmp_path / "installed_plugins.json"
        path.write_text(
            json.dumps({PLUGINS_KEY: {plugin_key(PLUGIN): {INSTALL_PATH_KEY: "/x/0.2.1"}}}),
            encoding="utf-8")
        name, basis = installed_version_name(PLUGIN, path)
        assert name is None
        assert "shape unexpected" in basis, basis

    def test_an_unstatable_candidate_is_unreadable_not_absent(self, tmp_path: Path, monkeypatch):
        """`absent` says "re-run the sync"; `unreadable` refuses to report an unmeasured count.

        The fake denies ONE path — the candidate — and both directions are asserted under it.
        A fake that denied everything passed just as well against the bug this pins (probing
        `candidate.parent`): the parent is listable, so the "absent" arm fell through to the
        right answer for the wrong reason and the "unreadable" arm was denied either way.
        """
        import cache_install_resolve as cir

        base = tmp_path / "shipwright-foo"
        denied, missing = base / "0.2.1", base / "gone"
        denied.mkdir(parents=True)
        real_scandir = os.scandir

        def fake(p):
            if Path(os.fspath(p)) == denied:
                raise PermissionError(13, "denied")
            return real_scandir(p)

        monkeypatch.setattr(cir.os, "scandir", fake)
        assert cir._probe_missing_dir(denied) == "unreadable"
        assert cir._probe_missing_dir(missing) == "absent"

    def test_the_resolver_probes_the_candidate_and_not_its_parent(self, tmp_path: Path, monkeypatch):
        """Through `resolve_version_dir`, because the direct test above cannot see the argument.

        Mutation-checked: changing the call site to `_probe_missing_dir(candidate.parent)`
        leaves the direct-call test green — it passes its own argument — so only a test that
        goes through the resolver pins WHICH path gets probed. With the parent probed, a
        listable plugin dir answers `absent` and every tracked file is then reported missing.
        """
        import cache_install_resolve as cir

        base = tmp_path / PLUGIN
        denied = base / "0.2.1"
        denied.mkdir(parents=True)  # parent stays listable; only the candidate is denied
        real_scandir = os.scandir

        monkeypatch.setattr(cir.os.path, "isdir", lambda p: Path(os.fspath(p)) != denied)
        monkeypatch.setattr(cir.os, "scandir", lambda p: (
            (_ for _ in ()).throw(PermissionError(13, "denied"))
            if Path(os.fspath(p)) == denied else real_scandir(p)))

        manifest = tmp_path / "installed_plugins.json"
        manifest.write_text(json.dumps({PLUGINS_KEY: {plugin_key(PLUGIN): [
            {INSTALL_PATH_KEY: str(denied)}]}}), encoding="utf-8")

        _, reason, _ = cir.resolve_version_dir(base, PLUGIN, manifest)
        assert reason == "unreadable", (
            f"got {reason!r} — a denied version dir under a listable plugin dir must not "
            f"read as `absent`, which prints 'run update-marketplace.sh' and reports every "
            f"tracked file missing on no measurement at all")

    def test_a_denied_stat_does_not_escape_the_resolver(self, tmp_path: Path, monkeypatch):
        """`Path.is_dir()` RE-RAISES PermissionError — it swallows only ENOENT/ENOTDIR/
        EBADF/ELOOP — so probing the candidate with it let a denied stat propagate out of
        `check_sync`, whose docstring promises that no exception leaks out. Making every
        `Path.is_dir` raise pins that the resolver does not depend on it.
        """
        import cache_install_resolve as cir

        def denied(self):
            raise PermissionError(13, "denied")

        manifest = tmp_path / "installed_plugins.json"
        manifest.write_text(json.dumps({PLUGINS_KEY: {plugin_key(PLUGIN): [
            {INSTALL_PATH_KEY: str(tmp_path / PLUGIN / "0.2.1")}]}}), encoding="utf-8")
        monkeypatch.setattr(Path, "is_dir", denied)

        version_dir, reason, basis = cir.resolve_version_dir(tmp_path / PLUGIN, PLUGIN, manifest)
        assert (version_dir, reason) == (None, "absent"), (version_dir, reason)
        assert basis == "installed_plugins", basis

    def test_an_install_path_outside_this_cache_root_is_named(self, tmp_path: Path):
        """Only the final component is used, so a relocated cache must not pass silently."""
        path = tmp_path / "installed_plugins.json"
        path.write_text(
            json.dumps({PLUGINS_KEY: {plugin_key(PLUGIN): [
                {INSTALL_PATH_KEY: "D:\\elsewhere\\shipwright-foo\\0.2.1"}]}}),
            encoding="utf-8")
        name, basis = installed_version_name(
            PLUGIN, path, expected_parent=tmp_path / "cache" / PLUGIN)
        assert name == "0.2.1"
        assert "outside this cache root" in basis, basis
