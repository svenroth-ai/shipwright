"""Drift protection for the shared requirement-elicitation module.

`shared/requirement-elicitation.md` is a cross-plugin SSoT: adopt, project, and
iterate all instruct the agent to follow it when eliciting requirements. Nothing
else enforces that the pointer resolves, so a rename or delete would silently
turn every citation into dead prose and the method would stop being applied — the
exact failure mode described in CLAUDE.md ("plugin-side fixes that silently never
took effect").

`shared/context-format.md` is its companion: the `CONTEXT.md` domain-glossary
format, deliberately kept distinct from the framework-vocabulary
`shared/glossary.md` (the naming collision the REQ-3 campaign SPEC flags).

Both directions are covered:
  forward — the module and the format doc exist, are non-empty, and still carry
            each section the campaign relies on (the grilling method, the
            universal coverage checklist plus its stop-condition, the Matt Pocock
            attribution, and the CONTEXT.md-vs-glossary.md distinction);
  reverse — every plugin that elicits requirements still cites the module.

This mirrors `test_fr_authoring_refs.py`, the sibling guard for the FR-authoring
rulebook.
"""

from __future__ import annotations

from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
MODULE = REPO_ROOT / "shared" / "requirement-elicitation.md"
CONTEXT_FORMAT = REPO_ROOT / "shared" / "context-format.md"

#: Reference docs that must cite the module — one per requirement-elicitation
#: surface (the divergent interview implementations the module unifies). Both
#: iterate surfaces that touch requirement text are pinned — FEATURE
#: (path-a-feature) and CHANGE (path-b-change) — mirroring how the sibling
#: fr-authoring guard pins both.
CITING_DOCS = (
    "plugins/shipwright-project/skills/project/references/interview-protocol.md",
    "plugins/shipwright-adopt/skills/adopt/references/step-c-interview.md",
    "plugins/shipwright-iterate/skills/iterate/references/path-a-feature.md",
    "plugins/shipwright-iterate/skills/iterate/references/path-b-change.md",
)

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
    for dimension in ("purpose", "boundaries", "failure", "glossary", "rationale", "out of scope"):
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


# --------------------------------------------------------------------------- #
# Reverse — every requirement-elicitation surface still cites the module.
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("rel", CITING_DOCS)
def test_elicitation_surface_cites_the_module(rel):
    doc = REPO_ROOT / rel
    assert doc.is_file(), f"expected requirement-elicitation reference doc at {rel}"
    assert "requirement-elicitation.md" in doc.read_text(encoding="utf-8"), (
        f"{rel} elicits requirements but no longer cites "
        f"shared/requirement-elicitation.md — the method would silently stop "
        f"being applied"
    )
