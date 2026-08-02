"""What the cache-sync verdict is allowed to claim about what it read.

Companion to ``test_plugin_cache_sync_shared_tree.py`` (which pins what is
compared) and to ``test_plugin_cache_sync.py`` (at its grandfathered size
ceiling). Claiming coverage the loop does not deliver is the defect the whole
iterate exists to close, so it must not reappear in the reporting layer:
deletions the syncer never propagated, trees skipped as ``n/a``, the un-gated
mirror, and an advisory that fires on every healthy run all belong here.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPTS = _REPO_ROOT / "scripts"
_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.append(str(_HERE))  # for the sibling cache_sync_fixtures module
if str(_SCRIPTS) not in sys.path:
    # APPEND, matching the module under test: prepending would let scripts/'s
    # top-level module names win resolution for the whole pytest process
    # (ADR-045 lib-collision, one directory over). Nothing here needs
    # precedence — no other `check_plugin_cache_sync` exists on any path.
    sys.path.append(str(_SCRIPTS))

from check_plugin_cache_sync import check_sync, main  # noqa: E402
from cache_sync_fixtures import seed_repo_and_cache as _seed  # noqa: E402


class TestDeletionsAndUnreadableTrees:
    """States the check used to report as a confident, wrong green."""

    def test_a_cache_only_file_is_counted_as_an_unpropagated_deletion(
            self, tmp_path: Path):
        files = {"scripts/lib/a.py": "a = 1\n"}
        repo, cache = _seed(tmp_path, shared=files,
                            cache_shared={**files, "scripts/lib/gone.py": "x = 1\n"})
        result = check_sync(repo_root=repo, cache_root=cache)
        # Not drift — a legitimately cache-only artifact must not fail the
        # gate — but never silent: it stays importable at runtime.
        assert result["status"] == "ok"
        assert result["shared"]["cache_only_count"] == 1

    def test_the_verdict_names_which_trees_it_covers(self, tmp_path: Path):
        files = {"scripts/lib/a.py": "a = 1\n"}
        repo, cache = _seed(tmp_path, shared=files, cache_shared=files)
        result = check_sync(repo_root=repo, cache_root=cache)
        assert result["verified"] == ["plugins", "shared"]
        assert result["ungated"] and "trg-5005bf57" in result["ungated"][0]

    def test_a_repo_without_shared_does_not_claim_to_have_verified_it(
            self, tmp_path: Path):
        repo, cache = _seed(tmp_path)
        result = check_sync(repo_root=repo, cache_root=cache)
        assert result["status"] == "ok"
        assert "shared" not in result["verified"]


class TestTheCrossPluginMirrorIsOutOfScope:
    """The third cache tree is deliberately not gated here — yet.

    ``cache/plugins/<name>/`` backs ``../../plugins/shipwright-X``. Gating it
    once needed ``ensure_shared_cache._plugins_healthy`` fixed first — it judged
    all 14 mirrors from ONE sentinel file, so a green built on it would have
    restated the bug one tree over. That blocker is gone since
    iterate-2026-08-01-cache-heal-per-plugin: the healer now compares each
    tree's FILE SET against its repair source. Joining the mirror here is now
    plain follow-up work, tracked as ``trg-5005bf57``.

    The healer does not make this check redundant: it detects ABSENCE
    (presence-only, because clone and cache differ in line endings), while this
    check detects STALENESS (CRLF-normalised content hashes).
    """

    def test_a_stale_mirror_neither_drifts_nor_joins_the_walk(self, tmp_path: Path):
        repo, cache = _seed(tmp_path, mirror={"skills/x/SKILL.md": "# stale\n",
                                              "scripts/extra.py": "x = 1\n"})
        result = check_sync(repo_root=repo, cache_root=cache)
        assert result["status"] == "ok"
        # cache_only_count is the assertion the mirror's two files COULD move:
        # were the mirror folded into this record under any key, the extra
        # file with no repo counterpart would land here.
        assert result["plugins"][0]["cache_only_count"] == 0
        assert "plugins" in result["verified"]


class TestOrphanMarkersAreSurfaced:
    """``.orphaned_at`` is the cache manager's notice of intent to delete."""

    def test_markers_are_reported_without_failing_the_gate(self, tmp_path: Path):
        files = {"scripts/lib/a.py": "a = 1\n"}
        repo, cache = _seed(tmp_path, shared=files, cache_shared=files,
                            mirror={"skills/x/SKILL.md": "# x\n"})
        (cache / "shared" / "scripts" / ".orphaned_at").write_text(
            "1785539695046", encoding="utf-8")
        result = check_sync(repo_root=repo, cache_root=cache)
        # Advisory: a pending reap is a warning about the future, not drift now.
        assert result["status"] == "ok"
        assert "shared/scripts" in result["orphan_markers"]

    def test_an_ungated_tree_never_crowds_out_the_gated_one(
            self, tmp_path: Path, capsys):
        """The failure this scan was measured doing on the live cache.

        22 markers existed, 14 of them under the un-gated ``plugins/`` mirror.
        Sorted, every ``plugins/`` path precedes every ``shared/`` one, so a
        truncated advisory named five mirror dirs and never mentioned
        ``shared/scripts`` — the directory whose reap breaks F11. Scanning only
        the gated trees is what makes that structurally impossible.
        """
        files = {"scripts/lib/a.py": "a = 1\n"}
        repo, cache = _seed(tmp_path, shared=files, cache_shared=files)
        for name in ("shipwright-aaa", "shipwright-bbb", "shipwright-ccc"):
            marker = cache / "plugins" / name / ".orphaned_at"
            marker.parent.mkdir(parents=True, exist_ok=True)
            marker.write_text("1785539695046", encoding="utf-8")
        (cache / "shared" / "scripts" / ".orphaned_at").write_text(
            "1785539695046", encoding="utf-8")

        result = check_sync(repo_root=repo, cache_root=cache)
        assert result["orphan_markers"] == ["shared/scripts"]

        # The advisory prints only alongside drift (it is permanently on
        # otherwise), so drift the shared tree to see it reach the operator.
        (cache / "shared" / "scripts" / "lib" / "a.py").write_text(
            "stale = 1\n", encoding="utf-8")
        main(["--repo-root", str(repo), "--cache-root", str(cache)])
        assert "shared/scripts" in capsys.readouterr().err

    def test_a_marker_on_a_cached_plugin_is_reported(self, tmp_path: Path):
        """Pins ``scopes.append(plugin_cache)``, which no test reached before.

        The scope is the plugin BASE, not the version dir, because the cache
        manager writes the marker one level up too — "this whole plugin is up
        for reaping", the most severe marker there is.
        """
        files = {"scripts/lib/a.py": "a = 1\n"}
        repo, cache = _seed(tmp_path, shared=files, cache_shared=files)
        (cache / "shipwright-foo" / ".orphaned_at").write_text(
            "1785539695046", encoding="utf-8")
        result = check_sync(repo_root=repo, cache_root=cache)
        assert result["orphan_markers"] == ["shipwright-foo"]

    def test_no_markers_means_an_empty_list(self, tmp_path: Path):
        files = {"scripts/lib/a.py": "a = 1\n"}
        repo, cache = _seed(tmp_path, shared=files, cache_shared=files,
                            mirror={"skills/x/SKILL.md": "# x\n"})
        result = check_sync(repo_root=repo, cache_root=cache)
        assert result["orphan_markers"] == []


class TestTheGreenLineDoesNotOverclaim:
    """The reported reason this iterate exists: the OK line said too much."""

    def test_ok_line_names_every_tree_it_read(self, tmp_path: Path, capsys):
        # shared/ gets THREE files and the plugin one, so the printed count
        # cannot be satisfied by echoing the plugin's tracked_count.
        files = {"scripts/lib/a.py": "a = 1\n", "constitution.md": "# c\n",
                 "prompts/code_reviewer/system": "review\n"}
        repo, cache = _seed(tmp_path, shared=files, cache_shared=files)
        rc = main(["--repo-root", str(repo), "--cache-root", str(cache)])
        assert rc == 0
        out = capsys.readouterr().out
        assert "shared" in out, "an OK that never mentions shared/ overclaims"
        assert "3 files" in out, "the count proves the tree was walked"
        assert "trg-5005bf57" in out, "the un-gated tree is named where it is read"

    def test_warn_line_names_the_shared_tree_when_it_drifted(
            self, tmp_path: Path, capsys):
        repo, cache = _seed(tmp_path, shared={"scripts/lib/a.py": "new = 1\n"},
                            cache_shared={"scripts/lib/a.py": "old = 1\n"})
        main(["--repo-root", str(repo), "--cache-root", str(cache)])
        err = capsys.readouterr().err
        assert "shared" in err
        # Name the offending file, not just the tree — `- shared/: {}` would
        # satisfy a bare substring check.
        assert "scripts/lib/a.py" in err

    def test_json_payload_carries_both_trees(self, tmp_path: Path, capsys):
        files = {"scripts/lib/a.py": "a = 1\n"}
        repo, cache = _seed(tmp_path, shared=files, cache_shared=files)
        main(["--repo-root", str(repo), "--cache-root", str(cache), "--json"])
        payload = json.loads(capsys.readouterr().out)
        assert {"plugins", "shared", "orphan_markers"} <= set(payload)

    def test_early_return_statuses_carry_the_documented_shape(
            self, tmp_path: Path, capsys):
        """A ``--json`` consumer gets the same keys on BOTH early returns."""
        keys = {"plugins", "shared", "orphan_markers", "drifted_count"}

        repo = tmp_path / "empty_repo"
        repo.mkdir()
        main(["--repo-root", str(repo), "--cache-root", str(tmp_path / "nope"),
              "--json"])
        payload = json.loads(capsys.readouterr().out)
        assert payload["status"] == "cache_root_absent"
        assert keys <= set(payload)

        cache = tmp_path / "cache"
        cache.mkdir()
        main(["--repo-root", str(repo), "--cache-root", str(cache), "--json"])
        payload = json.loads(capsys.readouterr().out)
        assert payload["status"] == "no_repo_plugins"
        assert keys <= set(payload)

    def test_json_mode_keeps_stderr_clean(self, tmp_path: Path, capsys):
        """The advisory must not leak into a ``--json`` consumer's stream."""
        files = {"scripts/lib/a.py": "a = 1\n"}
        repo, cache = _seed(tmp_path, shared=files, cache_shared=files)
        (cache / "shared" / "scripts" / ".orphaned_at").write_text(
            "1785539695046", encoding="utf-8")
        main(["--repo-root", str(repo), "--cache-root", str(cache), "--json"])
        captured = capsys.readouterr()
        assert json.loads(captured.out)["orphan_markers"] == ["shared/scripts"]
        assert captured.err == ""
