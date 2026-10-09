"""F11 claim gate: every test an iterate adds or changes names the requirement it proves.

Before this gate the only tagging rule was reactive (the AC ratchet fires for a newly
minted unbound criterion), so a test added under an UNCHANGED criterion always shipped
untagged. This gate closes that, diff-only and with ratchet semantics: the thousands of
legacy untagged tests are untouched; only what this diff adds or edits must be tagged.

It reuses the production machinery rather than parsing tags itself:
``_layer_coverage_regen.regenerate_base_head`` regenerates the base (merge-base) and
head manifests through the compliance plugin's ``test_links`` collector — the parser
that binds multi-line Playwright declarations, ``describe``-level tags and class-level
pytest marks — and memoises both evidence-free manifests, so the removal gate and this
one share a single regeneration per run. ``_keystone_base_manifest.require_manifest_shape``
validates both sides fail-closed. The verdict is :mod:`._tag_binding_core`.

Hard STOP at every complexity. Every infra gap — not a git work tree, no ``--commit``, no
merge-base, the collector cannot load, a manifest is malformed, the diff cannot be listed,
a file cannot be read — is a FAILURE with a remediation, never a SKIP (in particular never
the lazy-loader SKIP: a collector that does not load STOPs here). A non-git directory is no
exception: it has no diff to judge, and an unobtainable diff STOPs. (The regenerating sibling
gates — removal, integration coverage, CI supply chain — still SKIP there; this one does not.)

Exemptions are per test, read from the F5c entry's ``exemptions`` block
(``lib.exemption_record``). The FRs the run's ``work_completed`` event names
(``affected_frs`` + ``new_frs``) are the expected tag set; a new tag outside it WARNs, and
no such event at all WARNs that the out-of-scope check did not run.
"""

from __future__ import annotations

import sys
from pathlib import Path

_SCRIPTS_ROOT = Path(__file__).resolve().parents[2]
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from lib.exemption_record import entry_exemptions_error  # noqa: E402
from lib.iterate_entry import find_entry_by_run_id  # noqa: E402

from ._keystone_base_manifest import ReadError, require_manifest_shape  # noqa: E402
from ._layer_coverage_ac import spec_text_at  # noqa: E402
from ._layer_coverage_regen import _merge_base, regenerate_base_head  # noqa: E402
from ._tag_binding_core import TagVerdict, evaluate  # noqa: E402
from .common import CheckResult, Severity, read_events_jsonl  # noqa: E402
from .git_helpers import _run_git, git_context  # noqa: E402

CHECK_NAME = "test tag binding (added/changed tests name their requirement)"
_HOW = (
    "tag each test with the requirement it proves - pytest `@pytest.mark.covers(\"FR-XX.YY/ACnn\")` "
    "(on the function or its class), TS/JS `{ tag: ['@FR-XX.YY'] }` or `// @covers FR-XX.YY` - "
    "or record a per-test exemption in the F5c entry (references/F5c.md, `exemptions`)"
)
_MAX_LISTED = 12

__all__ = ["CHECK_NAME", "check_test_tag_binding"]


def _fail(detail: str) -> CheckResult:
    return CheckResult(CHECK_NAME, False, detail)


def _expected_frs(project_root: Path, run_id: str) -> set[str] | None:
    """The run's Spec-Impact FRs; ``None`` when no ``work_completed`` event names the run."""
    frs: set[str] | None = None
    for event in read_events_jsonl(project_root):
        if event.get("type") == "work_completed" and event.get("adr_id") == run_id:
            frs = frs or set()
            for key in ("affected_frs", "new_frs"):
                value = event.get(key) or []
                frs |= {str(f) for f in value} if isinstance(value, list) else set()
    return frs


def _changed_paths(project_root: Path, base_sha: str, head_sha: str) -> set[str] | None:
    """Paths as the collector writes them: unquoted (a non-ASCII name stays itself) and
    NUL-separated, so no file name can be mistaken for two or lost to quoting."""
    rc, out, _ = _run_git(project_root, "-c", "core.quotePath=false", "diff", "--no-renames",
                          "--name-only", "-z", base_sha, head_sha)
    return {p for p in out.split("\0") if p} if rc == 0 else None


def check_test_tag_binding(project_root: Path, run_id: str, commit_hash: str = "") -> CheckResult:
    project_root = Path(project_root)
    ctx = git_context(project_root)
    if ctx == "not_git":
        return _fail("cannot enforce: not a git work tree, so the diff cannot be obtained - run the "
                     "iterate inside a git work tree (its own `git worktree add` checkout) and re-run F11")
    if ctx != "work_tree":
        return _fail("cannot enforce: git could not answer whether this is a work tree - run "
                     "`git -C <project> rev-parse --is-inside-work-tree` and fix what it reports")
    if not commit_hash:
        return _fail("cannot enforce: no --commit supplied - re-run verify_iterate_finalization.py "
                     "with --commit \"$(git rev-parse HEAD)\"")
    entry = find_entry_by_run_id(project_root, run_id) or {}
    err = entry_exemptions_error(entry)
    if err:
        return _fail(f"{run_id}: the F5c entry's {err} - fix it via append_iterate_entry.py")
    try:
        regen = regenerate_base_head(project_root, commit_hash, with_evidence=False, base_prune_only=True)
        if regen is None:
            return _fail("cannot enforce: the traceability collector could not regenerate the base/head "
                         "manifests (no merge-base with the default branch, the compliance plugin's "
                         "collector did not load, or the tree could not be read) - fetch the default branch "
                         "(`git fetch origin`) and check plugins/shipwright-compliance is present")
        base, head, _renames = regen
        require_manifest_shape(base, "regenerated at base")
        require_manifest_shape(head, "regenerated at head")
        base_sha = _merge_base(project_root, commit_hash)
        changed = _changed_paths(project_root, base_sha, commit_hash) if base_sha else None
        if changed is None:
            return _fail("cannot enforce: the diff against the merge-base could not be listed - "
                         "run `git diff --name-only $(git merge-base origin/HEAD HEAD) HEAD`")
        sides = {"base": base_sha, "head": commit_hash}
        texts: dict[tuple[str, str], str | None] = {}

        def read(path: str, side: str) -> str | None:
            if (path, side) not in texts:
                texts[(path, side)] = spec_text_at(project_root, sides[side], path)
            return texts[(path, side)]

        exemptions = list((entry.get("exemptions") or {}).get("items") or [])
        verdict = evaluate(base, head, changed, read, exemptions, _expected_frs(project_root, run_id))
    except ReadError as exc:
        return _fail(f"cannot enforce: {exc}")
    except Exception as exc:  # noqa: BLE001 - an enforcing gate that crashes must read RED
        return _fail(f"cannot enforce: {type(exc).__name__}: {exc}")
    return _result(verdict)


def _result(v: TagVerdict) -> CheckResult:
    total = len(v.touched)
    share = f"{100 * len(v.exempted) / total:.0f}%" if total else "0%"
    summary = (f"{len(v.tagged_new)} newly tagged test(s), {len(v.moved)} moved; "
               f"exempted {len(v.exempted)} of {total} added/edited tests ({share})")
    if v.findings:
        listed = "; ".join(f"{test} [{kind}: {why}]" for kind, test, why in v.findings[:_MAX_LISTED])
        more = f" (+{len(v.findings) - _MAX_LISTED} more)" if len(v.findings) > _MAX_LISTED else ""
        return _fail(f"{len(v.findings)} test(s) name no requirement: {listed}{more} -> {_HOW}. {summary}")
    if v.warnings:
        return CheckResult(CHECK_NAME, False, f"{summary}; " + "; ".join(v.warnings[:_MAX_LISTED]),
                           severity=Severity.WARNING.value, strict_exempt=True)
    return CheckResult(CHECK_NAME, True, summary)
