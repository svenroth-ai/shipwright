"""Drift-protection: the AC1 dispatch rule ("can this driving harness spawn
an independent Agent-tool subagent — if not, run `review_via_codex.py`") is
pointed to from each of its four real spawn sites; the full procedure lives
in exactly one place, `shared/prompts/codex_review_dispatch.md`.

Cross-plugin by nature (`shipwright-build`, `shipwright-plan`,
`shipwright-iterate` x2), so it lives in `integration-tests/`, mirroring
`test_model_tier_spawn_instructions_present.py`'s anchor-based approach:
search for a stable, normalized marker rather than whole prose, so the test
survives benign rewording but fails when a site's pointer disappears entirely
— the exact "prose branching rots silently" risk the Architecture Review
named (Internal Plan Review finding #3,
iterate-2026-09-13-codex-internal-review-transport). The doc itself, not each
site, is what a spec-reviewer REJECT (2026-09-17) asked to be made concrete
and runnable — that content is guarded separately, below.

The four sites are enumerated here, not assumed: grepped for `Task(` /
`Agent(`-style review-role spawns across the repo when this test was written.
A fifth site appearing later without a matching entry here is exactly the
regression this test exists to catch — add it to `DISPATCH_SITES` in the same
diff that adds the spawn.
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

_ANCHOR = "codex_review_dispatch.md"
CANONICAL_DOC = REPO_ROOT / "shared" / "prompts" / "codex_review_dispatch.md"

DISPATCH_SITES = (
    # build's own Kern SKILL.md is capped at 300 LOC (test_reviewer_orchestration
    # .test_build_kern_still_under_300_loc) and carries only a pointer — the
    # real anchor lives one level down, same split as the model-tier note.
    REPO_ROOT / "plugins" / "shipwright-build" / "skills" / "build" / "references"
    / "code-review.md",
    REPO_ROOT / "plugins" / "shipwright-plan" / "skills" / "plan" / "references"
    / "step-5-external-review.md",
    REPO_ROOT / "plugins" / "shipwright-iterate" / "skills" / "iterate" / "SKILL.md",
    REPO_ROOT / "plugins" / "shipwright-iterate" / "skills" / "iterate" / "references"
    / "campaign-mode.md",
)


@pytest.mark.parametrize("site", DISPATCH_SITES)
def test_dispatch_site_exists(site: Path) -> None:
    assert site.is_file(), f"expected dispatch site not found: {site}"


#: How close "Dispatch rule" must sit before the anchor for the anchor to
#: count as a real dispatch pointer rather than an unrelated mention
#: elsewhere in the file (e.g. a changelog note) — the four real sites' gaps
#: measure well under 100 chars; 150 leaves headroom for benign rewording
#: without accepting a stray, disconnected reference (external code review,
#: LOW, 2026-09-17: "would still pass if the anchor were unrelated to the
#: review spawn").
_DISPATCH_RULE_WINDOW_CHARS = 150


@pytest.mark.parametrize("site", DISPATCH_SITES)
def test_dispatch_rule_present_at_site(site: Path) -> None:
    text = site.read_text(encoding="utf-8")
    anchor_at = text.find(_ANCHOR)
    assert anchor_at != -1, (
        f"{site} lost its Codex-driver dispatch rule (expected {_ANCHOR!r} "
        "somewhere in the file). A Codex-driven session hitting this spawn "
        "site with no dispatch rule would silently have no way to run this "
        "review role at all."
    )
    window_start = max(0, anchor_at - _DISPATCH_RULE_WINDOW_CHARS)
    preceding = text[window_start:anchor_at]
    assert "dispatch rule" in preceding.lower(), (
        f"{site} names {_ANCHOR!r} but not next to a 'Dispatch rule' marker "
        f"within {_DISPATCH_RULE_WINDOW_CHARS} chars before it — the anchor "
        "may be an unrelated mention (e.g. a changelog note) rather than the "
        "actual dispatch pointer at this spawn site."
    )


def test_canonical_dispatch_doc_exists() -> None:
    assert CANONICAL_DOC.is_file(), f"canonical dispatch doc not found: {CANONICAL_DOC}"


def test_canonical_dispatch_doc_names_a_real_runnable_cli() -> None:
    """A spec-reviewer REJECT (2026-09-17) found the original prose pointed at
    a review_via_codex.py that did not exist (only an import-only library
    module did) — the doc must name the actual CLI entry point, not an
    aspirational one."""
    text = CANONICAL_DOC.read_text(encoding="utf-8")
    assert "review_via_codex.py" in text
    cli = REPO_ROOT / "shared" / "scripts" / "tools" / "review_via_codex.py"
    assert cli.is_file(), f"{CANONICAL_DOC} names review_via_codex.py but it does not exist at {cli}"


def test_canonical_dispatch_doc_distinguishes_fallback_from_codex_success() -> None:
    """External Review finding openai #8: a failed-then-agent-fallback pass
    must be distinguishable in reviews.json from a clean codex-answered
    pass — the doc must instruct recording `--transport agent
    --transport-note` on the fallback branch, not just `--transport codex`."""
    text = CANONICAL_DOC.read_text(encoding="utf-8")
    assert "--transport agent" in text
    assert "--transport-note" in text


def test_sub_iterate_runner_agent_carries_no_dispatch_rule() -> None:
    """The ADR-029 carve-out (Internal Plan Review finding #1): the dispatch
    rule belongs at the ORCHESTRATOR's own spawn site (campaign-mode.md
    3f-bis), never inside the Agent-tool-less delegate's own instructions —
    the runner always defers regardless of which harness drives it."""
    runner_agent = (
        REPO_ROOT / "plugins" / "shipwright-iterate" / "agents" / "sub-iterate-runner.md"
    )
    assert runner_agent.is_file()
    text = runner_agent.read_text(encoding="utf-8")
    assert _ANCHOR not in text, (
        "sub-iterate-runner.md should not carry the Codex-driver dispatch "
        "rule — it has no Agent tool either way and always defers to the "
        "orchestrator's campaign-mode.md 3f-bis step"
    )
