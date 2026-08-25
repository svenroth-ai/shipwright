"""Fresh-evidence assembly for the cross-layer F11 gate (split from ``_layer_coverage_regen``
to keep both under the 300-LOC cap).

The one job here: turn this run's provenance-verified, emit-side-staged raw runner reports
into the per-test evidence dict the gate reads — built IN-MEMORY, read-only, from ONLY the
provenance-listed files, so a stale/planted index or a repo-root leftover can never credit a
pass (external-review MUST-FIX 2, R3 for evidence).
"""

from __future__ import annotations

import fnmatch
import sys
from pathlib import Path

_SHARED_SCRIPTS = Path(__file__).resolve().parents[2]
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))

from lib import evidence_drop  # noqa: E402

from .git_helpers import _run_git  # noqa: E402


def _read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return None


def _read_json(path: Path):
    import json  # noqa: PLC0415
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError):
        return None


def fresh_evidence(project_root: Path, run_id: str, commit_hash: str, evio) -> dict:
    """This run's per-test evidence, fail-closed on freshness AND built IN-MEMORY from ONLY
    the provenance-listed staged reports (external-review MUST-FIX 2 — R3 for evidence):

    1. the emit-side provenance sidecar's ``run_id`` matches this run, AND
    2. its recorded ``head_commit`` is present AND (when a commit is verified) an ANCESTOR of /
       equal to it — foreign/diverged-branch evidence never credits THIS head (the sidecar is
       stamped at F0.5, before the F6 commit, so it names an ancestor — the executed-passing
       evidence is proven at that ancestor, not re-executed at HEAD; a per-commit clear+stage
       handles within-run multi-commit staleness), THEN
    3. the index is assembled by ``build_index`` over ONLY the reports named in the provenance
       (the exact files the emit-side staged under ``.shipwright/compliance/evidence/``). We do
       NOT call ``refresh_index`` — it also searches repo-ROOT fallbacks (a prior run's
       ``test-results.json`` etc.) that ``clear_evidence_reports`` never purges (false-green)
       AND it WRITES the index (post-F6 tracked-tree drift). This keeps the verifier read-only.

    **Multi-root JUnit (R1a, closes the A6 deferral).** ``reports.junit`` is now a LIST of
    ``{name, base, mtime}`` entries (evidence_drop E-B — one per pytest test-root, ADR-044).
    Each is parsed with its OWN recorded ``base`` so a cross-root id (e.g.
    ``plugins/shipwright-compliance/tests/test_x.py::test_y``) actually joins the manifest.
    An entry missing ``name``/``base`` is rejected (skipped fail-closed), never guessed at
    base="" — that used to silently under-cover every layer outside the ONE root whose report
    happened to reach here first. An entry whose ``name`` is not a bare ``junit-NN.xml``
    basename (external-review finding: a path-separator or absolute value in a malformed/
    tampered ``_provenance.json`` could otherwise read a file OUTSIDE the evidence dir) is
    rejected the same way — only the staged-convention filename is ever read.

    Any proof missing / no staged report → EMPTY evidence → every layer ``MISSING``.
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
    evd = evidence_drop.evidence_dir(project_root)
    staged = prov.get("reports") or {}
    junit_reports: list[tuple[str, str]] = []
    for r in staged.get("junit") or []:
        if not isinstance(r, dict) or "name" not in r or "base" not in r:
            continue  # malformed/missing-base entry — reject, never default to base=""
        name = r["name"]
        if (
            not isinstance(name, str)
            or "/" in name
            or "\\" in name
            or not fnmatch.fnmatchcase(name, evidence_drop.JUNIT_GLOB)
        ):
            continue  # not a bare staged-convention filename — reject, never read outside evd
        text = _read_text(evd / name)
        if text is not None:
            junit_reports.append((text, str(r["base"])))
    playwright = _read_json(evd / evidence_drop.REPORT_NAMES["playwright"]) if "playwright" in staged else None
    vitest = _read_json(evd / evidence_drop.REPORT_NAMES["vitest"]) if "vitest" in staged else None
    if not junit_reports and playwright is None and vitest is None:
        return {}
    try:
        index = evio.build_index(
            junit_reports=junit_reports, playwright=playwright, vitest=vitest, root=Path(project_root),
        )
    except Exception:  # noqa: BLE001 — a broken/invalid report degrades to empty (fail-closed)
        return {}
    results = index.get("results") if isinstance(index, dict) else None
    return results if isinstance(results, dict) else {}


__all__ = ["fresh_evidence"]
