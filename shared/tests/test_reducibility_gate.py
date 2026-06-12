"""Drift-protection for the Reducibility Reviewer gate (trg-af476d87).

The "intelligent bloat gate" replaces the raw >LOC verdict with an LLM
reducibility reviewer: cheap LOC routes, the reviewer blocks only on a
concrete, falsifiable reduction from a CLOSED catalog (D/A/X/C/S/M/P/T),
each citing what-to-remove + est-LOC-saved + keeps-tests-green. No concrete
finding → PASS.

These tests pin the SHAPE of the gate across all four surfaces so the
catalog, the idiom-map, and the three reviewer prompts cannot silently
drift apart:

- ``shared/reducibility-catalog.md``                — the SSoT reference
- ``shared/profiles/reducibility-idioms.json``      — per-language idiom-map
- ``plugins/shipwright-build/agents/code-reviewer.md`` — local diff reviewer
- ``shared/prompts/pr_reviewer/system``             — B4.5 CI Tier-3 reviewer
- ``shared/prompts/iterate_reviewer/system``        — external plan reviewer

This file lives in ``shared/tests/`` because it reaches across ``shared/``
and two plugins — the natural home for the cross-surface invariant.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

CATALOG = REPO_ROOT / "shared" / "reducibility-catalog.md"
IDIOM_MAP = REPO_ROOT / "shared" / "profiles" / "reducibility-idioms.json"
CODE_REVIEWER = (
    REPO_ROOT / "plugins" / "shipwright-build" / "agents" / "code-reviewer.md"
)
PR_REVIEWER = REPO_ROOT / "shared" / "prompts" / "pr_reviewer" / "system"
ITERATE_REVIEWER = (
    REPO_ROOT / "shared" / "prompts" / "iterate_reviewer" / "system"
)

# The closed catalog: code -> smell keyword that MUST appear next to it.
CATALOG_CODES = {
    "D": "duplication",
    "A": "abstraction",
    "X": "dead",
    "C": "control-flow",
    "S": "data-shape",
    "M": "comment",
    "P": "dependency",
    "T": "test",
}

IDIOM_LANGUAGES = ("stack_agnostic", "python", "typescript")


# ---------------------------------------------------------------------------
# AC1 — the SSoT catalog
# ---------------------------------------------------------------------------


def test_catalog_exists():
    assert CATALOG.is_file(), f"missing SSoT catalog: {CATALOG}"


def test_catalog_states_loc_is_a_router():
    body = CATALOG.read_text(encoding="utf-8").lower()
    # The central thesis: LOC routes, it does not rule.
    assert "router" in body, "catalog must state LOC is a ROUTER"
    assert "no concrete finding" in body or "no finding" in body, (
        "catalog must state: no concrete finding → PASS"
    )


@pytest.mark.parametrize("code,keyword", list(CATALOG_CODES.items()))
def test_catalog_lists_every_code(code: str, keyword: str):
    """Each catalog code appears as a heading with its smell keyword."""
    body = CATALOG.read_text(encoding="utf-8")
    # Heading form: ``### D — Duplication`` (em-dash or hyphen tolerated).
    heading = re.search(
        rf"^#{{2,4}}\s*{re.escape(code)}\s*[—\-–]\s*(.+)$",
        body,
        re.MULTILINE,
    )
    assert heading is not None, f"catalog missing heading for code {code!r}"
    assert keyword.lower() in heading.group(1).lower(), (
        f"code {code!r} heading must name its smell ({keyword!r}): "
        f"{heading.group(0)!r}"
    )


def test_catalog_defines_finding_contract():
    body = CATALOG.read_text(encoding="utf-8").lower()
    # Every finding cites three falsifiable parts.
    assert "what to remove" in body
    assert "est-loc" in body or "loc-saved" in body or "loc saved" in body
    assert "keeps tests green" in body or "tests stay green" in body or (
        "tests green" in body
    )


@pytest.mark.parametrize("guard", [f"G{i}" for i in range(1, 7)])
def test_catalog_lists_six_guardrails(guard: str):
    body = CATALOG.read_text(encoding="utf-8")
    assert re.search(rf"\b{guard}\b", body), f"catalog missing guardrail {guard}"


def test_catalog_long_but_coherent_is_never_a_finding():
    body = CATALOG.read_text(encoding="utf-8").lower()
    assert "long" in body and "coherent" in body, (
        "G1 (long-but-coherent is never a finding) must be explicit"
    )


def test_catalog_splits_two_goals():
    body = CATALOG.read_text(encoding="utf-8").lower()
    # Goal A blocks on the diff; Goal B is advisory and bounded.
    assert "blocking" in body, "Goal A (block on the diff) must be present"
    assert "advisory" in body, "Goal B (advisory boy-scout) must be present"
    assert "touched unit" in body or "touched-unit" in body, (
        "Goal B must be bounded to the touched unit"
    )


def test_catalog_encodes_behavioral_rules():
    """Beyond presence of codes, the catalog must encode the BEHAVIOR
    (external-review OpenAI #1): the router definition, the unproven-safety
    downgrade, the touched-unit scope, and the untrusted-content rule.
    """
    body = CATALOG.read_text(encoding="utf-8").lower()
    assert "whole-file measured loc" in body, "router definition must be explicit"
    assert "never block" in body, "unproven-safety must downgrade, never block"
    assert "enclosing" in body, "touched unit = changed hunk + enclosing symbol"
    assert "evidence" in body, "untrusted-content rule (content = evidence) required"


# ---------------------------------------------------------------------------
# AC2 — the per-language idiom-map
# ---------------------------------------------------------------------------


def test_idiom_map_is_valid_json():
    assert IDIOM_MAP.is_file(), f"missing idiom-map: {IDIOM_MAP}"
    data = json.loads(IDIOM_MAP.read_text(encoding="utf-8"))
    assert isinstance(data, dict)


def test_idiom_map_has_all_languages():
    data = json.loads(IDIOM_MAP.read_text(encoding="utf-8"))
    langs = data.get("languages", {})
    for lang in IDIOM_LANGUAGES:
        assert lang in langs, f"idiom-map missing language section {lang!r}"


@pytest.mark.parametrize("lang", IDIOM_LANGUAGES)
def test_idiom_map_covers_all_codes_per_language(lang: str):
    data = json.loads(IDIOM_MAP.read_text(encoding="utf-8"))
    section = data["languages"][lang]
    for code in CATALOG_CODES:
        assert code in section, f"{lang!r} idiom-map missing code {code!r}"
        entry = section[code]
        assert entry.get("idioms"), (
            f"{lang!r}/{code!r} must list at least one idiom"
        )
        # G1 hook: every entry carries a long-but-coherent exemption note.
        assert entry.get("long_but_coherent"), (
            f"{lang!r}/{code!r} must carry a long_but_coherent exemption note"
        )


# ---------------------------------------------------------------------------
# AC3 — local diff reviewer dimension (bounce-back surface)
# ---------------------------------------------------------------------------


def test_code_reviewer_has_reducibility_section():
    body = CODE_REVIEWER.read_text(encoding="utf-8")
    assert "## Reducibility Reviewer" in body, (
        "code-reviewer.md must carry a Reducibility Reviewer section"
    )
    low = body.lower()
    assert "router" in low, "must state LOC is a router"
    assert "reducibility-catalog.md" in body, "must point at the SSoT catalog"
    assert "reducibility-idioms.json" in body, "must point at the idiom-map"
    assert "no concrete finding" in low or "no finding" in low, (
        "must state: no concrete finding → PASS"
    )


def test_code_reviewer_reducibility_is_separate_from_bloat_checklist():
    """The dimension must NOT live inside the parity-locked section.

    Growing the byte-identical ``## Bloat Checklist`` section would ratchet
    the grandfathered sub-iterate-runner.md baseline. The Reducibility
    Reviewer must be its own section, placed AFTER the closing marker.
    """
    body = CODE_REVIEWER.read_text(encoding="utf-8")
    end_marker = body.find("<!-- /Bloat Checklist -->")
    section = body.find("## Reducibility Reviewer")
    assert end_marker != -1 and section != -1
    assert section > end_marker, (
        "Reducibility Reviewer must come AFTER the Bloat Checklist end marker "
        "(keep the parity section byte-identical)"
    )


# ---------------------------------------------------------------------------
# AC4 — B4.5 CI Tier-3 reviewer (self-contained, no file reads in CI)
# ---------------------------------------------------------------------------


def test_pr_reviewer_has_self_contained_reducibility_rule():
    body = PR_REVIEWER.read_text(encoding="utf-8")
    low = body.lower()
    assert "reducib" in low, "pr_reviewer must mention reducibility"
    # Self-contained: the eight codes are inlined (CI reviewer can't read files).
    # Anchor each code to its smell KEYWORD adjacency — a bare ``\bA\b`` would
    # tautologically match the article "A" elsewhere in the prompt (the SECURITY
    # section), so a deleted rule-7 could still pass (code-reviewer finding #2).
    for code, keyword in CATALOG_CODES.items():
        assert re.search(rf"\b{re.escape(code)}\b\s+\S*{re.escape(keyword)}", body), (
            f"pr_reviewer must inline catalog code {code!r} next to its smell "
            f"({keyword!r}) — CI has no file access"
        )
    assert "coherent" in low, "must encode G1 (long-but-coherent never a finding)"
    assert "est-loc" in low or "loc saved" in low or "loc-saved" in low, (
        "must require the est-LOC-saved part of the finding contract"
    )
    # Conservative CI block threshold (external-review OpenAI #2 + code-reviewer
    # finding #3): the live Required Check must keep its NUMERIC material-LOC
    # threshold, or merge behaviour can silently regress while this test stays
    # green. Pin both the word and the number.
    assert "material" in low, "CI rule must gate `block` on a MATERIAL reduction"
    assert re.search(r"\d+\+?\s*LOC", body), (
        "CI rule must keep a concrete numeric block threshold (e.g. '15+ LOC')"
    )


# ---------------------------------------------------------------------------
# AC5 — external plan reviewer (advisory, goal-B pre-emption)
# ---------------------------------------------------------------------------


def test_iterate_reviewer_has_reducibility_focus():
    body = ITERATE_REVIEWER.read_text(encoding="utf-8").lower()
    assert "reducib" in body or "simpler approach" in body, (
        "iterate_reviewer must add a reducibility / simpler-approach focus"
    )
    assert "over-produc" in body or "less code" in body or "minimal" in body, (
        "plan-stage reducibility must target over-production"
    )


# ---------------------------------------------------------------------------
# AC6 — glossary terms
# ---------------------------------------------------------------------------


def test_glossary_defines_reducibility_terms():
    body = (REPO_ROOT / "shared" / "glossary.md").read_text(encoding="utf-8")
    assert re.search(r"-\s*\*\*Reducibility-Catalog\*\*", body), (
        "glossary must define Reducibility-Catalog"
    )
    assert re.search(r"-\s*\*\*LOC-as-Router\*\*", body), (
        "glossary must define LOC-as-Router"
    )
