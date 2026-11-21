"""The ONE place that knows where Shipwright's tool-owned project files live.

Campaign ``root-files-into-config`` (BRIEF
``.shipwright/planning/campaigns/2026-11-14-root-files-into-shipwright-dir-BRIEF.md``,
sections 4.5-4.7 and 11.7.3). Before this module the names of the root
``shipwright_*`` files were literals scattered over ~350 non-test files; moving
them was therefore unreviewable. R0b centralises them here and changes NOTHING
else: every resolver call returns the CURRENT root name, byte for byte. R1 teaches
the readers a second location, R3 flips the writers, R4 removes the fallback -
each of those is an edit in THIS file plus its guard test, not a repo-wide hunt.

**Import contract.** Stdlib only and no intra-package import, so it loads under any
name: plugin code appends ``shared/scripts/lib`` to ``sys.path`` and does
``import shipwright_paths`` (the ``file_lock`` / ``atomic_write`` precedent -
every plugin has its own ``lib`` package, ADR-045), shared code may use
``lib.shipwright_paths`` or the relative form. Two module objects are harmless:
the registry is immutable data.

**What the API answers** (``root`` is always the project root the caller already
holds; the resolver never walks the filesystem):

- :func:`rel` / :func:`name` - the repo-relative POSIX path of a file today.
- :func:`path` - ``root / rel``.
- :func:`main_path` - the same, resolved at the MAIN repo root (class 8: a worktree
  reads the main tree's ``shipwright_model_config.json``); the caller supplies the
  main root, so this module stays git-free.
- :func:`rel_at` - repo-relative POSIX path **at a given commit**, for the
  historical readers that run ``git show <rev>:<path>`` / ``cat-file`` / ``ls-tree``
  or compare ``git status --porcelain`` output (BRIEF 11.9 items 1 and 6). Before the
  flip it is the root name for every commit; R1 teaches it the flip commit, and those
  readers keep the legacy path for pre-flip commits forever (R4 never removes it).
- :func:`legacy_rel` - always the pre-flip root name: for persisted provenance
  strings and ``git show`` of a base that predates the move.
- :func:`lock_for` - the advisory lock file for a data file, or ``None``. Only
  ``run_config`` and ``ac_registry`` carry a data-file lock today; ``sync_config``
  is written under the EVENTS lock (BRIEF 11.9 item 4). No caller builds a lock path
  itself. R1 turns this into the fixed-order dual lock (BRIEF 4.7.2).
- :func:`names_of` / :func:`rels_of_kind` - the lists other modules used to hand-maintain
  (``CONFIG_MARKERS``, ``CONFIG_FILES``, ``DERIVED_SNAPSHOTS``, ...), generated from the
  registry's KIND column.
"""

from __future__ import annotations

import sys
from collections import namedtuple
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable

# ---- kinds -----------------------------------------------------------------
CONFIG = "config"          # hand- or tool-written settings
BASELINE = "baseline"      # ratchet files: may only improve
REGISTER = "register"      # ledgers / registers owned by a minting tool or by hand
DERIVED = "derived"        # regenerated every run; never migrated as content
MARKER = "marker"          # makes a directory a Shipwright project but is not config
STATE = "state"            # runtime state records
POINTER = "pointer"        # RESERVED: the root stub R3 leaves for old plugins. No file
#                            carries it until R3 decides the format (BRIEF 11.5); the
#                            kind exists now so every consumer is written against it.

KINDS: tuple[str, ...] = (CONFIG, BASELINE, REGISTER, DERIVED, MARKER, STATE, POINTER)

_EVENTS_LOCK = "shipwright_events.jsonl.lock"


FileSpec = namedtuple(
    "FileSpec",
    "key basename kind moves marker main_root retired run_written lock fixed_tmp",
    defaults=(True, False, False, False, False, None, ()),
)
FileSpec.__doc__ = """One registry row.

``moves``: the campaign moves it to ``.shipwright/config/`` (R3). ``marker``: counts as a project
marker (``project_root.CONFIG_MARKERS`` order is registry order). ``main_root``: read from the MAIN
repo root, worktree-aware (BRIEF 11.2 class 8). ``retired``: no producer writes it any more; resolved
at its legacy location only and never listed as a snapshot. ``run_written``: a run WRITES it and
nothing can re-derive it, so the mid-run restore must not reset it (``derived_snapshots``). ``lock``:
the data-file lock name today, relative to the project root. ``fixed_tmp``: fixed-name temp siblings a
writer creates (BRIEF 11.4 / 11.9.4); random ``<name>.<rand>.tmp`` temps come from ``lib.atomic_write``.
"""


def _cfg(key: str, **kw) -> FileSpec:
    return FileSpec(key, f"shipwright_{key}.json", CONFIG, **kw)


#: Registry order is meaningful: it is the order of ``CONFIG_MARKERS`` and of every
#: list generated below.
_SPECS: tuple[FileSpec, ...] = (
    # --- project markers (run_config is the primary; it moves LAST, BRIEF 8.3)
    _cfg("run_config", marker=True, lock="shipwright_run_config.json.lock"),
    FileSpec("project_config", "shipwright_project_config.json", CONFIG, marker=True),
    FileSpec("plan_config", "shipwright_plan_config.json", CONFIG, marker=True),
    FileSpec("build_config", "shipwright_build_config.json", CONFIG, marker=True),
    # the event log stays at the root (operator decision 0.2) but marks a project
    FileSpec("events", "shipwright_events.jsonl", MARKER, moves=False, marker=True),
    # --- other configs
    FileSpec("sync_config", "shipwright_sync_config.json", CONFIG,
             lock=_EVENTS_LOCK, fixed_tmp=("shipwright_sync_config.json.tmp",)),
    FileSpec("test_config", "shipwright_test_config.json", CONFIG),
    FileSpec("iterate_config", "shipwright_iterate_config.json", CONFIG),
    FileSpec("changelog_config", "shipwright_changelog_config.json", CONFIG),
    FileSpec("compliance_config", "shipwright_compliance_config.json", CONFIG,
             fixed_tmp=("shipwright_compliance_config.json.tmp",)),
    FileSpec("security_config", "shipwright_security_config.json", CONFIG),
    FileSpec("model_config", "shipwright_model_config.json", CONFIG, main_root=True),
    FileSpec("design_config", "shipwright_design_config.json", CONFIG),
    FileSpec("deploy_config", "shipwright_deploy_config.json", CONFIG),
    # D2 (operator decision pending): stays at the root, recorded so the sorter and
    # the guard know it
    FileSpec("audit_config", "audit_config.json", CONFIG, moves=False),
    # --- baselines
    FileSpec("bloat_baseline", "shipwright_bloat_baseline.json", BASELINE),
    FileSpec("ac_coverage_baseline", "shipwright_ac_coverage_baseline.json", BASELINE),
    FileSpec("adr_collision_baseline", "shipwright_adr_collision_baseline.json", BASELINE),
    FileSpec("inline_suppressions", "shipwright_inline_suppressions.json", BASELINE),
    FileSpec("known_failures", "shipwright_known_failures.json", BASELINE),
    # --- registers
    FileSpec("ac_registry", "shipwright_ac_registry.json", REGISTER,
             lock="shipwright_ac_registry.json.lock"),
    FileSpec("accepted_risks", "shipwright_accepted_risks.yaml", REGISTER),
    # --- derived
    FileSpec("test_results", "shipwright_test_results.json", DERIVED, run_written=True,
             fixed_tmp=("shipwright_test_results.json.tmp",)),
    FileSpec("audit_report", "shipwright_audit_report.json", DERIVED, moves=False,
             retired=True),
    FileSpec("plan_snapshot", "shipwright_plan_snapshot.json", DERIVED, moves=False,
             retired=True),
    # --- runtime state; D1 (operator decision pending): provisionally stays
    FileSpec("dev_server", "shipwright_dev_server.json", STATE, moves=False),
)

SPECS: dict[str, FileSpec] = {s.key: s for s in _SPECS}
assert len(SPECS) == len(_SPECS), "duplicate resolver key"
_BY_BASENAME: dict[str, FileSpec] = {s.basename: s for s in _SPECS}


def spec(key: str) -> FileSpec:
    try:
        return SPECS[key]
    except KeyError:
        raise KeyError(f"unknown Shipwright file key {key!r}; known: {sorted(SPECS)}") from None


def key_for_basename(basename: str) -> str | None:
    s = _BY_BASENAME.get(basename)
    return s.key if s else None


# ---- single-file API -------------------------------------------------------
def rel(key: str) -> str:
    """Repo-relative POSIX path of *key* in the CURRENT layout (the project root)."""
    return spec(key).basename


def name(key: str) -> str:
    """The bare FILE NAME of *key* (never a path): for ``Path.name`` / basename comparisons."""
    return spec(key).basename


def legacy_rel(key: str) -> str:
    """The pre-flip root name; stable forever (provenance strings, old bases)."""
    return spec(key).basename


def rel_at(key: str, commit: str | None = None) -> str:
    """Repo-relative POSIX path of *key* as it exists at *commit* (``None``: the tree the
    caller is standing in, i.e. the working tree at its current layout).

    For ``git show <rev>:<path>``, ``git cat-file``, ``git ls-tree`` and comparison
    with ``git status --porcelain`` output. Before the flip every commit has the
    root path; ``commit`` is accepted now so call sites are written against the final
    signature (R1 resolves the flip commit here).
    """
    del commit  # R0b: one layout for every commit
    return spec(key).basename


def path(key: str, root: Path | str) -> Path:
    """Absolute path of *key* under the project *root*."""
    return Path(root) / rel(key)


def json_path_or_none(name: str, root: Path | str) -> Path | None:
    """``root / shipwright_<name>.json`` for a config *name* (a registry file named exactly so, or an
    unknown name, whose old construction is kept); ``None`` for a registry file with another name. For a config name taken from a spec's ``field`` string (``run_config.mode``),
    which may name something that is not a project file at all."""
    s = SPECS.get(name)
    if s is not None and s.basename != f"shipwright_{name}.json":
        return None
    # unknown names keep the pre-resolver construction, so the caller's result is unchanged
    return Path(root) / f"shipwright_{name}.json"


def main_path(key: str, project_root: Path | str, main_root: Path | str | None) -> Path:
    """Path of *key* at the MAIN repo root; falls back to *project_root* when the
    caller could not resolve a main root (non-git project, git unavailable)."""
    return Path(main_root or project_root) / rel(key)


def lock_for(key: str, root: Path | str) -> Path | None:
    """Advisory lock file guarding *key*, or ``None`` if it has no data-file lock.

    ``run_config`` and ``ac_registry`` have their own lock; ``sync_config`` is
    serialised by the events lock (it stays at the root with the event log).
    """
    lock = spec(key).lock
    return Path(root) / lock if lock else None


def lock_rel(key: str) -> str | None:
    """Repo-relative name of the lock file guarding *key* (``None``: no data-file lock)."""
    return spec(key).lock


def lock_beside(data_path: Path | str) -> Path:
    """The advisory lock for an EXPLICIT data file (``<file>.lock``, same directory).

    For callers handed an arbitrary path (a ``--registry-file`` argument, the event log
    resolved by ``events_layout``) rather than a project root. R1 turns the registry-backed
    :func:`lock_for` into the dual lock; this helper keeps the legacy ``<file>.lock``
    shape in one place so no caller concatenates ``".lock"`` itself.
    """
    p = Path(data_path)
    return p.with_name(p.name + ".lock")


def family_globs() -> tuple[str, ...]:
    """fnmatch patterns that cover the whole ``shipwright_*`` root-file family
    (``change_type_paths`` sorts them as tooling/infra/compliance, not bookkeeping)."""
    return ("shipwright_*.json", "shipwright_*.yaml")


# ---- generated lists -------------------------------------------------------
def _select(kinds: Iterable[str] | None, *, moves: bool | None, marker: bool | None,
            include_retired: bool) -> list[FileSpec]:
    wanted = None if kinds is None else set(kinds)
    out = []
    for s in _SPECS:
        if wanted is not None and s.kind not in wanted:
            continue
        if moves is not None and s.moves != moves:
            continue
        if marker is not None and s.marker != marker:
            continue
        if s.retired and not include_retired:
            continue
        out.append(s)
    return out


def names_of(kinds: Iterable[str] | None = None, *, moves: bool | None = None,
             marker: bool | None = None, include_retired: bool = False) -> tuple[str, ...]:
    """Current repo-relative POSIX paths of the registry entries matching the filters,
    in registry order."""
    return tuple(s.basename for s in _select(kinds, moves=moves, marker=marker,
                                             include_retired=include_retired))


rels_of_kind = names_of


def keys_of(kinds: Iterable[str] | None = None, *, moves: bool | None = None,
            marker: bool | None = None, include_retired: bool = False) -> tuple[str, ...]:
    return tuple(s.key for s in _select(kinds, moves=moves, marker=marker,
                                        include_retired=include_retired))


def snapshot_paths(kind: str = DERIVED) -> frozenset[str]:
    """Paths of *kind* that must not enter an iterate commit (``DERIVED_SNAPSHOTS`` /
    ``RESTORABLE_SNAPSHOTS`` are generated from this). R1 emits BOTH the legacy and the
    new path for kind ``derived`` until R4 (BRIEF 4.7.6)."""
    return frozenset(names_of((kind,)))


def run_written_paths() -> frozenset[str]:
    """Snapshot paths a run writes and nothing can re-derive (excluded from the mid-run restore)."""
    return frozenset(x.basename for x in _SPECS if x.run_written and not x.retired)


def all_basenames() -> frozenset[str]:
    """Every file name in the registry, retired ones included (guard + sorters)."""
    return frozenset(s.basename for s in _SPECS)


def basename_of(path_like: str | Path) -> str:
    return PurePosixPath(str(path_like).replace("\\", "/")).name


# Best effort at ONE registry object however it was imported: when this file is loaded first as
# ``lib.shipwright_paths`` the bare name aliases it. (A copy bound first under the other name stays
# separate - R1, which adds layout state, must keep patching and reading through one import form.)
_me = sys.modules.get(__name__)  # absent when a loader execs before registering
if _me is not None:
    sys.modules.setdefault("shipwright_paths", _me)
