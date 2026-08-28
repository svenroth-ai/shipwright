#!/usr/bin/env python3
"""Extract one version's section from the TAGGED ``CHANGELOG.md`` blob.

Reads ``git show v{version}:CHANGELOG.md`` — the byte-exact content that was
released, not the worktree file — so this never races the worktree (Step 7
runs after Step 6's commit+tag, alongside other writers) and never needs the
``CHANGELOG.md.lock`` every other reader/writer of that file takes. Fails
loudly (never silently) if the tag doesn't exist yet.

Section slicing reuses ``changelog_sections.section_starts``/``section_end`` —
the same SSoT the aggregator and the plugin-side writer share — so this
reader can never disagree with them about where a section ends.

Previous-version resolution (for the release body's compare link) is
semver-aware and REMOTE-verified: a local tag alone proves nothing about
what's actually on GitHub (a locally-present, never-pushed tag would produce
a compare link that 404s), so each candidate is checked with
``git ls-remote --tags origin`` before being accepted. On no resolvable
predecessor, ``previous_version_tag`` is ``null`` — never fabricated.

CLI:

    uv run shared/scripts/tools/extract_changelog_section.py \\
        --project-root . --version 1.2.3

Output JSON: ``{"status": "ok", "version": "1.2.3", "section_text": "...",
"previous_version_tag": "v1.2.2" | null}`` or
``{"status": "error", "reason": "..."}``.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

_SCRIPTS_ROOT = Path(__file__).resolve().parent.parent
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from changelog_sections import section_end, section_starts  # noqa: E402

# Matches the aggregator's own drop-file bound so nothing silently truncates
# into the condensation prompt — a refusal is loud, a truncation is not.
MAX_SECTION_BYTES = 64 * 1024

_SEMVER_TAG_RE = re.compile(r"^v(\d+)\.(\d+)\.(\d+)$")


class ExtractError(RuntimeError):
    """Raised for every refusal path — the CLI turns this into a JSON error."""


def _git(args: list[str], project_root: Path, *, timeout: float = 15.0) -> str:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=str(project_root),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ExtractError(f"git {' '.join(args)} failed to run: {exc}") from exc
    if result.returncode != 0:
        raise ExtractError(
            f"git {' '.join(args)} exited {result.returncode}: {result.stderr.strip()}"
        )
    return result.stdout


def _read_tagged_changelog(project_root: Path, version: str) -> str:
    tag = f"v{version}"
    try:
        return _git(["show", f"{tag}:CHANGELOG.md"], project_root)
    except ExtractError as exc:
        raise ExtractError(
            f"could not read CHANGELOG.md from tag {tag} — is it pushed? ({exc})"
        ) from exc


def _extract_section(text: str, version: str) -> str:
    # MAX_SECTION_BYTES bounds only the SLICED section below, never the whole
    # file: a mature CHANGELOG.md accumulates every past release and easily
    # exceeds this bound in total (this repo's own is 450KB+) while any one
    # release's own section stays small — bounding the whole file would
    # permanently refuse every future release once the file crosses the cap.
    lines = text.splitlines(keepends=True)
    starts = section_starts(lines, version)
    if len(starts) == 0:
        raise ExtractError(f"no '## [{version}]' heading found in tagged CHANGELOG.md")
    if len(starts) > 1:
        raise ExtractError(
            f"ambiguous — {len(starts)} '## [{version}]' headings found in tagged CHANGELOG.md"
        )
    start = starts[0]
    end = section_end(lines, start)
    section = "".join(lines[start:end])
    if len(section.encode("utf-8")) > MAX_SECTION_BYTES:
        raise ExtractError(
            f"section for {version} exceeds {MAX_SECTION_BYTES} bytes — refusing to condense"
        )
    return section


def _candidate_previous_tags(project_root: Path, version: str) -> list[str]:
    """Semver-sorted (descending) local tags strictly below ``version``."""
    output = _git(["tag", "--list", "v*"], project_root)
    parsed: list[tuple[tuple[int, int, int], str]] = []
    for line in output.splitlines():
        tag = line.strip()
        match = _SEMVER_TAG_RE.match(tag)
        if not match:
            continue  # non-semver noise (e.g. "v-next") is ignored, not guessed at
        parsed.append(((int(match[1]), int(match[2]), int(match[3])), tag))

    version_match = _SEMVER_TAG_RE.match(f"v{version}")
    current_key = (
        (int(version_match[1]), int(version_match[2]), int(version_match[3]))
        if version_match
        else None
    )
    parsed.sort(key=lambda item: item[0], reverse=True)
    return [tag for key, tag in parsed if current_key is None or key < current_key]


def _remote_has_tag(project_root: Path, tag: str) -> bool:
    try:
        output = _git(["ls-remote", "--tags", "origin", f"refs/tags/{tag}"], project_root)
    except ExtractError:
        return False
    return bool(output.strip())


def _resolve_previous_version_tag(project_root: Path, version: str) -> str | None:
    for candidate in _candidate_previous_tags(project_root, version):
        if _remote_has_tag(project_root, candidate):
            return candidate
    return None


def extract(project_root: Path, version: str) -> dict:
    changelog_text = _read_tagged_changelog(project_root, version)
    section_text = _extract_section(changelog_text, version)
    previous_version_tag = _resolve_previous_version_tag(project_root, version)
    return {
        "status": "ok",
        "version": version,
        "section_text": section_text,
        "previous_version_tag": previous_version_tag,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    parser.add_argument("--project-root", default=".")
    parser.add_argument("--version", required=True, help="e.g. 1.2.3 (no leading 'v')")
    args = parser.parse_args(argv)

    try:
        result = extract(Path(args.project_root).resolve(), args.version)
    except ExtractError as exc:
        print(json.dumps({"status": "error", "reason": str(exc)}, indent=2))
        return 1

    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
