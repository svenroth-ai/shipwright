"""Per-unit campaign worktree identity + path-safety capability (R2; wired
into the live campaign loop by R5a, "the flip").

Campaign ``campaign-dag-scheduler`` R2
(``.shipwright/planning/iterate/campaigns/campaign-dag-scheduler/sub-iterates/R2-worktree-capability.md``).
Builds (``references/campaign-worktree.md``) the naming, guard-mode identity,
and Windows path-length machinery a per-unit worktree needs. This module is
the single place that
constructs the composite identity string, so every call site (the
``setup_unit_worktree.py`` wrapper, the runner's own isolation guard, a
future R4 reconcile/cleanup) builds the byte-identical value —
``check_worktree_location.py``'s existing ``expected_campaign_slug``
parameter already accepts a composite ``"{slug}--{unit_id}"`` value with ZERO
change to ``lib.worktree_location`` itself (that guard just compares a
string); this is call-site wiring only.

Path form: ``.worktrees/campaign-{slug}--{unit_id}`` for attempt 0, and
``.worktrees/campaign-{slug}--{unit_id}-a{attempt}`` for attempt >= 1 (R4
mints attempts; a future caller passes one rather than string-formatting the
suffix itself).

Both components are validated with the SAME charset
``lib.campaign_graph.id_charset_ok`` already enforces for a sub-iterate id
(R1) — that module's own docstring already reserves a literal ``--`` as
"the campaign-slug/unit-id path separator" for this module's naming, so a
malformed slug or unit id can never forge a second ``--`` and collide two
different ``(slug, unit_id)`` pairs onto the same composite string.

Security hardening (round-6 finding, v5): :func:`resolved_worktree_path`
always RECOMPUTES the expected path from validated ``(slug, unit_id,
attempt)`` — a destructive caller (a future R4 cleanup) must never trust a
path string read back from ``loop_state.json`` instead of recomputing it
here — and refuses (raises) a resolved path landing outside
``<main_root>/.worktrees/``. Reachable only defense-in-depth today (the
charset validation above already makes an escaping id unreachable), but a
destructive operation must never depend on exactly one validation layer.

Total path-length bound (v6, Windows finding): id length alone is bounded
(64 chars, R1's ``_ID_CHARSET_RE``), but the TOTAL resolved path is not — a
real ~35-char campaign slug, plus ``campaign-``, plus a 64-char unit id, plus
an ``-a{n}`` attempt suffix, under this repo's own nested ``.worktrees/``
structure, can reach Windows' ``MAX_PATH`` (260) on the stated primary dev
platform. :func:`path_length_error` checks this BEFORE a caller invokes
``git worktree add`` and names the campaign slug + unit id, rather than
letting git fail mid-checkout with an opaque error. **Checks BOTH the
worktree directory path AND git's own administrative
``<main_root>/.git/worktrees/<name>`` path** (external plan review, GLM,
medium): a real run of this exact wrapper hit ``fatal: '$GIT_DIR' too big``
from git itself at a worktree path comfortably UNDER 260 characters — the
admin path git derives from the same directory basename, nested one level
deeper under ``.git/worktrees/``, is the one that actually overflowed.
Checking only the worktree path (as a first version of this module did) is
insufficient; all three (worktree path, admin directory, and the admin
directory's own longest child file — external plan review, OpenAI, medium)
are computed and the longest one decides the verdict.

**Windows reserved device names rejected** (external plan review, OpenAI,
medium, partial): ``id_charset_ok``'s charset already excludes every
character that would make an id an absolute path, a drive letter, or a
git-ref-illegal string, but ``CON``, ``NUL``, ``COM1`` etc. pass that regex
and are UNUSABLE as a Windows path segment regardless of what governs it —
:func:`composite_worktree_name` also rejects a campaign slug or unit id that
case-insensitively EQUALS a reserved name (not merely contains one).
"""

from __future__ import annotations

import sys
from pathlib import Path

_SCRIPTS_ROOT = Path(__file__).resolve().parents[1]
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from lib.campaign_graph import id_charset_ok  # noqa: E402
from lib.worktree_isolation import WORKTREES_DIRNAME  # noqa: E402

#: Windows' historical MAX_PATH. The wrapper CLI's ``--max-path`` accepts an
#: override for testability only (a deterministic tight bound without
#: needing a real 260+-character filesystem path on every dev machine /
#: CI runner) — the default stays this constant everywhere production code
#: does not pass its own value.
WINDOWS_MAX_PATH = 260

#: Windows reserved device names — illegal as a path SEGMENT on that
#: platform regardless of extension or case. Checked as an exact,
#: case-insensitive match against a whole component, never a substring
#: (``console`` and ``comedy`` are fine; ``CON`` and ``com1`` are not).
_WINDOWS_RESERVED_NAMES = frozenset(
    {"CON", "PRN", "AUX", "NUL"}
    | {f"COM{n}" for n in range(1, 10)}
    | {f"LPT{n}" for n in range(1, 10)}
)


class CampaignUnitWorktreeError(ValueError):
    """Raised for an invalid ``(campaign_slug, unit_id, attempt)`` triple, or
    a resolved path that would escape the approved worktree root."""


def _check_not_reserved(label: str, value: str) -> None:
    if value.upper() in _WINDOWS_RESERVED_NAMES:
        raise CampaignUnitWorktreeError(
            f"{label} {value!r} is a Windows-reserved device name — unusable "
            "as a path segment on that platform")


def composite_worktree_name(campaign_slug: str, unit_id: str, *, attempt: int = 0) -> str:
    """The per-unit worktree DIRECTORY basename — also the value to pass as
    ``check_worktree_location.py --campaign-slug`` and
    ``setup_iterate_worktree.py --slug`` (that script prefixes neither, so
    THIS function's return value already includes the ``campaign-`` prefix
    the rest of the codebase's campaign-worktree convention uses).

    Raises :class:`CampaignUnitWorktreeError` for either component failing
    ``lib.campaign_graph.id_charset_ok``, either component being a Windows
    reserved device name, or a non-int / negative ``attempt`` — never
    silently coerces.
    """
    if not id_charset_ok(campaign_slug):
        raise CampaignUnitWorktreeError(f"invalid campaign slug: {campaign_slug!r}")
    if not id_charset_ok(unit_id):
        raise CampaignUnitWorktreeError(f"invalid unit id: {unit_id!r}")
    _check_not_reserved("campaign slug", campaign_slug)
    _check_not_reserved("unit id", unit_id)
    if isinstance(attempt, bool) or not isinstance(attempt, int) or attempt < 0:
        raise CampaignUnitWorktreeError(
            f"attempt must be a non-negative int, got {attempt!r}")
    suffix = f"-a{attempt}" if attempt >= 1 else ""
    return f"campaign-{campaign_slug}--{unit_id}{suffix}"


def resolved_worktree_path(main_root: Path | str, campaign_slug: str, unit_id: str,
                            *, attempt: int = 0) -> Path:
    """The full per-unit worktree path, ALWAYS recomputed from validated
    inputs (security hardening, v5) — never accept a caller-supplied path
    string for a destructive operation instead of calling this.

    Raises :class:`CampaignUnitWorktreeError` if the composite name is
    invalid (propagated from :func:`composite_worktree_name`), or if the
    resolved path would land outside ``<main_root>/.worktrees/``.
    """
    name = composite_worktree_name(campaign_slug, unit_id, attempt=attempt)
    main_root = Path(main_root).resolve()
    wt_base = (main_root / WORKTREES_DIRNAME).resolve()
    candidate = (wt_base / name).resolve()
    try:
        candidate.relative_to(wt_base)
    except ValueError:
        raise CampaignUnitWorktreeError(
            f"resolved worktree path {candidate} escapes the approved root {wt_base}"
        ) from None
    return candidate


def git_admin_path(main_root: Path | str, campaign_slug: str, unit_id: str, *,
                    attempt: int = 0) -> Path:
    """``<main_root>/.git/worktrees/<name>`` — the administrative directory
    ``git worktree add`` creates for a linked worktree, keyed off the SAME
    directory basename :func:`composite_worktree_name` returns. Not the
    worktree path itself, but a real second place the same basename lands,
    and (per this module's docstring) the one that overflowed first in
    practice."""
    name = composite_worktree_name(campaign_slug, unit_id, attempt=attempt)
    return Path(main_root).resolve() / ".git" / "worktrees" / name


#: The longest-named file `git worktree add` creates INSIDE the admin
#: directory (`git_admin_path`) — `gitdir` (points back at the worktree's own
#: `.git` file). External plan review (OpenAI, medium): a path check that
#: stops at the admin DIRECTORY still misses a CHILD file `git` itself
#: creates one level deeper, which can cross MAX_PATH even when the
#: directory alone does not.
_GIT_ADMIN_CHILD_FILENAME = "gitdir"


def path_length_error(main_root: Path | str, campaign_slug: str, unit_id: str, *,
                       attempt: int = 0, max_path: int = WINDOWS_MAX_PATH) -> str:
    """``""`` if the resolved per-unit worktree path, its git administrative
    directory, AND that directory's longest known child file (see
    :func:`git_admin_path`'s docstring and `_GIT_ADMIN_CHILD_FILENAME`) all
    fit within `max_path` characters, else a message naming the campaign
    slug, unit id, and which of the three paths overflowed (never a bare
    length number with no context) — meant to be checked BEFORE calling
    ``git worktree add``, per this module's docstring.
    """
    admin_path = git_admin_path(main_root, campaign_slug, unit_id, attempt=attempt)
    candidates = (
        ("worktree", resolved_worktree_path(main_root, campaign_slug, unit_id, attempt=attempt)),
        ("git administrative", admin_path),
        ("git administrative child file", admin_path / _GIT_ADMIN_CHILD_FILENAME),
    )
    longest_label, longest_path = max(candidates, key=lambda pair: len(str(pair[1])))
    length = len(str(longest_path))
    if length <= max_path:
        return ""
    return (
        f"resolved {longest_label} path for campaign slug {campaign_slug!r} unit "
        f"{unit_id!r} is {length} characters, exceeding the {max_path}-character "
        f"Windows MAX_PATH bound: {longest_path}"
    )
