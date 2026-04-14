#!/usr/bin/env python3
"""Classify target Shipwright phase for a task description."""

import json
import re
import sys

PHASE_KEYWORDS: dict[str, set[str]] = {
    "project": {
        "idea", "spec", "requirements", "decompose", "app", "website",
        "project", "concept", "brief", "scope",
    },
    "design": {
        "design", "mockup", "mockups", "ui", "wireframe", "wireframes",
        "layout", "screen", "screens", "visual", "figma", "prototype",
        "landing", "landingpage",
    },
    "plan": {
        "plan", "breakdown", "sections", "roadmap", "schedule",
        "milestones", "estimate",
    },
    "build": {
        # NOTE: "build" (the verb) is intentionally NOT in this set.
        # In user task titles "build a X" almost always means "create a new X",
        # which is a project-creation intent, not the Shipwright build phase.
        # Keeping "build" here made "Build a ToDo-App" classify as build
        # (score 1 via "build") vs project (score 1 via "app") with the tie
        # going to build, which showed a wrong phase badge on the kanban card.
        "implement", "code", "function", "component",
        "refactor", "endpoint", "route", "hook",
    },
    "test": {
        "test", "tests", "e2e", "playwright", "vitest", "unit",
        "coverage", "regression", "bug", "fix",
    },
    "security": {
        "security", "vulnerability", "vulnerabilities", "scan", "cve",
        "pentest",
    },
    "deploy": {
        "deploy", "deployment", "release", "production", "publish",
        "staging", "rollout",
    },
    "changelog": {
        "changelog", "version", "tag", "bump",
    },
    "compliance": {
        "audit", "sbom", "compliance", "traceability", "evidence",
    },
}

PHASE_PRIORITY = [
    "design", "test", "security", "deploy", "compliance", "changelog",
    "plan", "project", "build",
]

DEFAULT_PHASE = "project"


def classify(message: str) -> dict:
    msg_lower = message.lower().strip()

    if not msg_lower:
        return {"phase": DEFAULT_PHASE, "confidence": 0.0, "scores": {}}

    words = set(re.findall(r"\b\w+\b", msg_lower))

    scores: dict[str, int] = {phase: 0 for phase in PHASE_KEYWORDS}
    for phase, keywords in PHASE_KEYWORDS.items():
        for kw in keywords:
            if " " in kw:
                if kw in msg_lower:
                    scores[phase] += 1
            elif kw in words:
                scores[phase] += 1

    max_score = max(scores.values())
    if max_score == 0:
        return {"phase": DEFAULT_PHASE, "confidence": 0.0, "scores": scores}

    winner = next(
        (p for p in PHASE_PRIORITY if scores[p] == max_score),
        max(scores, key=scores.get),
    )
    confidence = min(0.5 + (max_score * 0.15), 0.95)

    return {
        "phase": winner,
        "confidence": round(confidence, 2),
        "scores": scores,
    }


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Classify Shipwright phase")
    parser.add_argument("message", nargs="?", help="Task description to classify")
    parser.add_argument("--message", dest="message_flag", help="Task description (flag form)")
    args = parser.parse_args()

    message = args.message or args.message_flag or ""
    result = classify(message)
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
