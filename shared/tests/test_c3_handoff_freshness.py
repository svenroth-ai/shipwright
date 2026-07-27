"""Canon **C3** `session_handoff.md fresh` — decided by CONTENT, never by mtime.

The F11 twin moved off filesystem mtime in iterate-2026-07-27-name-the-blocker.
C3 kept the defect until iterate-2026-07-27-c3-phase-content-key because its
content key had to be *designed*: C3 is phase-scoped, and the handoff is a
single overwritten file with no per-phase history.

The design these tests pin: **C3 keys on the run and reports the phase.** Keying
on the marker's ``phase`` was rejected on evidence — ``verify_phase.py --phase
all`` hands one ``run_id`` to eight phase dispatchers that all read the SAME
handoff, so a phase key would pass whichever phase wrote last and warn on the
other seven. That is a new structural false fire, which is the defect class the
change exists to remove. ``test_auditing_a_whole_run_*`` are the regression pair
for exactly that.
"""

from __future__ import annotations

import inspect
import os
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts" / "tools"))

import pytest  # noqa: E402

from verifiers.handoff_freshness import (  # noqa: E402
    check_c3_session_handoff_fresh_after_phase as check_c3,
)

RUN = "iterate-2026-07-27-c3-phase-content-key"
OTHER = "iterate-2026-07-01-something-else"


def _write(root: Path, body: str) -> Path:
    docs = root / ".shipwright" / "agent_docs"
    docs.mkdir(parents=True, exist_ok=True)
    path = docs / "session_handoff.md"
    path.write_text(body, encoding="utf-8")
    return path


def _canon(run_id: str, phase: str = "build", extra: str = "") -> str:
    return (
        f'---\ncanon_generated: true\nrun_id: "{run_id}"\nphase: "{phase}"\n'
        f'reason: "phase complete"\ntimestamp: "2026-07-27T09:00:00+00:00"\n{extra}---\n\n'
        "# Session Handoff\n"
    )


# --- (A) the defect this replaces --------------------------------------------

def test_an_old_handoff_naming_this_run_passes(tmp_path):
    """The regression. A handoff written three hours ago still describes THIS
    run — time spent waiting on CI is not staleness."""
    path = _write(tmp_path, _canon(RUN))
    old = time.time() - 3 * 60 * 60
    os.utime(path, (old, old))

    result = check_c3(tmp_path, "build", run_id=RUN)

    assert result.ok is True
    assert "mtime" not in result.detail.lower()


def test_a_brand_new_handoff_naming_another_run_fails(tmp_path):
    """The other half: recency never rescues a handoff that describes a
    different run. Under the old rule this passed on mtime alone."""
    _write(tmp_path, _canon(OTHER))

    result = check_c3(tmp_path, "build", run_id=RUN)

    assert result.ok is False
    assert OTHER in result.detail


def test_the_check_never_consults_mtime(tmp_path):
    """Drift guard: the mtime path is deleted, not merely out-ranked. Two files
    identical in content but a day apart in mtime must verdict identically."""
    fresh_root, stale_root = tmp_path / "fresh", tmp_path / "stale"
    for root in (fresh_root, stale_root):
        root.mkdir()
        _write(root, _canon(RUN))
    old = time.time() - 86_400
    os.utime(stale_root / ".shipwright" / "agent_docs" / "session_handoff.md", (old, old))

    a = check_c3(fresh_root, "build", run_id=RUN)
    b = check_c3(stale_root, "build", run_id=RUN)

    assert (a.ok, a.detail) == (b.ok, b.detail)


def test_the_source_carries_no_mtime_call():
    """Belt-and-braces for the above: no stat/mtime call survives in the check."""
    src = inspect.getsource(check_c3)
    for forbidden in ("st_mtime", "getmtime", "max_age_seconds", "time.time"):
        assert forbidden not in src


# --- (C) the result names which phase wrote the handoff ----------------------

def test_a_passing_result_names_the_writing_phase(tmp_path):
    _write(tmp_path, _canon(RUN, phase="test"))

    result = check_c3(tmp_path, "test", run_id=RUN)

    assert result.ok is True
    assert "test" in result.detail


def test_a_handoff_written_by_another_phase_of_this_run_passes_and_says_so(tmp_path):
    """The known bound, pinned so it stays deliberate: one overwritten file has
    no per-phase history, so C3 for `build` passes on `test`'s write within the
    same run — and says which phase actually wrote it."""
    _write(tmp_path, _canon(RUN, phase="test"))

    result = check_c3(tmp_path, "build", run_id=RUN)

    assert result.ok is True
    assert "test" in result.detail


def test_a_marker_without_a_phase_renders_a_placeholder(tmp_path):
    _write(tmp_path, _canon(RUN, phase=""))

    result = check_c3(tmp_path, "build", run_id=RUN)

    assert result.ok is True
    assert "(unnamed)" in result.detail


# --- (D) an unanswerable check says so, distinctly ---------------------------

def test_a_missing_handoff_is_not_a_pass(tmp_path):
    result = check_c3(tmp_path, "build", run_id=RUN)

    assert result.ok is False
    assert "missing" in result.detail


def test_a_handoff_without_a_canon_marker_is_not_a_pass(tmp_path):
    _write(tmp_path, "# Session Handoff\n\nno frontmatter here\n")

    result = check_c3(tmp_path, "build", run_id=RUN)

    assert result.ok is False
    assert "no canon marker" in result.detail


def test_a_non_canon_frontmatter_block_is_not_a_marker(tmp_path):
    """`canon_generated: true` is what makes a block a marker — a hand-written
    YAML header that happens to carry a run_id must not satisfy C3."""
    _write(tmp_path, f'---\nrun_id: "{RUN}"\nphase: "build"\n---\n\n# Session Handoff\n')

    result = check_c3(tmp_path, "build", run_id=RUN)

    assert result.ok is False
    assert "no canon marker" in result.detail


def test_a_marker_without_a_run_id_is_not_a_pass(tmp_path):
    _write(tmp_path, _canon("", phase="build"))

    result = check_c3(tmp_path, "build", run_id=RUN)

    assert result.ok is False
    assert "no run id" in result.detail


@pytest.mark.parametrize("sentinel", ["", "unknown", "  ", "UNKNOWN"])
def test_a_degenerate_run_id_cannot_evaluate_rather_than_warn(tmp_path, sentinel):
    """A degenerate audit context must reach C3 as itself and be reported as
    unanswerable — never silently compared against the marker and warned."""
    _write(tmp_path, _canon(RUN))

    result = check_c3(tmp_path, "build", run_id=sentinel)

    assert result.ok is False
    assert "cannot evaluate" in result.detail


def test_an_unreadable_handoff_is_not_a_pass(tmp_path, monkeypatch):
    _write(tmp_path, _canon(RUN))

    def _boom(*_a, **_k):
        raise OSError("nope")

    monkeypatch.setattr(Path, "read_text", _boom)
    result = check_c3(tmp_path, "build", run_id=RUN)

    assert result.ok is False
    assert "unreadable" in result.detail


def test_an_inaccessible_handoff_reads_as_unreadable_not_missing(tmp_path, monkeypatch):
    """`Path.is_file()` answers False for a file it cannot stat, which would
    report an existing-but-locked handoff as one nobody wrote. Different defect,
    different remedy — AC (D) wants them told apart."""
    _write(tmp_path, _canon(RUN))

    def _denied(*_a, **_k):
        raise PermissionError("locked")

    monkeypatch.setattr(Path, "read_text", _denied)
    result = check_c3(tmp_path, "build", run_id=RUN)

    assert result.ok is False
    assert "unreadable" in result.detail
    assert "missing" not in result.detail


def test_run_id_is_keyword_only_and_has_no_default():
    """Eight call sites. A default would let a missed one compare against "" and
    warn forever; keyword-only + no default makes the interpreter catch it."""
    sig = inspect.signature(check_c3)
    param = sig.parameters["run_id"]

    assert param.kind is inspect.Parameter.KEYWORD_ONLY
    assert param.default is inspect.Parameter.empty
    with pytest.raises(TypeError):
        check_c3(Path("."), "build")  # type: ignore[call-arg]


def test_a_malformed_marker_does_not_dump_its_contents_into_the_detail(tmp_path):
    """Stop-hook findings are operator-facing; a hostile or corrupt handoff
    must not paste a wall of text into them."""
    _write(tmp_path, _canon("x" * 5000, phase="build"))

    result = check_c3(tmp_path, "build", run_id=RUN)

    assert result.ok is False
    assert len(result.detail) < 400


def test_terminal_escapes_in_a_marker_never_reach_the_detail(tmp_path):
    """These details are printed into terminals and logs (`format_report` emits
    real ANSI itself), so an ESC/OSC sequence carried in a tracked handoff could
    rewrite what the operator sees. Applies to the supplied run id too."""
    _write(tmp_path, _canon("\x1b[31mred\x1b]0;title\x07", phase="build"))

    result = check_c3(tmp_path, "build", run_id="run\x1b[2Jclear")

    assert result.ok is False
    for forbidden in ("\x1b", "\x07", "\x00"):
        assert forbidden not in result.detail


# Applicability (which phases C3 covers) and whole-run `--phase all` audits live
# in test_c3_applicability.py.
