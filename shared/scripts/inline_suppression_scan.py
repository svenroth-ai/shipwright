"""Discover inline ``# nosemgrep`` suppressions from version control.

Leaf module, deliberately — the ratchet (``inline_suppressions``) and the
compliance dashboard both need this, and a shared LEAF each imports by its
unique top-level name is the pattern that keeps them in lockstep without either
importing the other's package (ADR-044/045). Mirrors the
``accepted_risks`` / ``accepted_risk_scan`` split exactly.

**The file set comes from git, not from an extension allowlist.** That is not a
convenience: *source-controlled* is precisely the property being measured, and
deriving the set from ``git ls-files`` removes a whole bypass class — a
suppression in a file type nobody thought to allow-list would otherwise be
invisible to the gate. A non-git tree falls back to a walk with an explicit
exclusion set and reports ``mode: "walk"``, because a discovery step that
silently narrows its own scope reads as "all clear".

**Formats where a suppression cannot be IN EFFECT are excluded**
(``NON_CODE_SUFFIXES``: prose, plus JSON/JSONL which have no comment syntax).
It is a denylist, never an allowlist of code, so a format nobody listed fails
loudly rather than silently.

**Three disclosed limits** — each a deliberate refusal to re-implement
Semgrep's own semantics, which is the drift this whole design exists to avoid.
Full reasoning in ``docs/security-ci-setup.md``; in brief:

1. **String literals are not excluded** — a rule id inside a docstring or
   string is counted. Safe direction: a spurious BLOCK naming the exact
   ``path:line``, never a hidden suppression.
2. **The bare form is not counted.** Without a rule id it suppresses every rule
   on its line, so it is the more dangerous form — but on this repo all nine
   bare-token occurrences are prose, so counting it would be 100%
   false-positive.
3. **Rule ids are matched as written, not as Semgrep resolves them.** Semgrep
   accepts an id PREFIX, so the count is per *spelling*, not per rule: the same
   rule under two spellings becomes two entries, neither of which ratchets
   (Stage-3 doubt review, D5). What still holds is that no spelling grows
   unrecorded.

Both spellings Semgrep honours for the TOKEN (``nosemgrep`` and the ``nosem``
alias) are matched, case-insensitively — not a limit but a fixed defect:
keying to the literal lowercase token left ``# nosem: <rule-id>`` as a working,
undisclosed bypass (Stage-2 code review).
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path
from typing import Any

#: Comment openers a suppression may sit behind. Broad on purpose — a marker
#: this list misses would silently under-count, which is the unsafe direction.
COMMENT_MARKERS = ("#", "//", "--", ";", "/*", "<!--", "%", "(*", "{-")

#: Skipped by the NON-git fallback walk only. The git path needs no exclusions
#: because every one of these is gitignored.
EXCLUDED_DIRS = frozenset({
    ".git", ".venv", "venv", "env", "node_modules", "__pycache__",
    ".worktrees", "site-packages", ".mypy_cache", ".pytest_cache",
    ".ruff_cache", ".tox",
})

#: Formats in which a suppression comment can never be IN EFFECT, so counting
#: one would record a suppression that suppresses nothing. Two kinds:
#:
#: * **Prose** — Semgrep applies no code rule to markdown or reST.
#: * **JSON / JSON Lines** — the format has no comment syntax at all, so the
#:   token can only ever appear inside a string, as data.
#:
#: The JSON half is not hypothetical, and it is structural rather than
#: incidental: Shipwright's own governance artifacts QUOTE code. A review
#: record (`.shipwright/planning/iterate/<run>/reviews.json`) embeds reviewer
#: prose discussing suppression syntax; a triage card filed about a suppression
#: quotes the offending line verbatim; `shipwright_events.jsonl` and
#: `.shipwright/triage.jsonl` are tracked append-logs written by background
#: producers. Stage-3 doubt review (D8) predicted this for `.jsonl`; the F0
#: suite then caught the `.json` half live, on THIS run's own review record.
#: Filing or reviewing anything about this gate must not turn the repo red.
#:
#: A DENYLIST, deliberately, never an allowlist of code extensions: a format
#: missing here yields a visible false positive naming the exact file, whereas a
#: code extension missing from an allowlist is a SILENT miss (external review,
#: GPT #2). ``.txt`` is therefore absent — Semgrep's supply-chain rules do run
#: over `requirements.txt`.
#:
#: Disclosed cost: a JSONC/JSON5 file using `//` comments would be missed. No
#: such file is scanned by Semgrep here, and the alternative — counting every
#: quoted example in every record artifact — is a gate nobody could keep green.
NON_CODE_SUFFIXES = frozenset({
    ".md", ".markdown", ".mdx", ".rst", ".adoc", ".org", ".json", ".jsonl",
})

#: Read size for the streaming token pre-filter. There is deliberately NO size
#: cap on eligibility any more: the earlier 2 MB cap was a silent BYPASS (a
#: tracked file padded past it could carry a live suppression the count never
#: saw — Stage-2 code review), and replacing it with a 50 MB cap that BLOCKED
#: merely moved the defect to the other side, turning a perfectly readable
#: large tracked file into a red build with an untrue remedy ("make the file
#: readable"). Streaming in chunks removes the reason a cap existed at all
#: (Stage-3 doubt review, D10).
_CHUNK_BYTES = 1 << 20

#: The token Semgrep actually honours, in every spelling it accepts.
#:
#: **Both halves of this are load-bearing.** Semgrep treats ``nosem`` as an
#: alias for ``nosemgrep`` and matches the token case-insensitively, so a gate
#: keyed to the literal lowercase ``nosemgrep`` is blind to a real, working
#: suppression written ``# nosem: <rule-id>`` or ``# NOSEMGREP: <rule-id>``.
#: The first draft was exactly that blind, and it is the failure mode this
#: whole module exists to prevent — a suppression in effect that the count
#: cannot see (Stage-2 code review, HIGH). Verified when widening: no
#: occurrence of either variant exists in this repo today, so the seeded
#: counts are unchanged by it.
SUPPRESSION_TOKEN = "nosem"

#: Byte-level pre-filter, applied BEFORE decoding, so only the handful of files
#: actually holding the token are decoded. `git grep -lI -i` would cut the
#: candidate set ~8x faster still, and was measured and DECLINED: it skips an
#: unreadable file silently, trading away the fail-closed detection that makes
#: an unscanned tracked file a BLOCK rather than a hole. A security property is
#: not worth 400 ms.
_TOKEN_BYTES_RE = re.compile(SUPPRESSION_TOKEN.encode("ascii"), re.IGNORECASE)

#: Matches ``nosem[grep]: <rule>[,<rule>…]``. Rule ids are dotted identifiers,
#: and the character class deliberately excludes ``{`` and ``<`` so an f-string
#: placeholder or an angle-bracket prose placeholder yields no match — both
#: occur throughout this repo's own tests and docs.
#:
#: Writing that format with a LITERAL example rule id would make this very
#: comment a counted site, inventing a rule called ``rule``. That is not a
#: hypothetical: an earlier draft did exactly that and the live repo guard
#: blocked on it — the disclosed string-literal limitation, caught by the gate
#: dogfooding itself. Angle brackets above are load-bearing, not decorative.
#: ``[^\S\r\n]`` is "whitespace but not a line break" — it covers NBSP and the
#: other Unicode spaces a real editor emits, which a literal ``[ \t]`` missed
#: while Semgrep's own ``\s*`` honoured them (Stage-3 doubt review, D12).
SUPPRESSION_RE = re.compile(
    r"nosem(?:grep)?[^\S\r\n]*:[^\S\r\n]*"
    r"([A-Za-z0-9_.\-]+(?:[^\S\r\n]*,[^\S\r\n]*[A-Za-z0-9_.\-]+)*)",
    re.IGNORECASE,
)


def has_comment_marker(prefix: str) -> bool:
    """Whether the text before ``nosemgrep`` opens a comment.

    An all-whitespace (or empty) prefix counts: a suppression may be the first
    token on its line. Both real forms in this repo are covered — a standalone
    comment line (``fr_table_reader.py``) and a trailing one on a code line
    (``test_runner.py``).
    """
    return not prefix.strip() or any(m in prefix for m in COMMENT_MARKERS)


def rules_on_line(line: str) -> list[str]:
    """Every rule id suppressed on one line, in source order."""
    out: list[str] = []
    for match in SUPPRESSION_RE.finditer(line):
        if not has_comment_marker(line[: match.start()]):
            continue
        out.extend(r.strip() for r in match.group(1).split(",") if r.strip())
    return out


def _read_if_relevant(path: Path) -> bytes | None:
    """The file's bytes if it holds the suppression token, else ``None``.

    **Small files are read in one go; only large ones stream.** Measured, and
    the measurement overturned the obvious design: a chunked loop over ALL of
    this repo's 3702 tracked files ran ~1.2 s against ~0.6 s for a single
    ``read_bytes`` each — thousands of small files pay for the extra syscalls
    and the Python-level loop. Streaming still earns its place above the
    threshold, where slurping a tracked model/PDF/video whole just to reject it
    is the memory hazard Stage-3 doubt review (D10) named; such a file is read
    in full only once the token is actually present.

    The overlap keeps a token straddling a chunk boundary from being missed,
    which would be a silent under-count — the unsafe direction.
    """
    if path.stat().st_size <= _CHUNK_BYTES:
        raw = path.read_bytes()
        return raw if _TOKEN_BYTES_RE.search(raw) else None

    tail = b""
    with path.open("rb") as fh:
        while chunk := fh.read(_CHUNK_BYTES):
            if _TOKEN_BYTES_RE.search(tail + chunk):
                return path.read_bytes()
            tail = chunk[-len(SUPPRESSION_TOKEN):]
    return None


def _git_tracked(root: Path) -> list[str] | None:
    """Tracked paths, or ``None`` when this is not a usable git tree."""
    try:
        res = subprocess.run(
            ["git", "ls-files", "-z"],
            cwd=str(root), capture_output=True, timeout=120,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if res.returncode != 0:
        return None
    return [p for p in res.stdout.decode("utf-8", "replace").split("\0") if p]


def _walk_paths(root: Path) -> list[str]:
    """Fallback file set for a non-git tree — sorted, so output is stable."""
    out: list[str] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in EXCLUDED_DIRS)
        for name in sorted(filenames):
            out.append((Path(dirpath) / name).relative_to(root).as_posix())
    return out


def scan(project_root: Path | str) -> dict[str, Any]:
    """Discovery result: ``sites``, the ``mode`` used, and ``unreadable``.

    ``unreadable`` is REPORTED, never silently skipped, and covers both a file
    that raised on read and one above :data:`MAX_BYTES`. Either yields a
    partial count, and a partial count in a security gate is a bypass — the
    caller fails closed on it (external review, GPT #4; the size half was a
    live bypass found in Stage-2 code review). A file that fails to DECODE is a
    different thing: a binary blob cannot hold a source comment, so it is
    skipped without suspicion.

    Everything is sorted, so two runs over the same tree produce byte-identical
    diagnostics regardless of filesystem traversal order.
    """
    root = Path(project_root)
    tracked = _git_tracked(root)
    rels = tracked if tracked is not None else _walk_paths(root)

    sites: dict[str, list[str]] = {}
    unreadable: list[str] = []
    for rel in rels:
        path = root / rel
        if path.suffix.lower() in NON_CODE_SUFFIXES:
            continue
        # Never follow a symlink (it can point outside the tree). NOT scope
        # narrowing: if the target is tracked it is scanned under its own path,
        # and if it is not tracked it is not source-controlled — the property
        # being measured. A gitlink (submodule) is another repo's concern.
        if path.is_symlink() or path.is_dir():
            continue
        if not path.is_file():
            # TRACKED but not present as a regular file: sparse checkout, a
            # worktree `rm` without `git rm`, or a path over Windows MAX_PATH.
            # `is_file()` swallows the OSError, so this used to `continue`
            # silently — a partial count landing as an advisory `shrunk` while
            # the gate stayed green (Stage-3 doubt review, D4).
            unreadable.append(rel)
            continue
        try:
            raw = _read_if_relevant(path)
        except OSError:
            # Reported, never skipped: an unscanned tracked file is a hole in
            # the count, and a hole in a security gate is a bypass.
            unreadable.append(rel)
            continue
        if raw is None:
            continue  # token absent — the overwhelming majority
        # `replace`, NOT a decode-failure skip. The decode is only reached for
        # files the token pre-filter already matched, so skipping here would
        # mean "this file contains a suppression token, and I will now discard
        # it without reporting it" — fail-OPEN, and reachable with any
        # cp1252/latin-1 source file (the Windows editor default). Found in
        # Stage-3 doubt review, which also noted the binary-blob test had been
        # written in a shape that made the hole look benign. Undecodable bytes
        # become U+FFFD and simply fail to match the rule-id character class.
        text = raw.decode("utf-8", "replace")
        for lineno, line in enumerate(text.splitlines(), start=1):
            for rule in rules_on_line(line):
                sites.setdefault(rule, []).append(f"{rel}:{lineno}")

    return {
        "sites": {r: sorted(s) for r, s in sorted(sites.items())},
        "mode": "git" if tracked is not None else "walk",
        "unreadable": sorted(unreadable),
        # How many files were actually examined. Without it no consumer can
        # tell "0 suppressions across 3702 files" from "0 files examined" — and
        # the latter (a fresh `git init`, a sub-directory of a repo holding no
        # tracked files, a scaffold) rendered as a clean bill of health for a
        # tree nothing was read from (Stage-3 doubt review, D3).
        "files_examined": len(rels),
    }


def scan_sites(project_root: Path | str) -> dict[str, list[str]]:
    """``{rule_id: ["path:line", …]}`` for every explicit inline suppression."""
    return scan(project_root)["sites"]
