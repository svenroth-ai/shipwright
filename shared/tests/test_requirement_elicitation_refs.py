"""Drift protection for the shared requirement-elicitation module — forward
direction (the module and its companion doc exist and still carry what the
campaign relies on).

`shared/requirement-elicitation.md` is a cross-plugin SSoT: adopt, project, and
iterate all instruct the agent to follow it when eliciting requirements. Nothing
else enforces that the pointer resolves, so a rename or delete would silently
turn every citation into dead prose and the method would stop being applied — the
exact failure mode described in CLAUDE.md ("plugin-side fixes that silently never
took effect").

`shared/context-format.md` is its companion: the `CONTEXT.md` domain-glossary
format, deliberately kept distinct from the framework-vocabulary
`shared/glossary.md` (the naming collision the REQ-3 campaign SPEC flags).

Split from `test_requirement_elicitation_discovery.py` (the reverse direction —
every requirement-elicitation surface still cites the module) to stay under the
300-LOC bloat-baseline cap. See that file's docstring for the reverse-direction
rationale, including the FR-01.16 AC09 dynamic-discovery mechanism.
"""

from __future__ import annotations

from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
MODULE = REPO_ROOT / "shared" / "requirement-elicitation.md"
CONTEXT_FORMAT = REPO_ROOT / "shared" / "context-format.md"

#: Section anchors the campaign and citing docs rely on — renaming one without
#: updating the references would leave the method half-applied.
REQUIRED_SECTIONS = (
    "## 1. The grilling loop",
    "## 2. One question at a time, each with a recommendation",
    "## 3. Look it up — facts are found, not asked",
    "## 4. Sharpen the language against the glossary",
    "## 5. Stress-test with concrete scenarios",
    "## 6. Cross-check against the code",
    "## 7. Capture as you go — CONTEXT.md and ADRs",
    "## 8. The coverage checklist — the completeness contract",
    "## 9. Confirm before acting",
    "## 10. Where the output lands",
    "## 11. The shared question bank",
    "## 12. How each plugin applies it",
    # Sec.0 precedes Sec.1 in the document and is load-bearing by the module's
    # own text (see `test_module_pins_the_execution_order_rule_by_sentence`
    # below) — appended at the END per the P4.4 card's own instruction, not
    # inserted at position 0, so the existing 12 entries keep their order.
    "## 0. The order — do it in this sequence",
)

#: Sections the CONTEXT.md format doc must keep.
CONTEXT_SECTIONS = (
    "## 1. What CONTEXT.md is — and what it is not",
    "## 2. The format",
    "## 3. Rules",
    "## 4. Where it lives",
)


# --------------------------------------------------------------------------- #
# Forward — the shared docs exist and still carry what the campaign relies on.
# --------------------------------------------------------------------------- #

def test_module_exists_and_is_non_empty():
    assert MODULE.is_file(), f"missing shared elicitation module: {MODULE}"
    assert MODULE.read_text(encoding="utf-8").strip(), "module is empty"


def test_context_format_exists_and_is_non_empty():
    assert CONTEXT_FORMAT.is_file(), f"missing CONTEXT.md format doc: {CONTEXT_FORMAT}"
    assert CONTEXT_FORMAT.read_text(encoding="utf-8").strip(), "format doc is empty"


@pytest.mark.parametrize("section", REQUIRED_SECTIONS)
def test_module_retains_cited_sections(section):
    body = MODULE.read_text(encoding="utf-8")
    assert section in body, (
        f"elicitation module section {section!r} is gone — the campaign and the "
        f"citing skill docs reference the method by these sections; update them "
        f"in the same change"
    )


@pytest.mark.parametrize("section", CONTEXT_SECTIONS)
def test_context_format_retains_cited_sections(section):
    body = CONTEXT_FORMAT.read_text(encoding="utf-8")
    assert section in body, f"context-format section {section!r} is gone"


def test_module_attributes_matt_pocock():
    """The method is adopted from Matt Pocock's skills; attribution is binding."""
    body = MODULE.read_text(encoding="utf-8")
    assert "Matt Pocock" in body, (
        "the module adopts Matt Pocock's grilling / domain-modeling method — "
        "attribution must stay in the doc"
    )
    assert "mattpocock/skills" in body, "keep the source repo link for provenance"


def test_module_carries_the_completeness_stop_condition():
    """The centralized guarantee: elicitation is not done until every dimension
    is answered or explicitly recorded as an unconfirmed assumption.

    Pinned positively (not just the section heading) so a reword cannot gut the
    load-bearing rule — the same reason `test_fr_authoring_refs` pins its rule
    text, not only the section title.
    """
    body = MODULE.read_text(encoding="utf-8")
    # The stop-condition ties into the vocabulary fr-authoring already defines.
    assert "Basis: assumed" in body, (
        "the coverage stop-condition must route an unconfirmed dimension to "
        "`Basis: assumed` — the honest cell fr-authoring §4a already defines"
    )
    # The recommended-answer rule (Pocock) — the anti-100-questions discipline.
    assert "recommend" in body.lower(), "keep the 'each question carries a recommendation' rule"


def test_module_lists_the_coverage_dimensions():
    """The universal checklist names the dimensions that must be covered — the
    thing the operator asked to centralize so grilling is deep enough everywhere.

    Scoped to §8, not the whole document: the dimension words also occur in the
    intro and the §11 question bank, so a document-wide search would still pass
    if the §8 checklist itself dropped a dimension (external-review finding).
    """
    body = MODULE.read_text(encoding="utf-8")
    start = body.index("## 8. The coverage checklist")
    end = body.index("## 9.", start)
    section = body[start:end].lower()
    for dimension in ("outcome", "purpose", "boundaries", "failure", "glossary",
                      "rationale", "out of scope"):
        assert dimension in section, f"§8 coverage checklist is missing the {dimension!r} dimension"
    assert "basis: assumed" in section, (
        "the §8 stop-condition must route an unanswered dimension to `Basis: assumed`"
    )


def test_module_pins_the_load_bearing_rules_by_sentence():
    """Pin the RULES, not only the section headings.

    A structural check on headings alone can be satisfied by keeping a heading
    while gutting the rule under it. These two are the operator's centralization
    guarantee: the shared checklist may be extended but never bypassed, and a
    requirement is not finished until its coverage is complete.
    """
    body = MODULE.read_text(encoding="utf-8")
    assert "never skipped" in body, (
        "the 'plugins may add to but never skip the shared checklist' rule must "
        "survive verbatim — it is what stops a surface from under-grilling"
    )
    assert "not finished" in body, (
        "the coverage stop-condition ('a requirement is not finished until …') "
        "must survive verbatim, not just its section heading"
    )


def test_module_pins_the_execution_order_rule_by_sentence():
    """Sec.0 precedes Sec.1 and is the module's own load-bearing claim about
    itself ("the order is load-bearing") — yet `REQUIRED_SECTIONS` had no
    entry for it until P4.4, so Sec.0 could be deleted whole without any test
    turning red. Pin the RULE sentence, not just the heading (mirrors
    `test_module_pins_the_load_bearing_rules_by_sentence` above), so a reword
    that quietly dropped the claim would still be caught.
    """
    body = MODULE.read_text(encoding="utf-8")
    assert "the order is load-bearing" in body, (
        "Sec.0's own claim that the execution order is load-bearing must "
        "survive verbatim — it is why Sec.0 exists as a separate, numbered "
        "step before Sec.1 rather than as informal framing prose"
    )


def test_module_pins_the_minimum_two_scenarios_rule_by_sentence():
    """FR-01.16 AC05: Sec.5's stress-test minimum ("two per requirement, put
    to the person") is a concrete, falsifiable number the module derived from
    its own acceptance round (zero scenarios volunteered vs. three found more
    than code-reading had) — a rewrite that softened it back to "as many as
    feels useful" would reintroduce the exact failure it fixes.
    """
    body = MODULE.read_text(encoding="utf-8")
    assert "The minimum is two per requirement, put to the person" in body, (
        "Sec.5's minimum-two-scenarios rule must survive verbatim, not just "
        "the section heading — it is the number that stopped scenario count "
        "from silently collapsing to zero"
    )


def test_module_pins_the_glossary_cross_check_trigger_by_sentence():
    """FR-01.16 AC04: Sec.4's glossary cross-check has a concrete TRIGGER
    ("every time a term is captured, check it against the terms already
    there"), added specifically because "the moment fuzzy language appears"
    is not something anyone notices about their own writing. The sentence
    soft-wraps across a markdown source line in the raw file, so whitespace
    is normalized (collapsed to single spaces) before the substring check —
    the same substance-over-layout concern as the other pinning assertions
    in this file, just made explicit here because this is the one sentence
    that actually wraps.
    """
    body = MODULE.read_text(encoding="utf-8")
    normalized = " ".join(body.split())
    assert (
        "Trigger: every time a term is captured, check it against the terms "
        "already there" in normalized
    ), (
        "Sec.4's glossary cross-check trigger must survive verbatim — "
        "without a concrete trigger, sharpening a term against CONTEXT.md "
        "stops happening because nobody notices the moment to do it"
    )


def test_module_pins_its_internal_cross_references():
    """A rename of a doc the module points OUT to would leave a dangling in-prose
    reference. The file-existence checks catch a delete of the module itself, but
    not a broken reference from it — so pin the two docs it depends on.
    """
    body = MODULE.read_text(encoding="utf-8")
    assert "context-format.md" in body, (
        "the module must keep pointing to the CONTEXT.md format doc (§4/§7)"
    )
    assert "fr-authoring.md" in body, (
        "the module must keep pointing to fr-authoring.md — where its output lands (§10)"
    )


def test_context_format_states_the_glossary_distinction():
    """CONTEXT.md (target-project DOMAIN glossary) must not be confused with
    shared/glossary.md (the FRAMEWORK vocabulary) — the SPEC's named landmine.

    Assert the DISTINCTION, not merely that both names appear: both strings
    could survive in unrelated prose while the contrast itself was deleted
    (external-review finding).
    """
    body = CONTEXT_FORMAT.read_text(encoding="utf-8")
    lower = body.lower()
    assert "glossary.md" in body, "the doc must name shared/glossary.md to draw the distinction"
    # The contrast itself — target-project DOMAIN vs the FRAMEWORK vocabulary.
    assert "domain" in lower and "framework" in lower, (
        "the distinction must contrast the target-project DOMAIN glossary with "
        "the framework vocabulary, not merely name both files"
    )
    assert "never merge" in lower, (
        "keep the explicit 'they never merge' rule stating the two are separate artifacts"
    )
    assert "Matt Pocock" in body, "attribute the CONTEXT.md format to its source"
