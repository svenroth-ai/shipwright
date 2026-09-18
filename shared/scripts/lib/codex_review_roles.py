"""Per-role schema and canonical-basename tables for the Codex-CLI
internal-review transport — split from `codex_review_transport.py` to stay
under the 300-line source cap (iterate-2026-09-18-codex-review-tier-config
added the model-override/allowlist logic that pushed it over).
"""

from __future__ import annotations

from pathlib import Path

_SCHEMAS_DIR = Path(__file__).resolve().parents[2] / "schemas"
ROLE_SCHEMAS: dict[str, Path] = {
    "spec": _SCHEMAS_DIR / "codex_spec_review_schema.json",
    "code": _SCHEMAS_DIR / "codex_code_review_schema.json",
    "doubt": _SCHEMAS_DIR / "codex_doubt_review_schema.json",
    "plan_review": _SCHEMAS_DIR / "codex_plan_review_schema.json",
}

ROLE_CANONICAL_BASENAMES: dict[str, str] = {
    "spec": "spec_review_reply.json",
    "code": "code_review_reply.json",
    "doubt": "doubt_review_reply.json",
    # plan_review has no `record_review_pass.py --from` adapter (`plan_internal`
    # is a metadata-only row, review_payloads.py) — the plan site reads this
    # file directly and writes plan.md's `## Internal Plan Review` section
    # itself, it never feeds record_review_pass.py. Still needs a REAL
    # basename distinct from the temp file: `.get(role, tmp_path.name)`'s
    # fallback below made canonical_path == tmp_path itself when this key was
    # absent, so the `finally` unlink deleted the very file just returned as
    # `canonical_path` (spec-reviewer REJECT, 2026-09-17).
    "plan_review": "plan_review_reply.json",
}

assert ROLE_SCHEMAS.keys() == ROLE_CANONICAL_BASENAMES.keys(), (
    "ROLE_SCHEMAS and ROLE_CANONICAL_BASENAMES must name the same roles — a "
    "role missing its basename here is the exact defect the direct index in "
    "run_codex_review below now fails loudly on instead of silently deleting "
    "the payload (code-reviewer REJECT, 2026-09-17)"
)
