"""FR-row <-> grill-trace coverage join — split out of
``verify_grill_trace_completeness.py`` the moment that file crossed the
300-LOC bloat-baseline threshold (same precedent as
``_write_context_term_cli.py`` / ``context_md_format.py`` in P4.1).

Closes a gap external plan review found in the ``grill_trace_coverage``
guard alone (P4.2): "an interview ran, zero traces exist" catches a
SKIPPED interview, but not a PARTIALLY recorded one where some elicited
requirements never got a trace. FR ids don't exist until spec generation
(Step 6), so this join can only run at gate-time (Step 8), via the same
``Name``-column slug convention ``shared/grill-trace-format.md`` §1
documents — the slug an interviewer is asked to choose from the
requirement's short capability name, matched against the FR row's own
``Name`` cell once spec generation has written it.

Not one of the four closed-vocabulary STOP conditions
(``verify_grill_trace_completeness.py``'s module docstring) — kept in its
own, differently-named module and result (``fr_trace_coverage``) so it is
never confused with them.
"""

from __future__ import annotations

import re
from pathlib import Path

from tools.verifiers.common import CheckResult, Severity

# One FR row per line of a spec.md's Functional Requirements table, in the
# converged column order `spec-generation.md` documents:
# `| ID | Area | Name | Priority | Description | Basis | Layers |`.
# Anchored on a literal "FR-" in the first cell, which naturally excludes
# the header row and the `|---|` separator row. A narrow, LOCAL parser —
# deliberately not `drift_parsers.parse_fr_table`, which owns `id`/`text`/
# `priority` but never exposes `Name` (the only cell this coverage check
# needs); forking a general FR-table reader for one column would cost more
# than it saves.
_FR_ROW_RE = re.compile(r"^\|\s*(FR-[\w.]+)\s*\|([^|]*)\|([^|]*)\|", re.MULTILINE)
_REMOVED_REQUIREMENTS_RE = re.compile(r"^#{2,3}\s+Removed Requirements\s*$", re.MULTILINE)
_SLUG_COLLAPSE_RE = re.compile(r"[^a-z0-9]+")


def slugify(name: str) -> str:
    """Lower-kebab-case, matching ``shared/grill-trace-format.md``'s
    ``requirement_key`` convention."""
    return _SLUG_COLLAPSE_RE.sub("-", name.strip().lower()).strip("-")


def extract_fr_names(spec_content: str) -> dict[str, str]:
    """``{FR id: Name cell text}`` for every LIVE row in a spec.md's
    Functional Requirements table — rows inside a ``## Removed
    Requirements`` / ``### Removed Requirements`` subsection are excluded,
    mirroring ``drift_parsers.parse_fr_table``'s own exclusion (a retired
    FR is not something a live interview trace should have to cover)."""
    body = _REMOVED_REQUIREMENTS_RE.split(spec_content, maxsplit=1)[0]
    names: dict[str, str] = {}
    for m in _FR_ROW_RE.finditer(body):
        fr_id, name = m.group(1).strip(), m.group(3).strip()
        if name:
            names[fr_id] = name
    return names


def check_fr_trace_coverage(spec_paths: list[Path], trace_keys: set[str]) -> CheckResult:
    """SKIPPED entirely before any spec.md exists (nothing to join against
    yet — the normal state during the interview itself, before Step 6)."""
    name = "fr_trace_coverage"
    if not spec_paths:
        return CheckResult(
            name, None, "no spec.md found yet — nothing to check", severity=Severity.SKIPPED.value,
        )
    fr_names: dict[str, str] = {}
    for path in spec_paths:
        fr_names.update(extract_fr_names(path.read_text(encoding="utf-8", errors="ignore")))
    if not fr_names:
        return CheckResult(
            name, None, "no FR rows found in any spec.md yet", severity=Severity.SKIPPED.value,
        )
    missing = sorted(
        f"{fr_id} (Name={name_!r} -> slug {slugify(name_)!r})"
        for fr_id, name_ in fr_names.items()
        if slugify(name_) not in trace_keys
    )
    if missing:
        # WARNING, not the ERROR default: the join key (a Name-cell slug picked at
        # interview time vs. an FR id minted independently at spec-generation time,
        # PR #705 review) has no stable identity contract — a rename, a punctuation/
        # Unicode difference, or two Names colliding on one slug all produce a false
        # "missing" here. This check's own module docstring says it is NOT one of the
        # four closed-vocabulary STOPs; ERROR severity made it behave like a fifth one
        # and hard-block Step 8 for projects that did the elicitation work correctly.
        # Stays visible (still a real signal for a genuinely skipped/partial interview)
        # without gating completion on a brittle heuristic.
        return CheckResult(
            name, False,
            f"FR row(s) with no matching grill-trace requirement_key: {missing}",
            severity=Severity.WARNING.value,
        )
    return CheckResult(name, True, f"{len(fr_names)} FR row(s), every one has a matching grill-trace")
