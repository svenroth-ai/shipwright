"""Who refreshes the decision-drops INDEX.md, writing mechanics, and the
deliberate absence of churn/CI-drift machinery.

Mirrors ``test_adr_index_producers.py`` and ``test_adr_index_writing.py``
where the pattern applies. It deliberately does NOT have a
``test_committed_index_is_not_stale``-style CI guard against a real checkout:
``INDEX.md`` itself (not the directory it lists — that's tracked) is
gitignored, so there is never a committed copy in a clean CI clone to
compare against — see ``lib/decision_drops_index.py``'s module docstring for
the full rationale.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from lib import atomic_write
from lib.decision_drops_index import (
    DROP_INDEX_FILENAME,
    REGEN_COMMAND,
    REGEN_TOOL_RELPATH,
    drop_dir,
    rebuild_decision_drops_index,
    regen_command_resolved,
    render_decision_drops_index,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]


def _regen_script() -> Path:
    return _REPO_ROOT / "shared" / REGEN_TOOL_RELPATH


# --------------------------------------------------------------- writing


def test_missing_drops_dir_is_a_strict_noop(tmp_path):
    assert rebuild_decision_drops_index(tmp_path) is None


def test_rebuild_writes_the_render(tmp_path):
    dd = drop_dir(tmp_path)
    dd.mkdir(parents=True)
    path = rebuild_decision_drops_index(tmp_path)
    assert path is not None
    assert path.name == DROP_INDEX_FILENAME
    assert path.read_text(encoding="utf-8") == render_decision_drops_index(dd)


def test_failed_write_leaves_the_previous_index_intact(tmp_path, monkeypatch):
    dd = drop_dir(tmp_path)
    dd.mkdir(parents=True)
    good = rebuild_decision_drops_index(tmp_path).read_text(encoding="utf-8")

    def boom(*a, **k):
        raise OSError("disk full")

    monkeypatch.setattr(atomic_write.os, "replace", boom)
    with pytest.raises(OSError):
        rebuild_decision_drops_index(tmp_path)
    assert (dd / DROP_INDEX_FILENAME).read_text(encoding="utf-8") == good


def test_render_is_written_verbatim_lf_even_on_windows(tmp_path):
    dd = drop_dir(tmp_path)
    dd.mkdir(parents=True)
    raw = rebuild_decision_drops_index(tmp_path).read_bytes()
    assert b"\r\n" not in raw


def test_lock_is_anchored_at_the_resolved_drops_dirs_own_root(tmp_path, monkeypatch):
    """Two callers passing DIFFERENT project_roots that both resolve (via
    resolve_main_repo_root, e.g. two worktrees of the same main repo) to the
    SAME drops dir must contend on the SAME lock file — not two different
    ones keyed off each caller's own root. That was the bug: the lock used to
    be anchored on the caller's project_root while the artifact was anchored
    on drop_dir()'s resolved root."""
    from lib import decision_drops_index as ddi

    main_root = tmp_path / "main"
    worktree_root = tmp_path / "worktree"
    dd = main_root / ".shipwright" / "agent_docs" / ddi.DROP_DIRNAME
    dd.mkdir(parents=True)

    monkeypatch.setattr(ddi, "drop_dir", lambda _root: dd)
    seen_locks = []
    real_file_lock = ddi.file_lock

    def spy(path, **kwargs):
        seen_locks.append(path)
        return real_file_lock(path, **kwargs)

    monkeypatch.setattr(ddi, "file_lock", spy)
    ddi.rebuild_decision_drops_index(main_root)
    ddi.rebuild_decision_drops_index(worktree_root)
    assert len(seen_locks) == 2
    assert seen_locks[0] == seen_locks[1]


def test_regen_command_names_a_script_that_exists():
    assert _regen_script().is_file(), f"{REGEN_COMMAND} names a script that is missing"


def test_regen_command_is_layout_independent():
    assert "{shared_root}" in REGEN_COMMAND
    resolved = regen_command_resolved()
    assert "{shared_root}" not in resolved
    assert Path(resolved.split("uv run ", 1)[1].split(" ", 1)[0]).is_file()


def test_cli_regenerates_the_index(tmp_path):
    dd = drop_dir(tmp_path)
    dd.mkdir(parents=True)
    proc = subprocess.run(
        [sys.executable, str(_regen_script()), "--project-root", str(tmp_path)],
        capture_output=True, text=True, encoding="utf-8",
    )
    assert proc.returncode == 0, proc.stderr
    assert (dd / DROP_INDEX_FILENAME).is_file()


def test_cli_on_a_repo_without_a_drops_dir_creates_nothing(tmp_path):
    proc = subprocess.run(
        [sys.executable, str(_regen_script()), "--project-root", str(tmp_path)],
        capture_output=True, text=True, encoding="utf-8",
    )
    assert proc.returncode == 0, proc.stderr
    assert not drop_dir(tmp_path).exists()


# ---------------------------------------------------------- iterate F3 (write)


def _run_drop(root: Path, run_id: str, title: str) -> int:
    """Drive the CLI, not the bare function — the index refresh (like the
    ADR index's own) fires from ``main()``, mirroring
    ``test_adr_index_producers._run_drop``."""
    from tools import write_decision_drop as wdd

    return wdd.main([
        "--project-root", str(root), "--run-id", run_id,
        "--section", "Iterate — change: x", "--title", title,
        "--context", "c", "--decision", "d", "--consequences", "q",
    ])


def test_write_decision_drop_refreshes_the_drops_index(tmp_path):
    assert _run_drop(tmp_path, "iterate-2026-08-07-x", "T") == 0
    dd = drop_dir(tmp_path)
    text = (dd / DROP_INDEX_FILENAME).read_text(encoding="utf-8")
    assert "T" in text


def test_write_decision_drop_index_refresh_is_best_effort_and_warns(tmp_path, monkeypatch, capsys):
    """Patches ``rebuild_decision_drops_index`` (what ``refresh_best_effort``
    resolves at call time via its OWN module globals) — patching
    ``refresh_best_effort`` itself would miss ``write_decision_drop.py``'s
    already-bound import alias, exactly like ``test_adr_index_producers``'s
    equivalent patches ``rebuild_adr_index``, not ``refresh_best_effort``."""
    def boom(_root):
        raise OSError("index is unwritable")

    from lib import decision_drops_index

    monkeypatch.setattr(decision_drops_index, "rebuild_decision_drops_index", boom)
    assert _run_drop(tmp_path, "iterate-2026-08-07-y", "T") == 0
    assert "index is unwritable" in capsys.readouterr().err


# ------------------------------------------------- release pass (fold + delete)


def test_aggregate_folding_a_drop_refreshes_the_drops_index_to_empty(tmp_path):
    from tools.aggregate_decisions import aggregate

    assert _run_drop(tmp_path, "iterate-2026-08-07-z", "Folded") == 0
    dd = drop_dir(tmp_path)
    assert "Folded" in (dd / DROP_INDEX_FILENAME).read_text(encoding="utf-8")

    aggregate(tmp_path)
    assert "No pending decision-drops" in (dd / DROP_INDEX_FILENAME).read_text(encoding="utf-8")


# ------------------------------------------------- deliberate absence of churn


def test_the_drops_index_carries_no_churn_allowlist_entry():
    """Neither INDEX.md (gitignored — git can never conflict on it) nor the
    tracked *.json payloads (each a uniquely-named new file per run, so two
    branches adding different ones merges cleanly) need one. See module
    docstring."""
    from lib.churn_merge import CHURN_ALLOWLIST

    assert not any("decision-drops" in entry for entry in CHURN_ALLOWLIST)
