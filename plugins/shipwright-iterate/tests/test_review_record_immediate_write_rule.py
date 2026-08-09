"""Drift-protection for the immediate-write ordering mandate
(iterate-2026-08-09-compaction-state-audit).

Root cause: a reviewer's raw reply exists only in the Task tool's result
until the orchestrator's next action writes it to a payload file for
record_review_pass.py. Nothing mandated that write happen before any other
action — a compaction landing in that window could lose the finding outright.
The mandate is repeated at every site that actually spawns a review subagent:
SKILL.md Step 8 (standalone iterate), `iteration-reviews.md`'s "Recording
each review pass" (the shared rationale + the run_id-in-prompt requirement
the SubagentStop salvage hook depends on), and campaign-mode.md's 3f-bis
(the autonomous/campaign spawn site — NOT sub-iterate-runner.md's Step 3.7,
which only delegates the cascade and never calls the Agent tool itself).

Each site is anchored on its own heading/marker first, then searched for the
same marker phrase — survives wording tweaks, fails when a site's mandate is
silently dropped.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
SKILL_MD = REPO_ROOT / "plugins" / "shipwright-iterate" / "skills" / "iterate" / "SKILL.md"
ITERATION_REVIEWS_MD = (
    REPO_ROOT / "plugins" / "shipwright-iterate" / "skills" / "iterate"
    / "references" / "iteration-reviews.md"
)
CAMPAIGN_MODE_MD = (
    REPO_ROOT / "plugins" / "shipwright-iterate" / "skills" / "iterate"
    / "references" / "campaign-mode.md"
)

MANDATE_MARKER = "before any other reasoning"


def _extract_step_8_body(text: str) -> str:
    pattern = re.compile(r"^### Step 8: Full Code Review.*?(?=\n### )",
                         flags=re.MULTILINE | re.DOTALL)
    match = pattern.search(text)
    return match.group(0) if match else ""


def _extract_recording_each_pass_body(text: str) -> str:
    pattern = re.compile(r"^## Recording each review pass.*?(?=\n## )",
                         flags=re.MULTILINE | re.DOTALL)
    match = pattern.search(text)
    return match.group(0) if match else ""


def _extract_3f_bis_body(text: str) -> str:
    pattern = re.compile(r"^   3f-bis\..*?(?=\n   3g\.)",
                         flags=re.MULTILINE | re.DOTALL)
    match = pattern.search(text)
    return match.group(0) if match else ""


def _normalize_ws(text: str) -> str:
    """Collapse runs of whitespace (incl. newlines) to a single space, so a
    marker phrase survives hard-wrapped prose (campaign-mode.md wraps at
    ~80 chars; SKILL.md/iteration-reviews.md write dense single-line
    paragraphs) — both are legitimate markdown styles."""
    return re.sub(r"\s+", " ", text)


SITES = [
    ("SKILL.md Step 8", SKILL_MD, _extract_step_8_body),
    ("iteration-reviews.md Recording each review pass", ITERATION_REVIEWS_MD,
     _extract_recording_each_pass_body),
    ("campaign-mode.md 3f-bis", CAMPAIGN_MODE_MD, _extract_3f_bis_body),
]


@pytest.mark.parametrize("label,path,extractor", SITES, ids=[s[0] for s in SITES])
def test_site_extracts(label, path, extractor) -> None:
    text = path.read_text(encoding="utf-8")
    body = extractor(text)
    assert body, f"Could not extract the {label} section — probe regex may need updating."


@pytest.mark.parametrize("label,path,extractor", SITES, ids=[s[0] for s in SITES])
def test_site_carries_immediate_write_mandate(label, path, extractor) -> None:
    text = path.read_text(encoding="utf-8")
    body = _normalize_ws(extractor(text))
    assert MANDATE_MARKER in body, (
        f"{label} is missing the immediate-write ordering mandate "
        f"({MANDATE_MARKER!r}) — a reviewer's reply must be written to disk "
        f"before any other reasoning or the next spawn."
    )


@pytest.mark.parametrize("label,path,extractor", [SITES[0], SITES[2]],
                        ids=[SITES[0][0], SITES[2][0]])
def test_spawn_sites_require_run_id_in_prompt(label, path, extractor) -> None:
    """Only the actual spawn sites (not the rationale doc) need the
    run_id-in-prompt requirement — the SubagentStop salvage hook can only
    find the run_id in the subagent's own transcript."""
    text = path.read_text(encoding="utf-8")
    body = _normalize_ws(extractor(text))
    assert "run_id in plain text" in body, (
        f"{label} must require the spawn prompt to state the run_id in "
        f"plain text — write-review-payload-on-stop.py cannot resolve it "
        f"any other way."
    )
