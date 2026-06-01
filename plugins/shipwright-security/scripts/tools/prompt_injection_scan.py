#!/usr/bin/env python3
"""Prompt injection and Claude Code plugin-specific security scanner.

Scans Shipwright plugin files for patterns that Semgrep / Trivy / Gitleaks
cannot detect — specifically: prompt-override attempts in Markdown skill
definitions, malicious shell commands in hook configs, dangerous Python
patterns in scripts, and suspicious dependency additions.

Output is a list of findings in the same normalized schema used by the
OSS scanner backend, so the report generator can merge them transparently.

Usage:
    # Full repo scan
    uv run scripts/tools/prompt_injection_scan.py \
        --full --path . --output prompt_risks.json

    # Diff-only scan (PR mode)
    uv run scripts/tools/prompt_injection_scan.py \
        --diff origin/main --output prompt_risks.json

Exit codes:
    0  no findings above --fail-on threshold
    1  findings above threshold
    2  scan error (invalid args, git failure, etc.)
"""

from __future__ import annotations

import argparse
import io
import json
import re
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _fix_windows_encoding() -> None:
    if sys.platform == "win32":
        try:
            sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
            sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


SCRIPT_DIR = Path(__file__).resolve().parent
PLUGIN_ROOT = SCRIPT_DIR.parent.parent
SHARED_ROOT = PLUGIN_ROOT.parent.parent / "shared"

sys.path.insert(0, str(SHARED_ROOT / "scripts"))

try:
    from lib.errors import structured_error, structured_success  # type: ignore
except (ImportError, ModuleNotFoundError):
    def structured_error(what_failed, what_was_attempted, error_category, is_retryable,
                         partial_results=None, alternatives=None, context=None):
        return {
            "success": False,
            "error": {
                "what_failed": what_failed,
                "what_was_attempted": what_was_attempted,
                "error_category": error_category,
                "is_retryable": is_retryable,
                "partial_results": partial_results or {},
                "alternatives": alternatives or [],
                "context": context or {},
            },
        }

    def structured_success(data=None):
        result = {"success": True}
        if data:
            result.update(data)
        return result


SEVERITY_ORDER = ["critical", "high", "medium", "low", "info"]


# ---------------------------------------------------------------------------
# Detection rules
# ---------------------------------------------------------------------------

# Patterns for Markdown skill / agent files.
# Matched case-insensitively against each line.
PROMPT_OVERRIDE_PATTERNS: list[tuple[str, str]] = [
    (r"ignore (all )?(previous|prior|above|preceding) instructions", "PROMPT_OVERRIDE_IGNORE"),
    (r"disregard (the |all )?(above|previous|prior|preceding)", "PROMPT_OVERRIDE_DISREGARD"),
    (r"you are now (a |an )?", "PROMPT_OVERRIDE_ROLE_SWITCH"),
    (r"new instructions:", "PROMPT_OVERRIDE_NEW_INSTRUCTIONS"),
    (r"system prompt:", "PROMPT_OVERRIDE_SYSTEM_PROMPT"),
    (r"\bDAN mode\b", "PROMPT_OVERRIDE_DAN"),
    (r"developer mode (enabled|activated|on)", "PROMPT_OVERRIDE_DEV_MODE"),
    (r"jailbreak", "PROMPT_OVERRIDE_JAILBREAK"),
    (r"reveal (your |the )?system prompt", "PROMPT_OVERRIDE_REVEAL_PROMPT"),
]

# Suspicious Unicode code points often used for smuggling.
SUSPICIOUS_UNICODE = {
    0x200B: "ZERO_WIDTH_SPACE",
    0x200C: "ZERO_WIDTH_NON_JOINER",
    0x200D: "ZERO_WIDTH_JOINER",
    0x2060: "WORD_JOINER",
    0x202A: "LEFT_TO_RIGHT_EMBEDDING",
    0x202B: "RIGHT_TO_LEFT_EMBEDDING",
    0x202C: "POP_DIRECTIONAL_FORMATTING",
    0x202D: "LEFT_TO_RIGHT_OVERRIDE",
    0x202E: "RIGHT_TO_LEFT_OVERRIDE",
    0x2066: "LEFT_TO_RIGHT_ISOLATE",
    0x2067: "RIGHT_TO_LEFT_ISOLATE",
    0x2068: "FIRST_STRONG_ISOLATE",
    0x2069: "POP_DIRECTIONAL_ISOLATE",
}

# Shell download patterns in hooks.json.
SHELL_DOWNLOAD_PATTERNS = [
    r"\bcurl\b[^\n]*\bhttps?://",
    r"\bwget\b[^\n]*\bhttps?://",
    r"Invoke-WebRequest",
    r"Invoke-RestMethod",
]

# Shell pipe-to-interpreter patterns in hooks.json (e.g. "curl ... | bash").
SHELL_PIPE_INTERP_PATTERNS = [
    r"\|\s*bash\b",
    r"\|\s*sh\b",
    r"\|\s*zsh\b",
    r"\|\s*python(3)?\b",
    r"\|\s*pwsh\b",
    r"\|\s*powershell",
    r"\|\s*node\b",
]

# Dangerous Python patterns.
# Note: `compile()` is intentionally NOT flagged — too many legitimate uses
# (re.compile, ast.compile, template engines) with very low security signal.
PY_DANGEROUS_PATTERNS: list[tuple[str, str, str]] = [
    (r"(?<!\.)\beval\s*\(", "PY_EVAL", "high"),
    (r"(?<!\.)\bexec\s*\(", "PY_EXEC", "high"),
    (r"(?<!\.)\b__import__\s*\(", "PY_DYNAMIC_IMPORT", "medium"),
    (r"\bos\.system\s*\(", "PY_OS_SYSTEM", "high"),
    (r"subprocess\.[a-zA-Z_]+\([^)]*shell\s*=\s*True", "PY_SHELL_TRUE", "medium"),
    (r"\bpickle\.loads?\s*\(", "PY_PICKLE_LOAD", "high"),
    (r"\bmarshal\.loads?\s*\(", "PY_MARSHAL_LOAD", "high"),
]

# Base64 blob detection: 100+ consecutive base64 chars on a single line
# inside a prose (non-code) markdown file. Code blocks are skipped.
BASE64_BLOB_PATTERN = re.compile(r"[A-Za-z0-9+/]{100,}={0,2}")

# Hidden HTML comment detection.
HTML_COMMENT_PATTERN = re.compile(r"<!--(.*?)-->", re.DOTALL)


# ---------------------------------------------------------------------------
# Finding builder
# ---------------------------------------------------------------------------

_finding_counter = 0


def make_finding(
    severity: str,
    rule: str,
    description: str,
    affected_file: str,
    affected_line: int | None,
    remediation_class: str = "needs-review",
    remediation_hint: str | None = None,
) -> dict[str, Any]:
    global _finding_counter
    _finding_counter += 1
    severity_score_map = {
        "critical": 9.5, "high": 8.0, "medium": 5.0, "low": 3.0, "info": 1.0,
    }
    return {
        "id": f"prompt-injection-{_finding_counter:04d}",
        "severity": severity,
        "severity_score": severity_score_map.get(severity, 5.0),
        "type": "prompt_injection",
        "rule": rule,
        "cve_id": None,
        "affected_package": None,
        "affected_file": affected_file,
        "affected_line": affected_line,
        "description": description,
        "remediation_hint": remediation_hint,
        "cwe_classes": [],
        "source": "shipwright-prompt-scan",
        "_remediation_class": remediation_class,
    }


# ---------------------------------------------------------------------------
# Markdown scanner
# ---------------------------------------------------------------------------

ALLOWLIST_MARKER = "shipwright-prompt-scan: allow"


def _has_allowlist_marker(text: str) -> bool:
    """Check if a file has opted out of prompt injection scanning.

    Files documenting the scanner's own patterns (e.g. CONTRIBUTING.md,
    SECURITY.md, design specs) can add `shipwright-prompt-scan: allow`
    in their first 20 lines to skip the scan.
    """
    head = "\n".join(text.split("\n")[:20])
    return ALLOWLIST_MARKER in head


def scan_markdown(path: Path, rel_path: str) -> list[dict[str, Any]]:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []

    if _has_allowlist_marker(text):
        return []

    findings: list[dict[str, Any]] = []
    lines = text.split("\n")

    # Prompt override pattern scan (case-insensitive)
    for i, line in enumerate(lines, 1):
        lower = line.lower()
        for pattern, rule_id in PROMPT_OVERRIDE_PATTERNS:
            if re.search(pattern, lower, re.IGNORECASE):
                findings.append(make_finding(
                    severity="high",
                    rule=rule_id,
                    description=(
                        f"Detected prompt-override pattern '{pattern}' in markdown "
                        f"file. May indicate an attempt to override Claude's "
                        f"instructions at runtime."
                    ),
                    affected_file=rel_path,
                    affected_line=i,
                    remediation_hint=(
                        "Remove the pattern or rewrite to make intent clear. "
                        "Skill definitions should instruct Claude directly, not "
                        "reference 'previous instructions'."
                    ),
                ))

    # Suspicious Unicode scan
    for i, line in enumerate(lines, 1):
        for ch in line:
            cp = ord(ch)
            if cp in SUSPICIOUS_UNICODE:
                findings.append(make_finding(
                    severity="high",
                    rule=f"UNICODE_{SUSPICIOUS_UNICODE[cp]}",
                    description=(
                        f"Suspicious Unicode code point U+{cp:04X} "
                        f"({SUSPICIOUS_UNICODE[cp]}) found. These characters "
                        f"are commonly used to hide content from reviewers."
                    ),
                    affected_file=rel_path,
                    affected_line=i,
                    remediation_hint="Remove the invisible character.",
                ))
                break  # one finding per line is enough

    # Base64 blob scan (skip fenced code blocks)
    in_fence = False
    for i, line in enumerate(lines, 1):
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if BASE64_BLOB_PATTERN.search(line):
            findings.append(make_finding(
                severity="medium",
                rule="BASE64_BLOB_IN_PROSE",
                description=(
                    "Long base64-like string detected outside of a code block. "
                    "May indicate hidden encoded content."
                ),
                affected_file=rel_path,
                affected_line=i,
                remediation_hint="Move to a code block or remove if unintended.",
            ))

    # Hidden HTML comments with suspicious content
    for match in HTML_COMMENT_PATTERN.finditer(text):
        content = match.group(1).strip()
        if not content:
            continue
        line_num = text[: match.start()].count("\n") + 1
        # Flag only if the comment looks like a prompt
        lowered = content.lower()
        if any(
            re.search(pattern, lowered) for pattern, _ in PROMPT_OVERRIDE_PATTERNS
        ):
            findings.append(make_finding(
                severity="high",
                rule="HTML_COMMENT_HIDDEN_PROMPT",
                description=(
                    "HTML comment contains prompt-override patterns. Comments "
                    "are invisible in rendered markdown but may still be "
                    "processed by LLMs."
                ),
                affected_file=rel_path,
                affected_line=line_num,
                remediation_hint="Remove the HTML comment or rewrite content.",
            ))

    return findings


# ---------------------------------------------------------------------------
# hooks.json scanner
# ---------------------------------------------------------------------------

def scan_hooks_json(path: Path, rel_path: str) -> list[dict[str, Any]]:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []

    findings: list[dict[str, Any]] = []
    lines = text.split("\n")

    for i, line in enumerate(lines, 1):
        # Shell download patterns → CRITICAL
        for pattern in SHELL_DOWNLOAD_PATTERNS:
            if re.search(pattern, line):
                findings.append(make_finding(
                    severity="critical",
                    rule="HOOKS_EXTERNAL_DOWNLOAD",
                    description=(
                        "Hook configuration contains an external download "
                        "(curl / wget / Invoke-WebRequest). Hooks must not "
                        "fetch remote content at runtime."
                    ),
                    affected_file=rel_path,
                    affected_line=i,
                    remediation_hint="Replace with a bundled local script.",
                ))
                break

        # Pipe-to-interpreter → CRITICAL
        for pattern in SHELL_PIPE_INTERP_PATTERNS:
            if re.search(pattern, line):
                findings.append(make_finding(
                    severity="critical",
                    rule="HOOKS_PIPE_TO_INTERPRETER",
                    description=(
                        "Hook configuration pipes output directly into a "
                        "shell interpreter (| bash, | sh, etc.). This is a "
                        "classic RCE pattern."
                    ),
                    affected_file=rel_path,
                    affected_line=i,
                    remediation_hint="Avoid piping to interpreters in hooks.",
                ))
                break

    return findings


# ---------------------------------------------------------------------------
# Python scanner
# ---------------------------------------------------------------------------

def scan_python(path: Path, rel_path: str) -> list[dict[str, Any]]:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []

    findings: list[dict[str, Any]] = []
    lines = text.split("\n")

    for i, line in enumerate(lines, 1):
        # Skip obvious comments
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        for pattern, rule_id, severity in PY_DANGEROUS_PATTERNS:
            if re.search(pattern, line):
                findings.append(make_finding(
                    severity=severity,
                    rule=rule_id,
                    description=(
                        f"Dangerous Python pattern '{pattern}' detected. "
                        f"Such patterns enable arbitrary code execution."
                    ),
                    affected_file=rel_path,
                    affected_line=i,
                    remediation_hint=(
                        "Refactor to use safe alternatives (ast.literal_eval, "
                        "subprocess with shell=False, etc.)."
                    ),
                ))

    return findings


# ---------------------------------------------------------------------------
# Dependency files scanner
# ---------------------------------------------------------------------------

def scan_dependency_file(
    path: Path,
    rel_path: str,
    baseline_deps: set[str] | None,
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


# ---------------------------------------------------------------------------
# Walker
# ---------------------------------------------------------------------------

SKIP_DIRS = {
    ".git", ".venv", "venv", "node_modules", "__pycache__", ".pytest_cache",
    "dist", "build", ".mypy_cache", ".ruff_cache", "e2e-results", "playwright-report",
    "fixtures",  # test fixtures are intentionally suspicious
}

# Files that reference injection patterns as literals (scanner source, tests).
# Matched against the POSIX-style relative path.
SELF_REFERENCE_PATHS = {
    "plugins/shipwright-security/scripts/tools/prompt_injection_scan.py",
    "plugins/shipwright-security/tests/test_prompt_injection_scan.py",
}


def _is_excluded(path: Path, root: Path) -> bool:
    """Under a SKIP_DIRS segment, or a SELF_REFERENCE_PATHS file (shared by the full walk + --diff path)."""
    if any(part in SKIP_DIRS for part in path.parts):
        return True
    try:
        rel = path.relative_to(root).as_posix()
    except ValueError:
        rel = path.as_posix()
    return rel in SELF_REFERENCE_PATHS


def iter_scannable_files(root: Path) -> list[Path]:
    """Walk the tree, excluding skip dirs + self-reference files (_is_excluded)."""
    return [p for p in root.rglob("*") if p.is_file() and not _is_excluded(p, root)]


def scan_file(
    path: Path,
    root: Path,
    baseline_deps: set[str] | None = None,
) -> list[dict[str, Any]]:
    """Dispatch to the right scanner based on filename."""
    try:
        rel_path = path.relative_to(root).as_posix()
    except ValueError:
        rel_path = path.as_posix()

    name = path.name.lower()
    suffix = path.suffix.lower()

    if suffix == ".md":
        return scan_markdown(path, rel_path)
    if name == "hooks.json":
        return scan_hooks_json(path, rel_path)
    if suffix == ".py":
        return scan_python(path, rel_path)
    if name in ("pyproject.toml", "package.json"):
        return scan_dependency_file(path, rel_path, baseline_deps)
    return []


# ---------------------------------------------------------------------------
# Git diff helper
# ---------------------------------------------------------------------------

def get_changed_files(base_ref: str, repo_root: Path) -> list[Path]:
    """Return list of files changed relative to base_ref."""
    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", f"{base_ref}...HEAD"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return []

    if result.returncode != 0:
        return []

    files: list[Path] = []
    for line in result.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        path = repo_root / line
        if path.is_file():
            files.append(path)
    return files


# ---------------------------------------------------------------------------
# Output builder
# ---------------------------------------------------------------------------

def build_output(
    findings: list[dict[str, Any]],
    repo: str,
) -> dict[str, Any]:
    severity_counts = Counter(f.get("severity", "unknown") for f in findings)
    return {
        "scan_date": datetime.now(timezone.utc).isoformat(),
        "repo": repo,
        "scanner": "shipwright-prompt-scan",
        "total_findings": len(findings),
        "by_severity": {sev: severity_counts.get(sev, 0) for sev in SEVERITY_ORDER},
        "remediation": {
            "fixed": 0,
            "declined": 0,
            "deferred": 0,
            "open": len(findings),
        },
        "findings": findings,
    }


def count_above_threshold(findings: list[dict[str, Any]], fail_on: set[str]) -> int:
    if not fail_on:
        return 0
    return sum(1 for f in findings if f.get("severity", "").lower() in fail_on)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Scan for prompt injection and plugin-specific risks",
    )
    parser.add_argument(
        "--path",
        default=".",
        help="Target directory (default: current)",
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help="Scan all files, not just the diff",
    )
    parser.add_argument(
        "--diff",
        help="Scan only files changed relative to this git ref (e.g. origin/main)",
    )
    parser.add_argument(
        "--output",
        help="Output JSON file (default: stdout)",
    )
    parser.add_argument(
        "--repo",
        default="unknown",
        help="Repository name for output metadata",
    )
    parser.add_argument(
        "--fail-on",
        help="Comma-separated severities that cause exit 1 (e.g. critical,high)",
    )
    args = parser.parse_args()

    if not args.full and not args.diff:
        args.full = True  # default if neither is specified

    try:
        fail_on = set()
        if args.fail_on:
            parts = [p.strip().lower() for p in args.fail_on.split(",") if p.strip()]
            for p in parts:
                if p not in SEVERITY_ORDER:
                    raise ValueError(f"Unknown severity '{p}'")
            fail_on = set(parts)
    except ValueError as e:
        print(
            json.dumps(
                structured_error(
                    what_failed=str(e),
                    what_was_attempted="parse --fail-on",
                    error_category="validation",
                    is_retryable=False,
                )
            ),
            file=sys.stderr,
        )
        return 2

    target = Path(args.path).resolve()
    if not target.exists():
        print(
            json.dumps(
                structured_error(
                    what_failed=f"Target path does not exist: {target}",
                    what_was_attempted="resolve scan path",
                    error_category="validation",
                    is_retryable=False,
                )
            ),
            file=sys.stderr,
        )
        return 2

    # Select files to scan. Both modes apply the same exclusion (_is_excluded);
    # diff-mode must filter too, else a self-reference / skip-dir file in a PR
    # diff is false-flagged (the bug seen on PR #125).
    if args.diff:
        files = [f for f in get_changed_files(args.diff, target) if not _is_excluded(f, target)]
    else:
        files = iter_scannable_files(target)

    all_findings: list[dict[str, Any]] = []
    for path in files:
        try:
            all_findings.extend(scan_file(path, target))
        except Exception as e:  # noqa: BLE001 — keep scanning on error
            print(
                f"[prompt-injection-scan] Error scanning {path}: {e}",
                file=sys.stderr,
            )

    output = build_output(all_findings, repo=args.repo)

    if args.output:
        output_path = Path(args.output).resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(output, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        result = structured_success(
            data={
                "command": "prompt_injection_scan",
                "output_path": str(output_path),
                "findings_count": len(all_findings),
                "by_severity": output["by_severity"],
                "files_scanned": len(files),
            }
        )
    else:
        result = structured_success(
            data={
                "command": "prompt_injection_scan",
                "findings_count": len(all_findings),
                "by_severity": output["by_severity"],
                "files_scanned": len(files),
                "output": output,
            }
        )

    print(json.dumps(result, ensure_ascii=False))

    if count_above_threshold(all_findings, fail_on) > 0:
        return 1
    return 0


if __name__ == "__main__":
    _fix_windows_encoding()
    sys.exit(main())
