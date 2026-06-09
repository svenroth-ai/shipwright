"""Idle-main artifact hygiene — completes ADR-089 for two stragglers.

iterate-2026-06-09-idle-main-artifact-hygiene (anchor trg-7640bd14).

(a) The phase-quality skill-compliance roll-ups (report/dashboard/findings)
    are TRANSIENT derived caches of the already-gitignored ``FINDING_DIR``
    JSONs — they must live UNDER ``FINDING_DIR`` so they never show up as
    ``??`` on idle main (never tracked, not in audit_staleness.DOC_REGISTRY).

(b) The bloat marker WRITER (``check_file_size.py`` PostToolUse) and READER
    (``bloat_gate_on_stop.py`` Stop) must key the marker / baseline /
    re-measure off the canonical MAIN repo root, not ``Path.cwd()``. A hook
    firing with cwd != repo-root (sub-package test run, monorepo
    auto-descent) otherwise writes ``shared/.shipwright/locks/...`` which the
    root-anchored ``/.shipwright/*`` ignore misses -> leak.

These are EMPIRICAL probes (touches_io_boundary): real ``git init`` tmp repos,
real subprocess hook invocations, real ``git status`` — not mocks.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

_SHARED_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
HOOKS_DIR = _SHARED_SCRIPTS / "hooks"
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))

from lib import phase_quality as pq  # noqa: E402
from lib import repo_root as _rr  # noqa: E402

_REPO_ROOT = Path(__file__).resolve().parents[2]
_TEMPLATE = _REPO_ROOT / "shared" / "templates" / "shipwright-gitignore.template"
_FRAMEWORK_GITIGNORE = _REPO_ROOT / ".gitignore"


# ---------------------------------------------------------------------------
# git helpers (silent-skip CI-discipline: hard-fail in CI on missing git)
# ---------------------------------------------------------------------------

def _has_git() -> bool:
    try:
        return subprocess.run(["git", "--version"], capture_output=True).returncode == 0
    except OSError:
        return False


def _require_git() -> None:
    if not _has_git():
        if os.environ.get("CI", "").lower() in ("true", "1"):
            pytest.fail("git is required for idle-main-artifact-hygiene probes; install git")
        pytest.skip("git not available")


def _init_repo(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=str(root), check=True)
    subprocess.run(["git", "config", "user.email", "t@example.com"], cwd=str(root), check=True)
    subprocess.run(["git", "config", "user.name", "T"], cwd=str(root), check=True)


def _oversize(p: Path, n: int = 420) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("x\n" * n, encoding="utf-8")


# ---------------------------------------------------------------------------
# AC-2 — fail-soft main-root resolver
# ---------------------------------------------------------------------------

def test_main_repo_root_or_falls_back_on_non_git(tmp_path):
    """Advisory hooks must never brick: a non-git dir resolves to the fallback."""
    assert _rr.main_repo_root_or(tmp_path) == tmp_path
    sentinel = tmp_path / "elsewhere"
    assert _rr.main_repo_root_or(tmp_path, fallback=sentinel) == sentinel


def test_main_repo_root_or_resolves_main_root_from_subdir(tmp_path):
    """From a sub-package dir, the resolver returns the MAIN repo root."""
    _require_git()
    repo = tmp_path / "repo"
    _init_repo(repo)
    sub = repo / "shared"
    sub.mkdir()
    assert _rr.main_repo_root_or(sub).resolve() == repo.resolve()


# ---------------------------------------------------------------------------
# AC-2 — writer (check_file_size) never leaks a nested marker
# ---------------------------------------------------------------------------

def _run_writer(cwd: Path, file_path: Path, sid: str) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env.pop("SHIPWRIGHT_SESSION_ID", None)  # force payload-keyed sid
    return subprocess.run(
        [sys.executable, str(HOOKS_DIR / "check_file_size.py")],
        input=json.dumps({"tool_name": "Write", "session_id": sid,
                          "tool_input": {"file_path": str(file_path)}}),
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        cwd=str(cwd), env=env,
    )


def test_writer_subdir_cwd_writes_marker_to_repo_root(tmp_path):
    """PostToolUse recorder fired from a SUBDIR keys the marker off the MAIN
    root, not cwd — no ``shared/.shipwright/locks/`` leak."""
    _require_git()
    repo = tmp_path / "repo"
    _init_repo(repo)
    sub = repo / "shared"
    sub.mkdir()
    big = sub / "huge.py"
    _oversize(big)

    _run_writer(sub, big, sid="S1")

    root_marker = repo / ".shipwright" / "locks" / "bloat_pending.S1.json"
    nested_marker = sub / ".shipwright" / "locks" / "bloat_pending.S1.json"
    assert root_marker.is_file(), "marker must land at the MAIN repo root"
    assert not nested_marker.exists(), "must NOT leak a nested shared/.shipwright/locks/"
    doc = json.loads(root_marker.read_text(encoding="utf-8"))
    paths = [e["path"] for e in doc["entries"]]
    assert paths == ["shared/huge.py"], f"path must be repo-root-relative; got {paths}"


# ---------------------------------------------------------------------------
# AC-2 — reader (bloat_gate_on_stop) reads the root marker from a subdir cwd
# ---------------------------------------------------------------------------

def _run_gate(cwd: Path, sid: str) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env["SHIPWRIGHT_SESSION_ID"] = sid
    return subprocess.run(
        [sys.executable, str(HOOKS_DIR / "bloat_gate_on_stop.py")],
        input=json.dumps({"session_id": sid}), capture_output=True, text=True,
        encoding="utf-8", errors="replace", cwd=str(cwd), env=env,
    )


def test_reader_subdir_cwd_reads_root_marker_and_blocks(tmp_path):
    """Stop gate fired from a SUBDIR finds the ROOT marker + baseline and
    blocks on a genuine new crossing (current cwd-based code finds nothing)."""
    _require_git()
    repo = tmp_path / "repo"
    _init_repo(repo)
    (repo / "shipwright_bloat_baseline.json").write_text(
        json.dumps({"version": 1, "entries": []}), encoding="utf-8")
    (repo / "big.py").write_text("x\n" * 420, encoding="utf-8")
    locks = repo / ".shipwright" / "locks"
    locks.mkdir(parents=True)
    (locks / "bloat_pending.S2.json").write_text(json.dumps({"version": 1, "entries": [
        {"path": "big.py", "now": 420, "limit": 300, "delta": "crossing",
         "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}]}), encoding="utf-8")
    sub = repo / "plugins"
    sub.mkdir()

    res = _run_gate(sub, "S2")
    out = res.stdout.strip()
    assert out, f"gate must emit a block decision; got empty stdout (stderr={res.stderr!r})"
    assert json.loads(out).get("decision") == "block", out


# ---------------------------------------------------------------------------
# AC-1 — skill-compliance roll-ups live under the gitignored FINDING_DIR
# ---------------------------------------------------------------------------

def test_rollup_constants_live_under_finding_dir():
    assert pq.REPORT_PATH.startswith(pq.FINDING_DIR + "/"), pq.REPORT_PATH
    assert pq.DASHBOARD_PATH.startswith(pq.FINDING_DIR + "/"), pq.DASHBOARD_PATH
    assert pq.SUMMARY_PATH.startswith(pq.FINDING_DIR + "/"), pq.SUMMARY_PATH


def _seed_finding(proj: Path) -> None:
    d = proj / pq.FINDING_DIR
    d.mkdir(parents=True, exist_ok=True)
    (d / "finding_iterate_run-1_sess-1.json").write_text(json.dumps({
        "phase": "iterate", "run_id": "run-1", "session_id": "sess-1",
        "audited_at": "2026-06-09T00:00:00Z", "source": "stop",
        "canon": [{"id": "C1", "status": "FAIL", "evidence": "x", "tier": 1}],
    }), encoding="utf-8")


def test_regenerate_writes_rollups_under_finding_dir(tmp_path):
    _seed_finding(tmp_path)
    pq.regenerate_all_aggregates(tmp_path)
    assert (tmp_path / pq.REPORT_PATH).is_file()
    assert (tmp_path / pq.DASHBOARD_PATH).is_file()
    assert (tmp_path / pq.SUMMARY_PATH).is_file()
    # The legacy tracked-eligible paths must NOT be written.
    assert not (tmp_path / ".shipwright/compliance/skill-compliance-report.md").exists()
    assert not (tmp_path / ".shipwright/compliance/skill-compliance-dashboard.md").exists()
    assert not (tmp_path / ".shipwright/agent_docs/skill-compliance-findings.md").exists()


def test_rollups_are_gitignored_after_render(tmp_path):
    """git-status-clean-after-Stop: with the canon .gitignore installed, the
    3 roll-ups never show up as ``??`` (they live under the ignored dir)."""
    _require_git()
    repo = tmp_path / "repo"
    _init_repo(repo)
    (repo / ".gitignore").write_text(_TEMPLATE.read_text(encoding="utf-8"), encoding="utf-8")
    _seed_finding(repo)
    pq.regenerate_all_aggregates(repo)
    # -uall lists every untracked file individually (no dir-collapse) so the
    # assertion can't pass trivially from git collapsing an untracked dir.
    out = subprocess.run(["git", "-C", str(repo), "status", "--porcelain", "-uall"],
                         capture_output=True, text=True).stdout
    assert "skill-compliance" not in out, f"roll-ups leaked into git status:\n{out}"


# ---------------------------------------------------------------------------
# AC-3 — defensive nested-locks ignore propagates via the canon template
# ---------------------------------------------------------------------------

_NESTED_LOCKS_RULE = "**/.shipwright/locks/"


def test_nested_locks_rule_in_canon_template():
    assert _NESTED_LOCKS_RULE in _TEMPLATE.read_text(encoding="utf-8"), (
        "defensive nested-locks ignore must live in the canon SSoT template so "
        "adopt + gitignore_selfheal propagate it to every adopted repo"
    )


def test_nested_locks_rule_in_framework_gitignore():
    assert _NESTED_LOCKS_RULE in _FRAMEWORK_GITIGNORE.read_text(encoding="utf-8")


def test_nested_locks_dir_is_ignored_by_canon_block(tmp_path):
    """Belt-and-suspenders: even if a stray producer writes a nested locks dir,
    the canon block ignores it (the resolver fix is the real fix)."""
    _require_git()
    repo = tmp_path / "repo"
    _init_repo(repo)
    (repo / ".gitignore").write_text(_TEMPLATE.read_text(encoding="utf-8"), encoding="utf-8")
    nested = repo / "shared" / ".shipwright" / "locks"
    nested.mkdir(parents=True)
    (nested / "bloat_pending.X.json").write_text("{}", encoding="utf-8")
    # -uall forces per-file enumeration so a leaked nested marker would surface
    # as `?? shared/.shipwright/locks/bloat_pending.X.json` (not a collapsed dir).
    out = subprocess.run(["git", "-C", str(repo), "status", "--porcelain", "-uall"],
                         capture_output=True, text=True).stdout
    assert ".shipwright/locks" not in out, f"nested locks dir leaked:\n{out}"
