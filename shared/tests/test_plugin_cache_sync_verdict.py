"""What the cache-sync verdict is allowed to claim about what it read.

Companion to ``test_plugin_cache_sync_shared_tree.py`` (which pins what is
compared) and to ``test_plugin_cache_sync.py`` (at its grandfathered size
ceiling). Claiming coverage the loop does not deliver is the defect the whole
iterate exists to close, so it must not reappear in the reporting layer:
deletions the syncer never propagated, trees skipped as ``n/a``, the
cross-plugin mirror's own basis/verdict semantics, and an advisory that fires
on every healthy run all belong here.
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
from cache_sync_fixtures import write_tree as _write  # noqa: E402


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
        assert result["verified"] == ["plugins", "shared", "mirror"]
        # All three trees are gated now — nothing left un-gated to name.
        assert result["ungated"] == []

    def test_a_repo_without_shared_does_not_claim_to_have_verified_it(
            self, tmp_path: Path):
        repo, cache = _seed(tmp_path)
        result = check_sync(repo_root=repo, cache_root=cache)
        assert result["status"] == "ok"
        assert "shared" not in result["verified"]


class TestTheCrossPluginMirrorIsInScope:
    """The third cache tree gets its own basis and verdict semantics (P2.29).

    ``cache/plugins/<name>/`` backs ``../../plugins/shipwright-X``. Gating it
    once needed ``ensure_shared_cache._plugins_healthy`` fixed first — it judged
    all 14 mirrors from ONE sentinel file, so a green built on it would have
    restated the bug one tree over. That blocker is gone since
    iterate-2026-08-01-cache-heal-per-plugin: the healer now compares each
    tree's FILE SET against its repair source, so joining the mirror is no
    longer blocked (supersedes trg-5005bf57).

    The healer does not make this check redundant: it detects ABSENCE
    (presence-only, because clone and cache differ in line endings), while this
    check detects STALENESS (CRLF-normalised content hashes) against a basis of
    its own — ``"cache"``, never ``"git"`` — since the mirror's repair source is
    itself a cache-side copy, not the repo.
    """

    def test_a_stale_mirror_is_drift(self, tmp_path: Path):
        repo, cache = _seed(tmp_path, mirror={"skills/x/SKILL.md": "# stale\n",
                                              "scripts/extra.py": "x = 1\n"})
        result = check_sync(repo_root=repo, cache_root=cache)
        assert result["status"] == "drift"
        entry = result["mirror"][0]
        assert entry["state"] == "drift"
        assert entry["basis"] == "cache"
        assert entry["plugin"] == "shipwright-foo"
        assert "skills/x/SKILL.md" in entry["sample"]
        # A mirror-only file (no source counterpart) is an unpropagated
        # deletion, counted but not itself a reason to fail — same rule as
        # the plugins/shared trees' cache_only_count.
        assert entry["cache_only_count"] == 1

    def test_an_in_sync_mirror_is_ok_and_verified(self, tmp_path: Path):
        repo, cache = _seed(tmp_path)  # default mirror matches the source
        result = check_sync(repo_root=repo, cache_root=cache)
        assert result["status"] == "ok"
        assert result["mirror"][0]["state"] == "ok"
        assert "mirror" in result["verified"]

    def test_a_missing_mirror_is_drift(self, tmp_path: Path):
        repo, cache = _seed(tmp_path, mirror=None)
        result = check_sync(repo_root=repo, cache_root=cache)
        assert result["status"] == "drift"
        assert result["mirror"][0]["state"] == "not_mirrored"

    def test_the_warn_line_names_the_drifted_mirror(self, tmp_path: Path, capsys):
        repo, cache = _seed(tmp_path, mirror={"skills/x/SKILL.md": "# stale\n"})
        main(["--repo-root", str(repo), "--cache-root", str(cache)])
        err = capsys.readouterr().err
        assert "mirror shipwright-foo" in err
        assert "skills/x/SKILL.md" in err

    def test_a_green_mirror_never_triggers_the_git_fallback_basis_note(
            self, tmp_path: Path, capsys):
        """The mirror's permanent "cache" basis must not read as a degraded
        git-vs-walk fallback — that note exists to flag the OTHER two trees."""
        repo, cache = _seed(tmp_path)
        rc = main(["--repo-root", str(repo), "--cache-root", str(cache)])
        assert rc == 0
        out = capsys.readouterr().out
        assert "basis: cache" not in out

    def test_a_plugin_with_no_cached_version_reports_no_source_not_drift(
            self, tmp_path: Path):
        """Nothing to hold the mirror accountable to — already a `plugins` finding."""
        import shutil
        repo, cache = _seed(tmp_path, mirror=None)
        shutil.rmtree(cache / "shipwright-foo")
        result = check_sync(repo_root=repo, cache_root=cache)
        assert result["mirror"][0]["state"] == "no_source"
        assert result["plugins"][0]["state"] == "not_in_cache"
        # The double-count rule, pinned on the arithmetic: only the `plugins`
        # record's own absence counts, never the mirror's `no_source` too.
        assert result["drifted_count"] == 1

    def test_the_mirror_source_is_the_newest_cached_version_not_installed_plugins(
            self, tmp_path: Path):
        """The healer this check audits never reads installed_plugins.json.

        A stray newer version dir left over from an aborted sync (P2.06) is
        exactly what the healer would mirror from, so this tree has to judge
        the mirror by the SAME rule the healer used to write it — even where
        that disagrees with the `plugins` tree's own installed_plugins-based
        choice.
        """
        repo, cache = _seed(tmp_path)  # mirror defaults to the 0.1.0 content
        _write(cache / "shipwright-foo" / "0.2.0", {"skills/x/SKILL.md": "# v2\n"})
        # installed_plugins.json names 0.1.0 as the live version — what the
        # `plugins` tree compares against.
        manifest = tmp_path / "installed_plugins.json"
        manifest.write_text(json.dumps({"plugins": {
            "shipwright-foo@shipwright": [
                {"installPath": str(cache / "shipwright-foo" / "0.1.0")},
            ],
        }}), encoding="utf-8")

        result = check_sync(repo_root=repo, cache_root=cache,
                            installed_plugins=manifest)
        assert result["plugins"][0]["cache_version"] == "0.1.0"
        # The mirror is judged against 0.2.0 (the newest cached version, what
        # the healer mirrors from) — drifting against the DEFAULT (0.1.0
        # content) mirror proves it, since judging against 0.1.0 would be ok.
        assert result["mirror"][0]["state"] == "drift"


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

    def test_the_gated_mirror_tree_surfaces_its_own_orphan_markers(
            self, tmp_path: Path, capsys):
        """Now that the mirror is gated (P2.29), its markers are read too.

        Measured on the live cache pre-gating: 22 markers existed, 14 of them
        under the then-un-gated ``plugins/`` mirror, and — sorted — every
        ``plugins/`` path precedes every ``shared/`` one, so a truncated
        advisory named five mirror dirs and never mentioned
        ``shared/scripts``, the directory whose reap breaks F11. That drove
        scanning ONLY the gated trees. Now the mirror IS gated, so scanning it
        too is consistent with that same rule, not a regression of it —
        ``shared/scripts`` still shows up alongside the mirror's own markers.
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
        assert set(result["orphan_markers"]) == {
            "shared/scripts", "plugins/shipwright-aaa",
            "plugins/shipwright-bbb", "plugins/shipwright-ccc",
        }

        # The advisory prints only alongside drift (it is permanently on
        # otherwise), so drift the shared tree to see it reach the operator.
        (cache / "shared" / "scripts" / "lib" / "a.py").write_text(
            "stale = 1\n", encoding="utf-8")
        main(["--repo-root", str(repo), "--cache-root", str(cache)])
        err = capsys.readouterr().err
        assert "shared/scripts" in err
        assert "plugins/shipwright-aaa" in err

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
        assert "mirror" in out, "the third gated tree is named where it is read"

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

    def test_json_payload_carries_all_three_trees(self, tmp_path: Path, capsys):
        files = {"scripts/lib/a.py": "a = 1\n"}
        repo, cache = _seed(tmp_path, shared=files, cache_shared=files)
        main(["--repo-root", str(repo), "--cache-root", str(cache), "--json"])
        payload = json.loads(capsys.readouterr().out)
        assert {"plugins", "shared", "mirror", "orphan_markers"} <= set(payload)

    def test_early_return_statuses_carry_the_documented_shape(
            self, tmp_path: Path, capsys):
        """A ``--json`` consumer gets the same keys on BOTH early returns."""
        keys = {"plugins", "shared", "mirror", "orphan_markers", "drifted_count"}

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
