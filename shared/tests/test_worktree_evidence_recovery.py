"""P1.14: post-P1.11 immutable test-evidence recovery from retained worktrees.

Locks in the two exact-byte recoveries (P2.03 triage-defer-lifecycle, P2.05
grade-snapshot-dedup) and the supplemental audit manifest that records them
plus the two runs correctly excluded as inherited-stale evidence. The
original P1.11 backfill manifest (test-results-backfill-manifest.json) must
stay byte-for-byte unedited -- this run supplements it, never rewrites it.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from lib.iterate_test_results import validate_evidence_bytes
from tools.verifiers.git_blob_read import GitReadError, committed_bytes_reader

_REPO_ROOT = Path(__file__).resolve().parents[2]
# origin/main tip this run branched from, at the time these two runs were
# validated as reachable durable F5c summaries (main == origin/main then).
# Pinned rather than live "origin/main": the commit is immutable and stays
# an ancestor of main forever, so the check keeps working without a fetch.
_VALIDATED_MAIN_TIP = "d6b2124a3843c392ed52147938ca796207d88b93"
_ITERATES = _REPO_ROOT / ".shipwright" / "agent_docs" / "iterates"
_ORIGINAL_MANIFEST = _ITERATES / "test-results-backfill-manifest.json"
_SUPPLEMENTAL_MANIFEST = (
    _ITERATES / "test-results-worktree-evidence-recovery-manifest.json"
)

_RECOVERED = {
    "iterate-2026-08-01-triage-defer-lifecycle": (
        "db508c455a3b19ef3d39ad206b58d2c4587619679e0c101a362a4ff942acb484",
        3456,
    ),
    "iterate-2026-08-01-grade-snapshot-dedup": (
        "9cff8b81d86c788a3072f888e5808f9466a7b57f05c54d9d8cc5f081536bd04a",
        6863,
    ),
}

_UNAVAILABLE_STALE = {
    "iterate-2026-08-01-verify-local-surface-gates",
    "iterate-2026-08-01-collect-test-ids-verbosity",
}

_CONFIRMED_SELF_DELIVERED = "iterate-2026-08-02-ensure-shared-cache-fanout"

# Hardcoded at authoring time -- a real byte-for-byte lock, not a semantic proxy.
# This is the hash of the COMMITTED GIT BLOB (read via git cat-file, below), not
# of a working-tree read: a working-tree read is subject to checkout-time EOL
# translation (Windows CRLF vs the LF the blob is actually stored as), so
# hashing raw read_bytes() output is platform-dependent and hashes a DIFFERENT
# value in CI than it does locally on Windows.
_ORIGINAL_MANIFEST_SHA256 = (
    "78f28cc2f91afe613df30e5653d8148c0c80bbded2efec433d9e7d38567ce4ff"
)


def test_recovered_evidence_matches_declared_bytes_and_validates():
    for run_id, (expected_sha256, expected_bytes) in _RECOVERED.items():
        artifact = _ITERATES / f"{run_id}.test-results.json"
        raw = artifact.read_bytes()

        assert len(raw) == expected_bytes
        assert hashlib.sha256(raw).hexdigest() == expected_sha256

        doc = validate_evidence_bytes(raw, run_id)
        assert doc["iterate_latest"]["run_id"] == run_id


def test_recovered_runs_have_a_durable_f5c_summary_reachable_from_main():
    # Checks git-history reachability at the pinned commit only -- NOT that the
    # compact <run_id>.json summary still exists in the current checkout. F5c's
    # 50-entry retention window is an intentional, documented recency cache over
    # those summaries (references/F5c.md: "a 50-run recency cache, not the
    # historical record"), so any later iterate's ordinary retention sweep can
    # evict these two once enough newer runs land -- that is not data loss, it
    # is the designed behavior. What must stay permanent is reachability of the
    # committed blob at this pinned commit, which retention (a working-tree
    # delete) can never touch (iterate-2026-08-08-cache-sync-add-detection-gap:
    # the 61st entry's retention sweep evicted both from the checkout and broke
    # the stronger, undocumented "must still exist locally" version of this
    # assertion this test carried before).
    reader = committed_bytes_reader(_REPO_ROOT, _VALIDATED_MAIN_TIP)
    for run_id in _RECOVERED:
        rel = f".shipwright/agent_docs/iterates/{run_id}.json"
        try:
            committed = reader(rel)
        except GitReadError as exc:  # pragma: no cover - fails closed, not silently
            raise AssertionError(f"cannot read {rel} at {_VALIDATED_MAIN_TIP[:8]}: {exc}")
        assert committed is not None, f"{rel} is absent from origin/main tip"
        doc = json.loads(committed.decode("utf-8"))
        assert doc["run_id"] == run_id


def test_original_backfill_manifest_is_unedited():
    reader = committed_bytes_reader(_REPO_ROOT, _VALIDATED_MAIN_TIP)
    rel = ".shipwright/agent_docs/iterates/test-results-backfill-manifest.json"
    try:
        committed = reader(rel)
    except GitReadError as exc:  # pragma: no cover - fails closed, not silently
        raise AssertionError(f"cannot read {rel} at {_VALIDATED_MAIN_TIP[:8]}: {exc}")
    assert committed is not None, f"{rel} is absent from the validated main tip"

    # Byte-for-byte lock against the committed GIT BLOB (platform-independent):
    # any reformat, reorder, or field edit fails this, not just the two
    # run_ids this change happens to care about.
    assert hashlib.sha256(committed).hexdigest() == _ORIGINAL_MANIFEST_SHA256

    # Local checkout must not diverge either, modulo checkout-time EOL translation.
    raw = _ORIGINAL_MANIFEST.read_bytes()
    assert raw.replace(b"\r\n", b"\n") == committed.replace(b"\r\n", b"\n")

    doc = json.loads(raw.decode("utf-8"))
    assert doc["backfill_run_id"] == "iterate-2026-08-03-preserve-test-evidence"
    recovered_ids = {row["run_id"] for row in doc["recovered"]}
    unavailable_ids = {row["run_id"] for row in doc["unavailable"]}
    # The two P1.14 recoveries must never be back-dated into the P1.11 manifest.
    assert not recovered_ids & set(_RECOVERED)
    assert "iterate-2026-08-01-grade-snapshot-dedup" in unavailable_ids


def test_supplemental_manifest_records_recoveries_and_exclusions():
    doc = json.loads(_SUPPLEMENTAL_MANIFEST.read_text(encoding="utf-8"))

    assert doc["schema_version"] == 1
    assert doc["supplements"] == (
        ".shipwright/agent_docs/iterates/test-results-backfill-manifest.json"
    )

    recovered_by_id = {row["run_id"]: row for row in doc["recovered"]}
    assert set(recovered_by_id) == set(_RECOVERED)
    for run_id, (expected_sha256, expected_bytes) in _RECOVERED.items():
        row = recovered_by_id[run_id]
        assert row["sha256"] == expected_sha256
        assert row["bytes"] == expected_bytes
        assert row["embedded_run_id_matches_target"] is True
        artifact = _REPO_ROOT / row["artifact"]
        assert artifact.is_file()
        assert hashlib.sha256(artifact.read_bytes()).hexdigest() == expected_sha256

    unavailable_ids = {row["run_id"] for row in doc["unavailable"]}
    assert unavailable_ids == _UNAVAILABLE_STALE
    for row in doc["unavailable"]:
        assert row["reason"].strip()
        assert "iterate-2026-07-28-main-self-heal" in row["reason"]

    confirmed_ids = {row["run_id"] for row in doc["confirmed_self_delivered"]}
    assert confirmed_ids == {_CONFIRMED_SELF_DELIVERED}


def test_stale_worktree_run_ids_are_not_imported_as_their_own_evidence():
    for run_id in _UNAVAILABLE_STALE:
        artifact = _ITERATES / f"{run_id}.test-results.json"
        assert not artifact.exists()


def test_p1_10_already_self_delivered_its_own_immutable_snapshot():
    artifact = _ITERATES / f"{_CONFIRMED_SELF_DELIVERED}.test-results.json"
    raw = artifact.read_bytes()

    doc = validate_evidence_bytes(raw, _CONFIRMED_SELF_DELIVERED)
    assert doc["iterate_latest"]["run_id"] == _CONFIRMED_SELF_DELIVERED
