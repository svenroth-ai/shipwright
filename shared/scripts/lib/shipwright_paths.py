"""The ONE place that knows where Shipwright's tool-owned project files live.

Campaign ``root-files-into-config`` (BRIEF
``.shipwright/planning/campaigns/2026-11-14-root-files-into-shipwright-dir-BRIEF.md``,
sections 4.5-4.7, 11.7.3, 12, 14). R0b centralised the root ``shipwright_*`` names here
with NO behaviour change: every call returns the CURRENT root name, byte for byte. R1 teaches
the readers a second location, R3 flips the writers, R4 removes the fallback. Not every step is
an edit here alone: frozen module constants and ``root / rel(...)`` joins elsewhere must first
route through :func:`path` / :func:`all_known_rels` (R1b, BRIEF 12.1).

**Import contract.** Stdlib only, no intra-package import, so it loads under any name: plugins
append ``shared/scripts/lib`` to ``sys.path`` and ``import shipwright_paths`` (their own ``lib``
package must not be shadowed, ADR-045); shared code uses ``lib.shipwright_paths`` or the relative
form. All those names resolve to ONE module object (:func:`_unify`, end of file), so layout state
added by R1 is never split. A hand loader that execs under an alias name must re-read
``sys.modules`` afterwards; the shared object's ``__name__`` is whichever alias loaded it first.

**API** (``root`` is the project root the caller holds; nothing here walks the filesystem or runs
git): names and paths (:func:`rel`, :func:`name`, :func:`path`, :func:`main_path` for the MAIN repo
root, :func:`rel_at` per commit and :func:`legacy_rel` for history, BRIEF 11.9), locks
(:func:`lock_for`; R1 makes it the dual lock of 4.7.2), generated lists (:func:`names_of` & co.)
and every candidate location (:func:`known_rels`, :func:`all_known_rels`; R1c owns their contract).
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
POINTER = "pointer"        # RESERVED: the root stub R3 leaves (format: shipwright_pointer)

KINDS: tuple[str, ...] = (CONFIG, BASELINE, REGISTER, DERIVED, MARKER, STATE, POINTER)

_EVENTS_LOCK = "shipwright_events.jsonl.lock"


FileSpec = namedtuple(
    "FileSpec",
    "key basename kind moves marker main_root retired run_written lock fixed_tmp target",
    defaults=(True, False, False, False, False, None, (), ".shipwright/config"),
)
FileSpec.__doc__ = """One registry row.

``moves``: the campaign moves it to ``.shipwright/config/`` (R3). ``marker``: counts as a project
marker (``project_root.CONFIG_MARKERS`` order is registry order). ``main_root``: read from the MAIN
repo root, worktree-aware (BRIEF 11.2 class 8). ``retired``: no producer writes it any more; resolved
at its legacy location only and never listed as a snapshot. ``run_written``: a run WRITES it and
nothing can re-derive it, so the mid-run restore must not reset it (``derived_snapshots``). ``lock``:
the data-file lock name today, relative to the project root. ``fixed_tmp``: fixed-name temp siblings a
writer creates (BRIEF 11.4 / 11.9.4); random ``<name>.<rand>.tmp`` temps come from ``lib.atomic_write``.
``target``: the directory the file moves to (only read when ``moves``).
"""


def _cfg(key: str, **kw) -> FileSpec:
    return FileSpec(key, f"shipwright_{key}.json", CONFIG, **kw)


#: Registry order is meaningful: it is the order of ``CONFIG_MARKERS`` and every generated list.
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
    # --- runtime state; D1: moves to .shipwright/runtime/ (flag flips in R1c/R3)
    FileSpec("dev_server", "shipwright_dev_server.json", STATE, moves=False,
             target=".shipwright/runtime"),
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
    """Repo-relative POSIX path of *key* at *commit* (``None``: the working tree), for ``git show``,
    ``cat-file``, ``ls-tree`` and ``git status --porcelain`` comparisons. Root for every commit
    before the flip; the signature is final so call sites need no change when R1 resolves it. Pre-flip
    commits keep the legacy path forever (R4 never removes it); 'migrated?' at a commit is decided by
    the NEW path existing, never by the root blob missing - after R3 it is the stub (BRIEF 14.4)."""
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
    """Advisory lock guarding *key*, or ``None``: ``run_config`` and ``ac_registry`` have their own,
    ``sync_config`` is serialised by the events lock (it stays at the root with the event log)."""
    lock = spec(key).lock
    return Path(root) / lock if lock else None


def lock_rel(key: str) -> str | None:
    """Repo-relative name of the lock file guarding *key* (``None``: no data-file lock)."""
    return spec(key).lock


def lock_beside(data_path: Path | str) -> Path:
    """``<file>.lock`` beside an EXPLICIT data file (a ``--registry-file`` argument, the event log
    from ``events_layout``), so no caller concatenates ``".lock"`` itself."""
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
    return [s for s in _SPECS if (wanted is None or s.kind in wanted) and (moves is None or s.moves == moves)
            and (marker is None or s.marker == marker) and (include_retired or not s.retired)]


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


# ---- known locations (R1a; no production caller until R1c) -----------------
def new_rel(key: str) -> str | None:
    """Post-move repo-relative path of *key*; ``None`` for a file that does not move."""
    s = spec(key)
    return f"{s.target}/{s.basename}" if s.moves and not s.retired else None


def known_rels(key: str) -> tuple[str, ...]:
    """Every location *key* may live at, new first: ``(new, legacy)`` or ``(legacy,)``."""
    new = new_rel(key)
    return (new, legacy_rel(key)) if new else (legacy_rel(key),)


def all_known_rels(kinds: Iterable[str] | None = None, *, moves: bool | None = None,
                   marker: bool | None = None, include_retired: bool = False) -> tuple[str, ...]:
    """:func:`known_rels` of every registry entry matching the :func:`names_of` filters, in
    registry order: the source for frozen path sets that must match both layouts."""
    return tuple(r for s in _select(kinds, moves=moves, marker=marker,
                                    include_retired=include_retired) for r in known_rels(s.key))


#: Every name the repo loads this file under (plugins, ``lib``, review_record_tier, shared_lib_loader).
_ALIASES = ("shipwright_paths", "lib.shipwright_paths", "_shipwright_shared_review_lib.shipwright_paths",
            "_shipwright_shared_lib.shipwright_paths", "_shipwright_brief_dir_lib.shipwright_paths")


def _unify() -> None:
    """ONE module object for every name in :data:`_ALIASES` (BRIEF 12.3): an alias load adopts an already
    loaded resolver from the SAME file (bare name first; importlib returns ``sys.modules[name]`` after exec
    and binds it on the parent), and the bare name is registered when absent. ``None`` (a test hiding the
    resolver), a fake, another tree: left alone. Not thread-safe (hooks import single-threaded)."""
    me = sys.modules.get(__name__)
    if me is None or me.__dict__ is not globals() or __name__ not in _ALIASES:
        return  # exec without registering, or a probe under its own name (dotted or not)
    import os.path as _osp  # not pathlib: import must survive a faked os.name (test_dev_server_path_anchors)
    here = _osp.normcase(_osp.realpath(__file__))
    for other in (sys.modules.get(n) for n in _ALIASES):
        same = other is not None and hasattr(other, "SPECS") and getattr(other, "__file__", None)
        if same and other is not me and _osp.normcase(_osp.realpath(other.__file__)) == here:
            sys.modules[__name__] = me = other
            break
    sys.modules.setdefault("shipwright_paths", me)


_unify()
