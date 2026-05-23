"""Tests for ``record_event.attach_commit_to_event`` (iterate-2026-05-23).

Round-trip + edge-case tests for the new post-commit SHA patcher. The
helper exists so iterate finalize can:

  1. Record the ``work_completed`` event PRE-commit (commit="").
  2. Regenerate compliance MDs (which now include the event).
  3. Run the F6 git commit (atomically with MDs).
  4. Patch the event's ``commit`` field POST-commit with the just-known
     SHA — writing back to the gitignored ``shipwright_events.jsonl`` so
     no tracked-file dirt is produced.

Atomicity is required: a crash mid-write must leave the previous line
intact (we tolerate the unpatched event over a corrupt log).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_TOOLS = Path(__file__).resolve().parents[1] / "scripts" / "tools"
if str(_TOOLS) not in sys.path:
    sys.path.insert(0, str(_TOOLS))


def _write_event(project_root: Path, event: dict) -> str:
    """Append one event via the public ``append_event`` API."""
    from record_event import append_event

    return append_event(project_root, event)


def _read_lines(project_root: Path) -> list[str]:
    return (project_root / "shipwright_events.jsonl").read_text(
        encoding="utf-8"
    ).splitlines()


# ---------------------------------------------------------------------------
# Happy-path round-trip
# ---------------------------------------------------------------------------


def test_attach_commit_to_event_patches_only_commit_field(tmp_path):
    """All fields except ``commit`` are byte-preserved across the patch."""
    from record_event import attach_commit_to_event

    event = {
        "v": 1, "id": "evt-deadbeef", "ts": "2026-05-23T10:00:00+00:00",
        "type": "work_completed", "source": "iterate",
        "commit": "",  # pre-commit placeholder
        "intent": "change",
        "description": "fix stale compliance MDs",
        "affected_frs": ["FR-01.14"],
        "tests": {"passed": 11, "total": 11, "e2e_run": True},
        "spec_impact": "none",
        "spec_impact_justification": "Internal SDLC tooling change.",
        "adr_id": "iterate-2026-05-23-compliance-md-single-producer",
        "changed_files": ["audit_staleness.py", "finalize_iterate.py"],
    }
    _write_event(tmp_path, event)

    ok = attach_commit_to_event(tmp_path, "evt-deadbeef", "abc123def456")
    assert ok is True

    [line] = _read_lines(tmp_path)
    parsed = json.loads(line)
    # commit got the SHA.
    assert parsed["commit"] == "abc123def456"
    # Every other field equals the original.
    for key in event:
        if key == "commit":
            continue
        assert parsed[key] == event[key]


def test_attach_commit_to_event_returns_false_when_id_not_found(tmp_path):
    """Unknown event_id — return False, do NOT modify the log."""
    from record_event import attach_commit_to_event

    event = {
        "v": 1, "id": "evt-real0001", "ts": "2026-05-23T10:00:00+00:00",
        "type": "work_completed", "source": "iterate", "commit": "",
        "intent": "change", "description": "test",
    }
    _write_event(tmp_path, event)
    before = (tmp_path / "shipwright_events.jsonl").read_bytes()

    ok = attach_commit_to_event(tmp_path, "evt-doesnotexist", "abc123")
    assert ok is False

    after = (tmp_path / "shipwright_events.jsonl").read_bytes()
    assert before == after


# ---------------------------------------------------------------------------
# Multi-line + same-millisecond robustness
# ---------------------------------------------------------------------------


def test_attach_commit_to_event_patches_target_line_only(tmp_path):
    """Two events same millisecond — only the matching event_id is patched."""
    from record_event import attach_commit_to_event

    ts = "2026-05-23T10:00:00.123456+00:00"
    a = {"v": 1, "id": "evt-aaaa1111", "ts": ts, "type": "work_completed",
         "source": "iterate", "commit": "", "description": "A"}
    b = {"v": 1, "id": "evt-bbbb2222", "ts": ts, "type": "work_completed",
         "source": "iterate", "commit": "", "description": "B"}
    _write_event(tmp_path, a)
    _write_event(tmp_path, b)

    ok = attach_commit_to_event(tmp_path, "evt-bbbb2222", "sha-for-B")
    assert ok is True

    lines = _read_lines(tmp_path)
    assert len(lines) == 2
    parsed_a = json.loads(lines[0])
    parsed_b = json.loads(lines[1])
    assert parsed_a["id"] == "evt-aaaa1111"
    assert parsed_a["commit"] == ""  # untouched
    assert parsed_b["id"] == "evt-bbbb2222"
    assert parsed_b["commit"] == "sha-for-B"


def test_attach_commit_to_event_preserves_unrelated_events(tmp_path):
    """Non-target events (different types, earlier, later) all pass through unchanged."""
    from record_event import attach_commit_to_event

    earlier_task = {"v": 1, "id": "evt-task0001", "ts": "2026-05-22T10:00:00Z",
                    "type": "task_created", "description": "earlier task"}
    target = {"v": 1, "id": "evt-target01", "ts": "2026-05-23T10:00:00Z",
              "type": "work_completed", "source": "iterate", "commit": "",
              "description": "target"}
    later_phase = {"v": 1, "id": "evt-phase001", "ts": "2026-05-23T11:00:00Z",
                   "type": "phase_completed", "phase": "iterate"}

    _write_event(tmp_path, earlier_task)
    _write_event(tmp_path, target)
    _write_event(tmp_path, later_phase)

    ok = attach_commit_to_event(tmp_path, "evt-target01", "abc999")
    assert ok is True

    lines = _read_lines(tmp_path)
    assert len(lines) == 3
    assert json.loads(lines[0]) == earlier_task
    assert json.loads(lines[2]) == later_phase
    parsed = json.loads(lines[1])
    assert parsed["commit"] == "abc999"
    # All target fields preserved except commit.
    for k, v in target.items():
        if k == "commit":
            continue
        assert parsed[k] == v


# ---------------------------------------------------------------------------
# Corrupt-line tolerance
# ---------------------------------------------------------------------------


def test_attach_commit_to_event_skips_corrupt_lines(tmp_path):
    """Corrupt JSONL line mid-file — patch the target, leave corrupt line verbatim."""
    from record_event import attach_commit_to_event

    target = {"v": 1, "id": "evt-target02", "ts": "2026-05-23T10:00:00Z",
              "type": "work_completed", "source": "iterate", "commit": "",
              "description": "target"}

    # Hand-write the log: target + corrupt line + valid trailing event.
    valid_other = {"v": 1, "id": "evt-other001", "ts": "2026-05-23T11:00:00Z",
                   "type": "phase_started", "phase": "iterate"}
    log = tmp_path / "shipwright_events.jsonl"
    log.write_text(
        json.dumps(target, separators=(",", ":")) + "\n"
        + "{this is not valid json}\n"
        + json.dumps(valid_other, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )

    ok = attach_commit_to_event(tmp_path, "evt-target02", "abc111")
    assert ok is True

    lines = _read_lines(tmp_path)
    # Three lines still present in the same order.
    assert len(lines) == 3
    # Corrupt line passed through verbatim.
    assert lines[1] == "{this is not valid json}"
    # Trailing event still parses identical.
    assert json.loads(lines[2]) == valid_other
    # Target's commit is patched.
    assert json.loads(lines[0])["commit"] == "abc111"


def test_attach_commit_to_event_missing_log_returns_false(tmp_path):
    """No events.jsonl yet — return False, do not crash."""
    from record_event import attach_commit_to_event

    # No file written.
    ok = attach_commit_to_event(tmp_path, "evt-anything", "abc")
    assert ok is False


def test_attach_commit_to_event_is_atomic_no_partial_write_on_unicode(tmp_path):
    """Non-ASCII content survives the temp-file + rename dance unchanged."""
    from record_event import attach_commit_to_event

    target = {
        "v": 1, "id": "evt-unicode01", "ts": "2026-05-23T10:00:00Z",
        "type": "work_completed", "source": "iterate", "commit": "",
        "description": "Compliance regen — fügen Snapshot-Audit hinzu (UTF-8 üöä)",
    }
    _write_event(tmp_path, target)

    ok = attach_commit_to_event(tmp_path, "evt-unicode01", "sha999")
    assert ok is True

    parsed = json.loads(_read_lines(tmp_path)[0])
    assert "üöä" in parsed["description"]
    assert parsed["commit"] == "sha999"
