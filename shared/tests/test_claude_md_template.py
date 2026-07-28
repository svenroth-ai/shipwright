"""Pin the iterate-discoverability content in the CLAUDE.md template.

Both pipelines that produce a CLAUDE.md for a Shipwright-managed
project must surface the same iterate workflow:

- `shared/templates/claude-md-template.md` — read by /shipwright-project
  (greenfield) per `plugins/shipwright-project/skills/project/references/
  project-scaffolding.md`.
- `plugins/shipwright-adopt/scripts/lib/artifact_writer.py:_render_claude_md`
  — hardcoded f-string used by /shipwright-adopt (brownfield).

The two are split-brain by design (template-loading vs hardcoded
render), so this test asserts the content stays mirrored. Drift here
means greenfield and brownfield projects ship different onboarding
text — exactly the kind of inconsistency that lost adopted users
the CHANGELOG-fragment + ADR conventions before this iterate.
"""

from __future__ import annotations

import json
import subprocess
import sys
import pathlib
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
TEMPLATE_PATH = REPO_ROOT / "shared" / "templates" / "claude-md-template.md"
CONSTITUTION_PATH = REPO_ROOT / "shared" / "constitution.md"
OWN_CLAUDE_MD = REPO_ROOT / "CLAUDE.md"
STANDING_REQUEST_HEADING = "## Review subagents: standing request."

#: The standing-request grant. Claude Code ships two literal lines in its binary
#: ("Do not call the AgentTool / use workflows … unless the user requested it");
#: nothing local removes them, so CLAUDE.md — which the harness frames as
#: instructions that OVERRIDE default behavior — is where the request is made
#: once. The grant must cover subagents and must NOT cover workflows, whose tool
#: contract carries its own explicit per-invocation opt-in.
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


# Bullets that must appear in BOTH the template and adopt's rendered
# output. Substring matches — full prose lives in the source files.
REQUIRED_ITERATE_BULLETS = (
    "/shipwright-iterate",
    "Do NOT edit code directly",
    "ADR",
    "CHANGELOG",
    "Conventional Commits",
    "iterate/",
)


# Both CLAUDE.md producers must also carry the plain-language question-asking
# rule, so every generated project (greenfield AND brownfield) inherits it.
# Marker = the section heading; a distinctive phrase pins the substance too.
REQUIRED_PLAIN_LANGUAGE_MARKERS = (
    "Asking the user questions (plain language)",
    "non-senior developer",
)


# Both producers must carry the keep-it-lean writing rule: CLAUDE.md is
# orientation + a terse invariant index; a new invariant is ONE line + an ADR
# pointer, rationale lives in the ADR (iterate-2026-07-10-claude-md-invariant-
# index). Without this, adopted repos accrete multi-hundred-line DO-NOT blocks.
REQUIRED_LEAN_MARKERS = (
    "Editing this file (keep it lean)",
    "one line + a pointer",
    "Growth is gated",
    "SHIPWRIGHT_CLAUDE_MD_GROWTH_OK",
)


def test_template_file_lists_what_iterate_handles() -> None:
    """Greenfield path: the template file itself surfaces the bullets."""
    body = TEMPLATE_PATH.read_text(encoding="utf-8")
    for bullet in REQUIRED_ITERATE_BULLETS:
        assert bullet in body, (
            f"claude-md-template.md missing required bullet {bullet!r} — "
            f"greenfield CLAUDE.md will not surface iterate-workflow rules."
        )


def test_template_warns_against_other_skills() -> None:
    """Adopted/onboarded projects must not use the pre-onboarding skills
    (project/plan/build) directly — iterate is the single entry point."""
    body = TEMPLATE_PATH.read_text(encoding="utf-8")
    assert "shipwright-project" in body
    assert "shipwright-plan" in body
    assert "shipwright-build" in body


def test_template_carries_plain_language_question_rule() -> None:
    """Greenfield path: the template surfaces the plain-language rule so the
    generated CLAUDE.md tells the agent to phrase questions to the user in
    functional, non-jargon terms (mirrors shared/constitution.md)."""
    body = TEMPLATE_PATH.read_text(encoding="utf-8")
    for marker in REQUIRED_PLAIN_LANGUAGE_MARKERS:
        assert marker in body, (
            f"claude-md-template.md missing plain-language marker {marker!r} — "
            f"greenfield CLAUDE.md will not surface the question-phrasing rule."
        )


def test_template_carries_keep_it_lean_rule() -> None:
    """Greenfield path: the template tells future agents WHERE invariants
    belong (one line here + rationale in the ADR), so generated CLAUDE.md
    files don't accrete inline-rationale DO-NOT blocks."""
    body = TEMPLATE_PATH.read_text(encoding="utf-8")
    for marker in REQUIRED_LEAN_MARKERS:
        assert marker in body, (
            f"claude-md-template.md missing keep-it-lean marker {marker!r} — "
            f"greenfield CLAUDE.md will not surface the invariant-index rule."
        )


def test_constitution_carries_plain_language_question_rule() -> None:
    """The constitution is the canonical source of the plain-language
    question-asking rule that both CLAUDE.md producers mirror. Pin it so the
    governance rule can't be silently deleted, leaving the templates orphaned."""
    body = CONSTITUTION_PATH.read_text(encoding="utf-8")
    assert "non-senior developer" in body, (
        "shared/constitution.md missing the plain-language question rule — "
        "the CLAUDE.md templates would mirror a rule that no longer exists."
    )


def test_adopt_rendered_claude_md_mirrors_template_iterate_bullets() -> None:
    """Brownfield path: adopt's hardcoded `_render_claude_md` must
    surface the same bullets as the template. Subprocess-load of
    artifact_writer to avoid the `lib` namespace collision documented
    in shared/tests/test_verifiers_adopt.py.
    """
    adopt_scripts = REPO_ROOT / "plugins" / "shipwright-adopt" / "scripts"
    helper = (
        "import sys; sys.path.insert(0, r'"
        + str(adopt_scripts).replace("\\", "\\\\")
        + "');\n"
        "from lib.artifact_writer import _render_claude_md\n"
        "out = _render_claude_md(\n"
        "    project_name='Demo', profile='vite-hono',\n"
        "    stack={'runtime': {}, 'frontend': {}, 'backend': {},\n"
        "           'database': {}, 'auth': {}},\n"
        "    commands={'build': 'x', 'test': 'x', 'dev': 'x'},\n"
        "    product_description='demo',\n"
        ")\n"
        "import sys; sys.stdout.buffer.write(out.encode('utf-8'))\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", helper],
        capture_output=True, check=True,
    )
    body = result.stdout.decode("utf-8")
    for bullet in REQUIRED_ITERATE_BULLETS:
        assert bullet in body, (
            f"adopt's rendered CLAUDE.md missing required bullet {bullet!r} — "
            f"brownfield CLAUDE.md drifted from claude-md-template.md."
        )
    for marker in REQUIRED_PLAIN_LANGUAGE_MARKERS:
        assert marker in body, (
            f"adopt's rendered CLAUDE.md missing plain-language marker "
            f"{marker!r} — brownfield CLAUDE.md drifted from "
            f"claude-md-template.md."
        )
    for marker in REQUIRED_LEAN_MARKERS:
        assert marker in body, (
            f"adopt's rendered CLAUDE.md missing keep-it-lean marker "
            f"{marker!r} — brownfield CLAUDE.md drifted from "
            f"claude-md-template.md."
        )
    for marker in REQUIRED_SUBAGENT_GRANT_MARKERS + REQUIRED_WORKFLOW_CARVEOUT_MARKERS:
        assert marker in body, (
            f"adopt's rendered CLAUDE.md missing {marker!r} — an ADOPTED "
            "project would inherit a gated review cascade while a greenfield "
            "one would not."
        )


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
    for marker in REQUIRED_SUBAGENT_GRANT_MARKERS + REQUIRED_WORKFLOW_CARVEOUT_MARKERS:
        assert marker in body, (
            f"repo CLAUDE.md missing {marker!r} — the project ships a rule it "
            "does not follow."
        )


def _standing_request_section(body: str) -> str:
    """The grant section, normalised — heading through the next H2."""
    start = body.index("## Review subagents:")
    rest = body[start + len("## Review subagents:"):]
    end = rest.find("\n## ")
    return " ".join((rest if end < 0 else rest[:end]).split())


def _render_brownfield_claude_md() -> str:
    """Render adopt's hardcoded CLAUDE.md through the real code path."""
    adopt_scripts = REPO_ROOT / "plugins" / "shipwright-adopt" / "scripts"
    helper = (
        "import sys; sys.path.insert(0, r'"
        + str(adopt_scripts).replace(chr(92), chr(92) * 2)
        + "')\n"
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

def _run_write_claude_md(proj: pathlib.Path) -> None:
    """Invoke the REAL writer in a subprocess (lib namespace collision)."""
    adopt_scripts = REPO_ROOT / "plugins" / "shipwright-adopt" / "scripts"
    helper = (
        "import sys, pathlib\n"
        "sys.path.insert(0, r'" + str(adopt_scripts).replace(chr(92), chr(92)*2) + "')\n"
        "from lib.artifact_writer import write_claude_md\n"
        "write_claude_md(pathlib.Path(r'" + str(proj).replace(chr(92), chr(92)*2) + "'),\n"
        "    project_name='Demo', profile='vite-hono',\n"
        "    stack={'runtime': {}, 'frontend': {}, 'backend': {},\n"
        "           'database': {}, 'auth': {}},\n"
        "    commands={'build': 'x', 'test': 'x', 'dev': 'x'},\n"
        "    product_description='demo')\n"
    )
    subprocess.run([sys.executable, "-c", helper], capture_output=True, check=True)


def _loadbearing_fixture(proj: pathlib.Path) -> None:
    body = "# Real Project\n\n" + ("Load-bearing prose. " * 120) + "\n"
    assert len(body.encode("utf-8")) > 1024, "fixture must trip the 1 KB threshold"
    (proj / "CLAUDE.md").write_text(body, encoding="utf-8")


def test_a_preserved_loadbearing_claude_md_still_receives_the_grant(tmp_path) -> None:
    """The delivery leg AC3 is actually about — found by the Stage-3 doubt pass.

    `write_claude_md` refuses to overwrite an existing CLAUDE.md over ~1 KB and
    writes its render to a side-file the harness never loads. Every repo mature
    enough to be worth adopting takes that branch, so the grant reached none of
    them — while the mirror test stayed green because it calls the renderer
    directly. This one goes through the writer.
    """
    proj = tmp_path / "proj"
    proj.mkdir()
    _loadbearing_fixture(proj)
    _run_write_claude_md(proj)

    delivered = (proj / "CLAUDE.md").read_text(encoding="utf-8")
    assert "Load-bearing prose." in delivered, (
        "preserved content must survive — appending must never overwrite"
    )
    for marker in REQUIRED_SUBAGENT_GRANT_MARKERS + REQUIRED_WORKFLOW_CARVEOUT_MARKERS:
        assert marker in delivered, (
            f"a preserved load-bearing CLAUDE.md did not receive {marker!r} — "
            "the adopted project would run without the standing request while "
            "a greenfield one gets it."
        )


def test_appending_the_grant_is_idempotent(tmp_path) -> None:
    """Adopt is re-runnable; a second pass must not stack a duplicate section."""
    proj = tmp_path / "proj"
    proj.mkdir()
    _loadbearing_fixture(proj)

    _run_write_claude_md(proj)
    after_one = (proj / "CLAUDE.md").read_text(encoding="utf-8")
    _run_write_claude_md(proj)
    after_two = (proj / "CLAUDE.md").read_text(encoding="utf-8")

    assert after_one.count(STANDING_REQUEST_HEADING) == 1
    assert after_two == after_one, (
        "a second adopt run changed CLAUDE.md — the append must be idempotent "
        "by heading, or repeated onboarding stacks duplicate grants"
    )


def _preservation_notes(proj: pathlib.Path) -> list[str]:
    """Every `CLAUDE.md` note from adopt's preservation log, oldest first."""
    log = proj / ".shipwright" / "adopt" / "preservation_log.json"
    entries = json.loads(log.read_text(encoding="utf-8"))["entries"]
    return [e.get("note", "") for e in entries if e["file"] == "CLAUDE.md"]


def test_the_preservation_log_records_that_the_file_was_appended_to(tmp_path) -> None:
    """The audit trail must not still read 'skipped'.

    `preservation_log.json` is the operator's only record of what adopt did to
    a file it promised to preserve. The action stays `skipped_loadbearing` —
    the render genuinely was skipped — so the note is the sole place the append
    is disclosed. Left unchanged, the log would assert adopt touched nothing
    while the file on disk had grown a section.
    """
    proj = tmp_path / "proj"
    proj.mkdir()
    _loadbearing_fixture(proj)
    _run_write_claude_md(proj)

    notes = _preservation_notes(proj)
    assert notes, "adopt recorded no preservation entry for CLAUDE.md"
    assert "APPENDED" in notes[-1], (
        "the preservation log must disclose the append — an entry that only "
        f"says the render was skipped understates what happened: {notes[-1]!r}"
    )
    assert "nothing overwritten" in notes[-1], (
        "…and must say the append was additive, which is the property that "
        "makes writing to a preserved file defensible at all"
    )


def test_a_second_run_records_that_the_grant_was_already_present(tmp_path) -> None:
    """The two cases must be distinguishable in the log, or 'APPENDED' on every
    re-run would suggest repeated modification of a preserved file."""
    proj = tmp_path / "proj"
    proj.mkdir()
    _loadbearing_fixture(proj)

    _run_write_claude_md(proj)
    _run_write_claude_md(proj)

    notes = _preservation_notes(proj)
    assert len(notes) >= 2, "each adopt run must append its own log entry"
    assert "already present" in notes[-1], (
        f"a re-run must record a no-op, not another append: {notes[-1]!r}"
    )
    assert "APPENDED" not in notes[-1], (
        "the second run wrote nothing — claiming an append would make the log "
        "unusable as evidence of what adopt actually changed"
    )
