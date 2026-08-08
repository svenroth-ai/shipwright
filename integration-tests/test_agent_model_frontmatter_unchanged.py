"""Structural guard: no agent's `model:` frontmatter is pinned by this feature.

The BRIEF this feature implements is explicit that a prior attempt hardcoded
`model: opus`/`model: sonnet` into agent files and was abandoned before
delivery — hardcoding removes a plugin consumer's choice in either direction.
This diff's whole design is additive-only: a resolved tier is passed as an
Agent-tool call PARAMETER, never written into an agent's frontmatter.

This test does NOT hash whole files (a golden-hash would false-fail on any
unrelated future edit — a description tweak — and block someone else's
iterate for a reason unrelated to model tiers). It asserts only the `model:`
value, from an explicit expected map. Update EXPECTED_MODEL deliberately, with
a recorded decision, if a `model:` value is ever meant to change — see the
consumer-freedom rejection in
`.shipwright/planning/iterate/iterate-agent-model-tiers-BRIEF.md`.

Line-anchored frontmatter parsing (not YAML-library dependent, matching this
repo's own `shared/scripts/lib/canon_frontmatter.py` approach) so a value
inside the agent's PROMPT body (e.g. an example mentioning "model: gpt-4")
can never be mistaken for the frontmatter key.
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
PLUGINS_DIR = REPO_ROOT / "plugins"

#: Agents whose `model:` is pinned by a separately recorded decision that
#: PREDATES and is independent of this feature — not something this diff (or
#: a future one following its pattern) may add to silently. A THIRD pin
#: therefore cannot be added by just registering it in EXPECTED_MODEL below;
#: it requires deliberately editing this differently-named constant too,
#: which is the point: adding an entry here IS the decision this feature's
#: "no frontmatter pins" constraint says must be recorded, not incidental.
_PINNED_BY_DECISION: dict[str, str] = {
    "plugins/shipwright-plan/agents/opus-plan-reviewer.md": "opus",
    "plugins/shipwright-test/agents/browser-fixer.md": "sonnet",
}

#: Every agent this repo ships, and the `model:` value it must carry. This is
#: the reverse-drift target: every file matched by the glob below must have
#: an entry here, and every entry here must resolve to a real file. Every
#: entry NOT in `_PINNED_BY_DECISION` must be `"inherit"` — enforced below.
EXPECTED_MODEL: dict[str, str] = {
    "plugins/shipwright-build/agents/spec-reviewer.md": "inherit",
    "plugins/shipwright-build/agents/code-reviewer.md": "inherit",
    "plugins/shipwright-build/agents/doubt-reviewer.md": "inherit",
    "plugins/shipwright-build/agents/section-builder.md": "inherit",
    "plugins/shipwright-iterate/agents/sub-iterate-runner.md": "inherit",
    "plugins/shipwright-test/agents/test-runner.md": "inherit",
    "plugins/shipwright-security/agents/security-fixer.md": "inherit",
    "plugins/shipwright-plan/agents/section-writer.md": "inherit",
    "plugins/shipwright-run/agents/phase-runner.md": "inherit",
    **_PINNED_BY_DECISION,
}


def _frontmatter_model(path: Path) -> str | None:
    """Line-anchored: only a `model:` line strictly between the two `---`
    frontmatter fences counts — never a mention inside the prompt body."""
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0].strip() != "---":
        return None
    for line in lines[1:]:
        if line.strip() == "---":
            return None  # closed the fence without finding `model:`
        if line.startswith("model:"):
            return line.split(":", 1)[1].strip()
    return None


def _all_agent_files() -> list[Path]:
    return sorted(PLUGINS_DIR.glob("*/agents/**/*.md"))


def test_glob_finds_at_least_the_known_agents() -> None:
    """Non-vacuity guard: if the glob pattern ever stops matching anything
    (e.g. a directory layout change), every other test in this file would
    trivially pass on zero files — assert real matches first."""
    found = _all_agent_files()
    assert len(found) >= len(EXPECTED_MODEL), (
        f"expected at least {len(EXPECTED_MODEL)} agent files, found {len(found)}: "
        f"{[str(p.relative_to(REPO_ROOT)) for p in found]}"
    )


@pytest.mark.parametrize("rel_path", sorted(EXPECTED_MODEL))
def test_forward_drift_every_registry_entry_resolves_to_a_file(rel_path: str) -> None:
    assert (REPO_ROOT / rel_path).is_file(), (
        f"EXPECTED_MODEL names {rel_path!r} but no such file exists — "
        "the agent was moved/renamed/deleted; update this test's registry."
    )


def test_unpinned_agents_are_registered_as_inherit() -> None:
    """The reverse-drift test only proves 'registered', not 'not pinned' — a
    new agent shipped with `model: opus` would satisfy it by simply being
    added to EXPECTED_MODEL, exactly the way this file's own remediation
    text tells a maintainer to fix a failure. This is the test that actually
    catches that: any registered agent outside `_PINNED_BY_DECISION` must be
    `"inherit"`, so a silent third pin fails here even when everything else
    is green."""
    unaccounted_pins = {
        rel_path: value
        for rel_path, value in EXPECTED_MODEL.items()
        if rel_path not in _PINNED_BY_DECISION and value != "inherit"
    }
    assert not unaccounted_pins, (
        f"agent(s) registered with a non-inherit model: outside "
        f"_PINNED_BY_DECISION: {unaccounted_pins} — a frontmatter pin must be "
        "added to _PINNED_BY_DECISION, with a recorded reason, not just to "
        "EXPECTED_MODEL."
    )


def test_reverse_drift_every_matched_agent_file_is_in_the_registry() -> None:
    matched = {str(p.relative_to(REPO_ROOT)).replace("\\", "/") for p in _all_agent_files()}
    unregistered = matched - set(EXPECTED_MODEL)
    assert not unregistered, (
        f"agent file(s) not covered by EXPECTED_MODEL: {sorted(unregistered)} — "
        "a new agent was added without recording its expected model: value here."
    )


@pytest.mark.parametrize("rel_path,expected", sorted(EXPECTED_MODEL.items()))
def test_model_frontmatter_unchanged(rel_path: str, expected: str) -> None:
    path = REPO_ROOT / rel_path
    actual = _frontmatter_model(path)
    assert actual == expected, (
        f"{rel_path} has model: {actual!r}, expected {expected!r}. This feature "
        "is additive-only (Agent-tool call parameter, never frontmatter) — if "
        "this is a deliberate, separately-decided pin, update EXPECTED_MODEL "
        "with a recorded decision; it must not be a side effect of this diff."
    )
