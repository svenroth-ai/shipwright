"""Project / phase / run-id resolution.

Stop-hook resolution helpers — all best-effort, all fail-open.

* :func:`is_shipwright_project` — greenfield gate.
* :func:`phase_from_plugin_root` — ``CLAUDE_PLUGIN_ROOT`` → phase name.
* :func:`cwd_is_strict_ancestor_of` + :func:`project_root_was_explicitly_selected`
  — monorepo auto-descent guard (plan v7).
* :func:`resolve_run_id` — composite-fallback run_id resolution (§ 5.3).
* :func:`resolve_source` — orchestrator / standalone / iterate classifier.

Iterate Campaign B (B3): split out of the 1108-LOC monolith.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

_SCRIPTS_ROOT = Path(__file__).resolve().parents[2]
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from ._constants import PLUGIN_TO_PHASE  # noqa: E402
# Canonical greenfield/foreign predicate — the single source of truth for every
# hook (iterate-2026-06-12-canonical-project-predicate). Re-exported here so
# existing ``phase_quality.is_shipwright_project`` callers stay unchanged while
# the marker set lives in exactly one place.
from lib.project_root import is_shipwright_project  # noqa: E402
from lib.events_log import resolve_events_path  # noqa: E402
from lib.jsonl_records import read_jsonl_records  # noqa: E402
# Engagement predicate lives in _triage_bundle; importing it here is one-way and
# acyclic (_triage_bundle does not import _resolution) and keeps
# resolve_engaged_phases next to the other session-state resolvers.
from ._triage_bundle import (  # noqa: E402
    load_engagement_inputs,
    phase_is_engaged,
)


def phase_from_plugin_root(plugin_root: str | os.PathLike[str] | None) -> str | None:
    """Map ``CLAUDE_PLUGIN_ROOT`` to the Shipwright phase name.

    Handles both install layouts:

    * **Un-versioned** marketplace mirror — ``.../plugins/shipwright-iterate``
      → ``.name == "shipwright-iterate"`` matches directly.
    * **Versioned** install (Claude Code's ``installed_plugins.json`` uses
      ``installPath=.../<plugin>/<version>``) — ``.../shipwright-iterate/0.4.1``
      → ``.name == "0.4.1"`` does NOT match, so we fall back to the parent
      directory (the plugin name). Without this fallback every Stop hook
      keyed on phase silently no-ops under a versioned install — which is
      exactly how phase_quality + this compliance hook went dark after the
      marketplace switched to version-pinned installPaths (verified
      iterate-2026-05-30). The lookup is name-keyed (not path-substring) so
      an unrelated ancestor directory cannot spoof a phase.
    """
    if not plugin_root:
        return None
    p = Path(plugin_root)
    phase = PLUGIN_TO_PHASE.get(p.name)
    if phase:
        return phase
    # Versioned install: the plugin name is the immediate parent of the
    # version segment. Check it (and one more level to tolerate a future
    # ``.../<plugin>/<version>/<sub>`` shape) before giving up.
    for ancestor in list(p.parents)[:2]:
        phase = PLUGIN_TO_PHASE.get(ancestor.name)
        if phase:
            return phase
    return None


def cwd_is_strict_ancestor_of(cwd: Path, project_root: Path) -> bool:
    """Return True when *cwd* is a STRICT ancestor of *project_root*.

    This is the "auto-descent happened" signal: ``resolve_project_root``
    walked from ``cwd`` down into a subfolder because ``cwd`` itself had
    no Shipwright markers. Callers compose this with
    :func:`project_root_was_explicitly_selected` to decide whether to
    skip audit-like side effects when the user is working at a parent
    directory of a managed subfolder.

    Returns ``False`` when:

    - ``cwd == project_root`` (user is in the managed folder)
    - ``cwd`` is below ``project_root`` (user is inside a subdir)
    - ``cwd`` and ``project_root`` are unrelated paths
    - Path resolution fails (fail-open + stderr log — avoids silently
      blocking every audit after one environment hiccup; the off-scope
      pollution risk stays bounded by subsequent functional invocations)

    ``.resolve(strict=False)`` handles symlinks (dereferenced) and
    Windows case-insensitivity (normalised) cross-platform.
    """
    try:
        cwd_r = cwd.resolve(strict=False)
        pr_r = project_root.resolve(strict=False)
    except OSError as exc:
        sys.stderr.write(
            f"[phase-quality] cwd_is_strict_ancestor_of: resolve failed "
            f"({type(exc).__name__}: {exc}) — assuming not-ancestor\n"
        )
        return False
    if cwd_r == pr_r:
        return False
    return cwd_r in pr_r.parents


def project_root_was_explicitly_selected(project_root: Path) -> bool:
    """Return True when ``SHIPWRIGHT_PROJECT_ROOT`` resolves to ``project_root``.

    Distinguishes two cases:

    - **Deliberate opt-in**: user set ``SHIPWRIGHT_PROJECT_ROOT`` to point
      at THIS specific managed project (e.g. for CI/automation running
      from outside the managed folder). Returns ``True``.
    - **Ambient env**: CI or parent shell has ``SHIPWRIGHT_PROJECT_ROOT``
      set for unrelated reasons AND ``resolve_project_root`` didn't
      actually use it (env path doesn't exist or isn't a Shipwright
      project, so resolver fell through to auto-descent). Returns
      ``False``.

    Handles: empty string, whitespace-only, relative paths (resolved to
    absolute via ``.resolve``), non-existent paths, symlinks, Windows
    case-insensitivity. Any resolution failure returns ``False``
    (conservative — don't grant opt-in on broken input).
    """
    env = os.environ.get("SHIPWRIGHT_PROJECT_ROOT", "").strip()
    if not env:
        return False
    try:
        env_r = Path(env).resolve(strict=False)
        pr_r = project_root.resolve(strict=False)
    except OSError:
        return False
    return env_r == pr_r


def resolve_run_id(project_root: Path, session_id: str) -> str:
    """Composite-fallback run_id resolution (plan § 5.3).

    Priority:
    1. ``shipwright_run_config.json::run_id``
    2. ``events.jsonl`` latest ``run_started`` event
    3. ``SHIPWRIGHT_LOOP_ID`` + ``SHIPWRIGHT_LOOP_UNIT_ID``
    4. ``session_id`` itself (standalone)
    """
    run_config = project_root / "shipwright_run_config.json"
    if run_config.exists():
        try:
            data = json.loads(run_config.read_text(encoding="utf-8"))
            run_id = data.get("run_id")
            if isinstance(run_id, str) and run_id:
                return run_id
        except (json.JSONDecodeError, OSError):
            pass

    events_path = project_root / "shipwright_events.jsonl"
    if events_path.exists():
        try:
            latest_run_id: str | None = None
            # Record-boundary recovery via the shared SSoT: a merge=union merge can
            # leave two records on one physical line, and the pre-fix per-line
            # json.loads dropped BOTH — silently falling through to the session-id
            # fallback and mis-attributing every audit row keyed on the resolved run
            # (iterate-2026-07-20-events-record-boundary-remainder). read_jsonl_records
            # returns only JSON objects, in wire order, so latest-wins is preserved.
            for obj in read_jsonl_records(events_path).records:
                if obj.get("type") == "run_started":
                    rid = obj.get("run_id") or obj.get("id")
                    if isinstance(rid, str) and rid:
                        latest_run_id = rid
            if latest_run_id:
                return latest_run_id
        except OSError:
            pass

    loop_id = os.environ.get("SHIPWRIGHT_LOOP_ID", "").strip()
    loop_unit = os.environ.get("SHIPWRIGHT_LOOP_UNIT_ID", "").strip()
    if loop_id and loop_unit:
        return f"{loop_id}-{loop_unit}"
    if loop_id:
        return loop_id

    return session_id or "unknown"


def resolve_source(project_root: Path, phase: str) -> str:
    """Infer the audit source (orchestrator / standalone / iterate).

    Used for operator telemetry — does not gate any logic. ``iterate`` is
    always tagged regardless of orchestrated state because iterate runs
    on a separate finalize path.
    """
    if phase == "iterate":
        return "iterate"
    run_config = project_root / "shipwright_run_config.json"
    if not run_config.exists():
        return "standalone"
    try:
        data = json.loads(run_config.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return "standalone"
    if data.get("standalone") is True:
        return "standalone"
    if not data.get("current_step"):
        return "standalone"
    return "orchestrator"


def _canonical_phases() -> list[str]:
    """Unique canonical phase names, in ``PLUGIN_TO_PHASE`` declaration order."""
    seen: set[str] = set()
    out: list[str] = []
    for phase in PLUGIN_TO_PHASE.values():
        if phase not in seen:
            seen.add(phase)
            out.append(phase)
    return out


def _engagement_evidence_unreadable(project_root: Path) -> bool:
    """``True`` iff the event log EXISTS but cannot be read (partial flush / OSError).

    A genuinely ABSENT event log is NOT "unreadable" — cfg-based engagement
    (status / current_step / completed_steps) still applies, so absence must not
    trigger fail-open. Only an existing-but-unreadable log counts as insufficient
    evidence. Any resolver error is treated as unreadable (conservative).
    """
    try:
        ev_path = resolve_events_path(project_root)
    except Exception:  # noqa: BLE001
        return True
    if not ev_path.exists():
        return False
    try:
        ev_path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return True
    return False


def resolve_engaged_phases(project_root: Path) -> list[str]:
    """Canonical phases the Stop-time phase-quality audit should cover.

    Resolved from SESSION STATE (run config + event log) via the well-tested
    :func:`phase_is_engaged`, NOT from ``CLAUDE_PLUGIN_ROOT``. This is what lets a
    SINGLE claimed Stop invocation audit the phase(s) that actually ran, instead
    of the 11× fan-out auditing every plugin's phase (10 of which never ran).

    **Fail-open — "never fewer".** Returns the FULL canonical phase set when
    engagement evidence is insufficient or unreadable: a missing/malformed run
    config (``cfg is None``), an existing-but-unreadable event log (partial flush
    / OSError), any internal error, OR a degenerate empty result. Under stale
    end-of-session state the audit covers MORE, never silently fewer.
    """
    all_phases = _canonical_phases()
    if _engagement_evidence_unreadable(project_root):
        return all_phases
    try:
        cfg, events = load_engagement_inputs(project_root)
        if cfg is None:
            return all_phases
        engaged = [p for p in all_phases if phase_is_engaged(p, cfg, events)]
    except Exception:  # noqa: BLE001 — fail-open: audit more, never fewer
        return all_phases
    return engaged or all_phases


__all__ = [
    "cwd_is_strict_ancestor_of",
    "is_shipwright_project",
    "phase_from_plugin_root",
    "project_root_was_explicitly_selected",
    "resolve_engaged_phases",
    "resolve_run_id",
    "resolve_source",
]
