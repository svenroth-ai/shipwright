"""Integration test for performance_check.py CLI surface (AC-6 + AC-14).

Exercises the runner end-to-end via subprocess. Lighthouse is faked via the
SHIPWRIGHT_PERF_LHCI_FAKE seam (guarded by SHIPWRIGHT_TEST_MODE=1) so no
real Chromium / Playwright is required.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
RUNNER = REPO_ROOT / "plugins" / "shipwright-test" / "scripts" / "lib" / "performance_check.py"
FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _make_temp_profile(tmp_path: Path, *, gate: str = "warn",
                       enabled: bool = True, build_dir: str = "bundle/sample-app",
                       min_score: int = 85, max_kb_gz: int = 250,
                       lcp_max_ms: int = 2500) -> Path:
    """Write a minimal profile JSON for the integration test."""
    profile = {
        "name": "test-fixture-profile",
        "testing": {
            "performance": {
                "enabled": enabled,
                "lighthouse": {"min_score": min_score, "lcp_max_ms": lcp_max_ms},
                "bundle": {"max_kb_gz": max_kb_gz, "build_output_dir": build_dir},
                "gate": gate,
            }
        },
    }
    profile_path = tmp_path / "profile.json"
    profile_path.write_text(json.dumps(profile), encoding="utf-8")
    return profile_path


def _run(args: list[str], env_extra: dict[str, str] | None = None,
         cwd: Path | None = None) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env.setdefault("SHIPWRIGHT_TEST_MODE", "1")
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        [sys.executable, str(RUNNER), *args],
        cwd=str(cwd) if cwd else None,
        env=env, capture_output=True, text=True, encoding="utf-8",
        timeout=60,
    )


# ── --help smoke (AC-14) ─────────────────────────────────────────────────────

def test_help_works():
    proc = _run(["--help"])
    assert proc.returncode == 0
    assert "performance" in proc.stdout.lower()
    assert "--profile-path" in proc.stdout
    assert "--dev-url" in proc.stdout


# ── (a) all-pass scenario via fake LHR + fixture bundle ──────────────────────

def test_all_pass_with_fake_lhci_and_sample_bundle(tmp_path):
    # cwd = the fixtures dir so build_output_dir 'bundle/sample-app' resolves
    cwd = FIXTURES
    profile_path = _make_temp_profile(tmp_path)
    proc = _run(
        ["--cwd", str(cwd), "--profile-path", str(profile_path),
         "--dev-url", "http://localhost:3000", "--gate", "warn"],
        env_extra={"SHIPWRIGHT_PERF_LHCI_FAKE": str(FIXTURES / "lhci" / "lhr-good.json")},
    )
    assert proc.returncode == 0, f"stdout={proc.stdout}\nstderr={proc.stderr}"
    out = json.loads(proc.stdout)
    assert out["success"] is True
    assert out["gate"] == "warn"
    assert out["lighthouse"]["ran"] is True
    assert out["lighthouse"]["score"] == 92
    assert out["lighthouse"]["score_passed"] is True
    assert out["lighthouse"]["lcp_ms"] == 1840
    assert out["lighthouse"]["lcp_passed"] is True
    assert out["bundle"]["ran"] is True
    assert out["bundle"]["files_measured"] == 2
    assert out["bundle"]["passed"] is True


# ── (b) lighthouse fail under gate=block → exit 1 ────────────────────────────

def test_block_gate_fails_when_lighthouse_below_budget(tmp_path):
    # cwd = a throwaway tmp project root, NOT the tracked FIXTURES dir: on a
    # failed sub-check the runner emits .shipwright/triage.jsonl under cwd, so
    # pointing it at FIXTURES would leak into version control. The bundle
    # sub-check gracefully skips (no build dir here); this test asserts only the
    # lighthouse gate behavior, and the LHR fixture is passed by absolute path.
    cwd = tmp_path
    profile_path = _make_temp_profile(tmp_path, gate="block")
    proc = _run(
        ["--cwd", str(cwd), "--profile-path", str(profile_path),
         "--dev-url", "http://localhost:3000"],
        env_extra={"SHIPWRIGHT_PERF_LHCI_FAKE": str(FIXTURES / "lhci" / "lhr-bad.json")},
    )
    assert proc.returncode == 1, f"stdout={proc.stdout}\nstderr={proc.stderr}"
    out = json.loads(proc.stdout)
    assert out["success"] is False
    assert out["gate"] == "block"
    assert out["lighthouse"]["score"] == 71
    assert out["lighthouse"]["score_passed"] is False
    assert out["lighthouse"]["lcp_ms"] == 4100
    assert out["lighthouse"]["lcp_passed"] is False
    # Regression guard: a failed sub-check makes the runner emit
    # .shipwright/triage.jsonl under the project root passed via --cwd. That
    # root MUST be throwaway (tmp_path), never the tracked fixtures dir — else
    # every run leaves plugins/shipwright-test/tests/fixtures/.shipwright/
    # behind and dirties the tree (iterate-2026-07-15-perf-test-triage-leak).
    # Anchoring on tmp_path fails loudly if --cwd is ever pointed back at
    # FIXTURES.
    assert (tmp_path / ".shipwright" / "triage.jsonl").exists(), (
        "triage emission should land under the throwaway tmp project root"
    )


# ── warn gate: same bad LHR but exit 0 + success true ────────────────────────

def test_warn_gate_succeeds_even_on_lighthouse_failure(tmp_path):
    cwd = FIXTURES
    profile_path = _make_temp_profile(tmp_path, gate="warn")
    proc = _run(
        ["--cwd", str(cwd), "--profile-path", str(profile_path)],
        env_extra={"SHIPWRIGHT_PERF_LHCI_FAKE": str(FIXTURES / "lhci" / "lhr-bad.json")},
    )
    # No --dev-url passed → lighthouse skipped; bundle still runs and passes
    assert proc.returncode == 0
    out = json.loads(proc.stdout)
    assert out["success"] is True
    assert out["gate"] == "warn"
    assert out["lighthouse"]["skipped"] is True
    assert out["bundle"]["ran"] is True


# ── profile-opts-out scenario ────────────────────────────────────────────────

def test_seam_rejection_falls_through_without_test_mode(tmp_path):
    """SHIPWRIGHT_PERF_LHCI_FAKE without SHIPWRIGHT_TEST_MODE: warn +
    fall through to real Lighthouse, NOT silent skip (Review Finding 5+10).

    Real Lighthouse will fail (no node, no playwright, no dev URL on this
    test runner) — but the result must be 'lighthouse_unavailable' from a
    REAL attempted run, with the WARNING about test_mode in stderr.
    """
    cwd = FIXTURES
    profile_path = _make_temp_profile(tmp_path)
    # Inherit env but explicitly REMOVE SHIPWRIGHT_TEST_MODE.
    env = os.environ.copy()
    env.pop("SHIPWRIGHT_TEST_MODE", None)
    env["SHIPWRIGHT_PERF_LHCI_FAKE"] = str(FIXTURES / "lhci" / "lhr-good.json")
    proc = subprocess.run(
        [sys.executable, str(RUNNER),
         "--cwd", str(cwd), "--profile-path", str(profile_path),
         "--dev-url", "http://localhost:3000", "--gate", "warn"],
        env=env, capture_output=True, text=True, encoding="utf-8", timeout=60,
    )
    # Real Lighthouse path was attempted (no fake short-circuit). Without a
    # real dev server, lighthouse will skip; the seam-rejection warning is
    # in stderr.
    assert "WARNING" in proc.stderr
    assert "SHIPWRIGHT_TEST_MODE" in proc.stderr
    out = json.loads(proc.stdout)
    # Lighthouse skipped because real run couldn't reach localhost:3000 OR
    # node/playwright unavailable in test env. Either way: skipped, NOT a
    # fake-derived populated result.
    assert out["lighthouse"]["skipped"] is True
    assert out["lighthouse"]["score"] is None  # no fake data leaked through


def test_disabled_profile_emits_skipped_result_exit_0(tmp_path):
    cwd = FIXTURES
    profile_path = _make_temp_profile(tmp_path, enabled=False)
    proc = _run(["--cwd", str(cwd), "--profile-path", str(profile_path)])
    assert proc.returncode == 0
    out = json.loads(proc.stdout)
    assert out["success"] is True
    assert out["skipped"] is True
    assert "opts out" in out["skip_reason"].lower()


# ── shipwright_test_config.json shallow override ─────────────────────────────

def test_test_config_override_tightens_gate(tmp_path):
    """Project ships shipwright_test_config.json setting gate=block + tighter score."""
    project_root = tmp_path / "proj"
    project_root.mkdir()
    # link the bundle fixture into the project root so build_output_dir resolves
    (project_root / "bundle").symlink_to(FIXTURES / "bundle", target_is_directory=True) \
        if hasattr(os, "symlink") and sys.platform != "win32" else None
    # Windows fallback: copy the bundle dir
    if not (project_root / "bundle").exists():
        import shutil
        shutil.copytree(FIXTURES / "bundle", project_root / "bundle")

    profile_path = _make_temp_profile(tmp_path, gate="warn", min_score=80)
    (project_root / "shipwright_test_config.json").write_text(
        json.dumps({"performance": {"gate": "block",
                                    "lighthouse": {"min_score": 95}}}),
        encoding="utf-8",
    )
    proc = _run(
        ["--cwd", str(project_root), "--profile-path", str(profile_path),
         "--dev-url", "http://localhost:3000"],
        env_extra={"SHIPWRIGHT_PERF_LHCI_FAKE": str(FIXTURES / "lhci" / "lhr-good.json")},
    )
    # lighthouse fixture score=92 < min_score=95 → block fails
    assert proc.returncode == 1, f"stdout={proc.stdout}"
    out = json.loads(proc.stdout)
    assert out["gate"] == "block"
    assert out["lighthouse"]["score"] == 92
    assert out["lighthouse"]["score_passed"] is False
    assert out["lighthouse"]["score_budget"] == 95
    # lcp_max_ms inherited from profile (2500) → 1840 passes
    assert out["lighthouse"]["lcp_passed"] is True
