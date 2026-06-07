"""Software Bill of Materials (SBOM) generator.

Produces .shipwright/compliance/sbom.md with all open-source dependencies,
versions, and licenses.

Iterate B.2 (ADR-056) — also acts as a triage producer: emits one
``source="sbom"`` action-unit per workspace/manifest with packages that are
resolved but declare no license (``license == UNKNOWN_LICENSE``). Packages
merely ``NOT_INSTALLED`` in the scan env are a scan artifact and are NOT
flagged (iterate-2026-06-07). Auto-resolves when the workspace re-runs clean.

Iterate 2026-05-24 (cluster-collapse): when N>=2 workspaces share the
same undeclared-dep set AND same manifest_type, collapse into ONE
action-unit (`sbom:undeclared-cluster:<hash>`) per ADR-057's
launch-surface principle. Per-workspace shape (`sbom:undeclared:<path>`)
preserved for N=1 cases and as a shadow-key in current_keys to shield
legacy items from accidental auto-dismiss.
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from scripts.lib.collectors import NOT_INSTALLED, UNKNOWN_LICENSE
from scripts.lib.mermaid import license_pie

if TYPE_CHECKING:
    from scripts.lib.data_collector import ComplianceData


_COPYLEFT_LICENSES = {
    "GPL", "GPL-2.0", "GPL-3.0",
    "AGPL", "AGPL-3.0",
    "LGPL", "LGPL-2.1", "LGPL-3.0",
    "MPL-2.0",
}


def _license_cell(license_: str) -> str:
    """Inventory-table cell for a license. ``NOT_INSTALLED`` (a scan artifact,
    not a repo property) renders as a neutral ``-`` so it never reads as a
    concern; everything else (real license or genuine ``unknown``) is verbatim.
    ASCII-only on purpose: the artifact is printed by cp1252-default tooling.
    """
    return "-" if license_ == NOT_INSTALLED else license_


def generate(data: ComplianceData) -> str:
    """Generate SBOM as Markdown — answers "is this repo license-sound?".

    Surfaces genuine concerns (copyleft + resolved-but-no-license); stays silent
    about ``NOT_INSTALLED`` deps (a scan-environment artifact): they render as
    ``—`` in the inventory and are excluded from the license count, pie, and the
    compliance verdict.
    """
    deps = data.dependencies

    runtime = [d for d in deps if d.dep_type == "runtime"]
    dev = [d for d in deps if d.dep_type == "dev"]
    copyleft = [d for d in deps if _is_copyleft(d.license)]
    no_license = [d for d in deps if d.license == UNKNOWN_LICENSE]  # Fall 2
    resolved = [d for d in deps if d.license not in (NOT_INSTALLED, UNKNOWN_LICENSE)]

    # Unique licenses = real, resolved licenses only (no sentinels).
    unique_licenses = sorted({d.license for d in resolved})

    lines = [
        "# Software Bill of Materials (SBOM)",
        "",
        f"Generated: {data.timestamp}",
        "",
        "## Summary",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Runtime dependencies | {len(runtime)} |",
        f"| Dev dependencies | {len(dev)} |",
        f"| Total packages | {len(deps)} |",
        f"| Unique licenses | {len(unique_licenses)} ({', '.join(unique_licenses) if unique_licenses else 'none'}) |",
        f"| Copyleft licenses | {len(copyleft)} |",
        "",
    ]

    if not deps:
        lines.append("_No dependency manifests found (package.json, pyproject.toml)._")
        return "\n".join(lines) + "\n"

    # License distribution — resolved licenses only (sentinels are not licenses).
    lines.extend(["## License Distribution", "", license_pie(resolved), ""])

    # Dependency inventory (NOT_INSTALLED → `—`).
    for title, group in (("Runtime Dependencies", runtime), ("Dev Dependencies", dev)):
        if not group:
            continue
        lines.extend([f"## {title}", "", "| Package | Version | License |", "|---------|---------|---------|"])
        for d in sorted(group, key=lambda x: x.name):
            lines.append(f"| {d.name} | {d.version} | {_license_cell(d.license)} |")
        lines.append("")

    # License compliance — a clear verdict for the reader.
    lines.extend(["## License Compliance", ""])
    if copyleft:
        lines.extend([
            "**WARNING: Copyleft licenses detected.** These may restrict commercial use.",
            "",
            "| Package | Version | License | Risk |",
            "|---------|---------|---------|------|",
        ])
        for d in copyleft:
            lines.append(f"| {d.name} | {d.version} | {d.license} | Review required |")
        lines.append("")
    if no_license:
        lines.append(
            f"**{len(no_license)} dependency(ies) declare no license** - see "
            "'Dependencies Without a Declared License' below."
        )
        lines.append("")
    if not copyleft and not no_license:
        lines.append(
            "No license concerns: all resolved dependencies are permissively licensed."
            if resolved else "No dependency licenses were resolved in this scan."
        )
        lines.append("")

    # Genuine no-declared-license (Fall 2) — the reader must verify these.
    if no_license:
        lines.extend([
            "## Dependencies Without a Declared License",
            "",
            f"**{len(no_license)} package(s)** are installed but ship no license "
            "metadata. Verify their license terms before distribution.",
            "",
            "| Package | Version | Type |",
            "|---------|---------|------|",
        ])
        for d in sorted(no_license, key=lambda x: x.name):
            lines.append(f"| {d.name} | {d.version} | {d.dep_type} |")
        lines.append("")

    return "\n".join(lines) + "\n"


COMPLIANCE_DIR = ".shipwright/compliance"
LEGACY_COMPLIANCE_DIRNAME = "compliance"


def generate_file(project_root: Path, data: ComplianceData | None = None) -> Path:
    """Generate SBOM and write to .shipwright/compliance/sbom.md."""
    if data is None:
        from scripts.lib.data_collector import collect_all
        data = collect_all(project_root)

    output_dir = project_root / COMPLIANCE_DIR
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "sbom.md"
    output_path.write_text(generate(data), encoding="utf-8")
    return output_path


def _is_copyleft(license_str: str) -> bool:
    """Check if a license is copyleft."""
    upper = license_str.upper()
    return any(cl in upper for cl in ("GPL", "AGPL", "LGPL", "MPL"))


# ---------------------------------------------------------------------------
# Triage producer (Iterate B.2 / ADR-056)
# ---------------------------------------------------------------------------

# Cap surfaced to operators in the triage body. Top-N + "+N more" footer
# protects the inbox from a pathological 5k-dep monorepo (mirrors the
# Top-10 cap used by phase-quality + audit producers).
_UNDECLARED_TOP_N = 20

_TRIAGE_SOURCE = "sbom"
_TRIAGE_DEDUP_PREFIX = "sbom:undeclared:"
_TRIAGE_CLUSTER_PREFIX = "sbom:undeclared-cluster:"
# Cluster-collapse threshold: bucket workspaces that share the same
# (undeclared-set, manifest_type) signature; emit one action-unit per
# bucket when len(members) >= _CLUSTER_MIN_MEMBERS. Below = per-workspace.
_CLUSTER_MIN_MEMBERS = 2


def _import_triage_api():
    """Lazy import of the triage helpers (mirrors audit_detector pattern).

    Returns ``(append_idempotent, mark_status, read_all_items)`` on
    success or ``(None, None, None)`` if ``shared/scripts/`` isn't on
    ``sys.path`` (e.g. in a minimal CI env without the monorepo layout).
    """
    shared_scripts = Path(__file__).resolve().parents[4] / "shared" / "scripts"
    if str(shared_scripts) not in sys.path:
        sys.path.insert(0, str(shared_scripts))
    try:
        from triage import (  # noqa: PLC0415
            append_triage_item_idempotent,
            mark_status,
            read_all_items,
        )
        return append_triage_item_idempotent, mark_status, read_all_items
    except ImportError:
        return None, None, None


def _shell_quote_workspace(workspace: str) -> str:
    """Single-quote a workspace path for safe shell paste.

    Reviewer-flagged hardening (Gemini #3 / OpenAI #5): even though the
    payload is operator-facing copy-paste, repo paths can contain spaces
    or shell metacharacters (`my dir`, `foo;bar`) that would silently
    misexecute. POSIX single-quoting is the safest form because nothing
    inside is expanded; the only escape needed is for an embedded `'`,
    which we render as `'\\''` (close-quote + escaped quote +
    open-quote).
    """
    return "'" + workspace.replace("'", "'\\''") + "'"


def _launch_payload(manifest_rel_path: str, manifest_type: str) -> str:
    """Render the workspace-specific ``cd && install && regenerate`` block.

    Operator copies the fence content into a new Claude session; the
    aggregator wraps the text in a ```text fence (see
    ``shared/scripts/tools/aggregate_triage.py:_render_launch_payload``).

    For root manifests (``manifest_rel_path == "package.json"`` or
    ``"pyproject.toml"``) the ``cd`` step is omitted — the operator is
    already at the right place. The regenerate step is always emitted
    after the install completes so the triage item auto-resolves.

    Commands are chained with ``&&`` so a failing ``cd`` short-circuits
    the install (reviewer-flagged H1: prevents `npm install` from
    silently running in the repo root when the workspace dir is gone).
    The workspace path is single-quoted via ``_shell_quote_workspace``
    against shell-metacharacter injection.
    """
    workspace = "."
    parent = Path(manifest_rel_path).parent
    if parent != Path(""):
        workspace = parent.as_posix()

    install_cmd = "npm install" if manifest_type == "npm" else "uv sync"
    regen_cmd = (
        "uv run plugins/shipwright-compliance/scripts/tools/update_compliance.py"
        " --project-root . --phase iterate"
    )
    if workspace == ".":
        return f"{install_cmd} \\\n  && {regen_cmd}"
    quoted = _shell_quote_workspace(workspace)
    return (
        f"cd {quoted} \\\n"
        f"  && {install_cmd} \\\n"
        f"  && cd - \\\n"
        f"  && {regen_cmd}"
    )


def _render_detail(undeclared: list[dict]) -> str:
    """Render the body listing top-N undeclared packages + `+N more` footer.

    Sorted by ``(name, version)`` for deterministic output across runs +
    platforms (reviewer-flagged: same name with different versions
    in one manifest must produce a stable diff).
    """
    ordered = sorted(undeclared, key=lambda d: (d["name"], d["version"]))
    shown = ordered[:_UNDECLARED_TOP_N]
    remaining = len(ordered) - len(shown)
    bullets = ", ".join(f"{d['name']}@{d['version']}" for d in shown)
    footer = f" (+{remaining} more)" if remaining > 0 else ""
    return (
        f"{len(ordered)} package(s) without a resolvable license. "
        f"Top {len(shown)}: {bullets}{footer}"
    )


def _cluster_signature(undeclared: list[dict]) -> tuple[str, ...]:
    """Sorted, de-duplicated tuple of undeclared dep names.

    De-dup via set (external-review OpenAI #5): duplicate name entries
    in the input must NOT produce different signatures.
    """
    return tuple(sorted({d["name"] for d in undeclared}))


def _cluster_dedup_key(
    signature: tuple[str, ...], manifest_type: str
) -> str:
    """Stable cluster dedup key = the ``(signature, manifest_type)`` pair
    ONLY, **not** the member list (sub-iterate A; supersedes the
    membership-encoding of external-review OpenAI #2/#3).

    Identity is decoupled from membership: drift while >=2 members keep
    the signature reuses the SAME id (no churn, dismissed pile stops
    growing — AC-4); the bucket dismisses only when its last member
    resolves. ``manifest_type`` is folded in so npm/python clusters that
    share a signature don't collide (AC-8). Body re-render under drift is
    deferred (append-only store) — see campaign A spec + trg-9403a648.
    """
    components = manifest_type + "\n--sig--\n" + "|".join(signature)
    h = hashlib.sha256(components.encode("utf-8")).hexdigest()[:12]
    return f"{_TRIAGE_CLUSTER_PREFIX}{h}"


def _cluster_install_command(manifest_type: str) -> str:
    """Per-manifest-type install command (external-review OpenAI #6:
    explicit branching, no silent default).
    """
    if manifest_type == "npm":
        return "npm install"
    if manifest_type == "python":
        return "uv sync --extra dev"
    raise ValueError(
        f"unsupported manifest_type for cluster launch payload: {manifest_type!r}"
    )


def _cluster_regen_command() -> str:
    return (
        "uv run plugins/shipwright-compliance/scripts/tools/update_compliance.py"
        " --project-root . --phase iterate"
    )


def _cluster_launch_payload(
    workspaces: list[str], manifest_type: str
) -> str:
    """Bash for-loop that installs each workspace then regenerates compliance.

    Workspace paths derived from manifest paths' parents — single-quoted
    via _shell_quote_workspace (mirrors B.2 hardening). Workspaces sorted
    alphabetically for diff-stable output (AC-4).
    """
    install_cmd = _cluster_install_command(manifest_type)
    regen_cmd = _cluster_regen_command()

    def _workspace_of(manifest_rel: str) -> str:
        parent = Path(manifest_rel).parent
        return "." if parent == Path("") else parent.as_posix()

    ws_paths = sorted({_workspace_of(m) for m in workspaces})
    quoted = " ".join(_shell_quote_workspace(w) for w in ws_paths)
    return (
        f"for d in {quoted} ; do \\\n"
        f"  ( cd \"$d\" && {install_cmd} ) || exit 1 ;\\\n"
        f"done \\\n"
        f"  && {regen_cmd}"
    )


def _cluster_title(members: list[dict], signature: tuple[str, ...]) -> str:
    # Wording per external-review OpenAI #10: undeclared deps, not licenses.
    return (
        f"SBOM: {len(members)} workspaces missing license metadata "
        f"for {len(signature)} shared package(s)"
    )


def _cluster_detail(
    members: list[dict], signature: tuple[str, ...]
) -> str:
    shown_pkgs = list(signature)[:_UNDECLARED_TOP_N]
    pkgs_str = ", ".join(shown_pkgs)
    pkgs_more = (
        f" (+{len(signature) - len(shown_pkgs)} more)"
        if len(signature) > len(shown_pkgs) else ""
    )
    ws_paths = sorted(m["manifest_rel_path"] for m in members)
    shown_ws = ws_paths[:_UNDECLARED_TOP_N]
    ws_str = ", ".join(shown_ws)
    ws_more = (
        f" (+{len(ws_paths) - len(shown_ws)} more)"
        if len(ws_paths) > len(shown_ws) else ""
    )
    return (
        f"Common undeclared ({len(signature)}): {pkgs_str}{pkgs_more}\n"
        f"Workspaces ({len(members)}): {ws_str}{ws_more}"
    )


def emit_undeclared_triage(
    project_root: Path,
    *,
    run_id: str | None = None,
    commit: str | None = None,
) -> dict:
    """Emit ``source="sbom"`` triage items for workspaces with undeclared licenses.

    Two action-unit shapes (cluster-collapse iterate, ADR-057):

    - **Per-workspace** (``sbom:undeclared:<manifest-rel-path>``): used
      when a workspace's undeclared signature is unique among the run's
      workspaces (bucket of size 1).
    - **Cluster** (``sbom:undeclared-cluster:<sha256-12>``): used when
      N>=2 workspaces share the same (undeclared-set, manifest_type)
      signature. Dedup key = (signature, manifest_type) pair ONLY
      (sub-iterate A) so membership drift reuses the SAME id (no churn);
      the bucket dismisses only when its last member resolves.

    Auto-dismiss: any currently-``triage`` ``source="sbom"`` item whose
    ``dedupKey`` is NOT in this run's ``current_keys`` is marked
    ``dismissed`` with ``reason="sbomResolved"``. ``current_keys``
    includes:

      1. Every key actually appended this run (cluster + per-workspace)
      2. Shadow per-workspace keys for every cluster member — shields
         legacy per-workspace items from accidental dismiss when a
         workspace joins a cluster (external-review HIGH: OpenAI #1 /
         Gemini #1; preserves AC-7 back-compat).

    Previously promoted / dismissed items stay terminal.

    Window-less idempotent dedup (``window_seconds=None``).

    Returns ``{"appended": N, "dismissed": M, "clusters": C}`` for
    telemetry. The ``clusters`` field (AC-10) is additive — pre-existing
    callers reading ``appended`` / ``dismissed`` are unaffected.
    Best-effort: per-item exceptions are swallowed so SBOM generation
    never crashes the compliance update pipeline.
    """
    project_root = Path(project_root).resolve()
    append_idempotent, mark_status_fn, read_all_items = _import_triage_api()
    if append_idempotent is None:
        return {
            "appended": 0,
            "dismissed": 0,
            "clusters": 0,
            "error": "triage_api_unavailable",
        }

    from scripts.lib.data_collector import collect_undeclared_by_workspace
    groups = collect_undeclared_by_workspace(project_root)

    # Bucket groups by (signature, manifest_type). Same signature with
    # different manifest_type CANNOT cluster (AC-8) — different install
    # command, different launch payload.
    from collections import defaultdict
    buckets: dict[tuple[tuple[str, ...], str], list[dict]] = defaultdict(list)
    for group in groups:
        sig = _cluster_signature(group["undeclared"])
        mt = group["manifest_type"]
        buckets[(sig, mt)].append(group)

    current_keys: set[str] = set()
    appended = 0
    clusters_emitted = 0
    errors: list[str] = []

    def _emit_per_workspace(group: dict, mt: str) -> None:
        """Append one per-workspace item for ``group``. Updates ``appended``
        and ``current_keys`` in enclosing scope; on failure records to
        ``errors``.
        """
        nonlocal appended
        rel = group["manifest_rel_path"]
        undeclared = group["undeclared"]
        dedup_key = f"{_TRIAGE_DEDUP_PREFIX}{rel}"
        current_keys.add(dedup_key)
        title = f"SBOM: {len(undeclared)} undeclared license(s) in {rel}"
        detail = _render_detail(undeclared)
        try:
            payload = _launch_payload(rel, mt)
        except Exception as exc:  # noqa: BLE001
            # _launch_payload doesn't currently raise but be defensive
            # so the per-workspace path stays alive for unknown types.
            errors.append(f"per_ws_payload:{rel}:{type(exc).__name__}")
            return
        try:
            new_id = append_idempotent(
                project_root,
                source=_TRIAGE_SOURCE,
                severity="low",
                kind="compliance",
                title=title[:160],
                detail=detail,
                dedup_key=dedup_key,
                run_id=run_id,
                commit=commit,
                match_commit=False,
                window_seconds=None,
                launch_payload=payload,
            )
            if new_id is not None:
                appended += 1
        except Exception as exc:  # noqa: BLE001
            errors.append(f"append:{rel}:{type(exc).__name__}")

    for (signature, manifest_type), members in buckets.items():
        if len(members) < _CLUSTER_MIN_MEMBERS:
            _emit_per_workspace(members[0], manifest_type)
            continue

        # Cluster path (N>=2 members with shared signature + type).
        member_paths = [m["manifest_rel_path"] for m in members]
        try:
            payload = _cluster_launch_payload(member_paths, manifest_type)
        except ValueError as exc:
            # Code-review M1: unsupported manifest_type for cluster
            # launch-payload MUST fall back to per-workspace emit so
            # the workspaces don't orphan without any triage item.
            errors.append(f"cluster_payload:{manifest_type}:{exc}")
            for member in members:
                _emit_per_workspace(member, manifest_type)
            continue

        dedup_key = _cluster_dedup_key(signature, manifest_type)
        current_keys.add(dedup_key)
        # Shadow per-workspace keys (AC-7 back-compat): shield any
        # pre-existing per-workspace items for these workspaces
        # from being auto-dismissed by the resolve loop below.
        for m_path in member_paths:
            current_keys.add(f"{_TRIAGE_DEDUP_PREFIX}{m_path}")

        title = _cluster_title(members, signature)
        detail = _cluster_detail(members, signature)
        try:
            new_id = append_idempotent(
                project_root,
                source=_TRIAGE_SOURCE,
                severity="low",
                kind="compliance",
                title=title[:160],
                detail=detail,
                dedup_key=dedup_key,
                run_id=run_id,
                commit=commit,
                match_commit=False,
                window_seconds=None,
                launch_payload=payload,
            )
            if new_id is not None:
                appended += 1
                clusters_emitted += 1
        except Exception as exc:  # noqa: BLE001
            errors.append(
                f"append_cluster:{dedup_key}:{type(exc).__name__}"
            )

    dismissed = 0
    try:
        for item in read_all_items(project_root):
            if item.get("source") != _TRIAGE_SOURCE:
                continue
            if item.get("status") != "triage":
                continue
            dk = item.get("dedupKey")
            if not isinstance(dk, str):
                continue
            # Dismiss only items in either of our two shape namespaces.
            if not (
                dk.startswith(_TRIAGE_DEDUP_PREFIX)
                or dk.startswith(_TRIAGE_CLUSTER_PREFIX)
            ):
                continue
            if dk in current_keys:
                continue
            try:
                mark_status_fn(
                    project_root,
                    item["id"],
                    new_status="dismissed",
                    by="sbomGenerator",
                    reason="sbomResolved",
                )
                dismissed += 1
            except Exception as exc:  # noqa: BLE001
                errors.append(f"dismiss:{item.get('id', '?')}:{type(exc).__name__}")
    except Exception as exc:  # noqa: BLE001
        errors.append(f"read_all:{type(exc).__name__}")

    result: dict = {
        "appended": appended,
        "dismissed": dismissed,
        "clusters": clusters_emitted,
    }
    if errors:
        result["error"] = "; ".join(errors)
    return result
