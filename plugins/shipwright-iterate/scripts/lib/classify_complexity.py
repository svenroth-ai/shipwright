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
# Diff-driven risk detectors live in a dedicated module (kept under the bloat
# limit). Re-exported here so existing importers — shared.contracts.iterate,
# the test-plugin boundary report, the detector tests — keep resolving them
# from classify_complexity. SSoT for the patterns is risk_detectors.
from risk_detectors import (  # noqa: E402, F401 — re-exported surface
    CI_SUPPLYCHAIN_FILE_PATTERNS, CROSS_COMPONENT_FILE_PATTERNS, IO_BOUNDARY_FILE_PATTERNS,
    TOUCHES_BUILD_FILE_PATTERNS, is_ci_supplychain_change, is_cross_component_change,
    is_io_boundary_change, touches_build_files,
)

# Canonical risk taxonomy — one authoritative list, referenced by SKILL.md,
# references and tests. Lives in its own module (it only ever grows);
# re-exported here so existing importers keep resolving it.
from risk_taxonomy import RISK_TAXONOMY  # noqa: E402, F401 — re-exported surface


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
        # WP8/F24: utf-8-sig (BOM-tolerant) — non-ASCII FR titles otherwise crash on cp1252.
        config = json.loads(Path(sync_config_path).read_text(encoding="utf-8-sig"))
    except (FileNotFoundError, json.JSONDecodeError, UnicodeDecodeError):
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
    parser.add_argument("--run-id", help="Persist the session plan under .shipwright/ (requires --project-root; no-ops otherwise)")
    args = parser.parse_args()

    result = classify(args.message, args.sync_config, args.project_root)
    print(json.dumps(result, indent=2))
    # Additive, opt-in: persist the WebUI session plan (never perturbs stdout;
    # fail-soft so a persist error can't abort the iterate session).
    if args.run_id and args.project_root:
        from session_plan import persist_session_plan_safe
        persist_session_plan_safe(result, args.run_id, args.project_root)


if __name__ == "__main__":
    main()
