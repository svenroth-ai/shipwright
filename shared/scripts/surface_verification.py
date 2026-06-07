"""End-to-End Verification Gate orchestrator (F0.5 of the iterate skill).

Single chokepoint that proves the user-erlebbare Surface was empirically
driven through a running stack. Writes evidence JSON to
``{project_root}/.shipwright/runs/{run_id}/surface_verification.json`` and
exits non-zero on any of the four fail-closed conditions:

    1  unknown surface or invalid arguments
    2  tests_run == 0 (greedy filter mismatch — Playwright's silent killer)
    3  exit_code != 0 after the 3-retry cap
    4  surface == "none" without --justification

A non-zero exit is STOP — F1+ of the iterate finalization MUST NOT proceed.
The post-commit audit in ``shared/scripts/tools/verifiers/iterate_checks.py``
provides a second layer that reads the consolidated block from
``shipwright_test_results.json`` and fails the verifier on the same
conditions.

Usage::

    uv run shared/scripts/surface_verification.py \\
        --project-root . \\
        --run-id iterate-2026-05-06-foo \\
        --surface cli \\
        --runner "uv run pytest plugins/shipwright-iterate/tests/ -v"

For ``surface=none`` (no startable surface) a justification is mandatory::

    uv run shared/scripts/surface_verification.py \\
        --project-root . \\
        --run-id iterate-2026-05-06-bar \\
        --surface none \\
        --justification "pure type-hint rename; no runtime path exercised"

The orchestrator deliberately does NOT manage the dev_server lifecycle for
``web`` / ``api`` surfaces — callers (the iterate skill prose, or a wrapping
script) are expected to start ``dev_server.py`` first and stop it after.
This keeps the orchestrator stateless and testable.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Exit codes — line-up 1:1 with the four fail-closed conditions documented in
# SKILL.md F0.5. Tests in shared/tests/test_surface_verification.py rely on
# this mapping; do not renumber without updating both sides.
EXIT_OK = 0
EXIT_INVALID_ARGS = 1
EXIT_ZERO_TESTS = 2
EXIT_RUNNER_FAILED = 3
EXIT_NONE_WITHOUT_JUSTIFICATION = 4

VALID_SURFACES = ("web", "cli", "api", "none")
DEFAULT_RETRY_CAP = 3

# Matches ANSI CSI escape sequences (SGR colour, cursor moves). pytest and
# playwright colour their summary line even when stdout is captured (no TTY);
# the escape bytes break the `\b`...`\d` word-boundary anchors in the summary
# parser below. See ADR-048 (conventions.md).
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


def _now_iso() -> str:
    """Canonical ISO-8601 UTC timestamp (`...Z`) for the evidence block."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def parse_tests_run(stdout: str, surface: str) -> int:
    """Best-effort extraction of how many tests actually executed.

    The greedy-filter trap (Playwright `--grep` matching zero specs but
    exit 0) is the failure mode this exists to detect, so the parser
    leans pessimistic: when no signal is found we return 0 and let the
    caller surface a fail-closed.

    Surface-specific heuristics — order matters within each block:

    - **cli (pytest)**: ``"N passed"``, ``"N failed"`` in the trailing
      summary line (``=== 5 passed in 0.32s ===``). Sum passed + failed.
    - **web (playwright)**: ``"N passed"``, ``"N failed"`` in the
      Playwright reporter's final line (same shape as pytest).
    - **api**: number of non-empty lines in stdout (caller is expected
      to print one line per assertion); tests can override with
      ``--tests-run`` for full determinism.

    Callers may always pass ``--tests-run N`` to bypass this parser.
    """
    if not stdout:
        return 0

    # Strip ANSI escapes first — pytest/playwright colour the summary line
    # ("\x1b[1m5 passed\x1b[0m") even with stdout captured, and the escape
    # bytes destroy the `\b` word boundary before the digit. See ADR-048.
    stdout = _ANSI_RE.sub("", stdout)

    if surface in ("cli", "web"):
        passed = 0
        failed = 0
        # Match e.g. "5 passed", "1 failed" — anchor on whole-word number to
        # avoid grabbing "passed in 0.32" or test names containing "passed".
        for match in re.finditer(r"\b(\d+)\s+passed\b", stdout):
            passed = max(passed, int(match.group(1)))
        for match in re.finditer(r"\b(\d+)\s+failed\b", stdout):
            failed = max(failed, int(match.group(1)))
        return passed + failed

    if surface == "api":
        return sum(1 for line in stdout.splitlines() if line.strip())

    return 0


# The runner is exec'd with shell=False, so these are never interpreted — a
# runner that uses them would exec the operator/builtin as a bogus binary and
# die with a cryptic FileNotFoundError. Detected up front for a clear error.
_SHELL_OPERATORS = frozenset({"&&", "||", ";", "|", "&", ">", ">>", "<", "<<"})
_SHELL_BUILTINS = frozenset({"cd", "export", "set", "source", ".", "pushd", "popd"})

_RUNNER_HINT = (
    "F0.5 runs the runner with NO shell (cwd=project_root), so shell operators "
    "(&&, ;, |) and builtins (cd, export) are not interpreted. Pass a single "
    "executable invocation instead — point the tool at the path directly, e.g. "
    "'uv run --extra dev pytest plugins/<plugin>/tests/<file>.py -q' — or wrap "
    "the steps in a script and call that."
)


def _tokenize(cmd: list[str] | str) -> list[str]:
    """Convert ``cmd`` to a list usable with ``subprocess.run(..., shell=False)``.

    On Windows we use ``posix=False`` so backslashes in paths
    (``C:\\\\Users\\\\...\\\\python.exe``) survive shlex-splitting.
    On POSIX we keep the default mode so single-quoted args and
    embedded shell metacharacters parse the way users expect.

    Raises ``ValueError`` when the runner is a compound shell command (a bare
    shell operator token, or a leading shell builtin) — these cannot work under
    shell=False, so we reject them with an actionable message rather than let
    the exec fail cryptically.
    """
    tokens = list(cmd) if isinstance(cmd, list) else shlex.split(cmd, posix=(os.name != "nt"))
    if not tokens:
        return tokens
    bad_op = next((t for t in tokens if t in _SHELL_OPERATORS), None)
    if bad_op is not None:
        raise ValueError(f"runner contains the shell operator {bad_op!r}. {_RUNNER_HINT}")
    if tokens[0] in _SHELL_BUILTINS:
        raise ValueError(f"runner starts with the shell builtin {tokens[0]!r}. {_RUNNER_HINT}")
    return tokens


def run_with_retries(
    cmd: list[str] | str,
    cwd: Path,
    retry_cap: int = DEFAULT_RETRY_CAP,
) -> tuple[int, str, int]:
    """Run ``cmd`` up to ``retry_cap`` times until exit code 0.

    Returns ``(final_exit_code, combined_stdout, attempts)``. Each retry
    re-runs from scratch (no incremental state); the runner is expected
    to be idempotent. Stdout/stderr from every attempt is concatenated
    with separator banners so the evidence file shows the failure trail.

    ``cmd`` is normalised to a list (no shell) — paths with spaces and
    backslashes survive without cmd.exe quote-eating them.
    """
    try:
        cmd_list = _tokenize(cmd)
    except ValueError as exc:
        # Malformed runner (compound shell command) — fail fast with an
        # actionable message and 0 attempts, instead of exec'ing a bogus binary
        # and burning the whole retry budget on a cryptic FileNotFoundError.
        return 127, f"[orchestrator] invalid runner: {exc}", 0
    display = " ".join(cmd_list)
    chunks: list[str] = []
    last_exit = 0

    for attempt in range(1, retry_cap + 1):
        chunks.append(f"=== attempt {attempt}/{retry_cap}: {display} ===")
        try:
            result = subprocess.run(
                cmd_list,
                cwd=str(cwd),
                capture_output=True,
                text=True,
                check=False,
            )
        except FileNotFoundError as exc:
            chunks.append(f"[orchestrator] command not found: {exc}")
            last_exit = 127
            return last_exit, "\n".join(chunks), attempt

        chunks.append(result.stdout or "")
        if result.stderr:
            chunks.append("--- stderr ---")
            chunks.append(result.stderr)

        last_exit = result.returncode
        if last_exit == 0:
            return last_exit, "\n".join(chunks), attempt

        # Tiny sleep between retries — gives transient races (port binding,
        # filesystem flush) a chance to settle without slowing the happy path.
        if attempt < retry_cap:
            time.sleep(0.5)

    return last_exit, "\n".join(chunks), retry_cap


def write_evidence(
    project_root: Path,
    run_id: str,
    block: dict,
) -> Path:
    """Persist the evidence block under ``.shipwright/runs/{run_id}/``.

    The path is shared with the autonomous-loop runner output dir, so
    F5 (Test Results JSON) can find it deterministically. Returns the
    path so the caller can include it in commit-stage output.
    """
    runs_dir = project_root / ".shipwright" / "runs" / run_id
    runs_dir.mkdir(parents=True, exist_ok=True)
    evidence_path = runs_dir / "surface_verification.json"
    evidence_path.write_text(
        json.dumps(block, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return evidence_path


def build_block(
    *,
    surface: str,
    runner: str,
    exit_code: int,
    tests_run: int,
    evidence_path: str,
    justification: str | None,
    attempts: int,
) -> dict:
    """Construct the schema-compliant evidence block.

    Schema is documented in SKILL.md F0.5 Step 3. Keys are stable —
    callers (finalize_iterate.py, iterate_checks.py, compliance
    data_collector.py) read them by name. Backwards-compat note:
    only readers that look up the new key see it; older readers
    ignore it.
    """
    block: dict = {
        "surface": surface,
        "runner": runner,
        "exit_code": exit_code,
        "tests_run": tests_run,
        "evidence_path": evidence_path,
        "timestamp": _now_iso(),
        "attempts": attempts,
    }
    if justification is not None:
        block["justification"] = justification
    return block


def verify_surface(
    *,
    project_root: Path,
    run_id: str,
    surface: str,
    runner: str | list[str] | None,
    justification: str | None,
    tests_run_override: int | None,
    retry_cap: int = DEFAULT_RETRY_CAP,
) -> tuple[int, dict]:
    """Run the gate. Returns ``(exit_code, evidence_block)``.

    The block is written to disk before this function returns so callers
    that hard-fail mid-flow still leave a partial evidence trail for the
    audit. Callers should consult the returned ``exit_code`` rather than
    raising — this keeps the CLI deterministic and tests cheap.
    """
    if surface not in VALID_SURFACES:
        block = build_block(
            surface=surface,
            runner=runner or "",
            exit_code=EXIT_INVALID_ARGS,
            tests_run=0,
            evidence_path="",
            justification=justification,
            attempts=0,
        )
        return EXIT_INVALID_ARGS, block

    if surface == "none":
        if not justification or not justification.strip():
            block = build_block(
                surface=surface,
                runner="",
                exit_code=EXIT_NONE_WITHOUT_JUSTIFICATION,
                tests_run=0,
                evidence_path="",
                justification=justification,
                attempts=0,
            )
            return EXIT_NONE_WITHOUT_JUSTIFICATION, block

        block = build_block(
            surface=surface,
            runner="",
            exit_code=0,
            tests_run=0,
            evidence_path="",
            justification=justification.strip(),
            attempts=0,
        )
        return EXIT_OK, block

    runner_repr: str
    if isinstance(runner, list):
        if not runner:
            block = build_block(
                surface=surface, runner="", exit_code=EXIT_INVALID_ARGS,
                tests_run=0, evidence_path="", justification=justification,
                attempts=0,
            )
            return EXIT_INVALID_ARGS, block
        runner_arg: list[str] | str = runner
        runner_repr = " ".join(runner)
    else:
        if not runner or not runner.strip():
            block = build_block(
                surface=surface, runner=runner or "",
                exit_code=EXIT_INVALID_ARGS, tests_run=0,
                evidence_path="", justification=justification, attempts=0,
            )
            return EXIT_INVALID_ARGS, block
        runner_arg = runner.strip()
        runner_repr = runner.strip()

    final_exit, combined_output, attempts = run_with_retries(
        runner_arg, project_root, retry_cap=retry_cap
    )

    runs_dir = project_root / ".shipwright" / "runs" / run_id
    runs_dir.mkdir(parents=True, exist_ok=True)
    log_path = runs_dir / "surface_verification.log"
    log_path.write_text(combined_output, encoding="utf-8")

    if tests_run_override is not None:
        tests_run = tests_run_override
    else:
        tests_run = parse_tests_run(combined_output, surface)

    if final_exit != 0:
        block = build_block(
            surface=surface,
            runner=runner_repr,
            exit_code=final_exit,
            tests_run=tests_run,
            evidence_path=str(log_path),
            justification=justification,
            attempts=attempts,
        )
        return EXIT_RUNNER_FAILED, block

    if tests_run == 0:
        block = build_block(
            surface=surface,
            runner=runner_repr,
            exit_code=final_exit,
            tests_run=0,
            evidence_path=str(log_path),
            justification=justification,
            attempts=attempts,
        )
        return EXIT_ZERO_TESTS, block

    block = build_block(
        surface=surface,
        runner=runner_repr,
        exit_code=final_exit,
        tests_run=tests_run,
        evidence_path=str(log_path),
        justification=justification,
        attempts=attempts,
    )
    return EXIT_OK, block


# ── AC-4 of iterate-2026-05-14-triage-producers-2: triage emission ───────

# Maps surface_verification.py's runtime-fail exit codes to the canonical
# condition string the iterate-2 spec locks in. EXIT_INVALID_ARGS (1) is
# intentionally NOT mapped — it's a config error (unknown surface name),
# not a substantive F0.5 fail-closed. The fourth condition "missing_block"
# is detected POST-COMMIT in `iterate_checks.py` (which audits the
# `shipwright_test_results.json.iterate_latest.surface_verification`
# block) — out of scope for THIS file since it IS the writer of the block.
_EXIT_TO_CONDITION = {
    EXIT_ZERO_TESTS: "tests_zero",
    EXIT_RUNNER_FAILED: "exit_nonzero",
    EXIT_NONE_WITHOUT_JUSTIFICATION: "surface_none_no_just",
}


def _f05_dedup_key(run_id: str, surface: str, condition: str) -> str:
    """Canonical F0.5 triage dedup key.

    Defined once so the producer (:func:`_emit_failure_to_triage`) and the
    resolve pass (:func:`_resolve_stale_f05_items`) cannot drift apart on
    the key shape.
    """
    return f"f0.5:{run_id}:{surface}:{condition}"


def _emit_failure_to_triage(
    project_root: Path,
    *,
    run_id: str,
    surface: str,
    condition: str,
    detail: str,
    evidence_path: str | None,
    commit: str | None = None,
) -> str | None:
    """Append a single F0.5 fail-closed item to ``.shipwright/triage.jsonl``.

    Best-effort. Returns the new triage id, ``None`` on dedup, and never
    raises (top-level exceptions are caught + logged to stderr — F0.5
    must STOP via its own exit_code regardless of triage state).

    ``dedup_key=f"f0.5:{run_id}:{surface}:{condition}"``, ``match_commit=True``,
    ``window_seconds=24*3600`` — daily re-flag until the operator
    promotes/dismisses.
    """
    try:
        shared_scripts = Path(__file__).resolve().parent
        if str(shared_scripts) not in sys.path:
            sys.path.insert(0, str(shared_scripts))
        from triage import append_triage_item_idempotent  # noqa: PLC0415
    except Exception as exc:  # noqa: BLE001
        sys.stderr.write(
            f"[f0.5] triage import failed: {type(exc).__name__}: {exc}\n"
        )
        return None

    title = f"F0.5 {condition} on surface={surface}"[:160]
    try:
        return append_triage_item_idempotent(
            project_root,
            source="f0.5",
            severity="critical",
            kind="bug",
            title=title,
            detail=detail or title,
            dedup_key=_f05_dedup_key(run_id, surface, condition),
            evidence_path=evidence_path,
            run_id=run_id,
            commit=commit,
            match_commit=True,
            window_seconds=24 * 3600,
        )
    except Exception as exc:  # noqa: BLE001
        sys.stderr.write(
            f"[f0.5] triage emit failed for {condition}: "
            f"{type(exc).__name__}: {exc}\n"
        )
        return None


def _detail_for_condition(
    condition: str,
    block: dict,
) -> str:
    """Compose a human-actionable detail string from the evidence block."""
    surface = block.get("surface", "<unknown>")
    runner = block.get("runner", "")
    tests_run = block.get("tests_run", "?")
    exit_code = block.get("exit_code", "?")
    if condition == "tests_zero":
        return (
            f"surface={surface} runner={runner!r} executed but matched zero "
            f"tests (tests_run=0). Likely Playwright --grep / pytest filter "
            f"mismatch. Verify the runner command actually targets the "
            f"newly-authored spec."
        )
    if condition == "exit_nonzero":
        return (
            f"surface={surface} runner={runner!r} exit_code={exit_code} "
            f"after retry cap (tests_run={tests_run}). See evidence log for "
            f"failure trail."
        )
    if condition == "surface_none_no_just":
        return (
            "surface=none was selected but no --justification was provided. "
            "F0.5 requires a one-line rationale when no surface is exercised."
        )
    return f"unknown F0.5 condition {condition!r}"


def _resolve_stale_f05_items(
    project_root: Path,
    *,
    run_id: str,
    surface: str,
    current_keys: set[str],
) -> int:
    """Dismiss still-open F0.5 items for ``(run_id, surface)`` whose
    condition cleared.

    Mirrors ``audit_detector.mirror_findings_to_triage``'s auto-dismiss:
    any ``source="f0.5"`` item still in ``triage`` status whose dedup key
    is absent from ``current_keys`` flips to ``dismissed`` with
    ``reason="f05Resolved"``.

    Scoped to ``(run_id, surface)`` (dedup-key prefix
    ``f0.5:{run_id}:{surface}:``). Two reasons the scope is this tight:
    a later iterate's surface check says nothing about an earlier
    iterate's failure (different ``run_id``); and a re-run of the SAME
    ``run_id`` on a DIFFERENT surface must not retract a genuine
    still-open failure from the original surface. This fixes the observed
    bug where an F0.5 P0 item from a runner that failed with exit 127 was
    never retracted when the SAME run + surface re-ran green minutes
    later. Operator-promoted / operator-dismissed items stay terminal
    (``status != "triage"`` is skipped).

    Best-effort — never raises; returns the number of items dismissed.
    """
    try:
        shared_scripts = Path(__file__).resolve().parent
        if str(shared_scripts) not in sys.path:
            sys.path.insert(0, str(shared_scripts))
        from triage import mark_status, read_all_items  # noqa: PLC0415
    except Exception as exc:  # noqa: BLE001
        sys.stderr.write(
            f"[f0.5] triage import failed (resolve): "
            f"{type(exc).__name__}: {exc}\n"
        )
        return 0

    prefix = f"f0.5:{run_id}:{surface}:"
    dismissed = 0
    try:
        for item in read_all_items(project_root):
            if item.get("source") != "f0.5":
                continue
            if item.get("status") != "triage":
                continue
            dk = item.get("dedupKey") or ""
            if not dk.startswith(prefix):
                continue
            if dk in current_keys:
                continue
            try:
                mark_status(
                    project_root,
                    item["id"],
                    new_status="dismissed",
                    by="f05Detector",
                    reason="f05Resolved",
                )
                dismissed += 1
            except Exception as exc:  # noqa: BLE001
                sys.stderr.write(
                    f"[f0.5] resolve mark_status failed for "
                    f"{item.get('id')}: {type(exc).__name__}: {exc}\n"
                )
    except Exception as exc:  # noqa: BLE001
        sys.stderr.write(
            f"[f0.5] resolve pass failed: {type(exc).__name__}: {exc}\n"
        )
    return dismissed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="F0.5 End-to-End Verification Gate orchestrator."
    )
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument(
        "--surface",
        required=True,
        choices=VALID_SURFACES,
        help="Behavior surface: web (Playwright) | cli (pytest/CLI) | api (HTTP) | none",
    )
    parser.add_argument(
        "--runner",
        default=None,
        help="Shell command to execute (required unless --surface=none).",
    )
    parser.add_argument(
        "--justification",
        default=None,
        help="Required when --surface=none.",
    )
    parser.add_argument(
        "--tests-run",
        type=int,
        default=None,
        help="Override tests_run count (skip stdout parsing).",
    )
    parser.add_argument(
        "--retry-cap",
        type=int,
        default=DEFAULT_RETRY_CAP,
    )
    args = parser.parse_args(argv)

    project_root = args.project_root.resolve()

    exit_code, block = verify_surface(
        project_root=project_root,
        run_id=args.run_id,
        surface=args.surface,
        runner=args.runner,
        justification=args.justification,
        tests_run_override=args.tests_run,
        retry_cap=args.retry_cap,
    )

    evidence_path = write_evidence(project_root, args.run_id, block)

    # Iterate-2 AC-4: mirror fail-closed conditions into
    # .shipwright/triage.jsonl BEFORE we return the exit code. Best-effort —
    # emission errors never change the exit semantics (F0.5 still STOPs
    # the iterate via its own exit_code).
    condition = _EXIT_TO_CONDITION.get(exit_code)
    if condition is not None:
        try:
            log_path = (
                project_root / ".shipwright" / "runs" / args.run_id
                / "surface_verification.log"
            )
            _emit_failure_to_triage(
                project_root,
                run_id=args.run_id,
                surface=str(block.get("surface", "")),
                condition=condition,
                detail=_detail_for_condition(condition, block),
                evidence_path=str(log_path) if log_path.exists() else None,
            )
        except Exception as exc:  # noqa: BLE001
            sys.stderr.write(
                f"[f0.5] triage emission top-level failed: "
                f"{type(exc).__name__}: {exc}\n"
            )

    # Iterate-2026-05-16 Bug 2 fix: resolve pass — a green (or
    # differently-failing) re-run of the SAME run_id + surface retracts
    # stale F0.5 items. EXIT_INVALID_ARGS is a config error (unknown
    # surface name), not a verdict on the surface, so it never resolves
    # anything — a stale item can survive one mistyped-surface run and is
    # then cleared by the next valid run.
    if exit_code != EXIT_INVALID_ARGS:
        try:
            surface_repr = str(block.get("surface", ""))
            current_keys: set[str] = set()
            if condition is not None:
                current_keys.add(
                    _f05_dedup_key(args.run_id, surface_repr, condition)
                )
            _resolve_stale_f05_items(
                project_root,
                run_id=args.run_id,
                surface=surface_repr,
                current_keys=current_keys,
            )
        except Exception as exc:  # noqa: BLE001
            sys.stderr.write(
                f"[f0.5] resolve pass top-level failed: "
                f"{type(exc).__name__}: {exc}\n"
            )

    summary = {
        "exit_code": exit_code,
        "surface": block.get("surface"),
        "tests_run": block.get("tests_run"),
        "evidence_block": str(evidence_path),
    }
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
