"""Unit P5: ``release.py push-tag`` (F1a/F1b/F4 decided from the run state), the public tag check, and the thin prose.

In-process with an injected runner, as ``test_release_p4_cli.py``; the real-git proof of the three decisions stays in
``tests/golden/test_p4_decisions.py`` (run through the CLI driver since P5).
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

import release
from lib import release_commit, release_push
from .test_release_cli import Fake
from .test_release_p4_cli import HEAD, VERSION, rec, seed

pytestmark = pytest.mark.covers("FR-01.09/AC01")

SKILL_DIR = Path(__file__).resolve().parents[1] / "skills" / "changelog"
OK = {"push-tag-commit": {"stdout": HEAD + "\n"}, "push-head": {"stdout": "main\n"}}
MERGED = {**OK, "verify-base": {"stdout": "origin/main\n"}, "verify-remote-url": {"stdout": "bare\n"}}


def committed(tmp_path: Path) -> None:
    release_commit.write_state(tmp_path, {"version": VERSION, "commit": HEAD, "tag": f"v{VERSION}", "checks_passed": []})


def push(tmp_path: Path, plugin_root: Path, fake: Fake):
    return release_push.push_tag(rec(tmp_path, fake), plugin_root, version=VERSION)


def test_on_the_trunk_the_trunk_and_exactly_this_tag_go_out_in_one_push(tmp_path, plugin_root):
    committed(tmp_path)
    seed(tmp_path, mode="standalone", branch="develop", on_trunk=True)
    fake = Fake(**{**OK, "push-head": {"stdout": "develop\n"}})
    code, out = push(tmp_path, plugin_root, fake)
    assert code == 0 and out["pushed"] is True and fake.keys() == ["push-tag-commit", "push-head", "push-moved", "push-tags"]
    assert fake.argv("push-tags") == ["git", "push", "--end-of-options", "origin", "refs/heads/develop", f"refs/tags/v{VERSION}"]  # never --tags


def test_the_trunk_push_keeps_the_release_guards_rule_that_head_moved_only_by_event_files(tmp_path, plugin_root):
    committed(tmp_path)
    seed(tmp_path, mode="standalone", branch="main", on_trunk=True)
    ok = Fake(**{**OK, "push-moved": {"stdout": "shipwright_events.jsonl\0.shipwright/events/drops/a.jsonl\0"}})
    assert push(tmp_path, plugin_root, ok)[0] == 0
    fake = Fake(**{**OK, "push-moved": {"stdout": "shipwright_events.jsonl\0shipwright_events.jsonl.py\0"}})
    code, out = push(tmp_path, plugin_root, fake)
    assert code == 1 and out["reason"] == "head_moved_since_release" and out["paths"] == ["shipwright_events.jsonl.py"] and "push-tags" not in fake.keys()
    code, out = push(tmp_path, plugin_root, Fake(**{**OK, "push-moved": {"exit": 128}}))
    assert code == 128 and out["reason"] == "head_check_failed"


def test_a_moved_tag_or_a_checkout_on_another_branch_pushes_nothing(tmp_path, plugin_root):
    committed(tmp_path)
    seed(tmp_path, mode="standalone", branch="main", on_trunk=True)
    fake = Fake(**{**OK, "push-tag-commit": {"stdout": "b" * 40 + "\n"}})
    assert push(tmp_path, plugin_root, fake)[1]["reason"] == "tag_not_the_release_commit" and "push-tags" not in fake.keys()
    fake = Fake(**{**OK, "push-head": {"stdout": "other\n"}})
    assert push(tmp_path, plugin_root, fake)[1]["reason"] == "head_not_on_branch" and "push-tags" not in fake.keys()


def test_f1a_from_a_feature_branch_only_the_tag_is_pushed_once_the_release_commit_is_on_the_base(tmp_path, plugin_root):
    committed(tmp_path)
    seed(tmp_path, mode="standalone", branch="release/x", on_trunk=False, pr_url="u")
    fake = Fake(**MERGED)
    code, out = push(tmp_path, plugin_root, fake)
    assert code == 0 and fake.argv("push-tags") == ["git", "push", "origin", f"refs/tags/v{VERSION}"]
    assert fake.keys().index("verify-fetch") < fake.keys().index("verify-merged") < fake.keys().index("push-tags") and out["branch"] == "release/x"


def test_f1b_a_hand_invoked_release_waits_for_the_merge_and_pushes_nothing(tmp_path, plugin_root):
    committed(tmp_path)
    seed(tmp_path, mode="standalone", branch="release/x", on_trunk=False, pr_url="u", autonomy="guided")
    fake = Fake(**MERGED, **{"verify-merged": {"exit": 1}})
    code, out = push(tmp_path, plugin_root, fake)
    assert code == 1 and out["reason"] == "waiting_for_merge" and out["pushed"] is False and "push-tags" not in fake.keys()


def test_an_unreadable_merge_state_is_not_a_merge(tmp_path, plugin_root):
    committed(tmp_path)
    seed(tmp_path, mode="standalone", branch="release/x", on_trunk=False, pr_url="u")
    fake = Fake(**MERGED, **{"verify-fetch": {"exit": 1, "stderr": "could not resolve host"}})
    code, out = push(tmp_path, plugin_root, fake)
    assert code == 1 and out["reason"] == "merge_state_unknown" and "push-tags" not in fake.keys()


def test_a_driven_run_never_merges_its_pr_so_its_tag_goes_out_with_the_pr_open(tmp_path, plugin_root):
    committed(tmp_path)
    seed(tmp_path, mode="pipeline", branch="release/x", on_trunk=False, pr_url="u")
    fake = Fake(**OK)
    code, _ = push(tmp_path, plugin_root, fake)
    assert code == 0 and fake.keys() == ["push-tag-commit", "push-tags"]


def test_a_state_without_a_mode_or_with_a_foreign_branch_name_pushes_nothing(tmp_path, plugin_root):
    committed(tmp_path)
    seed(tmp_path, branch="main", on_trunk=True, mode=None)
    fake = Fake()
    assert push(tmp_path, plugin_root, fake)[1]["reason"] == "run_state_missing"
    seed(tmp_path, mode="standalone", branch="+main")
    assert push(tmp_path, plugin_root, fake)[1]["reason"] == "branch_not_a_trunk" and fake.calls == []


def test_f4_a_refused_push_is_the_pushes_own_exit_code(tmp_path, plugin_root):
    committed(tmp_path)
    seed(tmp_path, mode="standalone", branch="main", on_trunk=True)
    code, out = push(tmp_path, plugin_root, Fake(**{**OK, "push-tags": {"exit": 128, "stderr": "rejected"}}))
    assert code == 128 and out["reason"] == "tag_push_failed" and out["pushed"] is False


def test_nothing_is_pushed_for_a_release_that_was_not_cut_or_whose_event_was_not_recorded(tmp_path, plugin_root):
    seed(tmp_path, mode="standalone", branch="main", on_trunk=True)
    fake = Fake()
    code, out = push(tmp_path, plugin_root, fake)
    assert code == 1 and out["reason"] == "release_not_committed" and fake.calls == []
    committed(tmp_path)
    seed(tmp_path, branch=None)
    code, out = push(tmp_path, plugin_root, fake)
    assert code == 1 and out["reason"] == "event_not_recorded" and fake.calls == []


def test_the_cli_dispatches_push_tag_and_prints_the_payload(tmp_path, plugin_root, capsys):
    committed(tmp_path)
    seed(tmp_path, mode="standalone", branch="main", on_trunk=True)
    fake = Fake(**{**OK, "push-head": {"stdout": "main\n"}})
    code = release.main(["push-tag", "--project-root", str(tmp_path), "--version", VERSION], runner=fake)
    assert code == 0 and json.loads(capsys.readouterr().out)["pushed"] is True and fake.keys() == ["push-tag-commit", "push-head", "push-moved", "push-tags"]


def test_the_tag_check_script_uses_the_public_entry_and_agrees_with_it(tmp_path, plugin_root):
    """Boundary: the plugin script and the shared verifier meet only at ``check_release_tag`` (the P4 review's private-helper import)."""
    script = plugin_root / "scripts" / "checks" / "verify_release_tag.py"
    assert not re.search(r"\bcc\._\w+", script.read_text(encoding="utf-8")), "the script reaches a private helper of the shared verifier"
    shared = plugin_root.parents[1] / "shared"
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "CHANGELOG.md").write_text(f"# Changelog\n\n## [v{VERSION}] - 2026-01-01\n\n- x\n", encoding="utf-8")
    for cmd in (["init", "-b", "main"], ["-c", "user.name=t", "-c", "user.email=t@t", "commit", "--allow-empty", "-m", "x"],
                ["tag", f"v{VERSION}"]):
        subprocess.run(["git", *cmd], cwd=repo, check=True, capture_output=True)

    def run(version: str) -> tuple[int, dict]:
        done = subprocess.run([sys.executable, str(script), "--shared-root", str(shared), "--project-root", str(repo), "--version", version],
                              capture_output=True, text=True, encoding="utf-8", timeout=120)
        return done.returncode, json.loads(done.stdout)

    code, found = run(VERSION)
    assert code == 0 and found["ok"] and set(found["checks"]) == {"tag_exists", "changelog_names_release"} and "advisory" in found
    code, found = run("9.9.9")
    assert code == 1 and not found["ok"] and not found["checks"]["tag_exists"]["ok"]


def _prose() -> dict[str, str]:
    files = [SKILL_DIR / "SKILL.md", *sorted((SKILL_DIR / "references").glob("*.md"))]
    return {f.name: f.read_text(encoding="utf-8") for f in files if f.name != "release-notes-prompt.md"}  # the prompt is a runtime input, not prose for the model


def test_f7_no_prose_line_writes_run_state_in_any_mode():
    """Fails on the prose before P5: SKILL.md Step C and ``compliance-evidence.md`` named ``update-step`` and ``--restore``."""
    forbidden = ("update-step", "update_step", "--restore", "append_phase_history", "update_build_dashboard", "generate_session_handoff")
    found = {name: [w for w in forbidden if w in text] for name, text in _prose().items()}
    assert not {n: w for n, w in found.items() if w}, found


def test_f7_the_phase_close_is_one_close_phase_call_and_every_push_is_the_cli():
    skill = _prose()["SKILL.md"]
    assert len(re.findall(r'release\.py" close-phase', skill)) == 1
    assert "git push" not in skill and "orchestrator.py" not in skill
    assert re.findall(r"^(?:uv run|gh|git) .*$", skill, re.M).count("gh pr merge --merge --delete-branch") == 1  # outward commands stay literal
