"""Tests for shared/scripts/hooks/mark_implementation_span.py.

trg-e6d1cc5e follow-up to TC5.1 (PR #617): the 'implementation' iterate-timing
span is agent-prose only (SKILL.md `start implementation` / `end
implementation`) and in practice almost never fires. This hook backstops both
edges from deterministic PostToolUse signals — see the module docstring.
"""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]

sys.path.insert(0, str(Path(__file__).resolve().parent))  # shared/tests (fixtures)
sys.path.insert(0, str(_REPO_ROOT / "shared" / "scripts"))
sys.path.insert(0, str(_REPO_ROOT / "shared" / "scripts" / "hooks"))
sys.path.insert(0, str(_REPO_ROOT / "shared" / "scripts" / "tools"))

import mark_implementation_span as mis  # noqa: E402
import setup_iterate_worktree as siw  # noqa: E402
from lib.iterate_timings_normalize import read_raw_events  # noqa: E402

_SESSION = "sess-impl-test"


def _setup_worktree(work: Path, slug: str, run_id: str) -> Path:
    code, payload = siw.setup(str(work), slug, run_id, session_id=_SESSION)
    assert code == 0, payload
    return Path(payload["project_root"])


def _run_hook(monkeypatch, worktree: Path, payload: dict) -> None:
    monkeypatch.chdir(worktree)
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))
    assert mis.main() == 0


def _write_payload(file_path: str) -> dict:
    return {
        "session_id": _SESSION, "tool_name": "Write",
        "tool_input": {"file_path": file_path, "content": "x"},
    }


def _bash_payload(command: str) -> dict:
    return {
        "session_id": _SESSION, "tool_name": "Bash",
        "tool_input": {"command": command},
    }


_SELF_REVIEW_CMD = (
    'uv run "shared/scripts/tools/record_review_pass.py" record '
    '--run-id iterate-impl --review-type self --status completed '
    '--from none'
)


def test_write_outside_shipwright_starts_implementation(git_origin_repo, monkeypatch):
    work, _ = git_origin_repo
    wt = _setup_worktree(work, "impl1", "iterate-impl1")
    (wt / "src").mkdir(parents=True, exist_ok=True)
    target = wt / "src" / "thing.py"
    target.write_text("x = 1\n", encoding="utf-8")
    _run_hook(monkeypatch, wt, _write_payload(str(target)))
    events = read_raw_events(wt, "iterate-impl1")
    starts = [e for e in events if e.get("event") == "start" and e.get("name") == "implementation"]
    assert len(starts) == 1


def test_write_inside_shipwright_is_ignored(git_origin_repo, monkeypatch):
    work, _ = git_origin_repo
    wt = _setup_worktree(work, "impl2", "iterate-impl2")
    spec = wt / ".shipwright" / "planning" / "iterate" / "spec.md"
    spec.parent.mkdir(parents=True, exist_ok=True)
    spec.write_text("spec\n", encoding="utf-8")
    _run_hook(monkeypatch, wt, _write_payload(str(spec)))
    events = read_raw_events(wt, "iterate-impl2")
    assert not any(e.get("event") == "start" and e.get("name") == "implementation" for e in events)


def test_second_write_does_not_duplicate_start(git_origin_repo, monkeypatch):
    work, _ = git_origin_repo
    wt = _setup_worktree(work, "impl3", "iterate-impl3")
    (wt / "src").mkdir(parents=True, exist_ok=True)
    a = wt / "src" / "a.py"
    b = wt / "src" / "b.py"
    a.write_text("a\n", encoding="utf-8")
    b.write_text("b\n", encoding="utf-8")
    _run_hook(monkeypatch, wt, _write_payload(str(a)))
    _run_hook(monkeypatch, wt, _write_payload(str(b)))
    events = read_raw_events(wt, "iterate-impl3")
    starts = [e for e in events if e.get("event") == "start" and e.get("name") == "implementation"]
    assert len(starts) == 1


def test_self_review_bash_call_ends_implementation_and_starts_review(git_origin_repo, monkeypatch):
    work, _ = git_origin_repo
    wt = _setup_worktree(work, "impl4", "iterate-impl4")
    (wt / "src").mkdir(parents=True, exist_ok=True)
    target = wt / "src" / "thing.py"
    target.write_text("x = 1\n", encoding="utf-8")
    _run_hook(monkeypatch, wt, _write_payload(str(target)))
    _run_hook(monkeypatch, wt, _bash_payload(_SELF_REVIEW_CMD))
    events = read_raw_events(wt, "iterate-impl4")
    assert any(e.get("event") == "end" and e.get("name") == "implementation" for e in events)
    assert any(e.get("event") == "start" and e.get("name") == "review" for e in events)
    assert any(e.get("event") == "start" and e.get("name") == "self_review" for e in events)


def test_self_review_bash_call_without_prior_start_does_not_emit_end(git_origin_repo, monkeypatch):
    work, _ = git_origin_repo
    wt = _setup_worktree(work, "impl5", "iterate-impl5")
    _run_hook(monkeypatch, wt, _bash_payload(_SELF_REVIEW_CMD))
    events = read_raw_events(wt, "iterate-impl5")
    assert not any(e.get("event") == "end" and e.get("name") == "implementation" for e in events)
    # review/self_review still open — self-review recording is unconditional.
    assert any(e.get("event") == "start" and e.get("name") == "review" for e in events)


def test_unrelated_bash_command_is_ignored(git_origin_repo, monkeypatch):
    work, _ = git_origin_repo
    wt = _setup_worktree(work, "impl6", "iterate-impl6")
    _run_hook(monkeypatch, wt, _bash_payload("git status"))
    events = read_raw_events(wt, "iterate-impl6")
    assert events == []


def test_repeated_self_review_bash_call_does_not_duplicate_review_start(git_origin_repo, monkeypatch):
    """First-wins (code review, trg-e6d1cc5e round 2): a prior version only
    guarded the `implementation` end mark, so a second matching Bash call
    (e.g. a resumed run re-invoking record_review_pass.py) re-opened
    `review`/`self_review` a second time."""
    work, _ = git_origin_repo
    wt = _setup_worktree(work, "impl7", "iterate-impl7")
    _run_hook(monkeypatch, wt, _bash_payload(_SELF_REVIEW_CMD))
    _run_hook(monkeypatch, wt, _bash_payload(_SELF_REVIEW_CMD))
    events = read_raw_events(wt, "iterate-impl7")
    review_starts = [e for e in events if e.get("event") == "start" and e.get("name") == "review"]
    self_review_starts = [
        e for e in events if e.get("event") == "start" and e.get("name") == "self_review"
    ]
    assert len(review_starts) == 1
    assert len(self_review_starts) == 1


def test_bash_command_with_self_and_completed_as_substrings_is_not_matched(git_origin_repo, monkeypatch):
    """Value-based matching (code review, trg-e6d1cc5e round 2): a prior
    version matched on raw substrings `"self"`/`"completed"` anywhere in the
    command, false-positiving on values like a `--disposition` note that
    happens to contain those words while the actual `--status` is not
    `completed`."""
    work, _ = git_origin_repo
    wt = _setup_worktree(work, "impl8", "iterate-impl8")
    command = (
        'uv run "shared/scripts/tools/record_review_pass.py" record '
        '--run-id iterate-impl8 --review-type self --status not_run '
        '--disposition "skipped, completed in prior session" --from none'
    )
    _run_hook(monkeypatch, wt, _bash_payload(command))
    events = read_raw_events(wt, "iterate-impl8")
    assert events == []


def test_equals_form_flag_value_is_matched(git_origin_repo, monkeypatch):
    """`--review-type=self` (argparse's `=`-joined form), not just the
    space-separated form (code review, trg-e6d1cc5e round 3)."""
    work, _ = git_origin_repo
    wt = _setup_worktree(work, "impl9", "iterate-impl9")
    command = (
        'uv run "shared/scripts/tools/record_review_pass.py" record '
        '--run-id=iterate-impl9 --review-type=self --status=completed --from=none'
    )
    _run_hook(monkeypatch, wt, _bash_payload(command))
    events = read_raw_events(wt, "iterate-impl9")
    assert any(e.get("event") == "start" and e.get("name") == "review" for e in events)


def test_lock_timeout_on_review_write_leaves_done_marker_unset(git_origin_repo, monkeypatch):
    """A transient lock timeout on the guard-critical write must not durably
    mark the run "done" — that would permanently suppress the retry the
    event-based guard in `_handle_bash` would otherwise allow (code review,
    trg-e6d1cc5e round 3: a prior version marked done unconditionally)."""
    work, _ = git_origin_repo
    wt = _setup_worktree(work, "impl10", "iterate-impl10")
    monkeypatch.setattr(mis, "record_start", lambda *a, **k: (_ for _ in ()).throw(mis.LockTimeout()))
    _run_hook(monkeypatch, wt, _bash_payload(_SELF_REVIEW_CMD))
    events = read_raw_events(wt, "iterate-impl10")
    assert not any(e.get("event") == "start" and e.get("name") == "review" for e in events)
    assert not mis.state.has_any_done_marker(wt)


def test_self_review_only_lock_timeout_is_retried_on_next_call(git_origin_repo, monkeypatch):
    """Asymmetric failure (doubt review round 3): `review` succeeds but
    `self_review` alone hits a transient `LockTimeout`. The retry guard must
    key off `self_review`, not `review` — a prior version's guard checked
    only `review`, so a retry saw `review` already present and returned
    before ever retrying the still-missing `self_review`."""
    work, _ = git_origin_repo
    wt = _setup_worktree(work, "impl12", "iterate-impl12")
    real_record_start = mis.record_start

    def _fail_self_review_only(*a, **k):
        if k.get("name") == "self_review":
            raise mis.LockTimeout()
        return real_record_start(*a, **k)

    monkeypatch.setattr(mis, "record_start", _fail_self_review_only)
    _run_hook(monkeypatch, wt, _bash_payload(_SELF_REVIEW_CMD))
    events = read_raw_events(wt, "iterate-impl12")
    assert any(e.get("event") == "start" and e.get("name") == "review" for e in events)
    assert not any(e.get("event") == "start" and e.get("name") == "self_review" for e in events)
    assert not mis.state.has_any_done_marker(wt)

    monkeypatch.setattr(mis, "record_start", real_record_start)
    _run_hook(monkeypatch, wt, _bash_payload(_SELF_REVIEW_CMD))
    events = read_raw_events(wt, "iterate-impl12")
    review_starts = [e for e in events if e.get("event") == "start" and e.get("name") == "review"]
    self_review_starts = [
        e for e in events if e.get("event") == "start" and e.get("name") == "self_review"
    ]
    assert len(review_starts) == 1
    assert len(self_review_starts) == 1


def test_no_active_iterate_skips_pointer_resolution(tmp_path, monkeypatch):
    """Doubt review round 3: the hook's `Write|Edit|Bash` matcher fires for
    the plugin's whole session lifetime, not merely during an active
    iterate — an ordinary checkout with no run pointer for any session must
    take a git-free fast path rather than paying `pointer_run_id`'s
    unconditional `git rev-parse` cost on every tool call, forever."""
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    (repo / ".shipwright").mkdir()
    monkeypatch.chdir(repo)

    def _boom(*a, **k):
        raise AssertionError("pointer_run_id must not be called with no active iterate")

    monkeypatch.setattr(mis, "pointer_run_id", _boom)
    monkeypatch.setattr(mis, "pointer_worktree_root", _boom)
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(_write_payload(
        str(repo / "src" / "thing.py")))))
    assert mis.main() == 0


def test_resolved_pointer_is_cached_across_calls(git_origin_repo, monkeypatch):
    """The second call in the same worktree/session must not re-invoke the
    git-backed pointer resolvers (code review, trg-e6d1cc5e round 3: every
    call before the done marker exists paid two `git rev-parse` shellouts)."""
    work, _ = git_origin_repo
    wt = _setup_worktree(work, "impl11", "iterate-impl11")
    (wt / "src").mkdir(parents=True, exist_ok=True)
    a = wt / "src" / "a.py"
    b = wt / "src" / "b.py"
    a.write_text("a\n", encoding="utf-8")
    b.write_text("b\n", encoding="utf-8")
    _run_hook(monkeypatch, wt, _write_payload(str(a)))
    assert mis.state.resolved_cache_path(wt).exists()

    def _boom(*a, **k):
        raise AssertionError("pointer_run_id must not be called once cached")

    monkeypatch.setattr(mis, "pointer_run_id", _boom)
    monkeypatch.setattr(mis, "pointer_worktree_root", _boom)
    _run_hook(monkeypatch, wt, _write_payload(str(b)))
    events = read_raw_events(wt, "iterate-impl11")
    starts = [e for e in events if e.get("event") == "start" and e.get("name") == "implementation"]
    assert len(starts) == 1


def test_outside_active_iterate_is_a_noop(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(_write_payload(
        str(tmp_path / "src" / "thing.py")))))
    assert mis.main() == 0


def test_malformed_stdin_never_raises(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "stdin", io.StringIO("not json"))
    assert mis.main() == 0
