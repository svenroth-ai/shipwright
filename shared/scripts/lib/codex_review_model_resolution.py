"""Model-slug resolution for the Codex-CLI internal-review transport.

Split out of ``codex_review_transport.py`` to keep that module under its
300-line source cap (iterate-2026-09-19-codex-reviewer-session-override).
Unlike a pure extraction, this module also ADDS the session-env-var stage
(step 2 below) to the transport's own model-resolution contract — see that
module's own docstring for exactly what changed.

Precedence for a review role's Codex model, resolved fresh on every call
(nothing here is cached across calls or persisted anywhere):

1. An explicit ``model`` argument — the caller's own per-invocation override
   (``review_via_codex.py``'s ``--codex-model`` flag).
2. This role's session-scoped env var (:data:`ROLE_TO_CODEX_ENV_VAR`) —
   ambient, read fresh on every call, nothing shipwright-side ever persists
   it. Exists because ``codex exec`` has no first-party flag the shared
   Python reviewer scripts can read at review time for a value chosen once
   per session; a plain env var reaches every dispatch site for free once
   set, since Codex CLI's own ``shell_environment_policy.inherit=all``
   already carries ambient env into the script invocations it makes — no
   change needed to ``codex_review_dispatch.md``'s fixed per-role commands.
3. The persisted ``shipwright_model_config.json`` key
   (:data:`ROLE_TO_CODEX_CONFIG_KEY`), resolved from ``worktree_root``'s
   MAIN repo root via ``lib.model_tier_config.load_model_config``.
4. The caller-supplied ``default`` (``codex_review_transport.CODEX_REVIEW_MODEL``
   in practice) — never imported back from that module here, to avoid a
   circular import (it imports *this* module).

Only the SOURCE label (never the resolved value itself) is returned
alongside the model, on purpose: `run_codex_review`'s syntactic allowlist
embeds the source in its error message so an operator can tell which axis
produced a hostile value, without ever echoing the value itself into a
string another tool (`codex_review_dispatch.md`) interpolates into a
double-quoted shell argument — the same "never echo" contract
`codex_review_transport.py` already enforces for its own error messages.

**Independent of the reasoning-effort axis.** For a `REASONING_EFFORT_ROLES`
role (`spec`/`code`/`doubt`), `run_codex_review` always adds `-c
model_reasoning_effort=<CODEX_REVIEW_REASONING_EFFORT>` to `codex exec`'s
argv, keyed on ROLE, never on which model this function resolves — an
override (any of the four stages above) to a model that does not accept
`model_reasoning_effort` makes that `codex exec` invocation fail at launch;
the failure surfaces as an ordinary `status: error` result, not a silent
skip of the flag (Internal Plan Review, medium, 2026-09-20).
"""

from __future__ import annotations

import os
from collections.abc import Set as AbstractSet
from pathlib import Path

# ALWAYS package-qualified, never the bare-try-first pattern used elsewhere in
# `shared/scripts/lib/*.py` -- the `model_tier_config` import below only
# supports being loaded as `lib.model_tier_config` (its own `.repo_root`
# sibling import needs that package context), and since that import runs
# unconditionally regardless of which arm a bare/package-qualified try for
# `codex_review_roles` took, this whole module can only ever finish loading
# with `shared/scripts` already on sys.path -- so a bare-try for
# `codex_review_roles` here would be dead code, not a real fallback (doubt-
# reviewer finding, iterate-2026-09-19-codex-reviewer-session-override).
from lib.codex_review_roles import ROLE_SCHEMAS
from lib.model_tier_config import load_model_config

__all__ = [
    "ROLE_TO_CODEX_CONFIG_KEY",
    "ROLE_TO_CODEX_ENV_VAR",
    "resolve_codex_review_model",
]

#: role -> the `shipwright_model_config.json` key that configures its
#: persisted Codex reviewer identity. `plan_review` gets its own key so a
#: project pinning the spec/code/doubt cascade never silently drags the
#: plan reviewer's model along with it (same reasoning as the Claude-side
#: `plan_review` role staying independent of `review`).
ROLE_TO_CODEX_CONFIG_KEY: dict[str, str] = {
    "spec": "codex_review",
    "code": "codex_review",
    "doubt": "codex_review",
    "plan_review": "codex_plan_review",
}

#: role -> the env var carrying a SESSION-scoped override for that role's
#: Codex reviewer model. Mirrors the two config keys above one-to-one.
ROLE_TO_CODEX_ENV_VAR: dict[str, str] = {
    "spec": "SHIPWRIGHT_CODEX_REVIEW_MODEL",
    "code": "SHIPWRIGHT_CODEX_REVIEW_MODEL",
    "doubt": "SHIPWRIGHT_CODEX_REVIEW_MODEL",
    "plan_review": "SHIPWRIGHT_CODEX_PLAN_REVIEW_MODEL",
}

def _check_role_tables_complete(
    role_keys: AbstractSet[str], config_keys: AbstractSet[str], env_keys: AbstractSet[str],
) -> None:
    """`raise`, not `assert` -- stripped under `python -O`; a role missing
    from either table would otherwise reach a `KeyError` deep inside
    resolution instead of failing loudly at import time (mirrors the
    equivalent guard `review_via_codex.py` carried for its own, now-moved,
    mapping). A plain function, not inline module-level code, so a test can
    exercise the failure directly rather than via `importlib.reload` --
    reloading this module re-runs its own bare-import fallback, which is
    fragile across a shared pytest process (iterate-2026-09-19-codex-reviewer-session-override)."""
    if config_keys != role_keys or env_keys != role_keys:
        raise RuntimeError(
            "ROLE_TO_CODEX_CONFIG_KEY and ROLE_TO_CODEX_ENV_VAR must both name every "
            "role in ROLE_SCHEMAS -- a role missing from either would raise KeyError "
            "instead of failing loudly at import time"
        )


_check_role_tables_complete(ROLE_SCHEMAS.keys(), ROLE_TO_CODEX_CONFIG_KEY.keys(), ROLE_TO_CODEX_ENV_VAR.keys())


def resolve_codex_review_model(
    role: str, worktree_root: Path, model: str | None, default: str,
) -> tuple[str, str]:
    """Resolve ``role``'s effective Codex model slug and where it came from.

    Returns ``(requested_model, source)`` — ``source`` is a fixed, literal
    label (never derived from an operator-authored value), safe to embed in
    an error message. Does not validate the resolved slug — that stays
    `run_codex_review`'s own job (the syntactic allowlist), so this module
    never has to decide what "hostile" means.

    ``role`` must already be a validated member of `ROLE_SCHEMAS` — this is
    a private helper for `run_codex_review`'s own model-resolution step.
    """
    if model is not None:
        return model, "the explicit model= argument"
    env_value = os.environ.get(ROLE_TO_CODEX_ENV_VAR[role], "").strip()
    if env_value:
        return env_value, f"the {ROLE_TO_CODEX_ENV_VAR[role]} environment variable"
    config_key = ROLE_TO_CODEX_CONFIG_KEY[role]
    configured = load_model_config(worktree_root).get(config_key)
    if configured is not None:
        return configured, f"shipwright_model_config.json's {config_key!r} key"
    return default, "the hardcoded default"
