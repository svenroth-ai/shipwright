"""Canonical ``.shipwright/`` artifact-ignore block: parse SSoT + merge.

Single source of truth for which ``.shipwright/`` paths every consuming
project gitignores. The rules live in
``shared/templates/shipwright-gitignore.template`` between BEGIN/END
markers; this module parses them and merges the missing ones idempotently
into a target project's ``.gitignore``.

Used by ``/shipwright-adopt`` and ``/shipwright-project`` so framework-side
gitignore changes propagate to consuming projects, and by the drift test
``shared/tests/test_gitignore_template_congruent.py`` which keeps the
template congruent with the framework's own ``.gitignore``.

Design rationale (line-level merge, not whole-block replace): a rule
already present anywhere in the target is never duplicated; only genuinely
missing rules are added. This matches the "add missing lines, no
duplicates" contract and self-heals EXISTING projects when a later
template revision introduces a new re-exclude (re-running adopt/project
back-fills just the new line) — the regression that left shipwright-webui
missing ``/.shipwright/agent_docs/runtime/``.

Add-only is not enough alone: a canonical rule can be *narrowed* (a
whole-directory ignore replaced by two file-level ignores, e.g.
iterate-2026-08-08-track-decision-drops), and a rule absent from
``canonical`` is invisible to "missing" above — neither added nor removed.
The SUPERSEDED block (a second marker-delimited template section, parsed
by :func:`read_superseded_rules`) closes that gap: a listed rule is
actively stripped from a target's managed block if present, in the SAME
pass that adds its replacement(s). See the template's own SUPERSEDED
comment for the rationale.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BEGIN_MARKER = "# === BEGIN Shipwright canonical .shipwright artifact-ignore (managed) ==="
END_MARKER = "# === END Shipwright canonical .shipwright artifact-ignore (managed) ==="

SUPERSEDED_BEGIN_MARKER = (
    "# === BEGIN Shipwright superseded .shipwright artifact-ignore rules (managed) ==="
)
SUPERSEDED_END_MARKER = (
    "# === END Shipwright superseded .shipwright artifact-ignore rules (managed) ==="
)

_MANAGED_HEADER_LINES = (
    "# Managed by Shipwright (adopt/project). Do not hand-edit — re-running",
    "# /shipwright-adopt or /shipwright-project back-fills missing rules.",
    "# SSoT: shared/templates/shipwright-gitignore.template",
)


def default_template_path() -> Path:
    """Resolve the SSoT template relative to this module.

    Works both in the monorepo (``shared/`` at repo root) and in the
    runtime plugin cache (``shared/`` at the cache root): ``shared/`` is
    self-contained, so ``parents[2]`` of ``shared/scripts/lib/<this>`` is
    always the ``shared/`` directory.
    """
    return (
        Path(__file__).resolve().parents[2]
        / "templates"
        / "shipwright-gitignore.template"
    )


def extract_marked_rules(
    text: str, *, begin: str = BEGIN_MARKER, end: str = END_MARKER
) -> list[str]:
    """Return the ordered rule-lines between *begin*/*end* markers in *text*.

    Comments (``#`` lines) and blank lines inside the block are dropped;
    only actual gitignore patterns are returned, stripped. Returns ``[]``
    when the markers are absent or malformed (END without a preceding
    BEGIN). Defaults to the canonical-block markers; pass
    ``SUPERSEDED_BEGIN_MARKER``/``SUPERSEDED_END_MARKER`` to read the
    retraction block instead — same parsing rules, different section.
    """
    inside = False
    rules: list[str] = []
    for raw in text.splitlines():
        stripped = raw.strip()
        if stripped == begin:
            inside = True
            continue
        if stripped == end:
            inside = False
            continue
        if not inside or not stripped or stripped.startswith("#"):
            continue
        rules.append(stripped)
    return rules


def read_canonical_rules(template_path: Path | None = None) -> list[str]:
    """Return the canonical rule-lines from the SSoT template (ordered)."""
    path = template_path or default_template_path()
    rules = extract_marked_rules(path.read_text(encoding="utf-8"))
    if not rules:
        raise ValueError(
            f"no canonical artifact-ignore rules found between markers in {path}; "
            "the template is malformed or missing its BEGIN/END markers"
        )
    return rules


def read_superseded_rules(template_path: Path | None = None) -> list[str]:
    """Return the ordered retracted rule-lines from the SSoT template.

    Unlike :func:`read_canonical_rules`, an empty/absent SUPERSEDED block is
    legal (no rule has ever been retracted yet) — returns ``[]`` rather than
    raising.
    """
    path = template_path or default_template_path()
    return extract_marked_rules(
        path.read_text(encoding="utf-8"),
        begin=SUPERSEDED_BEGIN_MARKER,
        end=SUPERSEDED_END_MARKER,
    )


def _strip_superseded(text: str, superseded: list[str]) -> tuple[str, list[str]]:
    """Remove any *superseded* rule-lines found inside the target's OWN
    managed block (between its BEGIN/END markers), returning
    ``(new_text, retracted)`` — the ordered subset actually present and
    removed.

    Scoped to the managed block deliberately: this only undoes what a prior
    ``gitignore_canon`` run itself added, matching the block's own "do not
    hand-edit" contract. A rule that happens to match outside the block
    (a project's own hand-written line) is left alone.
    """
    if not superseded or BEGIN_MARKER not in text:
        return text, []
    superset = set(superseded)
    inside = False
    retracted: list[str] = []
    out: list[str] = []
    for raw in text.splitlines():
        stripped = raw.strip()
        if stripped == BEGIN_MARKER:
            inside = True
            out.append(raw)
            continue
        if stripped == END_MARKER:
            inside = False
            out.append(raw)
            continue
        if inside and stripped in superset:
            retracted.append(stripped)
            continue
        out.append(raw)
    if not retracted:
        return text, []
    result = "\n".join(out)
    if text.endswith("\n") and not result.endswith("\n"):
        result += "\n"
    return result, retracted


def _insert_missing(text: str, missing: list[str]) -> str:
    """Return *text* with *missing* rules added inside the managed block.

    If a managed block already exists, the missing rules are inserted just
    before its END marker (extending it). Otherwise a fresh managed block
    is appended at EOF (separated by a blank line from prior content).
    Canonical order is preserved because *missing* is built by iterating
    the canonical list in order, so gitignore negation/re-exclude ordering
    stays valid.
    """
    if BEGIN_MARKER in text and END_MARKER in text:
        out: list[str] = []
        for line in text.splitlines():
            if line.strip() == END_MARKER:
                out.extend(missing)
            out.append(line)
        result = "\n".join(out)
        return result if result.endswith("\n") else result + "\n"

    block = "\n".join(
        [BEGIN_MARKER, *_MANAGED_HEADER_LINES, *missing, END_MARKER]
    )
    if not text:
        return block + "\n"
    prefix = text if text.endswith("\n") else text + "\n"
    return f"{prefix}\n{block}\n"


def merge_canonical_block(
    project_root: Path,
    *,
    template_path: Path | None = None,
) -> dict:
    """Idempotently merge the canonical rules into ``project_root/.gitignore``.

    Line-level merge: a canonical rule already present anywhere in the
    target ``.gitignore`` (exact stripped match) is left untouched; missing
    rules are added inside a marked managed block. A rule listed in the
    template's SUPERSEDED block is actively stripped from the target's
    managed block first (see :func:`_strip_superseded`), in the SAME pass
    that adds its canonical replacement(s) — add-only cannot retract a
    narrowed or removed rule, so this is not optional for staying
    congruent with a template that has ever retracted anything. Re-running
    is a no-op once every canonical rule is present and no superseded rule
    remains.

    Returns ``{action, path, added, retracted, already_present,
    total_canonical}`` where ``action`` is ``unchanged`` / ``created`` /
    ``updated`` (``created`` = the ``.gitignore`` did not exist before).
    """
    canonical = read_canonical_rules(template_path)
    superseded = read_superseded_rules(template_path)
    gi_path = project_root / ".gitignore"
    existed = gi_path.exists()
    text = gi_path.read_text(encoding="utf-8") if existed else ""

    text, retracted = _strip_superseded(text, superseded)
    present = {line.strip() for line in text.splitlines()}
    missing = [rule for rule in canonical if rule not in present]
    already_present = [rule for rule in canonical if rule in present]

    if not missing and not retracted:
        return {
            "action": "unchanged",
            "path": str(gi_path),
            "added": [],
            "retracted": [],
            "already_present": already_present,
            "total_canonical": len(canonical),
        }

    gi_path.write_text(_insert_missing(text, missing), encoding="utf-8")
    return {
        "action": "updated" if existed else "created",
        "path": str(gi_path),
        "added": missing,
        "retracted": retracted,
        "already_present": already_present,
        "total_canonical": len(canonical),
    }


def plan_merge(
    text: str, *, template_path: Path | None = None
) -> tuple[str, bool, list[str], list[str]]:
    """Pure planner: return ``(merged_text, changed, added, retracted)`` for
    *text*.

    Side-effect-free twin of :func:`merge_canonical_block` (which writes the
    file). Reuses the SAME merge primitives (``read_canonical_rules`` +
    ``read_superseded_rules`` + ``_strip_superseded`` + ``_insert_missing``)
    so the self-heal commit-path (``lib.gitignore_selfheal``) never
    reinvents the merge. ``added`` is the ordered subset of canonical rules
    missing from *text*; ``retracted`` is the ordered subset of superseded
    rules that were present in *text* and stripped.
    """
    canonical = read_canonical_rules(template_path)
    superseded = read_superseded_rules(template_path)
    text, retracted = _strip_superseded(text, superseded)
    present = {line.strip() for line in text.splitlines()}
    missing = [rule for rule in canonical if rule not in present]
    if not missing and not retracted:
        return text, False, [], []
    return _insert_missing(text, missing), True, missing, retracted


def main(argv: list[str] | None = None) -> int:
    """CLI: merge the canonical block into a project's .gitignore.

    Enables manual self-heal of an already-adopted project:
    ``uv run gitignore_canon.py --project-root <path>``.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--project-root",
        default=".",
        help="Target project root containing (or to contain) .gitignore",
    )
    parser.add_argument(
        "--template",
        default=None,
        help="Override the SSoT template path (default: bundled template)",
    )
    args = parser.parse_args(argv)
    result = merge_canonical_block(
        Path(args.project_root).resolve(),
        template_path=Path(args.template).resolve() if args.template else None,
    )
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
