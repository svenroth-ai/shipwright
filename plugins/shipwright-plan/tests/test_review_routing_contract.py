"""Pin the shared checkpoint which decides the plan review fallback route,
and prove the Step 5a architecture-review CLI's real input contract.

FR-01.03/AC03, AC11 have no artifact a deterministic check can observe
mid-session (which reviewer ran, whether the user was actually asked) — the
same class of judgement criterion FR-01.03/AC02's drift test already covers
(`test_missing_key_stop_and_ask_drift.py`). PR review (high) found that
text-pinning alone does not PROVE either AC, since the pinned artifact
(`self_review_fallback_ran`) is write-only and nothing checks that the
production run actually behaved this way — so both are left unbound with
the reason recorded here and in the seam survey (Named Exception 8), the
drift-pin tests kept as a guard against the reference doc itself drifting.

FR-01.03/AC09, AC10 DO have a deterministic seam: the Step 5a CLI invocation
itself (`external_review.py --mode architecture`) refuses to run reviewed
over the plan in place of a brief — asserted below via the real command,
not a re-implementation of its input-selection logic. AC09 also has an
end-to-end test driving `external_review.main()` itself with only the
network call stubbed, after PR review (high) found the direct-renderer-call
test alone insufficient.
"""

import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

_SHARED_TOOLS = Path(__file__).resolve().parents[3] / "shared" / "scripts" / "tools"
if str(_SHARED_TOOLS) not in sys.path:
    sys.path.insert(0, str(_SHARED_TOOLS))


def _normalized(text: str) -> str:
    """Collapse markdown line-wrapping (including blockquote '> ' prefixes)
    to single spaces, so a phrase pinned below survives a wrap-column reflow
    without silently going unchecked."""
    text = re.sub(r"^>\s?", "", text, flags=re.MULTILINE)
    return re.sub(r"\s+", " ", text)

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
REFERENCE = PLUGIN_ROOT / "skills" / "plan" / "references" / "step-5-external-review.md"
_EXTERNAL_REVIEW_CLI = (
    PLUGIN_ROOT.parent.parent / "shared" / "scripts" / "tools" / "external_review.py"
)
_STRIP_KEYS = {"OPENROUTER_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY", "OPENAI_API_KEY"}


def _keyless_env() -> dict:
    return {k: v for k, v in os.environ.items() if k not in _STRIP_KEYS}


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


def test_self_review_fallback_only_runs_when_no_independent_review_completed():
    """Not bound to FR-01.03/AC03 (see seam survey Exception 8, new): PR
    review (high) found this pins only the instruction TEXT, not an
    observable artifact — `self_review_fallback_ran` (the would-be seam) is
    write-only, nothing reads it, so a production regression that ignored
    this instruction would still pass. Kept as a drift-pin guard (the class
    this repo already uses for AC02's identical situation), just no longer
    claimed as AC-proving. The plan's own author re-reading it never
    satisfies the review step UNLESS the independent reviewer (Step 5-int)
    could not be reached either — the one checkpoint that decides this names
    both conditions and treats the fallback as the last resort, not an
    option."""
    text = REFERENCE.read_text(encoding="utf-8")
    checkpoint = _normalized(text[
        text.index("## Pre-5b Checkpoint"): text.index("## Self-Review Fallback")
    ])
    assert "Step 5-int with `Ran: yes`, OR a completed Branch A external review" in checkpoint
    assert "run the **Self-Review Fallback**" in checkpoint
    fallback = _normalized(text[text.index("## Self-Review Fallback"): text.index("## Step 5b")])
    assert "Runs only when the Pre-5b Checkpoint above says no independent review completed" in fallback
    assert "true last resort" in fallback


def test_architecture_reject_stops_and_asks_the_user_to_choose():
    """Not bound to FR-01.03/AC11 (see seam survey Exception 8, new): same
    gap as AC03 above — pins the instruction text, but whether the run
    actually stopped and asked a person is not recorded anywhere a
    deterministic check can read mid-session. Either reviewer answering that
    the work should not be built this way stops the run and puts a
    three-way choice to a person — alternative, keep-with-reason, or
    rework — before Step 6."""
    body = REFERENCE.read_text(encoding="utf-8")
    step_5a = _normalized(
        body[body.index("## Step 5a"): body.index("## Branch B", body.index("## Step 5a"))]
    )
    assert "`reject` from either reviewer → STOP and ask the user" in step_5a
    assert "before Step 6" in step_5a
    assert (
        "take the alternative, keep the plan (I'll record why the objection "
        "does not hold), or rework and re-review?"
    ) in step_5a


@pytest.mark.covers("FR-01.03/AC09", "FR-01.03/AC10")
def test_architecture_mode_requires_a_brief_not_the_plan(tmp_path):
    """FR-01.03/AC09/AC10: the second question (should this be built at all)
    is asked over a short brief, never the plan itself — the real CLI
    refuses a plan handed to it in the brief's place (a usage error, not a
    silent fall-through that would anchor the reviewer on the plan's own
    reasoning)."""
    spec = tmp_path / "spec.md"
    plan = tmp_path / "plan.md"
    spec.write_text("# Spec\nStop the thing from breaking.", encoding="utf-8")
    plan.write_text("# Plan\nDo it this way, because X.\n", encoding="utf-8")
    fake_plugin = tmp_path / "fake-plugin"
    fake_plugin.mkdir()

    missing_brief = subprocess.run(
        [sys.executable, str(_EXTERNAL_REVIEW_CLI), "--mode", "architecture",
         "--spec-file", str(spec), "--plugin-root", str(fake_plugin)],
        capture_output=True, text=True, env=_keyless_env(), cwd=tmp_path,
    )
    assert missing_brief.returncode == 2
    assert "--brief-file" in missing_brief.stderr

    plan_instead_of_brief = subprocess.run(
        [sys.executable, str(_EXTERNAL_REVIEW_CLI), "--mode", "architecture",
         "--spec-file", str(spec), "--plan-file", str(plan),
         "--plugin-root", str(fake_plugin)],
        capture_output=True, text=True, env=_keyless_env(), cwd=tmp_path,
    )
    assert plan_instead_of_brief.returncode == 2
    assert "--plan-file belongs to --mode plan" in plan_instead_of_brief.stderr


def test_architecture_review_prompt_carries_the_brief_not_the_plan_reasoning():
    """Unit-level check of the template-substitution function
    `external_review.py` itself uses to build the request (not a
    re-implementation of it) — kept as a fast lower-level guard, but the
    real AC09 proof is the end-to-end test below, which drives the same
    substitution through the actual CLI entrypoint (PR review, high)."""
    import external_review

    brief_text = "BRIEF-ONLY: do a queue exist to fix X? (rejection reasons omitted)"
    spec_text = "SPEC-ONLY: X must not fail weekly."
    rendered = external_review._render_user_prompt(
        "Brief: {BRIEF}\nSpec: {SPEC}", brief_text, spec_text,
    )
    assert brief_text in rendered
    assert spec_text in rendered
    assert rendered == f"Brief: {brief_text}\nSpec: {spec_text}"


@pytest.mark.covers("FR-01.03/AC09")
def test_architecture_cli_end_to_end_threads_the_brief_into_the_outgoing_prompt(
    tmp_path, monkeypatch,
):
    """FR-01.03/AC09, full CLI path: PR review (high) found the sibling test
    above insufficient — it calls the renderer directly, so a CLI that
    accepted a brief and then silently reviewed something else would still
    pass it. This drives `external_review.main()` itself (real argparse,
    real mode selection, real prompt loading) and stubs only the actual
    network call (`retrying_completion`), so the assertion is on what the
    CLI actually sent, not on a re-implementation of its input-selection."""
    import external_review

    brief_text = "BRIEF-ONLY: should a retry queue exist at all for X?"
    spec_text = "SPEC-ONLY: X must not fail weekly."
    plan_text = "PLAN-ONLY: implement the retry queue this way, because Y."

    spec_file = tmp_path / "spec.md"
    brief_file = tmp_path / "brief.md"
    plan_file = tmp_path / "plan.md"
    spec_file.write_text(spec_text, encoding="utf-8")
    brief_file.write_text(brief_text, encoding="utf-8")
    plan_file.write_text(plan_text, encoding="utf-8")
    fake_plugin = tmp_path / "fake-plugin"
    fake_plugin.mkdir()

    captured_prompts: list[str] = []

    def fake_retrying_completion(client, *, via, max_retries, **create_kwargs):
        captured_prompts.append(create_kwargs["messages"][1]["content"])
        return {"status": "success", "feedback": "SHIPWRIGHT_VERDICT: approve"}

    monkeypatch.setattr(external_review, "retrying_completion", fake_retrying_completion)
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key-not-a-real-secret")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(
        sys, "argv",
        [
            "external_review.py", "--mode", "architecture",
            "--spec-file", str(spec_file), "--brief-file", str(brief_file),
            "--plugin-root", str(fake_plugin), "--project-root", str(tmp_path),
        ],
    )

    external_review.main()

    assert captured_prompts, "the CLI never reached the network-call boundary"
    for prompt in captured_prompts:
        assert brief_text in prompt
        assert plan_text not in prompt
