"""Cross-process integration coverage for the campaign_progress.py -> autonomous_loop.py
stdin pipe (iterate-2026-09-03-review-scratch-path).

`campaign-mode.md` step 2 no longer writes `campaign_units.json` to a scratch
path and re-reads it — it pipes `campaign_progress.py list-units` straight
into `autonomous_loop.py init --units-from -`. This is the cross_component
integration coverage (category:"integration") for that composition: two real
subprocesses, real pipe, proving the producer's JSON shape is exactly what the
consumer's stdin branch expects.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_CAMPAIGN_PROGRESS = (
    _REPO_ROOT / "plugins" / "shipwright-iterate" / "scripts" / "tools" / "campaign_progress.py"
)
_AUTONOMOUS_LOOP = _REPO_ROOT / "shared" / "scripts" / "lib" / "autonomous_loop.py"


def test_list_units_piped_into_init_composes(tmp_path):
    campaign_dir = tmp_path / "campaign"
    campaign_dir.mkdir()
    (campaign_dir / "status.json").write_text(json.dumps({
        "campaign": "pipe-composition",
        "sub_iterates": [
            {"id": "S1", "slug": "alpha", "spec_path": "s1.md"},
            {"id": "S2", "slug": "bravo", "spec_path": "s2.md"},
        ],
    }), encoding="utf-8")

    producer = subprocess.run(  # nosec B603 - fixed argv, shell=False
        [sys.executable, str(_CAMPAIGN_PROGRESS), "list-units", "--campaign-dir", str(campaign_dir)],
        capture_output=True, text=True, check=False, timeout=60,
    )
    assert producer.returncode == 0, producer.stderr

    state_path = tmp_path / "loop_state.json"
    consumer = subprocess.run(  # nosec B603 - fixed argv, shell=False
        [
            sys.executable, str(_AUTONOMOUS_LOOP), "init",
            "--state", str(state_path), "--kind", "sub_iterate",
            "--units-from", "-", "--branch-strategy", "serial",
            "--root-session-id", "root",
        ],
        input=producer.stdout, capture_output=True, text=True, check=False, timeout=60,
    )
    assert consumer.returncode == 0, consumer.stderr

    state = json.loads(state_path.read_text(encoding="utf-8"))
    ids = [u["id"] for u in state["units"]]
    assert ids == ["S1", "S2"], state


def test_init_reports_a_clean_error_on_empty_stdin(tmp_path):
    """A producer that emits nothing (upstream failure, empty campaign)
    must not surface as an unhandled JSONDecodeError traceback."""
    state_path = tmp_path / "loop_state.json"
    consumer = subprocess.run(  # nosec B603 - fixed argv, shell=False
        [
            sys.executable, str(_AUTONOMOUS_LOOP), "init",
            "--state", str(state_path), "--kind", "sub_iterate",
            "--units-from", "-", "--branch-strategy", "serial",
            "--root-session-id", "root",
        ],
        input="", capture_output=True, text=True, check=False, timeout=60,
    )
    assert consumer.returncode == 1, consumer.stdout
    assert "Traceback" not in consumer.stderr, consumer.stderr
    assert "No units JSON received on stdin" in consumer.stderr, consumer.stderr
