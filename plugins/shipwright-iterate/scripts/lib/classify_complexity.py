#!/usr/bin/env python3
"""Two-stage complexity classifier for Shipwright iterate workflow.

Stage 1 (this script): Quick estimate from prompt + sync config keywords.
Stage 2 (AI agent): Repo scout confirms/upgrades via structured scan.

Output: JSON with estimate, confidence, risk_flags, and signals.
"""

import json
import re
import sys
from pathlib import Path

# Self-bootstrap: sibling modules must resolve even under
# importlib.spec_from_file_location (contracts/iterate.py, test harnesses).
_LIB_DIR = str(Path(__file__).resolve().parent)
if _LIB_DIR not in sys.path:
    sys.path.insert(0, _LIB_DIR)

from complexity_history import load_history_prior  # noqa: E402
from complexity_vocabulary import (  # noqa: E402, F401 — re-exported surface
    COMPLEXITY_ORDER, SCOPE_LARGE_KEYWORDS, SCOPE_MEDIUM_KEYWORDS,
    SCOPE_SMALL_KEYWORDS, estimate_scope, match_scope_keyword,
)

# --- Canonical Risk Taxonomy ---
# One authoritative list. Referenced by SKILL.md, references, and tests.

RISK_TAXONOMY = {
    "touches_auth": {
        "patterns": [
            r"auth", r"login", r"signup", r"sign.?up", r"session",
            r"middleware\.ts", r"supabase/.*auth",
        ],
        "min_complexity": "small",
        "enforces": ["mandatory_review"],
    },
    "touches_rls": {
        "patterns": [r"rls", r"row.?level", r"policy", r"policies"],
        "min_complexity": "small",
        "enforces": ["mandatory_review"],
    },
    "touches_middleware": {
        "patterns": [r"middleware", r"next\.config"],
        "min_complexity": "small",
        "enforces": ["mandatory_review"],
    },
    "touches_migrations": {
        "patterns": [
            r"migration", r"migrate", r"schema", r"alter\s+table",
            r"create\s+table", r"supabase/migrations",
        ],
        "min_complexity": "small",
        "enforces": ["mandatory_review", "down_sql"],
    },
    "touches_billing": {
        "patterns": [
            r"stripe", r"payment", r"checkout", r"webhook",
            r"subscription", r"billing", r"invoice",
        ],
        "min_complexity": "small",
        "enforces": ["mandatory_review"],
    },
    "touches_shared_infra": {
        "patterns": [
            r"src/lib/", r"src/components/ui/", r"layout",
            r"shared.*component", r"global.*css", r"globals\.css",
        ],
        "min_complexity": "small",
        "enforces": ["full_test_suite"],
    },
    "touches_public_api": {
        "patterns": [
            r"api/", r"route\.ts", r"endpoint", r"export.*type",
            r"public.*api",
        ],
        "min_complexity": "small",
        "enforces": ["mandatory_review"],
    },
    "cross_split": {
        "patterns": [],  # Detected by sync config, not keywords
        "min_complexity": "medium",
        "enforces": ["full_review", "full_test_suite"],
    },
    "touches_build": {
        # Triggers performance budget check on iterate (mirrors what
        # /shipwright-test Step 3.8 runs in the pipeline). Catches
        # dependency / build-config changes that can blow bundle size or
        # break Lighthouse score without anyone noticing until the next
        # full pipeline. Patterns match prompt keywords; diff-driven
        # detection uses TOUCHES_BUILD_FILE_PATTERNS via touches_build_files().
        "patterns": [
            r"package\.json", r"package-lock\.json",
            r"yarn\.lock", r"pnpm-lock\.yaml", r"bun\.lockb",
            r"npm-shrinkwrap\.json",
            r"next\.config\.", r"vite\.config\.",
            r"tailwind\.config\.", r"webpack\.config\.",
            r"rollup\.config\.", r"tsconfig\.json",
        ],
        "min_complexity": "small",
        "enforces": ["performance_test_layer"],
    },
    "touches_io_boundary": {
        # Triggers Boundary Probe sub-step in Build TDD (see SKILL.md
        # Path A Step 6 + Phase Matrix). Catches producer/consumer
        # round-trip bugs where unit tests of each side pass but the
        # serialized format on disk drifts (motivating example: env
        # iterate's BOM + inline-comment bugs that survived 47 unit tests
        # AND two external reviews). Diff-driven detection uses
        # IO_BOUNDARY_FILE_PATTERNS via is_io_boundary_change().
        #
        # E spec MEDIUM-A1: anchored / specific patterns only. The original
        # bare verb prefixes (`parse_`, `load_`, `write_`, `\bdump\b`,
        # `serialize`, `write_text`, `read_text`) fired on unrelated
        # prompts ("rewrite the load_user route", "improve dump utility",
        # "add parse_query helper", "rewrite the page header"). Replaced
        # with anchored function names + stdlib calls + concrete file
        # patterns. The diff-driven `is_io_boundary_change()` path-match
        # remains the primary detection — these patterns only cover
        # prompt-text classification.
        "patterns": [
            # Concrete file patterns (still tight).
            r"\.env\b",
            r"\bhooks\.json\b",
            r"\bsettings\.json\b",
            r"_config\.json",
            r"_state\.json",
            # Anchored function names (specific, not verb prefixes).
            r"\bparse_env\b",
            # Specific stdlib calls (require the module qualifier).
            r"\bjson\.dump(s)?\b",
            r"\bjson\.loads?\b",
            r"\byaml\.dump\b",
            r"\byaml\.safe_load\b",
        ],
        "min_complexity": "small",
        "enforces": ["round_trip_test"],
    },
}

# File-glob patterns for diff-driven touches_build detection (basename match).
TOUCHES_BUILD_FILE_PATTERNS = (
    "package.json", "package-lock.json", "yarn.lock",
    "pnpm-lock.yaml", "bun.lockb", "npm-shrinkwrap.json",
    "next.config.js", "next.config.ts", "next.config.mjs", "next.config.cjs",
    "vite.config.js", "vite.config.ts", "vite.config.mjs",
    "tailwind.config.js", "tailwind.config.ts",
    "webpack.config.js", "webpack.config.ts",
    "rollup.config.js", "rollup.config.ts", "rollup.config.mjs",
    "tsconfig.json",
)


def touches_build_files(changed_files: list[str]) -> bool:
    """Return True if any changed file matches a build-touching pattern.

    Diff-driven detection — caller passes `git diff --name-only` output.
    Match is by basename only (path-agnostic).
    """
    if not changed_files:
        return False
    for path in changed_files:
        name = path.replace("\\", "/").rsplit("/", 1)[-1]
        if name in TOUCHES_BUILD_FILE_PATTERNS:
            return True
    return False


# Regex patterns (anchored on basename) for diff-driven
# touches_io_boundary detection. Used by is_io_boundary_change() —
# producer/consumer round-trip bugs typically surface in these file
# shapes:
#   - .env / .env.local / .env.* — env-iterate motivating example
#   - hooks.json / settings.json — hook chain config
#   - <name>_config.json — shipwright_*_config.json family
#   - <name>_state.json — loop_state.json, external_review_state.json, ...
# The path-match path covers the producer/consumer-in-same-diff case for
# all known real-world examples. AST-pair detection (producer + consumer
# living in different .py files in the same diff) is explicitly deferred
# per Sub-Iterate A spec — file paths cover 90%+ of cases empirically.
IO_BOUNDARY_FILE_PATTERNS = (
    r"(^|/)\.env(\..+)?$",
    r"(^|/)hooks\.json$",
    r"(^|/)settings\.json$",
    r"(^|/)[^/]*_config\.json$",
    r"(^|/)[^/]*_state\.json$",
)


def is_io_boundary_change(changed_files: list[str] | None) -> bool:
    """Return True if any changed file matches an IO boundary pattern.

    Diff-driven detection — caller passes `git diff --name-only` output.
    Path normalization handles Windows backslashes.

    # DEFERRED — AST-pair detection (writer + reader living in different
    # .py files within the same diff) is intentionally NOT implemented.
    # See `.shipwright/planning/iterate/campaigns/iterate-skill-hardening/
    # sub-iterates/A-boundary-tests-foundation.md` Acceptance Criteria
    # line 53-60: the original AC text read this as required, but the
    # Implementation Plan allowed deferral. Per E spec HIGH-1, A's spec
    # was relabeled `(deferred)` with this rationale: path-match catches
    # every known real-world boundary bug (the env-iterate BOM + inline-
    # comment bugs both touched `.env` files in the diff), so the
    # additional complexity of AST-pair scanning is not justified
    # empirically. Reactivate when a real-world bug emerges that needs it.
    """
    if not changed_files:
        return False
    for path in changed_files:
        normalized = path.replace("\\", "/")
        for pattern in IO_BOUNDARY_FILE_PATTERNS:
            if re.search(pattern, normalized):
                return True
    return False


def _complexity_index(level: str) -> int:
    """Return numeric index for complexity comparison."""
    return COMPLEXITY_ORDER.index(level)


def detect_risk_flags(message: str) -> list[dict]:
    """Detect risk flags from message using canonical taxonomy."""
    msg_lower = message.lower()
    flags = []
    for flag_name, flag_def in RISK_TAXONOMY.items():
        if flag_name == "cross_split":
            continue  # Needs sync config, not keyword matching
        for pattern in flag_def["patterns"]:
            if re.search(pattern, msg_lower):
                flags.append({
                    "flag": flag_name,
                    "min_complexity": flag_def["min_complexity"],
                    "enforces": flag_def["enforces"],
                })
                break
    return flags


def detect_cross_split(
    message: str, sync_config_path: str | None
) -> dict | None:
    """Check if change spans multiple planning splits."""
    if not sync_config_path:
        return None
    try:
        config = json.loads(Path(sync_config_path).read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return None

    msg_lower = message.lower()
    splits_hit = set()
    for mapping in config.get("mappings", []):
        pattern = mapping.get("pattern", "")
        parts = re.findall(r"\w+", pattern)
        for part in parts:
            if part.lower() in msg_lower and len(part) > 3:
                for fr in mapping.get("frs", []):
                    # FR format: FR-NN.XX — extract split number
                    m = re.match(r"FR-(\d+)\.", fr)
                    if m:
                        splits_hit.add(m.group(1))
                break

    if len(splits_hit) >= 2:
        flag_def = RISK_TAXONOMY["cross_split"]
        return {
            "flag": "cross_split",
            "min_complexity": flag_def["min_complexity"],
            "enforces": flag_def["enforces"],
            "splits": sorted(splits_hit),
        }
    return None


def classify(
    message: str,
    sync_config_path: str | None = None,
    project_root=None,
) -> dict:
    """Stage 1: Quick complexity estimate from prompt + risk flags.

    Canonical, history-aware path (estimate_scope = legacy vocabulary-only).
    Scope precedence: keyword match > history prior > trivial default;
    risk floors apply on top either way. Stage 2 (repo scout) may upgrade.
    """
    # Detect risk flags
    risk_flags = detect_risk_flags(message)

    # Cross-split check
    cross_split = detect_cross_split(message, sync_config_path)
    if cross_split:
        risk_flags.append(cross_split)

    # Scope estimate: keyword > history prior > default.
    keyword_level = match_scope_keyword(message)
    history = None
    if keyword_level is not None:
        scope_estimate, prior_source = keyword_level, "keyword"
    else:
        history = load_history_prior(project_root)
        if history is not None:
            scope_estimate, prior_source = history["prior"], "history"
        else:
            scope_estimate, prior_source = "trivial", "default"

    # Apply risk flag minimums
    effective_min = "trivial"
    for flag in risk_flags:
        flag_min = flag["min_complexity"]
        if _complexity_index(flag_min) > _complexity_index(effective_min):
            effective_min = flag_min

    # Final estimate = max(scope_estimate, risk_floor)
    if _complexity_index(effective_min) > _complexity_index(scope_estimate):
        estimate = effective_min
    else:
        estimate = scope_estimate

    # Confidence scoring
    confidence = 0.5
    if risk_flags:
        confidence += 0.15  # Risk flags boost confidence
    if sync_config_path and Path(sync_config_path).exists():
        confidence += 0.1  # Sync config available
    if estimate in ("large", "medium"):
        confidence += 0.1  # Higher scope = more confident in needing structure
    confidence = min(round(confidence, 2), 0.95)

    # Build signals for Repo Scout
    flag_names = [f["flag"] for f in risk_flags]
    enforcements = set()
    for flag in risk_flags:
        enforcements.update(flag.get("enforces", []))

    return {
        "estimate": estimate,
        "confidence": confidence,
        "risk_flags": flag_names,
        "enforcements": sorted(enforcements),
        "signals": {
            "scope_keyword_estimate": keyword_level or "trivial",
            "prior_source": prior_source,
            "history_prior": history["prior"] if history else None,
            "history_n": history["n"] if history else 0,
            "risk_floor": effective_min,
            "cross_split": cross_split is not None,
            "has_sync_config": (
                sync_config_path is not None
                and Path(sync_config_path).exists()
            ),
        },
    }


def main():
    """CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Stage 1 complexity estimate for Shipwright iterate"
    )
    parser.add_argument("--message", required=True, help="User message")
    parser.add_argument("--sync-config", help="Path to shipwright_sync_config.json")
    parser.add_argument(
        "--project-root",
        help="Enables the history prior from .shipwright/agent_docs/iterates/",
    )
    args = parser.parse_args()

    result = classify(args.message, args.sync_config, args.project_root)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
