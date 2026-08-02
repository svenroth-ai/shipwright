"""``grade_snapshot.dirty`` describes the tree BEFORE the producer wrote
(``trg-f5ae5371``).

A Control Grade is computed from the working tree. ``dirty`` says whether tracked
content differed from HEAD when that grade was measured. It does not make ``base``
identify the graded commit on branch lineage, where ``base`` is the merge-base.

The obvious implementation — ask git when the snapshot is emitted — was built and
WITHDRAWN before commit after two review rounds, because by then the producer has
written its own output into the tree: ``update_compliance`` rewrites six tracked
documents, and ``finalize_iterate`` has already appended to the tracked event log.
Measured on four producers; reproduced end-to-end with ``dirty=true`` and **zero
uncommitted source**.

These tests exercise the REAL ``update_compliance`` loop against a REAL git repo,
because the defect is entirely about ordering between two things a mock cannot
order. Split from ``test_grade_snapshot_regen.py``, which owns the emitter's
idempotency and dashboard-parity subjects.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

import scripts.tools.update_compliance as update_compliance
from scripts.lib.data_collector import ComplianceData, DependencyInfo

RUN = "iterate-2026-08-01-grade-snapshot-dirty-capture"
_OMITTED = object()

#: Every environment name the capture reads. Cleared per test so a developer's own
#: exported run id cannot make one of these pass or fail for the wrong reason.
CAPTURE_ENV = (
    "SHIPWRIGHT_SOURCE_DIRTY", "SHIPWRIGHT_SOURCE_DIRTY_RUN",
    "SHIPWRIGHT_SOURCE_DIRTY_ROOT", "SHIPWRIGHT_RUN_ID",
)


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(root), *args], check=True,
                   capture_output=True, text=True, timeout=30)


def _porcelain(root: Path) -> str:
    return subprocess.run(
        ["git", "-C", str(root), "status", "--porcelain", "--untracked-files=no"],
        capture_output=True, text=True, timeout=30).stdout


def _gradeable_data(root: Path) -> ComplianceData:
    """ComplianceData whose report is gradeable: one declared dependency makes the
    dependency-hygiene dimension measurable → a letter + score to snapshot."""
    return ComplianceData(
        project_root=root,
        dependencies=[DependencyInfo("left-pad", "1.0.0", "runtime", "MIT")],
        timestamp="2026-08-01T00:00:00Z",
    )


def _snapshots(root: Path) -> list[dict]:
    path = root / "shipwright_events.jsonl"
    if not path.exists():
        return []
    events = (json.loads(ln) for ln in path.read_text(encoding="utf-8").splitlines()
              if ln.strip())
    return [e for e in events if e.get("type") == "grade_snapshot"]


def _pristine_repo(root: Path) -> None:
    """A repo where the producer's own outputs are TRACKED and committed."""
    subprocess.run(["git", "init", "-q", "-b", "main", str(root)], check=True,
                   capture_output=True, text=True, timeout=30)
    _git(root, "config", "user.email", "fixture@example.invalid")
    _git(root, "config", "user.name", "fixture")
    _git(root, "config", "commit.gpgsign", "false")
    (root / ".shipwright" / "compliance").mkdir(parents=True, exist_ok=True)
    # The files the regen rewrites / appends to must ALREADY be tracked, or their
    # modification would not register as dirt at all and the tests would pass
    # vacuously — asserting "clean" about a tree nothing could have dirtied.
    (root / ".shipwright" / "compliance" / "dashboard.md").write_text(
        "stale\n", encoding="utf-8")
    (root / "shipwright_events.jsonl").write_text("", encoding="utf-8")
    (root / "src.py").write_text("print('committed')\n", encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "pristine")


def _regen(root: Path, monkeypatch, capsys, *, run_id=_OMITTED) -> dict:
    """Run the real ``update_compliance`` dashboard branch; return its snapshot."""
    monkeypatch.setattr(update_compliance, "collect_all", lambda pr: _gradeable_data(root))
    argv = ["update_compliance.py", "--project-root", str(root), "--phase", "design"]
    if run_id is not _OMITTED:
        argv += ["--run-id", run_id]
    monkeypatch.setattr(sys, "argv", argv)
    assert update_compliance.main() == 0
    capsys.readouterr()
    snaps = _snapshots(root)
    assert len(snaps) == 1
    return snaps[0]


@pytest.fixture(autouse=True)
def _clear_env(monkeypatch):
    """`update_compliance.main()` runs IN-PROCESS here, so the capture writes the
    real `os.environ`. `setenv` before `delenv` is what registers the names with
    monkeypatch — a bare `delenv` on an absent name records nothing to restore, and
    the writes would leak into every later test in this process."""
    for name in CAPTURE_ENV:
        monkeypatch.setenv(name, "sentinel")
        monkeypatch.delenv(name, raising=False)


class TestDirtyDescribesTheTreeBeforeTheProducerWrote:
    """category: integration — the capture-before-write ordering."""

    def test_pristine_tree_emits_dirty_false(self, tmp_path, monkeypatch, capsys):
        """THE regression. The regen rewrites dashboard.md and appends to the
        tracked event log before emitting — and still reports the tree it graded as
        clean, because the answer was captured at entry."""
        _pristine_repo(tmp_path)

        snap = _regen(tmp_path, monkeypatch, capsys, run_id=RUN)

        assert snap["dirty"] is False, (
            "the producer's own writes were counted as tree dirt — "
            "this is the withdrawn implementation")
        # And the producer really did dirty the tree in the meantime, which is what
        # makes the assertion above meaningful rather than vacuous.
        assert _porcelain(tmp_path).strip(), "nothing was written — proves nothing"

    def test_genuinely_uncommitted_source_emits_dirty_true(
            self, tmp_path, monkeypatch, capsys):
        """The fix must not blanket-report clean: real uncommitted work is dirt."""
        _pristine_repo(tmp_path)
        (tmp_path / "src.py").write_text("print('edited')\n", encoding="utf-8")

        assert _regen(tmp_path, monkeypatch, capsys, run_id=RUN)["dirty"] is True

    def test_a_parents_earlier_capture_wins(self, tmp_path, monkeypatch, capsys):
        """What ``finalize_iterate`` buys: it captures BEFORE appending
        ``work_completed`` to the tracked log, and the regen inherits that answer
        rather than measuring a tree the parent already dirtied."""
        _pristine_repo(tmp_path)

        # The parent captured on the pristine tree ...
        monkeypatch.setenv("SHIPWRIGHT_SOURCE_DIRTY", "0")
        monkeypatch.setenv("SHIPWRIGHT_SOURCE_DIRTY_RUN", RUN)
        monkeypatch.setenv("SHIPWRIGHT_SOURCE_DIRTY_ROOT", str(tmp_path.resolve()))
        # ... then wrote to the tracked event log, exactly as Step 1 does.
        (tmp_path / "shipwright_events.jsonl").write_text(
            '{"type":"work_completed"}\n', encoding="utf-8")

        assert _regen(tmp_path, monkeypatch, capsys, run_id=RUN)["dirty"] is False

    def test_an_unrelated_runs_capture_is_not_inherited(
            self, tmp_path, monkeypatch, capsys):
        """A stale export in a long-lived shell must not answer for this run."""
        _pristine_repo(tmp_path)
        (tmp_path / "src.py").write_text("print('edited')\n", encoding="utf-8")
        monkeypatch.setenv("SHIPWRIGHT_SOURCE_DIRTY", "0")
        monkeypatch.setenv("SHIPWRIGHT_SOURCE_DIRTY_RUN", "some-other-run")
        monkeypatch.setenv("SHIPWRIGHT_SOURCE_DIRTY_ROOT", str(tmp_path.resolve()))

        assert _regen(tmp_path, monkeypatch, capsys, run_id=RUN)["dirty"] is True

    def test_run_id_falls_back_to_the_environment(self, tmp_path, monkeypatch, capsys):
        """No ``--run-id``: the ambient run id still binds the inherited capture."""
        _pristine_repo(tmp_path)
        monkeypatch.setenv("SHIPWRIGHT_RUN_ID", RUN)
        monkeypatch.setenv("SHIPWRIGHT_SOURCE_DIRTY", "0")
        monkeypatch.setenv("SHIPWRIGHT_SOURCE_DIRTY_RUN", RUN)
        monkeypatch.setenv("SHIPWRIGHT_SOURCE_DIRTY_ROOT", str(tmp_path.resolve()))
        (tmp_path / "src.py").write_text("print('edited after capture')\n",
                                         encoding="utf-8")

        assert _regen(tmp_path, monkeypatch, capsys)["dirty"] is False

    def test_an_explicit_run_id_beats_the_environment(
            self, tmp_path, monkeypatch, capsys):
        """Precedence (external review, dependency/low): a caller that NAMES the run
        knows better than a variable an unrelated shell may have exported."""
        _pristine_repo(tmp_path)
        (tmp_path / "src.py").write_text("print('edited')\n", encoding="utf-8")
        # The ambient run id has a clean capture; the explicit one has none, so the
        # regen must measure — and find the edit.
        monkeypatch.setenv("SHIPWRIGHT_RUN_ID", "ambient-run")
        monkeypatch.setenv("SHIPWRIGHT_SOURCE_DIRTY", "0")
        monkeypatch.setenv("SHIPWRIGHT_SOURCE_DIRTY_RUN", "ambient-run")
        monkeypatch.setenv("SHIPWRIGHT_SOURCE_DIRTY_ROOT", str(tmp_path.resolve()))

        assert _regen(tmp_path, monkeypatch, capsys, run_id=RUN)["dirty"] is True

    def test_an_explicit_empty_run_id_does_not_adopt_the_environment(
            self, tmp_path, monkeypatch, capsys):
        """Even an unusable explicit value wins over ambient state.

        ``safe_run_id`` rejects the empty value, so this invocation is unbound and
        measures the edited tree instead of borrowing another run's clean capture.
        """
        _pristine_repo(tmp_path)
        (tmp_path / "src.py").write_text("print('edited')\n", encoding="utf-8")
        monkeypatch.setenv("SHIPWRIGHT_RUN_ID", "ambient-run")
        monkeypatch.setenv("SHIPWRIGHT_SOURCE_DIRTY", "0")
        monkeypatch.setenv("SHIPWRIGHT_SOURCE_DIRTY_RUN", "ambient-run")
        monkeypatch.setenv("SHIPWRIGHT_SOURCE_DIRTY_ROOT", str(tmp_path.resolve()))

        assert _regen(tmp_path, monkeypatch, capsys, run_id="")["dirty"] is True

    def test_no_git_omits_the_field_rather_than_guessing(
            self, tmp_path, monkeypatch, capsys):
        """Not a repo: the snapshot must not claim a tree state it cannot know."""
        (tmp_path / ".shipwright" / "compliance").mkdir(parents=True)

        assert "dirty" not in _regen(tmp_path, monkeypatch, capsys, run_id=RUN)
