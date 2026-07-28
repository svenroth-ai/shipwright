"""Pin the review-subagent standing request across all three CLAUDE.md carriers.

Split out of `test_claude_md_template.py`, which owns a different question —
that the greenfield template and adopt's brownfield render stay *mirrored* on
the onboarding bullets. This file owns one rule's CONTENT; whether an adopted
project actually receives it is the writer's question, pinned separately in
`plugins/shipwright-adopt/tests/test_claude_md_standing_request_append.py`.

Claude Code ships two lines as literal constants in its binary ("Do not call
the AgentTool / use workflows or deep-research **unless the user requested
it**"). Nothing local removes them, so `CLAUDE.md` — which the harness frames as
instructions that OVERRIDE default behavior — is where the request gets made
once. The grant must cover **reviewers** and must NOT cover **fan-out**, whose
tool contract carries its own explicit per-invocation opt-in.

Two failure modes are guarded separately, because neither check sees the other's:

- **Divergence** — carrier equality. Substring markers alone let a carrier drift
  semantically while every marker is still found somewhere in the body.
- **Identical regression** — the negative assertion. Append "and dynamic
  workflows are covered too" to all three carriers and equality still holds and
  every marker still matches.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
TEMPLATE_PATH = REPO_ROOT / "shared" / "templates" / "claude-md-template.md"
OWN_CLAUDE_MD = REPO_ROOT / "CLAUDE.md"

#: Each marker pins an OPERATIVE instruction, not the grant's self-description.
#: Stage 2 showed the first version could lose "do not pause to ask" and stay
#: green — leaving a section that describes a grant but no longer tells the
#: session to act on it, i.e. the pre-change behaviour.
REQUIRED_SUBAGENT_GRANT_MARKERS = (
    "The review cascade is requested by default",
    "never pause to ask",
    "never record a review `not_run` citing a session policy",
    "this file is that request",
)
#: The carve-out is the point: the Workflow tool's own contract demands a
#: per-invocation opt-in. Granting reviewers must never read as granting
#: fan-out — including the parallel implementation subagents a phase skill
#: prescribes, which Stage 2 caught the first wording silently authorising.
REQUIRED_WORKFLOW_CARVEOUT_MARKERS = (
    "The grant covers reviewers, not fan-out",
    "ask explicitly, every time",
    "never infer them from the grant above",
    "section-builder",
)

ALL_MARKERS = REQUIRED_SUBAGENT_GRANT_MARKERS + REQUIRED_WORKFLOW_CARVEOUT_MARKERS


def _render_brownfield_claude_md() -> str:
    """Render adopt's hardcoded CLAUDE.md through the real code path.

    Subprocess-loaded to avoid the `lib` namespace collision documented in
    `shared/tests/test_verifiers_adopt.py` (ADR-044).
    """
    adopt_scripts = REPO_ROOT / "plugins" / "shipwright-adopt" / "scripts"
    helper = (
        "import sys; sys.path.insert(0, r'"
        + str(adopt_scripts).replace(chr(92), chr(92) * 2) + "')\n"
        "from lib.artifact_writer import _render_claude_md\n"
        "out = _render_claude_md(\n"
        "    project_name='Demo', profile='vite-hono',\n"
        "    stack={'runtime': {}, 'frontend': {}, 'backend': {},\n"
        "           'database': {}, 'auth': {}},\n"
        "    commands={'build': 'x', 'test': 'x', 'dev': 'x'},\n"
        "    product_description='demo',\n"
        ")\n"
        "sys.stdout.buffer.write(out.encode('utf-8'))\n"
    )
    return subprocess.run(
        [sys.executable, "-c", helper], capture_output=True, check=True,
    ).stdout.decode("utf-8")


def _standing_request_section(body: str) -> str:
    """The grant section, normalised — heading through the next H2."""
    start = body.index("## Review subagents:")
    rest = body[start + len("## Review subagents:"):]
    end = rest.find("\n## ")
    return " ".join((rest if end < 0 else rest[:end]).split())


# --- the grant is present in each carrier ----------------------------------


def test_template_carries_the_subagent_standing_request() -> None:
    """Greenfield path: the shipped CLAUDE.md must make the review cascade a
    standing request, or every onboarded project inherits the lapse this rule
    exists to stop — five recorded runs closed `code = not_run` citing the
    session policy."""
    body = TEMPLATE_PATH.read_text(encoding="utf-8")
    for marker in REQUIRED_SUBAGENT_GRANT_MARKERS:
        assert marker in body, (
            f"claude-md-template.md missing subagent-grant marker {marker!r} — "
            "a generated CLAUDE.md would leave the cascade gated."
        )


def test_template_does_not_grant_workflows() -> None:
    """The carve-out is the point: the Workflow tool's own contract requires an
    explicit per-invocation opt-in ('the user must request that scale, not have
    it inferred'). Granting subagents must never be read as granting fan-out."""
    body = TEMPLATE_PATH.read_text(encoding="utf-8")
    for marker in REQUIRED_WORKFLOW_CARVEOUT_MARKERS:
        assert marker in body, (
            f"claude-md-template.md missing workflow carve-out {marker!r} — "
            "the grant would read as covering dynamic workflows too."
        )


def test_own_claude_md_carries_the_same_grant_and_carveout() -> None:
    """This repo eats its own cooking: the rule it ships must govern it too."""
    body = OWN_CLAUDE_MD.read_text(encoding="utf-8")
    for marker in ALL_MARKERS:
        assert marker in body, (
            f"repo CLAUDE.md missing {marker!r} — the project ships a rule it "
            "does not follow."
        )


def test_brownfield_render_carries_the_grant_and_carveout() -> None:
    """An ADOPTED project must not inherit a gated cascade while a greenfield
    one gets the grant."""
    body = _render_brownfield_claude_md()
    for marker in ALL_MARKERS:
        assert marker in body, (
            f"adopt's rendered CLAUDE.md missing {marker!r} — an ADOPTED "
            "project would inherit a gated review cascade while a greenfield "
            "one would not."
        )


# --- the two blind spots: divergence, and identical regression -------------


def test_the_three_carriers_hold_the_same_section_not_just_the_markers() -> None:
    """A real mirror, not a presence check.

    Stage 2 and the external code review landed on this independently: marker
    substrings let a carrier drift semantically — the renderer could authorise
    workflows, drop the opt-out, or broaden the grant, and every marker would
    still be found somewhere in the body. The three carriers must be equivalent
    after whitespace normalisation, so a change to one is a change to all three
    or a red test.
    """
    template = _standing_request_section(TEMPLATE_PATH.read_text(encoding="utf-8"))
    brownfield = _standing_request_section(_render_brownfield_claude_md())
    own = _standing_request_section(OWN_CLAUDE_MD.read_text(encoding="utf-8"))

    assert template == brownfield, (
        "greenfield template and brownfield renderer carry DIFFERENT "
        "standing-request sections — an adopted project would get a different "
        "grant from a generated one.\n"
        f"template  : {template[:200]}\n"
        f"brownfield: {brownfield[:200]}"
    )
    assert template == own, (
        "this repo's CLAUDE.md carries a different standing-request section "
        "than the one it ships — the project would not be governed by the rule "
        "it hands to everyone else.\n"
        f"template: {template[:200]}\n"
        f"own     : {own[:200]}"
    )


#: Words that would AFFIRMATIVELY authorise fan-out. The equality test is blind
#: to a regression applied identically to all three carriers, and the marker
#: tuples are substring checks that can only prove text was ADDED. This is the
#: negative half: the section must not grant what it exists to withhold.
_FORBIDDEN_GRANTS = (
    "dynamic workflows are covered",
    "workflows are covered too",
    "deep-research is covered",
    "section-builder is covered",
    "including dynamic workflows",
)


def test_the_section_never_affirmatively_grants_fan_out() -> None:
    """Drift tests catch divergence; this catches identical regression.

    Append ", and dynamic workflows are covered too" to all three carriers and
    every marker still matches and all three stay equal — the carve-out the
    change exists for would be gone with a green suite (Stage-3 doubt).
    """
    for label, body in (
        ("template", TEMPLATE_PATH.read_text(encoding="utf-8")),
        ("repo CLAUDE.md", OWN_CLAUDE_MD.read_text(encoding="utf-8")),
        ("brownfield render", _render_brownfield_claude_md()),
    ):
        section = _standing_request_section(body).lower()
        for phrase in _FORBIDDEN_GRANTS:
            assert phrase not in section, (
                f"{label}: the standing-request section affirmatively grants "
                f"fan-out ({phrase!r}) — the carve-out is the point of the "
                "section, and equality plus substring markers cannot see this."
            )
