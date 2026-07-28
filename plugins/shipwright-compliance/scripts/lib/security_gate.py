"""Decision logic for the ``check_security_scan`` PreToolUse deploy gate.

Split out of the hook script when the hook reached the 300-line cap
(iterate-2026-07-28-hygiene-sweep). The hook keeps payload parsing, deploy-command
detection and the fail-open wrapper; everything that decides *whether a deploy may
proceed* lives here, where it is directly unit-testable.

Subject: ``.shipwright/compliance/ci-security.json`` — the scanner chain's own
public-safe summary (``ci_security.summarize_ci_security``). Until 2026-07-28 the
gate read the RTM row ``| Unresolved findings | N |`` instead: code-review findings
summed over ``work_completed`` events, unrelated to any scan, and under-reporting
by construction (only 4 of 399 events carry a ``review`` block; ``review.fixed`` is
written at F5b *before* the remediation commits exist, into an append-only log).
See ``docs/hooks-and-pipeline.md`` and trg-17f53a39.

Posture: fail **closed** on every broken state; fail open **only** when the summary
is genuinely absent (a repo that was never scanned, e.g. a fresh adopt). An
artifact that is present and unusable is a scan that tried and failed — never
evidence of "clean".
"""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path

#: Canonical literal (not assembled from segments) so the artifact-path-canon
#: AST lint sees the ``.shipwright/`` prefix — same reason as ci_security.py.
CI_SECURITY_REL = ".shipwright/compliance/ci-security.json"

#: :func:`read_security_summary` sentinel for a present-but-untrustworthy file.
UNUSABLE = "unusable"

CONFIG_FILENAME = "shipwright_compliance_config.json"


def read_security_summary(project_root: str | Path) -> dict | str | None:
    """Return the summary dict, ``None`` if genuinely absent, else :data:`UNUSABLE`.

    The three states are kept distinct deliberately:
    ``ci_security.load_ci_security`` collapses absent and malformed into ``None``,
    which is right for a *grader* (both read as "unknown") and wrong for a *gate*.

    ``os.stat`` rather than ``Path.exists()`` / ``Path.is_file()``: those swallow
    every ``OSError`` and return ``False``, so a summary whose parent directory is
    not searchable, or whose metadata cannot be read, would look "never scanned"
    and ALLOW the release. Only a path that truly is not there reads as absent;
    every other stat failure is unusable.

    ``os.stat`` FOLLOWS symlinks, so exactly one mode is ever tested and it is
    always the target's — there is no second, unresolved ``st`` in scope to
    confuse it with. The ``lstat`` fallback runs only when ``stat`` said "not
    there", purely to tell a genuinely absent path from a DANGLING symlink; the
    latter is something present and broken, so it blocks.
    """
    path = Path(project_root) / CI_SECURITY_REL
    try:
        mode = os.stat(path).st_mode          # follows symlinks
    except (FileNotFoundError, NotADirectoryError):
        try:
            os.lstat(path)                    # link itself still there?
        except OSError:
            return None                       # genuinely absent — never scanned
        return UNUSABLE                       # dangling symlink: present, broken
    except OSError:
        return UNUSABLE  # permission denied, I/O error, name too long, …

    if not stat.S_ISREG(mode):
        return UNUSABLE  # directory, fifo, device, …

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return UNUSABLE
    return data if isinstance(data, dict) else UNUSABLE


def critical_count(summary: dict) -> int | None:
    """EXACT open-critical count, or ``None`` when the summary cannot say.

    Only ``by_severity.critical`` gives an exact number. ``critical_gate`` is
    deliberately NOT folded in: it is a boolean verdict, so reading a ``"fail"``
    as "1 critical" would let a threshold of 1 or more allow a deploy the producer
    just refused, on a count nobody measured. Callers handle the inexact case.
    """
    by_sev = summary.get("by_severity")
    if isinstance(by_sev, dict):
        crit = by_sev.get("critical")
        if isinstance(crit, int) and not isinstance(crit, bool) and crit >= 0:
            return crit
    return None


def load_threshold(project_root: str | Path) -> int:
    """``enforcement.allowed_critical_findings``, coerced to a safe non-negative int.

    Every malformed shape — unreadable file, bad JSON, a top-level list, a
    non-dict ``enforcement``, a bool/str/negative value — yields 0 (zero
    tolerance). A hand-edited config must never be able to WIDEN the gate, and
    must never raise into the hook's fail-open wrapper, which would allow the
    deploy outright.
    """
    config_path = Path(project_root) / CONFIG_FILENAME
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return 0
    if not isinstance(config, dict):
        return 0
    enforcement = config.get("enforcement")
    if not isinstance(enforcement, dict):
        return 0
    raw = enforcement.get("allowed_critical_findings", 0)
    if isinstance(raw, bool) or not isinstance(raw, int) or raw < 0:
        return 0
    return raw


def decide(project_root: str | Path) -> tuple[bool, str, dict]:
    """``(blocked, reason, details)`` for a deploy against ``project_root``.

    ``blocked is False`` → allow (``reason`` empty). See the module docstring for
    the posture; the branches below are the whole gate.
    """
    summary = read_security_summary(project_root)

    if summary is None:
        return (False, "", {})  # never scanned — not the same as scanned-clean

    if summary is UNUSABLE:
        return (True,
                f"{CI_SECURITY_REL} exists but is unreadable or malformed — "
                "a scan that failed is not evidence of a clean scan",
                {"summary_path": CI_SECURITY_REL, "state": "unusable"})

    if summary.get("degraded"):
        return (True,
                "the security scan is marked degraded — at least one scanner leg "
                "did not complete, so its findings are unknown",
                {"summary_path": CI_SECURITY_REL, "degraded": True,
                 "scan_date": summary.get("scan_date", "")})

    criticals = critical_count(summary)
    if criticals is None:
        gate = summary.get("critical_gate")
        if gate == "pass":
            return (False, "", {})
        reason = (
            f"{CI_SECURITY_REL} reports critical_gate=fail with no "
            "'by_severity.critical' count — open criticals cannot be sized "
            "against the allowed threshold"
            if gate == "fail" else
            f"{CI_SECURITY_REL} carries neither a usable 'by_severity.critical' "
            "count nor a 'critical_gate' verdict"
        )
        return (True, reason,
                {"summary_path": CI_SECURITY_REL, "critical_gate": gate,
                 "state": "no-count" if gate == "fail" else "no-verdict"})

    threshold = load_threshold(project_root)
    if criticals <= threshold:
        return (False, "", {})

    by_sev = summary.get("by_severity")
    return (True,
            f"{criticals} open critical security finding(s) exceed the allowed "
            f"threshold ({threshold})",
            {
                "critical_findings": criticals,
                "allowed_threshold": threshold,
                # Informational only — 'high' does NOT gate; the config key is
                # named allowed_critical_findings and is honoured as written.
                "high_findings": by_sev.get("high") if isinstance(by_sev, dict)
                else None,
                "scan_date": summary.get("scan_date", ""),
                "source": summary.get("source", ""),
                "summary_path": CI_SECURITY_REL,
            })
