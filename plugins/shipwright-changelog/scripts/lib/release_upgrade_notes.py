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
    argv = (["git", "diff", "--name-only", "--relative", "--end-of-options", f"{last_tag}..HEAD", "--", PAGES_DIR] if last_tag
            else ["git", "ls-files", "--", PAGES_DIR])
    done = rec.run("migration-pages", argv)
    if done.exit != 0:  # an unresolvable tag is not "no page changed"
        return None
    names = [ln.strip() for ln in done.stdout.splitlines() if ln.strip().endswith(".md")]
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
    return "upgrade-notes-" + re.sub(r"[^A-Za-z0-9_-]+", "-", rel).strip("-")


def _has_drop(project_root: Path, run_id: str) -> bool:
    return any((project_root / "CHANGELOG-unreleased.d" / "Changed").glob(f"{run_id}_*.md"))


def released(project_root: Path, version: str) -> bool:
    try:
        text = (project_root / "CHANGELOG.md").read_text(encoding="utf-8")
    except OSError:
        return False
    return re.search(rf"^## \[{re.escape(version)}\]", text, re.MULTILINE) is not None


def check(rec: Recorder, shared_root: Path, last_tag: str | None, version: str) -> dict[str, Any]:
    root, pages, results = rec.cwd, _pages(rec, last_tag), []
    if pages is None:
        return {"status": "query_failed", "pages": [], "sentence": "The migration pages could not be listed: stop and report it."}
    for page in pages:
        answer = answer_of((root / page).read_text(encoding="utf-8", errors="replace"))
        results.append({"page": page, "answer": answer, "action": needs_action(answer), "drop": None})
    actions = [r for r in results if r["action"]]
    if released(root, version):  # the section is already rendered: a new drop would disagree with it on the re-run
        status = "skipped_release_written" if actions else "no_action" if pages else "none_changed"
    else:
        written = 0
        for r in actions:
            run_id = _run_id(r["page"])
            if _has_drop(root, run_id):
                r["drop"] = "exists"
                continue
            done = rec.run("upgrade-note-drop", uv_script(
                shared_root / "scripts/tools/write_changelog_drop.py", "--project-root", str(root), "--run-id", run_id,
                "--category", "Changed", "--bullet", note_for(r["page"], r["answer"])))
            r["drop"] = "written" if done.exit == 0 else "failed"
            written += done.exit == 0
        status = ("action_drop_failed" if any(r["drop"] == "failed" for r in actions) else
                  "action_drop_written" if written else "action_drop_exists" if actions else "no_action" if pages else "none_changed")
    since = f"since {last_tag}" if last_tag else "in this repository"
    sentence = (f"No migration page changed {since}: no upgrade note added." if not pages else
                f"{len(pages)} migration page(s) changed {since}; none needs an action: no upgrade note added." if not actions else
                f"{len(actions)} migration page(s) {since} need an action: review the upgrade-note drop(s) before the release.")
    return {"status": status, "pages": results, "sentence": sentence}
