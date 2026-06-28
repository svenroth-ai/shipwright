#!/usr/bin/env python3
"""AR-10 producer — refresh the committed CI-security summary from CI.

Fetches the latest ``security.yml`` run's ``findings.json`` /
``prompt_risks.json`` (via the shared ``github_api`` helpers — the same
artifact path the ``github_triage`` producer uses) and writes the public-safe
summary to ``.shipwright/compliance/ci-security.json`` for the dashboard to
render. This is the **network** half of AR-10; the render/grade half
(``scripts.lib.ci_security``) is pure + offline.

**Fail-soft (never blocks a regen):** when ``gh`` is unavailable, offline, or
there is no fresh successful run within the freshness window, the existing
committed summary is left **untouched** — a green scan is never fabricated and
a good summary is never clobbered with empty data. ``update_compliance.py``
calls this best-effort before regenerating the dashboard.

Usage:
    uv run refresh_ci_security.py --project-root <path>
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_PLUGIN_ROOT = Path(__file__).resolve().parents[2]
if str(_PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(_PLUGIN_ROOT))
_SHARED_SCRIPTS = Path(__file__).resolve().parents[4] / "shared" / "scripts"
if str(_SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SHARED_SCRIPTS))

from scripts.lib.ci_security import summarize_ci_security, write_ci_security  # noqa: E402


def refresh_ci_security(project_root: Path | str, *, api=None) -> dict:
    """Fetch the latest CI security outcome and rewrite the committed summary.

    ``api`` defaults to the shared ``github_api`` module (injectable for tests).
    Returns a status dict — ``status`` is one of ``written`` (summary refreshed),
    ``skipped`` (fail-soft: gh unavailable / no fresh run / fetch failed), or
    ``error`` (unexpected). Never raises.
    """
    if api is None:
        import github_api as api  # lazy: only needed on the network path

    try:
        if not api.gh_available():
            return {"status": "skipped", "reason": "gh-unavailable"}
        run = api.latest_security_workflow_run()
        if not run:
            return {"status": "skipped", "reason": "no-fresh-run"}
        run_id = run.get("id") or 0
        findings = api.download_security_findings(run_id)
        if findings is None:  # fetch failed (≠ empty); ADR-052 None-vs-[]
            return {"status": "skipped", "reason": "findings-fetch-failed"}
        prompt_risks = api.download_prompt_risks(run_id)  # may be None → treated as []
        scan_date = run.get("run_started_at") or run.get("created_at") or ""
        source = f"security.yml#{run_id}"
        summary = summarize_ci_security(
            findings, prompt_risks or [], scan_date=scan_date, source=source)
        write_ci_security(project_root, summary)
        return {
            "status": "written",
            "source": source,
            "scan_date": summary["scan_date"],
            "open_high_critical": summary["open_high_critical"],
            "critical_gate": summary["critical_gate"],
        }
    except Exception as exc:  # noqa: BLE001 — fail-soft, never block a regen
        return {"status": "error", "reason": f"{type(exc).__name__}: {exc}"}


def main() -> int:
    parser = argparse.ArgumentParser(description="Refresh CI-security summary (AR-10)")
    parser.add_argument("--project-root", required=True)
    args = parser.parse_args()
    result = refresh_ci_security(Path(args.project_root).resolve())
    print(json.dumps(result, indent=2))
    # Fail-soft: skip/error are non-fatal (exit 0) so a regen is never blocked.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
