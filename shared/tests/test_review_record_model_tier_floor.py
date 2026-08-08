"""F11's model-tier floor note — advisory only, never a block.

Exercises `check_review_record` end-to-end (fabricated iterate entry + a
hand-built record), the same pattern `test_review_record_evidence_floor.py`
uses. The one property every test here shares: `result.ok` stays `True`
regardless of tier — a floor is a complement, not a gate (BRIEF: "takes no
freedom from anyone").
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from lib.review_record import (  # noqa: E402
    REVIEW_TYPES,
    STATUS_COMPLETED,
    STATUS_NOT_RUN,
    make_entry,
    new_record,
    upsert_review,
    write_record,
)
from tools.verifiers.review_record_check import check_review_record  # noqa: E402
from tools.verifiers.review_record_model_tier import model_tier_note  # noqa: E402

RUN = "iterate-2026-07-29-tier-floor"
WHY = "not needed for this test's floor scenario"


def _entry(root: Path) -> None:
    d = root / ".shipwright" / "agent_docs" / "iterates"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{RUN}.json").write_text(json.dumps({
        "run_id": RUN, "type": "bug", "complexity": "medium",
        "branch": "iterate/x", "tests_passed": True,
        "date": "2026-07-29T00:00:00+00:00",
    }), encoding="utf-8")


def _configure_floor(root: Path, tier: str) -> None:
    (root / "shipwright_model_config.json").write_text(
        json.dumps({"floors": {"review": tier}}), encoding="utf-8",
    )


def _record(root: Path, code_model_tier: str | None, spec_model_tier: str | None = "opus") -> None:
    """`spec_model_tier` defaults to `"opus"` — the top rank, so `spec`'s row
    stays silent (at-or-above any floor these tests configure) and every
    test below isolates `code`'s behavior, the thing it actually names."""
    record = new_record(RUN)
    for review_type in REVIEW_TYPES:
        # `spec` is set explicitly below (Stage-1-before-Stage-2 HARD-GATE:
        # a completed `code` row requires a completed+evidenced `spec` row).
        if review_type not in ("code", "spec"):
            record = upsert_review(record, make_entry(
                review_type, STATUS_NOT_RUN, disposition=WHY), force=True)
    spec_kwargs = {"recorded_by": "spec-reviewer"}
    if spec_model_tier is not None:
        spec_kwargs["model_tier"] = spec_model_tier
    record = upsert_review(record, make_entry("spec", STATUS_COMPLETED, **spec_kwargs))
    code_kwargs = {"recorded_by": "code-reviewer"}
    if code_model_tier is not None:
        code_kwargs["model_tier"] = code_model_tier
    record = upsert_review(record, make_entry("code", STATUS_COMPLETED, **code_kwargs))
    write_record(root, RUN, record)


def test_no_floor_configured_is_silent(tmp_path: Path) -> None:
    _entry(tmp_path)
    _record(tmp_path, code_model_tier="haiku")
    # no shipwright_model_config.json at all

    result = check_review_record(tmp_path, RUN)

    assert result.ok is True
    assert "floor" not in result.detail.lower()


def test_below_floor_tier_is_flagged_but_still_passes(tmp_path: Path) -> None:
    _entry(tmp_path)
    _configure_floor(tmp_path, "opus")
    _record(tmp_path, code_model_tier="sonnet")

    result = check_review_record(tmp_path, RUN)

    assert result.ok is True, "a below-floor tier must never block F11"
    assert "sonnet" in result.detail
    assert "opus" in result.detail


def test_inherit_tier_is_flagged_as_unconfirmed_when_floor_configured(tmp_path: Path) -> None:
    _entry(tmp_path)
    _configure_floor(tmp_path, "opus")
    _record(tmp_path, code_model_tier="inherit")

    result = check_review_record(tmp_path, RUN)

    assert result.ok is True
    assert "session-inherit" in result.detail or "not confirmed" in result.detail


def test_unrecorded_tier_is_flagged_not_silent(tmp_path: Path) -> None:
    """`check_review_record` only ever reads the CURRENT run's own record —
    never a historical one — so an absent `model_tier` on a completed row
    means this run's own operator-configured floor went unconfirmed, not
    that the row predates the field. Staying silent here would make the
    floor evadable by simply omitting `--model-tier`; the note must flag it,
    distinctly from below-floor, and must still never block."""
    _entry(tmp_path)
    _configure_floor(tmp_path, "opus")
    _record(tmp_path, code_model_tier=None)

    result = check_review_record(tmp_path, RUN)

    assert result.ok is True, "an unrecorded tier must never block, only note"
    assert "no recorded tier" in result.detail


def test_at_or_above_floor_is_silent(tmp_path: Path) -> None:
    _entry(tmp_path)
    _configure_floor(tmp_path, "sonnet")
    _record(tmp_path, code_model_tier="opus")

    result = check_review_record(tmp_path, RUN)

    assert result.ok is True
    assert "floor" not in result.detail.lower()


def test_malformed_model_tier_never_raises_and_is_unflagged(tmp_path: Path) -> None:
    """`write_record` now rejects a non-string `model_tier` (schema fix), so
    this can only happen via a hand-edited or pre-fix legacy file on disk —
    `model_tier_note` must stay defensive against that directly, in memory,
    bypassing `write_record`'s validation entirely."""
    _configure_floor(tmp_path, "opus")
    record = {
        "reviews": {
            "spec": {"status": STATUS_COMPLETED, "recorded_by": "spec-reviewer",
                     "model_tier": "opus"},
            "code": {"status": STATUS_COMPLETED, "recorded_by": "code-reviewer",
                     "model_tier": {"not": "a string"}},
        },
    }

    note = model_tier_note(record, tmp_path)

    assert note == ""


def test_floor_read_from_main_repo_root_not_worktree(tmp_path: Path) -> None:
    """F11 runs from a linked worktree (every iterate does — B1a). The floor
    config lives at the MAIN repo root, resolved via the same
    `resolve_main_repo_root` the CLI resolver uses (`lib.model_tier_config`);
    this proves `model_tier_note`, reached only through `check_review_record`,
    exercises that same path — not a worktree-local (and therefore silently
    empty) config lookup."""
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "t@example.com"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=tmp_path, check=True)
    (tmp_path / "README.md").write_text("x", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=tmp_path, check=True)
    _configure_floor(tmp_path, "opus")  # written at the MAIN root only

    subprocess.run(
        ["git", "worktree", "add", "-b", "wt-branch", str(tmp_path / ".worktrees" / "wt")],
        cwd=tmp_path, check=True, capture_output=True,
    )
    worktree_root = tmp_path / ".worktrees" / "wt"
    _entry(worktree_root)
    _record(worktree_root, code_model_tier="sonnet")  # below the "opus" floor

    result = check_review_record(worktree_root, RUN)

    assert result.ok is True
    assert "sonnet" in result.detail and "opus" in result.detail, (
        "model_tier_note did not find the MAIN-root floor from a worktree "
        f"project_root — got: {result.detail!r}"
    )
