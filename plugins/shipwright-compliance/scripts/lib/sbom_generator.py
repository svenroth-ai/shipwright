"""Software Bill of Materials (SBOM) generator.

Produces .shipwright/compliance/sbom.md with all open-source dependencies,
versions, and licenses.

Iterate B.2 (ADR-056) — also acts as a triage producer: emits one
``source="sbom"`` action-unit per workspace/manifest with packages whose
licenses couldn't be resolved (``license == "unknown"``). Auto-resolves
when the workspace re-runs clean. See
``.shipwright/planning/adr/056-sbom-undeclared-triage.md``.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING

from scripts.lib.mermaid import license_pie

if TYPE_CHECKING:
    from scripts.lib.data_collector import ComplianceData, DependencyInfo


_COPYLEFT_LICENSES = {
    "GPL", "GPL-2.0", "GPL-3.0",
    "AGPL", "AGPL-3.0",
    "LGPL", "LGPL-2.1", "LGPL-3.0",
    "MPL-2.0",
}


def generate(data: ComplianceData) -> str:
    """Generate SBOM as Markdown string."""
    deps = data.dependencies

    runtime = [d for d in deps if d.dep_type == "runtime"]
    dev = [d for d in deps if d.dep_type == "dev"]
    copyleft = [d for d in deps if _is_copyleft(d.license)]

    # Collect unique licenses
    unique_licenses = sorted(set(d.license for d in deps)) if deps else []

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

    # License distribution
    lines.extend([
        "## License Distribution",
        "",
        license_pie(deps),
        "",
    ])

    # Runtime dependencies
    if runtime:
        lines.extend([
            "## Runtime Dependencies",
            "",
            "| Package | Version | License |",
            "|---------|---------|---------|",
        ])
        for d in sorted(runtime, key=lambda x: x.name):
            lines.append(f"| {d.name} | {d.version} | {d.license} |")
        lines.append("")

    # Dev dependencies
    if dev:
        lines.extend([
            "## Dev Dependencies",
            "",
            "| Package | Version | License |",
            "|---------|---------|---------|",
        ])
        for d in sorted(dev, key=lambda x: x.name):
            lines.append(f"| {d.name} | {d.version} | {d.license} |")
        lines.append("")

    # License compliance
    lines.extend([
        "## License Compliance",
        "",
    ])

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
    else:
        lines.append("No copyleft licenses detected. All dependencies are permissively licensed or unknown.")
        lines.append("")

    # Unknown licenses
    unknown = [d for d in deps if d.license == "unknown"]
    if unknown:
        lines.extend([
            "## Unknown Licenses",
            "",
            f"**{len(unknown)} packages** have unknown licenses. "
            "Install dependencies (`npm install` / `uv sync`) and regenerate to detect licenses.",
            "",
            "| Package | Version | Type |",
            "|---------|---------|------|",
        ])
        for d in sorted(unknown, key=lambda x: x.name):
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


def emit_undeclared_triage(
    project_root: Path,
    *,
    run_id: str | None = None,
    commit: str | None = None,
) -> dict:
    """Emit ``source="sbom"`` triage items for workspaces with undeclared licenses.

    One item per manifest (ADR-054 D1):
      - ``dedup_key`` = ``"sbom:undeclared:<manifest-rel-path>"``
      - ``severity`` = ``"low"`` (visible but quiet — solo-dev pragmatism)
      - ``kind`` = ``"compliance"``
      - body lists the top-20 offenders + ``+N more`` footer
      - ``launchPayload`` carries the workspace-specific install + regen
        command

    Auto-dismiss: any currently-``triage`` ``source="sbom"`` item whose
    ``dedupKey`` is NOT in this run's set of workspaces-with-undeclared
    is marked ``dismissed`` with ``reason="sbomResolved"``. Previously
    promoted / dismissed items stay terminal (mirrors audit_detector's
    HIGH-2 contract).

    Window-less idempotent dedup (``window_seconds=None``) — the same
    workspace with the same undeclared set is one issue, persistent
    across days until the operator runs ``uv sync`` / ``npm install``.

    Returns ``{"appended": N, "dismissed": N}`` for telemetry. Best-effort:
    per-item exceptions are swallowed so SBOM generation never crashes
    the compliance update pipeline.
    """
    project_root = Path(project_root).resolve()
    append_idempotent, mark_status_fn, read_all_items = _import_triage_api()
    if append_idempotent is None:
        # Reviewer-flagged (OpenAI #10): make the lazy-import fallback
        # observable so operators can tell `no undeclared workspaces`
        # apart from `triage API missing — regression`.
        return {
            "appended": 0,
            "dismissed": 0,
            "error": "triage_api_unavailable",
        }

    from scripts.lib.data_collector import collect_undeclared_by_workspace
    groups = collect_undeclared_by_workspace(project_root)

    current_keys: set[str] = set()
    appended = 0
    errors: list[str] = []
    for group in groups:
        rel = group["manifest_rel_path"]
        manifest_type = group["manifest_type"]
        undeclared = group["undeclared"]
        dedup_key = f"{_TRIAGE_DEDUP_PREFIX}{rel}"
        current_keys.add(dedup_key)

        title = f"SBOM: {len(undeclared)} undeclared license(s) in {rel}"
        detail = _render_detail(undeclared)
        payload = _launch_payload(rel, manifest_type)
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
            # Reviewer-flagged M2: surface emit failures via the
            # returned `error` key so `update_compliance.py` doesn't
            # print a misleading "success" when a per-workspace append
            # crashed. One line per failing workspace.
            errors.append(f"append:{rel}:{type(exc).__name__}")

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
            if not dk.startswith(_TRIAGE_DEDUP_PREFIX):
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

    result: dict = {"appended": appended, "dismissed": dismissed}
    if errors:
        result["error"] = "; ".join(errors)
    return result
