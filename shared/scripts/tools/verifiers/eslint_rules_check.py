"""Build-phase verifier: the profile's architecture-rule ESLint blocks survived the app creation.

The build phase creates the Next.js app, and create-next-app writes its own ``eslint.config.mjs``;
the blocks that /shipwright-project step 7 merged earlier can be gone, and lint then passes with no
architecture rules. This check reads the project's config through
``shared/scripts/eslint_architecture_rules.py`` and names what is missing and the repair command.

Severity: a missing, unpaired or out-of-array block is an ERROR (WARNING while there is no
package.json yet, i.e. before the app exists); a legacy ``.eslintrc*`` only, a stale block (a block
folded by hand with an existing option differs from the profile on purpose) and a config entry after
the blocks are WARNINGs. A project whose profile has no ESLint rule, or whose profile cannot be
resolved, is skipped (the resolver reports the latter itself).
"""

from __future__ import annotations

from pathlib import Path

import eslint_architecture_rules as ear

from .common import CheckResult, Severity

NAME = "eslint_architecture_rules_present"
_HARD = ("missing", "unpaired", "outside")
# absolute path of the shipped tool: the repair must run from a user project, where no shared/ folder exists
_TOOL = Path(__file__).resolve().parents[1] / "check_eslint_architecture_rules.py"
FIX = f'uv run "{_TOOL}" --project-root "<project root>" --apply'


def check_eslint_architecture_rules(project_root: Path, **_kw) -> CheckResult:
    try:
        profile, rules = ear.rules_for_project(project_root, quiet=True)
    except Exception as exc:  # noqa: BLE001 - no profile or an invalid one is not this check's finding
        return CheckResult(NAME, None, f"skipped: profile not resolved ({type(exc).__name__})", Severity.SKIPPED.value)
    if not rules:
        return CheckResult(NAME, None, f"skipped: profile {profile} has no rule with an ESLint fragment",
                           Severity.SKIPPED.value)
    try:
        rep = ear.check(project_root, rules)
    except (OSError, ValueError) as exc:  # an unreadable or non-UTF-8 config must not crash the whole build canon
        return CheckResult(NAME, False, f"cannot read the eslint config: {type(exc).__name__}: {exc}", Severity.WARNING.value)
    bad = rep.bad
    if not bad:
        deps = [n for n in rep.notes if "devDependencies" in n]
        if deps:  # the blocks are there but ESLint cannot run them
            return CheckResult(NAME, False, f"blocks present in {rep.config}, but {deps[0]}", Severity.WARNING.value)
        return CheckResult(NAME, True, f"{len(rules)} architecture-rule block(s) present in {rep.config}")
    hard = [f for f in bad if f.status in _HARD]
    detail = "; ".join(f"{f.rule_id}: {f.status}" + (f" ({f.detail})" if f.detail else "") for f in bad)
    detail += f". Repair: {FIX}".replace("<project root>", str(project_root))
    if any(f.status == "stale" for f in bad):
        detail += " (a stale block may hold a hand-folded option; --replace-stale overwrites it)"
    app_exists = (Path(project_root) / "package.json").is_file()
    legacy_only = rep.config is None and rep.legacy
    error = bool(hard) and app_exists and not legacy_only
    return CheckResult(NAME, False, detail, Severity.ERROR.value if error else Severity.WARNING.value)
