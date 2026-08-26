#!/usr/bin/env python3
"""Orchestrate the four release-notes stages behind ONE call.

Extract -> condense -> validate/sanitize -> publish, each stage a distinct,
never-swallowed reported status. Written as one Python orchestrator (rather
than a bash chain of four separate CLI invocations) so a mid-chain failure
always reaches the final status line instead of risking a `set -e` abort
before it — every stage below is wrapped, nothing here can raise past
`main()`.

Called from `/shipwright-changelog` Step 7, after the release tag has been
pushed. Best-effort throughout (Iterate Spec AC): this never signals a
process failure the calling skill would treat as blocking — the tag is the
source of truth, the release page is a best-effort convenience on top of it.

CLI:

    uv run shared/scripts/tools/publish_release_notes.py \\
        --project-root . --version 1.2.3

Output JSON: ``{"status": "ok"|"exists"|"skipped"|"failed", "reason": "...",
"url": "..."}`` — ``reason`` is prefixed per stage
(``extract_failed:...`` / ``condensation_failed:...`` /
``notes_failed_validation:...`` / the create-stage's own reasons verbatim).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_SCRIPTS_ROOT = Path(__file__).resolve().parent.parent
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from repo_identity import resolve_repo_identity  # noqa: E402
from tools import condense_release_notes as crn  # noqa: E402
from tools import create_github_release as cgr  # noqa: E402
from tools import extract_changelog_section as ecs  # noqa: E402
from tools import validate_release_notes as vrn  # noqa: E402

_PROMPT_PATH = (
    Path(__file__).resolve().parents[3]
    / "plugins" / "shipwright-changelog" / "skills" / "changelog"
    / "references" / "release-notes-prompt.md"
)


def _changelog_blob_url(repo_identity: str, version: str) -> str:
    # Links to the file AS IT WAS AT THE TAG, not a computed heading-anchor
    # slug — GitHub's slugification isn't worth re-implementing here, and a
    # slightly-longer-to-scroll-to but always-correct link beats a short one
    # that can silently 404 on a slug mismatch.
    return f"https://github.com/{repo_identity}/blob/v{version}/CHANGELOG.md"


def _compare_url(repo_identity: str, previous_tag: str, version: str) -> str:
    return f"https://github.com/{repo_identity}/compare/{previous_tag}...v{version}"


def publish(project_root: Path, version: str) -> dict:
    try:
        extracted = ecs.extract(project_root, version)
    except ecs.ExtractError as exc:
        return {"status": "skipped", "reason": f"extract_failed:{exc}"}

    if not _PROMPT_PATH.is_file():
        return {"status": "skipped", "reason": f"condensation_failed:prompt file missing at {_PROMPT_PATH}"}
    try:
        prompt_template = _PROMPT_PATH.read_text(encoding="utf-8")
    except OSError as exc:
        return {"status": "skipped", "reason": f"condensation_failed:prompt file unreadable:{exc}"}

    condensed = crn.condense(
        extracted["section_text"], version, prompt_template, project_root=project_root
    )
    if condensed.get("status") != "ok":
        return {"status": "skipped", "reason": f"condensation_failed:{condensed.get('reason')}"}

    repo_identity = resolve_repo_identity(project_root)
    if not repo_identity:
        return {"status": "skipped", "reason": "condensation_failed:repo_identity_unresolved"}

    changelog_url = _changelog_blob_url(repo_identity, version)
    previous_tag = extracted.get("previous_version_tag")
    compare_url = _compare_url(repo_identity, previous_tag, version) if previous_tag else None
    footer = vrn.expected_footer(version, changelog_url, compare_url)

    result = vrn.validate(
        condensed["text"], version, footer=footer, repo_identity=repo_identity
    )
    if not result.ok:
        return {"status": "skipped", "reason": f"notes_failed_validation:{result.reason}"}

    notes_path = project_root / ".shipwright" / "runtime" / f"release_notes_v{version}.md"
    try:
        notes_path.parent.mkdir(parents=True, exist_ok=True)
        with notes_path.open("w", encoding="utf-8", newline="\n") as fh:
            fh.write(result.sanitized_body)
    except OSError as exc:
        return {"status": "failed", "reason": f"notes_write_failed:{exc}"}

    return cgr.create_release(version, notes_path, project_root)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    parser.add_argument("--project-root", default=".")
    parser.add_argument("--version", required=True, help="e.g. 1.2.3 (no leading 'v')")
    args = parser.parse_args(argv)

    result = publish(Path(args.project_root).resolve(), args.version)
    print(json.dumps(result, indent=2))
    return 0  # non-fatal by contract — the caller reads "status"


if __name__ == "__main__":
    sys.exit(main())
