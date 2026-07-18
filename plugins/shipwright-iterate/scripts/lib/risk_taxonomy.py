"""Canonical risk taxonomy for the Shipwright iterate workflow.

Extracted from ``classify_complexity.py`` (iterate-2026-07-18-ci-supplychain-risk-flag)
so that load-bearing module stays under the bloat limit — the same move the
diff-driven detectors got earlier. This registry only grows: every new risk flag
adds an entry, so it needed a home of its own rather than a widening exception.

SSoT. ``classify_complexity`` re-exports ``RISK_TAXONOMY`` so every existing
importer (SKILL.md consumers, shared.contracts.iterate, the taxonomy tests) keeps
resolving it from there.
"""

from __future__ import annotations

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
        # IO_BOUNDARY_FILE_PATTERNS via is_io_boundary_change() (the primary
        # detection). E spec MEDIUM-A1: prompt patterns are anchored function
        # names + stdlib calls + concrete file names only — the original loose
        # verb prefixes (`parse_`, `load_`, `write_`, `serialize`, …) fired on
        # unrelated prompts ("rewrite the page header", "add parse_query").
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
    "cross_component": {
        # Forces INTEGRATION coverage (Ledger `category:"integration"`), enforced
        # non-dodgeably by the F11 verifier `check_integration_coverage` which
        # RECOMPUTES the flag from the diff via CROSS_COMPONENT_FILE_PATTERNS. The
        # composition axis the boundary/app-surface machinery missed. These message
        # patterns are anchored Run-Summary hints; the diff path is primary.
        "patterns": [
            r"\bcross.?component\b",
            r"\bmerge machinery\b",
            r"\bchurn (resolver|merge)\b",
            r"\bintegrate_main\b",
            r"\bhook fan.?out\b",
            r"\bcampaign (drain|serial)\b",
            r"\bpipeline phase\b",
        ],
        "min_complexity": "medium",
        "enforces": ["integration_coverage", "full_test_suite"],
    },
    "touches_ci_supplychain": {
        # CI trust boundary. Enforced non-dodgeably by `check_ci_supplychain_ack`
        # (recomputes from the diff, demands a recorded acknowledgement); these
        # hints are Run-Summary only. Rationale + the "never means pin everything"
        # rule: SKILL.md taxonomy row + docs/hooks-and-pipeline.md.
        # Hints are anchored to identifiers, not bare English — a plain
        # `\bworkflow\b` fires on "the iterate workflow" (message-prose FP class).
        "patterns": [
            r"\bgithub (actions?|workflows?)\b",
            r"\bworkflow file\b",
            r"\.github\b",
            r"\bdependabot\b",
            r"\brenovate\b",
            r"\bci (trust|supply.?chain)\b",
        ],
        "min_complexity": "small",
        "enforces": ["mandatory_review", "ci_supplychain_ack"],
    },
}
