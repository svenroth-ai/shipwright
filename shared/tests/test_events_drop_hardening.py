"""Hardening before the events-drop-files flip (issue 978 follow-up to S6/S7/S8): seven review findings, each pinned.

1 (see test_events_drop_hardening_fold); 2 the F11 integrity claim
checks ownership and fails when git cannot answer; 3 the layout CI check accepts the rollback an emergency fold leaves;
4 adopt keeps an explicit ``events_layout: null``; 5 the F11 committed-check works in a repo subdirectory; 6 the layout
CI check cannot be bypassed through a side branch from before the flip; 7 the release skill stages only the agent docs a
project has.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.append(str(Path(__file__).resolve().parent))  # after shared/scripts: tests/ has its own `tools`
from _events_fold_helpers import NEW, commit, drop, ev, git, make_repo, put  # noqa: E402

from lib.events_fold_io import GitError  # noqa: E402
from lib.events_integrity import check_integrity  # noqa: E402
from lib.events_layout_ci import check_layout_ci  # noqa: E402
from lib.events_log import DROPS_DIR  # noqa: E402
from tools.verifiers import events_integrity_check  # noqa: E402
from tools.verifiers._events_committed import drops_committed_state  # noqa: E402
from tools.verifiers.events_integrity_check import check_events_integrity  # noqa: E402

pytestmark = pytest.mark.covers("FR-01.11")
ROOT = Path(__file__).resolve().parents[2]
SKILL = ROOT / "plugins" / "shipwright-changelog" / "skills" / "changelog" / "SKILL.md"


def _cfg(root: Path, value="__absent__", **extra) -> None:
    body = {"mappings": [], **extra}
    if value != "__absent__":
        body["events_layout"] = value
    (root / "shipwright_sync_config.json").write_text(json.dumps(body), encoding="utf-8")


def _layout(root: Path) -> object:
    return json.loads((root / "shipwright_sync_config.json").read_text(encoding="utf-8")).get("events_layout")




# --- 2. F11 integrity claim: ownership + fail closed -------------------------------------------------------


@pytest.fixture(name="pr")
def _pr(tmp_path):
    root = make_repo(tmp_path)
    drop(root, "run-old", ev("e1"))
    commit(root, "trunk")
    git(root, "branch", "base")
    git(root, "update-ref", "refs/remotes/origin/main", "base")
    git(root, "symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/main")
    git(root, "switch", "-q", "-c", "pr")
    return root


def test_f11_integrity_flags_a_drop_under_a_key_the_run_does_not_own(pr):
    drop(pr, "run-mine", ev("n1", NEW))
    commit(pr)
    assert check_events_integrity(pr, "run-mine").ok is True
    drop(pr, "run-other", ev("n2", NEW))
    commit(pr)
    bad = check_events_integrity(pr, "run-mine")
    assert bad.ok is False and "foreign_key" in bad.detail and "run-other" in bad.detail


def test_f11_integrity_compares_the_sanitized_run_id_and_allows_the_writers_fallback_key(pr):
    drop(pr, "run-mine", ev("n1", NEW))
    drop(pr, "_main", ev("n2", NEW))               # what the writer uses in the main tree when no run id is set
    commit(pr)
    assert check_events_integrity(pr, "run mine").ok is True        # 'run mine' sanitizes to 'run-mine', as the writer names it
    assert check_integrity(pr, "base", "HEAD", own_keys=("run mine", "_main")) == []   # the CI variant passes the raw id too


def test_f11_integrity_fails_instead_of_skipping_when_git_cannot_answer(pr, monkeypatch):
    drop(pr, "run-mine", ev("n1", NEW))
    commit(pr)

    def broken(*_a, **_kw):
        raise GitError("simulated: git exploded")

    monkeypatch.setattr(events_integrity_check, "check_integrity", broken)
    result = check_events_integrity(pr, "run-mine")
    assert result.ok is False and not result.is_skipped and "NOT checked" in result.detail


@pytest.mark.parametrize("strategy,expected", [("stacked", True), ("single-branch", True), ("serial", False)])
def test_f11_ownership_is_not_enforced_on_a_branch_that_carries_earlier_units(pr, strategy, expected):
    """stacked / single-branch units inherit the earlier units' drops (other keys): not foreign, unlike on serial."""
    drop(pr, "run-parent", ev("p1", NEW))     # the previous unit's drop, still in this branch's range
    drop(pr, "run-mine", ev("n1", NEW))
    (pr / ".shipwright").mkdir(exist_ok=True)
    (pr / ".shipwright" / "loop_state.json").write_text(json.dumps({"branch_strategy": strategy}), encoding="utf-8")
    commit(pr)
    assert check_events_integrity(pr, "run-mine").ok is expected


def test_f11_ownership_finds_the_campaign_state_in_the_campaign_worktree_and_ignores_a_finished_loop(pr):
    drop(pr, "run-parent", ev("p1", NEW))
    drop(pr, "run-mine", ev("n1", NEW))
    commit(pr)
    state = pr / ".worktrees" / "campaign-demo" / ".shipwright" / "loop_state.json"      # where a campaign keeps it, not at the root
    state.parent.mkdir(parents=True)
    state.write_text(json.dumps({"status": "in_progress"}), encoding="utf-8")            # no key = single-branch, the loop's default
    assert check_events_integrity(pr, "run-mine").ok is True
    assert "NOT enforced" in check_events_integrity(pr, "run-mine").detail
    state.write_text(json.dumps({"status": "complete", "branch_strategy": "single-branch"}), encoding="utf-8")
    assert check_events_integrity(pr, "run-mine").ok is False                            # a finished loop no longer switches it off


def test_f11_ownership_accepts_a_drop_written_from_this_worktree_under_another_key(pr):
    """absorb / a re-attempt / a rebase's detached key: the file name carries this worktree's id."""
    from lib.events_layout import worktree_id
    wt8 = worktree_id(pr)
    put(pr, DROPS_DIR, f"run-earlier--{wt8}--00000001.jsonl", {**ev("a1", NEW), "run": "run-earlier"})
    put(pr, DROPS_DIR, "run-stranger--aaaaaaaa--00000001.jsonl", {**ev("a2", NEW), "run": "run-stranger"})
    commit(pr)
    bad = check_events_integrity(pr, "run-mine")
    assert bad.ok is False and "run-stranger" in bad.detail and "run-earlier" not in bad.detail
    (pr / DROPS_DIR / "run-stranger--aaaaaaaa--00000001.jsonl").unlink()
    commit(pr, "only the own-worktree drop")
    assert check_events_integrity(pr, "run-mine").ok is True


def test_f11_integrity_still_skips_outside_a_work_tree(tmp_path):
    assert check_events_integrity(tmp_path, "run-x").is_skipped


# --- 3 + 6. layout CI check -------------------------------------------------------------------------------


def _legacy_append(root: Path, eid: str) -> None:
    with (root / "shipwright_events.jsonl").open("a", encoding="utf-8") as fp:
        fp.write(json.dumps(ev(eid)) + "\n")


def _flipped_repo(tmp_path, *, junk: bool):
    """main on drops, with a legacy log and (optionally) a corrupt drop no fold can move."""
    root = make_repo(tmp_path)
    _cfg(root, "drops")
    (root / "shipwright_events.jsonl").write_text(json.dumps(ev("f" * 8)) + "\n", encoding="utf-8")
    if junk:
        put(root, DROPS_DIR, "run-junk--aaaaaaaa--00000001.jsonl", "not json")
    commit(root, "flipped")
    git(root, "branch", "base-ref")
    git(root, "switch", "-q", "-c", "pr")
    return root


def test_rollback_that_leaves_only_unfoldable_drops_and_writes_the_legacy_log_is_accepted(tmp_path):
    root = _flipped_repo(tmp_path, junk=True)
    _cfg(root, "legacy")                       # the emergency fold: key back to legacy, the corrupt drop stays
    commit(root, "emergency fold")
    _legacy_append(root, "9" * 8)              # the rollback's own F5b event, written under the declared legacy layout
    commit(root, "rollback event")
    assert check_layout_ci(root, "base-ref") == []


def test_rollback_with_a_readable_or_new_drop_left_is_still_an_old_writer(tmp_path):
    root = _flipped_repo(tmp_path, junk=True)
    _cfg(root, "legacy")
    drop(root, "run-live", ev("a" * 16))       # a READABLE drop the fold should have moved
    _legacy_append(root, "9" * 8)
    commit(root, "legacy key, live drop, legacy append")
    assert [v.code for v in check_layout_ci(root, "base-ref")] == ["legacy_write_after_flip"]
    git(root, "reset", "-q", "--hard", "HEAD~1")
    _cfg(root, "legacy")
    put(root, DROPS_DIR, "run-new-junk--aaaaaaaa--00000001.jsonl", "not json")   # corrupt, but ADDED by this change
    _legacy_append(root, "9" * 8)
    commit(root, "legacy key, added junk, legacy append")
    assert [v.code for v in check_layout_ci(root, "base-ref")] == ["legacy_write_after_flip"]


def test_side_branch_from_before_the_flip_cannot_smuggle_a_legacy_append_into_a_post_flip_branch(tmp_path):
    root = make_repo(tmp_path)
    (root / "shipwright_events.jsonl").write_text(json.dumps(ev("f" * 8)) + "\n", encoding="utf-8")
    pre = commit(root, "legacy era")
    git(root, "switch", "-q", "-c", "side", pre)
    _legacy_append(root, "5" * 8)
    commit(root, "legacy append, parent not on drops")
    git(root, "switch", "-q", "main")
    _cfg(root, "drops")
    commit(root, "flip")
    git(root, "switch", "-q", "-c", "pr")
    drop(root, "run-pr", ev("b" * 16))
    commit(root, "pr work, forked after the flip")
    git(root, "merge", "-q", "--no-ff", "--no-edit", "side")
    assert "shipwright_events.jsonl" in git(root, "diff", "--name-only", "main...pr")           # the diff does show the legacy log
    assert [v.code for v in check_layout_ci(root, "main", "pr")] == ["legacy_write_after_flip"]


def test_rollback_exemption_needs_the_leftover_to_be_the_unchanged_unreadable_file_of_the_base(tmp_path):
    root = make_repo(tmp_path)
    _cfg(root, "drops")
    (root / "shipwright_events.jsonl").write_text(json.dumps(ev("f" * 8)) + "\n", encoding="utf-8")
    drop(root, "run-ok", ev("a" * 16))
    put(root, DROPS_DIR, "run-junk--aaaaaaaa--00000001.jsonl", "not json")
    commit(root, "flipped")
    git(root, "branch", "base-ref")
    git(root, "switch", "-q", "-c", "pr")
    _cfg(root, "legacy")
    _legacy_append(root, "9" * 8)
    commit(root, "legacy key, readable base drop left")
    assert [v.code for v in check_layout_ci(root, "base-ref")] == ["legacy_write_after_flip"]   # run-ok is readable: should have been folded
    git(root, "reset", "-q", "--hard", "base-ref")
    (root / DROPS_DIR / "run-ok--aaaaaaaa--00000001.jsonl").unlink()
    (root / DROPS_DIR / "run-ok--aaaaaaaa--00000001.jsonl").parent.joinpath("run-ok--aaaaaaaa--00000001.jsonl").write_text("garbage\n", encoding="utf-8")
    _cfg(root, "legacy")
    _legacy_append(root, "9" * 8)
    commit(root, "legacy key, a readable base drop corrupted by the change, legacy append")
    assert [v.code for v in check_layout_ci(root, "base-ref")] == ["legacy_write_after_flip"]


# --- 4. adopt keeps an explicit null ------------------------------------------------------------------------


def test_adopt_keeps_an_explicit_null_events_layout(tmp_path):
    adopt = ROOT / "plugins" / "shipwright-adopt" / "scripts"
    code = ("import sys; sys.path.insert(0, sys.argv[1]); from lib.events_layout_key import layout_entry; "
            "from pathlib import Path; import json; print(json.dumps(layout_entry(Path(sys.argv[2]), Path(sys.argv[2]) / 'cfg.json')))")

    def entry(text: str | None) -> dict:
        (tmp_path / "cfg.json").unlink(missing_ok=True)
        if text is not None:
            (tmp_path / "cfg.json").write_text(text, encoding="utf-8")
        run = subprocess.run([sys.executable, "-I", "-c", code, str(adopt), str(tmp_path)], capture_output=True, text=True, timeout=120, check=True)
        return json.loads(run.stdout)

    assert entry('{"events_layout": null}') == {"events_layout": None}     # the sentinel refuses this: adopt must not turn it into legacy
    assert entry('{"events_layout": "drops"}') == {"events_layout": "drops"}
    assert entry('{"other": 1}') == {"events_layout": "legacy"}
    assert entry(None) == {"events_layout": "legacy"}
    assert entry("{broken") == {"events_layout": "legacy"}


# --- 5. F11 committed-check in a repo subdirectory ------------------------------------------------------------


def test_committed_check_finds_the_drop_in_heads_tree_when_project_root_is_a_subdirectory(tmp_path):
    repo = make_repo(tmp_path)
    proj = repo / "proj"
    won = {"v": 1, "id": "w1", "ts": NEW, "type": "work_completed", "adr_id": "run-1"}
    drop(proj, "run-1", won)
    commit(repo, "drop committed")
    assert drops_committed_state(proj, "", "run-1", None) is True
    drop(proj, "run-2", {**won, "id": "w2", "adr_id": "run-2"})       # on disk only: F6 forgot to stage it
    assert drops_committed_state(proj, "", "run-2", None) is False


# --- 7. the release skill stages only the agent docs a project has ---------------------------------------------


def _skill_step6() -> str:
    text = SKILL.read_text(encoding="utf-8")
    return text[text.index("## Step 6: Commit and Tag"):]


def test_release_skill_never_names_architecture_or_conventions_unconditionally():
    step = _skill_step6()
    block = step[step.index("```bash"):step.index("```", step.index("```bash") + 7)]
    assert "BULLET_DOCS" in block
    for line in block.splitlines():
        if line.lstrip().startswith(("git add", "git commit", "CHANGELOG.md")):
            assert "architecture.md" not in line and "conventions.md" not in line, line


@pytest.mark.parametrize("have", [(), ("architecture",), ("architecture", "conventions")])
def test_release_skill_snippet_commits_in_a_project_without_the_bullet_docs(tmp_path, have):
    bash = shutil.which("bash")
    if bash is None:
        if os.environ.get("CI", "").lower() in ("true", "1"):
            pytest.fail("bash is required to execute the release skill snippet; install Git for Windows / bash")
        pytest.skip("bash not available")
    step = _skill_step6()
    loop = next(line for line in step.splitlines() if line.startswith("BULLET_DOCS="))
    repo = make_repo(tmp_path)
    docs = repo / ".shipwright" / "agent_docs"
    docs.mkdir(parents=True)
    for name in ("decision_log.md", "decision_log_index.md", *(f"{h}.md" for h in have)):
        (docs / name).write_text("x\n", encoding="utf-8")
    (repo / "CHANGELOG.md").write_text("c\n", encoding="utf-8")
    script = (loop + "\ngit add CHANGELOG.md\n"
              "git add .shipwright/agent_docs/decision_log.md .shipwright/agent_docs/decision_log_index.md $BULLET_DOCS\n"
              'git commit -q -m rel -- CHANGELOG.md .shipwright/agent_docs/decision_log.md .shipwright/agent_docs/decision_log_index.md $BULLET_DOCS\n')
    run = subprocess.run([bash, "-c", script], cwd=repo, capture_output=True, text=True, timeout=60)
    assert run.returncode == 0, run.stderr
    committed = git(repo, "show", "--name-only", "--format=", "HEAD").split()
    assert sorted(p for p in committed if p.endswith(("architecture.md", "conventions.md"))) == sorted(
        f".shipwright/agent_docs/{h}.md" for h in have)
