"""Pure render helpers for the SBOM doc: summary table + License-Compliance
verdict. Extracted from ``sbom_generator.py`` (AR-04 / iterate-2026-06-28) so
the honest "count all packages" + "N unresolved - verify" rendering lives in
one cohesive place AND ``sbom_generator.py`` stays under its grandfathered
size ceiling.

**ASCII-only output.** The artifact is consumed by cp1252-default tooling and
``test_doc_is_ascii_even_with_fall2_deps`` asserts
``generate(...).encode("ascii")`` — no emoji / em-dash / middle-dot.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from scripts.lib.collectors import NOT_INSTALLED, UNKNOWN_LICENSE

if TYPE_CHECKING:
    from scripts.lib.collectors import DependencyInfo

_COPYLEFT_TOKENS = ("GPL", "AGPL", "LGPL", "MPL")


def is_copyleft(license_str: str) -> bool:
    """True for GPL/AGPL/LGPL/MPL-family licenses (case-insensitive substring)."""
    upper = license_str.upper()
    return any(token in upper for token in _COPYLEFT_TOKENS)


def license_cell(license_: str) -> str:
    """Inventory-table cell for a license. ``NOT_INSTALLED`` (a scan artifact)
    renders as a neutral ``-``; everything else (a real license or genuine
    ``unknown``) is verbatim. ASCII-only on purpose."""
    return "-" if license_ == NOT_INSTALLED else license_


def _classify(deps: list[DependencyInfo]):
    """Partition deps into (resolved, no_license, not_installed, copyleft)."""
    resolved = [d for d in deps if d.license not in (NOT_INSTALLED, UNKNOWN_LICENSE)]
    no_license = [d for d in deps if d.license == UNKNOWN_LICENSE]
    not_installed = [d for d in deps if d.license == NOT_INSTALLED]
    copyleft = [d for d in deps if is_copyleft(d.license)]
    return resolved, no_license, not_installed, copyleft


def summary_lines(deps: list[DependencyInfo], *, deduped: int = 0) -> list[str]:
    """Summary table that counts ALL packages (AR-04): a ``Licenses resolved
    X / Y`` row plus a ``(deduplicated)`` annotation on the runtime count when
    installed-version dedup merged rows."""
    runtime = [d for d in deps if d.dep_type == "runtime"]
    dev = [d for d in deps if d.dep_type == "dev"]
    resolved, _no_license, _not_installed, copyleft = _classify(deps)
    unique = sorted({d.license for d in resolved})
    # Annotate the runtime line (the primary inventory line) when installed-
    # version dedup merged rows; guard on `runtime` so a 0-runtime repo never
    # renders the absurd "0 (deduplicated)" (code-review nit).
    rt_count = f"{len(runtime)}" + (" (deduplicated)" if deduped and runtime else "")
    return [
        "## Summary",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Runtime dependencies | {rt_count} |",
        f"| Dev dependencies | {len(dev)} |",
        f"| Total packages | {len(deps)} |",
        f"| Licenses resolved | {len(resolved)} / {len(deps)} |",
        f"| Unique licenses | {len(unique)} ({', '.join(unique) if unique else 'none'}) |",
        f"| Copyleft licenses | {len(copyleft)} |",
        "",
    ]


def license_compliance_lines(deps: list[DependencyInfo]) -> list[str]:
    """License-Compliance verdict + the genuine no-declared-license listing.

    Honest accounting (AR-04): a package whose license could not be determined
    — installed-but-no-license (``UNKNOWN_LICENSE``) OR absent from every venv
    (``NOT_INSTALLED``) — is counted as unresolved, and the report NEVER claims
    "all permissively licensed" while any unresolved license remains.
    """
    resolved, no_license, not_installed, copyleft = _classify(deps)
    lines = ["## License Compliance", ""]

    if copyleft:
        lines += [
            "**WARNING: Copyleft licenses detected.** These may restrict commercial use.",
            "",
            "| Package | Version | License | Risk |",
            "|---------|---------|---------|------|",
        ]
        for d in copyleft:
            lines.append(f"| {d.name} | {d.version} | {d.license} | Review required |")
        lines.append("")

    if no_license:
        lines.append(
            f"**{len(no_license)} dependency(ies) declare no license** - see "
            "'Dependencies Without a Declared License' below."
        )
        lines.append("")
    if not_installed:
        lines.append(
            f"**{len(not_installed)} dependency(ies) could not be resolved in this scan** "
            "- license unverified; verify before distribution."
        )
        lines.append("")
    if deps and not copyleft and not no_license and not not_installed:
        lines.append(
            f"No license concerns: all {len(deps)} packages resolved (0 unknown, 0 copyleft)."
        )
        lines.append("")

    if no_license:
        lines += [
            "## Dependencies Without a Declared License",
            "",
            f"**{len(no_license)} package(s)** are installed but ship no license "
            "metadata. Verify their license terms before distribution.",
            "",
            "| Package | Version | Type |",
            "|---------|---------|------|",
        ]
        for d in sorted(no_license, key=lambda x: x.name):
            lines.append(f"| {d.name} | {d.version} | {d.dep_type} |")
        lines.append("")

    return lines
