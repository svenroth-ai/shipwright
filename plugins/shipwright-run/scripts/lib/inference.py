#!/usr/bin/env python3
"""Inference engine for shipwright-run.

Infers scope, profile, and autonomy from user description and project state.

Usage:
    uv run inference.py --description "Build a SaaS app with Supabase"
    uv run inference.py --description "Add dark mode" --project-root /path/to/project

Output (JSON):
    {
        "scope": "full_app" | "extension",
        "profile": "supabase-nextjs" | null,
        "profile_confidence": "high" | "medium" | "low",
        "autonomy": "guided",
        "signals": ["keyword: supabase", "keyword: next.js"]
    }
"""

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Optional


# Profile detection rules: (keywords, profile_name)
PROFILE_RULES = [
    ({"supabase", "next.js", "nextjs"}, "supabase-nextjs"),
    ({"supabase", "react"}, "supabase-nextjs"),
    ({"supabase"}, "supabase-nextjs"),  # Default framework
    ({"next.js", "nextjs"}, "supabase-nextjs"),  # Suggest Supabase
]


def detect_scope(project_root: Optional[Path] = None, **kwargs) -> tuple[str, list[str]]:
    """Detect project scope from filesystem state.

    Returns (scope, signals).
    For ongoing changes to existing projects, use /shipwright-iterate instead.
    """
    signals = []

    if project_root:
        has_claude_md = (project_root / "CLAUDE.md").exists()
        has_agent_docs = (project_root / "agent_docs").is_dir()

        if has_claude_md:
            signals.append("file: CLAUDE.md exists")
        if has_agent_docs:
            signals.append("file: agent_docs/ exists")

        if has_claude_md and has_agent_docs:
            return "extension", signals

    signals.append("default: no existing project detected")
    return "full_app", signals


def detect_profile(description: str) -> tuple[Optional[str], str, list[str]]:
    """Detect stack profile from description text.

    Returns (profile_name, confidence, signals).
    """
    desc_lower = description.lower()
    signals = []

    # Extract keywords
    found_keywords = set()
    keyword_map = {
        "supabase": "supabase",
        "next.js": "next.js",
        "nextjs": "next.js",
        "next js": "next.js",
        "react": "react",
        "tailwind": "tailwind",
        "typescript": "typescript",
    }

    for keyword, canonical in keyword_map.items():
        if keyword in desc_lower:
            found_keywords.add(canonical)
            signals.append(f"keyword: {canonical}")

    # Match against rules
    for required_keywords, profile_name in PROFILE_RULES:
        canonical_required = set()
        for kw in required_keywords:
            canonical_required.add(keyword_map.get(kw, kw))

        if canonical_required.issubset(found_keywords):
            # Determine confidence
            if len(canonical_required) >= 2:
                confidence = "high"
            elif len(found_keywords) >= 2:
                confidence = "medium"
            else:
                confidence = "low"

            return profile_name, confidence, signals

    return None, "none", signals


def infer_settings(
    description: str,
    project_root: Optional[str] = None,
    **kwargs,
) -> dict:
    """Run full inference and return settings."""
    root = Path(project_root) if project_root else None

    scope, scope_signals = detect_scope(root)
    profile, confidence, profile_signals = detect_profile(description)

    return {
        "scope": scope,
        "profile": profile,
        "profile_confidence": confidence,
        "autonomy": "guided",
        "signals": scope_signals + profile_signals,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Inference engine")
    parser.add_argument("--description", required=True, help="User description")
    parser.add_argument("--project-root", help="Project root directory")
    parser.add_argument("--iterate", action="store_true", help="Deprecated — use /shipwright-iterate instead")
    args = parser.parse_args()

    result = infer_settings(args.description, args.project_root)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
