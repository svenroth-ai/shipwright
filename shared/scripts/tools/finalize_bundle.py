#!/usr/bin/env python3
"""Bundle the iterate finalization sub-tool invocations into ONE call.

The finalize phase runs a handful of sub-second tools one at a time — F1
``artifact_sync``, F3 ``write_decision_drop``, F4 ``write_changelog_drop``, F5c
``append_iterate_entry``, F5b ``finalize_iterate``. The wall-clock cost is the
*LLM turn-taking* (think → build a command → read output → next), not the
scripts. This orchestrator lets the agent author all content ONCE into a JSON
payload and invoke the five tools in one turn.

It is a PURE ORCHESTRATOR: it writes no artifact itself. Every file is produced
by the same unchanged tool as before — the bundle only changes how many LLM
turns invoke them. Each tool runs as a subprocess (``sys.executable`` — avoids
the ADR-045 ``sys.modules['lib']`` collision + argparse/``sys.exit`` global-state
hazards) with ``capture_output`` so the bundle emits exactly ONE JSON document.

Dependency order: F1 first (abort on drift BEFORE any write), then F3 → F4(×N) →
F5c, then F5b last (reads ``shipwright_test_results.json`` for compliance regen +
records the ``work_completed`` event). Abort-on-first-failure names the failed
step; all sub-tools are idempotent per ``run_id`` so re-running the whole bundle
after a fix is safe. F5 (test-results write), F2/F3a (agent-doc bullets) and F6
(commit) stay manual agent steps. Exit codes: 0 ok · 1 a step aborted · 2 the
payload could not be read / parsed / validated (no subprocess ran) · 3 an
unexpected internal error (still emits a structured JSON error document).

Payload schema / validation / argv live in the pure ``finalize_bundle_lib``
module. Full contract + workflow: iterate skill ``references/F-finalize-bundle.md``.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

# The pure schema/validation/argv layer is a sibling module. Ensure shared/scripts
# is importable when this file runs as ``__main__`` under a bare ``sys.executable``.
_SCRIPTS_DIR = Path(__file__).resolve().parent.parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from tools.finalize_bundle_lib import (  # noqa: E402
    BundleValidationError,
    RunResult,
    Runner,
    f1_argv,
    f3_argv,
    f4_argv,
    f5b_argv,
    f5c_argv,
    validate,
)

__all__ = ["BundleValidationError", "RunResult", "main", "run", "validate"]

_CAPTURE_LIMIT = 4000  # truncate captured stdout/stderr per step (external-review)


def _default_runner(argv: list, cwd: Path) -> RunResult:
    # encoding/errors: the sub-tools print UTF-8 (json.dumps(ensure_ascii=False));
    # on a cp1252 Windows default `text=True` alone would raise UnicodeDecodeError
    # INSIDE subprocess.run on a stray non-ASCII byte. errors="replace" keeps
    # capture total so the bundle can always emit its single JSON document.
    proc = subprocess.run(  # noqa: S603 — argv-list, shell=False, trusted tool paths
        argv, cwd=str(cwd), capture_output=True, text=True, shell=False,
        encoding="utf-8", errors="replace",
    )
    return RunResult(proc.returncode, proc.stdout or "", proc.stderr or "")


def _truncate(text: str | None) -> str:
    text = (text or "").strip()
    if len(text) <= _CAPTURE_LIMIT:
        return text
    return text[:_CAPTURE_LIMIT] + f"\n...[truncated {len(text) - _CAPTURE_LIMIT} chars]"


def _capture(rr: RunResult, **extra) -> dict:
    rec = {"returncode": rr.returncode, "stdout": _truncate(rr.stdout),
           "stderr": _truncate(rr.stderr)}
    rec.update(extra)
    return rec


def _f1_record(rr: RunResult) -> dict:
    """Interpret artifact_sync: drift is read from the stdout ``drift_detected``
    JSON, NOT the raw exit code — a crash also exits 1 (external-review MED)."""
    drift = None
    try:
        data = json.loads(rr.stdout)
        if isinstance(data, dict) and "drift_detected" in data:
            drift = bool(data["drift_detected"])
    except (json.JSONDecodeError, ValueError):
        drift = None
    if drift is True:
        return _capture(rr, status="drift",
                        reason="artifact_sync detected drift — update the affected "
                               "specs (or rerun once resolved) before finalizing")
    if drift is False or (drift is None and rr.returncode == 0):
        return _capture(rr, status="ok")
    return _capture(rr, status="failed",
                    reason="artifact_sync failed (non-zero exit with no drift signal)")


def _lift_finalize_steps(rec: dict, raw_stdout: str) -> None:
    """Surface finalize_iterate's OWN per-step statuses (event / compliance /
    dashboard / handoff / campaign_status) into ``rec["finalize_steps"]``.

    finalize_iterate treats compliance regen / handoff as best-effort and still
    exits 0 when they skip. Collapsing the finalize turns would otherwise bury
    that signal in the truncated F5b stdout under a green ``success`` (doubt-
    review MED). Lifting a compact status summary keeps a compliance-skip / event
    problem visible at the top of the bundle result. Best-effort — a non-JSON /
    truncated stdout leaves ``rec`` unchanged (this is not a failure)."""
    try:
        data = json.loads(raw_stdout or "")
    except (json.JSONDecodeError, ValueError):
        return
    steps = data.get("steps") if isinstance(data, dict) else None
    if not isinstance(steps, dict):
        return
    rec["finalize_steps"] = {
        name: (val.get("status") or ("skipped" if val.get("skipped") else "ok"))
        if isinstance(val, dict) else val
        for name, val in steps.items()
    }


def run(payload: dict, project_root: Path, runner: Runner | None = None) -> dict:
    """Run the finalization sub-tools in dependency order. Returns a result dict
    (``success``/``failed_step``/``steps``). Raises :class:`BundleValidationError`
    on a bad payload before any subprocess runs."""
    runner = runner or _default_runner
    run_id = validate(payload)
    root = Path(project_root).resolve()
    result: dict = {"success": True, "run_id": run_id, "failed_step": None, "steps": {}}

    def _abort(step: str) -> dict:
        result["success"] = False
        result["failed_step"] = step
        return result

    def _simple(step: str, argv: list) -> bool:
        """Run a single-shot tool, record it under ``step``, return ok?"""
        rec = _capture(runner(argv, root))
        rec["status"] = "ok" if rec["returncode"] == 0 else "failed"
        result["steps"][step] = rec
        return rec["status"] == "ok"

    # F1 — always, unless an explicit skip bypasses the drift gate.
    asy = payload.get("artifact_sync") or {}
    if asy.get("skip"):
        result["steps"]["F1"] = {"status": "skipped",
                                 "reason": "artifact_sync.skip=true (drift gate bypassed)"}
    else:
        rec = _f1_record(runner(f1_argv(root, asy.get("ref")), root))
        result["steps"]["F1"] = rec
        if rec["status"] != "ok":
            return _abort("F1")

    if not _simple("F3", f3_argv(root, run_id, payload["decision"])):
        return _abort("F3")

    # F4 — one changelog drop per bullet (aggregate result; stop on first fail).
    drops, f4_ok = [], True
    for item in payload["changelog"]:
        rr = runner(f4_argv(root, run_id, item), root)
        drops.append({"category": item["category"], "bullet": item["bullet"],
                      "status": "ok" if rr.returncode == 0 else "failed",
                      "returncode": rr.returncode, "stderr": _truncate(rr.stderr)})
        if rr.returncode != 0:
            f4_ok = False
            break
    result["steps"]["F4"] = {"status": "ok" if f4_ok else "failed", "drops": drops}
    if not f4_ok:
        return _abort("F4")

    if not _simple("F5c", f5c_argv(root, run_id, payload["iterate_entry"])):
        return _abort("F5c")
    # F5b last — reads test-results for compliance regen + records the event.
    rr = runner(f5b_argv(root, run_id, payload["finalize"]), root)
    rec = _capture(rr)
    rec["status"] = "ok" if rr.returncode == 0 else "failed"
    _lift_finalize_steps(rec, rr.stdout)  # surface event/compliance status (raw, pre-truncation)
    result["steps"]["F5b"] = rec
    if rec["status"] != "ok":
        return _abort("F5b")
    return result


def main(argv: list | None = None, runner: Runner | None = None) -> int:
    # UTF-8 stdout: the result carries non-ASCII (paths, ADR prose); the single-
    # JSON-document contract must survive a cp1252 default stdout (Windows).
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    except (AttributeError, ValueError):
        pass

    parser = argparse.ArgumentParser(
        description="Bundle the iterate finalization sub-tools into one call.",
    )
    parser.add_argument("--payload-file", required=True,
                        help="Path to the JSON payload file (see F-finalize-bundle.md).")
    parser.add_argument("--project-root", required=True,
                        help="Iterate worktree project root.")
    args = parser.parse_args(argv)

    def _emit(obj: dict) -> None:
        print(json.dumps(obj, indent=2, ensure_ascii=False))

    try:
        raw = Path(args.payload_file).read_text(encoding="utf-8")
    except OSError as exc:
        _emit({"success": False, "error": "payload_unreadable", "detail": str(exc)})
        return 2
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        _emit({"success": False, "error": "payload_invalid_json", "detail": str(exc)})
        return 2

    try:
        result = run(payload, Path(args.project_root), runner=runner)
    except BundleValidationError as exc:
        _emit({"success": False, "error": "payload_validation", "detail": str(exc)})
        return 2
    except Exception as exc:  # noqa: BLE001 — never break the one-JSON-document contract
        # A subprocess spawn failure (OSError), a decode error, or any other
        # unexpected error must still emit a structured document, not a traceback.
        _emit({"success": False, "error": "internal", "detail": f"{type(exc).__name__}: {exc}"})
        return 3

    _emit(result)
    return 0 if result["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
