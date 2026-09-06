"""`check_fr_hygiene_on_touched_rows` — the non-dodgeable, diff-scoped F11 gate
for `fr-authoring.md`'s I1 (name)/I2 (description)/I7 (criterion shape) rules
(iterate-2026-09-06-fr-hygiene-touched-rows).

Real-git via the `git_origin_repo` / `make_worktree` fixtures + helpers from
`test_integrate_main`, the same pattern `test_check_ci_supplychain_ack.py` uses.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from test_integrate_main import _git, _set_repo_identity, _write  # noqa: E402
from tools.verifiers import fr_hygiene as fh  # noqa: E402

_RUN = "iterate-2026-09-06-fr-hygiene-touched-rows"
_SPEC = ".shipwright/planning/01-core/spec.md"

_HEADER = "| ID | Area | Name | Priority | Description | Basis | Layers |\n" \
          "|---|---|---|---|---|---|---|\n"


def _clean_spec(extra_row: str = "", extra_body: str = "") -> str:
    return (
        "## 2. Functional Requirements\n\n"
        + _HEADER
        + "| FR-01.01 | Core | Login | Must | Users can sign in. | interview | unit |\n"
        + extra_row
        + "\n### FR-01.01 — Login\n\n"
        "#### Acceptance Criteria\n"
        "- (E) Given a registered user, when they submit valid credentials, "
        "then they are signed in.\n"
        + extra_body
    )


def _commit_spec(work: Path, content: str, msg: str) -> None:
    _write(work, _SPEC, content)
    _git(work, "add", "-A")
    _git(work, "commit", "-m", msg)
    _git(work, "push", "origin", "main")


def _seed_main(work: Path, content: str) -> None:
    _set_repo_identity(work)
    _commit_spec(work, content, "seed spec")


def _commit_on_worktree(wt: Path, content: str, msg: str) -> str:
    _write(wt, _SPEC, content)
    _git(wt, "add", "-A")
    _git(wt, "commit", "-m", msg)
    return _git(wt, "rev-parse", "HEAD").stdout.strip()


# --- inapplicable / no-op ----------------------------------------------------

def test_skips_outside_a_git_work_tree(tmp_path):
    res = fh.check_fr_hygiene_on_touched_rows(tmp_path, _RUN, "deadbeef")
    assert res.ok is True
    assert "not a git work tree" in res.detail


def test_fails_closed_when_git_context_is_unresolvable(tmp_path, monkeypatch):
    monkeypatch.setattr(fh, "git_context", lambda root: "git_error")
    res = fh.check_fr_hygiene_on_touched_rows(tmp_path, _RUN, "deadbeef")
    assert res.ok is False
    assert "work tree" in res.detail


def test_fails_closed_when_merge_base_is_unresolvable(tmp_path, monkeypatch):
    """The merge-base fail-closed check must fire unconditionally, BEFORE any
    "was spec.md touched" question gets asked — not only when spec.md happens
    to be in whatever narrower view a fallback could see (doubt review, high).
    No path is ever supplied here at all, proving the failure does not depend
    on what changed."""
    monkeypatch.setattr(fh, "git_context", lambda root: "work_tree")
    monkeypatch.setattr(fh, "_branch_base_commit", lambda root, commit: None)
    res = fh.check_fr_hygiene_on_touched_rows(tmp_path, _RUN, "deadbeef")
    assert res.ok is False
    assert "merge-base" in res.detail


def test_fails_closed_when_base_spec_text_is_unreadable(tmp_path, monkeypatch):
    monkeypatch.setattr(fh, "git_context", lambda root: "work_tree")
    monkeypatch.setattr(fh, "_branch_base_commit", lambda root, commit: "basecommit")

    def _fake_run_git(root, *args, timeout=None):
        if args[:2] == ("rev-parse", "deadbeef"):
            return 0, "headsha\n", ""
        if "diff" in args:
            return 0, _SPEC + "\n", ""
        return 1, "", ""

    monkeypatch.setattr(fh, "_run_git", _fake_run_git)

    def _spec_text_at(root, sha, path):
        return None if sha == "basecommit" else "content"

    monkeypatch.setattr(fh, "spec_text_at", _spec_text_at)
    res = fh.check_fr_hygiene_on_touched_rows(tmp_path, _RUN, "deadbeef")
    assert res.ok is False
    assert "at the base commit" in res.detail


def test_passes_when_no_spec_touched(git_origin_repo, make_worktree):
    work, _o = git_origin_repo
    _seed_main(work, _clean_spec())
    wt = make_worktree(work, "frh-nospec")
    _write(wt, "src/app.py", "print('hi')\n")
    _git(wt, "add", "-A")
    _git(wt, "commit", "-m", "unrelated change")
    commit = _git(wt, "rev-parse", "HEAD").stdout.strip()
    res = fh.check_fr_hygiene_on_touched_rows(wt, _RUN, commit)
    assert res.ok is True
    assert "no spec.md touched" in res.detail


# --- the gate fires -----------------------------------------------------------

def test_fails_on_name_and_description_violations_in_a_new_row(git_origin_repo, make_worktree):
    work, _o = git_origin_repo
    _seed_main(work, _clean_spec())
    wt = make_worktree(work, "frh-newrow")
    bad_row = (
        "| FR-01.02 | Core | Build copy-command (POST) | Must | "
        "Calls auth.ts login_handler() per ADR-042. | interview | unit |\n"
    )
    commit = _commit_on_worktree(wt, _clean_spec(extra_row=bad_row), "add bad FR row")
    res = fh.check_fr_hygiene_on_touched_rows(wt, _RUN, commit)
    assert res.ok is False
    assert "FR-01.02" in res.detail
    assert "name carries" in res.detail
    assert "description carries" in res.detail


def test_fails_on_edited_description_of_an_existing_row(git_origin_repo, make_worktree):
    work, _o = git_origin_repo
    _seed_main(work, _clean_spec())
    wt = make_worktree(work, "frh-editrow")
    edited = _clean_spec().replace(
        "Users can sign in.", "Calls src/auth.ts::loginHandler per ADR-099.",
    )
    commit = _commit_on_worktree(wt, edited, "smuggle implementation detail into FR-01.01")
    res = fh.check_fr_hygiene_on_touched_rows(wt, _RUN, commit)
    assert res.ok is False
    assert "FR-01.01" in res.detail


def test_fails_on_malformed_criterion_added_by_a_fold_edit(git_origin_repo, make_worktree):
    """The FOLD pattern fr-authoring.md §3 recommends: description unchanged,
    a new criterion appended. Must still be caught (module docstring)."""
    work, _o = git_origin_repo
    _seed_main(work, _clean_spec())
    wt = make_worktree(work, "frh-fold")
    folded = _clean_spec(
        extra_body="- Scaffold-creation half - verified (auth.ts, test_auth.py): "
                   "confirmed by running the existing suite.\n",
    )
    commit = _commit_on_worktree(wt, folded, "fold a status paragraph in as a criterion")
    res = fh.check_fr_hygiene_on_touched_rows(wt, _RUN, commit)
    assert res.ok is False
    assert "FR-01.01" in res.detail
    assert "Given" in res.detail


def test_passes_when_touched_row_is_clean(git_origin_repo, make_worktree):
    work, _o = git_origin_repo
    _seed_main(work, _clean_spec())
    wt = make_worktree(work, "frh-clean")
    good_row = (
        "| FR-01.02 | Core | Password reset | Should | "
        "Users who forget their password can reset it by email. | interview | unit |\n"
    )
    commit = _commit_on_worktree(wt, _clean_spec(extra_row=good_row), "add clean FR row")
    res = fh.check_fr_hygiene_on_touched_rows(wt, _RUN, commit)
    assert res.ok is True
    assert "clean" in res.detail


def test_passes_when_a_brand_new_spec_file_is_added(git_origin_repo, make_worktree):
    """A spec.md absent at the merge-base (a run that mints a whole new spec)
    must be judged against an empty base, not treated as an infra failure."""
    work, _o = git_origin_repo
    _set_repo_identity(work)
    _write(work, "src/app.py", "print('hi')\n")
    _git(work, "add", "-A")
    _git(work, "commit", "-m", "seed, no spec yet")
    _git(work, "push", "origin", "main")
    wt = make_worktree(work, "frh-newspec")
    commit = _commit_on_worktree(wt, _clean_spec(), "add a brand-new spec.md")
    res = fh.check_fr_hygiene_on_touched_rows(wt, _RUN, commit)
    assert res.ok is True
    assert "clean" in res.detail


def test_fails_on_a_dirty_row_in_a_brand_new_spec_file(git_origin_repo, make_worktree):
    """The "new spec file" case is not special-cased anywhere in the gate — a
    newly ADDED path is a completely ordinary member of `git diff --name-only
    base..commit`'s output (external review, openai leg, raised this as a
    hypothetical untracked-file bypass; verified here that a violating row in
    a brand-new, fully committed spec file is caught exactly like any other)."""
    work, _o = git_origin_repo
    _set_repo_identity(work)
    _write(work, "src/app.py", "print('hi')\n")
    _git(work, "add", "-A")
    _git(work, "commit", "-m", "seed, no spec yet")
    _git(work, "push", "origin", "main")
    wt = make_worktree(work, "frh-newspec-dirty")
    bad_row = (
        "| FR-01.02 | Core | Build copy-command (POST) | Must | "
        "Calls auth.ts login_handler() per ADR-042. | interview | unit |\n"
    )
    commit = _commit_on_worktree(
        wt, _clean_spec(extra_row=bad_row), "add a brand-new spec.md with a bad row",
    )
    res = fh.check_fr_hygiene_on_touched_rows(wt, _RUN, commit)
    assert res.ok is False
    assert "FR-01.02" in res.detail


def test_ignores_a_legacy_violation_in_a_row_this_run_never_touched(git_origin_repo, make_worktree):
    """The whole point of scoping to touched rows: a pre-existing violation on
    an untouched row must not block a run that edits something else."""
    work, _o = git_origin_repo
    legacy_bad_row = (
        "| FR-01.02 | Core | Legacy endpoint (GET) | Must | "
        "Reads from auth.ts per ADR-001, already shipped. | interview | unit |\n"
    )
    _seed_main(work, _clean_spec(extra_row=legacy_bad_row))
    wt = make_worktree(work, "frh-legacy")
    good_row = (
        "| FR-01.03 | Core | Two-factor login | Could | "
        "Users can add a second step to sign-in. | interview | unit |\n"
    )
    commit = _commit_on_worktree(
        wt, _clean_spec(extra_row=legacy_bad_row + good_row), "add unrelated clean FR row",
    )
    res = fh.check_fr_hygiene_on_touched_rows(wt, _RUN, commit)
    assert res.ok is True
    assert "FR-01.02" not in res.detail
