"""Base+head manifest regeneration for the enforcing F11 traceability gates (R3).

R3 is binding: an enforcing gate must **regenerate** the requirement→test index from the
base and head checkouts and compare — the committed ``test-traceability.json`` is
derived/RTM-visibility only and a hand-edited/stale one can never satisfy the gate. This
module does exactly that: it ``git archive``\\s the merge-base tree and the HEAD-commit
tree into throwaway temp dirs and runs the TT1 ``build_manifest`` collector against each,
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
when a gate actually fires (medium+ complexity, git available, merge-base resolvable).
"""

from __future__ import annotations

import importlib
import io as _io
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

_SHARED_SCRIPTS = Path(__file__).resolve().parents[2]
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))

from lib import evidence_drop  # noqa: E402

from .git_helpers import _git_available, _run_git  # noqa: E402

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
    rc, out, _ = _run_git(
        project_root, "diff", "-M", "--name-status", f"{base_sha}..{head_sha}",
    )
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

    Resolves against ``origin/HEAD`` → ``origin/main`` → a LOCAL ``main``/``master`` so an
    offline multi-commit branch still gets its true branch point (external-review MUST-FIX —
    the first-parent short-cut would compare only the tip commit and miss a removal/change
    made in an earlier branch commit). ``commit^`` is the last-resort ONLY for a degenerate
    repo with no discoverable default branch (e.g. a single-branch fixture), where it equals
    the base for a single-commit diff."""
    candidates: list[str] = []
    rc, ref, _ = _run_git(project_root, "rev-parse", "--abbrev-ref", "origin/HEAD")
    if rc == 0 and ref.strip().startswith("origin/"):
        candidates.append(ref.strip())
    candidates += ["origin/main", "origin/master", "main", "master"]
    for base_ref in candidates:
        rc, mb, _ = _run_git(project_root, "merge-base", base_ref, commit)
        if rc == 0 and mb.strip() and mb.strip() != commit:
            return mb.strip()
    rc, parent, _ = _run_git(project_root, "rev-parse", f"{commit}^")
    return parent.strip() if rc == 0 and parent.strip() else ""


def _safe_extract(tar: tarfile.TarFile, dest: Path) -> None:
    """Extract with the 3.12 data filter; fall back to a manual traversal guard on 3.11.

    The fallback uses proper path CONTAINMENT (``dest`` is the target or a parent of the
    resolved member), never a string ``startswith`` prefix — that would let a sibling dir
    (``/tmp/foo-evil`` starts with ``/tmp/foo``) slip through (external-review finding).
    The archive source is our own git tree, but the guard is defence-in-depth regardless.
    """
    try:
        tar.extractall(dest, filter="data")  # type: ignore[arg-type]
        return
    except TypeError:
        pass
    dest_r = dest.resolve()
    for member in tar.getmembers():
        # Reject anything but a regular file or directory (external-review finding): a symlink
        # / hardlink / device member could point outside the temp root and the collector would
        # follow it while scanning. Only reg + dir are needed to rebuild the manifest.
        if not (member.isreg() or member.isdir()):
            continue
        target = (dest / member.name).resolve()
        if target == dest_r or dest_r in target.parents:
            tar.extract(member, dest)
        # else: reject path traversal (absolute / .. / sibling) — skip the member


def _archive_tree(project_root: Path, sha: str, dest: Path) -> bool:
    """``git archive`` the tracked tree at ``sha`` into ``dest`` (tracked files only —
    ``.worktrees`` / gitignored churn are excluded). Returns False on any git failure."""
    try:
        proc = subprocess.run(
            ["git", "-C", str(project_root), "archive", "--format=tar", sha],
            capture_output=True, timeout=180,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    if proc.returncode != 0 or not proc.stdout:
        return False
    try:
        with tarfile.open(fileobj=_io.BytesIO(proc.stdout)) as tar:
            _safe_extract(tar, dest)
    except (tarfile.TarError, OSError):
        return False
    return True


def _build(test_links, io, root: Path, evidence: dict, source_commit: str) -> dict:
    return test_links.build_manifest(
        root,
        spec_files=io.discover_specs(root),
        test_roots=io.default_test_roots(root),
        evidence=evidence,
        source_commit=source_commit,
    )


def _fresh_evidence(project_root: Path, run_id: str, commit_hash: str, evio) -> dict:
    """This run's per-test evidence, fail-closed on freshness AND **regenerated** from the
    staged raw reports so a stale/planted index can never credit a pass (external-review
    MUST-FIX — the R3 "regenerate, don't trust" rule applied to evidence, not just manifests):

    1. the emit-side provenance sidecar's ``run_id`` matches this run, AND
    2. the provenance's recorded ``head_commit`` is present AND (when a commit is verified) is
       an ANCESTOR of / equal to it — so foreign/diverged-branch evidence never credits THIS
       head (the sidecar is stamped at F0.5, before the F6 commit, so it names an ancestor),
       THEN
    3. the evidence index is REBUILT from the raw reports the emit-side staged (which it
       cleared the dir before writing) via the TT-EV producer — the verifier does not trust
       the persisted ``test-evidence-index.json`` at all, so a restored/hand-edited index with
       old passing results is overwritten by content actually parsed from this run's reports.

    Any proof missing / no staged reports → EMPTY evidence → every layer ``MISSING``.
    """
    if not evidence_drop.evidence_is_fresh(project_root, run_id):
        return {}
    prov = evidence_drop.read_provenance(project_root) or {}
    prov_head = str(prov.get("head_commit") or "")
    if not prov_head:
        return {}
    if commit_hash:
        rc, _, _ = _run_git(project_root, "merge-base", "--is-ancestor", prov_head, commit_hash)
        if rc != 0:  # not an ancestor (foreign/diverged evidence) → fail-closed
            return {}
    # Regenerate the index from the staged reports (R3). refresh_index reads ONLY the
    # conventional evidence-dir reports (which stage_reports cleared + repopulated this run)
    # and overwrites the index, so its results are provably this run's report content.
    try:
        if evio.refresh_index(project_root) is None:  # no staged reports found
            return {}
    except Exception:  # noqa: BLE001 — a broken producer degrades to empty (fail-closed)
        return {}
    import json  # noqa: PLC0415
    index_path = Path(project_root) / ".shipwright" / "compliance" / "test-evidence-index.json"
    try:
        index = json.loads(index_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError):
        return {}
    results = index.get("results") if isinstance(index, dict) else None
    return results if isinstance(results, dict) else {}


def regenerate_base_head(
    project_root: Path,
    commit_hash: str,
    *,
    with_evidence: bool,
    run_id: str = "",
) -> tuple[dict, dict, dict[str, str]] | None:
    """Regenerate ``(base_manifest, head_manifest, rename_map)`` from the base + head
    checkouts (R3).

    ``with_evidence`` decides whether the HEAD manifest carries this run's execution
    evidence (cross-layer gate needs it; the removal gate does not — linkage is
    evidence-independent). ``rename_map`` (old→new path from ``git diff -M``) lets the
    removal gate follow a renamed test. Returns ``None`` when git is unavailable, no
    merge-base resolves, the collector cannot be loaded, or an archive fails — every such
    case is an infrastructure gap the caller renders as a SKIP, never a silent pass/crash.
    """
    if not commit_hash or not _git_available(project_root):
        return None
    base_sha = _merge_base(project_root, commit_hash)
    if not base_sha:
        return None
    loaded = _load_collector()
    if loaded is None:
        return None
    test_links, io, evio = loaded
    evidence = _fresh_evidence(project_root, run_id, commit_hash, evio) if with_evidence else {}
    try:
        with tempfile.TemporaryDirectory(prefix="sw-trace-base-") as bd, \
                tempfile.TemporaryDirectory(prefix="sw-trace-head-") as hd:
            base_root, head_root = Path(bd), Path(hd)
            if not _archive_tree(project_root, base_sha, base_root):
                return None
            if not _archive_tree(project_root, commit_hash, head_root):
                return None
            base = _build(test_links, io, base_root, {}, base_sha)
            head = _build(test_links, io, head_root, evidence, commit_hash)
    except (OSError, ValueError):
        return None
    return base, head, _rename_map(project_root, base_sha, commit_hash)


__all__ = ["regenerate_base_head", "_merge_base", "_load_collector"]
