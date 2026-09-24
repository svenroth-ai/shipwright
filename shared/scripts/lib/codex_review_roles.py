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

#: Which review roles carry the canonical reasoning-effort contract — ONLY
#: the review-cascade roles the iterate/build skills Task()-invoke and this
#: transport already dispatches (iterate-2026-09-20-m4-codex-subagent-
#: dispatch). Deliberately a STRICT SUBSET of ROLE_SCHEMAS: `plan_review` is
#: out of this iterate's scope (shipwright-plan, not iterate/build — see
#: that iterate's spec's "Out of Scope"), so it carries no entry here and
#: `run_codex_review`'s effort injection skips any role absent from this set.
REASONING_EFFORT_ROLES: frozenset[str] = frozenset({"spec", "code", "doubt"})

if not REASONING_EFFORT_ROLES <= ROLE_SCHEMAS.keys():
    # `raise`, not `assert` -- stripped under `python -O`, exactly the class
    # of import-time table guard `codex_review_model_resolution.py` already
    # documents rejecting `assert` for (doubt-reviewer, low, 2026-09-20).
    raise RuntimeError(
        "REASONING_EFFORT_ROLES must be a subset of ROLE_SCHEMAS — a role with "
        "no schema/transport entry has nothing for this contract to describe"
    )

#: AGENTS.md used to restate this value in prose ("Use gpt-5.6-sol with high
#: reasoning for required review subagents"), pinned by a test reading that
#: text. It deliberately no longer does
#: (iterate-2026-09-23-m5-agents-md-generation-drift, round 2): the prose
#: could only ever show a stale snapshot of what this constant, and
#: `codex_review_model_resolution.py`'s dynamic precedence over it, already
#: govern. `shared/tests/test_agents_md_claude_md_parity.py::
#: test_agents_md_does_not_hardcode_codex_review_models` now guards the
#: opposite direction — that the prose never comes back.
#:
#: Matches the Codex operating policy (review subagents run gpt-6-sol
#: with high reasoning) — a policy the dispatch call never actually
#: enforced until this iterate (no
#: `model_reasoning_effort` reached `codex exec`'s argv at all). Pinned by
#: assertion, not just documented, so a later edit here has to also touch
#: this line consciously — an enum-membership check against Codex CLI's
#: `model_reasoning_effort` values was tried instead and withdrawn: this
#: repo has no reachable copy of that value list to verify it against, so
#: the enum was itself an unverified claim, guarding one hardcoded literal
#: no config path can override today (code-reviewer, low, 2026-09-20). The
#: assert below is knowingly tautological (doubt-reviewer, low, 2026-09-20)
#: -- kept as a deliberate tripwire: a future edit to this literal must also
#: touch this line, not slip through in a larger diff.
#:
#: Confirmed live against real `codex exec`, TWICE, with the shipped
#: production argv (order and flags, including `--ignore-user-config`) --
#: not just this constant in isolation: (1) `-c model_reasoning_effort=high`
#: in its exact shipped position (after `-o`) prints `reasoning effort:
#: high` in codex's own banner and completes; (2) `-c
#: totally_bogus_unrecognized_key=nonsense` in the same position also
#: completes (`reasoning effort: none`, exit 0) rather than failing launch
#: -- codex silently ignores an unrecognized `-c` key instead of erroring,
#: which REBUTS the doubt-reviewer's HIGH claim that an override to a model
#: intolerant of `model_reasoning_effort` turns all three required reviews
#: `not_run`; the empirically-supported risk is the opposite one, addressed
#: below: `transport_note` can claim an effort the call never actually
#: observed (doubt-reviewer, high, 2026-09-20; both probes run 2026-09-20).
CODEX_REVIEW_REASONING_EFFORT = "high"
assert CODEX_REVIEW_REASONING_EFFORT == "high", "tripwire: touching this literal must also touch this comment block"

#: `codex exec`'s sandbox flag is already hardcoded read-only in
#: `run_codex_review`'s argv (Internal Plan Review finding #2's own
#: constraint — no write access for a review-only role); this constant is
#: the same value, named rather than duplicated as a bare string literal at
#: the one other call site that needs it.
CODEX_REVIEW_SANDBOX_MODE = "read-only"


def transport_note_for(role: str, effective_model: str) -> str:
    """The `--transport-note` value `run_codex_review` records for `role`.

    Lives here, next to the two constants it formats, rather than in
    `codex_review_transport.py` — that module sits at its own 300-line cap
    with zero headroom, and this function's only reason to be imported
    there is to read these same two constants (code-reviewer, low,
    2026-09-20). Bare `effective_model` for a role outside
    `REASONING_EFFORT_ROLES` (`plan_review` today).

    ``effective_model`` MUST already have passed
    `codex_review_transport._CODEX_MODEL_SLUG_PATTERN` before it reaches
    here — this function's return value is interpolated into a
    shell-quoted `--transport-note "{transport_note}"` argument by
    `codex_review_dispatch.md`, and this is the one place that formats the
    value into that string (doubt-reviewer, medium, 2026-09-20).
    """
    if role not in REASONING_EFFORT_ROLES:
        return effective_model
    return f"{effective_model} effort={CODEX_REVIEW_REASONING_EFFORT} sandbox={CODEX_REVIEW_SANDBOX_MODE}"
