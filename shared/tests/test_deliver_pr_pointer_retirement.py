"""F11 pointer retirement wiring (trg-276994a4).

``deliver_pr.py`` is the run's own definition of "finished" — DELIVERED means
MERGED + green. This is where ``lib.run_pointer_retirement`` is invoked, so a
retained post-merge worktree stops making ``phase_quality.pointer_run_id``
resolve a finished run for the rest of the session. These tests exercise only
the `main()` wiring — does it call the retirement helper with the right args,
and only on a DELIVERED exit — not the retirement logic itself (unit-tested
in ``test_run_pointer_retirement.py``) nor the full ladder (end-to-end in
``test_deliver_pr.py`` with a faked host).
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))

from tools import deliver_pr  # noqa: E402
from tools.deliver_pr import EXIT_CLOSED, EXIT_DELIVERED, EXIT_PENDING  # noqa: E402

PR = "https://github.com/o/r/pull/7"
REPO = "o/r"
HEAD = "iterate/slug"
BASE = "main"


def _argv(project_root: Path, *, run_id: str = "run-x") -> list[str]:
    return [
        "--pr", PR, "--repo", REPO, "--project-root", str(project_root),
        "--run-id", run_id, "--head-branch", HEAD, "--base-branch", BASE,
    ]


def test_main_retires_the_pointer_only_when_delivered(monkeypatch, tmp_path: Path):
    calls: list[tuple] = []
    monkeypatch.setattr(
        deliver_pr, "deliver",
        lambda *a, **k: {"exit_code": EXIT_DELIVERED, "status": "delivered", "steps": []},
    )
    monkeypatch.setattr(
        deliver_pr, "retire_run_pointer_best_effort",
        lambda root, run_id: calls.append((root, run_id)),
    )
    rc = deliver_pr.main(_argv(tmp_path, run_id="run-x"))
    assert rc == EXIT_DELIVERED
    assert calls == [(tmp_path.resolve(), "run-x")]


def test_main_retires_the_pointer_when_closed_unmerged(monkeypatch, tmp_path: Path):
    """A CLOSED-unmerged PR ends the run just as definitively as a merge —
    the original defect (a retained worktree keeps the pointer resolving a
    finished run) applies equally here."""
    calls: list[tuple] = []
    monkeypatch.setattr(
        deliver_pr, "deliver",
        lambda *a, **k: {"exit_code": EXIT_CLOSED, "status": "closed", "steps": []},
    )
    monkeypatch.setattr(
        deliver_pr, "retire_run_pointer_best_effort",
        lambda root, run_id: calls.append((root, run_id)),
    )
    rc = deliver_pr.main(_argv(tmp_path, run_id="run-x"))
    assert rc == EXIT_CLOSED
    assert calls == [(tmp_path.resolve(), "run-x")]


def test_main_does_not_retire_the_pointer_when_not_delivered(monkeypatch, tmp_path: Path):
    calls: list[tuple] = []
    monkeypatch.setattr(
        deliver_pr, "deliver",
        lambda *a, **k: {"exit_code": EXIT_PENDING, "status": "pending", "steps": []},
    )
    monkeypatch.setattr(
        deliver_pr, "retire_run_pointer_best_effort",
        lambda *a: calls.append(a),
    )
    rc = deliver_pr.main(_argv(tmp_path))
    assert rc == EXIT_PENDING
    assert calls == []
