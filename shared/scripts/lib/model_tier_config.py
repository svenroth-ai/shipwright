"""Per-role Claude model tier resolution for spawned subagents.

Every agent definition under ``plugins/*/agents/`` carries ``model: inherit``,
so a subagent runs on whatever the spawning session runs on. When the operator
drops the session to a cheaper tier for cost, every ``inherit`` agent follows —
including the review cascade and the unattended finalization drivers, silently.

This module resolves, per role (``review`` / ``finalization`` / ``execution``),
which tier a spawn should use. Precedence: an explicit per-run flag beats the
project config, which beats "unset". Unset and the explicit literal
``"inherit"`` are the SAME value — both mean "omit the Agent tool's ``model``
parameter", which is bit-identical to today's behavior. There is no
``model: inherit`` value the Agent tool itself understands; omitting the
parameter is how deferral is expressed, and this module's job stops at handing
back the resolved tier string — the caller (skill prose, executed by the LLM
driving the session) turns ``"inherit"`` into "no parameter" at the spawn site.

Config file: ``<MAIN repo root>/shipwright_model_config.json`` (schema:
``shared/schemas/model_config.schema.json``). Resolved from the MAIN repo
root, not ``project_root`` verbatim — a linked worktree's own copy would
silently diverge from what the operator configured once
(``lib.repo_root.resolve_main_repo_root``), the same rule durable artifacts
already follow.

Deliberately NOT built: a role registry (roles are the three names below,
enumerated directly) and frontmatter pins (``model: opus``/``model: sonnet``
hardcoded into agent ``.md`` files). Both were designed and dropped in a prior
attempt at this feature — see
``.shipwright/planning/iterate/iterate-agent-model-tiers-BRIEF.md``. A pin in
either direction removes a plugin consumer's choice; this module only ever
adds a call-time parameter, never edits frontmatter.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

# Package-relative import — a module inside lib/ importing a lib/ sibling
# must use `.repo_root`, never a `sys.path.insert` + absolute `lib.repo_root`
# import, per ADR-044: the latter binds/pollutes `sys.modules['lib']` when a
# detective execs this module under a sentinel name (see events_log.py).
# Every current importer of this module already puts `shared/scripts` on
# `sys.path` before importing it, so the package context this relies on is
# already established by the time this line runs.
from .repo_root import resolve_main_repo_root

#: The three spawn roles this feature distinguishes. Not every role has a
#: live consuming spawn site in every skill (e.g. iterate has no
#: execution-role Agent-tool spawn of its own — browser-fixer is build's) —
#: that is a wiring fact about the skills, not a constraint this resolver
#: enforces.
ROLES: frozenset[str] = frozenset({"review", "finalization", "execution"})

#: Valid tier literals for a role value (``review``/``finalization``/``execution``
#: keys, and the per-run flag value). ``inherit`` is explicit-deferral.
TIERS: frozenset[str] = frozenset({"opus", "sonnet", "haiku", "inherit"})

#: Valid tier literals for a ``floors`` entry. ``inherit`` is not orderable,
#: so it cannot be a floor.
RANKED_TIERS: frozenset[str] = frozenset({"opus", "sonnet", "haiku"})

#: Rank order low-to-high, for floor comparisons.
RANK: dict[str, int] = {"haiku": 1, "sonnet": 2, "opus": 3}

_CONFIG_FILENAME = "shipwright_model_config.json"


class ModelTierConfigError(ValueError):
    """An unknown role was requested of the resolver."""


def _warn(message: str) -> None:
    sys.stderr.write(f"warning: {message}\n")


def _repr_truncated(value: Any, limit: int = 60) -> str:
    """``repr(value)``, capped — an operator-authored config value that is
    invalid still gets echoed into a warning the driving LLM's tool output
    carries verbatim, so an unbounded value (a megabyte-long string) must not
    be handed through whole."""
    text = repr(value)
    return text if len(text) <= limit else f"{text[:limit]}...(truncated)"


def _config_path(project_root: Path | str) -> Path:
    """The config file's location — the MAIN repo root, worktree-aware.

    Falls back to ``project_root`` itself when main-root resolution fails
    (non-git project, git unavailable) — the same fail-soft contract every
    other caller of :func:`resolve_main_repo_root` uses.
    """
    project_root = Path(project_root)
    main_root = resolve_main_repo_root(project_root)
    return (main_root or project_root) / _CONFIG_FILENAME


def load_model_config(project_root: Path | str) -> dict[str, Any]:
    """Read ``shipwright_model_config.json`` from the MAIN repo root.

    Defensive: a missing file returns ``{}`` silently (the default,
    all-inherit configuration). Malformed JSON, or a file that cannot be read
    or decoded, returns ``{}`` and warns on stderr, so an operator sees why an
    override did not take effect rather than the run silently reverting to
    defaults. Any role or floor value outside the valid tier set is DROPPED
    (not raised, even when the value is a JSON array/object rather than a
    wrong string) with a stderr warning and only a length-capped echo — a
    config file is operator-authored, but it is still read the same way any
    other JSON input at a trust boundary is: validated before the value can
    reach a rendered Agent-tool call or a shell-invoked CLI flag. An
    unrecognized top-level or ``floors`` key also warns rather than being
    silently ignored, since a typo'd key name (``"reviews"``, ``"Review"``)
    is the likeliest authoring mistake and is otherwise indistinguishable
    from the file silently reverting to defaults.
    """
    path = _config_path(project_root)
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        _warn(f"malformed {_CONFIG_FILENAME} at {path} ({exc.msg} line {exc.lineno}); ignoring")
        return {}
    except (OSError, UnicodeDecodeError) as exc:
        _warn(f"unreadable {_CONFIG_FILENAME} at {path} ({exc}); ignoring")
        return {}
    if not isinstance(raw, dict):
        _warn(f"{_CONFIG_FILENAME} at {path} is not a JSON object; ignoring")
        return {}

    unknown_top = sorted(set(raw) - ROLES - {"floors"})
    if unknown_top:
        _warn(f"{_CONFIG_FILENAME}: unrecognized key(s) {unknown_top}; ignoring")

    cleaned: dict[str, Any] = {}
    for role in ROLES:
        value = raw.get(role)
        if value is None:
            continue
        # `isinstance` first: an unhashable value (a JSON array or object) in
        # `value in TIERS` would raise TypeError, not just fail the check —
        # a malformed config must fail SOFT even when the mistake is a
        # nested object, not just a wrong-string typo.
        if isinstance(value, str) and value in TIERS:
            cleaned[role] = value
        else:
            _warn(f"{_CONFIG_FILENAME}: {role!r} has an invalid tier "
                  f"{_repr_truncated(value)}; ignoring key")

    floors_raw = raw.get("floors")
    if isinstance(floors_raw, dict):
        unknown_floor = sorted(set(floors_raw) - ROLES)
        if unknown_floor:
            _warn(f"{_CONFIG_FILENAME}: floors has unrecognized key(s) {unknown_floor}; ignoring")
        floors_cleaned: dict[str, str] = {}
        for role in ROLES:
            value = floors_raw.get(role)
            if value is None:
                continue
            if isinstance(value, str) and value in RANKED_TIERS:
                floors_cleaned[role] = value
            else:
                _warn(f"{_CONFIG_FILENAME}: floors.{role} has an invalid tier "
                      f"{_repr_truncated(value)}; ignoring key")
        if floors_cleaned:
            cleaned["floors"] = floors_cleaned
    elif floors_raw is not None:
        _warn(f"{_CONFIG_FILENAME}: 'floors' is not a JSON object; ignoring")

    return cleaned


def resolve_model_tier(
    role: str,
    project_root: Path | str,
    flag_value: str | None = None,
    *,
    _config: dict[str, Any] | None = None,
) -> tuple[str, str]:
    """Resolve the tier for ``role``. Returns ``(resolved_tier, source)``.

    ``resolved_tier`` is always a member of :data:`TIERS` — never ``None``.
    ``source`` is one of ``"flag"``, ``"project_config"``, ``"unset"``.

    Precedence: an explicit, valid ``flag_value`` wins. Otherwise the project
    config's value for ``role`` wins. Otherwise ``"inherit"`` — the same
    value an explicit ``inherit`` flag or config entry would produce, per this
    module's docstring.

    An invalid ``flag_value`` (not a member of :data:`TIERS`) is treated as
    not given — it never overrides a valid project config value, and a
    warning is emitted so a typo'd flag doesn't silently defer to session
    default without the operator noticing.

    Raises :class:`ModelTierConfigError` if ``role`` is not one of
    :data:`ROLES`.

    ``_config`` is a private hook for a caller resolving multiple roles in one
    invocation (``resolve_model_tier.py``) to load the config file once and
    reuse it, instead of a fresh ``load_model_config`` per role. Callers
    outside this module should not pass it — omit it and the config is loaded
    normally.
    """
    if role not in ROLES:
        raise ModelTierConfigError(f"unknown role: {role!r}. Expected one of: {sorted(ROLES)}")

    if flag_value is not None:
        if flag_value in TIERS:
            return flag_value, "flag"
        _warn(f"--{role}-model={flag_value!r} is not a valid tier {sorted(TIERS)}; ignoring")

    config = _config if _config is not None else load_model_config(project_root)
    config_value = config.get(role)
    if config_value in TIERS:
        return config_value, "project_config"

    return "inherit", "unset"


def agent_model_param(resolved_tier: str) -> str | None:
    """The value to pass as the Agent tool's ``model`` parameter.

    ``"inherit"`` means "omit the parameter" — the Agent tool has no
    ``inherit`` literal of its own; deferral is expressed by absence.
    """
    return None if resolved_tier == "inherit" else resolved_tier
