#!/usr/bin/env python3
"""Has the stored data moved past the version we are rolling back to?

Rolling the application code back to an older version while the database has
already migrated forward puts the old code in front of a schema it does not
know. This module answers the narrow, checkable half of that question: which
migration files exist now that did not exist at the target ref.

It is deliberately app-tier only — it detects the mismatch, it never undoes
data. What to *do* about the mismatch is the target's own answer, recorded as
``rollback.data_rollback_strategy`` in its deploy profile.

Git is invoked with argument arrays and ``--`` path separators, never a shell:
the ref is operator input and reaches ``argv`` directly.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

DEFAULT_MIGRATIONS_DIR = "supabase/migrations"

# Conservative subset of git check-ref-format. The ref crosses two untrusted
# boundaries — git argv and the hosting API — so it is validated once, here, at
# the module that owns the git boundary, and re-used by the rollback orchestrator.
# Deliberately stricter than git: this is an allowlist for a value that will be
# executed against, not a faithful reimplementation of check-ref-format.
_REF_CHARS = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,254}$")
_REF_FORBIDDEN = ("..", "@{", "//", "\\", "^", "~", ":", "?", "*", "[")


def is_valid_ref(ref: str) -> bool:
    """True when ``ref`` is a git ref name safe to pass to git and the host."""
    if not ref or not _REF_CHARS.match(ref):
        return False
    if any(bad in ref for bad in _REF_FORBIDDEN):
        return False
    if ref.endswith(("/", ".")):
        return False
    # git's rules are per slash-separated component, not per whole string:
    # `feature/.hidden` and `release.lock/tip` are both invalid refs.
    return all(
        component and not component.startswith(".")
        and not component.endswith((".", ".lock"))
        for component in ref.split("/")
    )


def _git(project_root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(project_root), *args],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        check=False,
    )


def _lines(output: str) -> list[str]:
    return [line.strip() for line in output.split("\n") if line.strip()]


def detect(
    project_root: Path | str | None,
    target_ref: str,
    migrations_dir: str = DEFAULT_MIGRATIONS_DIR,
) -> dict:
    """Report whether migrations exist now that were absent at ``target_ref``.

    ``status`` is one of:

    - ``not-checked``   — no working tree was supplied (library call);
    - ``not-applicable``— the project has no migrations directory;
    - ``unknown``       — not a git repo, or the ref cannot be resolved. This
      **refuses** like ``drifted`` does: being unable to answer "has the data
      moved on?" is not permission to proceed;
    - ``clean``         — no migrations were added since the ref;
    - ``drifted``       — migrations were added since the ref.
    """
    blank = {"status": "not-checked", "drifted": None, "migrations": [], "reason": None}
    if project_root is None:
        return {**blank, "reason": "no project root supplied"}
    if not is_valid_ref(target_ref):
        return {**blank, "status": "unknown", "reason": f"invalid ref {target_ref!r}"}

    root = Path(project_root)
    if not (root / migrations_dir).is_dir():
        return {**blank, "status": "not-applicable", "drifted": False,
                "reason": f"{migrations_dir} does not exist"}

    if _git(root, "rev-parse", "--git-dir").returncode != 0:
        return {**blank, "status": "unknown", "reason": f"{root} is not a git repository"}

    resolved = _git(root, "rev-parse", "--verify", "--quiet", f"{target_ref}^{{commit}}")
    if resolved.returncode != 0:
        return {**blank, "status": "unknown",
                "reason": f"git cannot resolve {target_ref!r} in this working tree"}

    added = _git(root, "diff", "--diff-filter=A", "--name-only", target_ref, "--", migrations_dir)
    # A migration nobody has committed yet is still a schema that moved on.
    untracked = _git(root, "ls-files", "--others", "--exclude-standard", "--", migrations_dir)
    if added.returncode != 0 or untracked.returncode != 0:
        detail = (added.stderr or untracked.stderr or "").strip()
        return {**blank, "status": "unknown", "reason": f"git comparison failed: {detail}"}

    migrations = sorted(set(_lines(added.stdout)) | set(_lines(untracked.stdout)))
    return {
        "status": "drifted" if migrations else "clean",
        "drifted": bool(migrations),
        "migrations": migrations,
        "reason": None,
    }


def gate(
    project_root: Path | str | None,
    target_ref: str,
    migrations_dir: str = DEFAULT_MIGRATIONS_DIR,
    *,
    strategy: str | None = None,
    target_id: str | None = None,
    ack: bool = False,
) -> tuple[dict, str | None]:
    """Decide whether stored data blocks this rollback.

    Returns the drift report plus a refusal reason, or ``None`` to proceed.
    ``strategy`` is the target's declared ``rollback.data_rollback_strategy`` —
    a target that declares ``none-app-only`` has no data tier moving underneath
    its app, so the question does not arise and the check is skipped entirely.
    """
    if strategy == "none-app-only":
        return {
            "status": "not-applicable", "drifted": False, "migrations": [],
            "reason": f"{target_id or 'the target'} declares "
                      "data_rollback_strategy=none-app-only",
        }, None

    report = detect(project_root, target_ref, migrations_dir)
    if report["status"] not in ("drifted", "unknown") or ack:
        return report, None

    named = strategy or "not declared by the target"
    if report["status"] == "drifted":
        listed = ", ".join(report["migrations"][:10])
        detail = (
            f"stored data has moved past {target_ref}: {len(report['migrations'])} "
            f"migration(s) exist that it does not know ({listed}). Restoring the "
            f"code would put it in front of a schema it was never written for. "
            f"This target's data-rollback strategy is '{named}'. Re-run with "
            f"--ack-data-drift once you have decided what happens to the data."
        )
    else:
        detail = (
            f"cannot tell whether stored data has moved past {target_ref} "
            f"({report['reason']}). Refusing rather than guessing; this target's "
            f"data-rollback strategy is '{named}'. Re-run with --ack-data-drift "
            f"to proceed anyway."
        )
    return report, detail


__all__ = ["DEFAULT_MIGRATIONS_DIR", "detect", "gate", "is_valid_ref"]
