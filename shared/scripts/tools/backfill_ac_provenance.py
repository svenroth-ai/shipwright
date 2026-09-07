#!/usr/bin/env python3
"""Derive AC-scoped ``@pytest.mark.covers`` upgrades from criterion provenance
footnotes joined against the introducing commit's ``Run-ID:`` trailer (P3.4,
campaign ``req3-04c-ac-identity-wave2`` — the mechanical leg; see
``lib.backfill_ac_provenance`` for the join logic and why it is conservative).
The WRITE half (``apply_upgrades`` / ``validate_applied``) lives in
``_backfill_ac_provenance_apply.py`` — split out at the 300-LOC bloat cap.

Deterministic, auditable, and conservative by construction:

* only a footnote slug naming EXACTLY ONE ``(fr_id, ac_id)`` pair across the
  WHOLE document is used (``lib.backfill_ac_provenance.unique_provenance_acs``
  — never a guess between two candidates; the uniqueness check is document-wide,
  not per-FR, because a single commit can deliver criteria spanning multiple FRs);
* only a slug with EXACTLY ONE commit carrying ``Run-ID: <slug>`` is used —
  zero or more than one is reported, never guessed;
* only a test file the commit **added** (git status ``A``, never ``M``) is a
  candidate — a file the commit only modified is very often a pre-existing,
  multi-purpose fixture shared across many unrelated tests (measured: most
  files a real qualifying commit touches are exactly this), and tagging every
  test in it for one commit's criterion would be exactly the guess this tool
  exists not to make. A wholesale new file is the one shape where "every test
  in it" is safely the commit's own stated scope;
* a test file claimed by more than one distinct ``(fr_id, ac_id)`` — two
  different provenance chains landing on the same path — is a conflict and is
  excluded from BOTH, never arbitrarily resolved;
* within an eligible file, an ALREADY bare-tagged
  ``@pytest.mark.covers("<fr_id>")`` for the SAME fr_id is upgraded to name the
  AC, and a test with NO ``covers`` tag at all gets a brand-new AC-scoped one.
  A test that already carries some OTHER tag is left alone (never guessed
  which one wins);
* every non-``candidate`` outcome is counted in ``status_counts`` (external
  plan review, P3.4, glm low) — a conflict or an unresolved slug is a number a
  reviewer can ask for, never silently folded into "nothing happened";
* refuses outright on a shallow clone (external plan review, P3.4, openai
  medium) — a truncated ``git log`` can silently UNDER-report yield, and this
  tool would rather refuse loudly than report a quietly smaller number as if
  it were complete;
* ``--write`` re-validates every tag it just wrote against a FRESH read of the
  spec.md (external plan review, P3.4, glm medium) — derive-time and apply-time
  agreeing is checked, never assumed.

Default is a DRY RUN (report only, nothing written). ``--write`` applies:
an existing bare ``covers("FR-XX.YY")`` becomes ``covers("FR-XX.YY/ACnn")``
(a widened decorator argument, same idiom ``fr_tag_grammar`` already reads);
an untagged test gets a brand-new ``@pytest.mark.covers("FR-XX.YY/ACnn")``
decorator inserted the same way ``backfill_write.apply_writes`` already does
for the FR-level engine (reused here, not reimplemented).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

_LIB = Path(__file__).resolve().parents[1] / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from ac_identity import read_all  # noqa: E402
from backfill_ac_provenance import unique_provenance_acs  # noqa: E402

_TOOLS = Path(__file__).resolve().parent
if str(_TOOLS) not in sys.path:
    sys.path.insert(0, str(_TOOLS))

from _backfill_ac_provenance_apply import apply_upgrades, validate_applied  # noqa: E402
from verifiers.git_helpers import _run_git  # noqa: E402

_DEFAULT_SPEC = Path(".shipwright/planning") / "01-adopted" / "spec.md"


def _commit_has_own_run_id_line(project_root: Path, commit: str, slug: str) -> bool:
    """True only if ``commit``'s OWN message carries a LINE that IS exactly
    ``Run-ID: <slug>`` (external code review, P3.4, glm medium) -- git's
    native trailer parser (``%(trailers:key=...)``) was tried first and
    rejected: on this repo's own real commits the ``Run-ID:`` line sits in a
    paragraph separated by a blank line from a trailing ``Co-authored-by:``
    line, so git's "last paragraph must be all-trailers" heuristic does not
    recognise it as a trailer at all -- silently under-reporting every real
    match, which is worse than the substring risk this check exists to close.
    A plain per-line regex anchored on the WHOLE line (never a substring
    inside prose, and never matched merely because this slug is a PREFIX of
    another commit's longer slug) is exact here without that fragility."""
    rc, body, _ = _run_git(project_root, "log", "-1", "--format=%B", commit)
    if rc != 0:
        return False
    pattern = re.compile(r"^Run-ID:\s*" + re.escape(slug) + r"\s*$", re.MULTILINE)
    return bool(pattern.search(body))


def _commits_for_run_id(project_root: Path, slug: str) -> list[str]:
    """Every commit (any ref) whose OWN message carries an exact ``Run-ID:
    <slug>`` line, newest first. The ``-F`` (fixed-string) ``--grep`` below is
    a cheap OVER-approximation only -- it would also match a slug that is a
    PREFIX of a longer one, or prose in some OTHER commit that merely mentions
    this Run-ID -- so every candidate is re-checked against its own message
    with an exact, whole-line match before being trusted."""
    rc, out, _ = _run_git(
        project_root, "log", "--all", "--format=%H", "-F",
        f"--grep=Run-ID: {slug}",
    )
    if rc != 0:
        return []
    candidates = [ln.strip() for ln in out.splitlines() if ln.strip()]
    return [c for c in candidates if _commit_has_own_run_id_line(project_root, c, slug)]


def _is_under_a_tests_dir(rel: str) -> bool:
    """True when some DIRECTORY component of ``rel`` (never the filename
    itself) is literally ``tests`` — external code review (P3.4, glm low): a
    plain ``"/tests/" in rel`` substring check MISSES a top-level layout like
    ``tests/test_new.py`` (no leading slash before ``tests``), which this
    tool's own ``git status -A`` filter would otherwise silently drop."""
    posix = rel.replace("\\", "/")
    return "tests" in posix.split("/")[:-1]


def _added_test_files(project_root: Path, commit: str) -> list[str] | None:
    """Test files this commit ADDED (git status ``A`` only, never ``M``/``R``/``D``) —
    ``None`` on a git failure, distinguished from ``[]`` (ran fine, added nothing
    test-shaped) the same way ``git_helpers`` distinguishes "could not see" from
    "genuinely empty". ``--no-renames``: a rename would otherwise read as an ``A``
    that is really an edit of a pre-existing (and possibly shared) file — the exact
    risk this whole gate exists to exclude. ``-c core.quotePath=off``: a path with
    non-ASCII or special characters would otherwise come back C-quoted (e.g.
    ``"a/b\\303\\251.py"``) and never match a real repo-relative path (external
    code review, P3.4, glm low)."""
    rc, out, _ = _run_git(
        project_root, "-c", "core.quotePath=off", "show", "--no-renames",
        "--name-status", "--pretty=format:", commit,
    )
    if rc != 0:
        return None
    added: list[str] = []
    for line in out.splitlines():
        parts = line.split("\t", 1)
        if len(parts) == 2 and parts[0].strip() == "A":
            rel = parts[1].strip()
            if rel.endswith(".py") and _is_under_a_tests_dir(rel):
                added.append(rel)
    return added


def derive(project_root: Path, spec_path: Path | None = None) -> dict:
    """The candidate report — pure read, no writes."""
    spec_path = spec_path or (project_root / _DEFAULT_SPEC)
    content = spec_path.read_text(encoding="utf-8")
    uniq = unique_provenance_acs(read_all(content))
    candidates: list[dict] = []
    for fr_id in sorted(uniq):
        for slug, ac_id in sorted(uniq[fr_id].items()):
            commits = _commits_for_run_id(project_root, slug)
            entry = {"fr_id": fr_id, "ac_id": ac_id, "slug": slug}
            if len(commits) != 1:
                entry["status"] = "no_commit_found" if not commits else "ambiguous_commit_count"
                entry["commit_count"] = len(commits)
                candidates.append(entry)
                continue
            commit = commits[0]
            entry["commit"] = commit
            test_paths = _added_test_files(project_root, commit)
            if test_paths is None:
                entry["status"] = "git_error"
                candidates.append(entry)
                continue
            if not test_paths:
                entry["status"] = "no_added_test_file_in_commit"
                candidates.append(entry)
                continue
            entry["status"] = "candidate"
            entry["test_files"] = test_paths
            candidates.append(entry)
    _mark_multiply_claimed_files(candidates)
    status_counts: dict[str, int] = {}
    for cand in candidates:
        status_counts[cand["status"]] = status_counts.get(cand["status"], 0) + 1
    return {
        "fr_ids_with_unique_footnote": len(uniq),
        "candidates": candidates,
        "candidate_count": status_counts.get("candidate", 0),
        # Every non-candidate bucket, by name — external plan review (P3.4):
        # "for a backfill whose credibility rests on derived vs hand-mapped
        # stated, never blended, the silently-dropped bucket is the third
        # number a reviewer will ask for." Never silently absorbed into the
        # candidate count.
        "status_counts": status_counts,
    }


def _mark_multiply_claimed_files(candidates: list[dict]) -> None:
    """A test path claimed by more than one distinct ``(fr_id, ac_id)`` is a
    conflict — two independent provenance chains landing on the same added
    file is evidence the file is not as single-purpose as "added by one
    commit" assumed. Demotes every affected candidate's status in place and
    drops the shared path from its ``test_files`` list, so an unrelated file
    the SAME candidate also added is unaffected."""
    owners: dict[str, set[tuple[str, str]]] = {}
    for cand in candidates:
        if cand["status"] != "candidate":
            continue
        token = (cand["fr_id"], cand["ac_id"])
        for rel in cand["test_files"]:
            owners.setdefault(rel, set()).add(token)
    conflicted = {rel for rel, toks in owners.items() if len(toks) > 1}
    if not conflicted:
        return
    for cand in candidates:
        if cand["status"] != "candidate":
            continue
        kept = [rel for rel in cand["test_files"] if rel not in conflicted]
        dropped = [rel for rel in cand["test_files"] if rel in conflicted]
        if dropped:
            cand["conflicted_test_files"] = dropped
        cand["test_files"] = kept
        if not kept:
            cand["status"] = "all_test_files_conflicted"


def _is_shallow_clone(project_root: Path) -> bool:
    """External plan review (P3.4, openai medium): a shallow clone's git log
    is truncated, so ``_commits_for_run_id`` could silently miss the ONE
    commit that carries a slug's Run-ID and report ``no_commit_found`` for a
    real, provable case — a reduced-yield failure mode, not a wrong-answer
    one, but worth refusing loudly rather than reporting a quietly smaller
    number."""
    rc, out, _ = _run_git(project_root, "rev-parse", "--is-shallow-repository")
    return rc == 0 and out.strip() == "true"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--spec-file", help="Override the default 01-adopted/spec.md")
    parser.add_argument("--write", action="store_true", help="Apply the upgrades (default: dry run)")
    args = parser.parse_args(argv)

    project_root = Path(args.project_root).resolve()
    spec_path = Path(args.spec_file).resolve() if args.spec_file else (project_root / _DEFAULT_SPEC)
    if _is_shallow_clone(project_root):
        print(json.dumps({
            "success": False,
            "error": "shallow_clone: git history is truncated here, so a real "
                     "Run-ID commit could be invisible to `git log --grep` and "
                     "under-report yield rather than over-report it — unshallow "
                     "the clone (`git fetch --unshallow`) before running this tool",
        }, indent=2))
        return 1
    report = derive(project_root, spec_path)
    out: dict = {"derive": report}
    if args.write:
        # Snapshot every candidate file BEFORE writing (external plan review,
        # P3.4, glm low / external code review, P3.4, openai medium): if the
        # post-write validation below finds an orphan tag, every file this run
        # touched is restored byte-for-byte rather than leaving a half-applied
        # tree behind a non-zero exit.
        originals: dict[Path, bytes] = {}
        for cand in report["candidates"]:
            if cand.get("status") != "candidate":
                continue
            for rel in cand.get("test_files", []):
                abs_path = project_root / rel
                if abs_path.is_file():
                    originals[abs_path] = abs_path.read_bytes()
        apply_result = apply_upgrades(project_root, report)
        out["apply"] = apply_result
        orphans = validate_applied(project_root, apply_result, spec_path)
        if orphans:
            for abs_path, content in originals.items():
                abs_path.write_bytes(content)
            out["apply"]["orphan_tags_written"] = orphans
            out["apply"]["rolled_back"] = True
            print(json.dumps(out, indent=2, ensure_ascii=False))
            return 1
    print(json.dumps(out, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
