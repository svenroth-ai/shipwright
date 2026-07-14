"""contract_baseline — the immutable half of the cross-repo output-contract gate.

**This module is what makes the gate a mechanism rather than a reminder.** Pinning a
shape in a test cannot enforce a version bump, because the pin is editable in the same
change: update it to match the rename and the diff is empty, the required bump is "none",
and any version passes. *Editing the pin erases the evidence the check depends on.*

So the baseline is read from ``origin/main`` — the one thing a pull request cannot
rewrite. Everything here exists to answer two questions honestly:

* *What shape did we promise the consumer?* → :func:`published_baseline`
* *Has anyone quietly rewritten that promise?* → :func:`frozen_fixture_diff`,
  :func:`published_fixtures`
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

try:  # Package context — `from lib.contract_baseline import …` (shared/tests).
    from .contract_skeleton import ContractViolation, parse_version
except ImportError:  # Loaded by file path (the plugin gates): no parent package.
    # The plugin gates deliberately avoid sys.path — they already bind the `lib` /
    # `scripts.lib` namespaces for their own modules, and a shared package competing for
    # those would shadow them in a combined pytest run (ADR-045). They register
    # `contract_skeleton` in sys.modules under its bare name before loading this.
    from contract_skeleton import ContractViolation, parse_version  # type: ignore


def _git(repo_root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            ["git", "-C", str(repo_root), *args],
            capture_output=True, text=True, timeout=30, check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:  # pragma: no cover - defensive
        raise ContractViolation(f"cannot read the git baseline: {exc}") from exc


def git_show(repo_root: Path, ref: str, relpath: str) -> str | None:
    """File content at ``ref``, or ``None`` when it does not exist there."""
    done = _git(repo_root, "show", f"{ref}:{relpath}")
    return done.stdout if done.returncode == 0 else None


def _canonical(text: str) -> Any:
    """Parse, so the comparison ignores byte noise (CRLF, trailing newline)."""
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise ContractViolation(f"contract fixture is not valid JSON: {exc}") from exc


def published_fixtures(
    repo_root: Path, contracts_dir: str, stem: str, *, ref: str = "origin/main"
) -> list[str]:
    """The versions ``ref`` publishes for ``stem``, oldest first.

    Read from git, never from the working tree: a fixture DELETED on this branch is still
    a promise the consumer was given, so it must still be accounted for.
    """
    done = _git(repo_root, "ls-tree", "--name-only", ref, f"{contracts_dir}/")
    found: list[tuple[tuple[int, int], str]] = []
    for line in done.stdout.splitlines() if done.returncode == 0 else []:
        name = Path(line.strip()).name
        if not (name.startswith(f"{stem}-") and name.endswith(".json")):
            continue
        raw = name[len(stem) + 1: -len(".json")]
        try:
            found.append((parse_version(raw), raw))
        except ContractViolation:
            continue  # Not a versioned contract fixture — ignore it.
    return [version for _, version in sorted(found)]


def published_baseline(
    repo_root: Path, contracts_dir: str, stem: str, *, ref: str = "origin/main"
) -> tuple[str, Any] | None:
    """The contract as ``ref`` published it: ``(version, fixture)``, or ``None``.

    The baseline is the highest version ``ref`` carries — that is what the consumer has
    been told to expect. ``None`` means ``ref`` publishes no contract for this stem.
    Callers must NOT treat ``None`` as "all clear" without checking
    :func:`any_published_contract` — see its docstring for why.
    """
    versions = published_fixtures(repo_root, contracts_dir, stem, ref=ref)
    if not versions:
        return None
    newest = versions[-1]
    content = git_show(repo_root, ref, f"{contracts_dir}/{stem}-{newest}.json")
    return None if content is None else (newest, _canonical(content))


def any_published_contract(repo_root: Path, *, ref: str = "origin/main") -> bool:
    """Does ``ref`` publish ANY contract fixture, anywhere in the tree?

    Guards the bootstrap stand-down. ``published_baseline`` returns ``None`` both when a
    contract has genuinely never been published (the commit that introduces one: nothing
    can be broken, so the gate rightly stands down) and when it simply looked in the
    wrong place — because someone renamed ``tests/contracts/`` or changed the fixture
    stem. The second case silently DISARMS the gate, and a skipped gate is green.

    So a caller that finds no baseline must confirm the repo publishes no contract at all
    before standing down. If any exist elsewhere, the constants are stale, not the world.
    """
    done = _git(repo_root, "ls-tree", "-r", "--name-only", ref)
    if done.returncode != 0:
        return False
    return any(
        "/contracts/" in line and line.strip().endswith(".json")
        for line in done.stdout.splitlines()
    )


def frozen_fixture_diff(
    repo_root: Path, relpath: str, *, ref: str = "origin/main"
) -> str | None:
    """Guard the baseline: a published fixture must never be edited or deleted.

    ``None`` when unchanged, or when new on this branch (adding a version is the
    sanctioned path). Otherwise the reason. Without this, a developer greens a broken
    contract simply by rewriting the pin it is checked against.
    """
    baseline = git_show(repo_root, ref, relpath)
    if baseline is None:
        return None  # Not published yet — a new version, which is how change lands.
    path = repo_root / relpath
    if not path.is_file():
        return (
            f"{relpath} is a PUBLISHED contract fixture and was DELETED.\n"
            f"The consumer was told that this version means that shape, and is entitled\n"
            "to look it up. Superseding a version does not retract it — add the new\n"
            "fixture and leave this one in place."
        )
    if _canonical(path.read_text(encoding="utf-8")) == _canonical(baseline):
        return None
    return (
        f"{relpath} is a PUBLISHED contract fixture and was MODIFIED.\n"
        f"It is frozen against {ref}: the consumer has already been told that this\n"
        "version means this shape. Editing it in place would let a breaking change pass\n"
        "the gate silently — the exact failure this gate exists to prevent.\n\n"
        "  Add a NEW versioned fixture and bump schema_version instead."
    )
