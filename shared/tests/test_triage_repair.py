"""Repair pass for already-corrupted triage lines: scan + apply.

The outbox is UNTRACKED, so a corrupted line has no git history to recover from -
repair must preserve both records. Regression home for
iterate-2026-07-18-outbox-newline-corruption (AC4).

Split when this file crossed the 300-LOC gate: the minimal-rewrite, refusal and
lock-ordering guarantees live in `test_triage_repair_safety.py`.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

# `shared/scripts` MUST precede `shared/tests` on sys.path: BOTH contain a real
# `tools` package, and `shared/tests/tools` would otherwise shadow the one holding
# triage_repair. conftest already puts `shared/tests` on the path, so insert this
# at position 0 unconditionally rather than guarding on membership (a guard would
# leave a pre-existing, lower-priority entry in place).
_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(_SCRIPTS))
# The sibling-helper dir goes at the END: prepending it would put `shared/tests`
# ahead of `shared/scripts` and re-shadow `tools`.
_TESTS = str(Path(__file__).resolve().parent)
if _TESTS not in sys.path:
    sys.path.append(_TESTS)

import triage  # noqa: E402
from _triage_repair_helpers import (  # noqa: E402
    APPEND,
    STATUS,
    corrupt_outbox as _corrupt_outbox,
    j as _j,
    project as _project,
)
from tools.triage_repair import main, scan_path  # noqa: E402


# ---------------------------------------------------------------------------
# scan — reporting
# ---------------------------------------------------------------------------

def test_scan_reports_a_concatenated_line(tmp_path: Path) -> None:
    p = _corrupt_outbox(_project(tmp_path))
    report = scan_path(p)
    assert report.needs_repair is True
    assert report.recovered_records == 2
    assert report.unrecoverable == []


def test_scan_is_clean_on_a_healthy_file(tmp_path: Path) -> None:
    p = triage._outbox_path(_project(tmp_path))
    p.write_bytes((_j(APPEND) + "\n" + _j(STATUS) + "\n").encode())
    assert scan_path(p).needs_repair is False


def test_scan_flags_an_unterminated_file(tmp_path: Path) -> None:
    """An unterminated file is a latent corruption: the NEXT append concatenates."""
    p = triage._outbox_path(_project(tmp_path))
    p.write_bytes(_j(APPEND).encode())
    assert scan_path(p).needs_repair is True


def test_scan_separates_unrecoverable_text(tmp_path: Path) -> None:
    p = _corrupt_outbox(_project(tmp_path), tail='{"truncated":')
    report = scan_path(p)
    assert report.recovered_records == 2
    assert report.unrecoverable == ['{"truncated":']


# ---------------------------------------------------------------------------
# --apply — mutation
# ---------------------------------------------------------------------------

def test_report_mode_never_mutates(tmp_path: Path) -> None:
    project = _project(tmp_path)
    p = _corrupt_outbox(project)
    before = p.read_bytes()
    assert main(["--project-root", str(project)]) == 1  # non-zero: repair needed
    assert p.read_bytes() == before


def test_apply_requires_the_quiesced_acknowledgement(tmp_path: Path) -> None:
    """The atomic replace swaps the inode; a non-cooperating writer would be lost."""
    project = _project(tmp_path)
    p = _corrupt_outbox(project)
    before = p.read_bytes()
    assert main(["--project-root", str(project), "--apply"]) == 2
    assert p.read_bytes() == before


def test_apply_splits_the_line_and_preserves_both_records(tmp_path: Path) -> None:
    project = _project(tmp_path)
    p = _corrupt_outbox(project)
    assert main(["--project-root", str(project), "--apply", "--writers-quiesced"]) == 0

    lines = [ln for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert [json.loads(ln) for ln in lines] == [APPEND, STATUS]
    assert p.read_bytes().endswith(b"\n")


def test_apply_terminates_an_unterminated_file(tmp_path: Path) -> None:
    project = _project(tmp_path)
    p = triage._outbox_path(project)
    p.write_bytes(_j(APPEND).encode())
    assert main(["--project-root", str(project), "--apply", "--writers-quiesced"]) == 0
    assert p.read_bytes().endswith(b"\n")


def test_apply_quarantines_unrecoverable_text_verbatim(tmp_path: Path) -> None:
    project = _project(tmp_path)
    p = _corrupt_outbox(project, tail='{"truncated":')
    assert main(["--project-root", str(project), "--apply", "--writers-quiesced"]) == 0

    # Both good records survive in the repaired file...
    lines = [ln for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert [json.loads(ln) for ln in lines] == [APPEND, STATUS]

    # ...and the unrecoverable fragment is preserved, not dropped.
    q = project / ".shipwright" / "triage.outbox.quarantine.jsonl"
    entries = [json.loads(ln) for ln in q.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert any(e["original"] == '{"truncated":' for e in entries)


def test_retry_after_a_crashed_replace_does_not_double_quarantine(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The real retry: quarantine succeeded, the replace then failed, so the
    fragment is STILL on disk and the next run re-processes it.

    The previous version of this test re-ran `main` on an already-repaired file, so
    it never reached `_repair` at all and passed even with the whole content-hash
    dedupe deleted (caught by both reviewers as a false green).
    """
    import tools.triage_repair as tr

    project = _project(tmp_path)
    _corrupt_outbox(project, tail='{"truncated":')
    q = project / ".shipwright" / "triage.outbox.quarantine.jsonl"

    boom = {"n": 0}

    def exploding_write(path, data):
        boom["n"] += 1
        raise OSError("simulated crash after quarantine, before replace")

    monkeypatch.setattr(tr, "durable_atomic_write", exploding_write)
    with pytest.raises(OSError):
        main(["--project-root", str(project), "--apply", "--writers-quiesced"])
    monkeypatch.undo()  # restore before the retry below re-runs the real write

    assert boom["n"] == 1
    first = [ln for ln in q.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert len(first) == 1  # quarantined before the crash

    # The source is untouched, so the retry hits _repair again with the same fragment.
    assert main(["--project-root", str(project), "--apply", "--writers-quiesced"]) == 0
    second = [ln for ln in q.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert len(second) == 1, "content-hash dedupe must not re-quarantine the fragment"


def test_repeated_identical_fragments_quarantine_once(tmp_path: Path) -> None:
    """Dedupe also applies within a single run."""
    project = _project(tmp_path)
    frag = '{"truncated":'
    p = triage._outbox_path(project)
    p.write_bytes(((_j(APPEND) + frag + "\n") * 2).encode())

    assert main(["--project-root", str(project), "--apply", "--writers-quiesced"]) == 0
    q = project / ".shipwright" / "triage.outbox.quarantine.jsonl"
    entries = [ln for ln in q.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert len(entries) == 1


def test_second_run_on_a_repaired_file_is_clean(tmp_path: Path) -> None:
    project = _project(tmp_path)
    _corrupt_outbox(project)
    argv = ["--project-root", str(project), "--apply", "--writers-quiesced"]
    assert main(argv) == 0
    after = triage._outbox_path(project).read_bytes()
    assert main(argv) == 0
    assert triage._outbox_path(project).read_bytes() == after
