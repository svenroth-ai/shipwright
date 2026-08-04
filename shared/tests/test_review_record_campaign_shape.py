"""Integration: the campaign record shape the runner contract prescribes.

`cross_component` coverage for `iterate-2026-07-28-cascade-delegated-to-nobody`.
The three pieces this composes are the ones the defect fell between:

1. **the contract** — `sub-iterate-runner.md` Step 3.7's status-transition
   table, which says who may write which status,
2. **the CLI** — `record_review_pass.py`, run as a real subprocess, because the
   contract's value is that an agent can copy those commands and have them work,
3. **the gate** — `review_record_check.check_review_record`, in-process.

Asserting the markdown alone would prove only that someone wrote a table;
asserting the gate alone would prove only that a hand-built dict passes. The
bug lived in the join: the contract told the runner to close `code` as
completed, the CLI accepted it, and the gate had no way to know the pass had
not happened. So the commands are taken from the contract and actually run.

Raised as a requirement by the external plan review (openai #7): the first draft
of this test composed markdown ordering and a synthetic record, which would not
have caught the original defect.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _review_cli_harness import (  # noqa: E402
    EXTERNAL_REVIEW_OUTPUT,
    RUN_ID,
    make_project,
    payload,
    run_tool,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))

from tools.verifiers.review_record_check import check_review_record  # noqa: E402

_ITERATE = REPO_ROOT / "plugins" / "shipwright-iterate"
RUNNER_DOC = _ITERATE / "agents" / "sub-iterate-runner.md"

#: Exactly what the contract's table licenses the RUNNER to write. `code` and
#: `doubt` are `not_run` because the runner performs neither — it has no
#: `Agent` tool. `external_code` carries the code pass it actually ran.
_CAPABILITY_DISPOSITION = (
    "sub-iterate-runner has no Agent tool; internal cascade delegated to the "
    "campaign orchestrator (ADR-029, campaign mode only)"
)
_STAGE3_DISPOSITION = (
    "Stage 3 runs only behind a Stage 2 pass; the internal cascade did not run "
    "in this campaign sub-iterate"
)

#: Stage 1 shares Stage 2's cause in campaign mode: no Agent tool, no cascade.
_STAGE1_DISPOSITION = (
    "sub-iterate-runner has no Agent tool; the Stage-1 spec-reviewer HARD-GATE "
    "is delegated with the rest of the cascade (ADR-029, campaign mode only)"
)

CONTRACT_ROWS: tuple[tuple[str, str, str | None], ...] = (
    ("self", "completed", None),
    ("plan", "completed", None),
    ("spec", "not_run", _STAGE1_DISPOSITION),
    ("code", "not_run", _CAPABILITY_DISPOSITION),
    ("doubt", "not_run", _STAGE3_DISPOSITION),
    ("external_code", "completed", None),
)


def _norm_doc() -> str:
    """The runner contract, normalised for wording assertions."""
    text = RUNNER_DOC.read_text(encoding="utf-8")
    return re.sub(r"\s+", " ", re.sub(r"[*`]+", "", text)).lower()


def _record_row(root: Path, review_type: str, status: str, disposition: str | None):
    """Returns `(returncode, output)` — the harness's shape."""
    args = ["record", "--review-type", review_type, "--status", status]
    if disposition:
        args += ["--disposition", disposition]
    if status == "completed":
        # Evidence. The floor now asks whether a pass HAPPENED, and a completed
        # row with none is the shape it rejects — so the fixture has to produce
        # what a real recording produces, not the minimum the CLI accepts.
        args += ["--recorded-by", f"{review_type}-reviewer"]
    if status == "completed" and review_type in ("plan", "external_code"):
        args += [
            "--marker-status", "completed", "--provider", "openrouter",
            "--from", "external-review-json",
            "--payload-file", payload(root, f"{review_type}.json", EXTERNAL_REVIEW_OUTPUT),
        ]
    return run_tool(root, *args)


@pytest.fixture()
def campaign_root(tmp_path: Path) -> Path:
    """The project tree the CLI writes into, at `complexity: medium`.

    Built with the shared `_review_cli_harness` rather than a private copy —
    an earlier version forked `run_tool`/`make_project`, which the Stage-2
    reviewer caught as duplication (catalog D).
    """
    root = make_project(tmp_path)
    rc, out = run_tool(root, "init")
    assert rc == 0, out
    return root


# --- the join, end to end ---------------------------------------------------


def test_contract_shape_written_by_the_cli_passes_the_gate(campaign_root: Path):
    """The commands the contract prints must produce a record the gate accepts.

    This is the whole point of the fix: an honest campaign record — internal
    cascade `not_run` with its capability reason, external review carrying the
    pass — must SHIP. If it did not, the contract would be pushing runners back
    toward the mislabelling.
    """
    for review_type, status, disposition in CONTRACT_ROWS:
        rc, out = _record_row(campaign_root, review_type, status, disposition)
        assert rc == 0, f"{review_type}={status} was rejected by the CLI: {out}"

    result = check_review_record(campaign_root, RUN_ID)
    assert result.ok, result.detail


def test_the_gate_still_reports_what_the_substitution_costs(campaign_root: Path):
    """`external_code` alone satisfies the floor — the message must say what
    that does NOT buy, because Stage 1 and Stage 3 have no external route."""
    for review_type, status, disposition in CONTRACT_ROWS:
        _record_row(campaign_root, review_type, status, disposition)

    result = check_review_record(campaign_root, RUN_ID)
    assert result.ok, result.detail

    record = json.loads(
        (campaign_root / ".shipwright" / "planning" / "iterate" / RUN_ID
         / "reviews.json").read_text(encoding="utf-8")
    )
    assert record["reviews"]["code"]["status"] == "not_run"
    assert record["reviews"]["doubt"]["status"] == "not_run"
    assert record["reviews"]["external_code"]["status"] == "completed"

    # A green gate must not read as full coverage. This is the whole reason
    # the campaign residual gap was invisible: it passed, and said nothing.
    assert "external_code` alone" in result.detail, result.detail
    assert "spec-reviewer" in result.detail
    assert "doubt-reviewer" in result.detail


def test_no_substitution_note_when_the_internal_cascade_actually_ran(
    campaign_root: Path,
):
    """The note is about a substitution — with `code` completed there is none,
    and a gate that cried wolf on every run would be tuned out."""
    for review_type, status, disposition in CONTRACT_ROWS:
        if review_type in ("code", "spec"):
            # Stage 1 too: a completed Stage 2 with an unrun Stage 1 is the
            # cascade skipping its own HARD-GATE, which the gate now blocks.
            _record_row(campaign_root, review_type, "completed", None)
            continue
        _record_row(campaign_root, review_type, status, disposition)

    result = check_review_record(campaign_root, RUN_ID)
    assert result.ok, result.detail
    assert "NOTE" not in result.detail, result.detail


def test_unrecorded_doubt_blocks_the_push(campaign_root: Path):
    """The runner cannot skip the rows and push anyway.

    Its own F6-verify runs this verifier, so a `pending` type is what forces
    the runner to record — and, before this fix, what pressured it into
    inventing a status the contract never taught it.
    """
    for review_type, status, disposition in CONTRACT_ROWS:
        if review_type == "doubt":
            continue
        _record_row(campaign_root, review_type, status, disposition)

    result = check_review_record(campaign_root, RUN_ID)
    assert result.ok is False, result.detail
    assert "doubt" in result.detail


def test_a_bare_delegated_disposition_is_rejected(campaign_root: Path):
    """"delegated" is the word that hid the defect. The schema requires a
    disposition to NAME a rule (>1 word, >=12 chars), so the capability limit
    has to be spelled out where a reader will see it."""
    rc, _out = _record_row(campaign_root, "code", "not_run", "delegated")
    assert rc != 0, (
        "a one-word disposition must not be accepted — it is exactly how an "
        "unreviewed change gets laundered into a passing gate"
    )


def test_runner_may_not_close_code_completed_and_the_contract_says_so(
    campaign_root: Path,
):
    """The CLI cannot know who ran the review, so the contract is the only
    place this can be enforced. Pin that it says it.

    The pairing matters: the CLI *will* accept `code=completed` (asserted
    here), which is precisely why the prose has to forbid it.
    """
    rc, out = _record_row(campaign_root, "code", "completed", None)
    assert rc == 0, f"the CLI itself has no provenance to check: {out}"

    assert "may never write code or doubt as completed" in _norm_doc(), (
        "the runner contract must forbid closing code/doubt as completed — "
        "this sentence is the only enforcement point, since the CLI cannot "
        "know who ran the review"
    )


def test_substitution_note_does_not_claim_doubt_was_skipped_when_it_ran(
    campaign_root: Path,
):
    """Stage-1 review finding (low): `doubt` is recorded independently, so
    'neither ran' is false for a record where doubt=completed."""
    for review_type, status, disposition in CONTRACT_ROWS:
        if review_type == "doubt":
            _record_row(campaign_root, "doubt", "completed", None)
            continue
        _record_row(campaign_root, review_type, status, disposition)

    result = check_review_record(campaign_root, RUN_ID)
    assert result.ok, result.detail
    assert "neither ran" not in result.detail, result.detail
    assert "Stage-3 did" in result.detail, result.detail


# --- the `code` row is written once ----------------------------------------


def test_the_code_row_cannot_be_written_twice(campaign_root: Path):
    """Immutability is why Stage 1 cannot share this row.

    The first version of this fix documented BOTH Stage 1 and Stage 2 writing
    `code`. The second write raises, and `--force` replaces the entry rather
    than merging — so one stage's verdict would vanish. That is the mechanical
    fact behind "the `code` row belongs to Stage 2".
    """
    rc_first, out_first = _record_row(campaign_root, "code", "completed", None)
    assert rc_first == 0, out_first

    rc_second, _out = _record_row(campaign_root, "code", "completed", None)
    assert rc_second != 0, (
        "a second write to `code` must fail — if it silently succeeded, one "
        "stage's verdict would be lost without anyone noticing"
    )




# --- the contract and the test agree on the same rows -----------------------


@pytest.mark.parametrize("review_type,status", [
    (r, s) for r, s, _ in CONTRACT_ROWS
])
def test_contract_table_lists_every_row_this_test_writes(review_type, status):
    """Drift guard: if the contract's table changes, this test's fixture is
    stale and must be updated with it — otherwise the integration proves a
    shape nobody is told to produce.

    Scoped to the Step 3.7 table and asserted on the type-to-status PAIRING.
    The first version grepped bare substrings against the whole document, so 8
    of its 10 assertions were already true before the fix and flipping the
    table's `code, doubt` row to permit `completed` — the exact regression it
    is named after — would have left every case green.
    """
    table = _step_37_table()
    assert review_type in table, f"the Step 3.7 table must carry the {review_type} row"
    if status == "not_run":
        assert "| spec (stage 1), code, doubt | orchestrator - not the runner | not_run only" in table, (
            f"{review_type} is an internal stage: the table must own it to the "
            "orchestrator and cap the runner at not_run"
        )
    else:
        assert "completed" in table, (
            f"{review_type} is the runner's own work and must be recordable "
            "as completed"
        )


def _step_37_table() -> str:
    """Just the actor table, normalised — not the whole document.

    Scoped deliberately: grepping the whole 480-line contract made 8 of this
    guard's 10 assertions true before the fix ever landed.
    """
    section = _norm_doc_section("### Step 3.7:")
    start = section.index("| review type")
    return section[start:section.index("the runner may never", start)]


def _norm_doc_section(heading: str) -> str:
    text = RUNNER_DOC.read_text(encoding="utf-8")
    start = text.index(heading)
    rest = text[start + len(heading):]
    end = rest.find("\n### ")
    body = heading + (rest if end < 0 else rest[:end])
    body = body.replace("—", "-").replace("’", "'")
    return re.sub(r"\s+", " ", re.sub(r"[*`]+", "", body)).lower()


def test_the_table_never_lets_the_runner_close_an_internal_stage_completed():
    """The pairing that matters, asserted once and directly.

    The literal includes `spec`: Stage 1 joined the row when it became
    recordable, and it belongs there for the same reason as the other two — the
    campaign runner has no Agent tool, so it performs none of the three and may
    write none of them `completed`.
    """
    table = _step_37_table()
    assert "| spec (stage 1), code, doubt | orchestrator - not the runner | not_run only" in table, (
        "the internal stages must be one row, owned by the orchestrator, and "
        "writable by the runner only as not_run"
    )
