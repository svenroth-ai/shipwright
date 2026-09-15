#!/usr/bin/env python3
"""Validate deployment prerequisites.

Usage:
    uv run validate-deploy.py [--project-root <path>] [--confirm-failing-tests]

Output (JSON):
    {
        "success": true/false,
        "jelastic_token": true/false,
        "supabase_token": true/false,
        "supabase_linked": true/false,
        "has_migrations": true/false,
        "git_remote": "origin" | null,
        "test_gate": "passed" | "failing-unconfirmed" | "failing-confirmed" | "no-results",
        "warnings": [],
        "errors": []
    }

FR-01.08 criterion 1: a release is refused on failing tests until a person
confirms. ``_test_gate`` reads the same fields shipwright-deploy's own SKILL.md
Step B4 documents (``unit.status`` / ``e2e.status``) so both sides describe one
rule. A person's confirmation reaches this script ONLY via ``--confirm-failing-
tests`` — never inferred from an environment variable or a config default, so
the refusal cannot be silenced by anything but the flag the SKILL.md sets after
its own ``AskUserQuestion``.
"""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

# The routine, non-blocking E2E outcomes for a change with no startable web
# surface of its own. Anything else — "failed", "partial", "error", or an
# unrecognised value — is treated as a real E2E failure and blocks, matching
# criterion 1's actual intent (Tier-3 PR review round 5).
_E2E_NONBLOCKING_STATUSES = frozenset({"passed", "skipped", "not_run"})


def _test_gate(project_root: Path, confirmed: bool) -> tuple[str, str | None]:
    """Return ``(state, error_or_none)``.

    ``state`` is one of ``passed`` / ``failing-unconfirmed`` /
    ``failing-confirmed`` / ``no-results``. A genuinely ABSENT results file
    is treated the same as a failing one — ``/shipwright-deploy`` SKILL.md's
    prior (pre-mechanisation) Step B4 already required confirmation for
    *either* case ("tests failed **or** file does not exist"), and nothing
    in FR-01.08 asked to loosen that when mechanising criterion 1 into code.
    ``no-results`` is still reported as its own distinct ``state`` (rather
    than folded into ``failing-unconfirmed``) so a caller — and the
    standalone-invocation path in particular — can still tell "no test phase
    ran at all" apart from "tests ran and failed", but it BLOCKS exactly like
    ``failing-unconfirmed`` unless ``--confirm-failing-tests`` was passed.
    Tier-3 PR review, e4-checks-deploy-changelog round 3: an earlier version
    of this function treated ``no-results`` as warn-and-proceed, silently
    weakening the pre-existing confirmation requirement instead of
    mechanising it.

    A results file that EXISTS but fails to parse is treated as
    ``failing-*``, not ``no-results`` — external review (round 1,
    e4-checks-deploy-changelog): a present-but-corrupt file is not the same
    as an absent one, and the sibling deploy-phase check built in this same
    unit (``deploy_checks.check_test_gate_passed``) already blocks on
    malformed JSON; treating this gate's malformed case as a silent pass
    would have been inconsistent with that within one sub-iterate.
    """
    results_path = project_root / "shipwright_test_results.json"
    if not results_path.exists():
        if confirmed:
            return "no-results", None
        return "no-results", (
            "shipwright_test_results.json not found — re-run with "
            "--confirm-failing-tests only after a person has explicitly "
            "confirmed the deploy should proceed anyway"
        )

    unreadable_reason: str | None = None
    try:
        data = json.loads(results_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        unreadable_reason = str(exc)
        data = {}
    else:
        # A syntactically valid JSON value that isn't an object (`[]`, `"x"`,
        # `5`) would otherwise crash `.get()` below with AttributeError —
        # external code review (e4-checks-deploy-changelog): only invalid
        # JSON was caught, not valid-but-wrong-shaped JSON.
        if not isinstance(data, dict):
            unreadable_reason = f"root value is {type(data).__name__}, expected an object"
            data = {}

    if unreadable_reason is not None:
        if confirmed:
            return "failing-confirmed", None
        return "failing-unconfirmed", (
            f"shipwright_test_results.json exists but could not be read ({unreadable_reason}) "
            "— re-run with --confirm-failing-tests only after a person has "
            "explicitly confirmed the deploy should proceed anyway"
        )

    # shipwright_test_results.json is written in two shapes depending on
    # which flow last produced it: the full-pipeline /shipwright-test phase
    # writes unit/e2e/... at the TOP level (the shape _validate_test reads);
    # /shipwright-iterate's F5 step nests the identical sub-keys under
    # iterate_latest. A deploy can follow either flow, so this gate must
    # recognise both, or it silently never fires in an iterate-run repo —
    # caught by a real integration test against THIS repo's own file
    # (e4-checks-deploy-changelog).
    view = data
    if not isinstance(data.get("unit"), dict):
        nested = data.get("iterate_latest")
        if isinstance(nested, dict):
            view = nested

    unit_raw = view.get("unit")
    e2e_raw = view.get("e2e")
    unit = unit_raw if isinstance(unit_raw, dict) else {}
    e2e = e2e_raw if isinstance(e2e_raw, dict) else {}
    unit_ok = unit.get("status") == "passed"
    # E2E is non-blocking, matching the pipeline's own _validate_test
    # convention (constitution: "E2E can be flaky" — an "inform" warning,
    # never an "ask" gate). "not_run"/"skipped"/absent are the routine case
    # for a backend-only change with no startable web surface and must not
    # block. A blanket `status in (passed, skipped)` requirement was caught
    # by a real integration test against THIS repo's own current results
    # file, where e2e is routinely "not_run" — that stricter check would
    # have refused every deploy here (e4-checks-deploy-changelog). An
    # ALLOWLIST of the routine non-blocking statuses, not a blocklist of one
    # bad value, is what actually implements "only a reported partial
    # failure does [block]" — Tier-3 PR review round 5: the earlier
    # `!= "partial"` blocklist let "failed", "error", or any other explicit
    # failure status through as non-blocking too, which was never the
    # intent.
    e2e_status = e2e.get("status")
    e2e_ok = e2e_status is None or e2e_status in _E2E_NONBLOCKING_STATUSES
    if unit_ok and e2e_ok:
        return "passed", None

    if confirmed:
        return "failing-confirmed", None

    return "failing-unconfirmed", (
        f"tests have not passed (unit={unit.get('status')!r}, "
        f"e2e={e2e.get('status')!r}) — re-run with --confirm-failing-tests "
        "only after a person has explicitly confirmed the deploy should "
        "proceed anyway"
    )


def _has_migrations(project_root: Path) -> bool:
    """Check if supabase/migrations/ contains any forward .sql files."""
    migrations_dir = project_root / "supabase" / "migrations"
    if not migrations_dir.is_dir():
        return False
    for f in migrations_dir.iterdir():
        if f.is_file() and f.suffix == ".sql" and not f.name.startswith("."):
            return True
    return False


def _is_supabase_linked(project_root: Path) -> bool:
    """Check if supabase project is linked (config.toml + .supabase/ exist)."""
    has_config = (project_root / "supabase" / "config.toml").exists()
    has_link = (project_root / ".supabase").is_dir()
    return has_config and has_link


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate deployment prerequisites")
    parser.add_argument("--project-root", help="Path to project root")
    parser.add_argument(
        "--confirm-failing-tests", action="store_true",
        help="A person has explicitly confirmed deploying despite failing/missing tests",
    )
    args = parser.parse_args()

    project_root = Path(args.project_root) if args.project_root else Path.cwd()

    warnings: list[str] = []
    errors: list[str] = []

    jelastic_token = bool(os.environ.get("JELASTIC_TOKEN"))
    supabase_token = bool(os.environ.get("SUPABASE_ACCESS_TOKEN"))
    has_migrations = _has_migrations(project_root)
    supabase_linked = _is_supabase_linked(project_root)
    test_gate, test_gate_error = _test_gate(project_root, args.confirm_failing_tests)

    if test_gate_error:
        errors.append(test_gate_error)
    elif test_gate == "no-results":
        warnings.append(
            "shipwright_test_results.json not found — deploying without test "
            "verification, confirmed by a person (--confirm-failing-tests)"
        )
    elif test_gate == "failing-confirmed":
        warnings.append("deploying with failing tests — confirmed by a person (--confirm-failing-tests)")

    if not jelastic_token:
        errors.append("JELASTIC_TOKEN not set — deployment will fail")

    if has_migrations and not supabase_token:
        errors.append(
            "SUPABASE_ACCESS_TOKEN not set — required because supabase/migrations/ "
            "contains migration files. Get token at: https://supabase.com/dashboard/account/tokens"
        )
    elif not has_migrations and not supabase_token:
        warnings.append("SUPABASE_ACCESS_TOKEN not set — migrations will be skipped (no migrations found)")

    if has_migrations and not supabase_linked:
        errors.append(
            "Supabase project not linked — run 'supabase init' and 'supabase link --project-ref <ref>' first"
        )

    # Check git remote
    git_remote = None
    try:
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            capture_output=True, text=True, encoding="utf-8",
        )
        if result.returncode == 0:
            git_remote = result.stdout.strip()
    except (FileNotFoundError, OSError):
        warnings.append("git not available")

    success = len(errors) == 0

    print(json.dumps({
        "success": success,
        "jelastic_token": jelastic_token,
        "supabase_token": supabase_token,
        "supabase_linked": supabase_linked,
        "has_migrations": has_migrations,
        "git_remote": git_remote,
        "test_gate": test_gate,
        "warnings": warnings,
        "errors": errors,
    }, indent=2))

    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
