"""Shared helpers for the campaign-contract PROSE guards.

Not named ``test_*``, so pytest does not collect it — the same shape as
``_review_cli_harness.py`` next door, and for the same reason: two modules now
assert against `campaign-mode.md` and duplicating the normaliser would let them
drift apart while both stayed green.

The split itself is a bloat split. `test_campaign_review_contract_prose.py`
reached 354 lines against a 300-line limit when the step-3f-bis guards were
added, and those guards are a cohesive group with their own subject, so they
moved to `test_campaign_step_3f_bis.py` rather than being exception-allowed.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
_ITERATE = REPO_ROOT / "plugins" / "shipwright-iterate"
_SKILL_DIR = _ITERATE / "skills" / "iterate"

REVIEWS_DOC = _SKILL_DIR / "references" / "iteration-reviews.md"
CAMPAIGN_DOC = _SKILL_DIR / "references" / "campaign-mode.md"
RUNNER_DOC = _ITERATE / "agents" / "sub-iterate-runner.md"
RUNNER_SCHEMA = _ITERATE / "agents" / "sub_iterate_runner_contract.schema.json"


def norm(text: str) -> str:
    """Normalise markdown so wording is asserted, not layout.

    Unlike the sibling helper in `test_review_cascade_decoupled.py`, underscores
    are PRESERVED: half of what these modules assert is CLI flags
    (`--review-type external_code`), and stripping `_` as markdown emphasis
    silently turned every such assertion into one that could never match.
    """
    text = text.replace("—", "-").replace("’", "'").replace("§", "")
    text = re.sub(r"^[ \t]*>[ \t]?", " ", text, flags=re.MULTILINE)
    text = re.sub(r"[*`]+", "", text)
    return re.sub(r"\s+", " ", text).strip().lower()


def section(doc: Path, heading: str, *, stop: str = "\n### ") -> str:
    """The body of one `###` section, up to the next same-level heading."""
    text = doc.read_text(encoding="utf-8")
    start = text.index(heading)
    rest = text[start + len(heading):]
    end = rest.find(stop)
    return heading + (rest if end < 0 else rest[:end])


def step_3f_bis() -> str:
    """The body of loop step `3f-bis`, matched on its LABEL, not a mention.

    `3f-bis` also appears in campaign-mode.md's header note, and an earlier
    version sliced at the first occurrence and cut only at a bare "3g". That
    region spanned the note, the setup section and steps 3a-3f, so `--force` was
    satisfied by the note and `STRICT-STOP` by step 3f's own — both assertions
    passed with the step's flags and its REJECT paragraph deleted (Stage-2
    review). Anchoring on the label at line start is what makes them bite.
    """
    text = CAMPAIGN_DOC.read_text(encoding="utf-8")
    start = re.search(r"(?m)^\s*3f-bis\.", text)
    assert start, "campaign-mode.md must define loop step `3f-bis.`"
    body = text[start.start():]
    end = re.search(r"(?m)^\s*3g\.", body)
    return norm(body[:end.start()] if end else body)
