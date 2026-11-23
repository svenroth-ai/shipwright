"""The upgrade-notes check of ``references/release-workflow.md``, done in code (second pass A3).

A release must tell an existing project what, if anything, it has to do. The code lists the pages under
``docs/migrations/`` added or changed since the previous tag (every page when there is no tag), reads each page's
"Do you have to do anything?" answer, and files a drop under ``CHANGELOG-unreleased.d/Changed/`` (through
``write_changelog_drop.py``) for every page whose answer is not a plain "no". The model only reviews such a drop
(and names a companion release's minimum version where the page asks for it). When no page changed, or none
needs an action, the code returns the sentence the preview or summary then repeats. Idempotent: a page that already
has its drop, or a version whose section is already in ``CHANGELOG.md`` (an interrupted release, re-run), writes
nothing; the pages themselves are never edited.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

from .release_runner import Recorder, uv_script

PAGES_DIR = "docs/migrations"
QUESTION = "**Do you have to do anything?**"
_PLAIN_NO = re.compile(r"(?:no|nothing)(?:\s+(?:action|changes?)\s+(?:is\s+)?(?:needed|required))?\s*[.!]?", re.IGNORECASE)
_MAX_ANSWER = 400


def _pages(rec: Recorder, last_tag: str | None) -> list[str] | None:
    """Relative paths of the pages added or changed since ``last_tag``; all of them without a tag."""
    argv = (["git", "diff", "--name-only", "-z", "--relative", "--end-of-options", f"{last_tag}..HEAD", "--", PAGES_DIR] if last_tag
            else ["git", "ls-files", "-z", "--", PAGES_DIR])  # -z: a non-ASCII path is not C-quoted and silently dropped
    done = rec.run("migration-pages", argv)
    if done.exit != 0:  # an unresolvable tag is not "no page changed"
        return None
    names = [n for n in done.stdout.split("\0") if n.endswith(".md")]
    return sorted(n for n in names if (rec.cwd / n).is_file())  # a page deleted since the tag has nothing to say


def answer_of(text: str) -> str | None:
    """The page's own answer: the paragraph after the question, flattened; ``None`` when the page has no such line."""
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if QUESTION in line:
            para = [line.split(QUESTION, 1)[1].strip()]
            for follow in lines[i + 1:]:
                if not follow.strip():
                    if para[0] or len(para) > 1:
                        break
                    continue  # the answer is the paragraph after a question that stands alone
                para.append(follow.strip())
            return " ".join(p for p in para if p)
    return None


def needs_action(answer: str | None) -> bool:
    """A page without the line, or with an answer other than a plain "no", counts as action required."""
    return answer is None or _PLAIN_NO.fullmatch(re.sub(r"[*`_]", "", answer).strip()) is None


def note_for(page: str, answer: str | None) -> str:
    """The drop text: the page's own words, then the link. A page with no answer line says so instead of guessing."""
    if answer is None:
        return f"Existing projects: read {page} before upgrading; it does not say whether anything has to be done."
    own = answer if len(answer) <= _MAX_ANSWER else answer[:_MAX_ANSWER].rsplit(" ", 1)[0] + " ..."
    return f"Existing projects: {own} (see {page})"


def _run_id(page: str) -> str:
    rel = Path(page).with_suffix("").as_posix().removeprefix(PAGES_DIR + "/")  # the path, not the stem: two pages may share one
    slug = re.sub(r"[^A-Za-z0-9_-]+", "-", rel).strip("-")
    if slug == rel:
        return f"upgrade-notes-{slug}"
    return f"upgrade-notes-{slug}-{hashlib.sha256(rel.encode('utf-8')).hexdigest()[:8]}"  # x/y and x-y flatten alike: a lossy name gets the path's hash


def _has_drop(project_root: Path, run_id: str) -> bool:
    drops = (project_root / "CHANGELOG-unreleased.d" / "Changed")
    return drops.is_dir() and any(re.fullmatch(rf"{re.escape(run_id)}_\d{{3}}\.md", p.name) for p in drops.iterdir())


def released(project_root: Path, version: str) -> bool:
    try:
        text = (project_root / "CHANGELOG.md").read_text(encoding="utf-8")
    except OSError:
        return False
    return re.search(rf"^## \[{re.escape(version)}\]", text, re.MULTILINE) is not None


def _drop(rec: Recorder, shared_root: Path, run_id: str, note: str) -> str:
    if _has_drop(rec.cwd, run_id):
        return "exists"
    done = rec.run("upgrade-note-drop", uv_script(
        shared_root / "scripts/tools/write_changelog_drop.py", "--project-root", str(rec.cwd), "--run-id", run_id,
        "--category", "Changed", "--bullet", note))
    return "written" if done.exit == 0 else "failed"


def write_pending(rec: Recorder, shared_root: Path, pending: list[dict[str, str]]) -> list[str]:
    """The drops ``check(write=False)`` held back, written at aggregate time (after every question is answered)."""
    return [_drop(rec, shared_root, p["run_id"], p["note"]) for p in pending]


def check(rec: Recorder, shared_root: Path, last_tag: str | None, version: str, *, write: bool = True) -> dict[str, Any]:
    """``write=False``: nothing is written (a question that can still end the release is open); the drops are returned
    as ``pending`` and ``write_pending`` files them at aggregate time."""
    root, pages, results = rec.cwd, _pages(rec, last_tag), []
    if pages is None:
        return {"status": "query_failed", "pages": [], "pending": [], "sentence": "The migration pages could not be listed: stop and report it."}
    for page in pages:
        answer = answer_of((root / page).read_text(encoding="utf-8", errors="replace"))
        results.append({"page": page, "answer": answer, "action": needs_action(answer), "drop": None})
    actions = [r for r in results if r["action"]]
    pending: list[dict[str, str]] = []
    if released(root, version):  # the section is already rendered: a new drop would disagree with it on the re-run
        status = "skipped_release_written" if actions else "no_action" if pages else "none_changed"
    elif not write:
        pending = [{"run_id": _run_id(r["page"]), "note": note_for(r["page"], r["answer"])} for r in actions]
        for r in actions:
            r["drop"] = "deferred"
        status = "action_drop_deferred" if actions else "no_action" if pages else "none_changed"
    else:
        written = 0
        for r in actions:
            r["drop"] = _drop(rec, shared_root, _run_id(r["page"]), note_for(r["page"], r["answer"]))
            written += r["drop"] == "written"
        status = ("action_drop_failed" if any(r["drop"] == "failed" for r in actions) else
                  "action_drop_written" if written else "action_drop_exists" if actions else "no_action" if pages else "none_changed")
    since = f"since {last_tag}" if last_tag else "in this repository"
    sentence = (f"No migration page changed {since}: no upgrade note added." if not pages else
                f"{len(actions)} migration page(s) {since} need an action; the release section is already written, no new drop was made." if status == "skipped_release_written" else
                f"{len(pages)} migration page(s) changed {since}; none needs an action: no upgrade note added." if not actions else
                f"{len(actions)} migration page(s) {since} need an action: the upgrade note(s) are filed when the changelog section is written (`aggregate`)." if status == "action_drop_deferred" else
                f"{len(actions)} migration page(s) {since} need an action: review the upgrade-note drop(s) before the release.")
    return {"status": status, "pages": results, "pending": pending, "sentence": sentence}
