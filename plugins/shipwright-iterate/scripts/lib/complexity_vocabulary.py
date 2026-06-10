"""Scope-keyword vocabulary + matcher for the complexity classifier.

Extracted from classify_complexity.py (iterate-2026-06-10-complexity-
classifier-prior) and broadened: the original sets were web-app-only
(spinner/dashboard/new page), so on CLI/API/library/infra projects nothing
ever matched and every prompt fell through to "trivial" (measured: 64% of
real Stage-1 outputs vs 14% of runs actually finalizing trivial).

Two deliberate matching rules (corpus-validated against real prompts in
tests/fixtures/complexity_corpus.json):

- Boundaries are ALPHANUMERIC, not regex ``\\b``: underscores count as
  separators so `dashboard` keeps firing inside `update_build_dashboard.py`,
  while `new command` no longer fires inside `renew commander`.
- A naive plural suffix (`s`/`es`) is allowed so `Workflows` matches
  `workflow`; arbitrary inflection (`consolidated`) does not match.

Additions are anchored *scope-signal* phrases that generalize across stacks;
bare domain nouns (`parser`, `resolver`, `scheduler`) were rejected in
external review as collision-prone — prompts that only mention them are
carried by the history prior instead (see complexity_history.py).
"""

import re

COMPLEXITY_ORDER = ["trivial", "small", "medium", "large"]

SCOPE_LARGE_KEYWORDS = {
    # original web-app set
    "multi-language", "i18n", "internationalization", "rewrite",
    "rebuild", "overhaul", "migration", "redesign the entire",
    "replace all", "new split",
    # cross-domain additions ("new module" moved to medium: the corpus
    # shows such prompts finalize medium, large was over-classification)
    "rearchitect", "re-architect", "breaking change", "from scratch",
    "new subsystem",
}
SCOPE_MEDIUM_KEYWORDS = {
    # original web-app set
    "search", "filter", "dashboard", "wizard", "workflow",
    "new page", "new screen", "new route", "integration",
    # cross-domain additions
    "new module", "new command", "new endpoint", "new service",
    "new hook", "new script", "new producer", "new consumer",
    "new table", "new job", "new tool", "new check",
    "add support for", "consolidate", "race condition", "concurrency",
    "systemic", "cross-cutting", "end-to-end",
    "producer-consumer", "producer/consumer",
}
SCOPE_SMALL_KEYWORDS = {
    # original web-app set
    "spinner", "loading", "tooltip", "icon", "badge",
    "toast", "notification", "rename", "reorder",
    # cross-domain additions
    "typo", "bump", "pin", "wording", "label", "log message",
    "error message", "default value", "docs only", "comment",
    "off-by-one",
}

# Alphanumeric lookarounds (underscore = separator) + optional naive plural.
_PATTERN_TEMPLATE = r"(?<![A-Za-z0-9]){kw}(?:e?s)?(?![A-Za-z0-9])"

_COMPILED: dict[str, re.Pattern] = {}


def _pattern(keyword: str) -> re.Pattern:
    pat = _COMPILED.get(keyword)
    if pat is None:
        pat = re.compile(_PATTERN_TEMPLATE.format(kw=re.escape(keyword)))
        _COMPILED[keyword] = pat
    return pat


def match_scope_keyword(message: str) -> str | None:
    """Return the matched scope level or None on no match.

    Levels are checked large -> medium -> small: the highest matched scope
    wins (a prompt that both renames and rebuilds is a rebuild).
    """
    msg_lower = message.lower()
    for level, keywords in (
        ("large", SCOPE_LARGE_KEYWORDS),
        ("medium", SCOPE_MEDIUM_KEYWORDS),
        ("small", SCOPE_SMALL_KEYWORDS),
    ):
        for kw in keywords:
            if _pattern(kw).search(msg_lower):
                return level
    return None


def estimate_scope(message: str) -> str:
    """Legacy vocabulary-only estimate: "trivial" on no match.

    Kept for existing in-repo importers/tests (re-exported from
    classify_complexity; deliberately NOT part of the shared contract).
    `classify()` in classify_complexity.py is the canonical,
    history-aware decision path — new callers should use that.
    """
    return match_scope_keyword(message) or "trivial"
