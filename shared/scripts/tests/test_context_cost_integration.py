"""END-TO-END integration test: Stop hook -> statusline -> pressure estimate.

``cross_component`` gate (context-cost-meter touches
``shared/scripts/hooks/track_context_cost.py``, matching the
``hooks/.+\\.py$`` cross-component pattern): a real-scenario test proving the
components this feature adds actually compose, not three units mocked past
each other. Real transcript file on disk, real Stop-hook invocation (stdin +
env, exactly as Claude Code fires it), real statusline stdin/stdout contract,
real ``estimate_context_pressure.py --source context-cost`` consumer — the
SAME per-session JSON file passed hand to hand, nothing patched out.

Test Completeness Ledger row 15,
``.shipwright/planning/iterate/2026-08-07-context-cost-meter.md``.
"""

from __future__ import annotations

import io
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent.parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from hooks import track_context_cost  # noqa: E402
from tools import context_cost_statusline  # noqa: E402
from tools.estimate_context_pressure import estimate_pressure_context_cost  # noqa: E402

_T0 = datetime(2026, 8, 7, 12, 0, 0, tzinfo=timezone.utc)


def _write_transcript(path: Path, n_calls: int) -> None:
    records = [
        {
            "type": "assistant",
            "requestId": f"req-{i}",
            "timestamp": _T0.isoformat(),
            "message": {"model": "claude-sonnet-5", "usage": {"input_tokens": 1000}},
        }
        for i in range(n_calls)
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in records) + "\n",
        encoding="utf-8",
    )


def test_hook_write_flows_through_statusline_and_pressure_estimate(tmp_path, monkeypatch, capsys):
    session_id = "sess-integration"
    project_root = tmp_path
    transcript = project_root / "transcript.jsonl"
    _write_transcript(transcript, n_calls=3)

    (project_root / "shipwright_run_config.json").write_text("{}", encoding="utf-8")
    monkeypatch.setenv("SHIPWRIGHT_PROJECT_ROOT", str(project_root))
    monkeypatch.setenv("SHIPWRIGHT_SESSION_ID", session_id)
    monkeypatch.delenv("SHIPWRIGHT_RUN_ID", raising=False)

    # 1. The Stop hook fires exactly as Claude Code invokes it: JSON on stdin,
    #    nothing on the CLI.
    stop_payload = {"session_id": session_id, "transcript_path": str(transcript)}
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(stop_payload)))
    rc = track_context_cost.main()
    assert rc == 0

    # 2. The statusline script reads that SAME file via its own stdin
    #    contract (session_id + workspace.current_dir) -- no shared code path
    #    with the hook beyond the file on disk.
    statusline_payload = {"session_id": session_id, "workspace": {"current_dir": str(project_root)}}
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(statusline_payload)))
    rc = context_cost_statusline.main()
    assert rc == 0
    line = capsys.readouterr().out.strip()
    assert "3 calls" in line
    assert "$" in line

    # 3. estimate_context_pressure.py --source context-cost reads the SAME
    #    file, keyed purely by SHIPWRIGHT_SESSION_ID (no stdin at all) --
    #    proving the writer/reader session-id agreement holds through a real
    #    hook firing, not just the unit-level parity test.
    result = estimate_pressure_context_cost(project_root, threshold=2, mode="builder")
    assert result["tool_calls"] == 3
    assert result["source"] == "context-cost"
    assert result["cost_usd"] > 0
    assert result["recommend_checkpoint"] is True  # 3 >= threshold 2


def test_pressure_estimate_reports_no_data_before_any_stop_has_fired(tmp_path, monkeypatch):
    # The composition's graceful-absence leg: nothing has run yet.
    monkeypatch.setenv("SHIPWRIGHT_SESSION_ID", "sess-never-stopped")
    result = estimate_pressure_context_cost(tmp_path, threshold=120, mode="builder")
    assert result["tool_calls"] == 0
    assert result["no_data"] is True
    assert result["recommend_checkpoint"] is False
