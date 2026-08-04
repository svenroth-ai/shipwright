"""Integration: the 3f-bis handover — runner delegates, orchestrator promotes.

`cross_component` coverage for `iterate-2026-07-31-it7b-campaign-cascade`.

The sibling module `test_review_record_campaign_shape.py` pins the state the
runner LEAVES: `spec`/`code`/`doubt` closed `not_run` with their capability
reason. This module pins what happens NEXT — the step that did not exist until
this change. The campaign orchestrator has the `Agent` tool the runner lacks,
so at `3f-bis` (after `record`, before `merge`) it runs the delegated cascade
and promotes those three rows to `completed`.

Three pieces are composed, and the defect lived between them:

1. **the contract** — `campaign-mode.md` step 3f-bis, which prescribes the
   order `spec` → `code` → `doubt` and the use of `--force`. The prose
   itself is asserted in `test_campaign_review_contract_prose.py`, which
   already owns that document and its normaliser;
2. **the CLI** — `record_review_pass.py`, run as a real subprocess, because
   3f-bis's value is that an orchestrator can copy those commands and have
   them work,
3. **the gate** — `review_record_check.check_review_record`, in-process.

Asserting the markdown alone would prove only that someone wrote a step.
Asserting the gate alone would prove only that a hand-built dict passes. The
promotion is refused without `--force` and the gate rejects Stage 2 promoted
ahead of Stage 1 — neither is visible from either side on its own.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _review_cli_harness import (  # noqa: E402
    CODE_REVIEWER_REPLY,
    DOUBT_REVIEWER_REPLY,
    EXTERNAL_REVIEW_OUTPUT,
    RUN_ID,
    make_project,
    payload,
    run_tool,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))

from tools.verifiers.review_record_check import check_review_record  # noqa: E402

#: A Stage-1 PASS. Per `from_spec_reviewer`, an empty `spec_citations` list is
#: the honest empty result — a PASS finds no divergence between spec and diff.
SPEC_REVIEWER_PASS = json.dumps({
    "stage": "spec", "verdict": "PASS", "spec_citations": [],
})

#: What the RUNNER writes: it performs none of the three internal passes.
_DELEGATED = (
    ("spec", "the Stage-1 spec-reviewer HARD-GATE is delegated to the campaign "
             "orchestrator (ADR-029, campaign mode only)"),
    ("code", "the sub-iterate-runner has no Agent tool; the internal cascade is "
             "delegated to the campaign orchestrator (ADR-029)"),
    ("doubt", "Stage 3 runs only behind a Stage 2 pass; the internal cascade did "
              "not run in this campaign sub-iterate"),
)


@pytest.fixture()
def campaign_root(tmp_path: Path) -> Path:
    """A medium sub-iterate whose runner has just finished and pushed."""
    root = make_project(tmp_path)
    rc, out = run_tool(root, "init")
    assert rc == 0, out

    for review_type, status, extra in (
        ("self", "completed", ["--recorded-by", "self-review"]),
        ("plan", "completed", ["--recorded-by", "plan-review",
                                "--marker-status", "completed",
                                "--provider", "openrouter",
                                "--from", "external-review-json",
                                "--payload-file", payload(
                                    tmp_path, "plan.json", EXTERNAL_REVIEW_OUTPUT)]),
        ("external_code", "completed", ["--recorded-by", "external-review",
                                         "--marker-status", "completed",
                                         "--provider", "openrouter",
                                         "--from", "external-review-json",
                                         "--payload-file", payload(
                                             tmp_path, "code.json",
                                             EXTERNAL_REVIEW_OUTPUT)]),
    ):
        rc, out = run_tool(root, "record", "--review-type", review_type,
                           "--status", status, *extra)
        assert rc == 0, f"{review_type}: {out}"

    for review_type, disposition in _DELEGATED:
        rc, out = run_tool(root, "record", "--review-type", review_type,
                           "--status", "not_run", "--disposition", disposition)
        assert rc == 0, f"{review_type}: {out}"
    return root


def _promote(root: Path, tmp_path: Path, review_type: str, source: str,
             reply: str, *, force: bool = True):
    """Promote one delegated row the way step 3f-bis prescribes."""
    args = [
        "record", "--review-type", review_type, "--status", "completed",
        "--from", source,
        "--payload-file", payload(tmp_path, f"{review_type}.txt", reply),
        "--recorded-by", source,
    ]
    if force:
        args.append("--force")
    return run_tool(root, *args)


# --- the handover, end to end -----------------------------------------------


def test_orchestrator_promotes_the_delegated_rows_and_the_gate_accepts_it(
    campaign_root: Path, tmp_path: Path,
):
    """The whole point of 3f-bis: a sub-iterate that actually got its cascade
    must ship a record saying so, under the actor that performed it."""
    for review_type, source, reply in (
        ("spec", "spec-reviewer", SPEC_REVIEWER_PASS),
        ("code", "code-reviewer", CODE_REVIEWER_REPLY),
        ("doubt", "doubt-reviewer", DOUBT_REVIEWER_REPLY),
    ):
        rc, out = _promote(campaign_root, tmp_path, review_type, source, reply)
        assert rc == 0, f"3f-bis could not promote {review_type}: {out}"

    result = check_review_record(campaign_root, RUN_ID)
    assert result.ok, result.detail

    record = json.loads(
        (campaign_root / ".shipwright" / "planning" / "iterate" / RUN_ID
         / "reviews.json").read_text(encoding="utf-8")
    )
    assert record["reviews"]["spec"]["status"] == "completed", (
        "Stage 1 is an ordinary `reviews` key since the promotion; it lived "
        "under a sibling `gates` object only while the webui refused to read a "
        "record carrying a sixth key"
    )
    assert "gates" not in record, (
        "the retired seam is not written, and a pending legacy row is dropped "
        "once the real answer lands"
    )
    for review_type in ("code", "doubt"):
        assert record["reviews"][review_type]["status"] == "completed"
    assert record["reviews"]["code"]["recorded_by"] == "code-reviewer", (
        "who did the work decides the name — the orchestrator's cascade is a "
        "code-reviewer pass, not an external one"
    )


def test_promotion_is_refused_without_force(campaign_root: Path, tmp_path: Path):
    """3f-bis MUST pass `--force`, and this is why.

    The runner already closed the row, and a closed row is immutable
    (`re-recording a closed type exits 3`). Had `--force` not existed, the
    orchestrator's only route would have been to hand-edit `reviews.json` —
    i.e. fabricating the record would have been easier than writing it. This
    test is the reason the step is specified with the flag rather than without.
    """
    rc, out = _promote(campaign_root, tmp_path, "spec", "spec-reviewer",
                       SPEC_REVIEWER_PASS, force=False)
    assert rc == 3, (
        f"expected the terminal-row refusal (exit 3), got {rc}: {out}"
    )


def test_stage_2_cannot_be_promoted_ahead_of_stage_1(
    campaign_root: Path, tmp_path: Path,
):
    """The order in 3f-bis is load-bearing, not cosmetic.

    `spec` is the HARD-GATE: a `code` row completed while `spec` is not
    completed FAILS, because Stage 2 cannot legitimately have run without its
    gate passing first. An orchestrator that promoted `code` first — the
    obvious mistake, since `code` is the row people think of — would red its
    own sub-iterate at F11.
    """
    rc, out = _promote(campaign_root, tmp_path, "code", "code-reviewer",
                       CODE_REVIEWER_REPLY)
    assert rc == 0, out

    result = check_review_record(campaign_root, RUN_ID)
    assert result.ok is False, (
        "a completed `code` over a non-completed `spec` must fail the gate; "
        f"it passed instead: {result.detail}"
    )
