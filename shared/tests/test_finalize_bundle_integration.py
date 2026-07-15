"""END-TO-END integration test for finalize_bundle.py
(iterate-2026-07-15-finalize-bundle).

Proves the bundle really invokes the FIVE finalization sub-tools as subprocesses
and they COMPOSE to produce the real artifacts — the voluntary
``category:"integration"`` coverage for a multi-tool composition change. The
unit tests (test_finalize_bundle.py) prove argv construction with an injected
runner; this proves the whole thing runs on disk with the actual tools, and that
a WHOLE-BUNDLE retry after the finalize succeeded is idempotent (no duplicate
decision-drop / changelog-drop / iterate-entry / event) — the retry-safety
guarantee that rests on the two idempotency fixes to write_decision_drop /
write_changelog_drop.

Real subprocesses via ``sys.executable finalize_bundle.py`` on a minimal on-disk
fixture project. NOT marked ``slow`` so it gates in CI.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_BUNDLE = _REPO_ROOT / "shared" / "scripts" / "tools" / "finalize_bundle.py"

_RUN_ID = "iterate-2026-07-15-fb-integration"


def _init_fixture(root: Path) -> None:
    """Minimal project layout the five sub-tools need to run for real."""
    (root / "shipwright_run_config.json").write_text(
        json.dumps({"status": "complete", "iterate_history": []}), encoding="utf-8",
    )
    (root / ".shipwright" / "agent_docs").mkdir(parents=True, exist_ok=True)
    (root / ".shipwright" / "compliance").mkdir(parents=True, exist_ok=True)
    (root / "shipwright_events.jsonl").write_text("", encoding="utf-8")
    # F5b's compliance regen consumes the F5 test-results; provide a valid one
    # WITH a top-level coverage block (W4) so the fixture mirrors reality.
    (root / "shipwright_test_results.json").write_text(
        json.dumps({
            "iterate_latest": {"run_id": _RUN_ID, "unit": {"status": "pass"}},
            "coverage": {"total": 80.0},
        }),
        encoding="utf-8",
    )


def _payload(run_id: str = _RUN_ID) -> dict:
    return {
        "run_id": run_id,
        "artifact_sync": {"skip": True},  # no 2-commit git history in this fixture
        "decision": {
            "section": "Iterate — change: finalize bundle",
            "title": "Bundle the finalize round-trips",
            "context": "finalize is slow from sequential LLM turns",
            "decision": "one orchestrator invokes the five tools unchanged",
            "consequences": "~6 turns collapse to ~2",
            "architecture_impact": "none",
        },
        "changelog": [{"category": "Changed", "bullet": "Finalize runs as one bundled call"}],
        "iterate_entry": {
            "type": "change", "complexity": "medium", "branch": "iterate/fb",
            "tests_passed": True, "adr": run_id,
        },
        "finalize": {
            "reason": "iterate: finalize bundle",
            "event_extras": {
                "intent": "change",
                "description": "finalize_bundle orchestrator",
                "summary": "the finalize phase now runs as one bundled call",
                "spec_impact": "none",
                "spec_impact_justification": "artifacts byte-identical; only turn-taking collapses",
                "change_type": "tooling",
                "none_reason": "behavior-preserving finalization orchestration",
                "tests": {"passed": 1, "total": 1, "e2e_run": False},
            },
        },
    }


def _run_bundle(root: Path, payload: dict) -> dict:
    payload_file = root / "bundle_payload.json"
    payload_file.write_text(json.dumps(payload), encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, str(_BUNDLE),
         "--payload-file", str(payload_file), "--project-root", str(root)],
        capture_output=True, text=True, timeout=120,
    )
    # Bundle contract: exactly ONE JSON document on stdout (success or failure).
    result = json.loads(proc.stdout)
    result["_returncode"] = proc.returncode
    result["_stderr"] = proc.stderr
    return result


def _decision_drops(root: Path) -> list[Path]:
    d = root / ".shipwright" / "agent_docs" / "decision-drops"
    return sorted(d.glob("*.json")) if d.is_dir() else []


def _changelog_drops(root: Path) -> list[Path]:
    d = root / "CHANGELOG-unreleased.d"
    return sorted(d.rglob("*.md")) if d.is_dir() else []


def _work_events(root: Path) -> list[dict]:
    text = (root / "shipwright_events.jsonl").read_text(encoding="utf-8")
    events = [json.loads(ln) for ln in text.splitlines() if ln.strip()]
    return [e for e in events if e.get("type") == "work_completed"]


def test_bundle_composes_the_real_tools_and_writes_every_artifact(tmp_path):
    """category:integration — the bundle invokes all five tools for real and
    each produces its artifact with the payload's content."""
    root = tmp_path
    _init_fixture(root)
    result = _run_bundle(root, _payload())

    assert result["_returncode"] == 0, result.get("_stderr")
    assert result["success"] is True, result
    assert result["failed_step"] is None
    for step in ("F3", "F4", "F5c", "F5b"):
        assert result["steps"][step]["status"] == "ok", (step, result["steps"][step])
    assert result["steps"]["F1"]["status"] == "skipped"

    # F3 decision-drop carries the payload's fields.
    drops = _decision_drops(root)
    assert len(drops) == 1
    drop = json.loads(drops[0].read_text(encoding="utf-8"))
    assert drop["title"] == "Bundle the finalize round-trips"
    assert drop["architecture_impact"] == "none"

    # F4 changelog-drop carries the payload's bullet.
    cl = _changelog_drops(root)
    assert len(cl) == 1
    assert cl[0].parent.name == "Changed"
    assert cl[0].read_text(encoding="utf-8").strip() == "Finalize runs as one bundled call"

    # F5c iterate-entry written for this run.
    entry = root / ".shipwright" / "agent_docs" / "iterates" / f"{_RUN_ID}.json"
    assert entry.exists()
    assert json.loads(entry.read_text(encoding="utf-8"))["type"] == "change"

    # F5b recorded exactly one work_completed event with the classification.
    events = _work_events(root)
    assert len(events) == 1
    assert events[0]["change_type"] == "tooling"
    assert events[0]["spec_impact"] == "none"

    # W4: F5b's compliance regen must NOT drop the top-level coverage block.
    tr = json.loads((root / "shipwright_test_results.json").read_text(encoding="utf-8"))
    assert tr["coverage"]["total"] == 80.0


def test_whole_bundle_retry_is_idempotent(tmp_path):
    """category:integration — re-running the WHOLE bundle (the recovery path)
    produces NO duplicate artifacts, thanks to the drop-tool idempotency fixes +
    finalize_iterate's event idempotency."""
    root = tmp_path
    _init_fixture(root)

    first = _run_bundle(root, _payload())
    assert first["success"] is True, first.get("_stderr")

    second = _run_bundle(root, _payload())
    assert second["success"] is True, second.get("_stderr")

    # No duplicates on the second whole-bundle run (all four named artifacts).
    assert len(_decision_drops(root)) == 1
    assert len(_changelog_drops(root)) == 1
    assert len(_work_events(root)) == 1
    entries = list((root / ".shipwright" / "agent_docs" / "iterates").glob(f"{_RUN_ID}.json"))
    assert len(entries) == 1  # file-per-run_id — retry overwrites, never duplicates


def test_partial_failure_then_whole_bundle_retry_recovers_without_dups(tmp_path):
    """category:integration — the REAL recovery scenario: F5b fails on the first
    pass (FR-gate reject) AFTER F3/F4/F5c already wrote, then the whole bundle is
    re-run with a corrected classification. No duplicate decision/changelog drops,
    exactly one work_completed event."""
    root = tmp_path
    _init_fixture(root)

    # First pass: spec_impact=modify with NO affected_frs and NO change_type —
    # finalize_iterate's ADR-059 FR-gate rejects it, so F5b fails after F3/F4/F5c.
    bad = _payload()
    bad["finalize"]["event_extras"] = {"intent": "change", "spec_impact": "modify",
                                        "description": "unclassified"}
    first = _run_bundle(root, bad)
    assert first["_returncode"] == 1
    assert first["success"] is False and first["failed_step"] == "F5b"
    assert len(_decision_drops(root)) == 1   # F3 wrote
    assert len(_changelog_drops(root)) == 1  # F4 wrote
    assert len(_work_events(root)) == 0      # gate rejected BEFORE the event write

    # Retry the WHOLE bundle with a valid (No-FR/tooling) classification.
    second = _run_bundle(root, _payload())
    assert second["success"] is True, second.get("_stderr")
    assert len(_decision_drops(root)) == 1   # F3 deduped, not duplicated
    assert len(_changelog_drops(root)) == 1  # F4 deduped, not duplicated
    assert len(_work_events(root)) == 1       # exactly one event now


def _run_manual_sequence(root: Path, payload: dict) -> None:
    """Invoke the five tools the DOCUMENTED way, one subprocess each (F1 skipped,
    mirroring the payload) — the baseline the bundle must match."""
    tools = _REPO_ROOT / "shared" / "scripts" / "tools"
    run_id = payload["run_id"]
    d = payload["decision"]
    _sh([sys.executable, str(tools / "write_decision_drop.py"),
         "--project-root", str(root), "--run-id", run_id,
         "--section", d["section"], "--title", d["title"], "--context", d["context"],
         "--decision", d["decision"], "--consequences", d["consequences"],
         "--architecture-impact", d["architecture_impact"]])
    for item in payload["changelog"]:
        _sh([sys.executable, str(tools / "write_changelog_drop.py"),
             "--project-root", str(root), "--run-id", run_id,
             "--category", item["category"], "--bullet", item["bullet"]])
    _sh([sys.executable, str(tools / "append_iterate_entry.py"),
         "--project-root", str(root), "--run-id", run_id,
         "--entry-json", json.dumps(payload["iterate_entry"])])
    fin = payload["finalize"]
    _sh([sys.executable, str(tools / "finalize_iterate.py"),
         "--project-root", str(root), "--run-id", run_id,
         "--reason", fin["reason"], "--event-extras-json", json.dumps(fin["event_extras"])])


def _sh(argv: list) -> None:
    proc = subprocess.run(argv, capture_output=True, text=True, timeout=120)
    assert proc.returncode == 0, f"{argv[1]} failed: {proc.stderr}"


_VOLATILE_EVENT_KEYS = {"id", "ts", "session", "commit", "phase_timings"}


def _norm_event(e: dict) -> dict:
    return {k: v for k, v in e.items() if k not in _VOLATILE_EVENT_KEYS}


def test_bundle_output_equals_the_manual_sequence(tmp_path):
    """category:integration — the CORE invariant proof ('do not change what any
    tool WRITES'): on two byte-identical fixtures with the same payload, the
    bundle path produces artifacts EQUIVALENT (modulo the event's id/timestamp)
    to invoking the five tools manually in sequence."""
    bundle_root = tmp_path / "bundle"
    manual_root = tmp_path / "manual"
    bundle_root.mkdir()
    manual_root.mkdir()
    _init_fixture(bundle_root)
    _init_fixture(manual_root)

    payload = _payload()
    result = _run_bundle(bundle_root, payload)
    assert result["success"] is True, result.get("_stderr")
    _run_manual_sequence(manual_root, payload)

    # Decision-drop: identical (date is same-day, commit "" on both).
    assert (json.loads(_decision_drops(bundle_root)[0].read_text(encoding="utf-8"))
            == json.loads(_decision_drops(manual_root)[0].read_text(encoding="utf-8")))

    # Changelog-drop: byte-identical.
    assert (_changelog_drops(bundle_root)[0].read_bytes()
            == _changelog_drops(manual_root)[0].read_bytes())

    # Iterate-entry: identical modulo the tool-stamped `date` timestamp.
    be = json.loads((bundle_root / ".shipwright" / "agent_docs" / "iterates" / f"{_RUN_ID}.json")
                    .read_text(encoding="utf-8"))
    me = json.loads((manual_root / ".shipwright" / "agent_docs" / "iterates" / f"{_RUN_ID}.json")
                    .read_text(encoding="utf-8"))
    be.pop("date", None)
    me.pop("date", None)
    assert be == me

    # work_completed event: equivalent modulo id/timestamp/session/commit.
    assert _norm_event(_work_events(bundle_root)[0]) == _norm_event(_work_events(manual_root)[0])
