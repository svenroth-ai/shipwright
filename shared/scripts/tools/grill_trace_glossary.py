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
import sys
from pathlib import Path

# Bootstrap: make lib.atomic_write importable regardless of caller (mirrors
# context_md_format.py's own _LIB bootstrap — same reason: durable_read_bytes
# retries past a Windows mid-os.replace sharing violation, which a bare
# Path.read_bytes() would misreport as "unreadable").
_LIB = Path(__file__).resolve().parents[1] / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from atomic_write import durable_read_bytes  # noqa: E402

from tools.context_md_format import read_terms  # noqa: E402
from tools.verifiers.common import CheckResult  # noqa: E402

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
    actually read — surface it as its own failing result instead.

    Round 3 (PR #705 review): ``.exists()`` alone is also true for a
    directory, and says nothing about whether the path is actually
    readable (permissions, a mid-write Windows sharing violation, bad
    encoding). Both left the same silent-non-read failure class this
    check exists to catch — they just reached it via
    ``collect_known_terms`` afterwards instead, where it surfaced as a
    misleading ``malformed_context`` result (a check meant for a broken
    CONTEXT.md, not a broken glossary) or, if no traces existed yet, was
    never surfaced at all. Checking presence, file-ness, and an actual
    read here — before ``collect_known_terms`` ever runs — keeps this
    check the single place that owns "was the glossary source actually
    read"."""
    name = "glossary_source_available"
    if not glossary_path.exists():
        return CheckResult(
            name, False,
            f"{glossary_path} does not exist — the framework's own glossary is "
            "missing (a broken install), not a normal 'fresh project' state",
        )
    if not glossary_path.is_file():
        return CheckResult(
            name, False,
            f"{glossary_path} exists but is not a file (e.g. a directory) — "
            "the framework's own glossary path is broken (a broken install), "
            "not a normal state",
        )
    try:
        durable_read_bytes(glossary_path).decode("utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        return CheckResult(
            name, False,
            f"{glossary_path} exists but could not be read "
            f"({type(exc).__name__}: {exc}) — the framework's own glossary is "
            "broken (a broken install), not a normal state",
        )
    return CheckResult(name, True, f"{glossary_path} found")


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
