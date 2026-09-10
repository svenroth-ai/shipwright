"""Known-term collection for the grill-trace undefined-term STOP — split out
of ``verify_grill_trace_completeness.py`` the moment that file crossed the
300-LOC bloat-baseline threshold a second time (same precedent as
``grill_trace_fr_coverage.py``).

Union of ``shared/glossary.md`` (framework vocabulary) and the target
project's ``CONTEXT.md`` (domain vocabulary, via P4.1's sanctioned
``context_md_format.read_terms``) — the two sources
``shared/grill-trace-format.md`` §4 names.
"""

from __future__ import annotations

import re
from pathlib import Path

from tools.context_md_format import read_terms
from tools.verifiers.common import CheckResult

# shared/glossary.md ships alongside this script's own `shared/` tree — it is
# framework vocabulary, never part of a target project — so it resolves by
# file location, not via --project-root. `parents[2]` from
# shared/scripts/tools/<this file>.py is `shared/`.
DEFAULT_GLOSSARY_PATH = Path(__file__).resolve().parents[2] / "glossary.md"

# `- **Term** — ...` bullet entries anywhere in shared/glossary.md (mirrors
# context_md_format's line-anchored matching discipline — a bold phrase
# mid-sentence elsewhere in the glossary's own prose must not count).
_GLOSSARY_TERM_RE = re.compile(r"^\s*-\s+\*\*(.+?)\*\*", re.MULTILINE)


def parse_glossary_terms(glossary_path: Path) -> set[str]:
    if not glossary_path.exists():
        return set()
    content = glossary_path.read_text(encoding="utf-8")
    return set(_GLOSSARY_TERM_RE.findall(content))


def check_glossary_source_available(glossary_path: Path) -> CheckResult:
    """``shared/glossary.md`` ships with the framework itself, at a fixed
    location relative to this script — unlike a target project's
    ``CONTEXT.md`` (legitimately absent for a fresh project, §4), a missing
    ``shared/glossary.md`` means the Shipwright install is broken, not a
    normal state. External code review (P4.2) found the original code
    silently degraded this to an empty term set, letting a trace with no
    declared terms pass while one of the two required sources was never
    actually read — surface it as its own failing result instead."""
    name = "glossary_source_available"
    if glossary_path.exists():
        return CheckResult(name, True, f"{glossary_path} found")
    return CheckResult(
        name, False,
        f"{glossary_path} does not exist — the framework's own glossary is "
        "missing (a broken install), not a normal 'fresh project' state",
    )


def collect_known_terms(glossary_path: Path, context_path: Path) -> set[str]:
    """Union of ``shared/glossary.md``'s bold entries and the target
    project's ``CONTEXT.md`` ``Language`` terms — exact-case, exact-prose,
    no folding (the same matching contract ``context_md_format.py``
    documents for its own reader). A missing ``CONTEXT.md`` (P4.1 not yet
    run, or a fresh project) legitimately contributes no terms; call
    :func:`check_glossary_source_available` separately to catch a missing
    ``shared/glossary.md``, which is never legitimate."""
    terms = parse_glossary_terms(glossary_path)
    terms.update(t.term for t in read_terms(context_path))
    return terms
