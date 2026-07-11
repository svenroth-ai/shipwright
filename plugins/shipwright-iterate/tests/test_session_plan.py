"""Tests for the persisted iterate session plan (B2 / M-Pre-2).

Two guarantees the WebUI scoped Plan-Card depends on:
1. `classify_complexity.py` STDOUT stays byte-identical whether or not the
   plan is persisted (`--run-id` must not perturb the classification contract).
2. When `--run-id` is given, a `<run_id>.plan.json` lands under
   `.shipwright/agent_docs/iterates/` with the projected shape
   `{run_id, complexity, risk_flags[], phases[], skips[]}`.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(
    0,
    str(Path(__file__).resolve().parent.parent / "scripts" / "lib"),
)

from complexity_history import load_history_prior  # noqa: E402
from session_plan import (  # noqa: E402
    build_session_plan,
    persist_session_plan,
    persist_session_plan_safe,
    plan_path,
)

_CLASSIFIER = (
    Path(__file__).resolve().parent.parent
    / "scripts" / "lib" / "classify_complexity.py"
)


# --- Projection shape --------------------------------------------------------


def _phase_ids(entries):
    return {e["id"] for e in entries}


class TestBuildSessionPlan:
    def test_shape_keys(self):
        plan = build_session_plan(
            {"estimate": "medium", "risk_flags": ["touches_io_boundary"]},
            "iterate-2026-07-10-x",
        )
        assert set(plan) == {"run_id", "complexity", "risk_flags", "phases", "skips"}
        assert plan["run_id"] == "iterate-2026-07-10-x"
        assert plan["complexity"] == "medium"
        assert plan["risk_flags"] == ["touches_io_boundary"]

    def test_phases_and_skips_are_disjoint_and_shaped(self):
        plan = build_session_plan({"estimate": "trivial", "risk_flags": []}, "r")
        assert _phase_ids(plan["phases"]).isdisjoint(_phase_ids(plan["skips"]))
        for ph in plan["phases"]:
            assert set(ph) == {"id", "group"}
        for sk in plan["skips"]:
            assert set(sk) == {"id", "group", "reason"}
            assert sk["reason"]  # non-empty explanation

    def test_medium_with_risk_plans_all_reviews(self):
        plan = build_session_plan(
            {"estimate": "medium", "risk_flags": ["touches_auth"]}, "r"
        )
        planned = _phase_ids(plan["phases"])
        assert {"external_plan_review", "code_review", "confidence_calibration",
                "build", "self_review", "test", "finalize"} <= planned

    def test_trivial_no_risk_skips_reviews(self):
        plan = build_session_plan({"estimate": "trivial", "risk_flags": []}, "r")
        skipped = _phase_ids(plan["skips"])
        assert {"external_plan_review", "code_review",
                "confidence_calibration", "interview", "iterate_spec"} <= skipped

    def test_small_io_boundary_keeps_calibration(self):
        plan = build_session_plan(
            {"estimate": "small", "risk_flags": ["touches_io_boundary"]}, "r"
        )
        # §6: at small, code_review is risk-gated (planned) and calibration is
        # touches_io_boundary-gated (planned) — but external PLAN review is
        # medium+ ONLY, so it must be SKIPPED even here (FIX 1 regression).
        assert "confidence_calibration" in _phase_ids(plan["phases"])
        assert "code_review" in _phase_ids(plan["phases"])
        assert "external_plan_review" in _phase_ids(plan["skips"])

    def test_small_non_io_risk_skips_only_calibration(self):
        # Contrast: a small run with a NON-io-boundary risk flag keeps
        # code_review (any risk flag) but SKIPS calibration (io-boundary only)
        # AND external plan review (medium+ only).
        plan = build_session_plan(
            {"estimate": "small", "risk_flags": ["touches_auth"]}, "r"
        )
        assert "code_review" in _phase_ids(plan["phases"])
        assert "confidence_calibration" in _phase_ids(plan["skips"])
        assert "external_plan_review" in _phase_ids(plan["skips"])

    def test_external_plan_review_is_medium_plus_only(self):
        # FIX 1 (HIGH): external PLAN review is §6 medium+ (auto) only, NOT
        # risk-flag-gated. small+risk_flag is a normal classify output (io/auth
        # floor to small), so the Plan-Card must show it SKIPPED there.
        for flags in ([], ["touches_io_boundary"], ["touches_auth"]):
            for comp in ("trivial", "small"):
                plan = build_session_plan({"estimate": comp, "risk_flags": flags}, "r")
                assert "external_plan_review" in _phase_ids(plan["skips"]), (
                    f"{comp}+{flags} must SKIP external plan review (§6)"
                )
        plan = build_session_plan({"estimate": "medium", "risk_flags": []}, "r")
        assert "external_plan_review" in _phase_ids(plan["phases"])


# --- Persist round-trip (boundary probe: producer -> file -> consumer) -------


class TestPersistRoundTrip:
    def test_writes_expected_location(self, tmp_path):
        result = {"estimate": "medium", "risk_flags": ["touches_io_boundary"]}
        written = persist_session_plan(result, "iterate-2026-07-10-rt", tmp_path)
        assert written == plan_path(tmp_path, "iterate-2026-07-10-rt")
        assert written.parts[-3:] == ("agent_docs", "iterates",
                                      "iterate-2026-07-10-rt.plan.json")

    def test_round_trip_shape_matches_producer(self, tmp_path):
        rid = "iterate-2026-07-10-roundtrip"
        result = {"estimate": "small", "risk_flags": ["touches_io_boundary"]}
        written = persist_session_plan(result, rid, tmp_path)
        # Consumer side: read the file exactly as the WebUI would.
        loaded = json.loads(written.read_text(encoding="utf-8"))
        assert loaded == build_session_plan(result, rid)

    def test_missing_estimate_defaults_trivial(self, tmp_path):
        written = persist_session_plan({}, "iterate-2026-07-10-defaults", tmp_path)
        loaded = json.loads(written.read_text(encoding="utf-8"))
        assert loaded["complexity"] == "trivial"
        assert loaded["risk_flags"] == []

    def test_safe_wrapper_swallows_io_error(self, tmp_path):
        # Valid run_id + project_root that is a FILE -> mkdir raises OSError;
        # the safe wrapper must swallow it (exercises the real I/O path).
        blocker = tmp_path / "not-a-dir"
        blocker.write_text("x", encoding="utf-8")
        assert persist_session_plan_safe(
            {"estimate": "small"}, "iterate-2026-07-10-blk", blocker) is None


# --- Boundary co-tenancy: plan files must not pollute the history prior ------


class TestPlanFilesExcludedFromHistory:
    """The producer writes into the exact dir load_history_prior globs `*.json`.

    Plan files must never be counted as finalized history entries — else a
    single classify would skew every subsequent complexity estimate.
    """

    def _write_real(self, store, i, complexity):
        (store / f"iterate-2026-06-{i}-real.json").write_text(
            json.dumps({"run_id": f"r{i}", "date": f"2026-06-{i}T10:00:00Z",
                        "complexity": complexity}),
            encoding="utf-8",
        )

    def test_plan_files_alone_yield_no_prior(self, tmp_path):
        for i in range(5):
            persist_session_plan({"estimate": "large"}, f"iterate-2026-07-2{i}-p",
                                 tmp_path)
        assert load_history_prior(tmp_path) is None

    def test_plan_files_do_not_shift_prior(self, tmp_path):
        store = tmp_path / ".shipwright" / "agent_docs" / "iterates"
        store.mkdir(parents=True)
        for i in (10, 11, 12):
            self._write_real(store, i, "small")
        baseline = load_history_prior(tmp_path)
        assert baseline == {"prior": "small", "n": 3}
        for i in range(5):
            persist_session_plan({"estimate": "large"}, f"iterate-2026-07-2{i}-p",
                                 tmp_path)
        assert load_history_prior(tmp_path) == baseline


# --- STDOUT byte-stability contract (AC1) ------------------------------------


class TestStdoutUnchanged:
    def _run(self, tmp_path, extra):
        cmd = [
            sys.executable, str(_CLASSIFIER),
            "--message", "add a small helper for course search",
            "--project-root", str(tmp_path),
        ] + extra
        return subprocess.run(cmd, capture_output=True, check=True)

    def test_run_id_does_not_change_stdout(self, tmp_path):
        # Same project-root both times -> identical history prior -> the ONLY
        # variable is --run-id. STDOUT must be byte-for-byte identical.
        without = self._run(tmp_path, [])
        with_id = self._run(tmp_path, ["--run-id", "iterate-2026-07-10-stdout"])
        assert with_id.stdout == without.stdout

    def test_run_id_persists_plan_file(self, tmp_path):
        self._run(tmp_path, ["--run-id", "iterate-2026-07-10-persisted"])
        target = plan_path(tmp_path, "iterate-2026-07-10-persisted")
        assert target.exists()
        loaded = json.loads(target.read_text(encoding="utf-8"))
        assert set(loaded) == {"run_id", "complexity", "risk_flags",
                               "phases", "skips"}
        assert loaded["run_id"] == "iterate-2026-07-10-persisted"

    def test_no_run_id_writes_no_file(self, tmp_path):
        self._run(tmp_path, [])
        iterates = tmp_path / ".shipwright" / "agent_docs" / "iterates"
        assert not iterates.exists() or not list(iterates.glob("*.plan.json"))

    def test_persisted_fields_derive_from_stdout(self, tmp_path):
        # The persisted complexity/risk_flags MUST equal the stdout JSON's
        # estimate/risk_flags for the same input (guards projection drift).
        proc = self._run(tmp_path, ["--run-id", "iterate-2026-07-10-derive"])
        stdout_json = json.loads(proc.stdout.decode("utf-8"))
        plan = json.loads(
            plan_path(tmp_path, "iterate-2026-07-10-derive").read_text("utf-8")
        )
        assert plan["complexity"] == stdout_json["estimate"]
        assert plan["risk_flags"] == stdout_json["risk_flags"]
