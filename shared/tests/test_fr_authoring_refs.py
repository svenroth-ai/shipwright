"""Drift protection for the shared FR-authoring rulebook.

`shared/fr-authoring.md` is a cross-plugin SSoT: adopt, project, and iterate all
instruct the agent to read it before authoring an FR. Nothing else enforces that
the pointer resolves, so a rename or delete would silently turn every citation
into dead prose and the rules would stop being applied — the exact failure mode
described in CLAUDE.md ("plugin-side fixes that silently never took effect").

Both directions are covered:
  forward — the rulebook exists, is non-empty, and still carries each numbered
            rule the citing docs rely on;
  reverse — every plugin that authors FR text still cites it.
"""

from __future__ import annotations

from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
RULEBOOK = REPO_ROOT / "shared" / "fr-authoring.md"

#: Reference docs that must cite the rulebook — one per FR-authoring surface.
CITING_DOCS = (
    "plugins/shipwright-adopt/skills/adopt/references/step-b8-semantic-enrichment.md",
    "plugins/shipwright-project/skills/project/references/spec-generation.md",
    "plugins/shipwright-iterate/skills/iterate/references/path-a-feature.md",
    "plugins/shipwright-iterate/skills/iterate/references/path-b-change.md",
)

#: Section anchors the citing docs reference by number — renaming a section
#: without updating the citations would leave dangling cross-references.
REQUIRED_SECTIONS = (
    "## 1. Plain language",
    "## 2. Altitude",
    "## 3. Mint or fold",
    "## 4. Numbering and grouping",
    # Cited by number from `path-b-change.md` and `spec-generation.md` (campaign
    # S5) — the row shape plus the Basis/Layers cell rules.
    "## 4a. The row",
    "## 5. The name",
    "## 7. Enforcement",
)


def test_rulebook_exists_and_is_non_empty():
    assert RULEBOOK.is_file(), f"missing shared FR-authoring rulebook: {RULEBOOK}"
    assert RULEBOOK.read_text(encoding="utf-8").strip(), "rulebook is empty"


@pytest.mark.parametrize("section", REQUIRED_SECTIONS)
def test_rulebook_retains_cited_sections(section):
    body = RULEBOOK.read_text(encoding="utf-8")
    assert section in body, (
        f"rulebook section {section!r} is gone — the citing skill docs "
        f"reference it by number; update them in the same change"
    )


@pytest.mark.parametrize("rel", CITING_DOCS)
def test_fr_authoring_surface_cites_the_rulebook(rel):
    doc = REPO_ROOT / rel
    assert doc.is_file(), f"expected FR-authoring reference doc at {rel}"
    assert "fr-authoring.md" in doc.read_text(encoding="utf-8"), (
        f"{rel} authors or edits FR text but no longer cites "
        f"shared/fr-authoring.md — the rule would silently stop being applied"
    )


def test_adopt_no_longer_carries_the_contradicting_guidance():
    """The old enrichment leitplanke pulled the opposite way and must stay gone.

    It told the agent to keep descriptions "nuechtern, technical" and to
    "describe what the code does" — directly at odds with plain business
    language. Appending the new rule without removing this one would leave two
    contradictory instructions in the same prompt.
    """
    doc = REPO_ROOT / CITING_DOCS[0]
    body = doc.read_text(encoding="utf-8")
    assert "Describe what the code *does*" not in body
    assert "nüchtern, technical" not in body


def test_adopt_positively_states_the_plain_language_rule():
    """Pin the rule POSITIVELY, not just the absence of the old wording.

    The negative assertions above only catch the two exact strings that were
    removed; a reword ("keep it technical") would sail past them while dropping
    the rule entirely. This asserts the replacement guidance is actually there.
    """
    body = (REPO_ROOT / CITING_DOCS[0]).read_text(encoding="utf-8")
    assert "plain business language" in body
    # The worked ❌/✅ pair is what makes the rule concrete for the agent.
    assert "❌" in body and "✅" in body


@pytest.mark.parametrize("rel", CITING_DOCS[2:])  # the two iterate paths
def test_iterate_paths_carry_the_mint_vs_fold_gate(rel):
    """The gate is the load-bearing half of the iterate change — pin it.

    Without it, `path-a`'s ADD branch reverts to minting one FR per unit of
    work, which is the root cause both triage items were filed against.
    """
    body = (REPO_ROOT / rel).read_text(encoding="utf-8")
    assert "MINT" in body and "FOLD" in body
