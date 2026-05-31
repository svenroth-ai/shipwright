#!/usr/bin/env python3
"""Validate required environment variables for any pipeline phase.

Reads the stack profile from shipwright_run_config.json, checks the
profile's required_env_vars for the given phase, and reports missing vars.
All vars (build, deploy, plugin) live in the project's .env.local.

Usage:
    uv run validate_env.py --project-root <path> --phase build|deploy|plugin|all [--profile-dir <path>]

Output (JSON):
    {
        "success": true/false,
        "phase": "build",
        "profile": "supabase-nextjs",
        "missing": [{"name": "...", "description": "..."}],
        "optional_missing": [{"name": "...", "description": "..."}],
        "found": ["VAR_NAME", ...],
        "env_file_exists": true/false,
        "env_file_path": ".env.local",
        "skipped": false,
        "skip_reason": null
    }
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path

# Allow importing shared lib
sys.path.insert(0, str(Path(__file__).parent / "lib"))


def _strip_inline_comment(raw: str) -> str:
    """Return the value portion of an env-file RHS, stripping inline comments.

    POSIX/dotenv conventions:
      - Leading whitespace is not part of the value.
      - If the value is wrapped in matching single/double quotes, the value is
        the content BETWEEN the quotes — anything after the closing quote
        (including ``#`` markers) is comment territory.
      - For unquoted values, an inline comment starts at the first whitespace
        followed by ``#``. ``KEY=value#nohash`` keeps ``#nohash`` because there
        is no whitespace separator (matches python-dotenv semantics).

    No escape handling on quotes — keeps parser surface small. The producer
    side (``init_env_file``) never emits escaped quotes.
    """
    raw = raw.lstrip()
    if not raw or raw[0] == "#":
        # Pure-comment RHS like ``KEY=        # placeholder``: empty value.
        return ""
    if raw[0] in ('"', "'"):
        quote = raw[0]
        end = raw.find(quote, 1)
        if end == -1:
            # Unclosed quote — fall back to defensive literal interpretation.
            return raw[1:].rstrip()
        return raw[1:end]
    # Unquoted: strip inline comment if separated by whitespace.
    m = re.search(r"\s+#", raw)
    if m:
        raw = raw[:m.start()]
    return raw.rstrip()


def parse_env_file(env_path: Path) -> dict[str, str]:
    """Parse a .env file into a dict of key-value pairs.

    Handles ``KEY=value``, ``KEY="value"``, ``KEY='value'``, ``export KEY=value``
    (POSIX-style), inline ``# comment`` (whitespace-separated, unquoted only),
    full-line comments, and blank lines. Does NOT expand variable references.
    """
    env_vars: dict[str, str] = {}
    if not env_path.exists():
        return env_vars

    # Strip a UTF-8 BOM at the start of the file. Notepad on Windows adds one
    # when saving as UTF-8 by default; without this, the first key gets a
    # ``﻿`` prefix and ``os.environ.get(KEY)`` returns None even though
    # the user thinks they filled in the value.
    text = env_path.read_text(encoding="utf-8-sig")

    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        # Strip optional `export ` prefix (POSIX shell habit; some operators
        # source `.env.local` directly into a shell session).
        if line.startswith("export ") or line.startswith("export\t"):
            line = line[len("export"):].lstrip()
        key, _, value = line.partition("=")
        key = key.strip()
        value = _strip_inline_comment(value)
        if key:
            env_vars[key] = value
    return env_vars


def load_profile(profile_name: str, profile_dir: Path) -> dict | None:
    """Load a stack profile JSON by name."""
    profile_path = profile_dir / f"{profile_name}.json"
    if not profile_path.exists():
        return None
    return json.loads(profile_path.read_text(encoding="utf-8"))


# Framework-level env vars used by Shipwright itself, regardless of stack
# profile. Mirrors the OpenRouter-first fallback order in
# ``shared/scripts/lib/external_review_config.py:is_external_review_enabled``
# so the .env.local scaffold reflects what the runtime actually checks for.
# Drift between the two is locked down by
# ``TestFrameworkOrderDriftProtection``.
_SHIPWRIGHT_FRAMEWORK_VARS: list[dict] = [
    {
        "name": "OPENROUTER_API_KEY",
        "description": "OpenRouter API key for external plan/iterate/code reviews "
                       "(preferred — single key for both Gemini and OpenAI)",
        "optional": True,
    },
    {
        "name": "GEMINI_API_KEY",
        "description": "Direct Google Gemini API key (alternative to OpenRouter)",
        "optional": True,
    },
    {
        "name": "OPENAI_API_KEY",
        "description": "Direct OpenAI API key (alternative to OpenRouter)",
        "optional": True,
    },
]


def _collect_phase_vars(
    profile: dict, phase: str,
) -> list[tuple[str, list[dict]]]:
    """Return list of (section_label, vars) tuples for *phase*.

    If *phase* is ``"all"``, returns all sections.  Otherwise returns
    only the requested phase.

    The framework-level review-key section is appended by
    ``init_env_file`` when ``include_framework=True``; this helper
    intentionally only inspects the profile so global ``phase=all``
    semantics for direct CLI users stay unchanged.
    """
    required = profile.get("required_env_vars", {})
    phase_order = ["build", "deploy", "plugin"]

    if phase == "all":
        return [
            (p.capitalize(), required.get(p, []))
            for p in phase_order
            if required.get(p)
        ]
    vars_list = required.get(phase, [])
    return [(phase.capitalize(), vars_list)] if vars_list else []


def _dedup_sections(
    sections: list[tuple[str, list[dict]]],
) -> list[tuple[str, list[dict]]]:
    """Drop duplicate var entries — first occurrence (by name) wins.

    Preserves the original section structure: a section that becomes empty
    after deduplication is dropped entirely.
    """
    seen: set[str] = set()
    out: list[tuple[str, list[dict]]] = []
    for label, vars_list in sections:
        kept = []
        for var in vars_list:
            name = var.get("name")
            if not name or name in seen:
                continue
            seen.add(name)
            kept.append(var)
        if kept:
            out.append((label, kept))
    return out


def _find_existing_keys(env_file_path: Path) -> set[str]:
    """Parse existing .env.local and return all keys (active or commented).

    Tolerates both ``KEY=value`` and ``export KEY=value`` forms (commented
    or active). Whitespace around ``=`` is also tolerated.
    """
    keys: set[str] = set()
    if not env_file_path.exists():
        return keys
    for line in env_file_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        check = stripped.lstrip("#").strip()
        # Strip optional `export ` prefix (handles `export KEY=` and
        # `# export KEY=` shapes alike).
        if check.startswith("export ") or check.startswith("export\t"):
            check = check[len("export"):].lstrip()
        if "=" in check:
            key = check.partition("=")[0].strip()
            if key:
                keys.add(key)
    return keys


def _ensure_gitignore(project_root: Path) -> bool:
    """Ensure .env.local is listed in the project's .gitignore.

    Creates .gitignore if it doesn't exist.  Appends the entry if missing.
    Returns True if the file was modified.
    """
    gitignore_path = project_root / ".gitignore"
    marker = ".env.local"

    if gitignore_path.exists():
        content = gitignore_path.read_text(encoding="utf-8")
        # Check if any line already covers .env.local
        for line in content.splitlines():
            stripped = line.strip()
            if stripped in (marker, ".env*.local", ".env.*.local"):
                return False
        # Append
        if not content.endswith("\n"):
            content += "\n"
        content += "\n# Shipwright secrets\n.env.local\n"
        gitignore_path.write_text(content, encoding="utf-8")
        return True

    # Create minimal .gitignore
    gitignore_path.write_text(
        "# Shipwright secrets\n.env.local\n",
        encoding="utf-8",
    )
    return True


def init_env_file(
    project_root: Path,
    phase: str,
    profile_dir: Path,
    *,
    include_framework: bool = False,
) -> dict:
    """Create or update .env.local with commented placeholders for required vars.

    Includes all phases when *phase* is ``"all"``, or a single phase otherwise.
    Also ensures .env.local is in .gitignore before creating the file.

    When ``include_framework=True``, the framework-level external-review keys
    (``OPENROUTER_API_KEY`` / ``GEMINI_API_KEY`` / ``OPENAI_API_KEY``) are
    appended after the profile-defined vars and deduplicated by name — first
    occurrence wins, so a profile that already lists one of these keys keeps
    its custom description. Default ``False`` preserves the global
    ``phase=all`` semantics for direct CLI (``--init``) users.

    Hard-stop: if ``_ensure_gitignore`` raises (permission/OS error), the
    function returns ``{"action": "skipped", "reason":
    "gitignore_enforcement_failed", "error": ...}`` and writes NO
    ``.env.local`` — secrets are never staged on a repo where the .gitignore
    rule could not be enforced.

    Return shape (always a dict):
      - ``action``: ``created`` | ``updated`` | ``unchanged`` | ``skipped``
      - ``path``: absolute path of ``.env.local`` (also under legacy key
        ``env_file_path`` for backwards-compat)
      - ``vars``: every key declared in this run (created + unchanged paths)
      - ``added``: only the keys appended this call (updated path)
      - ``framework_keys``: framework keys merged (when ``include_framework``)
      - ``missing_keys``: keys whose value in the FINAL file state is empty
        or matches ``_is_placeholder`` (computed even on ``unchanged``)
      - ``profile``: matched profile name
      - ``reason`` / ``error``: populated only on skipped paths
    """
    # Load profile
    run_config_path = project_root / "shipwright_run_config.json"
    if not run_config_path.exists():
        return {"action": "skipped", "reason": "No shipwright_run_config.json found"}

    run_config = json.loads(run_config_path.read_text(encoding="utf-8"))
    profile_name = run_config.get("profile")
    if not profile_name:
        return {"action": "skipped", "reason": "No profile set in run config"}

    profile = load_profile(profile_name, profile_dir)
    if not profile:
        return {"action": "skipped", "reason": f"Profile '{profile_name}' not found"}

    sections = _collect_phase_vars(profile, phase)
    if include_framework:
        sections = sections + [("Framework / External Review", list(_SHIPWRIGHT_FRAMEWORK_VARS))]
    sections = _dedup_sections(sections)
    all_vars = [v for _, vars_list in sections for v in vars_list]
    if not all_vars:
        return {"action": "skipped", "reason": f"No vars defined for phase '{phase}'"}

    framework_names = [v["name"] for v in _SHIPWRIGHT_FRAMEWORK_VARS]

    # Ensure .env.local is gitignored BEFORE creating it.
    # If enforcement fails (permission denied, locked file, OS error), abort
    # before any .env.local write — never stage secrets in a repo where the
    # ignore rule could not be locked in.
    try:
        _ensure_gitignore(project_root)
    except OSError as exc:
        return {
            "action": "skipped",
            "reason": "gitignore_enforcement_failed",
            "error": str(exc),
            "path": str(project_root / ".env.local"),
            "env_file_path": str(project_root / ".env.local"),
        }

    env_file_path = project_root / ".env.local"
    existing_keys = _find_existing_keys(env_file_path)

    if env_file_path.exists():
        # Find vars that need to be added
        missing_vars = [v for v in all_vars if v["name"] not in existing_keys]
        if not missing_vars:
            return {
                "action": "unchanged",
                "path": str(env_file_path),
                "env_file_path": str(env_file_path),
                "profile": profile_name,
                "vars": [v["name"] for v in all_vars],
                "framework_keys": framework_names if include_framework else [],
                "missing_keys": _compute_missing_keys(env_file_path, all_vars),
            }

        # Append missing vars to existing file
        lines = ["\n# --- Added by Shipwright ---"]
        for var in missing_vars:
            opt = " (optional)" if var.get("optional") else ""
            lines.append(f"# {var['name']}=        # {var['description']}{opt}")
        lines.append("")

        with env_file_path.open("a", encoding="utf-8") as f:
            f.write("\n".join(lines))

        return {
            "action": "updated",
            "path": str(env_file_path),
            "env_file_path": str(env_file_path),
            "profile": profile_name,
            "added": [v["name"] for v in missing_vars],
            "vars": [v["name"] for v in all_vars],
            "framework_keys": framework_names if include_framework else [],
            "missing_keys": _compute_missing_keys(env_file_path, all_vars),
        }

    # Create new file with all sections
    lines = [
        "# =============================================================================",
        "# Environment Variables — generated by Shipwright",
        f"# Profile: {profile_name}",
        "#",
        "# Fill in the values below and remove the leading '#' to activate each variable.",
        "# This file is NOT committed to git (.gitignore).",
        "# =============================================================================",
    ]
    for label, vars_list in sections:
        lines.append("")
        lines.append(f"# --- {label} ---")
        for var in vars_list:
            opt = " (optional)" if var.get("optional") else ""
            lines.append(f"# {var['name']}=        # {var['description']}{opt}")
    lines.append("")

    env_file_path.write_text("\n".join(lines), encoding="utf-8")

    return {
        "action": "created",
        "path": str(env_file_path),
        "env_file_path": str(env_file_path),
        "profile": profile_name,
        "vars": [v["name"] for v in all_vars],
        "framework_keys": framework_names if include_framework else [],
        "missing_keys": _compute_missing_keys(env_file_path, all_vars),
    }


def _compute_missing_keys(env_file_path: Path, all_vars: list[dict]) -> list[str]:
    """Return names of vars whose value in the FINAL file state is empty
    or a placeholder per ``_is_placeholder``.

    Independent of ``action`` — a freshly created scaffold has every key
    placeholder-empty, an ``unchanged`` outcome may also have placeholder
    values lingering from a prior run, and an ``updated`` outcome may
    have a mix of filled + new-but-empty entries. The handoff banner
    in adopt's Step H reads this list verbatim to decide what to surface.
    """
    if not env_file_path.exists():
        return [v["name"] for v in all_vars]
    parsed = parse_env_file(env_file_path)
    out: list[str] = []
    for var in all_vars:
        name = var["name"]
        value = parsed.get(name, "")
        if _is_placeholder(value):
            out.append(name)
    return out


_PLACEHOLDER_PATTERNS = [
    "...", "xxx", "your-key-here", "your_key_here",
    "<placeholder>", "todo", "changeme", "replace_me",
    "sk_test_xxx", "pk_test_xxx", "sbp_xxx",
]


def _is_placeholder(value: str) -> bool:
    """Detect common placeholder values that aren't real credentials."""
    stripped = value.strip()
    if not stripped:
        return True
    lower = stripped.lower()
    for pattern in _PLACEHOLDER_PATTERNS:
        if lower == pattern:
            return True
    # Catch values that are just dots or x's
    if all(c == "." for c in stripped):
        return True
    if all(c.lower() == "x" for c in stripped):
        return True
    # Catch angle-bracket wrapped values like <your-key>
    if stripped.startswith("<") and stripped.endswith(">"):
        return True
    return False


def validate(
    project_root: Path,
    phase: str,
    profile_dir: Path,
) -> dict:
    """Run env var validation for the given phase.

    Returns a result dict suitable for JSON output.
    """
    # Read run config to get profile name
    run_config_path = project_root / "shipwright_run_config.json"
    if not run_config_path.exists():
        return {
            "success": True,
            "phase": phase,
            "profile": None,
            "missing": [],
            "optional_missing": [],
            "found": [],
            "env_file_exists": False,
            "env_file_path": None,
            "skipped": True,
            "skip_reason": "No shipwright_run_config.json found — skipping env validation",
        }

    run_config = json.loads(run_config_path.read_text(encoding="utf-8"))
    profile_name = run_config.get("profile")
    if not profile_name:
        return {
            "success": True,
            "phase": phase,
            "profile": None,
            "missing": [],
            "optional_missing": [],
            "found": [],
            "env_file_exists": False,
            "env_file_path": None,
            "skipped": True,
            "skip_reason": "No profile set in run config — skipping env validation",
        }

    profile = load_profile(profile_name, profile_dir)
    if not profile:
        return {
            "success": True,
            "phase": phase,
            "profile": profile_name,
            "missing": [],
            "optional_missing": [],
            "found": [],
            "env_file_exists": False,
            "env_file_path": None,
            "skipped": True,
            "skip_reason": f"Profile '{profile_name}' not found in {profile_dir}",
        }

    sections = _collect_phase_vars(profile, phase)
    phase_vars = [v for _, vars_list in sections for v in vars_list]

    if not phase_vars:
        return {
            "success": True,
            "phase": phase,
            "profile": profile_name,
            "missing": [],
            "optional_missing": [],
            "found": [],
            "env_file_exists": False,
            "env_file_path": None,
            "skipped": True,
            "skip_reason": f"No required_env_vars defined for phase '{phase}' in profile",
        }

    # Collect available vars from .env.local and os.environ
    env_file_path = project_root / ".env.local"
    env_file_exists = env_file_path.exists()

    available_vars: dict[str, str] = {}
    if env_file_exists:
        available_vars.update(parse_env_file(env_file_path))
    # os.environ takes precedence over .env.local (mirrors load_shipwright_env)
    available_vars.update(os.environ)

    found: list[str] = []
    missing: list[dict] = []
    optional_missing: list[dict] = []

    placeholder_detected: list[str] = []

    for var_def in phase_vars:
        var_name = var_def["name"]
        is_optional = var_def.get("optional", False)
        value = available_vars.get(var_name, "")

        if value and not _is_placeholder(value):
            found.append(var_name)
        elif value and _is_placeholder(value):
            placeholder_detected.append(var_name)
            if is_optional:
                optional_missing.append({
                    "name": var_name,
                    "description": var_def.get("description", "") + " (placeholder value detected)",
                })
            else:
                missing.append({
                    "name": var_name,
                    "description": var_def.get("description", "") + " (placeholder value detected)",
                })
        elif is_optional:
            optional_missing.append({
                "name": var_name,
                "description": var_def.get("description", ""),
            })
        else:
            missing.append({
                "name": var_name,
                "description": var_def.get("description", ""),
            })

    success = len(missing) == 0

    return {
        "success": success,
        "phase": phase,
        "profile": profile_name,
        "missing": missing,
        "optional_missing": optional_missing,
        "found": found,
        "placeholder_detected": placeholder_detected,
        "env_file_exists": env_file_exists,
        "env_file_path": str(env_file_path),
        "skipped": False,
        "skip_reason": None,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate env vars for build/deploy")
    parser.add_argument("--project-root", required=True, help="Path to target project root")
    parser.add_argument("--phase", required=True, choices=["build", "deploy", "plugin", "all"], help="Pipeline phase")
    parser.add_argument(
        "--profile-dir",
        help="Directory containing profile JSON files (default: shared/profiles/ relative to this script)",
    )
    parser.add_argument(
        "--init",
        action="store_true",
        help="Create/update .env.local with commented placeholders for required vars",
    )
    args = parser.parse_args()

    project_root = Path(args.project_root).resolve()
    if not project_root.is_dir():
        print(json.dumps({"success": False, "error": f"Project root not found: {project_root}"}, indent=2))
        return 1

    if args.profile_dir:
        profile_dir = Path(args.profile_dir).resolve()
    else:
        # Default: shared/profiles/ relative to this script's location
        profile_dir = Path(__file__).parent.parent / "profiles"

    if args.init:
        result = init_env_file(project_root, args.phase, profile_dir)
        print(json.dumps(result, indent=2))
        return 0

    result = validate(project_root, args.phase, profile_dir)
    print(json.dumps(result, indent=2))

    return 0 if result.get("success", False) or result.get("skipped", False) else 1


if __name__ == "__main__":
    sys.exit(main())
