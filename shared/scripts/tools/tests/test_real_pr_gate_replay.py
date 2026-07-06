"""Replay the diff-coverage gate against REAL recent monorepo PR reports.

Empirical settling-window evidence for the deferred Phase-4 hard-flip
(iterate-2026-07-06-diff-coverage-real-pr-replay): instead of only synthetic
inputs, drive ``measure_diff_coverage --fail-under 80`` against the EXACT
``diff-cover.json`` each of the last 5 monorepo PRs produced in its own CI run
(pinned under ``fixtures/real_pr_diff_coverage/monorepo/`` with provenance in
``MANIFEST.json``). This is the record/replay pattern (cf. the G5 real-OSS
suite): the reports are real (diff-cover ran on the real combined coverage.xml
vs origin/main); the suite replays the gate DECISION against them offline and
deterministically — no network, no diff-cover subprocess, no git.

What it proves on REAL data:
  * the gate decides correctly across the real distribution (covered-pass,
    empty-diff-pass, and a genuine FAIL);
  * #325 (68%) is a real merged PR the 80% hard gate WOULD have blocked — and
    the block is legitimate (the adopt-side quote-strip shipped untested); so
    the threshold has real teeth without spurious red on this corpus.

Scope: this replays the gate DECISION on the real report; diff-cover's own
line-counting already ran authoritatively in each PR's CI (see MANIFEST).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_SHARED = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_SHARED))
sys.path.insert(0, str(_SHARED / "scripts"))

from lib.diff_coverage_gate import GATE_EXIT_FAIL, GATE_EXIT_PASS
from scripts.tools.measure_diff_coverage import diff_percent_from_report
from scripts.tools.measure_diff_coverage import main as measure_main

_FIXTURES = Path(__file__).parent / "fixtures" / "real_pr_diff_coverage" / "monorepo"
_MANIFEST = json.loads((_FIXTURES / "MANIFEST.json").read_text(encoding="utf-8"))
_THRESHOLD = _MANIFEST["threshold"]
_PRS = _MANIFEST["prs"]

# expected_decision -> the exit code the gate must return at the threshold.
_DECISION_EXIT = {
    "pass": GATE_EXIT_PASS,
    "pass_no_lines": GATE_EXIT_PASS,
    "fail": GATE_EXIT_FAIL,
}
_STUB_COVERAGE_XML = '<?xml version="1.0" ?>\n<coverage line-rate="0.8"/>\n'


def _load_report(entry: dict) -> dict:
    return json.loads((_FIXTURES / entry["fixture"]).read_text(encoding="utf-8"))


# --------------------------------------------------------------------------- #
# Registry drift protection (MANIFEST <-> fixture files), both directions.
# --------------------------------------------------------------------------- #
class TestManifestFixtureDrift:
    def test_forward_every_manifest_entry_has_a_fixture(self):
        for entry in _PRS:
            assert (_FIXTURES / entry["fixture"]).is_file(), (
                f"MANIFEST references missing fixture {entry['fixture']!r}")

    def test_reverse_every_fixture_is_in_the_manifest(self):
        on_disk = {p.name for p in _FIXTURES.glob("pr*.diff-cover.json")}
        in_manifest = {e["fixture"] for e in _PRS}
        assert on_disk == in_manifest, (
            f"fixture/manifest drift: on-disk={sorted(on_disk)} "
            f"manifest={sorted(in_manifest)}")

    def test_threshold_matches_the_gate_default(self):
        # The pinned corpus is scored at the same 80 the ci.yml gate uses.
        assert _THRESHOLD == 80


# --------------------------------------------------------------------------- #
# Per-PR replay: real report -> real gate decision.
# --------------------------------------------------------------------------- #
class TestRealPrReplay:
    @pytest.mark.parametrize("entry", _PRS, ids=[f"pr{e['pr']}" for e in _PRS])
    def test_recorded_values_match_the_fixture(self, entry):
        # Drift guard: the MANIFEST's recorded numbers must match the pinned
        # report (a re-captured fixture that changed must update the MANIFEST).
        report = _load_report(entry)
        assert report.get("total_num_lines") == entry["recorded_num_lines"]
        assert report.get("total_percent_covered") == entry["recorded_percent"]

    @pytest.mark.parametrize("entry", _PRS, ids=[f"pr{e['pr']}" for e in _PRS])
    def test_parser_on_real_report(self, entry):
        report = _load_report(entry)
        diff = diff_percent_from_report(report)
        if entry["expected_decision"] == "pass_no_lines":
            assert diff is None, "empty diff must parse to None (not a false 100%)"
        else:
            assert diff == float(entry["recorded_percent"])

    @pytest.mark.parametrize("entry", _PRS, ids=[f"pr{e['pr']}" for e in _PRS])
    def test_gate_decision_on_real_report(self, entry, tmp_path):
        # Full entrypoint replay: feed the REAL diff-cover.json through the gate.
        (tmp_path / "coverage.xml").write_text(_STUB_COVERAGE_XML, encoding="utf-8")
        rc = measure_main([
            "--project-root", str(tmp_path),
            "--coverage-xml", str(tmp_path / "coverage.xml"),
            "--diff-cover-json", str(_FIXTURES / entry["fixture"]),
            "--fail-under", str(_THRESHOLD),
        ])
        assert rc == _DECISION_EXIT[entry["expected_decision"]], (
            f"pr{entry['pr']} ({entry['recorded_percent']}%, "
            f"{entry['recorded_num_lines']} lines) decided {rc}, "
            f"expected {entry['expected_decision']}")


# --------------------------------------------------------------------------- #
# Aggregate distribution — the settling-window evidence, frozen.
# --------------------------------------------------------------------------- #
class TestRealPrDistribution:
    def test_distribution_at_threshold(self, capsys):
        dist = {"pass": 0, "pass_no_lines": 0, "fail": 0}
        for entry in _PRS:
            dist[entry["expected_decision"]] += 1
        print(f"\nReal-PR diff-coverage @{_THRESHOLD}%: {dist} "
              f"(n={len(_PRS)}) — FAIL(s): "
              f"{[e['pr'] for e in _PRS if e['expected_decision'] == 'fail']}")
        # The corpus must exercise all three decision branches on real data —
        # else it is not evidence that the gate behaves on real traffic.
        assert dist["fail"] >= 1, "corpus must contain a real under-covered PR"
        assert dist["pass"] >= 1, "corpus must contain a real covered-pass PR"
        assert dist["pass_no_lines"] >= 1, "corpus must contain a real no-lines PR"
        # Every real FAIL in the corpus is a legitimate block, documented in the
        # MANIFEST notes (guards against pinning a false-alarm as 'expected fail').
        for entry in _PRS:
            if entry["expected_decision"] == "fail":
                assert entry.get("notes", "").strip(), (
                    f"pr{entry['pr']} is an expected FAIL but has no MANIFEST "
                    f"note justifying it as a legitimate block")

    def test_no_pr_would_be_a_false_alarm_block(self):
        # A covered-pass PR must never be recorded below the threshold, and an
        # under-covered PR must never be recorded at/above it — i.e. the pinned
        # expected_decision is internally consistent with the recorded percent.
        for entry in _PRS:
            pct, n = entry["recorded_percent"], entry["recorded_num_lines"]
            if entry["expected_decision"] == "fail":
                assert n > 0 and pct < _THRESHOLD
            elif entry["expected_decision"] == "pass":
                assert n > 0 and pct >= _THRESHOLD
            else:  # pass_no_lines
                assert n == 0
