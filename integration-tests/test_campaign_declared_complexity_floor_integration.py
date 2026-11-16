"""Integration: a campaign unit's declared complexity survives the whole chain.

The defect lived BETWEEN the pieces: the brief said `medium`, the planner dropped
it, Stage 1 and the Step 3.4 re-check each re-derived `small` from a 113-178 line
diff, and the F11 gate agreed with the wrong record. This drives the REAL planner
(`campaign_init.py`), the REAL Stage-1 classifier, the REAL re-check CLI against a
REAL git repo with an ordinary ~120-line change, and the REAL `run_all_checks`
registry, as subprocesses (FR-01.11/AC52).
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
LIB = REPO_ROOT / "plugins" / "shipwright-iterate" / "scripts" / "lib"
INIT = REPO_ROOT / "plugins" / "shipwright-iterate" / "scripts" / "tools" / "campaign_init.py"
RUN_ID = "iterate-2026-11-16-u1-declared-floor"
CHECK = "risk re-check recording integrity"


def _git(repo: Path, *args: str) -> None:
    proc = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, encoding="utf-8")
    assert proc.returncode == 0, f"git {' '.join(args)}: {proc.stderr}"


def _run(*argv: str) -> tuple[int, dict]:
    proc = subprocess.run([sys.executable, *argv], capture_output=True, encoding="utf-8")
    return proc.returncode, (json.loads(proc.stdout) if proc.stdout.strip().startswith("{") else {})


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    repo = tmp_path / "project"
    (repo / "src").mkdir(parents=True)
    (repo / "src" / "app.py").write_text("print('hi')\n", encoding="utf-8")
    _git(repo.parent, "init", "-b", "main", str(repo))
    _git(repo, "config", "user.email", "t@example.com")
    _git(repo, "config", "user.name", "T")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "baseline")
    # An ordinary change: ~120 added lines, no risk detector fires on it.
    (repo / "src" / "rules.py").write_text("".join(f"RULE_{i} = {i}\n" for i in range(120)), encoding="utf-8")
    _git(repo, "add", "src/rules.py")
    return repo


def _plan(repo: Path, complexity: str | None) -> Path:
    unit = {"id": "U1", "slug": "rule-format", "title": "Rule format", "scope": "Add a rule object."}
    if complexity:
        unit["complexity"] = complexity
    code, _ = _run(str(INIT), "--project-root", str(repo), "--campaign-slug", "camp",
                   "--intent", "i", "--sub-iterates", json.dumps([unit]))
    assert code == 0
    return repo / ".shipwright/planning/iterate/campaigns/camp/sub-iterates/U1-rule-format.md"


def _recheck(repo: Path, spec: Path, stage1: str) -> tuple[int, dict]:
    return _run(str(LIB / "diff_risk_recheck.py"), "--project-root", str(repo), "--base-ref", "HEAD",
                "--stage1-complexity", stage1, "--run-id", RUN_ID, "--spec", str(spec))


def _f5c(repo: Path, complexity: str) -> None:
    d = repo / ".shipwright" / "agent_docs" / "iterates"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{RUN_ID}.json").write_text(json.dumps({
        "run_id": RUN_ID, "date": "2026-11-16T00:00:00Z", "type": "bug",
        "complexity": complexity, "branch": f"iterate/{RUN_ID}", "tests_passed": True,
    }), encoding="utf-8")


def _gate(repo: Path):
    sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))
    from tools.verifiers.iterate_checks import run_all_checks

    return [r for r in run_all_checks(repo, RUN_ID) if r.name == CHECK]


@pytest.mark.integration
@pytest.mark.covers("FR-01.11/AC52")
def test_declared_medium_unit_with_a_small_diff_stays_medium_end_to_end(repo: Path):
    spec = _plan(repo, "medium")
    code, stage1 = _run(str(LIB / "classify_complexity.py"), "--message", spec.read_text(encoding="utf-8"), "--spec", str(spec))
    assert code == 0 and stage1["estimate"] == "medium"

    # Even a runner that carried a stale `small` into Step 3.4 cannot lower the tier.
    code, out = _recheck(repo, spec, stage1="small")
    assert code == 0
    assert out["effective_complexity"] == "medium" and out["plan_review_required"] is True

    _f5c(repo, "small")                                   # the under-record is caught ...
    (match,) = _gate(repo)
    assert match.ok is False

    _f5c(repo, out["effective_complexity"])               # ... the agreeing record passes
    (match,) = _gate(repo)
    assert match.ok is True
    record = json.loads((repo / ".shipwright/planning/iterate" / RUN_ID / "risk_recheck.json").read_text("utf-8"))
    assert record["risk_recheck"]["declared_complexity"] == "medium"


@pytest.mark.integration
@pytest.mark.covers("FR-01.11/AC52")
def test_unit_declaring_nothing_keeps_todays_small(repo: Path):
    spec = _plan(repo, None)
    code, out = _recheck(repo, spec, stage1="small")
    assert code == 0
    assert out["effective_complexity"] == "small" and out["declared_complexity"] is None
    _f5c(repo, "small")
    (match,) = _gate(repo)
    assert match.ok is True
