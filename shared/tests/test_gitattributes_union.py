"""Convention-lock, pure-merge, and AC-4 reproduction for the append-log union
merge driver (`lib/gitattributes_union`).

- Convention-lock / drift (AC-1): the template declares exactly the churn
  allowlist's append-log paths, so a repo can never union one log while leaving
  the other to hand-resolution.
- `merge_into` (AC-1): idempotent, never-clobber merge of the fragment.
- AC-4 reproduction: two concurrent `triage.jsonl` appends merge under the union
  driver with NO conflict markers + no line loss — and a NEGATIVE control proving
  that the driver is what prevents the conflict (default git conflicts).

The guarded git commit-path (`self_heal_gitattributes`) + setup wiring live in
`test_gitattributes_union_selfheal.py`.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))

from lib import gitattributes_union as gu  # noqa: E402
from lib.churn_merge import EVENTS_LOG, TRIAGE_LOG  # noqa: E402

HEADER = '{"v":1,"schema":"triage","created":"2026-06-01T00:00:00Z"}'


# --------------------------------------------------------------------------- #
# Convention lock / drift (AC-1)
# --------------------------------------------------------------------------- #


def test_template_exists_and_declares_every_union_line():
    text = gu.load_fragment()
    for path in gu.UNION_PATHS:
        assert f"{path} merge=union" in text, path


def test_union_paths_match_churn_allowlist_append_logs():
    # The two append-log artifacts the resolver reconciles MUST equal the ones
    # the scaffolded .gitattributes declares (drift guard — keeps the first-line
    # union driver and the second-line resolver covering the same files).
    assert set(gu.UNION_PATHS) == {EVENTS_LOG, TRIAGE_LOG}


def test_managed_marker_is_the_template_first_line():
    assert gu.load_fragment().splitlines()[0] == gu.MANAGED_MARKER


# --------------------------------------------------------------------------- #
# merge_into — pure idempotent merge (AC-1)
# --------------------------------------------------------------------------- #


def test_merge_into_none_writes_full_fragment():
    text, changed = gu.merge_into(None)
    assert changed is True
    assert gu.missing_union_paths(text) == []


def test_merge_into_whitespace_only_treated_as_empty():
    text, changed = gu.merge_into("  \n\n   \n")
    assert changed is True
    assert gu.missing_union_paths(text) == []


def test_merge_into_is_idempotent():
    once, _ = gu.merge_into(None)
    twice, changed = gu.merge_into(once)
    assert changed is False
    assert twice == once


def test_merge_into_preserves_existing_user_entries():
    existing = "*.png binary\n*.md text\n"
    text, changed = gu.merge_into(existing)
    assert changed is True
    assert "*.png binary" in text and "*.md text" in text
    assert gu.missing_union_paths(text) == []


def test_merge_into_partial_adds_only_the_missing_line():
    existing = f"{EVENTS_LOG} merge=union\n"  # one of two already present
    text, changed = gu.merge_into(existing)
    assert changed is True
    assert gu.missing_union_paths(text) == []
    assert text.count(f"{EVENTS_LOG} merge=union") == 1  # not duplicated


def test_declares_union_tolerates_extra_attributes():
    existing = f"{EVENTS_LOG} merge=union -text\n{TRIAGE_LOG}   merge=union\n"
    assert gu.missing_union_paths(existing) == []
    _, changed = gu.merge_into(existing)
    assert changed is False


def test_merge_into_preserves_crlf_eol():
    existing = "*.png binary\r\n"
    text, _ = gu.merge_into(existing)
    assert f"{EVENTS_LOG} merge=union\r\n" in text


def test_no_duplicate_marker_when_marker_already_present():
    existing = gu.MANAGED_MARKER + "\n" + f"{EVENTS_LOG} merge=union\n"
    text, changed = gu.merge_into(existing)
    assert changed is True
    assert text.count(gu.MANAGED_MARKER) == 1


def test_commented_out_union_line_is_not_counted_as_present():
    # A `#`-commented declaration is inert to git, so the real line must still
    # be appended (boundary probe — .gitattributes carries comments).
    existing = f"# {EVENTS_LOG} merge=union\n"
    assert EVENTS_LOG in gu.missing_union_paths(existing)
    text, changed = gu.merge_into(existing)
    assert changed is True
    assert gu._declares_union(text, EVENTS_LOG)


# --------------------------------------------------------------------------- #
# AC-4 — real-git reproduction: union driver vs default conflict
# --------------------------------------------------------------------------- #


def _git(cwd: Path, *args: str, check: bool = True):
    env = os.environ.copy()
    env.update(
        GIT_AUTHOR_NAME="GA Test", GIT_AUTHOR_EMAIL="ga@test.invalid",
        GIT_COMMITTER_NAME="GA Test", GIT_COMMITTER_EMAIL="ga@test.invalid",
    )
    return subprocess.run(
        ["git", *args], cwd=str(cwd), env=env,
        capture_output=True, text=True, encoding="utf-8", check=check,
    )


def _init_triage_repo(root: Path, *, with_union: bool) -> None:
    root.mkdir(parents=True, exist_ok=True)
    _git(root, "init", "-b", "main")
    _git(root, "config", "user.email", "ga@test.invalid")
    _git(root, "config", "user.name", "GA Test")
    (root / ".shipwright").mkdir()
    (root / TRIAGE_LOG).write_text(
        HEADER + "\n" + '{"event":"append","id":"trg-base"}\n', encoding="utf-8"
    )
    if with_union:
        (root / ".gitattributes").write_text(gu.merge_into(None)[0], encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-m", "base")


def _append_commit(root: Path, line: str, msg: str) -> None:
    with (root / TRIAGE_LOG).open("a", encoding="utf-8", newline="\n") as fh:
        fh.write(line + "\n")
    _git(root, "add", "-A")
    _git(root, "commit", "-m", msg)


def test_ac4_union_driver_merges_concurrent_appends_without_markers(tmp_path):
    repo = tmp_path / "repo"
    _init_triage_repo(repo, with_union=True)
    _git(repo, "checkout", "-b", "branch-a")
    _append_commit(repo, '{"event":"append","id":"trg-aaaa"}', "A append")
    _git(repo, "checkout", "main")
    _append_commit(repo, '{"event":"append","id":"trg-bbbb"}', "B append")

    merge = _git(repo, "merge", "--no-edit", "branch-a", check=False)

    assert merge.returncode == 0, merge.stderr
    merged = (repo / TRIAGE_LOG).read_text(encoding="utf-8")
    assert "<<<<<<<" not in merged
    assert "trg-aaaa" in merged and "trg-bbbb" in merged  # no line loss
    assert merged.count(HEADER) == 1  # header not duplicated


def test_ac4_negative_control_without_union_produces_conflict(tmp_path):
    # Proves the union driver is the mechanism: the SAME concurrent appends
    # conflict under git's default merge.
    repo = tmp_path / "repo"
    _init_triage_repo(repo, with_union=False)
    _git(repo, "checkout", "-b", "branch-a")
    _append_commit(repo, '{"event":"append","id":"trg-aaaa"}', "A append")
    _git(repo, "checkout", "main")
    _append_commit(repo, '{"event":"append","id":"trg-bbbb"}', "B append")

    merge = _git(repo, "merge", "--no-edit", "branch-a", check=False)

    assert merge.returncode != 0  # default git: conflict
    assert "<<<<<<<" in (repo / TRIAGE_LOG).read_text(encoding="utf-8")
