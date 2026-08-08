"""Pin the shared checkpoint which decides the plan review fallback route."""

from pathlib import Path


REFERENCE = (
    Path(__file__).resolve().parent.parent / "skills" / "plan" / "references"
    / "step-5-external-review.md"
)


def test_every_external_review_branch_routes_to_the_one_checkpoint():
    text = REFERENCE.read_text(encoding="utf-8")
    assert text.count("## Pre-5b Checkpoint") == 1
    assert text.count("## Self-Review Fallback") == 1
    branch_a = text[text.index("## Branch A"):text.index("## Branch B")]
    branch_b = text[text.index("## Branch B"):text.index("## Branch C")]
    branch_c = text[text.index("## Branch C"):text.index("## Pre-5b Checkpoint")]
    assert "then the **Pre-5b Checkpoint**, then **Step 5b**" in branch_a
    assert "see the **Pre-5b Checkpoint**" in branch_b
    assert "Go to the **Pre-5b Checkpoint** below" in branch_c
    for branch in (branch_a, branch_b, branch_c):
        assert "go straight to Step 5b" not in branch
