"""Canonical ``.shipwright/`` artifact-ignore block: parse SSoT + merge.

Single source of truth for which ``.shipwright/`` paths every consuming
project gitignores. The rules live in
``shared/templates/shipwright-gitignore.template`` between BEGIN/END
markers; this module parses them and merges the missing ones idempotently
into a target project's ``.gitignore``. Used by ``/shipwright-adopt`` and
``/shipwright-project`` so framework-side gitignore changes propagate to
consuming projects, and by the drift test
``shared/tests/test_gitignore_template_congruent.py``.

Line-level merge (not whole-block replace): a rule already present anywhere
in the target is never duplicated; only genuinely missing rules are added —
self-heals an EXISTING project when a later template revision introduces a
new re-exclude.

Add-only is not enough alone: a canonical rule can be *narrowed* (a
whole-directory ignore replaced by file-level ones, e.g.
iterate-2026-08-08-track-decision-drops), invisible to "missing" above —
neither added nor removed. The SUPERSEDED block (:func:`read_superseded_rules`)
closes that: a listed rule is actively stripped, in the SAME pass that adds
its replacement(s). See the template's own SUPERSEDED comment.

Deliberately zero intra-``lib`` imports: a prior attempt to extract
``_strip_superseded`` into a sibling module and re-import it with
``from lib.X import Y`` broke a dotted-path consumer (``write-project-
config.py``) via a cross-plugin ``sys.modules['lib']`` collision. Keep this
module self-contained — see iterate-2026-08-15-gitignore-selfheal-outside-
block-retraction for the full story.
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
    """Resolve the SSoT template relative to this module — ``parents[2]`` of
    ``shared/scripts/lib/<this>`` is always the self-contained ``shared/``
    directory, in both the monorepo and the runtime plugin cache.
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

    Comments/blank lines inside the block are dropped. Returns ``[]`` when
    the markers are absent or malformed. Defaults to the canonical-block
    markers; pass the ``SUPERSEDED_*`` pair to read the retraction block.
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
    legal — returns ``[]`` rather than raising.
    """
    path = template_path or default_template_path()
    return extract_marked_rules(
        path.read_text(encoding="utf-8"),
        begin=SUPERSEDED_BEGIN_MARKER,
        end=SUPERSEDED_END_MARKER,
    )


def _strip_superseded(text: str, superseded: list[str]) -> tuple[str, list[str]]:
    """Remove *superseded* rule-lines found inside the managed BEGIN/END
    block, and also before it, returning ``(new_text, retracted)``.

    A rule that predates the block's own scaffolding sits ahead of it (e.g.
    shipwright-webui's decision-drops line, weeks older than that project's
    first managed block) — never after: nothing this module writes lands
    past the block's END marker, so a match found there is a project's own
    later-added content and is left alone.

    Extending the scope before the block requires an unambiguous single
    block: exactly one BEGIN, exactly one END, in that order. Zero markers
    strips anywhere; anything else malformed (duplicate/unmatched/reversed)
    falls back to scanning ONLY the first complete BEGIN-to-following-END
    region — a rule inside a second, malformed pair is preserved exactly
    like content after a well-formed block, never re-scanned (external
    review, 2026-08-16: the prior toggle-based fallback re-armed on every
    BEGIN it saw, so a second complete pair was wrongly still in scope).
    """
    if not superseded:
        return text, []
    superset = set(superseded)
    lines = text.splitlines()
    begins = [i for i, raw in enumerate(lines) if raw.strip() == BEGIN_MARKER]
    ends = [i for i, raw in enumerate(lines) if raw.strip() == END_MARKER]

    if not begins and not ends:
        lo, hi = 0, len(lines) - 1
    elif len(begins) == 1 and len(ends) == 1 and begins[0] < ends[0]:
        lo, hi = 0, ends[0]
    else:
        first_end = next((e for e in ends if e > begins[0]), None) if begins else None
        lo, hi = (begins[0] + 1, first_end) if begins and first_end is not None else (0, -1)

    retracted: list[str] = []
    out: list[str] = []
    for i, raw in enumerate(lines):
        stripped = raw.strip()
        if stripped in superset and lo <= i <= hi:
            retracted.append(stripped)
        else:
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
    target is left untouched; missing rules are added inside a marked
    managed block. A superseded rule is stripped first (see
    :func:`_strip_superseded`), in the SAME pass that adds its canonical
    replacement(s) — add-only cannot retract a narrowed/removed rule.

    Returns ``{action, path, added, retracted, already_present,
    total_canonical}``; ``action`` is ``unchanged`` / ``created`` / ``updated``.
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
    """Pure planner: return ``(merged_text, changed, added, retracted)``.

    Side-effect-free twin of :func:`merge_canonical_block` — reuses the SAME
    merge primitives so ``lib.gitignore_selfheal`` never reinvents the merge.
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
