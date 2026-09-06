"""Diff-scoped, non-dodgeable FR-row hygiene gate (iterate-2026-09-06-fr-hygiene-touched-rows).

``shared/fr-authoring.md``'s substantive rules — I1 (name hygiene), I2
(description hygiene), I7 (criterion shape) — are Group I's ADVISORY checks
(``plugins/shipwright-compliance/scripts/audit/group_i.py``), deliberately so:
an adopted repo's pre-existing spec must be able to clean up gradually without
reddening CI (`fr-authoring.md` §7). That is correct for rows nobody in THIS
run touched. It leaves a real gap for the rows this run itself writes or
edits: nothing stopped a currently-authored FR name/description from carrying
implementation prose, or a currently-authored criterion from being a status
paragraph instead of an assertion — exactly the leadwright failure mode this
gate exists for (`references/path-a-feature.md` already carries the unenforced
prose "do not let an edit smuggle a file path, symbol, or ADR number into a row
that was previously clean").

**What "touched" means.** An FR id is touched when, comparing the merge-base
version of a ``.shipwright/planning/*/spec.md`` against HEAD:

* its Name/Description cells changed (or it is a newly added row), OR
* its acceptance-criteria digest changed (the FOLD pattern `fr-authoring.md`
  §3 recommends — appending a criterion to an existing, description-unchanged
  row — must not escape this gate just because the row text itself did not
  move).

Both comparisons reuse existing per-FR parsing (``fr_table_reader.read_fr_rows``
for the row cells; ``lib.fr_criteria``'s anchor/pooling primitives, at
whole-document scope, for the criteria digest — see
``_whole_doc_criteria_digests`` for why this gate does not reuse
``_layer_coverage_ac.criteria_digests``'s region-restricted version even
though it is otherwise the same pooling; ``_layer_coverage_ac.spec_text_at``
for reading either side from git) rather than diffing raw text hunks: a table
row is one physical line, and `/shipwright-adopt`'s ``spec_document.py``
renders the WHOLE document from one f-string, so a naive hunk-diff would mark
every row touched on any regeneration. A per-parsed-row digest comparison is
immune to reflow and regeneration.

**Row identity is the FR id, and only the FR id** (external review,
iterate-mode leg) — INCLUDING across a `spec.md` FILE move, not only within
one file's own history (doubt review, high: the first cut of this gate
compared each touched path against its OWN base text only, so a row moved to
a different split — `fr-authoring.md` §4's own prescribed remedy for "filed
in the wrong split" — had no base-side counterpart at its new path and was
judged in full on content it never touched). `global_base_rows` below is the
fix: every touched path's base rows are pooled into one id-keyed map, so a
row's true prior content is found regardless of which touched path it lived
in at base. An id whose Name changed alongside an id rename is still not this
gate's concern — `fr_hygiene_detectors` judges what the id's OWN cells say at
base vs HEAD, and an id that changes IS a new id from this gate's point of
view (no `base_row` anywhere in the touched set to compare against, so it is
judged in full — the safe direction for an identity change nothing here can
distinguish from a genuinely new row).

**Non-dodgeable, at every complexity** — modelled on
:func:`~.integration_coverage.check_integration_coverage`, not on
:func:`~.layer_coverage.check_cross_layer_coverage` (which is a deliberate
medium+ COST decision about regenerating manifests with execution evidence;
this gate does neither, so it carries no such cost and no such floor). Fails
CLOSED on any git infrastructure gap — only a genuine non-git context stands it
down.

Global Group I advisory status is UNCHANGED by this gate. This is additive and
narrower: it holds this run to the letter of `fr-authoring.md` only for rows
this run itself chose to write or edit.
"""

from __future__ import annotations

import re
from pathlib import Path

from ._fr_hygiene_touched import (
    _new_duplicate_id_findings,
    _new_reject_findings,
    _orphan_anchor_findings,
    _row_findings,
    _row_map,
    _touched_ids,
)
from ._layer_coverage_ac import spec_text_at
from .common import CheckResult, Severity
from .git_helpers import (
    _branch_base_commit,
    _run_git,
    git_context,
)

_NAME = "FR-row hygiene on touched rows (fr-authoring.md I1/I2/I7)"

#: A `spec.md` path under any split, expressed as a pattern so it can be
#: matched against a git diff's path list instead of walking the disk.
#: `group_i_rows.scan_specs` walks the same tree but explicitly excludes
#: `iterate/` (S2b pass C2: that split holds per-run iterate specs, not the FR
#: catalogue) — this pattern does not carry that exclusion, but it is a
#: distinction without a difference here: files under `iterate/` are named
#: `{date}-{slug}.md`, never literally `spec.md`, so the two walks agree on
#: every real path in practice.
_SPEC_PATH_RE = re.compile(r"^\.shipwright/planning/[^/]+/spec\.md$")


def _spec_paths_touched(changed: list[str]) -> list[str]:
    hits: set[str] = set()
    for path in changed:
        norm = path.replace("\\", "/").strip()
        if _SPEC_PATH_RE.match(norm):
            hits.add(norm)
    return sorted(hits)


def check_fr_hygiene_on_touched_rows(
    project_root: Path, run_id: str, commit_hash: str = "",
) -> CheckResult:
    """Non-dodgeable gate: an FR row this run added or edited must be clean
    against `fr-authoring.md`'s I1 (name), I2 (description) and I7 (criterion
    shape) rules. See the module docstring for what counts as "touched" and
    why this does not reach untouched legacy rows."""
    del run_id  # accepted for the F11 verifier signature; not needed here
    ctx = git_context(project_root)
    if ctx == "not_git":
        return CheckResult(_NAME, True, "skipped (not a git work tree)",
                           severity=Severity.SKIPPED.value)
    if ctx != "work_tree":
        return CheckResult(
            _NAME, False,
            "git could not answer whether this is a work tree — common causes: a "
            "wedged index.lock, a stalled filesystem, a `safe.directory` / dubious-"
            "ownership refusal, or git missing from PATH. Refusing to certify FR "
            "rows as untouched.",
        )
    commit = commit_hash
    if not commit:
        rc, out, _ = _run_git(project_root, "rev-parse", "HEAD", timeout=10.0)
        commit = out.strip() if rc == 0 else ""
    if not commit:
        return CheckResult(
            _NAME, False,
            "no commit supplied and HEAD is unresolvable — refusing to certify "
            "FR rows as untouched",
        )
    # Resolve the merge-base FIRST, and fail closed on it BEFORE asking "was
    # spec.md touched" — the two questions used to be answered by separate
    # calls (`_iterate_changed_paths` for the first, `_branch_base_commit` for
    # the second), and `_iterate_changed_paths` silently falls back to the
    # single-commit view when the merge-base can't be resolved. That fallback
    # can say "no spec.md touched" — narrowly true of the one commit it could
    # see — while the real branch range (which this gate never got to check)
    # touched one earlier. Resolving the base once, up front, means a merge-
    # base failure fails closed unconditionally instead of only when spec.md
    # happens to be in the fallback's narrower view (doubt review).
    base_sha = _branch_base_commit(project_root, commit)
    if not base_sha:
        return CheckResult(
            _NAME, False,
            "no merge-base with the default branch could be resolved — "
            "refusing to certify FR rows as untouched",
        )
    rc, head_sha, _ = _run_git(project_root, "rev-parse", commit, timeout=10.0)
    if rc == 0 and head_sha.strip() == base_sha:
        # `commit` is already contained in the trunk — base_text and head_text
        # would be IDENTICAL, so every row would look untouched. Reporting
        # that as "clean" would claim rows were judged when none were; say
        # plainly that there was no branch range to judge instead.
        return CheckResult(
            _NAME, True,
            "commit is already contained in the trunk — no branch range to "
            "judge",
            severity=Severity.SKIPPED.value,
        )
    rc, out, _ = _run_git(
        project_root, "-c", "core.quotePath=false", "diff", "--name-only",
        f"{base_sha}..{commit}", timeout=30.0,
    )
    if rc != 0:
        return CheckResult(
            _NAME, False,
            f"cannot obtain the diff for {commit[:8]} — refusing to certify "
            "FR rows as untouched",
        )
    changed = [ln.strip() for ln in out.splitlines() if ln.strip()]
    specs = _spec_paths_touched(changed)
    if not specs:
        return CheckResult(_NAME, True, "no spec.md touched")

    text_by_path: dict[str, tuple[str, str]] = {}
    for path in specs:
        base_text = spec_text_at(project_root, base_sha, path)
        head_text = spec_text_at(project_root, commit, path)
        if base_text is None or head_text is None:
            side = "base" if base_text is None else "head"
            return CheckResult(
                _NAME, False,
                f"could not read {path} at the {side} commit — refusing to "
                "certify FR rows as untouched",
            )
        text_by_path[path] = (base_text, head_text)

    # Pooled across every touched path so a row's true prior content is found
    # regardless of which spec.md it lived in at base — see the module
    # docstring's "Row identity" paragraph. Later path wins on the rare
    # pre-existing collision of the same id across two files simultaneously;
    # that is a pre-existing FR-authoring defect (I4's territory) this gate
    # does not newly create or worsen.
    global_base_rows = {}
    for base_text, _head_text in text_by_path.values():
        global_base_rows.update(_row_map(base_text))
    base_texts_list = [base_text for base_text, _ in text_by_path.values()]
    head_texts_list = [head_text for _, head_text in text_by_path.values()]

    all_findings: list[str] = []
    # Pooled across every touched path, not per file (Tier-3 PR review, PR
    # #679): FR ids are catalog-wide, so a NEW duplicate split across two
    # touched spec.md files — one occurrence added to each — has exactly one
    # occurrence per file and is invisible to a per-file count.
    for finding in _new_duplicate_id_findings(base_texts_list, head_texts_list):
        all_findings.append(f"{', '.join(specs)}: {finding}")
    for path in specs:
        base_text, head_text = text_by_path[path]
        base_rejects: list = []
        head_rejects: list = []
        base_rows = _row_map(base_text, base_rejects)
        head_rows = _row_map(head_text, head_rejects)
        for reject_finding in _new_reject_findings(base_rejects, head_rejects):
            all_findings.append(f"{path}: {reject_finding}")
        for finding in _orphan_anchor_findings(base_text, head_text):
            all_findings.append(f"{path}: {finding}")
        for fr_id in sorted(_touched_ids(base_text, head_text)):
            row = head_rows.get(fr_id)
            if row is None:
                continue
            base_row = base_rows.get(fr_id) or global_base_rows.get(fr_id)
            hits = _row_findings(base_row, row, base_texts_list, head_text)
            if hits:
                all_findings.append(f"{fr_id} ({path}): {'; '.join(hits)}")

    if all_findings:
        shown = all_findings[:5]
        suffix = f" (+{len(all_findings) - 5} more)" if len(all_findings) > 5 else ""
        return CheckResult(
            _NAME, False,
            f"{len(all_findings)} touched FR row(s) violate fr-authoring.md: "
            + "; ".join(shown) + suffix
            + "  →  reword the row(s) in plain business language, or write the "
            "criterion as `- (E) Given ... when ... then ...` — see "
            "shared/fr-authoring.md",
        )
    return CheckResult(_NAME, True, f"{len(specs)} spec(s) touched, all edited FR row(s) clean")


__all__ = ["check_fr_hygiene_on_touched_rows"]
