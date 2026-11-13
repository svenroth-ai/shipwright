"""Microbenchmark of the per-run drops layout at 300 files (issue 978, S8, KC5).

Kill criterion (DESIGN 8.5): a run-scoped read <= 20 ms and a whole-log read <= 0.3 s at 300 drop files.
The fixture is the real shape: this repo's real legacy log (about 1250 events, 3.5 MB) plus 300 drop files
of 4 events each, built from real event bodies.

* **whole log** = ``read_events_assembled`` (legacy + every drop, merged and sorted);
* **run-scoped read** = the run's own drop files (a name glob) plus the legacy log filtered to the run
  (a raw-text prefilter before parsing -- the product has no dedicated run-scoped reader, this is the
  DESIGN 4.1 definition spelled out with the shipped primitives); the figure WITHOUT the prefilter is
  recorded too, because parsing the whole legacy log is what costs on a big log;
* **per-write cost** = one ``append_event`` against the 300 existing files (the dedup scans every drop).

A shared CI runner is noisy, so the assertions are generous (10x the budget) unless
``SHIPWRIGHT_BENCH_STRICT=1`` (Windows/local measuring) asks for the real bounds. The measured numbers are
printed as one ``BENCH`` JSON line and written to ``SHIPWRIGHT_BENCH_OUT`` when that is set.
"""

from __future__ import annotations

import json
import os
import platform
import shutil
import statistics
import subprocess
import sys
import time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "shared" / "scripts"))

pytestmark = pytest.mark.covers("FR-01.11")

FILES, PER_FILE, REPEATS = 300, 4, 15
STRICT = os.environ.get("SHIPWRIGHT_BENCH_STRICT") == "1"
RUN_MS, WHOLE_MS, WRITE_MS = (20, 300, 250) if STRICT else (200, 3000, 4000)
RUN_KEY = "run-150"


def _real_bodies() -> list[dict]:
    lines = [ln for ln in (REPO / "shipwright_events.jsonl").read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert lines, 'the benchmark needs a non-empty shipwright_events.jsonl (pin a snapshot fixture once the legacy log is folded away)'
    return [json.loads(ln) for ln in lines[-300:]]


def _build(root: Path) -> None:
    subprocess.run(["git", "init", "-q", "-b", "main", str(root)], check=True, capture_output=True)
    shutil.copyfile(REPO / "shipwright_events.jsonl", root / "shipwright_events.jsonl")
    bodies, folder = _real_bodies(), root / ".shipwright/events/drops"
    folder.mkdir(parents=True)
    for i in range(FILES):
        rows = []
        for j in range(PER_FILE):
            event = dict(bodies[(i * PER_FILE + j) % len(bodies)])
            event.update(id=f"evt-{i:04d}{j:012x}", run=f"run-{i}", ts=f"2026-10-{1 + i % 28:02d}T10:{j:02d}:00+00:00")
            rows.append(json.dumps(event, separators=(",", ":")) + "\n")
        (folder / f"run-{i}--aaaaaaaa--{i:08x}.jsonl").write_text("".join(rows), encoding="utf-8", newline="\n")


def _median_ms(fn, repeats: int = REPEATS) -> float:
    fn()  # warm the file cache; the first pass of a cold run is not the steady state the budget names
    samples = []
    for _ in range(repeats):
        start = time.perf_counter()
        fn()
        samples.append((time.perf_counter() - start) * 1000)
    return round(statistics.median(samples), 1)


def test_kc5_run_scoped_and_whole_log_reads_and_per_write_cost_at_300_files(tmp_path, monkeypatch):
    monkeypatch.setenv("SHIPWRIGHT_EVENTS_LAYOUT_TEST", "1")
    monkeypatch.setenv("SHIPWRIGHT_EVENTS_LAYOUT", "drops")
    monkeypatch.delenv("SHIPWRIGHT_RUN_ID", raising=False)
    from lib.events_read import read_events_assembled
    from lib.jsonl_records import read_jsonl_records
    from tools import record_event

    root = tmp_path / "bench"
    root.mkdir()
    _build(root)
    legacy, folder = root / "shipwright_events.jsonl", root / ".shipwright/events/drops"

    def run_scoped(prefilter: bool) -> list[dict]:
        own = [r for p in sorted(folder.glob(f"{RUN_KEY}--*.jsonl")) for r in read_jsonl_records(p).records]
        if prefilter:
            hits = [ln for ln in legacy.read_text(encoding="utf-8").splitlines() if RUN_KEY in ln]
            theirs = [r for r in map(json.loads, hits) if r.get("adr_id") == RUN_KEY]
        else:
            theirs = [r for r in read_jsonl_records(legacy).records if r.get("adr_id") == RUN_KEY]
        return own + theirs

    counter = iter(range(10_000))

    def one_write() -> None:
        event = {"v": 1, "id": f"evt-w{next(counter):015x}", "ts": "2026-11-07T10:00:00+00:00",
                 "type": "task_created", "description": "bench"}
        record_event.append_event(root, event, "run-bench")

    assert len(read_events_assembled(root).records) >= FILES * PER_FILE
    assert len(run_scoped(True)) == PER_FILE  # the run's own four events (none in the legacy log)
    figures = {
        "platform": platform.platform(), "python": platform.python_version(), "files": FILES,
        "legacy_events": len(read_jsonl_records(legacy).records), "strict": STRICT, "legacy_bytes": legacy.stat().st_size, "traced_by_coverage": sys.gettrace() is not None or "coverage" in sys.modules,
        "run_scoped_ms": _median_ms(lambda: run_scoped(True)),
        "run_scoped_unfiltered_legacy_ms": _median_ms(lambda: run_scoped(False)),
        "whole_log_ms": _median_ms(lambda: read_events_assembled(root)),
        "per_write_ms": _median_ms(one_write, 8),
    }
    line = "BENCH " + json.dumps(figures, sort_keys=True)
    print(line)
    if os.environ.get("SHIPWRIGHT_BENCH_OUT"):
        Path(os.environ["SHIPWRIGHT_BENCH_OUT"]).write_text(line[6:] + "\n", encoding="utf-8")
    if os.environ.get("GITHUB_STEP_SUMMARY"):   # the Linux runner's numbers land in the job summary without a workflow change
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as fp:
            fp.write("### Events drops benchmark (300 files)" + chr(10)*2 + "```json" + chr(10) + json.dumps(figures, indent=1, sort_keys=True) + chr(10) + "```" + chr(10))
    assert figures["run_scoped_ms"] <= RUN_MS, line
    assert figures["whole_log_ms"] <= WHOLE_MS, line
    assert figures["per_write_ms"] <= WRITE_MS, line
