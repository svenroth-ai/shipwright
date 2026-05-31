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

from ._constants import CONFIG_MARKERS, PLUGIN_TO_PHASE


def is_shipwright_project(project_root: Path) -> bool:
    """Return True when ``project_root`` looks like a Shipwright project.

    Matches the contract used by ``generate_handoff_on_stop.py`` and
    ``check_rtm_coverage.py`` so all Stop hooks agree on what counts as
    greenfield. We require at least one marker OR ``.shipwright/agent_docs/`` so
    fresh projects between ``/shipwright-project`` init and the first
    config write aren't skipped.
    """
    if any((project_root / m).exists() for m in CONFIG_MARKERS):
        return True
    return (project_root / ".shipwright" / "agent_docs").is_dir()


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
            content = events_path.read_text(encoding="utf-8", errors="ignore")
            latest_run_id: str | None = None
            for raw in content.splitlines():
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    obj = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                if not isinstance(obj, dict):
                    continue
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


__all__ = [
    "cwd_is_strict_ancestor_of",
    "is_shipwright_project",
    "phase_from_plugin_root",
    "project_root_was_explicitly_selected",
    "resolve_run_id",
    "resolve_source",
]
