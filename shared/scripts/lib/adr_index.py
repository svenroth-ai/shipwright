#!/usr/bin/env python3
"""Render and refresh ``.shipwright/planning/adr/INDEX.md``.

``INDEX.md`` is a committed derived view of the ADR spec folder, with two
producers: iterate F3 (``write_decision_drop``, so a row ships in the same
commit as its ADR) and every non-dry-run release pass. Both share the one
writing implementation here, and a drift guard fails when the committed index
falls behind the folder.

A row's label is the ADR file's own first ``#`` heading — retitle the ADR, never
the index. The split shape (pure ``render_adr_index`` + writing
``rebuild_adr_index``) mirrors ``lib/gate_policy.py`` and is what makes a
byte-equality drift guard possible. Living in ``lib/`` keeps the drop PRODUCER
from importing the aggregator that CONSUMES its drops; ``aggregate_decisions``
re-exports ``rebuild_adr_index`` for repos that already import it from there.

Why any of this — the stale-index defect, and why the label source had to change
before the call sites could — is ADR-116.
"""

from __future__ import annotations

import re
from pathlib import Path

from lib.atomic_write import durable_atomic_write
from lib.file_lock import LockTimeout, file_lock

ADR_SPEC_FOLDER = ".shipwright/planning/adr"
ADR_INDEX_FILENAME = "INDEX.md"

#: Path of the regeneration tool, relative to the SHARED ROOT (``shared/`` in
#: this monorepo, the plugin's shared dir in an adopted repo).
REGEN_TOOL_RELPATH = "scripts/tools/rebuild_adr_index.py"

#: The one documented way to refresh the index by hand. Named verbatim in the
#: generated header, the drift-guard failure message, F3.md and
#: docs/hooks-and-pipeline.md.
#:
#: ``{shared_root}`` is deliberately left UNRESOLVED, matching every other
#: runtime-prompt command in the iterate skill. This string is rendered into the
#: committed ``INDEX.md`` of every adopted repo, and an adopted repo has no
#: ``shared/`` directory — a monorepo-relative path baked into that header would
#: be unrunnable everywhere it actually ships. :func:`regen_command_resolved`
#: gives the concrete path when one is genuinely known at runtime.
#:
#: Deliberately NOT ``aggregate_decisions.py``: that would fold and DELETE the
#: caller's decision-drops as a side effect of refreshing an index.
REGEN_COMMAND = f"uv run {{shared_root}}/{REGEN_TOOL_RELPATH} --project-root ."


def regen_command_resolved() -> str:
    """:data:`REGEN_COMMAND` with ``{shared_root}`` filled in from this file.

    Used where the caller is a running process that knows where it lives (the
    F3 warning), so the remedy can be pasted as-is. Never written into the
    committed index — an absolute path is machine-specific.
    """
    shared_root = Path(__file__).resolve().parents[2]
    return REGEN_COMMAND.replace("{shared_root}", shared_root.as_posix())

_ADR_FILENAME_RE = re.compile(r"^(?P<num>\d{3,4})-(?P<slug>.+)\.md$")

# A leading "ADR-054 — " / "ADR 054: " token, in every style the real folder
# uses. ``\b`` after the digits stops "ADR-1040 Notes" being read as ADR-104.
_TITLE_PREFIX_RE = re.compile(
    r"^(?i:adr)[\s\-\u2013\u2014]*(?:\d{3,4}|X{3,4})\b[\s:\u2013\u2014\-]*"
)

# ATX level-1 heading only: "# x" yes, "## x" no. Up to 3 leading spaces per
# CommonMark. A closing run is only a closing run when whitespace precedes it,
# so "# Migrate to C#" keeps its "#" instead of rendering as "Migrate to C".
_H1_RE = re.compile(r"^ {0,3}#(?!#)\s+(?P<title>.+?)(?:\s+#+)?\s*$")

# The WHOLE fence run, not just three characters: CommonMark closes a fence only
# on the same character with a run at least as long as the opener, so a ```` block
# containing a ``` line stays open. Matching only ``` closed it early and promoted
# a heading that was still inside the code block to the ADR title.
_FENCE_RE = re.compile(r"^ {0,3}(?P<fence>`{3,}|~{3,})")

_FREEFORM_SORT_KEY = 10**9


def adr_spec_folder(project_root: Path | str) -> Path:
    """Resolve the ADR spec folder for ``project_root``.

    Always ``project_root``-relative, never worktree-resolved: ``INDEX.md`` and
    the ADR files it lists are TRACKED artifacts that belong to whichever
    checkout is being committed. That is the same asymmetry
    ``aggregate_decisions`` documents for ``decision_log.md`` vs the gitignored
    drop staging dir — and it is what lets the index ship in the very commit
    that adds the ADR.
    """
    return Path(project_root) / ADR_SPEC_FOLDER


def read_adr_title(path: Path) -> str | None:
    """Return an ADR file's own title, or ``None`` to fall back to the slug.

    The title is the first ATX level-1 heading that is **outside** YAML front
    matter and **outside** fenced code blocks — without those exclusions a
    ``# run this script`` comment inside a ```bash fence becomes an ADR title.
    A leading ``ADR-NNN`` token is stripped because the caller renders its own
    ``ADR-NNN — `` prefix from the filename; a heading that is *only* that token
    leaves nothing behind and falls back to the slug.

    **Known limit.** The FILENAME is the identity. If a heading's number
    disagrees with its filename's (``042-foo.md`` headed ``# ADR-137 — Title``),
    the heading's number is stripped and the filename's re-prefixed, so the view
    renders ``ADR-042 — Title`` and the disagreement is invisible here. That was
    equally true of the previous slug-derived labels; reconciling the two is a
    separate drift class, deliberately not handled by this reader.
    """
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        return None

    start = 0
    if lines and lines[0].strip() == "---":
        for idx in range(1, len(lines)):
            if lines[idx].strip() in ("---", "..."):
                start = idx + 1
                break
        else:  # unterminated front matter — treat the whole file as front matter
            return None

    fence: str | None = None
    for line in lines[start:]:
        opened = _FENCE_RE.match(line)
        if fence is not None:
            run = opened.group("fence") if opened else ""
            if run and run[0] == fence[0] and len(run) >= len(fence):
                fence = None
            continue
        if opened:
            fence = opened.group("fence")
            continue
        heading = _H1_RE.match(line)
        if heading:
            return _TITLE_PREFIX_RE.sub("", heading.group("title").strip()).strip() or None
    return None


def _escape_link_text(text: str) -> str:
    """Keep a title's brackets from terminating the markdown link label.

    Backslashes go FIRST. Escaping only the brackets turns a title containing
    ``\\]`` into ``\\\\]`` — markdown reads that as an escaped backslash followed
    by a LIVE ``]``, which closes the label early and lets the rest of the
    heading supply its own link destination.
    """
    return text.replace("\\", "\\\\").replace("[", r"\[").replace("]", r"\]")


def _link_destination(name: str) -> str:
    """Render a filename as a markdown link destination.

    Ordinary ADR slugs pass through untouched (so existing rows stay
    byte-identical); a name containing whitespace or parens would otherwise
    produce a destination that ends at the first ``)``, so those go in the
    CommonMark angle-bracket form instead.
    """
    if not any(ch in name for ch in " ()<>"):
        return name
    return "<" + name.replace("<", "%3C").replace(">", "%3E") + ">"


def _entries(folder: Path) -> list[tuple[int, str, str, str]]:
    """``(sort_key, filename, label, href)`` for every ADR file in ``folder``.

    ``_template-*`` files are scaffolding, not decisions: listing the
    bloat-exception template would render its placeholder heading
    ("Bloat exception — `<path/to/file>` raised to <new>-LOC") as if it were a
    real ADR. The skip is deliberately narrow. An earlier version skipped EVERY
    ``_``-prefixed file, which silently delisted ``_archive-agent-doc-updates.md``
    — real content that the previous index did link.
    """
    rows: list[tuple[int, str, str, str]] = []
    for md in sorted(folder.iterdir()):
        if md.is_symlink() or not md.is_file() or md.suffix.lower() != ".md":
            continue
        if md.name == ADR_INDEX_FILENAME or md.name.startswith("_template-"):
            continue
        title = read_adr_title(md)
        match = _ADR_FILENAME_RE.match(md.name)
        if match:
            sort_key = int(match.group("num"))  # regex guarantees digits
            body = title or match.group("slug").replace("-", " ")
            label = f"ADR-{match.group('num')} \u2014 {_escape_link_text(body)}"
        else:
            sort_key = _FREEFORM_SORT_KEY
            label = _escape_link_text(title or md.stem.replace("-", " "))
        rows.append((sort_key, md.name, label, _link_destination(md.name)))
    # Ties break on FILENAME, never on the label: the two files that share
    # number 097 must not swap places just because someone edited a title.
    rows.sort(key=lambda row: (row[0], row[1]))
    return rows


def render_adr_index(folder: Path) -> str:
    """Render the index for ``folder``. Pure — LF-only, no disk writes.

    LF is the contract: ``core.autocrlf=true`` leaves the working tree CRLF, so
    every comparison happens in LF-space via ``Path.read_text()``.
    """
    lines = [
        "# ADR Spec Folder \u2014 INDEX",
        "",
        "_Auto-generated \u2014 do not edit by hand. Each row's title comes from that",
        "ADR file's own `#` heading, so change the heading, not this file._",
        "",
        f"_Regenerate:_ `{REGEN_COMMAND}`",
        "",
    ]
    rows = _entries(folder)
    if not rows:
        lines += [
            "_No ADR specs yet. Add `.md` files under "
            f"`{ADR_SPEC_FOLDER}/<NNN>-<slug>.md` and regenerate._",
            "",
        ]
    else:
        lines += [f"- [{label}]({href})" for _, _, label, href in rows]
        lines.append("")
    return "\n".join(lines)


def rebuild_adr_index(project_root: Path | str) -> Path | None:
    """Refresh ``INDEX.md`` for ``project_root``. Returns the path, or ``None``.

    A missing ADR folder is a strict no-op: it must never be *created*, or an
    unrelated release pass would mint a new committed artifact in a repo that
    never adopted ADRs.

    Two producers now write this file, so the scan-render-write runs under a
    lock and lands through :func:`durable_atomic_write` — the repo's shared
    tmp+fsync+replace primitive. That is not just deduplication: it writes the
    ``str`` verbatim as UTF-8 (so the LF-only render stays LF on Windows, where
    ``Path.write_text`` would silently emit CRLF into a committed artifact) and
    it retries the rename past a concurrent reader holding the destination open,
    which on Windows otherwise raises ``PermissionError`` and loses the write.

    Raises :class:`LockTimeout` (a ``RuntimeError``, *not* an ``OSError``) if the
    index lock cannot be taken — callers that treat a refresh as best-effort must
    catch both.
    """
    folder = adr_spec_folder(project_root)
    if not folder.is_dir():
        return None
    index_path = folder / ADR_INDEX_FILENAME
    # The lock lives under .shipwright/locks/, NOT beside INDEX.md. `file_lock`
    # deliberately leaves its lock file on disk, and the canonical gitignore
    # whitelists /.shipwright/planning/ wholesale — so a lock inside the ADR
    # folder is untracked-and-not-ignored in an adopted repo, and F6's
    # folder-level `git add` would commit it. `.shipwright/locks/` is the
    # canonical home for transient locks and is ignored everywhere.
    # (No mkdir here — file_lock creates its own parent.)
    lock_path = Path(project_root) / ".shipwright" / "locks" / "adr_index.lock"
    with file_lock(str(lock_path), timeout_seconds=10.0):
        durable_atomic_write(index_path, render_adr_index(folder))
    return index_path


def refresh_best_effort(project_root: Path | str) -> str | None:
    """Refresh the index, returning a warning message instead of raising.

    The best-effort POLICY lives here, next to the producer that knows the
    remedy, rather than being restated at each call site. An index problem must
    never undo work the caller has already committed to (a written
    decision-drop) — but it must never be silent either, or the author gets a
    green local run and a red CI drift guard with no clue what to do.

    ``LockTimeout`` is a ``RuntimeError``, not an ``OSError``: contention with a
    concurrent release pass is precisely the case the lock exists for, so
    catching ``OSError`` alone would let it escape. Anything else still
    propagates — a programming error is not best-effort.

    Returns ``None`` on success, else a ready-to-print warning body.
    """
    try:
        rebuild_adr_index(project_root)
    except (OSError, LockTimeout) as exc:
        return (
            f"refreshing {ADR_SPEC_FOLDER}/{ADR_INDEX_FILENAME} failed: {exc}\n"
            f"         The index is now stale and the drift guard will fail. "
            f"Regenerate it with:\n         {regen_command_resolved()}"
        )
    return None
