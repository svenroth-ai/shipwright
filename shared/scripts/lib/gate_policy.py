"""Single-session phase-gate policy mechanism (Campaign 2026-07-07, SS2).

The enabler for the single-session pipeline. Every interactive
``AskUserQuestion`` + END-TURN gate in the project/design/plan/build/deploy
phase skills is cataloged in ``shared/config/gate_catalog.json`` with a per-gate
policy:

  * ``auto-default``          — proceed with the documented answer, no END-TURN;
  * ``orchestrator-approve``  — STOP and hand a gate-pending result to the
                                orchestrator to surface to a human;
  * ``hard-stop``             — ALWAYS stop for an explicit human decision
                                (constitution-locked; no autonomy bypasses it).

Inert outside a driven pipeline run: for a standalone / adopted / mode-less / v1 /
missing config every gate resolves to ``interactive``. The resolver NEVER
auto-answers a constitution-flagged gate (defense-in-depth on the validator).

``shared/config/gate_catalog.md`` is GENERATED from the JSON beside it by
``render_catalog_markdown`` — edit the JSON, then regenerate.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from lib.atomic_write import durable_read_text
from lib.gate_catalog_render import render_catalog_doc
from lib.gate_unattended import unattended_answer_for, validate_unattended

# Policies (order = escalation strength).
AUTO_DEFAULT = "auto-default"
ORCHESTRATOR_APPROVE = "orchestrator-approve"
HARD_STOP = "hard-stop"
POLICIES = (AUTO_DEFAULT, ORCHESTRATOR_APPROVE, HARD_STOP)

# Effective policy outside a driven pipeline run: the mechanism is inert.
INTERACTIVE = "interactive"

FIRES = ("always", "conditional", "never")
COVERED_PHASES = ("project", "design", "plan", "build", "test", "changelog", "deploy")

# ``single_session`` is the sole pipeline mode (mirror of run_config.v2 /
# orchestrator_pkg.constants — shared can't import a plugin).
SINGLE_SESSION = "single_session"

# Sentinel for "NOT a driven pipeline run" — standalone / adopted / mode-less / v1 /
# missing / corrupt config. NOT a pipeline mode: it exists only so the gate mechanism
# has something to key inertness on. The removed "multi_session" literal used to play
# this role; dropping it without a replacement sentinel would have flipped every
# standalone project from `interactive` gates to auto-answered ones. Activation is
# EXPLICIT-LITERAL-ONLY: only `mode == "single_session"` turns gates on.
INERT_MODE = "standalone"

_REQUIRED_GATE_KEYS = ("id", "phase", "policy", "default_answer", "constitution", "fires", "summary")

_CATALOG_PATH = Path(__file__).resolve().parents[2] / "config" / "gate_catalog.json"
_CONFIG_NAME = "shipwright_run_config.json"


class GateCatalogError(ValueError):
    """Raised by ``load_catalog`` when the catalog fails validation."""


# --------------------------------------------------------------------------- #
# Validation
# --------------------------------------------------------------------------- #

def validate_catalog(data: Any) -> list[str]:
    """Return a list of human-readable errors; empty means valid.

    Non-raising so a CLI can print all problems at once. Enforces the
    safety invariants that make the mechanism trustworthy — most importantly
    that no constitution-locked gate is auto-answered.
    """
    errors: list[str] = []
    if not isinstance(data, dict):
        return [f"catalog must be a dict, got {type(data).__name__}"]
    if data.get("schemaVersion") != 1:
        errors.append("schemaVersion must be 1")
    cov = data.get("covered_phases")
    if cov is not None and list(cov) != list(COVERED_PHASES):
        # Keep the (decorative) JSON list honest against the authoritative tuple.
        errors.append(f"covered_phases {cov} must equal {list(COVERED_PHASES)}")
    gates = data.get("gates")
    if not isinstance(gates, list) or not gates:
        return errors + ["'gates' must be a non-empty list"]

    seen: set[str] = set()
    for i, g in enumerate(gates):
        where = g.get("id", f"gates[{i}]") if isinstance(g, dict) else f"gates[{i}]"
        if not isinstance(g, dict):
            errors.append(f"{where}: must be an object")
            continue
        for key in _REQUIRED_GATE_KEYS:
            if key not in g:
                errors.append(f"{where}: missing required key {key!r}")
        gid = g.get("id")
        if isinstance(gid, str):
            if gid in seen:
                errors.append(f"{where}: duplicate gate id")
            seen.add(gid)
        phase = g.get("phase")
        if phase not in COVERED_PHASES:
            errors.append(f"{where}: phase {phase!r} not in {COVERED_PHASES}")
        elif isinstance(gid, str) and not gid.startswith(phase + "."):
            errors.append(f"{where}: id must be prefixed by its phase {phase!r}")
        policy = g.get("policy")
        if policy not in POLICIES:
            errors.append(f"{where}: policy {policy!r} not in {POLICIES}")
        if g.get("fires") not in FIRES:
            errors.append(f"{where}: fires {g.get('fires')!r} not in {FIRES}")
        if not isinstance(g.get("constitution"), bool):
            errors.append(f"{where}: 'constitution' must be a bool")
        summary = g.get("summary")
        if not isinstance(summary, str) or not summary.strip():
            errors.append(f"{where}: 'summary' must be a non-empty str")

        answer = g.get("default_answer")
        if policy == AUTO_DEFAULT:
            if not isinstance(answer, str) or not answer.strip():
                errors.append(f"{where}: auto-default gate needs a non-empty default_answer")
        elif answer is not None:
            errors.append(f"{where}: only auto-default gates may carry a default_answer")
        if g.get("constitution") is True and policy == AUTO_DEFAULT:
            errors.append(f"{where}: constitution-locked gate must not be auto-default")
        errors.extend(validate_unattended(where, g))

    return errors


def load_catalog(path: Optional[Path] = None) -> dict[str, Any]:
    """Load + validate the catalog; return it with ``gates`` keyed by id.

    Raises :class:`GateCatalogError` on any validation failure — a corrupt
    catalog must never be silently resolved against.
    """
    p = Path(path) if path is not None else _CATALOG_PATH
    data = json.loads(p.read_text(encoding="utf-8"))
    errors = validate_catalog(data)
    if errors:
        raise GateCatalogError(f"invalid gate catalog ({p}): " + "; ".join(errors))
    by_id = {g["id"]: g for g in data["gates"]}
    return {**data, "gates": by_id}


# --------------------------------------------------------------------------- #
# Mode resolution (run_config-driven)
# --------------------------------------------------------------------------- #

def read_run_config_mode(project_root: Any) -> str:
    """Return ``SINGLE_SESSION`` or ``INERT_MODE``.

    Fail-safe: a missing / mode-less / corrupt config reads as ``INERT_MODE``; only
    the literal ``single_session`` activates it. TOTAL at the read boundary, since
    the caller does not guard it — ``UnicodeDecodeError`` IS a ``ValueError``,
    ``RecursionError`` is NOT, a non-object raises ``AttributeError``, a BOM needs
    ``utf-8-sig``. LOCKSTEP with ``config_io._read_parse_shape`` within the retry budget.
    """
    if project_root is None:
        return INERT_MODE
    try:
        parsed = json.loads(durable_read_text(Path(project_root) / _CONFIG_NAME, encoding="utf-8-sig"))
    except (ValueError, OSError, RecursionError, TypeError):
        return INERT_MODE
    mode = parsed.get("mode") if isinstance(parsed, dict) else None
    return SINGLE_SESSION if mode == SINGLE_SESSION else INERT_MODE


def read_run_config_autonomy(project_root: Any) -> Optional[str]:
    """The run's ``autonomy`` from run_config, or ``None`` (same total-read guard as
    ``read_run_config_mode``)."""
    if project_root is None:
        return None
    try:
        parsed = json.loads(durable_read_text(Path(project_root) / _CONFIG_NAME, encoding="utf-8-sig"))
    except (ValueError, OSError, RecursionError, TypeError):
        return None
    value = parsed.get("autonomy") if isinstance(parsed, dict) else None
    return value if isinstance(value, str) else None


def effective_mode(*, explicit: Optional[str], env: Optional[str], project_root: Any) -> str:
    """Resolve the run mode by precedence: explicit > env > run_config > default."""
    for candidate in (explicit, env):
        if candidate:
            return SINGLE_SESSION if candidate == SINGLE_SESSION else INERT_MODE
    return read_run_config_mode(project_root)


# --------------------------------------------------------------------------- #
# Resolver
# --------------------------------------------------------------------------- #

def resolve_gate_policy(
    gate_id: str, *, mode: str, catalog: Optional[dict[str, Any]] = None,
    autonomy: Optional[str] = None,
) -> dict[str, Any]:
    """Resolve the effective policy for ``gate_id`` under ``mode``.

    Raises ``KeyError`` for an unknown gate id (a typo must never silently pass).
    Under any non-single-session mode the gate is ``interactive`` (inert). Under
    single-session it is the catalog policy — with a fail-closed guard that a
    constitution-locked gate is never resolved to a proceed.

    A caller that passes ``catalog=`` owns its validation: ``load_catalog`` (the
    default and the CLI path) always validates, but an unvalidated dict is
    trusted here except for the constitution/auto-default clamp below — an
    unknown ``policy`` string is echoed verbatim in ``effective_policy`` (still
    with ``should_stop=True``, since only the literal ``auto-default`` proceeds).

    ``autonomy="unattended"`` adds ``unattended_answer`` (the reviewed answer of an
    eligible gate, else ``None``). ``should_stop`` is unchanged: the master/CLI, not
    the resolver, applies the answer after its own checks.
    """
    cat = catalog if catalog is not None else load_catalog()
    gate = cat["gates"][gate_id]  # KeyError on unknown id — intentional
    base = {
        "gate_id": gate_id,
        "phase": gate["phase"],
        "mode": mode,
        "constitution": gate["constitution"],
        "fires": gate["fires"],
        "summary": gate["summary"],
        "autonomy": autonomy,
        "unattended_answer": None,
    }

    if mode != SINGLE_SESSION:
        return {**base, "effective_policy": INTERACTIVE, "should_stop": True, "default_answer": None}

    policy = gate["policy"]
    if gate["constitution"] and policy == AUTO_DEFAULT:
        # Unreachable via a validated catalog; fail closed rather than proceed.
        raise GateCatalogError(f"{gate_id}: constitution gate resolved to auto-default")

    should_stop = policy != AUTO_DEFAULT
    return {
        **base,
        "effective_policy": policy,
        "should_stop": should_stop,
        "default_answer": gate["default_answer"] if policy == AUTO_DEFAULT else None,
        "unattended_answer": unattended_answer_for(gate, autonomy),
    }


# --------------------------------------------------------------------------- #
# Doc generation (shared/config/gate_catalog.md is rendered from the JSON)
# --------------------------------------------------------------------------- #

def render_catalog_markdown(catalog: Optional[dict[str, Any]] = None) -> str:
    """Render the human-readable catalog doc from the JSON (deterministic,
    pure ASCII); the renderer lives in ``gate_catalog_render``."""
    return render_catalog_doc(
        catalog if catalog is not None else load_catalog(),
        policies_order=POLICIES,
        covered_phases=COVERED_PHASES,
        auto_default=AUTO_DEFAULT,
    )
