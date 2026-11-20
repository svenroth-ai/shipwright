"""New-dependency detection for the prompt-injection scanner.

Moved out of ``prompt_injection_scan.py`` unchanged in behaviour (that file sits
at its bloat-baseline ceiling); the scanner keeps thin wrappers so the public
``scan_dependency_file`` / ``extract_dependency_names`` names still resolve.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


def scan_dependency_file(
    path: Path,
    rel_path: str,
    baseline_deps: set[str] | None,
    make_finding,
) -> list[dict[str, Any]]:
    """Flag new dependencies for manual review.

    Without a baseline, we cannot know what's new — so we only flag if
    baseline_deps is provided (diff mode).
    """
    if baseline_deps is None:
        return []

    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []

    findings: list[dict[str, Any]] = []
    current_deps = extract_dependency_names(text, path.name)
    new_deps = current_deps - baseline_deps

    for dep in sorted(new_deps):
        findings.append(make_finding(
            severity="info",
            rule="NEW_DEPENDENCY",
            description=(
                f"New dependency '{dep}' added to {path.name}. "
                f"New dependencies should be reviewed for maintainer "
                f"reputation, download count, and known security issues."
            ),
            affected_file=rel_path,
            affected_line=None,
            remediation_class="needs-review",
            remediation_hint=(
                f"Verify '{dep}' is from a trusted maintainer and has no "
                f"known vulnerabilities (Snyk Advisor, deps.dev)."
            ),
        ))

    return findings


def extract_dependency_names(text: str, filename: str) -> set[str]:
    """Extract dependency package names from a dep file.

    Lightweight — doesn't fully parse, just pulls names.
    """
    names: set[str] = set()
    if filename == "pyproject.toml":
        # Match lines like:  "foo>=1.0" or  'foo==1.0',
        for match in re.finditer(r'["\']([a-zA-Z0-9_\-]+)[>=<~!\s]', text):
            names.add(match.group(1).lower())
    elif filename == "package.json":
        try:
            data = json.loads(text)
            for key in ("dependencies", "devDependencies", "peerDependencies"):
                for name in data.get(key, {}):
                    names.add(name.lower())
        except json.JSONDecodeError:
            pass
    return names
