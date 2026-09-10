"""Dynamic discovery of requirement-elicitation reference docs (P4.3, FR-01.16
AC09).

Split out of `test_requirement_elicitation_refs.py` to stay under the 300-LOC
bloat-baseline cap; the function is test-only tooling with a single caller
today, kept here (not `shared/scripts/lib/`) since it is not production code.

`discover_elicitation_reference_docs()` replaces a hand-maintained tuple of
"docs that must cite `shared/requirement-elicitation.md`" — which capabilities
elicit requirements is established by looking for them, not by consulting a
list someone must remember to extend.

External plan-review (round 1, GLM medium + OpenAI medium) flagged
`ELICITATION_SURFACE_MARKER` as a natural-language phrase rather than a
repo-author-owned structural marker (e.g. an HTML comment), fragile to a
future paraphrase. A dedicated marker was considered and rejected for this
sub-iterate: it would require editing all 4 current docs, and one of them
(`plugins/shipwright-adopt/skills/adopt/references/step-c-interview.md`) is
explicitly out of scope — this sub-iterate may only READ files under
`plugins/shipwright-adopt/`, never write them. Editing the other 3 docs alone
would leave the same fragility for the adopt surface and introduce an
inconsistent marker convention. Documented here as a known, scope-bounded
limitation rather than built around; the vacuous-pass guard in
`test_discovery_finds_at_least_the_known_citing_docs` (round 1, GLM low)
mitigates the worst-case failure mode of a marker drift (an empty or
partial discovery result fails loudly, rather than silently admitting one
doc's disappearance).
"""

from __future__ import annotations

from pathlib import Path

#: The elicitation-surface discovery marker. Verified (P4.3 precedent research)
#: to appear in exactly the 4 currently-known citing docs
#: (interview-protocol.md, step-c-interview.md, path-a-feature.md,
#: path-b-change.md) and in NO other `references/*.md` file in the repo — each
#: carries this phrase inside the blockquote describing the Pocock-style "one
#: question at a time, each with a recommended answer" grilling rule, so it is
#: a genuine positive signal that the doc governs human-facing elicitation, not
#: an incidental string.
#:
#: Deliberately NOT the string `"requirement-elicitation.md"` — the reverse
#: citation-check test already checks each discovered doc for that string;
#: keying discovery on the same string would collapse "is this an elicitation
#: surface" and "does it cite the module" into one check, defeating the
#: reverse check's purpose (a doc could vacuously "discover" itself by citing
#: the module without actually being a grilling surface).
ELICITATION_SURFACE_MARKER = "recommended answer"


def discover_elicitation_reference_docs(root: Path) -> tuple[Path, ...]:
    """Return every `plugins/*/skills/*/references/*.md` doc under `root` that
    carries `ELICITATION_SURFACE_MARKER`, sorted for stable parametrization.

    `root` is a required parameter (not a module-level constant) so a caller
    can point this at a temp fixture tree instead of the real repo, proving
    discovery is genuinely dynamic rather than a relabeled hardcoded list.
    """
    matches = []
    for path in root.glob("plugins/*/skills/*/references/*.md"):
        if not path.is_file():
            continue
        try:
            body = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        if ELICITATION_SURFACE_MARKER in body:
            matches.append(path)
    return tuple(sorted(matches))


def doc_cites_the_module(doc: Path) -> bool:
    """True iff `doc` cites `shared/requirement-elicitation.md` by name.

    Shared between the reverse citation-check parametrized test (which reads
    every discovered doc through this exact function) and the
    discovered-but-uncited proof test — so the dynamic-discovery proof shows
    a fixture doc genuinely enters the SAME enforcement path the real reverse
    check runs, not merely that the discovery function returns its path
    (external plan-review, round 1, OpenAI medium finding #3).

    Returns `False` (never raises) on a non-UTF-8 file, mirroring
    `discover_elicitation_reference_docs()`'s own `UnicodeDecodeError`
    handling — a file that can never be discovered should not be able to
    crash this companion check either (external code review, round 2, GLM
    low finding).
    """
    try:
        body = doc.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return False
    return "requirement-elicitation.md" in body
