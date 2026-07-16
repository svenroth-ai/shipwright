"""LLM-leg + cross_component composition tests for the backfill engine (TT6).

The opt-in adjudication leg runs OFFLINE via P1's stubbed record/replay adapter
(no live call), honours the §11-R1 rule that a heuristic/LLM verdict may never
auto-write alone, and enforces the §11-R4 data controls (payload carries only
path + title + candidate FR ids — never a test body). The composition test proves
the engine's written tags feed the real TT1 ``test_links`` collector + manifest.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _backfill_support import (  # noqa: E402
    SpyAdjudicator,
    auto_frs,
    backfill_llm,
    copy_repo,
    import_p1_adapter,
    run,
    sig,
    tt1_manifest,
)


# --------------------------------------------------------------------------- #
# AC2 — title-similarity + LLM may NEVER auto-write alone (§11-R1)             #
# --------------------------------------------------------------------------- #

def test_title_and_llm_never_auto_write(tmp_path):
    repo = copy_repo(tmp_path)
    # A deliberately HIGH-confidence LLM verdict must still not authorise a write.
    spy = SpyAdjudicator(proposed_fr="FR-05.01", confidence=0.99)
    report = run(repo, apply=True, adjudicator=spy, use_llm=True)

    assert "FR-05.01" not in auto_frs(report)
    export = next(p for p in report["proposals"] if "test_export" in p["test"])
    assert set(export["candidates"][0]["signals"]) == {"title_similarity", "llm"}
    assert export["candidates"][0]["confidence"] < sig.AUTO_WRITE_THRESHOLD
    # No test body ever left the engine — only path + title + candidate FR ids.
    assert spy.payloads, "the residue must reach the LLM leg"
    for p in spy.payloads:
        assert set(p) == {"test_path", "test_title", "candidate_frs"}
        assert all(fr.startswith("FR-") for fr in p["candidate_frs"])


def test_llm_leg_offline_via_p1_record_replay_adapter(tmp_path):
    """The opt-in leg runs offline through P1's stubbed adapter (no live call)."""
    repo = copy_repo(tmp_path)
    rr = import_p1_adapter()
    payload = {
        "test_path": "tests/test_export.py",
        "test_title": "test_export_orders_to_csv",
        "candidate_frs": ["FR-05.01"],
    }
    cassette = tmp_path / "cassette.json"
    key = rr.RecordReplayAdapter.key_for(payload)
    cassette.write_text(json.dumps({"schema_version": 2, "interactions": {
        key: {"payload": payload, "response": {
            "proposed_fr": "FR-05.01", "confidence": 0.6, "auto_write": False}},
    }}), encoding="utf-8")
    adapter = rr.RecordReplayAdapter(cassette)
    report = run(repo, apply=False, adjudicator=adapter, use_llm=True)
    export = next(p for p in report["proposals"] if "test_export" in p["test"])
    assert "llm" in export["candidates"][0]["signals"]
    assert "FR-05.01" not in auto_frs(report)     # advisory only


def test_llm_disabled_by_default_is_deterministic(tmp_path):
    """Without --use-llm the adjudicator is never consulted (offline default)."""
    repo = copy_repo(tmp_path)
    spy = SpyAdjudicator()
    report = run(repo, apply=False, adjudicator=spy, use_llm=False, split_convention=True)
    assert spy.payloads == []                      # leg never fired
    assert auto_frs(report) == {"FR-05.02", "FR-06.01"}


def test_secrets_are_redacted_before_leaving_the_process(tmp_path):
    """§11-R4 'redact secrets': a token embedded in a test title is scrubbed from
    the payload before it reaches the adjudicator."""
    repo = copy_repo(tmp_path)
    # Build the token at runtime so no secret-shaped literal sits in this source.
    token = "ghp" + "_" + "a" * 30
    leak = repo / "tests/leaky.test.ts"
    leak.write_text(
        "import { test } from 'vitest';\n"
        f"test('auth flow with {token} works', () => {{}});\n",
        encoding="utf-8")
    spy = SpyAdjudicator(proposed_fr=None)
    run(repo, apply=False, adjudicator=spy, use_llm=True)
    leaked = [p for p in spy.payloads if "auth flow" in p["test_title"]]
    assert leaked, "the leaky test must reach the LLM residue"
    assert token not in leaked[0]["test_title"]
    assert "[REDACTED]" in leaked[0]["test_title"]


def test_llm_payload_guard_refuses_a_body():
    with pytest.raises(ValueError):
        backfill_llm.validate_payload(
            {"test_path": "x", "test_title": "y", "candidate_frs": [], "body": "secret"})
    with pytest.raises(ValueError):
        backfill_llm.validate_payload(
            {"test_path": "x", "test_title": "B" * 5000, "candidate_frs": []})
    with pytest.raises(ValueError):
        backfill_llm.validate_payload(
            {"test_path": "x", "test_title": "y", "candidate_frs": ["not-an-fr"]})


def test_untrusted_llm_out_of_set_fr_is_dropped(tmp_path):
    repo = copy_repo(tmp_path)
    # The adjudicator (untrusted) proposes an FR NOT in the candidate set → the
    # engine must ignore it, never fabricate a proposal for it.
    rogue = SpyAdjudicator(proposed_fr="FR-99.99", confidence=0.99)
    report = run(repo, apply=False, adjudicator=rogue, use_llm=True)
    assert "FR-99.99" not in auto_frs(report)
    assert not any(
        any(c["fr"] == "FR-99.99" for c in p["candidates"]) for p in report["proposals"])


# --------------------------------------------------------------------------- #
# cross_component — the engine composes with the TT1 collector + manifest      #
# (category:"integration" behavior for the composition gate / F5 ledger)       #
# --------------------------------------------------------------------------- #

def test_backfill_feeds_tt1_manifest_end_to_end(tmp_path):
    """Integration: backfill writes tags → TT1 ``test_links`` builds a manifest
    whose coverage links + orphan reflect exactly the engine's decisions."""
    repo = copy_repo(tmp_path)
    run(repo, apply=True, split_convention=True)   # convention repo: unique split writes

    manifest = tt1_manifest(repo)
    by_id = {v["id"]: v for v in manifest["requirements"].values()}

    # The auto-written tags are now first-class coverage links in the manifest.
    e2e = [t["id"] for t in by_id["FR-05.02"]["tests"].get("e2e", [])]
    integ = [t["id"] for t in by_id["FR-06.01"]["tests"].get("integration", [])]
    assert any("FR-05.02-dashboard.spec.ts" in t for t in e2e)
    assert any("06-archive.test.ts" in t for t in integ)

    # The removed-FR orphan the engine surfaced is the manifest's orphan too.
    assert any(o["tagged_fr"] == "FR-05.09" for o in manifest["orphans"])
