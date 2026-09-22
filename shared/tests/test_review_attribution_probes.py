"""Confidence Calibration probes + a defense-in-depth guard test for
``lib.review_attribution`` (campaign-dag-scheduler R3).

Split out of ``test_review_attribution.py`` to keep that file under the
300-line source-file convention (``shipwright_bloat_baseline.json``) — same
module under test, same fixtures, just a second file so the split carries no
behavior change of its own.

The two probe tests are Step 3.8's (Confidence Calibration, mandatory at
medium+) empirical anchor: per `references/confidence-anti-patterns.md`,
"are you confident?" is answered with a probe + finding, not a yes/no. Both
ran clean (asymptote reached after round 2) — see the iterate ADR's
"Confidence Calibration" section for the full readout.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from lib.review_attribution import ReviewAttributionError, pin, verify


def _write_loop_state(path: Path, units: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"loop_id": "r3-test", "units": units}), encoding="utf-8")


def _commit_file(repo: Path, name: str, content: str) -> str:
    (repo / name).write_text(content, encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", name], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(repo), "commit", "-m", f"add {name}"], check=True, capture_output=True,
    )
    return subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"],
                           capture_output=True, text=True, check=True).stdout.strip()


def test_pin_with_a_non_ascii_unit_id_round_trips_through_the_on_disk_file(git_origin_repo):
    """Confidence Calibration probe 1 (asymptote round 1, no finding): a
    unit_id is caller-supplied (campaign spec IDs are ASCII slugs today, but
    nothing in `pin`/`verify` assumes that) — the on-disk JSON, not just the
    in-memory return value, must round-trip a non-ASCII id exactly."""
    work, _ = git_origin_repo
    unit_id = "R3-é-café"
    _commit_file(work, "x.txt", "x\n")
    state_path = work / ".shipwright" / "loop_state.json"
    _write_loop_state(state_path, [{"id": unit_id, "branch": "main", "attempt": 0}])

    result = pin(state_path, unit_id, project_root=str(work), campaign_worktree=str(work),
                 loop_id="r3-test")
    assert result["unit_id"] == unit_id

    pin_file = work / ".shipwright" / "runs" / "r3-test" / unit_id / "a0" / "review_pin.json"
    disk = json.loads(pin_file.read_text(encoding="utf-8"))
    assert disk["unit_id"] == unit_id


def test_re_pin_the_same_attempt_after_a_new_commit_overwrites_cleanly(git_origin_repo):
    """Confidence Calibration probe 2 (asymptote round 2, no finding —
    exhausted): external plan review (openai, medium) asked what a
    same-attempt re-pin does. Empirically: `pin` has no read-modify-write
    dependency on the prior pin file, so a re-pin after a new commit
    overwrites cleanly and `verify` checks against the NEW pinned value —
    no stale-pin residue."""
    work, _ = git_origin_repo
    state_path = work / ".shipwright" / "loop_state.json"
    _write_loop_state(state_path, [{"id": "RP", "branch": "main", "attempt": 0}])

    _commit_file(work, "a.txt", "a\n")
    first = pin(state_path, "RP", project_root=str(work), campaign_worktree=str(work),
                loop_id="r3-test")
    _commit_file(work, "b.txt", "b\n")
    second = pin(state_path, "RP", project_root=str(work), campaign_worktree=str(work),
                 loop_id="r3-test")

    assert second["reviewed_head"] != first["reviewed_head"]
    result = verify(state_path, "RP", project_root=str(work), campaign_worktree=str(work),
                     loop_id="r3-test", against="reviewed_head")
    assert result["ok"] is True
    assert result["pin"]["reviewed_head"] == second["reviewed_head"]


def test_verify_refuses_a_pin_file_belonging_to_a_different_unit_id(git_origin_repo):
    """Defense in depth (external plan review, openai, medium): even though
    `attempt_id` is already encoded in the pin's directory path, `verify`
    also cross-checks the pin payload's own `unit_id` field before trusting
    it — a pin file that somehow ended up at the wrong unit's path (a manual
    copy, a future caller passing the wrong `--unit-id` at read time) must
    fail closed rather than silently verify against the wrong unit's diff."""
    work, _ = git_origin_repo
    _commit_file(work, "m.txt", "x\n")
    state_path = work / ".shipwright" / "loop_state.json"
    _write_loop_state(state_path, [
        {"id": "P1", "branch": "main", "attempt": 0},
        {"id": "P2", "branch": "main", "attempt": 0},
    ])
    pin(state_path, "P1", project_root=str(work), campaign_worktree=str(work), loop_id="r3-test")

    # P2 has never been pinned, but its expected pin path is empty; point it
    # at P1's own pin file to simulate a misplaced/copied pin.
    p2_pin_dir = work / ".shipwright" / "runs" / "r3-test" / "P2" / "a0"
    p2_pin_dir.mkdir(parents=True)
    p1_pin_file = work / ".shipwright" / "runs" / "r3-test" / "P1" / "a0" / "review_pin.json"
    (p2_pin_dir / "review_pin.json").write_text(
        p1_pin_file.read_text(encoding="utf-8"), encoding="utf-8")

    with pytest.raises(ReviewAttributionError, match="belongs to unit"):
        verify(state_path, "P2", project_root=str(work), campaign_worktree=str(work),
               loop_id="r3-test", against="reviewed_head")


def test_verify_with_differently_cased_unit_id_does_not_false_block(git_origin_repo):
    """External plan review (glm, medium): `_find_unit` resolves case-folded,
    but the on-disk `unit_id` used to be the caller's OWN spelling — pinning
    as "unit-a" then verifying as "Unit-A" (same row, different call-site
    casing) stored two different strings and the mismatch cross-check BLOCKed
    a legitimate verify. Both now use the row's own canonical `id`."""
    work, _ = git_origin_repo
    _commit_file(work, "c.txt", "x\n")
    state_path = work / ".shipwright" / "loop_state.json"
    _write_loop_state(state_path, [{"id": "unit-a", "branch": "main", "attempt": 0}])

    pin(state_path, "unit-a", project_root=str(work), campaign_worktree=str(work),
        loop_id="r3-test")
    result = verify(state_path, "Unit-A", project_root=str(work), campaign_worktree=str(work),
                     loop_id="r3-test", against="reviewed_head")
    assert result["ok"] is True


def test_pin_refuses_a_unit_id_that_would_escape_the_runs_directory(git_origin_repo):
    """External plan review (openai, medium): `loop_id`/`unit_id`/`attempt_id`
    reach `Path()` unvalidated — a `unit_id` of `"../../escape"` would write
    the pin file outside `.shipwright/runs/{loop_id}/` entirely."""
    work, _ = git_origin_repo
    _commit_file(work, "d.txt", "x\n")
    state_path = work / ".shipwright" / "loop_state.json"
    _write_loop_state(state_path, [{"id": "../../escape", "branch": "main", "attempt": 0}])

    with pytest.raises(ReviewAttributionError, match="not a safe path segment"):
        pin(state_path, "../../escape", project_root=str(work), campaign_worktree=str(work),
            loop_id="r3-test")


@pytest.mark.parametrize("unit_id", ["D:evil", "a:b"])
def test_pin_refuses_a_unit_id_with_a_windows_drive_relative_escape(git_origin_repo, unit_id):
    """Code review (medium): `_safe_segment`'s original blocklist (`/`, `\\`,
    `.`/`..`, NUL) missed `:` — `Path("C:/proj/...") / "D:evil"` resolves to a
    path on a DIFFERENT drive entirely, writing the pin file outside
    `.shipwright/runs/` on Windows."""
    work, _ = git_origin_repo
    _commit_file(work, "e.txt", "x\n")
    state_path = work / ".shipwright" / "loop_state.json"
    _write_loop_state(state_path, [{"id": unit_id, "branch": "main", "attempt": 0}])

    with pytest.raises(ReviewAttributionError, match="not a safe path segment"):
        pin(state_path, unit_id, project_root=str(work), campaign_worktree=str(work),
            loop_id="r3-test")


def test_pin_succeeds_on_a_diff_containing_a_character_outside_cp1252(git_origin_repo):
    """Code review (high): `_run_git` used to decode subprocess output with
    the platform default (cp1252 on Windows), which cannot represent several
    UTF-8 sequences already present in this repo's own tracked files (curly
    quotes, em-dash). Any diff containing one crashed `pin` with an uncaught
    UnicodeDecodeError instead of a clean ReviewAttributionError. Now decoded
    explicitly as utf-8/replace, and the diff body itself is hashed as raw
    bytes rather than decoded text."""
    work, _ = git_origin_repo
    _commit_file(work, "unicode.txt", "an em dash \u2014 and curly quotes \u201cyes\u201d\n")
    state_path = work / ".shipwright" / "loop_state.json"
    _write_loop_state(state_path, [{"id": "U", "branch": "main", "attempt": 0}])

    result = pin(state_path, "U", project_root=str(work), campaign_worktree=str(work),
                 loop_id="r3-test")
    assert result["diff_sha256"]  # did not raise; a hash was produced


def test_verify_is_not_fooled_by_a_tag_sharing_the_branchs_name(git_origin_repo):
    """Code review (medium): `verify` used to resolve the branch tip with a
    bare `git rev-parse <branch>`; gitrevisions precedence resolves a
    same-named TAG before `refs/heads/`, so a tag sharing the branch's name
    pointing at an older commit would make a legitimate, untouched branch
    false-BLOCK. Fully-qualifying as `refs/heads/<branch>` closes this."""
    work, _ = git_origin_repo
    head = _commit_file(work, "f.txt", "x\n")
    state_path = work / ".shipwright" / "loop_state.json"
    _write_loop_state(state_path, [{"id": "T", "branch": "main", "attempt": 0}])
    pin(state_path, "T", project_root=str(work), campaign_worktree=str(work), loop_id="r3-test")

    # A tag named exactly "main" pointing at an OLDER commit than the branch
    # tip — gitrevisions precedence would resolve this tag instead of
    # refs/heads/main for a bare `git rev-parse main`.
    merge_base = subprocess.run(
        ["git", "-C", str(work), "merge-base", "origin/main", "HEAD"],
        capture_output=True, text=True, check=True).stdout.strip()
    subprocess.run(["git", "-C", str(work), "tag", "main", merge_base],
                    check=True, capture_output=True)

    result = verify(state_path, "T", project_root=str(work), campaign_worktree=str(work),
                     loop_id="r3-test", against="reviewed_head")
    assert result["ok"] is True
    assert result["current_tip"] == head


def test_verify_against_shipped_head_blocks_when_no_record_commit_landed(git_origin_repo):
    """Code review (low): a non-skipped unit whose branch tip is STILL
    exactly `reviewed_head` (no review-record commit landed on top of it)
    must BLOCK with an explicit reason, not the generic parent-mismatch
    detail meant for an actually-diverged branch."""
    work, _ = git_origin_repo
    _commit_file(work, "g.txt", "x\n")
    state_path = work / ".shipwright" / "loop_state.json"
    _write_loop_state(state_path, [{"id": "V", "branch": "main", "attempt": 0}])
    pin(state_path, "V", project_root=str(work), campaign_worktree=str(work), loop_id="r3-test")

    result = verify(state_path, "V", project_root=str(work), campaign_worktree=str(work),
                     loop_id="r3-test", against="shipped_head")
    assert result["ok"] is False
    assert "no review-record commit" in result["detail"]


def test_verify_against_shipped_head_blocks_when_a_skipped_unit_moved(git_origin_repo):
    """Code review (low): a `review_skipped` pin's `shipped_head` equals
    `reviewed_head` — any further commit on the branch (nothing should land
    on a skipped unit) must BLOCK, not be silently tolerated."""
    work, _ = git_origin_repo
    _commit_file(work, "h.txt", "x\n")
    state_path = work / ".shipwright" / "loop_state.json"
    _write_loop_state(state_path, [{"id": "W", "branch": "main", "attempt": 0}])
    pin(state_path, "W", project_root=str(work), campaign_worktree=str(work),
        loop_id="r3-test", review_skipped=True)

    _commit_file(work, "i.txt", "unexpected commit on a skipped unit\n")

    result = verify(state_path, "W", project_root=str(work), campaign_worktree=str(work),
                     loop_id="r3-test", against="shipped_head")
    assert result["ok"] is False


def test_verify_refuses_an_expect_file_that_would_escape_the_pin_directory(git_origin_repo):
    """Stage-3 external review (openai/gpt-5.6-luna, PR #787): `--expect-file`
    is caller-supplied (CLI flag) and was joined to the pin directory with no
    validation, so `--expect-file ../../secret` could make `verify()` read
    outside the unit's own pin directory. Routed through the same
    `_safe_segment` guard `unit_id` already uses."""
    work, _ = git_origin_repo
    _commit_file(work, "j2.txt", "x\n")
    state_path = work / ".shipwright" / "loop_state.json"
    _write_loop_state(state_path, [{"id": "X", "branch": "main", "attempt": 0}])
    pin(state_path, "X", project_root=str(work), campaign_worktree=str(work), loop_id="r3-test")

    with pytest.raises(ReviewAttributionError, match="not a safe path segment"):
        verify(state_path, "X", project_root=str(work), campaign_worktree=str(work),
               loop_id="r3-test", against="reviewed_head",
               expect_file="../../../etc/passwd")
