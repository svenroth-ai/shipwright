"""Shared test fixtures."""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

# Add shared scripts to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))


# Real platform os.name, captured once at import (before any test patches it).
_REAL_OS_NAME = os.name


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    """Stop an ``os.name="nt"`` monkeypatch from crashing the whole session
    on a non-Windows host.

    Several tests here simulate Windows by patching ``os.name`` to ``"nt"``
    (npm.cmd resolution, dev-server spawn, cmd_resolver, …). The monkeypatch
    is restored at *fixture teardown*, which runs AFTER this makereport phase.
    So if such a test FAILS on Linux/macOS, pytest's own failure renderer
    (``_pytest.nodes._repr_failure_py`` → ``Path(os.getcwd())``) instantiates a
    ``WindowsPath`` on a POSIX host → ``NotImplementedError`` → INTERNALERROR
    that aborts the ENTIRE run, masking every test after it. Surfaced the
    moment ``shared/tests`` first ran in CI (iterate-2026-05-31-ci-shared-tests).

    Pin ``os.name`` to the real platform for the duration of report rendering,
    then restore whatever the test had set. Report-only — the test already ran
    with its patched value, so behaviour is unchanged; only the rendered
    paths are POSIX-correct.
    """
    saved = os.name
    if saved != _REAL_OS_NAME:
        os.name = _REAL_OS_NAME
    try:
        yield
    finally:
        os.name = saved


_OSS_SCANNERS = ("semgrep", "trivy", "gitleaks")


@pytest.fixture(autouse=True)
def _isolate_scanner_environment(monkeypatch):
    """No-op safety net for the orchestrator path.

    Iterate sec-report-and-orchestrator-decouple (2026) removed
    `_check_security_available()`. The env-clearing here is now defensive:
    ensures AIKIDO_CLIENT_ID and any future scanner-related env vars don't
    leak from the host into shared-test assertions. Mirror of fixtures in
    plugins/shipwright-run/tests/conftest.py + integration-tests/conftest.py.
    """
    monkeypatch.delenv("AIKIDO_CLIENT_ID", raising=False)
    monkeypatch.delenv("SHIPWRIGHT_SCANNER_BACKEND", raising=False)
    monkeypatch.setenv("SHIPWRIGHT_TEST_DISABLE_OSS_SCANNERS", "1")
    real_which = shutil.which

    def _which_no_oss(cmd, *args, **kwargs):
        if cmd in _OSS_SCANNERS:
            return None
        return real_which(cmd, *args, **kwargs)

    monkeypatch.setattr(shutil, "which", _which_no_oss)


@pytest.fixture(autouse=True)
def _isolate_github_pr_api(monkeypatch):
    """Neutralise the live PR-CI fetchers by default
    (iterate-2026-06-11-automerge-gh-pr-ci-producer).

    ``github_triage.import_findings`` now fetches open PRs + per-PR check-runs.
    ``gh api`` substitutes ``{owner}/{repo}`` from the cwd's git remote — so an
    un-stubbed fetch in a test running inside the shipwright worktree would hit
    the REAL repo (non-deterministic, network-bound). Default everything to "no
    open PRs / fetch unavailable" so existing consumer tests stay hermetic; the
    dedicated ``test_github_triage_pr_ci`` suite re-stubs these explicitly.
    """
    try:
        import github_pr_api  # noqa: PLC0415
    except ImportError:
        return
    monkeypatch.setattr(github_pr_api, "fetch_open_prs", lambda: None, raising=False)
    monkeypatch.setattr(
        github_pr_api, "fetch_pr_check_runs", lambda head_sha: None, raising=False
    )
    monkeypatch.setattr(
        github_pr_api, "fetch_pr_state", lambda pr_number: None, raising=False
    )


@pytest.fixture(autouse=True)
def _sweep_tests_unset_ci(request, monkeypatch):
    # Sweep/D2V suites run the REAL outbox sweep, which no-ops under `$CI`
    # (`ci_without_optin` safety); they assert it COMMITS, so must run as a local
    # iterate ($CI unset). `$CI=true` on GitHub Actions → 44 false skips (PR #172).
    # A guard test re-sets CI in its own body (its setenv runs after this fixture).
    if request.path.name.startswith(("test_sweep_outbox", "test_d2v_empirical_gate")):
        monkeypatch.delenv("CI", raising=False)


@pytest.fixture
def tmp_project(tmp_path):
    """Create a temporary project directory with .shipwright/agent_docs/."""
    agent_docs = tmp_path / ".shipwright" / "agent_docs"
    agent_docs.mkdir(parents=True, exist_ok=True)
    return tmp_path


@pytest.fixture
def project_with_configs(tmp_project):
    """Create a temporary project with sample config files."""
    run_config = {
        "scope": "full_app",
        "profile": "supabase-nextjs",
        "autonomy_level": 2,
        "current_step": "build",
        "completed_steps": ["project", "design", "plan"],
        "completed_splits": ["01-auth"],
        "pipeline": ["project", "design", "plan", "build", "test", "changelog", "deploy"],
    }
    project_config = {
        "status": "complete",
        "splits": [
            {"name": "01-auth", "status": "complete"},
            {"name": "02-dashboard", "status": "in_progress"},
        ],
    }
    plan_config = {
        "status": "complete",
        "split": "02-dashboard",
    }
    build_config = {
        "sections": [
            {"name": "01-layout", "status": "complete", "commit": "abc1234"},
            {"name": "02-widgets", "status": "in_progress"},
        ],
    }

    for name, data in [
        ("shipwright_run_config.json", run_config),
        ("shipwright_project_config.json", project_config),
        ("shipwright_plan_config.json", plan_config),
        ("shipwright_build_config.json", build_config),
    ]:
        (tmp_project / name).write_text(json.dumps(data, indent=2), encoding="utf-8")

    return tmp_project


@pytest.fixture
def git_origin_repo(tmp_path):
    """A git working clone with a local bare 'origin' remote + one commit.

    Returns ``(work, origin)`` Paths. ``work`` is the MAIN repo working tree
    for worktree-isolation tests; ``.worktrees/<slug>`` children are created
    under it. ``origin`` is a local bare repo so ``git fetch origin`` works
    fully offline.

    ``.shipwright/`` is committed (``.gitkeep``) so the repo mirrors a real
    Shipwright project — where ``.shipwright/`` always carries tracked content.
    Without that, git collapses an untracked ``.shipwright/`` into a single
    ``?? .shipwright/`` status entry and the leak-guard's run-infra exclusion
    (which keys on ``.shipwright/runs/`` etc.) cannot see inside it.
    """
    env = os.environ.copy()
    env.update(
        {
            "GIT_AUTHOR_NAME": "Iso Test",
            "GIT_AUTHOR_EMAIL": "iso@test.invalid",
            "GIT_COMMITTER_NAME": "Iso Test",
            "GIT_COMMITTER_EMAIL": "iso@test.invalid",
        }
    )

    def _git(cwd, *args):
        return subprocess.run(
            ["git", *args],
            cwd=str(cwd),
            env=env,
            capture_output=True,
            text=True,
            check=True,
        )

    origin = tmp_path / "origin.git"
    work = tmp_path / "work"
    _git(tmp_path, "init", "--bare", "-b", "main", str(origin))
    _git(tmp_path, "clone", str(origin), str(work))
    (work / "README.md").write_text("hello\n", encoding="utf-8")
    shipwright_dir = work / ".shipwright"
    shipwright_dir.mkdir()
    (shipwright_dir / ".gitkeep").write_text("", encoding="utf-8")
    _git(work, "add", "-A")
    _git(work, "commit", "-m", "init")
    _git(work, "push", "origin", "main")
    _git(work, "remote", "set-head", "origin", "main")
    return work, origin


@pytest.fixture
def make_worktree():
    """Factory: ``make_worktree(work, slug)`` adds a linked git worktree.

    Creates ``<work>/.worktrees/<slug>`` on branch ``iterate/<slug>`` from
    ``main`` and returns its path. Shared by every worktree-isolation test
    (events-log resolution, decision-drop resolution, finalization checks)
    so the ``git worktree add`` invocation lives in exactly one place.
    """
    def _make(work: Path, slug: str) -> Path:
        wt = work / ".worktrees" / slug
        subprocess.run(
            ["git", "-C", str(work), "worktree", "add", str(wt),
             "-b", f"iterate/{slug}", "main"],
            capture_output=True, text=True, check=True,
        )
        return wt

    return _make


@pytest.fixture
def remove_worktree():
    """Factory: ``remove_worktree(work, wt)`` tears a linked worktree down
    the way iterate F11 cleanup (``git worktree remove --force``) does."""
    def _remove(work: Path, wt: Path) -> None:
        subprocess.run(
            ["git", "-C", str(work), "worktree", "remove", "--force", str(wt)],
            capture_output=True, text=True, check=True,
        )

    return _remove


# --------------------------------------------------------------------------- #
# D2V empirical-gate evidence collector (campaign 2026-06-08-triage-outbox-delivery)
# --------------------------------------------------------------------------- #


@pytest.fixture(scope="session")
def _d2v_evidence():
    """Session-scoped :class:`_d2v_helpers.Evidence` shared across the D2V gate
    modules so the concurrency-stress result AND the three e2e proofs land in ONE
    human-auditable artifact, flushed at session teardown with the exact node ids
    of the tests that ran.

    The artifact is written ONLY when at least one D2V method recorded a result
    (i.e. the gate actually ran) — a session that didn't touch the gate leaves
    the prior artifact untouched. Underscore-prefixed so it is unmistakably the
    gate's internal collector, not a general fixture.
    """
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import _d2v_helpers as ev  # noqa: PLC0415

    evidence = ev.Evidence()
    node_ids: list[str] = []
    _D2V_LIVE_EVIDENCE.clear()
    _D2V_LIVE_EVIDENCE.append(evidence)  # expose to pytest_sessionfinish
    yield _D2VEvidenceProxy(evidence, node_ids)
    if evidence.methods:
        evidence.flush(node_ids=sorted(set(node_ids)))


class _D2VEvidenceProxy:
    """Thin wrapper handed to each gate test: ``record(...)`` a MethodResult and
    register the calling test's node id (captured via the ``request`` fixture)."""

    def __init__(self, evidence, node_ids: list[str]):
        self._evidence = evidence
        self._node_ids = node_ids

    def record(self, result) -> None:
        self._evidence.record(result)

    def add_node_id(self, nid: str) -> None:
        self._node_ids.append(nid)


@pytest.fixture
def _evidence(_d2v_evidence, request):
    """Per-test handle: registers this test's node id with the session collector,
    then exposes ``record(MethodResult)``."""
    _d2v_evidence.add_node_id(request.node.nodeid)
    return _d2v_evidence


# Session-level handle the sessionfinish hook reads to enforce gate completeness.
_D2V_LIVE_EVIDENCE: list = []


def pytest_sessionfinish(session, exitstatus):
    """Gate-completeness enforcement (external-review): a PARTIAL D2V gate run must
    not silently pass. The gate is anchored on METHOD 1 (the >=200-trial slow
    proof): if METHOD 1 recorded, this IS a gate run and EVERY mandatory method
    must also have recorded — otherwise fail the session (a partial slow selection
    cannot masquerade as a complete gate). If METHOD 1 did NOT record, this is the
    default fast suite (smoke + e2e only), not the gate → no interference."""
    if not _D2V_LIVE_EVIDENCE:
        return
    evidence = _D2V_LIVE_EVIDENCE[0]
    recorded = evidence.recorded_tags()
    if "METHOD 1" not in recorded:
        return  # not a gate run (the >=200 anchor wasn't selected)
    missing = evidence.missing_required()
    if missing:
        session.exitstatus = 1
        rep = session.config.pluginmanager.get_plugin("terminalreporter")
        if rep is not None:
            rep.write_line(
                f"D2V GATE INCOMPLETE — METHOD 1 ran but mandatory {sorted(missing)} "
                f"missing; a partial gate run is NOT a pass.",
                red=True,
            )
