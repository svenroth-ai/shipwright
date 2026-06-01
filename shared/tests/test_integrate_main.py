"""AC-6/AC-7 — `integrate_main.py` wrapper + the separate Run-ID follow-up commit.

The load-bearing claim (AC-6, empirically confirmed against the real audit):
because `audit_staleness.find_snapshot_commit` uses `git log --diff-filter=AM`
(which skips merge commits), the regenerated MD snapshots must live in a
**separate, non-merge** follow-up commit carrying the `Run-ID:` trailer — and the
real audit must then find that commit.
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))

from tools import integrate_main  # noqa: E402

_AUDIT_STALENESS = (
    REPO_ROOT / "plugins" / "shipwright-compliance" / "scripts" / "audit" / "audit_staleness.py"
)


def _load_find_snapshot_commit():
    """Import the REAL `find_snapshot_commit` by file path (drift-proof: the test
    exercises the actual audit, not a copy of its git query)."""
    spec = importlib.util.spec_from_file_location("audit_staleness_probe", _AUDIT_STALENESS)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    # Register before exec: @dataclass resolves `cls.__module__` via sys.modules.
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod.find_snapshot_commit


def _env() -> dict[str, str]:
    env = os.environ.copy()
    env.update(
        GIT_AUTHOR_NAME="Integrate Test",
        GIT_AUTHOR_EMAIL="integrate@test.invalid",
        GIT_COMMITTER_NAME="Integrate Test",
        GIT_COMMITTER_EMAIL="integrate@test.invalid",
    )
    return env


def _git(cwd: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args], cwd=str(cwd), env=_env(), capture_output=True, text=True, check=check
    )


def _seed_repo(root: Path, *, ours_dashboard: str, theirs_dashboard: str, source_conflict: bool):
    """main has a base dashboard; `origin_main` and `ours` diverge. If
    `source_conflict`, both also edit a real source file `app.py`."""
    _git(root, "init", "-b", "main")
    dash = root / ".shipwright" / "compliance" / "dashboard.md"
    dash.parent.mkdir(parents=True, exist_ok=True)
    dash.write_text("base dashboard\n", encoding="utf-8")
    (root / "app.py").write_text("base\n", encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-m", "base")

    _git(root, "checkout", "-b", "origin_main")
    dash.write_text(theirs_dashboard, encoding="utf-8")
    if source_conflict:
        (root / "app.py").write_text("origin change\n", encoding="utf-8")
    _git(root, "commit", "-am", "origin advances")

    _git(root, "checkout", "main")
    _git(root, "checkout", "-b", "ours")
    dash.write_text(ours_dashboard, encoding="utf-8")
    if source_conflict:
        (root / "app.py").write_text("iterate change\n", encoding="utf-8")
    _git(root, "commit", "-am", "iterate advances")


def test_integrate_resolves_and_audit_finds_followup(tmp_path: Path, monkeypatch) -> None:
    _seed_repo(
        tmp_path,
        ours_dashboard="iterate dashboard\n",
        theirs_dashboard="main dashboard\n",
        source_conflict=False,
    )

    def fake_regen(project_root, run_id, **kw):
        dash = Path(project_root) / ".shipwright" / "compliance" / "dashboard.md"
        dash.write_text(f"regenerated from merged tree ({run_id})\n", encoding="utf-8")
        _git(Path(project_root), "add", "--", ".shipwright/compliance/dashboard.md")
        return {".shipwright/compliance/dashboard.md": "regenerated"}

    monkeypatch.setattr(integrate_main.rcc, "regenerate_tracked_snapshots", fake_regen)

    result = integrate_main.integrate(
        tmp_path, "iterate-2026-05-31-churn-merge-resolver",
        merge_ref="origin_main", do_fetch=False,
    )

    assert result["status"] == "ok", result
    assert "merge-committed" in result["steps"]
    assert "regenerated-followup" in result["steps"]

    # HEAD is the follow-up: a NON-merge commit with a Run-ID trailer.
    head = _git(tmp_path, "rev-parse", "HEAD").stdout.strip()
    parents = _git(tmp_path, "rev-list", "--parents", "-n", "1", "HEAD").stdout.split()
    assert len(parents) == 2, "follow-up must be a non-merge commit (exactly one parent)"
    body = _git(tmp_path, "log", "-1", "--format=%B", "HEAD").stdout
    assert "Run-ID: iterate-2026-05-31-churn-merge-resolver" in body

    # The REAL audit finds the follow-up (not the merge, not None) — AC-6.
    find_snapshot_commit = _load_find_snapshot_commit()
    assert find_snapshot_commit(tmp_path) == head


def test_integrate_validates_events_on_clean_union_merge(tmp_path: Path, monkeypatch) -> None:
    """H1 regression: when `merge=union` resolves events.jsonl SILENTLY (a clean
    merge, no conflict), validation must still run — a corrupt historic line
    introduced by the union must abort the integrate before any commit."""
    root = tmp_path
    _git(root, "init", "-b", "main")
    (root / ".gitattributes").write_text("shipwright_events.jsonl merge=union\n", encoding="utf-8")
    base = '{"type":"phase_completed","id":"evt-base","v":1}'
    log = root / "shipwright_events.jsonl"
    log.write_text(base + "\n", encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-m", "base")

    _git(root, "checkout", "-b", "origin_main")
    log.write_text(base + "\nthis line is NOT json\n", encoding="utf-8")  # corrupt append
    _git(root, "commit", "-am", "main corrupts the log")

    _git(root, "checkout", "main")
    _git(root, "checkout", "-b", "ours")
    log.write_text(base + '\n{"type":"work_completed","adr_id":"iterate-x","id":"evt-run","v":1}\n', encoding="utf-8")
    _git(root, "commit", "-am", "iterate appends run event")

    called = {"regen": False}
    monkeypatch.setattr(
        integrate_main.rcc, "regenerate_tracked_snapshots",
        lambda *a, **k: called.__setitem__("regen", True) or {},
    )

    result = integrate_main.integrate(root, "iterate-x", merge_ref="origin_main", do_fetch=False)

    assert result["status"] == "events_invalid", result
    assert called["regen"] is False
    # Aborted cleanly: no merge in progress, no unmerged paths.
    assert _git(root, "rev-parse", "--verify", "--quiet", "MERGE_HEAD", check=False).returncode != 0
    assert _git(root, "diff", "--name-only", "--diff-filter=U").stdout.strip() == ""


def test_integrate_aborts_and_restores_on_source_conflict(tmp_path: Path, monkeypatch) -> None:
    _seed_repo(
        tmp_path,
        ours_dashboard="iterate dashboard\n",
        theirs_dashboard="main dashboard\n",
        source_conflict=True,  # app.py conflicts → non-churn → must abort
    )

    called = {"regen": False}

    def fake_regen(*a, **k):
        called["regen"] = True
        return {}

    monkeypatch.setattr(integrate_main.rcc, "regenerate_tracked_snapshots", fake_regen)

    result = integrate_main.integrate(
        tmp_path, "iterate-x", merge_ref="origin_main", do_fetch=False,
    )

    assert result["status"] == "blocked"
    assert "app.py" in result["blocking"]
    assert called["regen"] is False, "regeneration must not run when blocked"
    # merge --abort restored a clean tree (no unmerged paths, nothing staged).
    assert _git(tmp_path, "diff", "--name-only", "--diff-filter=U").stdout.strip() == ""
    assert _git(tmp_path, "diff", "--cached", "--name-only").stdout.strip() == ""
