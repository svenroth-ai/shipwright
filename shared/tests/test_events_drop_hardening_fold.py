"""A file a reader holds open must not leave a fold half-done (issue 978 hardening, item 1 of 7; see test_events_drop_hardening)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.append(str(Path(__file__).resolve().parent))  # after shared/scripts: tests/ has its own `tools`
from _events_fold_helpers import NEW, commit, drop, ev, git, make_repo, put  # noqa: E402

from lib.events_fold import apply_fold, apply_quarantine, plan_fold, plan_quarantine  # noqa: E402
from lib.events_fold_full import apply_full_fold  # noqa: E402
from lib.events_log import ARCHIVE_DIR, DROPS_DIR, QUARANTINE_DIR  # noqa: E402
from tools import fold_events  # noqa: E402

pytestmark = pytest.mark.covers("FR-01.11")


def _layout(root: Path) -> object:
    return json.loads((root / "shipwright_sync_config.json").read_text(encoding="utf-8")).get("events_layout")


def _hold_open(monkeypatch, *names: str):
    """Make ``Path.unlink`` fail like Windows does for a file another process has open; returns the real method."""
    real = Path.unlink

    def locked(self, *a, **kw):
        if self.name in names:
            raise PermissionError(13, "The process cannot access the file because it is being used by another process")
        return real(self, *a, **kw)

    monkeypatch.setattr(Path, "unlink", locked)
    return real


def _events_in(root: Path, folder: str) -> set[str]:
    out: set[str] = set()
    for p in (root / folder).glob("*.jsonl"):
        out |= {json.loads(line)["id"] for line in p.read_text(encoding="utf-8").splitlines() if line.strip()}
    return out


def _drops_repo(tmp_path):
    root = make_repo(tmp_path)
    a = drop(root, "run-a", ev("e1"), ev("e2"))
    drop(root, "run-b", ev("e3", NEW))
    (root / "shipwright_sync_config.json").write_text('{"events_layout": "drops"}', encoding="utf-8")
    commit(root, "drops")
    return root, a.name


def test_emergency_fold_with_a_locked_drop_reports_it_keeps_the_layout_and_a_rerun_finishes(tmp_path, monkeypatch):
    root, locked = _drops_repo(tmp_path)
    real = _hold_open(monkeypatch, locked)
    result = apply_fold(root, plan_fold(root, mode="emergency"))
    assert result["status"] == "folded_incomplete" and result["not_deleted"] == [locked]
    assert [p.name for p in (root / DROPS_DIR).glob("*.jsonl")] == [locked]       # the other drop WAS removed: no abort halfway
    assert _events_in(root, ARCHIVE_DIR) == {"e1", "e2", "e3"}                      # the archive holds everything: nothing lost
    assert _layout(root) == "drops"                                                 # the rollback is not done yet
    monkeypatch.setattr(Path, "unlink", real)
    again = apply_fold(root, plan_fold(root, mode="emergency"))
    assert again["status"] == "folded" and _layout(root) == "legacy"
    assert not list((root / DROPS_DIR).glob("*.jsonl"))


def test_fold_cli_exits_1_for_a_locked_file_and_a_rerun_with_stage_commits_a_consistent_rollback(tmp_path, monkeypatch, capsys):
    root, locked = _drops_repo(tmp_path)
    _hold_open(monkeypatch, locked)
    code = fold_events.main(["emergency", "--project-root", str(root), "--stage"])
    out = json.loads(capsys.readouterr().out)
    assert code == 1 and out["status"] == "folded_incomplete" and out["not_deleted"] == [locked]
    assert "do not commit" in out["error"]
    staged = git(root, "diff", "--cached", "--name-status")
    assert ".shipwright/events/archive/fold-" in staged and "run-b--" in staged and locked not in staged   # as far as it got
    assert _layout(root) == "drops"
    monkeypatch.undo()                                                             # the reader lets go: the finishing re-run
    assert fold_events.main(["emergency", "--project-root", str(root), "--stage"]) == 0
    git(root, "commit", "-q", "-m", "rollback")
    assert git(root, "ls-files", DROPS_DIR).split() == [f"{DROPS_DIR}/.keep"]       # no live drop in the committed tree ...
    assert _layout(root) == "legacy" and len(git(root, "ls-files", ARCHIVE_DIR).split()) == 2   # ... and both archives committed


def test_full_fold_with_a_locked_file_keeps_the_layout_and_is_idempotent(tmp_path, monkeypatch):
    root, locked = _drops_repo(tmp_path)
    (root / "shipwright_events.jsonl").write_text(json.dumps(ev("l1")) + "\n", encoding="utf-8")
    real = _hold_open(monkeypatch, locked)
    result = apply_full_fold(root)
    assert result["status"] == "folded_into_legacy_incomplete" and result["not_deleted"] == [locked]
    assert {"l1", "e1", "e2", "e3"} <= {json.loads(x)["id"] for x in (root / "shipwright_events.jsonl").read_text(encoding="utf-8").splitlines()}
    assert _layout(root) == "drops"
    monkeypatch.setattr(Path, "unlink", real)
    again = apply_full_fold(root)
    assert again["status"] == "folded_into_legacy" and again["appended"] == 0 and _layout(root) == "legacy"
    lines = (root / "shipwright_events.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == len({json.loads(x)["id"] for x in lines}) == 4              # no event twice


def test_quarantine_with_a_locked_file_reports_it_and_a_rerun_finishes(tmp_path, monkeypatch):
    root = make_repo(tmp_path)
    junk = put(root, DROPS_DIR, "run-junk--aaaaaaaa--00000001.jsonl", "not json")
    commit(root, "junk")
    real = _hold_open(monkeypatch, junk.name)
    result = apply_quarantine(root, plan_quarantine(root))
    assert result["status"] == "quarantined_incomplete" and result["not_deleted"] == [junk.name]
    assert (root / QUARANTINE_DIR / junk.name).read_bytes() == junk.read_bytes()
    monkeypatch.setattr(Path, "unlink", real)
    assert apply_quarantine(root, plan_quarantine(root))["status"] == "quarantined" and not junk.exists()
