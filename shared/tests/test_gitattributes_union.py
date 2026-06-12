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

import pytest

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
    for path in gu.ALL_UNION_PATHS:
        assert f"{path} merge=union" in text, path


def test_union_paths_match_churn_allowlist_append_logs():
    # The two append-log artifacts the resolver reconciles MUST equal the ones
    # the scaffolded .gitattributes declares (drift guard — keeps the first-line
    # union driver and the second-line resolver covering the same files). This
    # set stays EXACTLY the two JSONL logs even after curated docs join the union
    # fragment (those live in CURATED_DOC_UNION_PATHS, a distinct category).
    assert set(gu.UNION_PATHS) == {EVENTS_LOG, TRIAGE_LOG}


def test_curated_doc_union_paths_are_the_two_agent_docs():
    # A DISTINCT category from the JSONL logs: curated markdown, not regenerated
    # churn, NOT in CHURN_ALLOWLIST — union is their first+only line of defense.
    assert set(gu.CURATED_DOC_UNION_PATHS) == {
        ".shipwright/agent_docs/architecture.md",
        ".shipwright/agent_docs/conventions.md",
    }
    # The fragment covers BOTH categories; the two are disjoint.
    assert set(gu.ALL_UNION_PATHS) == set(gu.UNION_PATHS) | set(gu.CURATED_DOC_UNION_PATHS)
    assert not (set(gu.UNION_PATHS) & set(gu.CURATED_DOC_UNION_PATHS))
    frag = gu.load_fragment()
    for path in gu.CURATED_DOC_UNION_PATHS:
        assert f"{path} merge=union" in frag, path


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
    # Extra attributes / spacing on the JSONL lines must still count as declared.
    # All four ALL_UNION_PATHS present (curated docs too) → nothing missing.
    existing = (
        f"{EVENTS_LOG} merge=union -text\n{TRIAGE_LOG}   merge=union\n"
        + "".join(f"{p} merge=union\n" for p in gu.CURATED_DOC_UNION_PATHS)
    )
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


# --------------------------------------------------------------------------- #
# Curated agent-doc union — real-git repro. Parameterized over BOTH curated docs
# (path-wiring regression on either is caught) + structural-order asserts.
# --------------------------------------------------------------------------- #

_CURATED_DOC_CASES = [
    (".shipwright/agent_docs/architecture.md", "## Architecture Updates"),
    (".shipwright/agent_docs/conventions.md", "## Learnings"),
]


def _init_curated_repo(root: Path, path: str, anchor: str, *, with_union: bool) -> None:
    root.mkdir(parents=True, exist_ok=True)
    _git(root, "init", "-b", "main")
    _git(root, "config", "user.email", "ga@test.invalid")
    _git(root, "config", "user.name", "GA Test")
    (root / path).parent.mkdir(parents=True, exist_ok=True)
    # A tracked append-log too, so this is a "managed" repo (JSONL beside agent-docs).
    (root / TRIAGE_LOG).write_text(HEADER + "\n", encoding="utf-8")
    (root / path).write_text(
        f"# Doc\n\n{anchor}\n\n- **iterate-base** (2026-06-01): base entry\n",
        encoding="utf-8",
    )
    if with_union:
        (root / ".gitattributes").write_text(gu.merge_into(None)[0], encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-m", "base")


def _prepend_bullet_commit(root: Path, path: str, anchor: str, bullet: str, msg: str) -> None:
    """Insert ``bullet`` as the first entry under ``anchor`` — the F2/F3a pattern."""
    head = f"{anchor}\n\n"
    text = (root / path).read_text(encoding="utf-8")
    assert head in text
    (root / path).write_text(text.replace(head, head + bullet + "\n", 1), encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-m", msg)


@pytest.mark.parametrize("path,anchor", _CURATED_DOC_CASES)
def test_union_merges_concurrent_curated_bullets_without_markers(tmp_path, path, anchor):
    # Two iterates each prepend a bullet at a section top. Under union BOTH bullets
    # survive in order, base preserved, NO markers — and merge=union is honored
    # server-side, so even pure auto-merge stops cascading DIRTY here.
    repo = tmp_path / "repo"
    _init_curated_repo(repo, path, anchor, with_union=True)
    _git(repo, "checkout", "-b", "branch-a")
    _prepend_bullet_commit(repo, path, anchor, "- **iterate-aaaa** (2026-06-12): A change", "A bullet")
    _git(repo, "checkout", "main")
    _prepend_bullet_commit(repo, path, anchor, "- **iterate-bbbb** (2026-06-12): B change", "B bullet")

    merge = _git(repo, "merge", "--no-edit", "branch-a", check=False)

    assert merge.returncode == 0, merge.stderr
    merged = (repo / path).read_text(encoding="utf-8")
    assert "<<<<<<<" not in merged
    assert merged.count(anchor) == 1  # heading not duplicated
    # Structural order: BOTH bullets land after the heading and BEFORE the base.
    h = merged.index(anchor)
    a = merged.index("iterate-aaaa")
    b = merged.index("iterate-bbbb")
    base = merged.index("iterate-base")
    assert h < a < base, merged
    assert h < b < base, merged


@pytest.mark.parametrize("path,anchor", _CURATED_DOC_CASES)
def test_negative_control_curated_bullets_conflict_without_union(tmp_path, path, anchor):
    # Proves union is the mechanism: the SAME prepends conflict under default git
    # merge (exactly what made PRs #207/#208/#210/#211 DIRTY).
    repo = tmp_path / "repo"
    _init_curated_repo(repo, path, anchor, with_union=False)
    _git(repo, "checkout", "-b", "branch-a")
    _prepend_bullet_commit(repo, path, anchor, "- **iterate-aaaa** (2026-06-12): A change", "A bullet")
    _git(repo, "checkout", "main")
    _prepend_bullet_commit(repo, path, anchor, "- **iterate-bbbb** (2026-06-12): B change", "B bullet")

    merge = _git(repo, "merge", "--no-edit", "branch-a", check=False)

    assert merge.returncode != 0  # default git: conflict
    assert "<<<<<<<" in (repo / path).read_text(encoding="utf-8")
