"""Advisory scan of the surfaces that configure an AI agent.

Complements ``prompt_injection_scan.py`` with a few deterministic checks that
no other scanner in the chain (Semgrep, Trivy, Gitleaks) performs:

* package-source redirection (``.npmrc``, ``pip.conf``, ``uv.toml`` ...)
* hook / settings entries that ship data off-machine or run shell commands
* hidden-content tricks and safety-suppressing instructions in Markdown
* ``SKILL.md`` tool scope declarations
* executables disguised under a documentation extension

Attribution: the *categories* of check (dependency-source redirection, bundled
hook and settings analysis, whitespace padding, anti-refusal instructions,
tool-scope declarations, concealed executables) were inspired by NVIDIA
SkillSpector (https://github.com/NVIDIA/SkillSpector, Apache-2.0,
Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES). The rules here are
re-implemented from scratch for Shipwright's findings schema; no SkillSpector
code or rule text is copied.

**Advisory by construction.** The CI critical gate (``security.yml``) blocks on
``severity == "critical"`` only. Findings from this package are clamped to
``medium`` so a new, still-unproven rule can never block a merge; promoting a rule
to blocking is a deliberate, separate decision.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Callable

sys.path.insert(0, str(Path(__file__).resolve().parent))
from skill_surface_concealed import scan_concealed  # noqa: E402
from skill_surface_hooks import scan_hooks, scan_settings  # noqa: E402
from skill_surface_prose import scan_prose  # noqa: E402
from skill_surface_registry import REGISTRY_FILES, scan_registry  # noqa: E402

MAX_SEVERITY = "medium"
_SEVERITY_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}

SETTINGS_FILES = {"settings.json", "settings.local.json"}


def _clamp(severity: str) -> str:
    """Never stronger than MAX_SEVERITY (advisory-only contract)."""
    sev = str(severity).lower()
    # Unknown or mis-cased values (e.g. "Critical") rank 0 and are capped too.
    return sev if _SEVERITY_RANK.get(sev, 0) >= _SEVERITY_RANK[MAX_SEVERITY] else MAX_SEVERITY


def _printable(text: str) -> str:
    """Make parsed-file text safe for the UTF-8 report write.

    A JSON escape such as ``\\ud800`` parses to a lone surrogate that cannot be encoded;
    a finding carrying one would crash ``main`` at the output write and leave an empty
    ``prompt_risks.json`` that the CI gate reads as "no criticals".
    """
    return text.encode("utf-8", "backslashreplace").decode("utf-8")


def _read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8-sig")  # a Windows BOM must not hide frontmatter
    except (OSError, UnicodeDecodeError):
        return None


# Directories whose Markdown configures the agent itself. A file there is the very thing
# under suspicion, so it must not be able to switch its own check off.
AGENT_CONFIG_DIRS = {"agents", "skills", "commands", ".claude", ".cursor"}
AGENT_CONFIG_NAMES = {"skill.md", "claude.md", "agents.md", "gemini.md", "copilot-instructions.md"}


def is_agent_surface(rel_path: str, name: str) -> bool:
    """Markdown that configures an agent (the only place safety-wording rules apply)."""
    return name in AGENT_CONFIG_NAMES or bool(set(rel_path.lower().split("/")[:-1]) & AGENT_CONFIG_DIRS)


def _marker_honoured(rel_path: str, name: str, suffix: str) -> bool:
    """The in-file allowlist marker only silences *documentation*.

    It exists for docs that quote the scanner's own patterns. Honouring it on
    ``SKILL.md`` / agent / command files, or on JSON, registry and binary files, would let
    attacker-written configuration clear itself with one line.
    """
    return suffix == ".md" and not is_agent_surface(rel_path, name)


def scan_surface(
    path: Path,
    rel_path: str,
    make_finding,
    has_allow_marker: Callable[[str], bool],
) -> list[dict[str, Any]]:
    """Run every applicable advisory check for ``path``.

    Never raises: an advisory check that fails must not take the existing scan of the
    same file down with it (``prompt_injection_scan.main`` drops a file's findings when
    its scan raises), so any rule error is reported on stderr and the file moves on.
    """
    findings: list[dict[str, Any]] = []

    def emit(severity: str, rule: str, description: str, line: int | None, hint: str | None) -> None:
        findings.append(make_finding(
            severity=_clamp(severity),
            rule=rule,
            description=_printable(description),
            affected_file=rel_path,
            affected_line=line,
            remediation_hint=_printable(hint) if hint else hint,
        ))

    name = path.name.lower()
    suffix = path.suffix.lower()
    try:
        scan_concealed(path, suffix, emit)

        text: str | None = None
        is_settings = name in SETTINGS_FILES and ".claude" in rel_path.lower().split("/")[:-1]
        if name in REGISTRY_FILES or is_settings or name == "hooks.json" or suffix == ".md":
            text = _read_text(path)
        if text is None or (_marker_honoured(rel_path, name, suffix) and has_allow_marker(text)):
            return findings

        if name in REGISTRY_FILES:
            scan_registry(name, text, emit)
        elif name == "hooks.json":
            scan_hooks(text, emit)
        elif is_settings:
            scan_settings(text, emit)
        elif suffix == ".md":
            scan_prose(text, emit, agent_surface=is_agent_surface(rel_path, name))
    except Exception as error:  # noqa: BLE001 - advisory checks must never abort the scan
        print(f"[skill-surface-scan] {rel_path}: {type(error).__name__}: {error}", file=sys.stderr)
    return findings
