"""Unit tests for ``lib.run_pointer_retirement``.

Covers the F11 pointer-retirement fix (trg-276994a4): a retained post-merge
worktree keeps ``pointer_run_id`` resolving a FINISHED run's id for the rest
of the session, because liveness was inferred from the worktree directory
alone. Retirement gives the pointer an explicit end-of-run signal instead.
"""

from __future__ import annotations

import json
from pathlib import Path

from lib.phase_quality._run_id import pointer_run_id
from lib.run_pointer_retirement import retire_run_pointer, retire_run_pointer_best_effort
from lib.worktree_isolation import ACTIVE_POINTER_DIRNAME, read_run_pointer, write_run_pointer


def test_retirement_stops_pointer_run_id_resolving_a_retained_worktree(tmp_path: Path):
    """The actual defect (trg-276994a4): a worktree directory that is still
    on disk (retained after merge, as this repo does) must stop being
    resolvable via the pointer once the run is retired — proving retirement
    changes the outcome, not just that a file was deleted."""
    worktree = tmp_path / ".worktrees" / "a"
    worktree.mkdir(parents=True)
    write_run_pointer(
        tmp_path, run_id="run-a", slug="a", branch="iterate/a",
        worktree_path=worktree, session_id="sess-a",
    )
    assert pointer_run_id(tmp_path, "sess-a") == "run-a"

    assert retire_run_pointer(tmp_path, "run-a") is True

    assert worktree.is_dir()  # retained, exactly as in production
    assert pointer_run_id(tmp_path, "sess-a") is None


def test_retire_run_pointer_unlinks_when_run_id_matches(tmp_path: Path):
    write_run_pointer(
        tmp_path, run_id="run-a", slug="a", branch="iterate/a",
        worktree_path=tmp_path / ".worktrees" / "a", session_id="sess-a",
    )
    assert retire_run_pointer(tmp_path, "run-a") is True
    assert read_run_pointer(tmp_path, "sess-a") is None


def test_retire_run_pointer_leaves_a_later_runs_pointer_alone(tmp_path: Path):
    """A session that finished run A and then started run B (same session id,
    same pointer path) must not have B's live pointer retired by A's late
    F11 delivery call — retirement matches on the pointer's own recorded
    run_id, not the session slot it happens to be filed under."""
    write_run_pointer(
        tmp_path, run_id="run-b", slug="b", branch="iterate/b",
        worktree_path=tmp_path / ".worktrees" / "b", session_id="sess-a",
    )
    assert retire_run_pointer(tmp_path, "run-a") is False
    ptr = read_run_pointer(tmp_path, "sess-a")
    assert ptr is not None
    assert ptr["run_id"] == "run-b"


def test_retire_run_pointer_normalizes_whitespace(tmp_path: Path):
    """Matches pointer_run_id's own normalization (it .strip()s the payload's
    run_id) — a whitespace-padded id must not silently fail to match."""
    write_run_pointer(
        tmp_path, run_id="run-a", slug="a", branch="iterate/a",
        worktree_path=tmp_path / ".worktrees" / "a", session_id="sess-a",
    )
    assert retire_run_pointer(tmp_path, "  run-a  ") is True
    assert read_run_pointer(tmp_path, "sess-a") is None


def test_retire_run_pointer_no_op_when_absent(tmp_path: Path):
    assert retire_run_pointer(tmp_path, "run-a") is False


def test_retire_run_pointer_no_op_on_blank_run_id(tmp_path: Path):
    write_run_pointer(
        tmp_path, run_id="run-a", slug="a", branch="iterate/a",
        worktree_path=tmp_path / ".worktrees" / "a", session_id="sess-a",
    )
    assert retire_run_pointer(tmp_path, "") is False
    assert read_run_pointer(tmp_path, "sess-a") is not None


def test_retire_run_pointer_no_op_on_corrupt_pointer(tmp_path: Path):
    target = tmp_path / ".shipwright" / ACTIVE_POINTER_DIRNAME / "sess-a.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("not json", encoding="utf-8")
    assert retire_run_pointer(tmp_path, "run-a") is False
    assert target.exists()


def test_retire_run_pointer_ignores_a_stray_non_pointer_json(tmp_path: Path):
    """A non-pointer JSON file that happens to carry a matching run_id field
    (external review: e.g. a stray config dump) must not be deleted just
    because that one key collides — a real pointer also carries
    worktree_path."""
    target = tmp_path / ".shipwright" / ACTIVE_POINTER_DIRNAME / "not-a-pointer.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps({"run_id": "run-a", "note": "unrelated"}), encoding="utf-8")
    assert retire_run_pointer(tmp_path, "run-a") is False
    assert target.exists()


def test_retire_run_pointer_unlinks_every_matching_pointer(tmp_path: Path):
    """Two pointer files can legitimately name the same run_id (a resumed
    iterate driven from a second session writes a second, differently-keyed
    pointer) — retirement must not stop at the first match, or the second
    file leaves the original defect live for whichever session owns it."""
    write_run_pointer(
        tmp_path, run_id="run-a", slug="a", branch="iterate/a",
        worktree_path=tmp_path / ".worktrees" / "a", session_id="sess-a",
    )
    write_run_pointer(
        tmp_path, run_id="run-a", slug="a", branch="iterate/a",
        worktree_path=tmp_path / ".worktrees" / "a", session_id="sess-b",
    )
    assert retire_run_pointer(tmp_path, "run-a") is True
    assert read_run_pointer(tmp_path, "sess-a") is None
    assert read_run_pointer(tmp_path, "sess-b") is None


def test_retire_run_pointer_recheck_survives_a_same_session_overwrite_race(
    tmp_path: Path, monkeypatch,
) -> None:
    """D3 (doubt-review): the pointer filename is session_id-keyed, so a
    same-session write landing between the match and the unlink (e.g. a
    campaign's next sub-iterate) could otherwise delete a brand-new pointer
    for a DIFFERENT run under the OLD run's name. Simulated by overwriting
    the file's content, via the real write path, right as the function's own
    re-check reads it a second time — proving the re-check catches it."""
    target = write_run_pointer(
        tmp_path, run_id="run-a", slug="a", branch="iterate/a",
        worktree_path=tmp_path / ".worktrees" / "a", session_id="sess-a",
    )
    calls = {"n": 0}
    real_read_text = Path.read_text

    def fake_read_text(self: Path, *args, **kwargs):
        if self == target:
            calls["n"] += 1
            if calls["n"] == 2:
                write_run_pointer(
                    tmp_path, run_id="run-b", slug="b", branch="iterate/b",
                    worktree_path=tmp_path / ".worktrees" / "b", session_id="sess-a",
                )
        return real_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", fake_read_text)

    assert retire_run_pointer(tmp_path, "run-a") is False
    ptr = read_run_pointer(tmp_path, "sess-a")
    assert ptr is not None
    assert ptr["run_id"] == "run-b"  # the new pointer survived, not deleted


def test_retire_run_pointer_recheck_swallows_a_corrupt_read(tmp_path: Path, monkeypatch) -> None:
    """The recheck read (D3) can itself land mid-write and see truncated or
    invalid JSON — that must be treated as 'no longer a confirmed match'
    (skip this file), not raise past the caller."""
    target = write_run_pointer(
        tmp_path, run_id="run-a", slug="a", branch="iterate/a",
        worktree_path=tmp_path / ".worktrees" / "a", session_id="sess-a",
    )
    calls = {"n": 0}
    real_read_text = Path.read_text

    def fake_read_text(self: Path, *args, **kwargs):
        if self == target:
            calls["n"] += 1
            if calls["n"] == 2:
                return "{not valid json"
        return real_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", fake_read_text)

    assert retire_run_pointer(tmp_path, "run-a") is False
    assert read_run_pointer(tmp_path, "sess-a") is not None


def test_retire_run_pointer_prints_diagnostic_when_unlink_fails(
    tmp_path: Path, monkeypatch, capsys,
) -> None:
    """A per-file unlink failure (external review: e.g. a permission error)
    must be printed to stderr and skipped, not raised past the caller — a
    PARTIAL retirement must never be indistinguishable from a clean success."""
    target = write_run_pointer(
        tmp_path, run_id="run-a", slug="a", branch="iterate/a",
        worktree_path=tmp_path / ".worktrees" / "a", session_id="sess-a",
    )
    real_unlink = Path.unlink

    def fake_unlink(self: Path, *args, **kwargs):
        if self == target:
            raise OSError("simulated permission error")
        return real_unlink(self, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", fake_unlink)

    assert retire_run_pointer(tmp_path, "run-a") is False
    err = capsys.readouterr().err
    assert "could not unlink" in err
    assert "run_id='run-a'" in err
    assert read_run_pointer(tmp_path, "sess-a") is not None


def test_best_effort_unlinks_the_pointer(tmp_path: Path):
    write_run_pointer(
        tmp_path, run_id="run-x", slug="x", branch="iterate/x",
        worktree_path=tmp_path / ".worktrees" / "x", session_id="sess-x",
    )
    assert retire_run_pointer_best_effort(tmp_path, "run-x") is True
    assert read_run_pointer(tmp_path, "sess-x") is None


def test_best_effort_prints_diagnostic_when_nothing_matches(tmp_path: Path, capsys):
    assert retire_run_pointer_best_effort(tmp_path, "run-x") is False
    assert "run_id='run-x'" in capsys.readouterr().err


def test_best_effort_swallows_errors(tmp_path: Path, monkeypatch, capsys):
    """Code review, delta pass: the prior version of this test asserted
    `False` via `resolve_main_repo_root` returning `None` on a nonexistent
    path — the NORMAL no-match path (`glob` on a missing dir yields nothing),
    identical to `test_retire_run_pointer_no_op_when_absent`. It would stay
    green with the `except Exception` block deleted. Raise from inside the
    try body instead, to actually pin that a genuine failure is swallowed."""
    import lib.run_pointer_retirement as rpr

    def boom(*_args, **_kwargs):
        raise OSError("simulated failure")

    monkeypatch.setattr(rpr, "retire_run_pointer", boom)
    assert retire_run_pointer_best_effort(tmp_path, "run-x") is False
    assert "pointer retirement failed" in capsys.readouterr().err
