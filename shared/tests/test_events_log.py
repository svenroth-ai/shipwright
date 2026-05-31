"""Unit tests for shared/scripts/lib/events_log.py.

Exercises worktree-aware resolution of shipwright_events.jsonl against a
REAL ``git worktree`` layout (not mocks) — per external review the
common-dir math must be verified on an actual linked worktree.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from lib.events_log import (
    EVENT_FILE,
    latest_event_dt,
    resolve_events_path,
    resolve_main_repo_root,
)

# Linked worktrees are created via the shared ``make_worktree`` fixture
# (shared/tests/conftest.py).


def test_main_repo_identity(git_origin_repo):
    """In the main repo the resolved path is project_root / EVENT_FILE."""
    work, _ = git_origin_repo
    resolved = resolve_events_path(work)
    assert resolved.resolve() == (work / EVENT_FILE).resolve()


def test_worktree_resolves_to_worktree_local(git_origin_repo, make_worktree):
    """From inside a linked worktree the log resolves to the WORKTREE's own
    copy — events.jsonl is a per-tree, PR-committed artifact (F6 stages it,
    it merges to main via the PR). It is NOT redirected to the main repo.

    Inverted by iterate-2026-05-29-events-jsonl-worktree-commit: the old
    main-repo redirect left the work_completed event uncommitted in the main
    tree, never entering the iterate PR."""
    work, _ = git_origin_repo
    wt = make_worktree(work, "probe")
    resolved = resolve_events_path(wt)
    assert resolved.resolve() == (wt / EVENT_FILE).resolve()
    assert resolved.resolve() != (work / EVENT_FILE).resolve()
    # The owning directory is the worktree, not the main repo root.
    assert resolved.parent.resolve() == wt.resolve()


def test_worktree_nested_path_resolved(git_origin_repo, make_worktree):
    """A worktree several levels under .worktrees/ resolves to its own local
    copy (no git-common-dir math involved any more — the resolver is a literal
    join)."""
    work, _ = git_origin_repo
    wt = make_worktree(work, "deep-slug")
    resolved = resolve_events_path(wt)
    assert resolved.resolve() == (wt / EVENT_FILE).resolve()


def test_non_git_dir_returns_local(tmp_path, recwarn):
    """A non-git directory resolves to project_root/EVENT_FILE, silently.

    Since iterate-2026-05-29-events-jsonl-worktree-commit ``resolve_events_path``
    is a literal join and never consults git, so a non-git dir is the same
    answer as everywhere else — and never warns."""
    resolved = resolve_events_path(tmp_path)
    assert resolved == tmp_path / EVENT_FILE
    assert len(recwarn) == 0


def test_resolve_events_path_is_git_independent(tmp_path, monkeypatch, recwarn):
    """``resolve_events_path`` no longer calls git at all — the log is a
    per-tree artifact, so the path is always ``project_root / EVENT_FILE``.

    Even with a hard-broken git binary the resolver returns the local path
    and emits NO warning (the git-resolution + its diagnostics now live ONLY
    in ``resolve_main_repo_root``, used by the decision-drop resolver). This
    pins that the events resolver is decoupled from git."""
    def _boom(*_args, **_kwargs):
        raise OSError("git: command not found — must never be reached")

    monkeypatch.setattr(subprocess, "run", _boom)
    resolved = resolve_events_path(tmp_path)
    assert resolved == tmp_path / EVENT_FILE
    assert len(recwarn) == 0


def test_main_repo_root_git_discovery_env_overrides_are_stripped(git_origin_repo, monkeypatch):
    """GIT_DIR / GIT_COMMON_DIR / GIT_WORK_TREE must NOT leak into the git
    invocation in ``resolve_main_repo_root`` (the decision-drop primitive) —
    otherwise resolution silently targets a different repo."""
    work, _ = git_origin_repo
    bogus = str(work / "bogus.git")
    monkeypatch.setenv("GIT_DIR", bogus)
    monkeypatch.setenv("GIT_COMMON_DIR", bogus)
    monkeypatch.setenv("GIT_WORK_TREE", str(work / "bogus-tree"))
    # With the overrides stripped, resolution still pins to `work`.
    assert resolve_main_repo_root(work).resolve() == work.resolve()


def test_str_project_root_accepted(git_origin_repo):
    """Accepts a str project_root, not only a Path."""
    work, _ = git_origin_repo
    resolved = resolve_events_path(str(work))
    assert resolved.resolve() == (work / EVENT_FILE).resolve()


# ---------------------------------------------------------------------------
# resolve_main_repo_root — the generic git-worktree-aware primitive that both
# resolve_events_path and write_decision_drop.drop_dir derive from.
# ---------------------------------------------------------------------------


def test_main_repo_root_plain_repo(git_origin_repo):
    """In a plain checkout the main-repo root is the repo root itself."""
    work, _ = git_origin_repo
    assert resolve_main_repo_root(work).resolve() == work.resolve()


def test_main_repo_root_from_worktree(git_origin_repo, make_worktree):
    """From inside a linked worktree it resolves to the MAIN repo root —
    NOT the ephemeral worktree that `git worktree remove` discards."""
    work, _ = git_origin_repo
    wt = make_worktree(work, "mrr-probe")
    assert resolve_main_repo_root(wt).resolve() == work.resolve()


def test_main_repo_root_non_git_returns_none_silently(tmp_path, recwarn):
    """A non-git directory yields None SILENTLY — `git rev-parse` returncode
    != 0 is a definitive 'not a repo', so callers fall back without a warning
    that would spam every non-git project."""
    assert resolve_main_repo_root(tmp_path) is None
    assert len(recwarn) == 0


def test_main_repo_root_git_unavailable_warns_then_none(tmp_path, monkeypatch):
    """A broken/absent git binary warns before returning None — silent data
    loss in a worktree run must stay visible. Exactly one diagnostic — a
    second would mean a duplicated warn path."""
    def _boom(*_args, **_kwargs):
        raise OSError("git: command not found")

    monkeypatch.setattr(subprocess, "run", _boom)
    with pytest.warns(UserWarning, match="git unavailable") as rec:
        assert resolve_main_repo_root(tmp_path) is None
    assert len(rec) == 1


def test_main_repo_root_str_project_root_accepted(git_origin_repo):
    """Accepts a str project_root, not only a Path."""
    work, _ = git_origin_repo
    assert resolve_main_repo_root(str(work)).resolve() == work.resolve()


# ---------------------------------------------------------------------------
# latest_event_dt — deterministic substitute for `datetime.now()` in render
# banners (iterate-2026-05-22-deterministic-render-timestamps).
# ---------------------------------------------------------------------------


def _write_events_jsonl(project_root: Path, lines: list[str]) -> None:
    """Write raw lines to the project's events.jsonl (newline-joined)."""
    path = project_root / EVENT_FILE
    path.write_text(("\n".join(lines) + "\n") if lines else "", encoding="utf-8")


def test_latest_event_dt_returns_none_when_log_missing(tmp_path: Path) -> None:
    """Brand-new project: no events.jsonl yet → None."""
    assert latest_event_dt(tmp_path) is None


def test_latest_event_dt_returns_none_when_log_empty(tmp_path: Path) -> None:
    """Existing-but-empty events.jsonl → None."""
    (tmp_path / EVENT_FILE).write_text("", encoding="utf-8")
    assert latest_event_dt(tmp_path) is None


def test_latest_event_dt_single_event(tmp_path: Path) -> None:
    """One event → its ts, parsed to UTC."""
    import json
    _write_events_jsonl(tmp_path, [
        json.dumps({"type": "x", "ts": "2026-05-20T12:00:00+00:00"}),
    ])
    from datetime import datetime, timezone
    dt = latest_event_dt(tmp_path)
    assert dt is not None
    assert dt == datetime(2026, 5, 20, 12, 0, 0, tzinfo=timezone.utc)


def test_latest_event_dt_multiple_events_returns_max(tmp_path: Path) -> None:
    """Multiple events → the chronologically-latest one."""
    import json
    _write_events_jsonl(tmp_path, [
        json.dumps({"type": "x", "ts": "2026-05-20T12:00:00+00:00"}),
        json.dumps({"type": "y", "ts": "2026-05-22T03:30:00+00:00"}),
        json.dumps({"type": "z", "ts": "2026-05-21T09:15:00+00:00"}),
    ])
    from datetime import datetime, timezone
    dt = latest_event_dt(tmp_path)
    assert dt == datetime(2026, 5, 22, 3, 30, 0, tzinfo=timezone.utc)


def test_latest_event_dt_handles_z_suffix(tmp_path: Path) -> None:
    """`Z` and `+00:00` suffixes both work and compare correctly."""
    import json
    _write_events_jsonl(tmp_path, [
        json.dumps({"type": "x", "ts": "2026-05-20T12:00:00Z"}),
        json.dumps({"type": "y", "ts": "2026-05-22T03:30:00+00:00"}),
    ])
    from datetime import datetime, timezone
    dt = latest_event_dt(tmp_path)
    assert dt == datetime(2026, 5, 22, 3, 30, 0, tzinfo=timezone.utc)


def test_latest_event_dt_handles_non_utc_offset(tmp_path: Path) -> None:
    """Mixed-timezone offsets are correctly ordered by instant, not by
    lexicographic comparison of the timestamp string.

    Lex-max would pick "2026-05-22T08:00:00+02:00" (later string) but
    "2026-05-22T07:30:00Z" is actually the later instant (08:00 CEST
    == 06:00 UTC, which is earlier than 07:30 UTC). The helper must
    parse-then-compare-as-datetime, not bare-string-max.
    """
    import json
    _write_events_jsonl(tmp_path, [
        # 06:00 UTC instant — string compares lex-largest
        json.dumps({"type": "x", "ts": "2026-05-22T08:00:00+02:00"}),
        # 07:30 UTC instant — chronologically later
        json.dumps({"type": "y", "ts": "2026-05-22T07:30:00Z"}),
    ])
    from datetime import datetime, timezone
    dt = latest_event_dt(tmp_path)
    assert dt == datetime(2026, 5, 22, 7, 30, 0, tzinfo=timezone.utc), (
        f"Expected the +02:00 event (06:00 UTC instant) to lose to the "
        f"07:30Z event (07:30 UTC instant), but got {dt!r}. "
        f"Likely cause: lexicographic max instead of datetime comparison."
    )


def test_latest_event_dt_skips_corrupt_lines(tmp_path: Path) -> None:
    """A malformed JSON line in the middle of the log doesn't kill resolution."""
    import json
    _write_events_jsonl(tmp_path, [
        json.dumps({"type": "x", "ts": "2026-05-20T12:00:00+00:00"}),
        "{not valid json",  # corrupt
        json.dumps({"type": "z", "ts": "2026-05-22T03:30:00+00:00"}),
    ])
    from datetime import datetime, timezone
    dt = latest_event_dt(tmp_path)
    assert dt == datetime(2026, 5, 22, 3, 30, 0, tzinfo=timezone.utc)


def test_latest_event_dt_skips_lines_without_ts(tmp_path: Path) -> None:
    """Lines lacking a `ts` field are silently skipped."""
    import json
    _write_events_jsonl(tmp_path, [
        json.dumps({"type": "x"}),  # no ts
        json.dumps({"type": "y", "ts": "2026-05-22T03:30:00+00:00"}),
    ])
    from datetime import datetime, timezone
    dt = latest_event_dt(tmp_path)
    assert dt == datetime(2026, 5, 22, 3, 30, 0, tzinfo=timezone.utc)


def test_latest_event_dt_skips_non_string_ts(tmp_path: Path) -> None:
    """Lines with a non-string `ts` (e.g. a number) are skipped."""
    import json
    _write_events_jsonl(tmp_path, [
        json.dumps({"type": "x", "ts": 1234567890}),
        json.dumps({"type": "y", "ts": "2026-05-20T12:00:00+00:00"}),
    ])
    from datetime import datetime, timezone
    dt = latest_event_dt(tmp_path)
    assert dt == datetime(2026, 5, 20, 12, 0, 0, tzinfo=timezone.utc)


def test_latest_event_dt_skips_unparseable_ts(tmp_path: Path) -> None:
    """Lines with a malformed `ts` string are skipped."""
    import json
    _write_events_jsonl(tmp_path, [
        json.dumps({"type": "x", "ts": "not a real timestamp"}),
        json.dumps({"type": "y", "ts": "2026-05-20T12:00:00+00:00"}),
    ])
    from datetime import datetime, timezone
    dt = latest_event_dt(tmp_path)
    assert dt == datetime(2026, 5, 20, 12, 0, 0, tzinfo=timezone.utc)


def test_latest_event_dt_naive_ts_treated_as_utc(tmp_path: Path) -> None:
    """A `ts` without timezone info is interpreted as UTC (event-log convention)."""
    import json
    _write_events_jsonl(tmp_path, [
        json.dumps({"type": "x", "ts": "2026-05-20T12:00:00"}),
    ])
    from datetime import datetime, timezone
    dt = latest_event_dt(tmp_path)
    assert dt == datetime(2026, 5, 20, 12, 0, 0, tzinfo=timezone.utc)


def test_latest_event_dt_all_corrupt_returns_none(tmp_path: Path) -> None:
    """Every line corrupt → None (graceful degrade)."""
    _write_events_jsonl(tmp_path, [
        "{garbage",
        "more garbage",
    ])
    assert latest_event_dt(tmp_path) is None


def test_latest_event_dt_is_deterministic(tmp_path: Path) -> None:
    """Two calls against the same events.jsonl, separated by wall-clock,
    return identical answers — the whole point of the helper.
    """
    import json
    import time
    _write_events_jsonl(tmp_path, [
        json.dumps({"type": "x", "ts": "2026-05-20T12:00:00+00:00"}),
    ])
    dt_1 = latest_event_dt(tmp_path)
    time.sleep(0.5)
    dt_2 = latest_event_dt(tmp_path)
    assert dt_1 == dt_2
