"""SessionStart Phase-Quality reports only the NEWEST run per phase.

``_findings.md`` is a retained history (last N runs). A FAIL from a superseded
run must stop being announced once a newer run of that phase exists —
otherwise a finding that was true once is replayed as "open" forever
(trg-5300dc0a: banner kept nagging after PR #789 closed it).
"""

from pathlib import Path

import pytest

from hooks import session_start_phase_quality as sq

_STALE_FAIL = "  - **W3** test-evidence.md mtime stale (768219s > 86400s)\n"


def _run(phase: str, run: str, audited_at: str, fails: str = "") -> str:
    block = f"## {phase} — {run}\n- audited_at: {audited_at}\n- source: {phase}\n"
    if fails:
        block += "- open FAILs:\n" + fails
    return block + "\n"


@pytest.fixture
def inject(tmp_path: Path, monkeypatch):
    from lib.phase_quality import SUMMARY_PATH

    def _go(digest: str) -> str:
        path = tmp_path / SUMMARY_PATH
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(digest, encoding="utf-8")
        monkeypatch.delenv("SHIPWRIGHT_PHASE_QUALITY_MODE", raising=False)
        monkeypatch.chdir(tmp_path)
        return sq.build_phase_quality_injection(str(tmp_path))

    return _go


def test_superseded_fail_not_reported_once_newer_run_passes(inject):
    digest = _run("iterate", "new", "2026-09-26T10:00:00+00:00") + _run(
        "iterate", "old", "2026-08-06T10:00:00+00:00", _STALE_FAIL
    )
    assert inject(digest) == ""


def test_fail_of_newest_run_is_still_reported(inject):
    digest = _run("iterate", "new", "2026-09-26T10:00:00+00:00", _STALE_FAIL) + _run(
        "iterate", "old", "2026-08-06T10:00:00+00:00"
    )
    out = inject(digest)
    assert "W3" in out and "1 offene" in out


def test_newest_chosen_by_audited_at_not_file_order(inject):
    digest = _run("iterate", "old", "2026-08-06T10:00:00+00:00", _STALE_FAIL) + _run(
        "iterate", "new", "2026-09-26T10:00:00+00:00"
    )
    assert inject(digest) == ""


def test_other_phase_fail_unaffected_by_newer_run_of_different_phase(inject):
    digest = _run("changelog", "c1", "2026-09-26T10:00:00+00:00") + _run(
        "iterate", "i1", "2026-08-06T10:00:00+00:00", _STALE_FAIL
    )
    assert "W3" in inject(digest)


def test_repeated_fail_in_every_run_collapses_to_one_line(inject):
    digest = "".join(
        _run("iterate", f"r{i}", f"2026-09-2{i}T10:00:00+00:00", _STALE_FAIL)
        for i in (3, 2, 1)
    )
    assert inject(digest).count("• W3") == 1


def test_same_run_id_audited_twice_only_newest_block_counts(inject):
    digest = _run("iterate", "X", "2026-09-26T12:00:00+00:00") + _run(
        "iterate", "X", "2026-09-26T10:00:00+00:00", _STALE_FAIL
    )
    assert inject(digest) == ""


def test_missing_audited_at_sorts_oldest(inject):
    undated = "## iterate — a\n- open FAILs:\n" + _STALE_FAIL + "\n"
    digest = undated + _run("iterate", "b", "2026-09-26T10:00:00+00:00")
    assert inject(digest) == ""


def test_newest_compared_as_instant_across_utc_offsets(inject):
    # 12:00+02:00 (= 10:00Z) is EARLIER than 11:00+00:00, though it sorts later as text.
    digest = _run("iterate", "new", "2026-09-26T11:00:00+00:00") + _run(
        "iterate", "old", "2026-09-26T12:00:00+02:00", _STALE_FAIL
    )
    assert inject(digest) == ""


def test_audited_at_lookalike_inside_fail_list_is_ignored(inject):
    fails = _STALE_FAIL + "  - audited_at: 2099-01-01T00:00:00+00:00\n"
    digest = _run("iterate", "new", "2026-09-26T10:00:00+00:00") + _run(
        "iterate", "old", "2026-08-06T10:00:00+00:00", fails
    )
    assert inject(digest) == ""


def test_sentinel_newest_run_does_not_retire_real_run_fail(inject):
    digest = _run("iterate", "unknown", "2026-09-27T10:00:00+00:00") + _run(
        "iterate", "real", "2026-09-26T10:00:00+00:00", _STALE_FAIL
    )
    assert "W3" in inject(digest)


def test_session_start_hook_end_to_end_retires_superseded_fail(monkeypatch, tmp_path):
    """Integration: the real SessionStart hook (capture_session_id.py, run as a
    subprocess) announces the current FAIL and NOT the superseded one."""
    import json
    import os
    import subprocess
    import sys

    from lib.phase_quality import SUMMARY_PATH

    script = str(
        Path(__file__).resolve().parent.parent / "scripts" / "hooks" / "capture_session_id.py"
    )
    (tmp_path / "shipwright_run_config.json").write_text("{}", encoding="utf-8")
    digest = (
        _run("iterate", "new", "2026-09-26T10:00:00+00:00",
             "  - **W2** current problem\n")
        + _run("iterate", "old", "2026-08-06T10:00:00+00:00", _STALE_FAIL)
    )
    path = tmp_path / SUMMARY_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(digest, encoding="utf-8")
    env = {k: v for k, v in os.environ.items()
           if k not in ("SHIPWRIGHT_SESSION_ID", "SHIPWRIGHT_PHASE_QUALITY_MODE")}
    env.update(CLAUDE_PLUGIN_ROOT="/fake/root", SHIPWRIGHT_PROJECT_ROOT=str(tmp_path))

    result = subprocess.run(
        [sys.executable, script], input=json.dumps({"session_id": "newest-run-sess"}),
        capture_output=True, text=True, encoding="utf-8", env=env, cwd=tmp_path,
    )
    ctx = json.loads(result.stdout)["hookSpecificOutput"]["additionalContext"]

    assert "W2" in ctx and "1 offene" in ctx
    assert "W3" not in ctx and "768219" not in ctx
