"""Pure detectors for FR-row hygiene against ``shared/fr-authoring.md``.

Moved here from ``plugins/shipwright-compliance/scripts/audit/group_i_detectors.py``
(iterate-2026-09-06-fr-hygiene-touched-rows) so a SECOND consumer — the
diff-scoped, non-dodgeable F11 gate in
``shared/scripts/tools/verifiers/fr_hygiene.py`` — can read the identical
vocabulary Group I's advisory ``I1``/``I2`` checks use, without that verifier
cross-plugin-importing the compliance plugin's own ``scripts/audit`` package
(the F11 verifiers under ``shared/scripts/tools/verifiers/`` never import a
plugin's private lib — see ``integration_coverage.py`` / ``ci_supplychain.py``
docstrings for the same rule applied to their own SSoTs). The direction
mirrors ``lib.fr_criteria``'s own precedent: "the parser moved here, not the
other way". ``group_i_detectors`` re-exports every name below unchanged, so
``group_i.name_violations`` / ``.description_violations`` / ``.is_fold_candidate``
remain the single entry point Group I and its tests already use.

Everything here is pure and total: string in, verdict out. No I/O, no
plugin imports.

The vocabularies below MUST stay in step with `shared/fr-authoring.md`:
§1/§5 for the implementation-detail fences, §3 for the fold verbs.

Deliberately NOT linted (the rulebook states them, no detector claims them):
§5.3 "about six words" and §5.4 "one FR, one capability" — both need editorial
judgement, and a wrong automated verdict on them would be worse than silence.
"""

from __future__ import annotations

import re


_HTTP_VERB_RE = re.compile(r"\b(?:GET|POST|PUT|PATCH|DELETE|HEAD)\b")
_ADR_RE = re.compile(r"\bADR-\d+", re.IGNORECASE)
_ITERATE_SLUG_RE = re.compile(r"\biterate-\d{4}-\d{2}-\d{2}")
#: A filename extension preceded by a word character. Deliberately anchored on
#: the extension rather than matching the whole path: a leading ``[\w./-]*\w``
#: overlaps its own character class (``\w`` is a subset of ``[\w./-]``), which
#: backtracks exponentially on a long word-char run that never reaches a dot —
#: a real ReDoS over arbitrary requirement prose (CodeQL py/redos, PR #395).
#: Presence is all this detector needs, so one literal dot suffices and the
#: match is linear. Longest alternatives first so ``.tsx`` is not read as
#: ``.ts`` + ``x``.
_FILE_PATH_RE = re.compile(
    r"\w\.(?:tsx|ts|jsx|js|mjs|cjs|py|json|ya?ml|toml|sh|md|css|html)\b"
)
_SNAKE_RE = re.compile(r"\b[a-z][a-z0-9]*(?:_[a-z0-9]+)+\b")
_CAMEL_RE = re.compile(r"\b[a-z]+[A-Z][A-Za-z]*\b")
#: PascalCase identifiers (``TaskService``, ``FrRow``). Requires an internal
#: capital, so ordinary capitalised prose ("Command Center") never matches.
#: Each repetition must start with an uppercase letter and the tail is
#: lowercase-only, so a run like ``ABCD`` has exactly ONE parse — an inner
#: ``[a-zA-Z]*`` would overlap the group's own ``[A-Z]`` start and reintroduce
#: the same backtracking class as the file-path pattern above.
_PASCAL_RE = re.compile(r"\b[A-Z][a-z]+(?:[A-Z][a-z]*)+\b")

#: Fold signals (§3). The "Phase N of" form requires a nearby FR reference —
#: without it, ordinary domain prose ("phase 2 of the application form") would
#: be misread as a change-delta.
_FOLD_RE = re.compile(
    r"\b(?:completes|complete|fixes|fix|polishes|polish|modifies|replaces"
    r"|extends|supersedes)\s+FR-\d"
    r"|\bPhase\s+\d+\s+of\b(?=.{0,60}FR-\d)",
    re.IGNORECASE,
)

#: Case-mixed words that are ordinary product vocabulary, not code symbols.
#: Matched case-insensitively against both camelCase and PascalCase hits.
_NOT_SYMBOLS = frozenset({
    "ios", "ipados", "iphone", "ipad", "macos", "tvos", "watchos", "icloud",
    "imessage", "ebay", "esim", "javascript", "typescript", "postgresql",
    "graphql", "youtube", "github", "gitlab", "openai", "chatgpt", "paypal",
})


def _has_code_symbol(text: str) -> bool:
    if _SNAKE_RE.search(text):
        return True
    candidates = _CAMEL_RE.findall(text) + _PASCAL_RE.findall(text)
    return any(m.lower() not in _NOT_SYMBOLS for m in candidates)


def violations(text: str) -> list[str]:
    """Kinds of implementation detail present in ``text`` (empty = clean)."""
    out: list[str] = []
    if _HTTP_VERB_RE.search(text):
        out.append("http-verb")
    if _ADR_RE.search(text):
        out.append("adr-number")
    if _ITERATE_SLUG_RE.search(text):
        out.append("iterate-slug")
    if _FILE_PATH_RE.search(text):
        out.append("file-path")
    if _has_code_symbol(text):
        out.append("code-symbol")
    return out


def name_violations(name: str) -> list[str]:
    """Implementation detail leaking into an FR *name* (§5)."""
    return violations(name)


def description_violations(description: str) -> list[str]:
    """Implementation detail leaking into an FR *description* (§1)."""
    return violations(description)


def is_fold_candidate(description: str) -> bool:
    """True when a row describes a change to another FR, not a capability (§3)."""
    return bool(_FOLD_RE.search(description))


__all__ = [
    "description_violations",
    "is_fold_candidate",
    "name_violations",
    "violations",
]
