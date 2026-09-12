"""Snapshot-reading half of the FR-01.02 #5/#10 rollout-transition grace —
split from ``_project_gate_rollout.py`` at the 300-LOC guideline (same
precedent as ``_project_gate_wiring.py``/``_project_gate_manifest.py``).
``_project_gate_rollout.py`` owns resolving WHICH historical commit;
this module owns reading WHAT that commit's ``spec.md`` / project manifest
actually said, and exposes the one entry point
(:func:`build_rollout_snapshot`) the two gate wrappers in
``_project_gate_wiring.py`` call.

**Split identity, not just spec.md content (external plan review, openai,
high).** A split "already empty at rollout" must mean the split was actually
DECLARED at rollout, not merely that *some* file happened to sit at that path
with zero rows — a split directory name reused across an unrelated
manifest revision could otherwise inherit a stranger's grace.
:func:`RolloutSnapshot.declared_split_names` therefore reads the declared
``splits`` list from ``shipwright_project_config.json``/
``shipwright_run_config.json`` AT the resolved rollout commit too
(best-effort, permissively — a malformed or absent manifest at that
historical commit means "not declared", i.e. no grace, never a crash), not
merely the split's ``spec.md`` text.

**Text/count identity, not value superset.** The layer-coverage precedent
(``_layer_coverage_rollout.py``) compares a *value* for superset-ness (an
FR's required layers can only legitimately widen). There is no equivalent
partial order for AC-hygiene text or a split's row count, so
``_project_gate_extras.py``'s comparison (which consumes this module's
output) is exact identity on the PARSED representation the existing gates
already use (``fr_table_reader.read_active_fr_rows`` row count,
``fr_criteria.criteria_for`` criterion text) — never raw file bytes. This
module only supplies the raw historical text; the identity comparison
itself lives in ``_project_gate_extras.py``, alongside the existing
rollout-unaware comparison it extends.
"""

from __future__ import annotations

import json
from pathlib import Path

from . import _project_gate_rollout as _rollout
from ._project_gate_manifest import _is_safe_split_name
from .git_helpers import _run_git

_GIT_TIMEOUT_SECONDS = 30.0

# Keyed by a CONCRETE (project_root, sha, posix_path) triple — never a
# symbolic ref, and never (sha, posix_path) alone: the actual git lookup is
# `_repo_relative_prefix(project_root) + posix_path`, so two nested projects
# in one repo (e.g. `repo/a/` and `repo/b/`) sharing the same relative
# spec.md path against the same resolved rollout SHA would otherwise collide
# on the same cache entry and read each other's historical text (external
# code review, both reviewers, high/medium — the sibling `_MANIFEST_CACHE`
# already included `project_root` in its key; this one didn't, an
# accidental omission rather than a deliberate asymmetry).
_TEXT_CACHE: dict[tuple[str, str, str], str | None] = {}
_MANIFEST_CACHE: dict[tuple[str, str], frozenset[str]] = {}
#: `git show <sha>:<path>` resolves `<path>` relative to the REPO TOPLEVEL,
#: never to `-C <dir>`'s own directory (measured directly: `git -C ./a show
#: <sha>:a/b/f` succeeds, `git -C ./a show <sha>:b/f` fails with "exists, but
#: not" — the exact opposite of `git -C ./a archive`, which archives only the
#: SUBTREE rooted at `./a`). Every path this module receives is already
#: `project_root`-relative (from `_read_spec_texts`), so a `project_root`
#: nested below the actual git toplevel needs the repo-relative PREFIX
#: prepended before it can reach `git show` correctly — internal plan review
#: (opus), medium. Keyed by `project_root` only (not `sha` — the prefix is a
#: property of the WORKING TREE's location, not of any particular commit).
_PREFIX_CACHE: dict[str, str] = {}


def clear_snapshot_cache() -> None:
    _TEXT_CACHE.clear()
    _MANIFEST_CACHE.clear()
    _PREFIX_CACHE.clear()


def _posix(rel_path: str) -> str:
    """``spec_texts`` keys come from ``str(Path.relative_to(...))`` — backslash-
    separated on Windows. ``git show <sha>:<path>`` needs POSIX-style tree
    paths on every platform."""
    return rel_path.replace("\\", "/")


def _is_safe_git_path(rel_path: str) -> bool:
    """Defense in depth: every path reaching this module today already comes
    from ``_read_spec_texts``/``_declared_split_names`` (lexically validated
    by ``_is_safe_split_name`` and resolved against the project root before
    ever being read), but external plan review (both reviewers, low) asked
    for an explicit guard here too rather than relying solely on the
    upstream caller staying correct forever. Rejects anything absolute, any
    ``..`` segment, and anything that could be misread as a git revision
    flag rather than a path."""
    posix = _posix(rel_path)
    if not posix or posix.startswith(("-", "/")):
        return False
    return ".." not in posix.split("/")


def _repo_relative_prefix(project_root: Path) -> str:
    """``project_root``'s own path relative to its git repo's toplevel
    (``""`` in the overwhelmingly common case — a Shipwright project IS its
    own git repo root). Best-effort: any git failure degrades to ``""``
    (no prefix), which only ever makes a nested-project lookup miss — the
    same fail-open direction as every other lookup in this module."""
    if str(project_root) in _PREFIX_CACHE:
        return _PREFIX_CACHE[str(project_root)]
    rc, out, _ = _run_git(project_root, "rev-parse", "--show-prefix",
                          timeout=_GIT_TIMEOUT_SECONDS)
    prefix = out.strip() if rc == 0 else ""
    _PREFIX_CACHE[str(project_root)] = prefix
    return prefix


def _read_at_commit(project_root: Path, sha: str, rel_path: str) -> str | None:
    if not _is_safe_git_path(rel_path):
        return None
    posix_path = _posix(rel_path)
    key = (str(project_root), sha, posix_path)
    if key in _TEXT_CACHE:
        return _TEXT_CACHE[key]
    repo_relative = _repo_relative_prefix(project_root) + posix_path
    rc, out, _ = _run_git(project_root, "show", f"{sha}:{repo_relative}",
                          timeout=_GIT_TIMEOUT_SECONDS)
    result = out if rc == 0 else None
    _TEXT_CACHE[key] = result
    return result


def _parse_declared_split_names(text: str | None) -> frozenset[str] | None:
    """Permissive JSON→names parse for a HISTORICAL manifest snapshot — unlike
    ``_project_gate_manifest._declared_split_names`` (which must fail LOUD on
    the LIVE manifest so a corrupt config cannot silently pass every gate),
    a rollout-snapshot parse failure here can only ever WITHHOLD an optional
    leniency, so it degrades to ``None`` (treated as "nothing declared")
    rather than raising or returning a separate error channel."""
    if text is None:
        return None
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    splits = data.get("splits")
    if not isinstance(splits, list):
        return None
    names = {
        s.get("name") for s in splits
        if isinstance(s, dict) and _is_safe_split_name(s.get("name"))
    }
    return frozenset(names)


def _rollout_declared_split_names(project_root: Path, sha: str) -> frozenset[str]:
    """The split names declared in ``shipwright_project_config.json`` (or,
    as a fallback, ``shipwright_run_config.json``) AT the resolved rollout
    commit — same manifest PRIORITY ``_declared_split_names`` uses for the
    live config: ``shipwright_project_config.json``'s mere EXISTENCE at that
    commit is authoritative, exactly as it is live, so an unparseable or
    ``splits``-less project config at rollout answers "nothing declared"
    (empty set) rather than falling through to ``shipwright_run_config.json``
    (code review, medium — an earlier draft fell through on ANY parse
    failure, indistinguishable from the file being absent; that could let a
    stale ``run_config.json`` split list grant grace the authoritative
    manifest at that same historical commit never declared — the exact
    "stranger's grace" ``split_predates_rollout`` exists to prevent,
    reintroduced one layer up). Never raises; any absence/malformation at
    that historical commit yields an empty set (no grace for any split)."""
    key = (sha, str(project_root))
    if key in _MANIFEST_CACHE:
        return _MANIFEST_CACHE[key]
    primary_text = _read_at_commit(project_root, sha, "shipwright_project_config.json")
    if primary_text is not None:
        result = _parse_declared_split_names(primary_text) or frozenset()
    else:
        fallback_text = _read_at_commit(project_root, sha, "shipwright_run_config.json")
        result = _parse_declared_split_names(fallback_text) or frozenset()
    _MANIFEST_CACHE[key] = result
    return result


class RolloutSnapshot:
    """A resolved rollout-instant snapshot of one project's own git history,
    lazily built once per ``(project_root, commit_hash)`` and reused across
    every hit this call evaluates. ``resolved`` is ``False`` when no rollout
    commit exists (greenfield, shallow clone, git failure) — every lookup
    then answers "not present at rollout" for free, without a git call per
    hit."""

    def __init__(self, project_root: Path, sha: str | None) -> None:
        self._project_root = project_root
        self._sha = sha

    @property
    def resolved(self) -> bool:
        return self._sha is not None

    def spec_text(self, rel_path: str) -> str | None:
        if self._sha is None:
            return None
        return _read_at_commit(self._project_root, self._sha, rel_path)

    def declared_split_names(self) -> frozenset[str]:
        if self._sha is None:
            return frozenset()
        return _rollout_declared_split_names(self._project_root, self._sha)


def build_rollout_snapshot(project_root: Path, commit_hash: str) -> RolloutSnapshot:
    """The single entry point the two `/shipwright-project` gate wrappers
    call — lazily, only once a rollout-unaware first pass already found a
    candidate hit (same laziness `layer_coverage_binding.py` uses for its
    own, more expensive archive-based rollout build). Never raises: any
    failure resolving ``commit_hash`` itself yields an unresolved snapshot
    (every lookup then answers "no grace"), the same fail-open direction as
    every other step in this module family."""
    try:
        head_sha = _rollout.resolve_head_sha(project_root, commit_hash)
        sha = _rollout.cached_rollout_sha(project_root, head_sha) if head_sha else None
    except Exception:  # noqa: BLE001 — best-effort optional grace, never a hard failure
        sha = None
    return RolloutSnapshot(project_root, sha)


__all__ = [
    "RolloutSnapshot",
    "build_rollout_snapshot",
    "clear_snapshot_cache",
]
