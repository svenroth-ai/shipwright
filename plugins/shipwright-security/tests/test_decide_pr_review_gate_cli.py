"""CLI-wiring coverage for `decide_pr_review_gate.py` — makes sure the
string->bool translation from GitHub Actions step outputs/outcomes onto
`decide_gate`'s keyword arguments is exactly right (behavior itself is
covered in `test_pr_review_gate_verdict.py`)."""

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "plugins" / "shipwright-security" / "scripts" / "tools" / "decide_pr_review_gate.py"
spec = importlib.util.spec_from_file_location("decide_pr_review_gate", SCRIPT)
cli = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(cli)


def test_all_generated_pr_prints_success_and_the_reason(capsys):
    exit_code = cli.main([
        "--stage1-conclusion", "success",
        "--tier-outcome", "success",
        "--all-generated", "true",
        "--all-generated-reason", "no reviewable content - all 2 paths are generated artifacts",
        "--needs-review", "true",
        "--consume-waiver-outcome", "skipped",
        "--review-outcome", "skipped",
        "--tier-reason", "no trusted review waiver",
    ])
    assert exit_code == 0
    out = capsys.readouterr().out
    assert "state=success" in out
    assert "desc=no reviewable content - all 2 paths are generated artifacts" in out


def test_review_failure_prints_failure(capsys):
    exit_code = cli.main([
        "--stage1-conclusion", "success",
        "--tier-outcome", "success",
        "--all-generated", "false",
        "--needs-review", "true",
        "--consume-waiver-outcome", "skipped",
        "--review-outcome", "failure",
    ])
    assert exit_code == 0
    out = capsys.readouterr().out
    assert "state=failure" in out
    assert "desc=review blocked or did not complete" in out
