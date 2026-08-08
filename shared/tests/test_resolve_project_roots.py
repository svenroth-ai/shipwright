"""Direct unit coverage for ``lib.phase_quality.resolve_project_roots``.

Code-review follow-up (D1 delta): the three branches were previously only
exercised indirectly through hook subprocess E2E tests, which this repo's
diff-coverage gate scores as uncovered (ADR-045). These call the function
directly, including the one case the E2E tests could not reach at all: an
explicit ``SHIPWRIGHT_PROJECT_ROOT`` opt-in with a pointer ALSO present —
the exact collision `resolve_project_roots`'s priority order exists for.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from lib.phase_quality._resolution import resolve_project_roots
from lib.worktree_isolation import write_run_pointer


def _init_main(main_root: Path) -> None:
    main_root.mkdir(parents=True, exist_ok=True)
    (main_root / "shipwright_run_config.json").write_text(
        json.dumps({"status": "complete", "run_id": "run-a"}), encoding="utf-8",
    )
    subprocess.run(["git", "init", "-q"], cwd=str(main_root), check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"],
                    cwd=str(main_root), check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=str(main_root), check=True)
    subprocess.run(["git", "add", "-A"], cwd=str(main_root), check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=str(main_root), check=True)


def test_no_env_no_pointer_returns_plain_root_for_all_three(tmp_path: Path, monkeypatch):
    _init_main(tmp_path)
    # resolve_project_root() reads the REAL process cwd, not the `cwd`
    # parameter — matching production, where the hook always derives `cwd`
    # from Path.cwd() itself right before this call.
    monkeypatch.chdir(tmp_path)
    audit_root, via_pointer, plain_root = resolve_project_roots(tmp_path, "sess-1")
    assert audit_root == plain_root == tmp_path.resolve()
    assert via_pointer is False


def test_no_env_valid_pointer_redirects_audit_root_only(tmp_path: Path, monkeypatch):
    main_root = tmp_path / "main"
    _init_main(main_root)
    worktree = main_root / ".worktrees" / "demo"
    subprocess.run(["git", "worktree", "add", "-q", "-b", "demo", str(worktree)],
                    cwd=str(main_root), check=True)
    (worktree / "shipwright_run_config.json").write_text(
        json.dumps({"status": "complete", "run_id": "run-a"}), encoding="utf-8",
    )
    write_run_pointer(
        main_root, run_id="run-a", slug="demo", branch="demo",
        worktree_path=worktree, session_id="sess-1",
    )
    monkeypatch.chdir(main_root)  # a Stop-subprocess's cwd is MAIN, even mid-iterate

    audit_root, via_pointer, plain_root = resolve_project_roots(main_root, "sess-1")

    assert audit_root == worktree.resolve()
    assert plain_root == main_root.resolve()
    assert via_pointer is True
    assert audit_root != plain_root


def test_env_wins_over_a_present_pointer(tmp_path: Path, monkeypatch):
    """The exact collision the priority order exists for: an explicit
    SHIPWRIGHT_PROJECT_ROOT opt-in must not be silently outranked by a
    pointer that ALSO resolves — the hook subprocess E2E tests only ever
    exercise env-set-with-no-pointer, never this."""
    main_root = tmp_path / "main"
    _init_main(main_root)
    worktree = main_root / ".worktrees" / "demo"
    subprocess.run(["git", "worktree", "add", "-q", "-b", "demo", str(worktree)],
                    cwd=str(main_root), check=True)
    (worktree / "shipwright_run_config.json").write_text(
        json.dumps({"status": "complete", "run_id": "run-a"}), encoding="utf-8",
    )
    write_run_pointer(
        main_root, run_id="run-a", slug="demo", branch="demo",
        worktree_path=worktree, session_id="sess-1",
    )
    monkeypatch.setenv("SHIPWRIGHT_PROJECT_ROOT", str(main_root))
    monkeypatch.chdir(main_root)

    audit_root, via_pointer, plain_root = resolve_project_roots(main_root, "sess-1")

    assert audit_root == plain_root == main_root.resolve()
    assert via_pointer is False


def test_resolve_project_root_failure_falls_back_to_cwd(tmp_path: Path, monkeypatch):
    """A multi-candidate monorepo makes the plain resolver raise ValueError
    (its own documented failure mode). `resolve_project_roots` must not
    propagate that past the Stop hook — it falls back to `cwd` itself."""
    import lib.phase_quality._resolution as resolution_mod

    _init_main(tmp_path)
    monkeypatch.chdir(tmp_path)

    def boom():
        raise ValueError("ambiguous: multiple shipwright_run_config.json candidates")

    monkeypatch.setattr(resolution_mod, "resolve_project_root", boom)

    audit_root, via_pointer, plain_root = resolve_project_roots(tmp_path, "sess-1")

    assert plain_root == tmp_path
    assert audit_root == tmp_path
    assert via_pointer is False
