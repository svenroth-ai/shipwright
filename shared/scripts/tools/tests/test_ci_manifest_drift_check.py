"""`ci_manifest_drift_check.py` (iterate-2026-08-26-r1b-ci-manifest-regen-gate,
AC4 b-e).

Covers: capturing the committed manifest via a REAL `git show` (a real repo,
not a mock — this is the one place a wrong `git` invocation would silently
capture nothing); staging CI's JUnit reports from a plan.json (and refusing
on a missing report or malformed plan); `run()`'s orchestration wiring (each
step's failure surfaces as exit 2, `DriftCheckError`, never swallowed) with
the regen/comparison steps mocked at the function boundary (unit scope —
`regenerate_manifest`'s own subprocess-isolation is exercised in the full
local proof run against a real, ISOLATED project root, never this repo's own
live tree — see the module docstring's ADR-045 note for why it must be a
subprocess at all); and a real subprocess CLI smoke test proving the module
actually imports and starts cleanly as `uv run ci_manifest_drift_check.py`
— the exact bug class this file exists to guard against (a prior draft's
`from lib import evidence_drop` only "worked" under pytest's own test-
collection sys.path side effect and crashed immediately as a real CLI call).
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

import scripts.tools.ci_manifest_drift_check as mod  # noqa: E402

_REPO_ROOT = Path(__file__).resolve().parents[4]


def _git(*args: str, cwd: Path) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)


def _git_repo_with_committed_manifest(tmp_path: Path, manifest: dict) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git("init", "-q", cwd=repo)
    _git("config", "user.email", "test@example.com", cwd=repo)
    _git("config", "user.name", "Test", cwd=repo)
    manifest_path = repo / ".shipwright" / "compliance" / "test-traceability.json"
    manifest_path.parent.mkdir(parents=True)
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    _git("add", "-A", cwd=repo)
    _git("commit", "-q", "-m", "add manifest", cwd=repo)
    return repo


class TestCaptureCommittedManifest:
    def test_captures_the_real_committed_content_via_git_show(self, tmp_path):
        repo = _git_repo_with_committed_manifest(tmp_path, {"schema_version": 3})
        scratch = tmp_path / "scratch.json"
        mod.capture_committed_manifest(repo, scratch)
        assert json.loads(scratch.read_text(encoding="utf-8")) == {"schema_version": 3}

    def test_missing_committed_file_raises(self, tmp_path):
        repo = tmp_path / "repo"
        repo.mkdir()
        _git("init", "-q", cwd=repo)
        _git("config", "user.email", "test@example.com", cwd=repo)
        _git("config", "user.name", "Test", cwd=repo)
        (repo / "readme.txt").write_text("x", encoding="utf-8")
        _git("add", "-A", cwd=repo)
        _git("commit", "-q", "-m", "init", cwd=repo)

        scratch = tmp_path / "scratch.json"
        try:
            mod.capture_committed_manifest(repo, scratch)
            raise AssertionError("expected DriftCheckError")
        except mod.DriftCheckError as exc:
            assert "test-traceability.json" in str(exc)


class TestStageCiReports:
    def test_stages_reports_named_in_the_plan(self, tmp_path):
        project_root = tmp_path / "project"
        project_root.mkdir()
        report = tmp_path / "r.xml"
        report.write_text("<testsuites/>", encoding="utf-8")
        plan_path = tmp_path / "plan.json"
        plan_path.write_text(json.dumps([{"rel_root": "shared/tests", "base": "", "junit_out": str(report)}]),
                             encoding="utf-8")

        mod.stage_ci_reports(project_root, run_id="r1", head_commit="deadbeef", plan_path=plan_path)

        staged = project_root / ".shipwright" / "compliance" / "evidence" / "junit-01.xml"
        assert staged.is_file()

    def test_missing_report_file_raises(self, tmp_path):
        project_root = tmp_path / "project"
        project_root.mkdir()
        plan_path = tmp_path / "plan.json"
        plan_path.write_text(json.dumps([{"rel_root": "shared/tests", "base": "", "junit_out": str(tmp_path / "never.xml")}]),
                             encoding="utf-8")
        try:
            mod.stage_ci_reports(project_root, run_id="r1", head_commit="deadbeef", plan_path=plan_path)
            raise AssertionError("expected DriftCheckError")
        except mod.DriftCheckError as exc:
            assert "never.xml" in str(exc)

    def test_malformed_plan_json_raises(self, tmp_path):
        project_root = tmp_path / "project"
        project_root.mkdir()
        plan_path = tmp_path / "plan.json"
        plan_path.write_text("{not valid", encoding="utf-8")
        try:
            mod.stage_ci_reports(project_root, run_id="r1", head_commit="deadbeef", plan_path=plan_path)
            raise AssertionError("expected DriftCheckError")
        except mod.DriftCheckError:
            pass

    def test_a_non_list_plan_raises_driftcheckerror_not_a_bare_exception(self, tmp_path):
        """External review: `{entry["base"] for entry in plan}` on a non-list `plan`
        (e.g. `{}`) raised an uncaught TypeError, which `run()` does not catch,
        so the tool crashed with exit 1 instead of the documented EXIT_ERROR."""
        project_root = tmp_path / "project"
        project_root.mkdir()
        plan_path = tmp_path / "plan.json"
        plan_path.write_text("{}", encoding="utf-8")
        try:
            mod.stage_ci_reports(project_root, run_id="r1", head_commit="deadbeef", plan_path=plan_path)
            raise AssertionError("expected DriftCheckError")
        except mod.DriftCheckError as exc:
            assert "list" in str(exc)

    def test_an_entry_missing_a_required_field_raises_driftcheckerror(self, tmp_path):
        project_root = tmp_path / "project"
        project_root.mkdir()
        plan_path = tmp_path / "plan.json"
        plan_path.write_text(json.dumps([{"rel_root": "shared/tests", "base": ""}]), encoding="utf-8")
        try:
            mod.stage_ci_reports(project_root, run_id="r1", head_commit="deadbeef", plan_path=plan_path)
            raise AssertionError("expected DriftCheckError")
        except mod.DriftCheckError as exc:
            assert "junit_out" in str(exc)

    def test_a_null_junit_out_raises_driftcheckerror_not_a_bare_typeerror(self, tmp_path):
        """Doubt-reviewer Stage 3: a JSON `null` for `junit_out` passed the old
        presence-only check ('junit_out' in entry is True for a null value),
        then crashed `Path(None).is_file()` with an uncaught TypeError."""
        project_root = tmp_path / "project"
        project_root.mkdir()
        plan_path = tmp_path / "plan.json"
        plan_path.write_text(
            json.dumps([{"rel_root": "shared/tests", "base": "", "junit_out": None}]),
            encoding="utf-8")
        try:
            mod.stage_ci_reports(project_root, run_id="r1", head_commit="deadbeef", plan_path=plan_path)
            raise AssertionError("expected DriftCheckError")
        except mod.DriftCheckError as exc:
            assert "junit_out" in str(exc)


class TestRunOrchestration:
    def test_a_failing_step_returns_exit_error_and_never_reaches_comparison(self, tmp_path, monkeypatch):
        monkeypatch.setattr(mod, "capture_committed_manifest",
                            lambda *a, **k: (_ for _ in ()).throw(mod.DriftCheckError("boom")))
        called = {"stage": False, "regen": False}
        monkeypatch.setattr(mod, "stage_ci_reports", lambda *a, **k: called.__setitem__("stage", True))
        monkeypatch.setattr(mod, "regenerate_manifest", lambda *a, **k: called.__setitem__("regen", True))

        code, output = mod.run(tmp_path, run_id="r1", head_commit="x", plan_path=tmp_path / "plan.json")

        assert code == mod.EXIT_ERROR
        assert "boom" in output
        assert called == {"stage": False, "regen": False}

    def test_an_unanticipated_exception_exits_error_not_the_bare_default(self, tmp_path, monkeypatch):
        """Doubt-reviewer Stage 3, doubt #1: `run()` used to catch ONLY
        `DriftCheckError`. Any other exception (e.g. an OSError from
        `evidence_drop.stage_reports`) escaped uncaught, and Python's default
        exit code for an uncaught exception is 1 — which ALIASES with
        `EXIT_STRUCTURAL_DRIFT`, so ci.yml's advisory wrapper would swallow a
        real infra failure as if it were reported drift."""
        monkeypatch.setattr(mod, "capture_committed_manifest",
                            lambda *a, **k: (_ for _ in ()).throw(OSError("disk full")))

        code, output = mod.run(tmp_path, run_id="r1", head_commit="x", plan_path=tmp_path / "plan.json")

        assert code == mod.EXIT_ERROR
        assert "disk full" in output

    def test_success_path_returns_the_comparators_own_exit_code(self, tmp_path, monkeypatch):
        monkeypatch.setattr(mod, "capture_committed_manifest", lambda *a, **k: None)
        monkeypatch.setattr(mod, "stage_ci_reports", lambda *a, **k: None)
        monkeypatch.setattr(mod, "regenerate_manifest", lambda *a, **k: None)
        monkeypatch.setattr(
            mod._compare_mod, "main_with_output",
            lambda argv: (mod.EXIT_STRUCTURAL_DRIFT, "drift here"),
        )

        code, output = mod.run(tmp_path, run_id="r1", head_commit="x", plan_path=tmp_path / "plan.json")

        assert code == mod.EXIT_STRUCTURAL_DRIFT
        assert output == "drift here"


class TestCliSmoke:
    def test_real_subprocess_invocation_imports_and_starts_cleanly(self, tmp_path):
        """The bug this guards: a prior draft's `from lib import evidence_drop`
        only worked under pytest's own sys.path side effect and crashed
        immediately as a real `uv run` invocation. Missing required args is
        expected (argparse exit 2) — what matters is that the traceback, if
        any, is argparse's, never a ModuleNotFoundError on import."""
        result = subprocess.run(
            ["uv", "run", "shared/scripts/tools/ci_manifest_drift_check.py"],
            cwd=_REPO_ROOT, capture_output=True, text=True, timeout=60,
        )
        assert "ModuleNotFoundError" not in result.stderr
        assert "the following arguments are required" in result.stderr
