"""Immutable per-run test-results evidence at iterate F5c."""

from __future__ import annotations

import contextlib
import inspect
import json
import stat
import threading
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from pathlib import Path

import pytest

import tools.append_iterate_entry as append_tool
import lib.iterate_test_results as evidence_module
from lib.iterate_test_results import (
    EvidenceError,
    evidence_file_for,
    install_immutable_evidence,
    read_current_evidence,
    validate_evidence_bytes,
)
from tools.append_iterate_entry import IterateAppendError, append_iterate_entry


RUN_ID = "iterate-2026-08-03-evidence-test"


def _raw(run_id: str = RUN_ID, *, newline: bytes = b"\r\n") -> bytes:
    text = json.dumps(
        {
            "coverage": {"total": 91.25, "source": "combined.xml"},
            "iterate_latest": {
                "run_id": run_id,
                "unit": {"status": "passed", "passed": 7, "total": 7},
                "degraded": [],
            },
        },
        indent=2,
    )
    return text.replace("\n", newline.decode("ascii")).encode("utf-8") + newline


def _entry(run_id: str = RUN_ID) -> dict:
    return {
        "run_id": run_id,
        "date": "2026-08-03T10:00:00Z",
        "type": "change",
        "complexity": "medium",
        "branch": "iterate/evidence-test",
        "tests_passed": True,
    }


def _seed_config(tmp_path) -> None:
    (tmp_path / "shipwright_run_config.json").write_text(
        json.dumps({"iterate_history": [], "_iterate_migration_state": "complete"}),
        encoding="utf-8",
    )


def test_exact_source_bytes_are_installed_unchanged(tmp_path):
    source = tmp_path / "shipwright_test_results.json"
    raw = _raw()
    source.write_bytes(raw)

    captured = read_current_evidence(tmp_path, RUN_ID)
    target, created = install_immutable_evidence(tmp_path, RUN_ID, captured)

    assert created is True
    assert target == evidence_file_for(tmp_path, RUN_ID)
    assert target.read_bytes() == raw


@pytest.mark.parametrize(
    ("raw", "match"),
    [
        (b"{", "malformed JSON"),
        (b"[]", "top-level JSON object"),
        (b'{"iterate_latest": []}', "iterate_latest must be an object"),
        (b'{"iterate_latest": {}}', "run_id must be a string"),
        (b'{"iterate_latest":{"run_id":"iterate-2026-08-03-other"}}', "belongs to"),
        (b"\xff", "UTF-8"),
        (
            b'{"iterate_latest":{"run_id":"iterate-2026-08-03-a",'
            b'"run_id":"iterate-2026-08-03-a"}}',
            "duplicate JSON key",
        ),
        (b'{"iterate_latest":{"run_id":"iterate-2026-08-03-a"},"x":NaN}', "non-standard"),
        (b'{"iterate_latest":{"run_id":"iterate-2026-08-03-a"},"x":Infinity}', "non-standard"),
        (b'{"iterate_latest":{"run_id":"iterate-2026-08-03-a"},"x":-Infinity}', "non-standard"),
    ],
)
def test_invalid_or_ambiguous_evidence_fails_closed(raw, match):
    with pytest.raises(EvidenceError, match=match):
        validate_evidence_bytes(raw, "iterate-2026-08-03-a")


def test_missing_current_snapshot_fails_closed(tmp_path):
    with pytest.raises(EvidenceError, match="missing shipwright_test_results.json"):
        read_current_evidence(tmp_path, RUN_ID)


def test_noncanonical_invocation_run_id_is_rejected_before_path_construction(tmp_path):
    with pytest.raises(EvidenceError, match="noncanonical run_id"):
        validate_evidence_bytes(_raw("../../escape"), "../../escape")


def test_same_bytes_are_idempotent_but_different_bytes_never_overwrite(tmp_path):
    raw = _raw()
    target, created = install_immutable_evidence(tmp_path, RUN_ID, raw)
    assert created is True

    same_target, created = install_immutable_evidence(tmp_path, RUN_ID, raw)
    assert same_target == target
    assert created is False

    with pytest.raises(EvidenceError, match="immutable evidence collision"):
        install_immutable_evidence(tmp_path, RUN_ID, _raw().replace(b"91.25", b"92.00"))
    assert target.read_bytes() == raw


def test_concurrent_different_bytes_never_replace_the_atomic_winner(
    tmp_path, monkeypatch
):
    first = _raw()
    second = first.replace(b"91.25", b"92.00")
    rendezvous = threading.Barrier(2)
    real_create = evidence_module._durable_create_no_replace

    def create_together(target, raw):
        rendezvous.wait(timeout=5)
        return real_create(target, raw)

    monkeypatch.setattr(evidence_module, "_durable_create_no_replace", create_together)

    def attempt(raw):
        try:
            target, created = install_immutable_evidence(tmp_path, RUN_ID, raw)
            return "created", raw, target, created
        except EvidenceError as exc:
            return "collision", raw, None, str(exc)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(attempt, (first, second)))

    winners = [result for result in results if result[0] == "created"]
    losers = [result for result in results if result[0] == "collision"]
    assert len(winners) == len(losers) == 1
    assert winners[0][3] is True
    assert "existing bytes differ" in losers[0][3]
    assert evidence_file_for(tmp_path, RUN_ID).read_bytes() == winners[0][1]


def test_existing_symlink_target_is_rejected(tmp_path):
    target = evidence_file_for(tmp_path, RUN_ID)
    target.parent.mkdir(parents=True)
    elsewhere = tmp_path / "elsewhere.json"
    elsewhere.write_bytes(_raw())
    try:
        target.symlink_to(elsewhere)
    except OSError:
        pytest.skip("symlink creation unavailable on this host")

    with pytest.raises(EvidenceError, match="symlink"):
        install_immutable_evidence(tmp_path, RUN_ID, _raw())


def test_symlinked_evidence_parent_is_rejected(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    managed = tmp_path / ".shipwright"
    try:
        managed.symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("symlink creation unavailable on this host")

    with pytest.raises(EvidenceError, match="symlink/reparse"):
        install_immutable_evidence(tmp_path, RUN_ID, _raw())


def test_reparse_parent_is_rejected_without_host_symlink_support(tmp_path, monkeypatch):
    parent = tmp_path / ".shipwright"
    real_lstat = Path.lstat

    def lstat_with_reparse(path):
        if path == parent:
            return SimpleNamespace(
                st_mode=stat.S_IFDIR,
                st_file_attributes=getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400),
            )
        return real_lstat(path)

    monkeypatch.setattr(Path, "lstat", lstat_with_reparse)

    with pytest.raises(EvidenceError, match="symlink/reparse"):
        evidence_file_for(tmp_path, RUN_ID)


def test_root_snapshot_reparse_is_rejected_without_host_link_support(
    tmp_path, monkeypatch
):
    source = tmp_path / "shipwright_test_results.json"
    source.write_bytes(_raw())
    real_lstat = Path.lstat

    def lstat_with_reparse(path):
        if path == source:
            return SimpleNamespace(
                st_mode=stat.S_IFREG,
                st_file_attributes=getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400),
            )
        return real_lstat(path)

    monkeypatch.setattr(Path, "lstat", lstat_with_reparse)

    with pytest.raises(EvidenceError, match="symlink/reparse"):
        read_current_evidence(tmp_path, RUN_ID)


def test_root_snapshot_replacement_during_read_fails_closed(tmp_path, monkeypatch):
    source = tmp_path / "shipwright_test_results.json"
    original = _raw()
    replacement = original + b" "
    source.write_bytes(original)
    monkeypatch.delattr(evidence_module.os, "O_NOFOLLOW", raising=False)

    def replacing_read(path):
        path.write_bytes(replacement)
        return replacement

    monkeypatch.setattr(evidence_module, "durable_read_bytes", replacing_read)

    with pytest.raises(EvidenceError, match="changed while reading"):
        read_current_evidence(tmp_path, RUN_ID)


def test_public_f5c_has_no_evidence_injection_bypass():
    assert "evidence_bytes" not in inspect.signature(append_iterate_entry).parameters


def test_public_f5c_reads_snapshot_while_holding_lock(tmp_path, monkeypatch):
    _seed_config(tmp_path)
    (tmp_path / "shipwright_test_results.json").write_bytes(_raw())
    inside = False
    real_lock = append_tool.file_lock
    real_install = append_tool.install_current_evidence

    @contextlib.contextmanager
    def observed_lock(*args, **kwargs):
        nonlocal inside
        with real_lock(*args, **kwargs):
            inside = True
            try:
                yield
            finally:
                inside = False

    def checked_install(*args, **kwargs):
        assert inside is True
        return real_install(*args, **kwargs)

    monkeypatch.setattr(append_tool, "file_lock", observed_lock)
    monkeypatch.setattr(append_tool, "install_current_evidence", checked_install)

    append_iterate_entry(tmp_path, _entry())


def test_f5c_reparse_guard_creates_no_managed_directory(tmp_path, monkeypatch):
    _seed_config(tmp_path)
    (tmp_path / "shipwright_test_results.json").write_bytes(_raw())
    managed = tmp_path / ".shipwright"
    real_lstat = Path.lstat

    def lstat_with_reparse(path):
        if path == managed:
            return SimpleNamespace(
                st_mode=stat.S_IFDIR,
                st_file_attributes=getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400),
            )
        return real_lstat(path)

    monkeypatch.setattr(Path, "lstat", lstat_with_reparse)

    with pytest.raises(IterateAppendError, match="symlink/reparse"):
        append_iterate_entry(tmp_path, _entry())

    assert not managed.exists()


def test_f5c_rejects_foreign_current_snapshot_before_writing_either_artifact(tmp_path):
    _seed_config(tmp_path)
    (tmp_path / "shipwright_test_results.json").write_bytes(
        _raw("iterate-2026-08-03-foreign")
    )

    with pytest.raises(IterateAppendError, match="belongs to"):
        append_iterate_entry(tmp_path, _entry())

    assert not evidence_file_for(tmp_path, RUN_ID).exists()
    assert not (tmp_path / ".shipwright/agent_docs/iterates" / f"{RUN_ID}.json").exists()


def test_artifact_only_crash_state_is_repaired_by_writing_the_summary(tmp_path):
    _seed_config(tmp_path)
    raw = _raw()
    install_immutable_evidence(tmp_path, RUN_ID, raw)
    (tmp_path / "shipwright_test_results.json").write_bytes(raw)

    result = append_iterate_entry(tmp_path, _entry())

    assert result["test_results_created"] is False
    summary = tmp_path / ".shipwright/agent_docs/iterates" / f"{RUN_ID}.json"
    assert json.loads(summary.read_text(encoding="utf-8"))["run_id"] == RUN_ID


def test_legacy_summary_only_state_is_repaired_from_validated_current_bytes(tmp_path):
    _seed_config(tmp_path)
    summary = tmp_path / ".shipwright/agent_docs/iterates" / f"{RUN_ID}.json"
    summary.parent.mkdir(parents=True)
    summary.write_text(json.dumps(_entry()), encoding="utf-8")
    raw = _raw()
    (tmp_path / "shipwright_test_results.json").write_bytes(raw)

    append_iterate_entry(tmp_path, _entry())

    assert evidence_file_for(tmp_path, RUN_ID).read_bytes() == raw
