"""``pointer_worktree_root`` must redirect only to a GENUINE linked worktree
of the resolved main repo — not any directory a pointer's ``worktree_path``
happens to name that is merely contained under main and carries a `.git`
entry (external review, round 3, security finding).
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from lib.phase_quality._run_id import pointer_worktree_root
from lib.phase_quality._worktree_identity import is_worktree_of
from lib.worktree_isolation import write_run_pointer


def _init_main(main_root: Path) -> None:
    main_root.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=str(main_root), check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"],
                    cwd=str(main_root), check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=str(main_root), check=True)
    subprocess.run(["git", "commit", "--allow-empty", "-q", "-m", "init"],
                    cwd=str(main_root), check=True)


def test_resolves_a_genuine_linked_worktree(tmp_path: Path):
    main_root = tmp_path / "main"
    _init_main(main_root)
    worktree = main_root / ".worktrees" / "demo"
    subprocess.run(["git", "worktree", "add", "-q", "-b", "demo", str(worktree)],
                    cwd=str(main_root), check=True)
    write_run_pointer(
        main_root, run_id="run-a", slug="demo", branch="demo",
        worktree_path=worktree, session_id="sess-1",
    )
    assert pointer_worktree_root(main_root, "sess-1") == worktree.resolve()


def test_rejects_a_directory_with_a_fake_git_dir_entry(tmp_path: Path):
    """A `.git` DIRECTORY (not the gitdir-FILE shape a real linked worktree
    has) must not be accepted — the bare `.exists()` check external review
    flagged would have redirected the audit into it."""
    main_root = tmp_path / "main"
    _init_main(main_root)
    rogue = main_root / ".worktrees" / "rogue"
    (rogue / ".git").mkdir(parents=True)
    write_run_pointer(
        main_root, run_id="run-a", slug="rogue", branch="rogue",
        worktree_path=rogue, session_id="sess-1",
    )
    assert pointer_worktree_root(main_root, "sess-1") is None


def test_rejects_a_gitdir_file_pointing_outside_main_roots_worktrees_tree(tmp_path: Path):
    """A `.git` FILE that parses as a gitdir pointer, but names a location
    outside `main_root/.git/worktrees/`, must not be accepted even though the
    candidate directory itself IS contained under `main_root` — the FILE
    shape alone is not identity."""
    main_root = tmp_path / "main"
    _init_main(main_root)
    other_root = tmp_path / "other"
    _init_main(other_root)
    foreign_gitdir = other_root / ".git" / "worktrees" / "foreign"
    foreign_gitdir.mkdir(parents=True)

    spoofed = main_root / ".worktrees" / "spoofed"
    spoofed.mkdir(parents=True)
    (spoofed / ".git").write_text(f"gitdir: {foreign_gitdir}\n", encoding="utf-8")

    write_run_pointer(
        main_root, run_id="run-a", slug="spoofed", branch="spoofed",
        worktree_path=spoofed, session_id="sess-1",
    )
    assert pointer_worktree_root(main_root, "sess-1") is None


def test_rejects_a_pointer_owned_by_a_different_session(tmp_path: Path):
    """A pointer FILE keyed to `sess-1`'s sanitised filename, but whose OWN
    `session_id` payload names a different session, must not redirect
    `sess-1`'s audit — the same ownership check `pointer_run_id` already
    applies (a filename alone is not proof of ownership: two session ids can
    sanitise to the same name), which `pointer_worktree_root` was missing
    (external review, round 3, security finding)."""
    main_root = tmp_path / "main"
    _init_main(main_root)
    worktree = main_root / ".worktrees" / "demo"
    subprocess.run(["git", "worktree", "add", "-q", "-b", "demo", str(worktree)],
                    cwd=str(main_root), check=True)

    # Written under the path `read_run_pointer(main_root, "sess-1")` reads,
    # but the payload's own `session_id` names a DIFFERENT session.
    write_run_pointer(
        main_root, run_id="run-a", slug="demo", branch="demo",
        worktree_path=worktree, session_id="sess-1",
    )
    pointer_path = main_root / ".shipwright" / "iterate_active" / "sess-1.json"
    data = json.loads(pointer_path.read_text(encoding="utf-8"))
    data["session_id"] = "sess-OTHER"
    pointer_path.write_text(json.dumps(data), encoding="utf-8")

    assert pointer_worktree_root(main_root, "sess-1") is None


def test_pointer_worktree_root_returns_none_for_a_sentinel_session(tmp_path: Path):
    main_root = tmp_path / "main"
    _init_main(main_root)
    assert pointer_worktree_root(main_root, "") is None


def test_pointer_worktree_root_falls_back_to_git_when_cwd_is_a_subdirectory(tmp_path: Path):
    """`fast_main_root` only short-circuits when `cwd/.git` is itself a
    directory. A cwd one level INSIDE main (no `.git` of its own) must fall
    through to the git-based `resolve_main_repo_root` resolver, not just
    return None — proving the two-tier resolution actually chains."""
    main_root = tmp_path / "main"
    _init_main(main_root)
    worktree = main_root / ".worktrees" / "demo"
    subprocess.run(["git", "worktree", "add", "-q", "-b", "demo", str(worktree)],
                    cwd=str(main_root), check=True)
    write_run_pointer(
        main_root, run_id="run-a", slug="demo", branch="demo",
        worktree_path=worktree, session_id="sess-1",
    )
    subdir = main_root / "shared"
    subdir.mkdir(parents=True, exist_ok=True)

    assert pointer_worktree_root(subdir, "sess-1") == worktree.resolve()


def test_pointer_worktree_root_returns_none_when_worktree_path_is_blank(tmp_path: Path):
    main_root = tmp_path / "main"
    _init_main(main_root)
    write_run_pointer(
        main_root, run_id="run-a", slug="demo", branch="demo",
        worktree_path=main_root / ".worktrees" / "demo", session_id="sess-1",
    )
    # str(Path("")) is "." (truthy), not "" — the blank case can only be
    # produced by editing the payload directly, matching how the
    # "different session" test above simulates a hand-edited pointer.
    pointer_path = main_root / ".shipwright" / "iterate_active" / "sess-1.json"
    data = json.loads(pointer_path.read_text(encoding="utf-8"))
    data["worktree_path"] = ""
    pointer_path.write_text(json.dumps(data), encoding="utf-8")

    assert pointer_worktree_root(main_root, "sess-1") is None


def test_pointer_worktree_root_returns_none_when_worktree_is_gone(tmp_path: Path):
    main_root = tmp_path / "main"
    _init_main(main_root)
    write_run_pointer(
        main_root, run_id="run-a", slug="demo", branch="demo",
        worktree_path=main_root / ".worktrees" / "never-created", session_id="sess-1",
    )
    assert pointer_worktree_root(main_root, "sess-1") is None


def test_pointer_worktree_root_swallows_an_unexpected_exception(tmp_path: Path, monkeypatch):
    """Best-effort per its own docstring: any unexpected failure inside the
    resolution chain falls back to None rather than raising past the caller,
    which runs this inside its own per-invocation try in the Stop hook."""
    import lib.phase_quality._run_id as run_id_mod

    main_root = tmp_path / "main"
    _init_main(main_root)

    def boom(*_args, **_kwargs):
        raise RuntimeError("simulated failure")

    monkeypatch.setattr(run_id_mod.worktree_isolation, "read_run_pointer", boom)
    assert pointer_worktree_root(main_root, "sess-1") is None


def test_resolves_a_genuine_worktree_located_outside_main_roots_own_tree(tmp_path: Path):
    """D5 (doubt-review): git has no requirement that a linked worktree live
    under its main repo's own directory — `git worktree add` accepts any
    path. A prior `relative_to(main_root)` containment pre-check would have
    silently rejected this genuine worktree with no diagnostic; is_worktree_of
    alone (gitdir-chain identity) is the real proof and must accept it."""
    main_root = tmp_path / "main"
    _init_main(main_root)
    worktree = tmp_path / "elsewhere" / "demo"  # sibling of main_root, not under it
    subprocess.run(["git", "worktree", "add", "-q", "-b", "demo", str(worktree)],
                    cwd=str(main_root), check=True)
    write_run_pointer(
        main_root, run_id="run-a", slug="demo", branch="demo",
        worktree_path=worktree, session_id="sess-1",
    )
    assert pointer_worktree_root(main_root, "sess-1") == worktree.resolve()


def test_is_worktree_of_resolves_a_relative_gitdir_against_the_worktree(tmp_path: Path):
    """git >= 2.48's `worktree.useRelativePaths` / `--relative-paths` writes
    a relative `gitdir:` line (e.g. `../../.git/worktrees/x`). It must
    resolve against the WORKTREE directory (the file that names it), not the
    process cwd — resolving against cwd would silently fail every
    relative-gitdir worktree closed, reverting to the pre-fix behaviour with
    no diagnostic (external review, round 3)."""
    main_root = tmp_path / "main"
    _init_main(main_root)
    worktree = main_root / ".worktrees" / "demo"
    gitdir = main_root / ".git" / "worktrees" / "demo"
    gitdir.mkdir(parents=True)
    worktree.mkdir(parents=True)
    (worktree / ".git").write_text("gitdir: ../../.git/worktrees/demo\n", encoding="utf-8")
    (gitdir / "gitdir").write_text(str(worktree / ".git"), encoding="utf-8")

    assert is_worktree_of(worktree.resolve(), main_root.resolve()) is True


def test_is_worktree_of_resolves_a_relative_back_link_against_the_admin_dir(tmp_path: Path):
    """Doubt-review delta pass: `useRelativePaths` writes BOTH `gitdir:`
    lines relative — the admin dir's back-link too, not only the worktree's
    forward link the sibling test above covers (which wrote its back-link
    ABSOLUTELY and so could not catch this). Resolving the back-link against
    the process cwd instead of `gitdir` — the file that names it — would
    silently reject this genuine worktree, reverting to the pre-fix
    behaviour with no diagnostic, exactly the failure class the forward-link
    fix was already hardened against."""
    import os

    main_root = tmp_path / "main"
    _init_main(main_root)
    worktree = main_root / ".worktrees" / "demo"
    gitdir = main_root / ".git" / "worktrees" / "demo"
    gitdir.mkdir(parents=True)
    worktree.mkdir(parents=True)
    (worktree / ".git").write_text("gitdir: ../../.git/worktrees/demo\n", encoding="utf-8")
    relative_back_link = os.path.relpath(worktree / ".git", start=gitdir)
    (gitdir / "gitdir").write_text(relative_back_link, encoding="utf-8")

    assert is_worktree_of(worktree.resolve(), main_root.resolve()) is True


def test_rejects_a_gitdir_naming_the_worktrees_container_itself(tmp_path: Path):
    """D-review (code review, Stage-2 delta pass): `relative_to` alone accepts
    EQUALITY, and `.git/worktrees` is a real directory once main has ever had
    one worktree — a hand-written `.git` FILE reading `gitdir: <main>/.git/
    worktrees` (the container, not an admin dir under it) would otherwise
    pass the identity check and redirect the Stop audit into an attacker-
    controlled directory."""
    main_root = tmp_path / "main"
    _init_main(main_root)
    worktree = main_root / ".worktrees" / "demo"
    subprocess.run(["git", "worktree", "add", "-q", "-b", "other", str(main_root / ".worktrees" / "other")],
                    cwd=str(main_root), check=True)
    worktree.mkdir(parents=True)
    worktrees_root = main_root / ".git" / "worktrees"
    (worktree / ".git").write_text(f"gitdir: {worktrees_root}\n", encoding="utf-8")

    assert is_worktree_of(worktree.resolve(), main_root.resolve()) is False


def test_rejects_a_gitdir_naming_a_different_worktrees_own_admin_dir(tmp_path: Path):
    """A `.git` FILE reading `gitdir: <main>/.git/worktrees/<other>` names a
    GENUINE admin dir — but of a DIFFERENT worktree. `gitdir.parent ==
    worktrees_root` alone would accept it; only the git-authored back-link
    (`<admin-dir>/gitdir` naming the linked worktree's OWN `.git` file) proves
    the pairing is mutual rather than merely a directory that exists."""
    main_root = tmp_path / "main"
    _init_main(main_root)
    other = main_root / ".worktrees" / "other"
    subprocess.run(["git", "worktree", "add", "-q", "-b", "other", str(other)],
                    cwd=str(main_root), check=True)
    spoofed = main_root / ".worktrees" / "spoofed"
    spoofed.mkdir(parents=True)
    (spoofed / ".git").write_text(
        f"gitdir: {main_root / '.git' / 'worktrees' / 'other'}\n", encoding="utf-8",
    )

    assert is_worktree_of(spoofed.resolve(), main_root.resolve()) is False
