"""The one artifact-state stamp — which project state a produced artifact describes.

Card ``trg-4d5b6a56`` (FR-01.10). Two producers shared one defect, fixed once
here: the test-results record was not bound to the code version it describes, and
the compliance evidence documents carried only ``Generated: <timestamp>`` — which
says *when* they were written, not *which state* they describe.

**The identifier is the run id.** ``audit_staleness.find_snapshot_commit`` keys on
a ``Run-ID:`` commit trailer (the SHA is merely what it returns), and a SHA cannot
be the stamp anyway: both producers write *before* their commit exists (F5b
renders, F6 commits), so an artifact cannot name the commit carrying it.
``build_dashboard.md`` already resolves this the same way — see the F11 verifier
``check_build_dashboard_has_run_id``. The commit SHA is supplementary, carried
where a real HEAD exists at production time. Full rationale, the rejected
SHA-primary alternative, and the total resolution contract:
``.shipwright/planning/iterate/2026-07-27-artifact-state-stamping.md``.

**Owns the shape, not the policy.** :class:`SourceState`, the banner form, the JSON
block form, git resolution. Event-log resolution stays with the compliance
collector, which reads the run id off the *same* work event that produces a
document's ``Generated:`` timestamp — a second "latest run" implementation here
would drift and break that guarantee. Nothing here enforces anything; refusing a
mismatched artifact belongs to the sibling cards owning those gates
(``trg-12b4cf3f``, ``trg-a1fd8125``).

**What is code-resolved, exactly.** ``commit`` and ``dirty`` are read from git by
this module — they are the pair that binds a record to a *code version*, which is
the card's actual complaint. ``run_id`` is **declared by the caller**: the run knows
its own id and passes it, exactly as the ``Run-ID:`` commit trailer and
``build_dashboard.md``'s ``| Run:`` marker are also written from the run's own
knowledge. Stated plainly because the campaign's verdict on the neighbouring
``mode: standalone`` field was that "stamping that field is instruction, not code" —
so claiming *every* value here is code-resolved would repeat the very overclaim
this campaign exists to remove. A caller that declares a wrong run id is not
detected; that would need a gate, which is the sibling cards' scope.
"""

from __future__ import annotations

import re
import subprocess
import unicodedata
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Iterable

#: Markdown banner prefix. Sits directly under ``Generated:`` in every compliance
#: evidence document.
BANNER_PREFIX = "Source-State:"

#: Anchored strip regex, mirroring ``audit_staleness.HEADER_STRIP_RE``. Anchored on
#: purpose: an unanchored pattern would delete document body text that merely
#: mentions the token, and would let a body occurrence hide real drift from the
#: Group E snapshot compare.
BANNER_STRIP_RE = re.compile(r"(?m)^Source-State:.*\n?")

#: Top-level key in ``shipwright_test_results.json``.
BLOCK_KEY = "source_state"

#: Rendered when the run id could not be resolved. An explicit token, because a
#: blank ``run=`` reads as a rendering bug rather than as honest absence.
UNKNOWN_RUN = "(unknown)"

#: Commits are abbreviated in operator-facing markdown; the JSON block keeps the
#: full 40-hex value because that is the side a gate compares.
SHORT_SHA_LEN = 12

_GIT_TIMEOUT_SECONDS = 10

#: Unicode categories refused in a run id: control, format, line/paragraph
#: separator. Covers C0/DEL *and* what an ASCII-only check misses (U+0085, U+2028,
#: U+2029) — any of which a downstream renderer may treat as a line break and could
#: therefore use to forge a banner line (external review, security/low).
_REJECTED_CATEGORIES = frozenset({"Cc", "Cf", "Zl", "Zp"})

_BANNER_RUN_RE = re.compile(r"\brun=(\S+)")

#: A commit is 7-40 hex digits and nothing else. Validated on BOTH sides: an
#: unvalidated commit could carry whitespace and inject a forged status token, and a
#: run id that is itself a legal token (``iterate-…-commit=deadbeef``) must not be
#: read back AS a commit. Parsing is token-exact for the same reason.
_COMMIT_RE = re.compile(r"[0-9a-fA-F]{7,40}")
_COMMIT_TOKEN = "commit="

#: ``dirty`` is three-valued and the banner says which: modified, clean, or — by
#: emitting neither token — "git could not answer". Collapsing clean into unknown
#: would lose exactly the distinction this stamp exists to make.
_DIRTY_TOKEN = "uncommitted-changes"
_CLEAN_TOKEN = "clean"


@dataclass(frozen=True)
class SourceState:
    """The state a produced artifact describes.

    ``None`` means *unresolved*, and is rendered/serialised as such — never
    replaced by a plausible-looking default. An artifact that cannot say which
    state it describes must say that, not guess.
    """

    run_id: str | None = None
    commit: str | None = None
    #: Tracked files modified relative to HEAD at production time. ``None`` when
    #: git could not answer. See :func:`resolve_git_state` for the exact meaning.
    dirty: bool | None = None

    def abbreviated(self) -> SourceState:
        """This state with the commit shortened to the banner's width — the exact
        round-trip target for :func:`banner_line` → :func:`parse_banner_line`."""
        if not self.commit:
            return self
        return replace(self, commit=self.commit[:SHORT_SHA_LEN])


def safe_run_id(value: Any) -> str | None:
    """Return ``value`` iff it is a usable single **token**, else ``None``.

    Event logs carry whatever a producer wrote. Surrounding whitespace is trimmed;
    a value is then refused — rather than sanitised into something that looks
    legitimate — if it contains:

    * **any interior whitespace.** The banner is whitespace-delimited, so a run id
      with a space is not one token: ``run one`` renders as ``run=run one`` and
      parses back as ``run``, and a value like ``x clean`` or ``x commit=dead…``
      would inject a *forged status token* into the banner. Rejecting whitespace is
      what makes the round-trip and the token invariant actually true. Canonical run
      ids are slugs, so nothing legitimate is lost.
    * **any control, format, or line/paragraph separator character** — C0/DEL plus
      the Unicode ones a naive ASCII check misses (U+0085, U+2028, U+2029), which
      downstream renderers may treat as line breaks and which could therefore forge
      banner lines.
    * **``{`` or ``}``** — the mark of an **unsubstituted template placeholder**.
      Every caller here is a runtime prompt, so a literal ``{run_id}`` that never got
      substituted is the realistic failure (external review found exactly that in a
      call site). It is otherwise a perfectly well-formed token, so nothing else
      would catch it, and stamping it would mean a record confidently naming a run
      that does not exist — worse than naming none.
    """
    if not isinstance(value, str):
        return None
    trimmed = value.strip()
    if not trimmed or "{" in trimmed or "}" in trimmed:
        return None
    for ch in trimmed:
        if ch.isspace() or unicodedata.category(ch) in _REJECTED_CATEGORIES:
            return None
    return trimmed


def safe_commit(value: Any) -> str | None:
    """Return ``value`` iff it is a plausible commit SHA (7-40 hex), else ``None``."""
    if not isinstance(value, str):
        return None
    trimmed = value.strip()
    return trimmed if _COMMIT_RE.fullmatch(trimmed) else None


# --- markdown banner form --------------------------------------------------


def banner_line(state: SourceState) -> str:
    """Render the single-line markdown banner for ``state``.

    Always exactly one line, always exactly one :data:`BANNER_PREFIX`, whatever
    the input — so a malformed run id cannot forge extra header lines.
    """
    run = safe_run_id(state.run_id) or UNKNOWN_RUN
    parts = [f"run={run}"]
    commit = safe_commit(state.commit)
    if commit:
        parts.append(f"{_COMMIT_TOKEN}{commit[:SHORT_SHA_LEN]}")
    if state.dirty is True:
        parts.append(_DIRTY_TOKEN)
    elif state.dirty is False:
        parts.append(_CLEAN_TOKEN)
    return f"{BANNER_PREFIX} " + " ".join(parts)


def parse_banner_line(text: str) -> SourceState | None:
    """Read the first anchored banner line out of ``text``.

    ``None`` when no banner is present — distinct from a banner that resolved
    nothing (a :class:`SourceState` with ``run_id=None``). ``commit`` returns as
    written, i.e. abbreviated.
    """
    if not isinstance(text, str):
        return None
    match = BANNER_STRIP_RE.search(text)
    if match is None:
        return None
    line = match.group(0)
    run_match = _BANNER_RUN_RE.search(line)
    run = run_match.group(1) if run_match else None
    if run == UNKNOWN_RUN:
        run = None
    # Exact TOKEN match, never a substring: a run id may legitimately contain the
    # word — a SIMPLIFY-mode run is called `...-cleanup` — and a substring test
    # would read `dirty=None` back as `False`, i.e. silently assert "clean" about a
    # tree git was never asked about.
    # Ordered, not a set: `set` iteration is hash-randomised, so a line carrying two
    # commit= tokens parsed differently run to run — and taking the FIRST yielded
    # value could hand back None while a valid token sat later in the line.
    ordered = line.split()
    commit = next(
        (c for c in (safe_commit(tok[len(_COMMIT_TOKEN):])
                     for tok in ordered if tok.startswith(_COMMIT_TOKEN)) if c),
        None,
    )
    tokens = set(ordered)
    if _DIRTY_TOKEN in tokens:
        dirty: bool | None = True
    elif _CLEAN_TOKEN in tokens:
        dirty = False
    else:
        dirty = None
    return SourceState(run_id=safe_run_id(run), commit=commit, dirty=dirty)


def strip_banner(text: str) -> str:
    """Remove every anchored banner line. Used by the Group E snapshot compare."""
    return BANNER_STRIP_RE.sub("", text)


# --- JSON block form -------------------------------------------------------


def to_block(state: SourceState) -> dict[str, Any]:
    """Serialise to the ``source_state`` block. Unresolved fields stay as ``null``
    rather than being omitted — absent must be *visibly* absent."""
    return {
        "run_id": safe_run_id(state.run_id),
        "commit": safe_commit(state.commit),
        # Validated like the other two: a non-bool would serialise as itself and read
        # back as None, so the block would not round-trip (AC6).
        "dirty": state.dirty if isinstance(state.dirty, bool) else None,
    }


def from_block(block: Any) -> SourceState:
    """Read a ``source_state`` block back. Total: any garbage yields an empty state.

    A hand-mangled record must read as "says nothing about its state", never raise
    and never yield a half-trusted value. ``dirty`` is accepted only as a real bool
    — a truthy ``"true"`` is not what the writer emits, so it reads as unresolved.
    """
    if not isinstance(block, dict):
        return SourceState()
    dirty = block.get("dirty")
    return SourceState(
        run_id=safe_run_id(block.get("run_id")),
        commit=safe_commit(block.get("commit")),
        dirty=dirty if isinstance(dirty, bool) else None,
    )


# --- git resolution --------------------------------------------------------


def _git(args: list[str], cwd: Path) -> str | None:
    """Run git with an argument array (never a shell), bounded timeout.

    stdout, or ``None`` on any failure (missing binary, not a repo, timeout,
    non-zero exit). Callers degrade; they never propagate.
    """
    try:
        proc = subprocess.run(
            ["git", "-C", str(cwd), *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=_GIT_TIMEOUT_SECONDS,
            check=False,
            shell=False,
        )
    except (FileNotFoundError, OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout


def _porcelain_paths(line: str) -> Iterable[str]:
    """Path(s) named by one ``git status --porcelain`` line (``R  old -> new``
    counts both sides as touched)."""
    body = line[3:] if len(line) > 3 else ""
    if " -> " in body:
        for half in body.split(" -> ", 1):
            yield half.strip().strip('"')
    elif body:
        yield body.strip().strip('"')


def _repo_relative(root: Path, paths: Iterable[str]) -> set[str]:
    """Re-express ``paths`` relative to the repo root, the way git prints them."""
    top = _git(["rev-parse", "--show-toplevel"], root)
    base = Path(top.strip()) if top and top.strip() else root
    out: set[str] = set()
    for raw in paths:
        candidate = Path(raw)
        if not candidate.is_absolute():
            candidate = root / candidate
        try:
            out.add(candidate.resolve().relative_to(base.resolve()).as_posix())
        except (ValueError, OSError):
            # Outside the repo: cannot be one of git's paths, so nothing to exclude.
            continue
    return out


def resolve_git_state(
    project_root: Path | str,
    *,
    run_id: str | None = None,
    exclude_paths: Iterable[str] = (),
) -> SourceState:
    """Resolve the state of the code at production time.

    ``commit`` is HEAD (full 40-hex), or ``None`` in a non-repo, an empty repo, or
    when git is unavailable. ``dirty`` means **tracked files modified relative to
    HEAD** (``--untracked-files=no``), ``None`` when git could not answer, with two
    deliberate narrowings: untracked files are ignored (a scratch file does not
    change which code ran), and ``exclude_paths`` drops named artifacts — callers
    pass the artifact they are about to stamp, since the stamp runs *after* it is
    written and without the exclusion ``dirty`` would be ``True`` every run.

    ``exclude_paths`` may be absolute or relative to ``project_root``; both are
    re-expressed relative to the **repository root** before matching, because that
    is what ``git status --porcelain`` prints. Without that step an exclusion
    silently fails to match whenever ``project_root`` is a subdirectory of the repo,
    and ``dirty`` degenerates to always-``True`` — the very failure the exclusion
    exists to prevent (external review, correctness/low).
    """
    root = Path(project_root)
    resolved_run = safe_run_id(run_id)

    head = _git(["rev-parse", "HEAD"], root)
    commit = head.strip() if head and head.strip() else None

    status = _git(["status", "--porcelain", "--untracked-files=no"], root)
    if status is None:
        dirty: bool | None = None
    else:
        excluded = _repo_relative(root, exclude_paths)
        dirty = False
        for line in status.splitlines():
            if not line.strip():
                continue
            paths = {p.replace("\\", "/") for p in _porcelain_paths(line)}
            if paths and paths <= excluded:
                continue
            dirty = True
            break

    return SourceState(run_id=resolved_run, commit=commit, dirty=dirty)


__all__ = [
    "BANNER_PREFIX",
    "BANNER_STRIP_RE",
    "BLOCK_KEY",
    "SHORT_SHA_LEN",
    "UNKNOWN_RUN",
    "SourceState",
    "banner_line",
    "from_block",
    "parse_banner_line",
    "resolve_git_state",
    "safe_commit",
    "safe_run_id",
    "strip_banner",
    "to_block",
]
