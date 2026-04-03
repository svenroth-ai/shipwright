#!/usr/bin/env python3
"""Classify user intent for Shipwright iterate workflow."""

import json
import re
import sys
from pathlib import Path

FEATURE_KEYWORDS = {"add", "create", "implement", "new", "build", "introduce", "develop"}
CHANGE_KEYWORDS = {"change", "update", "move", "reorder", "rename", "replace", "modify", "adjust", "refactor", "redesign", "restructure", "swap"}
BUG_KEYWORDS = {"fix", "bug", "broken", "error", "doesn't work", "wrong", "crash", "fail", "issue", "problem", "nicht", "kaputt", "fehler"}

# Slash commands and non-code requests to ignore
SKIP_PATTERNS = [
    r"^/",                    # Slash commands
    r"^(hi|hello|hey)\b",    # Greetings
    r"\?$",                   # Pure questions (ending with ?)
]


def classify(message: str, sync_config_path: str | None = None) -> dict:
    """Classify a user message into feature/change/bug/none."""
    msg_lower = message.lower().strip()

    # Skip patterns
    for pattern in SKIP_PATTERNS:
        if re.match(pattern, msg_lower):
            return {"type": "none", "confidence": 0.0, "affected_frs": [], "summary": ""}

    # Count keyword matches
    scores = {"feature": 0, "change": 0, "bug": 0}

    words = set(re.findall(r"\b\w+\b", msg_lower))

    for kw in FEATURE_KEYWORDS:
        if kw in words:
            scores["feature"] += 1

    for kw in CHANGE_KEYWORDS:
        if kw in words:
            scores["change"] += 1

    for kw in BUG_KEYWORDS:
        # Some bug keywords are multi-word
        if kw in msg_lower:
            scores["bug"] += 1

    # Find winner
    max_score = max(scores.values())
    if max_score == 0:
        return {"type": "none", "confidence": 0.0, "affected_frs": [], "summary": ""}

    intent_type = max(scores, key=scores.get)
    # Confidence based on how many keywords matched
    confidence = min(0.5 + (max_score * 0.15), 0.95)

    # Try to find affected FRs from sync config
    affected_frs = []
    if sync_config_path:
        affected_frs = _find_affected_frs(message, sync_config_path)
        if affected_frs:
            confidence = min(confidence + 0.1, 0.95)

    # Generate summary (first 80 chars of message)
    summary = message[:80].strip()
    if len(message) > 80:
        summary += "..."

    return {
        "type": intent_type,
        "confidence": round(confidence, 2),
        "affected_frs": affected_frs,
        "summary": summary,
    }


def _find_affected_frs(message: str, config_path: str) -> list[str]:
    """Check if message mentions files/components mapped in sync config."""
    try:
        config = json.loads(Path(config_path).read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return []

    frs = []
    msg_lower = message.lower()
    for mapping in config.get("mappings", []):
        # Check if any keywords from the pattern match the message
        pattern = mapping.get("pattern", "")
        # Extract meaningful parts from glob pattern
        parts = re.findall(r"\w+", pattern)
        for part in parts:
            if part.lower() in msg_lower and len(part) > 3:
                frs.extend(mapping.get("frs", []))
                break

    return list(set(frs))


def main():
    """CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Classify user intent")
    parser.add_argument("--message", required=True, help="User message to classify")
    parser.add_argument("--sync-config", help="Path to shipwright_sync_config.json")
    args = parser.parse_args()

    result = classify(args.message, args.sync_config)
    print(json.dumps(result))


if __name__ == "__main__":
    main()
