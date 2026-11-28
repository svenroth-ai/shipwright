"""R1d: the silent-failure gates of BRIEF 4.1 / 11.7.4 read a moving file where it lives, per commit.

Before R1d ``rel_at`` always answered the root name, so a reader of a HISTORICAL commit (``git show
<sha>:<path>``) saw a moved file as absent: the bloat gate diffed against an empty baseline, the AC
baseline growth check read a move as a bootstrap, the events-layout CI read no layout. And the anti-ratchet
skipped itself when no baseline was found. Each case below builds a real git history with the file in
its new place and asks the real reader.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "shared" / "scripts"))

from lib import shipwright_paths as sp  # noqa: E402

BS, NL = chr(92), chr(10)   # a backslash line continuation, spelled without an escape


def _git(root: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, check=True).stdout.strip()


def _repo(tmp_path: Path) -> Path:
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "t@example.invalid")
    _git(tmp_path, "config", "user.name", "t")
    _git(tmp_path, "config", "commit.gpgsign", "false")
    return tmp_path


def _commit(root: Path, files: dict[str, str | None], msg: str) -> str:
    for rel, text in files.items():
        p = root / rel
        if text is None:
            _git(root, "rm", "-q", "--", rel)
            continue
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
        _git(root, "add", "--", rel)
    _git(root, "commit", "-q", "--no-verify", "-m", msg)
    return _git(root, "rev-parse", "HEAD")


def _move(root: Path, key: str, text: str) -> tuple[str, str]:
    before = _commit(root, {sp.legacy_rel(key): text}, "at the root")
    after = _commit(root, {sp.legacy_rel(key): None, sp.new_rel(key): text}, "moved")
    return before, after


@pytest.mark.covers("FR-01.11")
def test_rel_at_answers_the_place_the_file_has_at_each_commit(tmp_path):
    root = _repo(tmp_path)
    before, after = _move(root, "bloat_baseline", "{}")
    assert sp.rel_at("bloat_baseline", before, root) == sp.legacy_rel("bloat_baseline")
    assert sp.rel_at("bloat_baseline", after, root) == sp.new_rel("bloat_baseline")
    assert sp.rel_at("bloat_baseline", None, root) == sp.new_rel("bloat_baseline")   # the working tree
    assert sp.rel_at("bloat_baseline", "no-such-commit", root) == sp.legacy_rel("bloat_baseline")
    assert sp.rel_at("events", after, root) == sp.legacy_rel("events")   # a file that never moves
    # strict: "git could not answer" is never the same answer as "not in that commit" (CI reads by it)
    assert sp.rel_at("bloat_baseline", before, root, strict=True) == sp.legacy_rel("bloat_baseline")
    with pytest.raises(OSError, match="cannot read commit"):
        sp.rel_at("bloat_baseline", "no-such-commit", root, strict=True)
    for bad in ("", "  ", "--all"):   # an empty rev would read the INDEX; a dash would be a git option
        assert sp.rel_at("bloat_baseline", bad, root) == sp.legacy_rel("bloat_baseline")
        with pytest.raises(OSError, match="not a commit"):
            sp.rel_at("bloat_baseline", bad, root, strict=True)


@pytest.mark.covers("FR-01.11")
def test_migrated_means_the_new_path_exists_never_that_the_root_blob_is_missing(tmp_path):
    """BRIEF 14.4: after R3 the root holds a pointer stub, so "root blob present" must not mean "not moved"."""
    root = _repo(tmp_path)
    key = "run_config"
    stub = _commit(root, {sp.legacy_rel(key): "shipwright-pointer stub", sp.new_rel(key): "{}"}, "stub + new")
    assert sp.rel_at(key, stub, root) == sp.new_rel(key)
    only_root = _commit(root, {sp.new_rel(key): None}, "new removed again")
    assert sp.rel_at(key, only_root, root) == sp.legacy_rel(key)


@pytest.mark.covers("FR-01.11")
def test_the_cli_gives_yaml_and_bash_the_same_answer(tmp_path):
    root = _repo(tmp_path)
    before, after = _move(root, "bloat_baseline", "{}")
    tool = REPO / "shared" / "scripts" / "tools" / "shipwright_rel_at.py"
    run = lambda *a: subprocess.run([sys.executable, str(tool), *a, "--project-root", str(root)],  # noqa: E731
                                    capture_output=True, text=True)
    assert run("bloat_baseline", "--commit", before).stdout.strip() == sp.legacy_rel("bloat_baseline")
    assert run("bloat_baseline", "--commit", after).stdout.strip() == sp.new_rel("bloat_baseline")
    assert run("no_such_key").returncode == 2
    assert run("bloat_baseline", "--commit", "no-such-commit").returncode == 3   # never a silent root answer
    assert run("events", "--commit", "no-such-commit").returncode == 3   # a file that never moves, too
    assert run("events", "--commit", after).stdout.strip() == sp.legacy_rel("events")


@pytest.mark.covers("FR-01.11")
def test_ac_baseline_growth_across_a_move_is_growth_not_a_bootstrap(tmp_path):
    from tools.verifiers._ac_baseline_growth import baseline_grown_since_parent
    root = _repo(tmp_path)
    parent, _ = _move(root, "ac_coverage_baseline", json.dumps({"unbound": ["FR-01.01/AC1"]}))
    grown, warnings = baseline_grown_since_parent(root, root / sp.new_rel("ac_coverage_baseline"),
                                                  {"FR-01.01/AC1", "FR-01.02/AC1"}, parent_sha=parent)
    assert grown == ["FR-01.02/AC1"] and warnings == []   # before R1d: [] (the parent "had no baseline")


@pytest.mark.covers("FR-01.11")
def test_the_events_layout_ci_reads_the_sync_config_where_it_lives_at_the_commit(tmp_path):
    from lib.events_layout_ci import _layout_at
    root = _repo(tmp_path)
    _, after = _move(root, "sync_config", json.dumps({"events_layout": "drops"}))
    assert _layout_at(root, after) == "drops"   # before R1d: None (read the root, which is gone)


@pytest.mark.covers("FR-01.11")
def test_the_rollout_snapshot_reads_the_project_manifest_where_it_lives_at_the_commit(tmp_path):
    from tools.verifiers._project_gate_rollout_snapshot import _rollout_declared_split_names
    root = _repo(tmp_path)
    _, after = _move(root, "project_config", json.dumps({"splits": [{"name": "01-core"}]}))
    assert _rollout_declared_split_names(root, after) == frozenset({"01-core"})   # before R1d: empty


@pytest.mark.covers("FR-01.11")
def test_the_backfill_check_accepts_the_run_written_snapshot_in_either_place():
    from tools.verifiers.test_results_backfill_check import _is_modified_snapshot_status
    for rel in sp.known_rels("test_results"):
        assert _is_modified_snapshot_status(f" M {rel}")
    assert not _is_modified_snapshot_status(" M elsewhere/shipwright_test_results.json")


@pytest.mark.covers("FR-01.11")
def test_the_pr_comment_never_shows_green_when_the_gate_could_not_run():
    sys.path.insert(0, str(REPO / "shared" / "scripts" / "hooks"))
    from build_bloat_diff import _render
    text = _render({"added": [], "removed": [], "changed": []}, {"status": "error", "reason": "missing-baseline"})
    assert "could not run (missing-baseline)" in text and "no anti-ratchet violation" not in text


def _ratchet(root: Path, *flags: str) -> subprocess.CompletedProcess:
    hook = REPO / "shared" / "scripts" / "hooks" / "anti_ratchet_check.py"
    return subprocess.run([sys.executable, str(hook), "--project-root", str(root), "--worktree", *flags],
                          capture_output=True, text=True)


@pytest.mark.covers("FR-01.11")
def test_the_anti_ratchet_fails_closed_without_a_baseline_when_one_is_required(tmp_path):
    assert _ratchet(tmp_path).returncode == 0                       # a fresh consumer repo: still fail-open
    missing = _ratchet(tmp_path, "--require-baseline")
    assert missing.returncode == 1 and "failing closed" in missing.stderr
    as_json = _ratchet(tmp_path, "--require-baseline", "--json")   # what bloat-check.yml reads
    assert as_json.returncode == 1 and json.loads(as_json.stdout)["reason"] == "missing-baseline"
    moved = tmp_path / sp.new_rel("bloat_baseline")
    moved.parent.mkdir(parents=True)
    moved.write_text(json.dumps({"version": 1, "entries": []}), encoding="utf-8")
    assert _ratchet(tmp_path, "--require-baseline").returncode == 0   # found in its new place


@pytest.mark.covers("FR-01.11")
def test_this_repos_bloat_gates_require_the_baseline_and_resolve_it_per_commit():
    """The workflow and the pre-commit hook are not Python, so the behaviour above only protects them if they
    call it: both require the baseline, and the workflow reads the base baseline where it lives at the base."""
    wf = (REPO / ".github" / "workflows" / "bloat-check.yml").read_text(encoding="utf-8")
    hook = (REPO / "scripts" / "hooks" / "pre-commit").read_text(encoding="utf-8")
    # the commands themselves, not a comment that mentions them (external code review)
    assert "--project-root . --require-baseline " + BS + NL + "              --worktree --json" in wf
    assert 'base_rel="$(uv run shared/scripts/tools/shipwright_rel_at.py bloat_baseline ' + BS in wf
    assert 'git show "${{ steps.base.outputs.base_sha }}:${base_rel}"' in wf
    assert 'head_rel="$(uv run shared/scripts/tools/shipwright_rel_at.py bloat_baseline)"' in wf
    assert '--head "$head_rel"' in wf
    assert ":shipwright_bloat_baseline.json" not in wf   # no `git show <base>:<root name>` left
    assert '--project-root "$repo_root" --require-baseline ' + BS + NL + "        --staged; then" in hook
    assert '-f "$repo_root/shipwright_bloat_baseline.json"' not in hook   # the hook no longer skips on it
    assert "anti_ratchet_check.py is missing - blocking" in hook   # nor on a deleted checker
