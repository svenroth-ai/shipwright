"""Wave-scoped identity collision safety for ``pointer_worktree_root``.

Distinct from ``test_pointer_worktree_root_identity.py``'s genuine-linked-
worktree verification: these tests cover what happens when several units in
one campaign wave share a single session-keyed pointer file.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from lib.phase_quality._run_id import pointer_worktree_root
from lib.worktree_isolation import write_run_pointer


def _init_main(main_root: Path) -> None:
    main_root.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=str(main_root), check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"],
                    cwd=str(main_root), check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=str(main_root), check=True)
    subprocess.run(["git", "commit", "--allow-empty", "-q", "-m", "init"],
                    cwd=str(main_root), check=True)


def test_a_wave_unit_never_inherits_a_siblings_shared_session_pointer(tmp_path: Path):
    """R5a code review round 3, HIGH: ``mark_implementation_span.py`` calls
    this with ``cwd = Path.cwd()`` — the CALLING unit's own per-unit
    worktree during a campaign wave, not `main_root`. Every unit in a wave
    shares one `session_id`, so the shared pointer can name a SIBLING's
    (also genuinely live, genuinely linked) worktree. Querying from unit A's
    own worktree must not redirect into unit B's."""
    main_root = tmp_path / "main"
    _init_main(main_root)
    wt_a = main_root / ".worktrees" / "campaign-mydag--R5a"
    wt_b = main_root / ".worktrees" / "campaign-mydag--R5b"
    subprocess.run(["git", "worktree", "add", "-q", "-b", "unit-a", str(wt_a)],
                    cwd=str(main_root), check=True)
    subprocess.run(["git", "worktree", "add", "-q", "-b", "unit-b", str(wt_b)],
                    cwd=str(main_root), check=True)
    # Simulates the real race: B's setup call landed last, overwriting the
    # one pointer file (same session_id) both units share.
    write_run_pointer(
        main_root, run_id="run-b", slug="campaign-mydag--R5b", branch="unit-b",
        worktree_path=wt_b, session_id="sess-1",
    )

    assert pointer_worktree_root(wt_a, "sess-1") is None
    # B, querying from its own correctly-pointed worktree, still gets it.
    assert pointer_worktree_root(wt_b, "sess-1") == wt_b.resolve()


def test_a_shared_root_caller_fails_closed_during_a_wave_rather_than_guessing(
    tmp_path: Path, monkeypatch,
):
    """External Tier-3 PR review, blocking (R5a): a caller rooted at the
    SHARED campaign worktree or main (never itself a per-unit worktree) must
    not silently inherit whichever unit's setup call last overwrote the
    session pointer — even though, unlike the sibling-vs-sibling case above,
    that pointer's OWN worktree is genuinely live and genuinely linked, so
    every other check here would happily accept it. The wave sentinel being
    set is what must gate this shut: nothing about `main_root` itself looks
    wrong on its own."""
    main_root = tmp_path / "main"
    _init_main(main_root)
    wt_b = main_root / ".worktrees" / "campaign-mydag--R5b"
    subprocess.run(["git", "worktree", "add", "-q", "-b", "unit-b", str(wt_b)],
                    cwd=str(main_root), check=True)
    write_run_pointer(
        main_root, run_id="run-b", slug="campaign-mydag--R5b", branch="unit-b",
        worktree_path=wt_b, session_id="sess-1",
    )

    # Outside a wave (no sentinel set), main_root is a perfectly ordinary
    # caller and the existing pointer resolves normally.
    monkeypatch.delenv("SHIPWRIGHT_LOOP_UNIT_ID", raising=False)
    assert pointer_worktree_root(main_root, "sess-1") == wt_b.resolve()

    # During a wave, the SAME call from the SAME root must fail closed.
    monkeypatch.setenv("SHIPWRIGHT_LOOP_UNIT_ID", "__campaign_wave__")
    assert pointer_worktree_root(main_root, "sess-1") is None
