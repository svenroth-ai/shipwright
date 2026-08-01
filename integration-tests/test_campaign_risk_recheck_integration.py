"""Integration coverage for the campaign diff-driven risk re-check (Step 3.4).

This is the `category:"integration"` behavior the `cross_component` risk flag
requires: the units below (detector tuples, the re-check CLI, git's real
working-tree view, and the complexity floor the F11 verifier reads) each pass
their own unit tests, but the defect this change fixes lived *between* them —
nothing called the detectors, so every one of them was individually correct and
collectively inert.

So these drive the CLI as a REAL subprocess against a REAL git repository, rather
than calling `recheck()` in-process. Properties only a composed run can show:

1. **Uncommitted and untracked work is visible.** The runner commits at F6, after
   Step 3.4, so a committed range is empty here; and a brand-new hook file appears
   in no `git diff` at all.
2. **A workflow moved OUT of the trust boundary still escalates** — git's default
   rename detection reports only the new path.
3. **The floor matches what the verifier demands.** `check_integration_coverage`
   green-SKIPs below `medium`; the two live in different plugins with drift-pinned
   pattern copies (ADR-044 bans the import), so only a test holds them together.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
CLI = REPO_ROOT / "plugins" / "shipwright-iterate" / "scripts" / "lib" / "diff_risk_recheck.py"

def _verifier_evaluates_at() -> tuple[str, ...]:
    """Read OUT OF the verifier source, not copied. A third hand-written replica
    would let `("large",)` send every medium run back to a green SKIP while this
    test stayed green — pinning the CLI to a copy instead of to the verifier."""
    src = (
        REPO_ROOT / "shared" / "scripts" / "tools" / "verifiers"
        / "integration_coverage.py"
    ).read_text(encoding="utf-8")
    m = re.search(r"complexity not in \(([^)]*)\)", src)
    assert m, "could not locate the complexity gate in integration_coverage.py"
    return tuple(re.findall(r'"([a-z]+)"', m.group(1)))


def _git(repo: Path, *args: str) -> None:
    proc = subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, encoding="utf-8"
    )
    assert proc.returncode == 0, f"git {' '.join(args)} failed: {proc.stderr}"


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A real git repo with one committed baseline commit."""
    repo = tmp_path / "project"
    (repo / "src").mkdir(parents=True)
    (repo / "src" / "app.py").write_text("print('hi')\n", encoding="utf-8")
    _git(repo.parent, "init", "-b", "main", str(repo))
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "baseline")
    return repo


def run_cli(repo: Path, stage1: str = "small") -> tuple[int, dict]:
    """Invoke the re-check exactly as the runner contract's Step 3.4 does."""
    proc = subprocess.run(
        [
            sys.executable, str(CLI),
            "--project-root", str(repo),
            "--base-ref", "HEAD",
            "--stage1-complexity", stage1,
        ],
        capture_output=True, encoding="utf-8",
    )
    # The contract promises valid JSON on stdout at EVERY exit status.
    return proc.returncode, json.loads(proc.stdout)


# ---------------------------------------------------------------------------
# 1. Success path — hooks.json, left UNCOMMITTED (fixtures split per review O5:
#    an escalating fixture returns before this path can be observed at all)
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.covers("FR-01.11")
def test_uncommitted_cross_component_change_is_detected(repo: Path):
    """The regression that would make this whole mechanism a no-op."""
    hooks = repo / "plugins" / "shipwright-iterate" / "hooks"
    hooks.mkdir(parents=True)
    (hooks / "hooks.json").write_text('{"hooks": {}}\n', encoding="utf-8")
    _git(repo, "add", "-A")  # staged, deliberately NOT committed

    code, out = run_cli(repo, stage1="small")

    assert code == 0, f"cross-component alone must not escalate: {out}"
    assert "cross_component" in out["risk_flags"]
    assert out["complexity_floor"] == "medium"
    assert out["effective_complexity"] == "medium"
    assert out["upgraded"] is True


@pytest.mark.integration
@pytest.mark.covers("FR-01.11")
def test_unstaged_change_is_detected(repo: Path):
    """Not even staged — the runner may re-check before touching the index."""
    (repo / "src" / "app.py").write_text("print('changed')\n", encoding="utf-8")
    code, out = run_cli(repo)
    assert code == 0
    assert out["changed_file_count"] == 1
    assert out["diff_loc"] > 0, "numstat must yield real counts, not zero"


@pytest.mark.integration
@pytest.mark.covers("FR-01.11")
def test_untracked_new_hook_is_detected(repo: Path):
    """A NEW file appears in no `git diff` — only `ls-files --others` sees it."""
    hooks = repo / "plugins" / "x" / "hooks"
    hooks.mkdir(parents=True)
    (hooks / "post_tool.py").write_text("# new hook\n", encoding="utf-8")
    # deliberately never `git add`ed
    code, out = run_cli(repo)
    assert code == 0
    assert "cross_component" in out["risk_flags"], (
        "an untracked hook script must still raise cross_component"
    )


@pytest.mark.integration
@pytest.mark.covers("FR-01.11")
def test_large_untracked_file_trips_the_diff_size_arm(repo: Path):
    """AC5's `> 100 LOC` arm must fire when the change is entirely NEW files.

    numstat cannot see untracked files, so counting only its output reports
    `diff_loc: 0` here and skips the plan review for a 120-line addition."""
    (repo / "brand_new_module.py").write_text(
        "\n".join(f"line_{i} = {i}" for i in range(120)) + "\n", encoding="utf-8"
    )
    code, out = run_cli(repo, stage1="small")

    assert code == 0
    assert out["diff_loc"] >= 120, (
        f"untracked lines must be counted; got diff_loc={out['diff_loc']}"
    )
    assert out["plan_review_required"] is True


@pytest.mark.integration
@pytest.mark.covers("FR-01.11")
def test_clean_tree_raises_nothing(repo: Path):
    code, out = run_cli(repo)
    assert code == 0
    assert out["risk_flags"] == []
    assert out["effective_complexity"] == "small"


# ---------------------------------------------------------------------------
# 2. Escalation path — workflow-only fixture
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.covers("FR-01.11")
def test_ci_workflow_change_escalates(repo: Path):
    wf = repo / ".github" / "workflows"
    wf.mkdir(parents=True)
    (wf / "ci.yml").write_text("on: push\n", encoding="utf-8")

    code, out = run_cli(repo, stage1="small")

    assert code == 3, f"CI trust-boundary change must exit 3, got {code}: {out}"
    esc = out["escalate"]
    assert esc["required"] is True
    assert esc["reason_code"] == "ci_supplychain_requires_operator"
    assert esc["paths"] == [".github/workflows/ci.yml"]


@pytest.mark.integration
@pytest.mark.covers("FR-01.11")
def test_moving_a_workflow_out_of_the_trust_boundary_still_escalates(repo: Path):
    """The rename blind spot — only a real repo can prove this closed.

    Rename detection is ON by default and reports ONLY the new path, so moving
    `security.yml` to `security.yml.disabled` matched no CI pattern: exit 0, and an
    autonomous unit disables a security workflow unnoticed. `--no-renames` makes it
    a delete plus an add. Depends on git's real behaviour, not a synthetic string."""
    wf = repo / ".github" / "workflows"
    wf.mkdir(parents=True)
    (wf / "security.yml").write_text("on: push\njobs: {}\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "add security workflow")
    _git(repo, "mv", ".github/workflows/security.yml",
         ".github/workflows/security.yml.disabled")

    code, out = run_cli(repo, stage1="small")

    assert code == 3, (
        f"disabling a security workflow by rename must escalate, got {code}: {out}"
    )
    assert ".github/workflows/security.yml" in out["escalate"]["paths"], (
        "the ORIGINAL trust-boundary path must reach the operator; reporting only "
        "the new name hides what was disabled"
    )


@pytest.mark.integration
@pytest.mark.covers("FR-01.11")
def test_escalation_result_matches_the_runner_contract_schema(repo: Path):
    """The CLI's finding must be expressible as a valid escalated result — the
    schema sets `additionalProperties: false` and requires non-empty `ci_paths`
    for this reason_code, so a shape mismatch here is a contract break.
    """
    jsonschema = pytest.importorskip("jsonschema")
    schema = json.loads(
        (REPO_ROOT / "plugins" / "shipwright-iterate" / "agents"
         / "sub_iterate_runner_contract.schema.json").read_text(encoding="utf-8")
    )
    wf = repo / ".github" / "workflows"
    wf.mkdir(parents=True)
    (wf / "release.yml").write_text("on: push\n", encoding="utf-8")
    _, out = run_cli(repo)

    jsonschema.validate(
        {
            "sub_iterate_id": "3.1",
            "status": "escalated",
            "reason": "Diff touches the CI trust boundary",
            "reason_code": out["escalate"]["reason_code"],
            "detected_complexity": out["effective_complexity"],
            "ci_paths": out["escalate"]["paths"],
        },
        schema,
    )


# ---------------------------------------------------------------------------
# 3. The seam: CLI floor <-> what the F11 verifier will accept
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.covers("FR-01.11")
def test_floor_unskips_the_integration_coverage_gate(repo: Path):
    """Pins the two SSoTs together: the verifier recomputes `cross_component` only
    AFTER a complexity gate that green-SKIPs below medium. If this floor drops below
    that threshold the gate reports green without evaluating — silently."""
    hooks = repo / "shared" / "scripts" / "hooks"
    hooks.mkdir(parents=True)
    (hooks / "audit.py").write_text("# hook\n", encoding="utf-8")
    _git(repo, "add", "-A")

    _, out = run_cli(repo, stage1="trivial")

    assert "cross_component" in out["risk_flags"]
    evaluates_at = _verifier_evaluates_at()
    assert evaluates_at, "verifier threshold parsed as empty — the regex drifted"
    assert out["effective_complexity"] in evaluates_at, (
        f"floor {out['effective_complexity']!r} is not in the verifier's own "
        f"evaluate-set {evaluates_at} — check_integration_coverage would return "
        "a green SKIP for this change"
    )


@pytest.mark.integration
@pytest.mark.covers("FR-01.11")
def test_verifier_and_detector_agree_on_cross_component_paths():
    """The F11 verifier keeps a drift-pinned COPY of the pattern tuple (ADR-044
    forbids the cross-plugin import). Composition is only real if both halves
    classify the same path the same way."""
    sys.path.insert(0, str(REPO_ROOT / "plugins" / "shipwright-iterate" / "scripts" / "lib"))
    sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts" / "tools"))
    import diff_risk_recheck as drr
    from verifiers import integration_coverage as ic

    for path in (
        "plugins/shipwright-iterate/hooks/hooks.json",
        "shared/scripts/hooks/audit_compliance_on_stop.py",
        "shared/scripts/lib/autonomous_loop.py",
        "src/components/Button.tsx",
    ):
        detector = "cross_component" in drr.detect_diff_flags([path])
        verifier = ic._is_cross_component([path])
        assert detector == verifier, (
            f"{path}: re-check says {detector}, F11 verifier says {verifier} — "
            "the drift-pinned pattern copies have diverged"
        )
