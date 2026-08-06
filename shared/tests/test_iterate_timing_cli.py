"""CLI for agent-emitted iterate-timing marks (iterate_timing.py start|end)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
_ITERATE_TIMING_PY = _SCRIPTS / "tools" / "iterate_timing.py"
sys.path.insert(0, str(_SCRIPTS))

from lib import iterate_timings_normalize as itn  # noqa: E402
from tools import iterate_timing as cli  # noqa: E402

RUN = "iterate-2026-08-04-iterate-timing-attribution"


def test_start_then_end_round_trips_through_normalize(tmp_path):
    assert cli.main(["start", "review", "--parent", "none",
                     "--project-root", str(tmp_path), "--run-id", RUN]) == 0
    assert cli.main(["end", "review", "--parent", "none",
                     "--project-root", str(tmp_path), "--run-id", RUN,
                     "--extra-json", json.dumps({"reviewer": "code-reviewer"})]) == 0

    valid, rejected = itn.normalize_iterate_timings(itn.read_raw_events(tmp_path, RUN))
    assert not rejected
    assert valid[0]["name"] == "review"
    assert valid[0]["extra"] == {"reviewer": "code-reviewer"}


def test_resume_across_real_separate_os_processes(tmp_path):
    """External code review: the sibling in-process test
    (test_sidecar_is_append_only_across_sequential_calls) calls the writer
    functions twice in the SAME Python process, which proves append-only
    statelessness but not genuine OS-process separation. This spawns two
    real `python iterate_timing.py` subprocesses — sharing nothing but the
    filesystem, exactly as a resumed Claude Code session would — proving the
    second invocation sees the first's write purely through the sidecar
    file, with no shared interpreter state to lean on."""
    env = {**os.environ}
    common = ["--parent", "none", "--project-root", str(tmp_path), "--run-id", RUN]
    start = subprocess.run(
        [sys.executable, str(_ITERATE_TIMING_PY), "start", "review", *common],
        capture_output=True, text=True, env=env)
    assert start.returncode == 0, start.stderr
    end = subprocess.run(
        [sys.executable, str(_ITERATE_TIMING_PY), "end", "review", *common],
        capture_output=True, text=True, env=env)
    assert end.returncode == 0, end.stderr

    valid, rejected = itn.normalize_iterate_timings(itn.read_raw_events(tmp_path, RUN))
    assert not rejected
    assert valid[0]["name"] == "review" and valid[0]["outcome"] == "completed"


def test_non_canonical_run_id_is_refused(tmp_path, capsys):
    rc = cli.main(["start", "review", "--parent", "none",
                   "--project-root", str(tmp_path), "--run-id", "not-canonical"])
    assert rc == 2
    assert itn.read_raw_events(tmp_path, "not-canonical") == []


def test_unknown_span_name_is_an_argparse_error(tmp_path):
    try:
        cli.main(["start", "bogus-span", "--parent", "none",
                 "--project-root", str(tmp_path), "--run-id", RUN])
        assert False, "argparse should have exited"
    except SystemExit as exc:
        assert exc.code == 2


def test_end_with_malformed_extra_json_is_refused(tmp_path):
    rc = cli.main(["end", "review", "--parent", "none",
                   "--project-root", str(tmp_path), "--run-id", RUN,
                   "--extra-json", "{not valid json"])
    assert rc == 2
