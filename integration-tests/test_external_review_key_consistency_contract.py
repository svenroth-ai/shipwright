"""Drift-protection test: every `reviews.openai.feedback` parse site also
names the driver=codex key (`reviews.opus.feedback`) it must read instead.

DRIVER_ROSTERS keys external_review.py's `reviews` dict by each roster
identity's own name (`{glm, openai}` for --driver claude, `{glm, opus}` for
--driver codex — shared/scripts/tools/external_review.py, DRIVER_ROSTERS),
so a consumer that only ever parses `reviews.openai.feedback` silently gets
nothing back under Codextender (--driver codex), where that key is
`reviews.opus` instead. A local PR-review preflight (F11, Codextender Part
C) found exactly this: the driver-selection fix updated 11 --driver call
sites but missed the downstream consumer prose in two of them. Guards
against the same class of drift recurring silently.

Split out of `test_external_review_driver_prose_contract.py` (the --driver
coverage tests) to keep both files under the 300-line limit — this file has
no dependency on that file's fenced-block/live-idiom helpers.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PLUGINS_ROOT = REPO_ROOT / "plugins"

_OPENAI_FEEDBACK_RE = re.compile(r"reviews\.openai\.feedback")
_OPUS_FEEDBACK_RE = re.compile(r"reviews\.opus\.feedback")

# Proximity window (lines), not file-level: the CI PR-review gate (Tier-3,
# round 5) found a file-level "both mentioned somewhere" check does not prove
# a SPECIFIC openai.feedback occurrence is the one paired with the opus
# alternative, only that some occurrence of each exists anywhere in the file.
# Binding each occurrence to a nearby opus mention ties the check to the
# actual parse SITE, not just the file.
_PARSE_SITE_PROXIMITY_LINES = 15


def _line_numbers(pattern: "re.Pattern[str]", text: str) -> list[int]:
    return [text.count("\n", 0, m.start()) + 1 for m in pattern.finditer(text)]


def test_every_openai_feedback_parse_site_also_names_the_opus_key():
    sites_missing_opus = []
    for md_file in PLUGINS_ROOT.rglob("*.md"):
        text = md_file.read_text(encoding="utf-8")
        openai_lines = _line_numbers(_OPENAI_FEEDBACK_RE, text)
        if not openai_lines:
            continue
        opus_lines = _line_numbers(_OPUS_FEEDBACK_RE, text)
        rel = str(md_file.relative_to(REPO_ROOT))
        for openai_line in openai_lines:
            if not any(abs(openai_line - opus_line) <= _PARSE_SITE_PROXIMITY_LINES
                       for opus_line in opus_lines):
                sites_missing_opus.append(f"{rel}:{openai_line}")
    assert not sites_missing_opus, (
        "the following reviews.openai.feedback occurrences have no "
        "reviews.opus.feedback mention (the key under --driver codex / "
        f"Codextender) within {_PARSE_SITE_PROXIMITY_LINES} lines -- a "
        "driver=codex run's second review would be silently dropped at "
        "that specific parse site:\n"
        + "\n".join(sites_missing_opus)
    )


def test_openai_feedback_parse_sites_are_still_present():
    """Sanity floor pinning the 4 known sites, mirroring
    test_known_call_sites_are_still_present in
    test_external_review_driver_prose_contract.py — if every one stopped
    matching (e.g. a rename), the assertion above would pass vacuously."""
    known_sites = {
        PLUGINS_ROOT / "shipwright-build" / "skills" / "build" / "references" / "code-review.md",
        PLUGINS_ROOT / "shipwright-iterate" / "agents" / "sub-iterate-runner.md",
        PLUGINS_ROOT / "shipwright-iterate" / "skills" / "iterate" / "references" / "iteration-planning.md",
        PLUGINS_ROOT / "shipwright-iterate" / "skills" / "iterate" / "references" / "iteration-reviews.md",
    }
    seen = {
        md_file for md_file in PLUGINS_ROOT.rglob("*.md")
        if _OPENAI_FEEDBACK_RE.search(md_file.read_text(encoding="utf-8"))
    }
    missing = known_sites - seen
    assert not missing, f"expected a reviews.openai.feedback parse mention in: {sorted(str(p) for p in missing)}"
