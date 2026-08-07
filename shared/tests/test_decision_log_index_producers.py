"""Who refreshes decision_log_index.md, and is the committed one current?

Mirrors ``test_adr_index_producers.py``: the renderer's own rules live in
``test_decision_log_index.py``. This file covers the call sites — the direct
append path (``write_decision_log.py``, used by plan/build/deploy) and the
release pass (``aggregate_decisions.py``) — and the drift guard.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from lib.decision_log_index import (
    DECISION_LOG_INDEX_FILENAME,
    DECISION_LOG_PATH,
    rebuild_decision_log_index,
    render_decision_log_index,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]


def _log(root: Path, text: str) -> Path:
    path = root / DECISION_LOG_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _index_path(root: Path) -> Path:
    return (root / DECISION_LOG_PATH).parent / DECISION_LOG_INDEX_FILENAME


# ------------------------------------------------- direct append (write_decision_log.py)


def test_append_decision_refreshes_the_index(tmp_path):
    from tools.write_decision_log import append_decision

    append_decision(
        tmp_path, section_ref="Build — x", commit_hash="abc123",
        context="why", decision="what we did", consequences="impact",
        title="A title",
    )
    index = _index_path(tmp_path)
    assert index.is_file() and "- [ADR-001 — A title]" in index.read_text(encoding="utf-8")


def test_a_second_append_keeps_both_rows(tmp_path):
    from tools.write_decision_log import append_decision

    append_decision(
        tmp_path, section_ref="Build — x", commit_hash="abc",
        context="c1", decision="d1", consequences="q1", title="First",
    )
    append_decision(
        tmp_path, section_ref="Build — y", commit_hash="def",
        context="c2", decision="d2", consequences="q2", title="Second",
    )
    text = _index_path(tmp_path).read_text(encoding="utf-8")
    assert "First" in text and "Second" in text


def test_append_decision_refresh_is_best_effort_and_warns(tmp_path, monkeypatch, capsys):
    from tools.write_decision_log import append_decision

    def boom(_root):
        return "index is unwritable"

    from lib import decision_log_index

    monkeypatch.setattr(decision_log_index, "refresh_best_effort", boom)
    append_decision(
        tmp_path, section_ref="Build — x", commit_hash="abc",
        context="why", decision="what", consequences="impact", title="T",
    )
    err = capsys.readouterr().err
    assert "index is unwritable" in err


def test_refresh_best_effort_warns_instead_of_raising_on_undecodable_log(tmp_path):
    """decision_log.md is read with a strict UTF-8 decode; a mojibaked file must
    degrade to a warning like any other refresh failure, not escape as a raw
    UnicodeDecodeError past append_decision's already-committed write."""
    from lib.decision_log_index import refresh_best_effort

    log_path = _log(tmp_path, "### ADR-001: X\n")
    log_path.write_bytes(b"### ADR-001: X \xff\xfe\n")
    warning = refresh_best_effort(tmp_path)
    assert warning is not None and "failed" in warning


# ------------------------------------------------- release pass (aggregate_decisions.py)


def test_aggregate_refreshes_with_zero_drops(tmp_path):
    from tools.aggregate_decisions import aggregate

    _log(tmp_path, "### ADR-086: X\n")
    aggregate(tmp_path)
    index = _index_path(tmp_path)
    assert index.is_file() and "- [ADR-086 — X]" in index.read_text(encoding="utf-8")


def test_aggregate_dry_run_writes_nothing(tmp_path):
    from tools.aggregate_decisions import aggregate

    _log(tmp_path, "### ADR-087: X\n")
    aggregate(tmp_path, dry_run=True)
    assert not _index_path(tmp_path).exists()


def test_aggregate_folding_a_drop_refreshes_the_index(tmp_path):
    from tools.aggregate_decisions import aggregate
    from tools.write_decision_drop import write_decision_drop

    _log(tmp_path, "### ADR-093: Existing\n")
    write_decision_drop(
        tmp_path, run_id="iterate-2026-08-07-z", section="Iterate — change: z",
        title="Folded", context="c", decision="d", consequences="q",
    )
    aggregate(tmp_path)
    text = _index_path(tmp_path).read_text(encoding="utf-8")
    assert "Existing" in text and "Folded" in text


# ------------------------------------------------------------- drift guard


def test_committed_index_is_not_stale():
    """The drift guard — compared in LF-space, mirroring the ADR index's own."""
    log_path = _REPO_ROOT / DECISION_LOG_PATH
    if not log_path.is_file():
        pytest.skip("no decision_log.md in this checkout")
    index = log_path.parent / DECISION_LOG_INDEX_FILENAME
    assert index.is_file(), f"{DECISION_LOG_PATH} has no {DECISION_LOG_INDEX_FILENAME} sibling"
    assert index.read_text(encoding="utf-8") == render_decision_log_index(
        log_path.read_text(encoding="utf-8")
    ), f"{DECISION_LOG_INDEX_FILENAME} is stale. Regenerate via rebuild_decision_log_index.py"


def test_drift_guard_actually_fails_on_a_stale_index(tmp_path):
    """Prove the guard above can fail, not just pass."""
    _log(tmp_path, "### ADR-091: X\n")
    rebuild_decision_log_index(tmp_path)
    _log(tmp_path, "### ADR-091: X\n\n### ADR-092: Added later\n")
    text = (tmp_path / DECISION_LOG_PATH).read_text(encoding="utf-8")
    assert _index_path(tmp_path).read_text(encoding="utf-8") != render_decision_log_index(text)


def test_every_entry_in_this_repo_is_listed():
    """Fence-aware count check, independent of byte-equality.

    Must agree with ``_entries`` (not a naive regex): this repo's log embeds
    an ``## Imported decisions`` block that quotes ADR-001..008 VERBATIM
    inside a fenced code block — real history preserved for reference, not
    live entries (the live log starts numbering at ADR-009, per the file's
    own adoption-merge marker). A naive `^### ADR-` scan would wrongly expect
    those 8 quoted headings to appear in the index too.
    """
    from lib.decision_log_index import _entries

    log_path = _REPO_ROOT / DECISION_LOG_PATH
    if not log_path.is_file():
        pytest.skip("no decision_log.md in this checkout")
    index_text = (log_path.parent / DECISION_LOG_INDEX_FILENAME).read_text(encoding="utf-8")
    entries = _entries(log_path.read_text(encoding="utf-8"))
    missing = [f"{kind}-{num}" for kind, num, _title in entries if f"{kind}-{num}" not in index_text]
    assert not missing, f"{len(missing)} decision(s) unlisted in the index: {missing}"


# --------------------------------------------------------------- churn membership


def test_the_index_is_registered_as_resolvable_churn():
    from lib.churn_merge import DECISION_LOG_INDEX, CHURN_ALLOWLIST, classify

    assert DECISION_LOG_INDEX in CHURN_ALLOWLIST
    resolvable, blocking = classify([DECISION_LOG_INDEX])
    assert resolvable == [DECISION_LOG_INDEX] and blocking == []


def test_the_index_is_not_a_derived_snapshot():
    from lib.churn_merge import DECISION_LOG_INDEX
    from lib.derived_snapshots import DERIVED_SNAPSHOTS

    assert DECISION_LOG_INDEX not in DERIVED_SNAPSHOTS
