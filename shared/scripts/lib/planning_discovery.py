"""One walk over ``.shipwright/planning/`` — shared by all 15 call sites.

Before this module the repo carried fifteen independent implementations of
"find the split specs under ``.shipwright/planning/``". They did not agree, and
the disagreements were invisible because each lived inside a different
function. The golden corpus (``integration-tests/requirements_corpus/``,
campaign S1) measured them: four raise ``NotADirectoryError`` when ``planning``
is a regular file, three exclude ``iterate/``, three do not sort, five recurse,
and two require ``is_file()`` where the others accept any ``exists()``.

**Parameterized, not opinionated.** Every caller passes the flags that
reproduce what it did before, so the fifteen behaviours survive byte-for-byte
(the corpus asserts it) while living in ONE place. That is the precondition for
converging them — deliberately a separate, per-call-site decision (campaign
S2b) — not a substitute for doing so. Do not "fix" a divergence here; change
the argument at the call site that owns it, under its own review.

**Neutral leaf, on purpose.** Standard library only, no relative imports, never
mutates ``sys.path``. That is what makes it loadable from every plugin realm —
via ``collectors/_lib_loader.load_shared_lib`` (which restores ``sys.path`` on
exit and would strand a path-mutating module), via
``audit/audit_adapters.load_shared_lib``, or by file location under a sentinel
name. Keep it that way (ADR-045).
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

#: The split directory holding per-run iterate specs rather than a split spec.
ITERATE_DIRNAME = "iterate"

#: The filename enumerated under each split.
SPEC_FILENAME = "spec.md"

_GUARDS = ("is_dir", "exists", "none")
_REQUIRES = ("exists", "is_file")


def iter_split_dirs(
    planning: Path | str,
    *,
    guard: str = "is_dir",
    sort: bool = True,
    include_iterate: bool = True,
) -> Iterator[Path]:
    """Yield the split directories directly under ``planning``.

    Non-directory entries are always skipped; every historical caller did that.
    The axes that callers genuinely disagreed on are explicit:

    ``guard``
        What happens when ``planning`` is absent or is not a directory — the
        axis with real teeth, because it decides degrade-vs-raise.

        - ``"is_dir"`` — yield nothing for either case (the majority).
        - ``"exists"`` — yield nothing when absent, but let a ``planning``
          *file* reach ``iterdir()`` and raise ``NotADirectoryError``. Four
          callers do this; it is a latent bug, frozen deliberately.
        - ``"none"`` — no pre-check: absent raises ``FileNotFoundError``, a
          file raises ``NotADirectoryError``.

    ``sort``
        ``True`` sorts by path before filtering — equivalent to the callers
        that filtered first, since all entries share one parent. ``False``
        keeps raw ``iterdir()`` order; three callers are filesystem-order
        dependent and the corpus pins that.

    ``include_iterate``
        ``False`` drops ``iterate/``, which holds per-run iterate specs rather
        than a split spec. Three callers exclude it.

    Yields lazily, so a caller relying on ``any()`` short-circuiting keeps it.
    The ``guard`` exceptions therefore surface on first iteration rather than
    at call time — every caller iterates immediately, so the exception still
    escapes the same public function with the same type.
    """
    if guard not in _GUARDS:
        raise ValueError(f"guard must be one of {_GUARDS}, got {guard!r}")
    planning = Path(planning)

    if guard == "is_dir":
        if not planning.is_dir():
            return
    elif guard == "exists":
        if not planning.exists():
            return

    entries: Iterator[Path] | list[Path] = planning.iterdir()
    if sort:
        entries = sorted(entries)

    for entry in entries:
        if not entry.is_dir():
            continue
        if not include_iterate and entry.name == ITERATE_DIRNAME:
            continue
        yield entry


def iter_spec_files(
    planning: Path | str,
    *,
    guard: str = "is_dir",
    sort: bool = True,
    include_iterate: bool = True,
    recursive: bool = False,
    require: str = "exists",
) -> Iterator[Path]:
    """Yield the ``spec.md`` under each split directory of ``planning``.

    Adds two axes to :func:`iter_split_dirs`:

    ``recursive``
        ``True`` switches to ``rglob``, which descends into nested
        sub-directories AND matches a loose ``spec.md`` sitting directly in
        ``planning``. Five callers do this. ``rglob`` never raises on an absent
        or non-directory ``planning``, so ``guard`` and ``require`` do not
        apply here — a caller needing to tell those cases apart must check
        before calling (``adopt_compliance`` does, for its message).

    ``require``
        ``"exists"`` accepts any entry at that path — including a *directory*
        named ``spec.md``, which then explodes at ``read_text``. ``"is_file"``
        rejects it. Two callers guard properly, the rest do not; the corpus's
        ``spec-dir`` fixture keeps the difference honest.

    Hidden splits are NOT an axis: pathlib's ``glob``/``rglob`` do match a
    leading dot, so recursive callers see ``.hidden-split/`` exactly like the
    ``iterdir`` ones. (Measured against the corpus; older comments in the tree
    claimed the opposite.)

    There is deliberately no ``filename`` parameter. A walk that targets a
    DIFFERENT file is not this function: ``rtm.collect_external_review_states``
    looks for ``external_review_state.json`` and must emit a row for each split
    that LACKS it, so it calls :func:`iter_split_dirs` and tests for the marker
    itself. Adding ``filename=`` here would offer that caller a shape that
    silently drops every missing row. If S2b needs a second target, give it the
    split dirs — not a filename knob.
    """
    if require not in _REQUIRES:
        raise ValueError(f"require must be one of {_REQUIRES}, got {require!r}")
    planning = Path(planning)

    if recursive:
        matches: Iterator[Path] | list[Path] = planning.rglob(SPEC_FILENAME)
        if sort:
            matches = sorted(matches)
        for match in matches:
            if not include_iterate and ITERATE_DIRNAME in match.parent.parts:
                continue
            yield match
        return

    for split_dir in iter_split_dirs(
        planning, guard=guard, sort=sort, include_iterate=include_iterate
    ):
        candidate = split_dir / SPEC_FILENAME
        if candidate.is_file() if require == "is_file" else candidate.exists():
            yield candidate


__all__ = [
    "ITERATE_DIRNAME",
    "SPEC_FILENAME",
    "iter_spec_files",
    "iter_split_dirs",
]
