"""Base+head manifest regeneration for the enforcing F11 traceability gates (R3).

R3 is binding: an enforcing gate must **regenerate** the requirement→test index from the
base and head checkouts and compare — the committed ``test-traceability.json`` is
derived/RTM-visibility only and a hand-edited/stale one can never satisfy the gate. This
module does exactly that: it materialises the merge-base tree and the HEAD-commit
tree (``ls-tree`` + ``cat-file``, so ``export-ignore`` cannot shrink them) into throwaway temp dirs and runs the TT1 ``build_manifest`` collector against each,
so the manifests reflect the real tracked spec + test state at each commit, not whatever
artifact happens to sit in the working tree.

Evidence is the one input that legitimately comes from the working tree, not the archive:
the per-test execution index (``.shipwright/compliance/test-evidence-index.json``) is a
gitignored churn artifact produced by THIS run's runners. It is loaded only when the
emit-side provenance proves it is fresh for this run (``evidence_drop.evidence_is_fresh``);
otherwise the head manifest is built with EMPTY evidence (fail-closed → every layer
``not_run``), so a stale index can never credit a pass.

The collector lives in the compliance plugin. A shared verifier must not eagerly
cross-plugin-import it (ADR-044), so the import is lazy + guarded here and only happens
when a gate actually fires (git available, merge-base resolvable, and — cross-layer only — medium+).
"""

from __future__ import annotations

import importlib
import sys
import tempfile
from pathlib import Path

_SHARED_SCRIPTS = Path(__file__).resolve().parents[2]
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))

from ._layer_coverage_evidence import fresh_evidence  # noqa: E402
from ._tree_materialise import _archive_tree  # noqa: E402,F401  (re-exported: rollout)
from .git_helpers import _run_git, git_context  # noqa: E402

_COLLECTOR: tuple | None = None
_COLLECTOR_MODULES = (
    "scripts.lib.collectors.test_links",
    "scripts.lib.collectors._test_links_io",
    "scripts.lib.collectors._execution_evidence_io",
)


def _load_collector() -> tuple | None:
    """Lazy-import ``(test_links, _test_links_io, _execution_evidence_io)`` from the
    compliance plugin, robust to a pre-bound ``scripts`` package (ADR-044/045).

    A shared verifier must not eagerly cross-plugin-import (ADR-044), and — critically —
    in a combined pytest session ANOTHER plugin's ``scripts`` package may already own
    ``sys.modules['scripts']``, so a naive ``import scripts.lib.collectors`` resolves the
    WRONG plugin and fails (the CI-red/local-green class ADR-045 warns about). We mirror
    ``_lib_loader.load_shared_lib``: save+clear any bound ``scripts``/``scripts.*``, force
    the compliance root to the front of ``sys.path``, import, cache the module OBJECTS,
    then restore the caller's ``sys.modules`` + ``sys.path`` exactly. Production (a clean
    verify subprocess) has no ``scripts`` bound, so this is a plain import there. Returns
    ``None`` on any failure → the gate SKIPs, never crashes finalization.
    """
    global _COLLECTOR
    if _COLLECTOR is not None:
        return _COLLECTOR
    repo_root = Path(__file__).resolve().parents[4]
    plugin_root = repo_root / "plugins" / "shipwright-compliance"
    if not plugin_root.is_dir():
        return None
    plugin_str = str(plugin_root)
    saved = {k: v for k, v in sys.modules.items() if k == "scripts" or k.startswith("scripts.")}
    for key in saved:
        sys.modules.pop(key, None)
    sys.path.insert(0, plugin_str)  # force precedence over any sibling-plugin `scripts`
    try:
        # ``_COLLECTOR_MODULES`` is a frozen module-level tuple of first-party literals: no arg, config or env var steers this import, and semgrep just does not trace the loop variable back to it. That tuple IS the whitelist the rule's own hint asks for.
        # nosemgrep: python.lang.security.audit.non-literal-import.non-literal-import
        mods = tuple(importlib.import_module(name) for name in _COLLECTOR_MODULES)
        _COLLECTOR = mods
        return _COLLECTOR
    except Exception:  # noqa: BLE001 — any import failure degrades to SKIP, never a crash
        return None
    finally:
        try:
            sys.path.remove(plugin_str)  # remove only the copy we inserted at index 0
        except ValueError:
            pass
        for key in [k for k in sys.modules if k == "scripts" or k.startswith("scripts.")]:
            sys.modules.pop(key, None)
        sys.modules.update(saved)  # restore the caller's prior scripts binding, if any


def _rename_map(project_root: Path, base_sha: str, head_sha: str) -> dict[str, str]:
    """old_path → new_path for files git detects as renamed between base and head.

    Feeds the removal gate so a test file renamed + tag-stripped can't read as ``deleted``
    (external-review escape). ``git diff -M --name-status`` emits ``R<score>\\told\\tnew``.
    Best-effort: any git failure yields an empty map (the gate then treats a moved test as
    absent → the pre-existing untagged/orphan checks still catch an in-place strip)."""
    rc, out, _ = _run_git(project_root, "diff", "-M", "--name-status", f"{base_sha}..{head_sha}")
    renames: dict[str, str] = {}
    if rc != 0:
        return renames
    for line in out.splitlines():
        parts = line.split("\t")
        if len(parts) == 3 and parts[0].startswith("R"):
            renames[parts[1].strip()] = parts[2].strip()
    return renames


def _merge_base(project_root: Path, commit: str) -> str:
    """Real branch-base for the iterate branch: merge-base with the default branch.

    Resolves against ``origin/HEAD`` → the branch's own upstream ``@{u}`` → ``origin/main``/
    ``master`` → a LOCAL ``main``/``master``. The ``@{u}`` tracking branch (coordinator FIX 2)
    covers an ADOPTED/brownfield repo whose default is ``develop``/``trunk`` and whose
    ``origin/HEAD`` symbolic-ref is unset — none of the name candidates would match, but the
    upstream does. There is NO ``commit^`` fallback (MUST-FIX 4): the first-parent short-cut
    would compare only the tip commit and miss a removal/change made in an earlier commit — a
    false-green. When NO method resolves a real merge-base we return ``""`` so the enforcing
    gate treats it as an infra failure and BLOCKS (fail-closed), never a narrowed diff."""
    candidates: list[str] = []
    rc, ref, _ = _run_git(project_root, "rev-parse", "--abbrev-ref", "origin/HEAD")
    if rc == 0 and ref.strip().startswith("origin/"):
        candidates.append(ref.strip())
    rc, up, _ = _run_git(project_root, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}")
    if rc == 0 and up.strip() and up.strip() != "@{u}":
        candidates.append(up.strip())  # the branch's tracking upstream (adopted-repo default)
    candidates += ["origin/main", "origin/master", "main", "master"]
    for base_ref in candidates:
        rc, mb, _ = _run_git(project_root, "merge-base", base_ref, commit)
        if rc == 0 and mb.strip() and mb.strip() != commit:
            return mb.strip()
    return ""


def _base_test_dirs(base: dict) -> set[str]:
    """Every dir the BASE manifest found a test in (tagged links + untagged + orphans), as posix
    rel paths. Fed to the HEAD ``_build`` so the gate re-scans wherever the base looked: a config
    narrowed/deleted BETWEEN base and head then can't hide a base-linked test from the removal gate
    (monotonic across the diff). The union floor only guards the default dirs, NOT the config-opted
    plugin/shared roots where this repo's tagged tests live — so without this a head commit that
    both removes an FR and drops ``test_roots`` would false-green."""
    ids: list[str] = [str(t) for t in (base.get("untagged_tests") or [])]
    ids += [str(o.get("test", "")) for o in (base.get("orphans") or []) if isinstance(o, dict)]
    for node in (base.get("requirements") or {}).values():
        if isinstance(node, dict):
            for links in (node.get("tests") or {}).values():
                ids += [str(li.get("path", "")) for li in links if isinstance(li, dict)]
    # A root-level base test (path with no dir) yields parent "." — KEEP it; ``_build`` maps
    # ``root / "."`` back to the project root so it is still re-scanned (never silently dropped).
    return {Path(pth).parent.as_posix() for tid in ids if (pth := tid.split("::", 1)[0])}


def _build(test_links, io, root: Path, evidence: dict, source_commit: str,
           extra_roots: set[str] | None = None, prune_dirs: frozenset[str] | None = None) -> dict:
    # Honour ``traceability.test_roots`` / ``exclude_dirs`` (from ``root`` — the archived base OR
    # head tree, so a base predating the key falls back to defaults) so a layer covered ONLY by a
    # config-opted plugin/shared test is SEEN by the enforcing gate, not just the RTM. Two floors
    # stop the gate from scanning LESS than it must (``configured_test_roots`` REPLACE-semantics
    # would otherwise let a narrowed config hide a removed FR's still-tagged test → false-green):
    # (1) UNION with ``default_test_roots`` — never below the conventional floor; (2) ``extra_roots``
    # (HEAD only) — re-scan every dir the BASE found a test in (see ``_base_test_dirs``), monotonic
    # across the diff. ``generate_file`` keeps pure REPLACE for the RTM; only the gate needs the
    # floors. ``configured_prune_dirs`` still applies so fixture mini-repos' fake ``@FR`` tags stay
    # out of the head-orphan sweep (else a false-RED).
    configured = io.configured_test_roots(root)
    test_roots: list[Path] = list(configured)
    seen = {r.resolve() for r in configured}
    for candidate in list(io.default_test_roots(root)) + [root / rel for rel in sorted(extra_roots or ())]:
        resolved = candidate.resolve()
        if resolved not in seen and candidate.is_dir():
            seen.add(resolved)
            test_roots.append(candidate)
    return test_links.build_manifest(
        root,
        spec_files=io.discover_specs(root),
        test_roots=test_roots,
        prune_dirs=io.configured_prune_dirs(root) if prune_dirs is None else prune_dirs,
        evidence=evidence,
        source_commit=source_commit,
    )


# Process-level caches (SHOULD-FIX 8), keyed by (root, commit); a fresh verify subprocess starts
# empty, tests clear them via ``clear_regen_cache``. The base manifest + rename map are evidence-
# INDEPENDENT, so every gate shares one build; so is an evidence-FREE head (the removal and the
# test-tag gate both read it), so it is built once per run too. Callers must not mutate either.
_BASE_CACHE: dict[tuple[str, str], tuple[dict, dict[str, str], frozenset[str]] | None] = {}
_HEAD_CACHE: dict[tuple[str, str, bool], dict] = {}


def clear_regen_cache() -> None:
    _BASE_CACHE.clear()
    _HEAD_CACHE.clear()


def _base_and_renames(project_root: Path, commit_hash: str, test_links, io):
    key = (str(project_root), commit_hash)
    if key in _BASE_CACHE:
        return _BASE_CACHE[key]
    result = None
    base_sha = _merge_base(project_root, commit_hash)
    if base_sha:
        try:
            with tempfile.TemporaryDirectory(prefix="sw-trace-base-") as bd:
                base_root = Path(bd)
                if _archive_tree(project_root, base_sha, base_root):
                    prune = io.configured_prune_dirs(base_root)
                    base = _build(test_links, io, base_root, {}, base_sha, prune_dirs=prune)
                    result = (base, _rename_map(project_root, base_sha, commit_hash), prune)
        except (OSError, ValueError):
            result = None
    _BASE_CACHE[key] = result
    return result


def regenerate_base_head(
    project_root: Path, commit_hash: str, *, with_evidence: bool, run_id: str = "",
    base_prune_only: bool = False,
) -> tuple[dict, dict, dict[str, str]] | None:
    """Regenerate ``(base_manifest, head_manifest, rename_map)`` from the base + head
    checkouts (R3). The base manifest + rename map are memoized per (root, commit) and shared
    between the two gates (SHOULD-FIX 8); only the HEAD manifest is rebuilt per call so the
    cross-layer gate can fold in this run's evidence (``with_evidence``). ``None`` = an infra gap
    (git unavailable, no base ref, collector or archive failure) the caller renders as an ERROR.

    ``base_prune_only`` (the test-tag gate): the head skips a folder only if BASE and HEAD both exclude it,
    so a change cannot hide its own new tests by growing ``exclude_dirs``. The coverage gates leave it off:
    for them the head's own ``exclude_dirs`` is the fixture fence (a fixture cannot credit a layer)."""
    if not commit_hash or git_context(project_root) != "work_tree":
        return None
    loaded = _load_collector()
    if loaded is None:
        return None
    test_links, io, evio = loaded
    br = _base_and_renames(project_root, commit_hash, test_links, io)
    if br is None:
        return None
    base, rename_map, base_prune = br
    head_key = (str(project_root), commit_hash, base_prune_only)
    if not with_evidence and head_key in _HEAD_CACHE:
        return base, _HEAD_CACHE[head_key], rename_map
    evidence = fresh_evidence(project_root, run_id, commit_hash, evio) if with_evidence else {}
    try:
        with tempfile.TemporaryDirectory(prefix="sw-trace-head-") as hd:
            head_root = Path(hd)
            if not _archive_tree(project_root, commit_hash, head_root):
                return None
            # Re-scan wherever the BASE found tests AND wherever a test git-renamed TO, so a config
            # narrowed/deleted between base and head can't hide a base-linked (or moved) test.
            extra = _base_test_dirs(base) | {Path(p).parent.as_posix() for p in rename_map.values() if p}
            head_prune = io.configured_prune_dirs(head_root)
            head = _build(test_links, io, head_root, evidence, commit_hash, extra_roots=extra,
                          prune_dirs=base_prune & head_prune if base_prune_only else head_prune)
    except (OSError, ValueError):
        return None
    if not with_evidence:
        _HEAD_CACHE[head_key] = head
    return base, head, rename_map


__all__ = ["regenerate_base_head", "_merge_base", "_load_collector"]
