"""What a build section declared it would touch, and what it actually touched.

Part (3) of the requirement write-back loop. "Nothing outside the section's
scope", read literally, made a section that cannot function without touching
something shared **unbuildable** — which was never the intent; the rule is aimed
at unrequested extra work. The resolution is that such a section may make the
smallest change it needs, *recorded as belonging to that section*. This module
is what makes "recorded" checkable: every changed file must be either declared by
the section's own ``## Files to Create/Modify`` block or carried as an attributed
extra on its requirement-impact declaration.

**The parser is deliberately forgiving.** Section files are LLM-written, so they
arrive with task checkboxes, bold paths, back-ticked and bare paths, em-dashes
and colons, and Windows separators. A strict parser would reject valid sections
and produce false failures — and a check that cries wolf gets switched off, which
is a worse outcome than not having it. Precision is recovered on the other side:
a *path* that does not parse simply is not declared, and the diff comparison is
what decides.

Origin: trg-e9e5188e (FR-01.05).
"""

from __future__ import annotations

import re

from lib.requirement_impact import to_repo_relative_posix

#: The block heading, at any depth, with or without spaces around the slash and
#: with any trailing decoration (a count, a note). Case-insensitive.
_HEADING_RE = re.compile(
    r"^\s{0,3}#{2,6}\s*files\s+to\s+create\s*/\s*modify\b.*$",
    re.IGNORECASE,
)
#: Any ATX heading — ends the block.
_ANY_HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s")
#: A leading list marker plus an optional task checkbox.
_BULLET_RE = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+(?:\[[ xX]\]\s*)?")
#: The first back-ticked span on the line — the most reliable path signal.
_BACKTICKED_RE = re.compile(r"`([^`]+)`")
#: Separators between a path and its description, longest first.
_DESC_SPLIT_RE = re.compile(r"\s+[—–-]\s+|:\s+")
#: A token that plausibly names a file or directory rather than prose.
_PATH_LIKE_RE = re.compile(r"^[\w.@+][\w./@+-]*$")

#: Artifacts the BUILD PHASE ITSELF is required to write, at Steps 9/10/10a/10b —
#: after the Step 8 commit. Because the phase commits with ``git add -A``, the
#: next section's commit sweeps up the previous section's bookkeeping, so these
#: paths appear in a range no matter how tightly it is scoped.
#:
#: They are excluded **as a category, said out loud** — not as a quiet special
#: case for this mechanism's own log. None of them is section work: no section
#: plan lists the event log or the decision log among its files, and requiring an
#: attributed extra for an artifact the framework mandates would train operators
#: to write meaningless reasons, which is how a check stops meaning anything.
#: Everything outside this list is still the section's to declare.
#: Kept as narrow as the flow allows — each entry names an artifact a specific
#: build step writes, not a whole area. ``.shipwright/agent_docs/`` as a
#: directory would have excluded any agent-doc a section might legitimately
#: edit; only the files Steps 9/10/10a actually produce are listed. The two
#: directory entries that remain are wholly machine-generated: compliance output
#: is regenerated in full by ``update_compliance.py``, and every declaration
#: under ``requirement-impact/`` is written by this mechanism itself.
FRAMEWORK_BOOKKEEPING: tuple[str, ...] = (
    ".shipwright/planning/requirement-impact/",
    ".shipwright/compliance/",
    ".shipwright/agent_docs/runtime/",
    ".shipwright/agent_docs/decision_log.md",
    ".shipwright/agent_docs/decision-drops/",
    ".shipwright/agent_docs/build_dashboard.md",
    ".shipwright/agent_docs/session_handoff.md",
    ".shipwright/agent_docs/triage_inbox.md",
    ".shipwright/triage.jsonl",
    "shipwright_events.jsonl",
    "shipwright_build_config.json",
    "design-fidelity-report.json",
)
#: Prose placeholders an LLM writes when a section declares no files. Kept as a
#: small closed set rather than a "must look like a path" rule: requiring a slash
#: or an extension would drop legitimate extension-less entries (``Makefile``,
#: ``Dockerfile``), and a missed declaration is a FALSE failure, whereas a stray
#: declared entry is merely inert — it just never matches a changed path.
_PLACEHOLDERS = frozenset({"none", "n/a", "na", "tbd", "-", "—"})


def parse_declared_files(text: str) -> list[str]:
    """Return the repo-relative paths a section declared, in order, de-duplicated."""
    out: list[str] = []
    seen: set[str] = set()
    for line in _block_lines(text or ""):
        for path in _paths_from_line(line):
            if path not in seen:
                seen.add(path)
                out.append(path)
    return out


def _block_lines(text: str) -> list[str]:
    """The lines between the block heading and the next heading."""
    lines = text.splitlines()
    try:
        start = next(i for i, line in enumerate(lines) if _HEADING_RE.match(line))
    except StopIteration:
        return []
    block: list[str] = []
    for line in lines[start + 1:]:
        if _ANY_HEADING_RE.match(line):
            break
        block.append(line)
    return block


def _paths_from_line(line: str) -> list[str]:
    """Extract every path a bullet line names, in order.

    A line may legitimately name more than one — ``- Create `a.ts` and `b.ts``` —
    and keeping only the first would report the rest as unattributed, the false
    failure this module exists to avoid.

    Back-ticked spans win when present, but **only those before the description
    separator**: in ``- src/a.ts — wraps `fetch``` the back-ticked token belongs
    to the prose, and taking it would both invent a path and drop the real one.
    """
    stripped = _BULLET_RE.sub("", line).strip()
    if not stripped:
        return []

    head = _DESC_SPLIT_RE.split(stripped, 1)[0]
    # Three sources, in order of confidence:
    #   1. back-ticked spans BEFORE the separator — the path, unambiguously;
    #   2. the head token itself, when it already looks like a path
    #      (`- src/a.ts — wraps `fetch`` must yield src/a.ts, NOT the prose's
    #      back-ticked word);
    #   3. back-ticked spans anywhere — for `- Modify: `src/x.ts`` and
    #      `- Tests: `src/x.test.ts``, where the separator comes first so the
    #      head is a label and taking it would drop the real path.
    candidates = _extract(_BACKTICKED_RE.findall(head))
    if candidates:
        return candidates
    # A head that unambiguously looks like a path (a separator or an extension)
    # beats a back-ticked word later in the prose.
    confident_head = [c for c in _extract([head]) if _looks_like_path(c)]
    if confident_head:
        return confident_head
    # Otherwise the head is probably a label ("Modify", "Tests", "New file") —
    # take the back-ticked path it introduces.
    anywhere = _extract(_BACKTICKED_RE.findall(stripped))
    # Last resort: an extension-less bare entry such as `Makefile`.
    return anywhere or _extract([head])


def _looks_like_path(candidate: str) -> bool:
    """A directory separator or a file extension — the unambiguous path signals."""
    return "/" in candidate or bool(re.search(r"\.[A-Za-z0-9]{1,8}$", candidate))


def _extract(raw_candidates) -> list[str]:
    """Normalize candidates, keeping only those that plausibly name a path."""
    out: list[str] = []
    for candidate in raw_candidates:
        cleaned = _strip_emphasis(str(candidate).strip())
        # A bare (un-backticked) path may still be followed by prose with no
        # separator; keep only the first whitespace-delimited token.
        tokens = cleaned.split()
        if not tokens:
            continue
        normalized = to_repo_relative_posix(tokens[0]).rstrip(",;")
        if not normalized or normalized.lower() in _PLACEHOLDERS:
            continue
        if not _PATH_LIKE_RE.match(normalized.rstrip("/")):
            continue
        out.append(normalized)
    return out


def _strip_emphasis(text: str) -> str:
    """Remove BALANCED markdown emphasis wrappers only.

    A per-character ``strip("*_")`` would mangle real filenames — ``_utils.py``
    becomes ``utils.py`` and ``__init__.py`` becomes ``init__.py`` — and the
    resulting phantom path is then reported as unattributed.
    """
    previous = None
    while previous != text:
        previous = text
        text = re.sub(r"^(\*\*|__|\*|_)(.+?)\1$", r"\2", text.strip())
    return text


def unattributed_paths(changed, *, declared, extras, requirement_specs=()) -> list[str]:
    """Changed paths that neither the section nor an attributed extra accounts for.

    A declared entry ending in ``/`` — or one that is a parent directory of a
    changed file — covers everything beneath it: sections routinely name a
    directory when they add several files to it, and treating that as
    undeclared would be a false failure of exactly the kind this module avoids.

    ``requirement_specs`` are requirements files the section's declaration
    *already accounts for*. Part (2) obliges a section that resolved a
    mockup-vs-spec contradiction to correct the requirement, so the ``spec.md``
    edit is a mandated output of this phase — and it arrives with a stronger
    record than an attributed extra: a behaviour-affecting declaration naming the
    FR, whose touch check git-verified that very file. Counting it as
    unattributed would make part (2) and part (3) contradict each other. The
    caller passes this **only** for a behaviour-affecting declaration, so a
    section claiming ``--impact none`` while editing requirements still fails.
    """
    declared_files: set[str] = set()
    declared_dirs: set[str] = set()
    for entry in (declared or []):
        norm = to_repo_relative_posix(entry)
        if not norm:
            continue
        if norm.endswith("/"):
            declared_dirs.add(norm.rstrip("/"))
        else:
            declared_files.add(norm)
    declared_files.discard("")
    declared_dirs.discard("")
    extra_files = {
        to_repo_relative_posix(
            item.get("path") if isinstance(item, dict) else item
        )
        for item in (extras or [])
    }
    extra_files |= {to_repo_relative_posix(p) for p in (requirement_specs or ())}
    extra_files.discard("")

    missing: set[str] = set()
    for raw in changed or []:
        path = to_repo_relative_posix(raw)
        if not path or path in extra_files or _covered(path, declared_files,
                                                        declared_dirs):
            continue
        if is_framework_bookkeeping(path):
            continue
        missing.add(path)
    return sorted(missing)


def is_framework_bookkeeping(path) -> bool:
    """True iff ``path`` is an artifact the phase itself is required to write.

    See :data:`FRAMEWORK_BOOKKEEPING` for why this category exists and why it is
    documented rather than hidden.
    """
    norm = to_repo_relative_posix(path)
    return any(
        norm == entry or norm.startswith(entry) if entry.endswith("/") else norm == entry
        for entry in FRAMEWORK_BOOKKEEPING
    )


def _covered(path: str, declared_files: set[str], declared_dirs: set[str]) -> bool:
    """True iff ``path`` is declared outright or lies under a declared directory.

    Only entries written WITH a trailing slash act as directories. The forgiving
    parser can mint a bare token out of prose (``- src/lib helpers as needed``
    yields ``src/lib``), and treating every such token as a directory would
    pre-attribute everything beneath it with no reason recorded — the
    shared-touch discipline switched off by one vague bullet.
    """
    if path in declared_files:
        return True
    return any(path.startswith(f"{entry}/") for entry in declared_dirs)
