"""Boundary Probe: finalize snapshot preserves runtime bytes verbatim.

iterate-2026-05-27-tracked-artifacts-single-producer-and-finalize-sandbox
`touches_io_boundary` round-trip:

* Producer: Stop-hook writes ``runtime/triage_inbox.md`` via
  ``aggregate_triage.main(--out-dir runtime/)``.
* File-on-disk: ``.shipwright/agent_docs/runtime/triage_inbox.md``
* Consumer: ``finalize_iterate._snapshot_triage_runtime`` copies runtime
  to tracked atomically, then unlinks runtime.

The boundary assertion is **byte-identity** across the producer→file→
consumer pipeline. Stop-hook output and snapshot-copy output MUST be
identical because the snapshot is literally a file copy.

This is the empirical asymptote referenced in the iterate spec's
Confidence Calibration section: if THIS probe finds no finding, the
marginal probe yields no signal (per asymptote heuristic).
"""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path



REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "shared" / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))


def _seed(project_root: Path) -> None:
    (project_root / "shipwright_run_config.json").write_text(
        json.dumps({"status": "complete"}),
        encoding="utf-8",
    )
    sw = project_root / ".shipwright"
    sw.mkdir(parents=True, exist_ok=True)
    # A handful of triage entries so the renderer has non-trivial content.
    items = [
        {
            "event": "append",
            "id": "trg-roundtrip-1",
            "ts": "2026-05-27T08:00:00Z",
            "originalTs": "2026-05-27T08:00:00Z",
            "source": "compliance",
            "severity": "high",
            "kind": "bug",
            "title": "boundary-probe item",
            "detail": "test fixture",
            "evidencePath": "n/a",
            "runId": "iterate-roundtrip",
            "commit": "deadbeef",
            "dedupKey": "compliance:boundary",
            "launchPayload": None,
            "frId": None,
            "suiteId": None,
            "eventId": None,
            "status": "triage",
            "suggestedPriority": "P1",
            "suggestedDomain": "engineering",
        },
    ]
    (sw / "triage.jsonl").write_text(
        "\n".join(json.dumps(it) for it in items) + "\n",
        encoding="utf-8",
    )
    # Empty events.jsonl — banner stays "(no events)" deterministically.
    (project_root / "shipwright_events.jsonl").write_text("", encoding="utf-8")


def test_runtime_to_tracked_byte_identity(tmp_path: Path) -> None:
    _seed(tmp_path)

    # Producer: run aggregate_triage with --out-dir runtime/, matching
    # the Stop-hook invocation exactly.
    from tools import aggregate_triage  # noqa: E402

    runtime_dir = tmp_path / ".shipwright" / "agent_docs" / "runtime"
    rc = aggregate_triage.main([
        "--project-root", str(tmp_path),
        "--out-dir", str(runtime_dir),
        "--now", "2026-05-27T08:00:00Z",  # deterministic banner
    ])
    assert rc == 0
    runtime_file = runtime_dir / "triage_inbox.md"
    assert runtime_file.is_file()
    runtime_bytes = runtime_file.read_bytes()

    # Consumer: finalize_iterate._snapshot_triage_runtime copies runtime
    # to tracked. We test the helper in isolation to keep the probe focus
    # narrow to the boundary.
    importlib.invalidate_caches()
    from tools import finalize_iterate as fi  # noqa: E402

    outcome = fi._snapshot_triage_runtime(tmp_path)
    assert outcome == "copied", f"expected 'copied', got {outcome!r}"

    tracked_file = tmp_path / ".shipwright" / "agent_docs" / "triage_inbox.md"
    assert tracked_file.is_file()
    tracked_bytes = tracked_file.read_bytes()

    # The boundary assertion: byte-for-byte equality.
    assert tracked_bytes == runtime_bytes, (
        f"snapshot copy lost {len(runtime_bytes) - len(tracked_bytes)} "
        "bytes; producer/consumer divergence detected — this is the "
        "round-trip failure mode the probe protects against."
    )

    # Idempotency arm: runtime file should be unlinked after snapshot.
    assert not runtime_file.exists(), (
        "snapshot must unlink runtime/triage_inbox.md after copy so the "
        "next Stop hook starts from a clean baseline"
    )


def test_snapshot_idempotent_on_second_run(tmp_path: Path) -> None:
    """Second snapshot call with empty runtime produces no diff in tracked.

    The tracked file's content may differ between first/second runs only
    if the underlying triage.jsonl + events.jsonl changed — they don't,
    in this fixture. Both the runtime-write (Stop-hook-shape) AND the
    seed-write (finalize internal) deliberately omit ``--now`` so the
    timestamp banner derives from events.jsonl identically in both paths
    (the real Stop hook does the same — it doesn't pass ``--now`` either).
    With events.jsonl empty, the banner is the deterministic "(no events)"
    string in both renders.
    """
    _seed(tmp_path)
    from tools import aggregate_triage  # noqa: E402

    runtime_dir = tmp_path / ".shipwright" / "agent_docs" / "runtime"
    aggregate_triage.main([
        "--project-root", str(tmp_path),
        "--out-dir", str(runtime_dir),
    ])

    importlib.invalidate_caches()
    from tools import finalize_iterate as fi  # noqa: E402

    fi._snapshot_triage_runtime(tmp_path)
    tracked_file = tmp_path / ".shipwright" / "agent_docs" / "triage_inbox.md"
    first = tracked_file.read_bytes()

    # Second call — runtime is empty (first call unlinked it), so this
    # exercises the seed path. The seed path produces different bytes
    # ONLY if events.jsonl changed; it hasn't.
    fi._snapshot_triage_runtime(tmp_path)
    second = tracked_file.read_bytes()

    # The seed path re-renders deterministically from the same triage.jsonl
    # + same events.jsonl. Bytes must match.
    assert first == second, (
        "second finalize call re-rendered tracked triage_inbox.md with "
        "different bytes; the perpetual-dirty-tree class is still open."
    )


def test_aggregate_triage_out_dir_rejects_escape(tmp_path: Path) -> None:
    """External review OpenAI #10: --out-dir must refuse paths outside project.

    A producer that accepts an unconstrained --out-dir parameter could be
    coerced into writing outside the tree (symlink-walk, absolute escape,
    `..` traversal). Constrain to under --project-root.
    """
    _seed(tmp_path)
    outside = tmp_path.parent / "outside_escape"
    outside.mkdir(parents=True, exist_ok=True)

    from tools import aggregate_triage  # noqa: E402

    rc = aggregate_triage.main([
        "--project-root", str(tmp_path),
        "--out-dir", str(outside),
        "--now", "2026-05-27T08:00:00Z",
    ])
    assert rc == 2, (
        f"expected exit 2 for path-escape, got {rc} — write-safety guard "
        "is missing"
    )
    assert not (outside / "triage_inbox.md").exists(), (
        "aggregate_triage wrote outside project_root despite --out-dir "
        "constraint failing — this is a write-safety regression."
    )
