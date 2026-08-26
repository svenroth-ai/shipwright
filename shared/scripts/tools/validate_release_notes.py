#!/usr/bin/env python3
"""Sanitize-and-validate a condensed release-notes body before publishing.

The mechanical contract gate in front of the LLM condensation step
(``condense_release_notes.py``). Judgment (what counts as "breaking" vs
"changed", how to compress a bullet) stays with the model; whether the
result is SAFE and SHAPED correctly to publish is decided here, entirely
without a model in the loop.

Returns the canonical SANITIZED body, not just a pass/fail verdict — the
caller must publish exactly the text this function returns, never the raw
input, so the neutralization below is actually what reaches the public page.

Checks (first failure wins, reason named):
- non-empty
- under a hard size cap, well below GitHub's ~125,000-char release-body limit
- every ``##`` heading is drawn from the fixed allowed vocabulary
- the version string appears in the body
- the body ends with the exact mechanically-computed footer (or, when no
  previous version was resolved, the CHANGELOG-anchor-only footer)

Then, independent of pass/fail, MECHANICAL NEUTRALIZATION is applied to
what's left before it is judged safe to publish:
- ``@mention`` and bare ``#NNN`` references are code-spanned (kills the
  live GitHub mention/cross-link, keeps the text readable)
- Markdown images, autolinks (``<https://...>``), bare ``http(s)://`` URLs,
  and raw HTML ``<a>``/``<img>`` tags are all REJECTED outright (not
  neutralized) — conservative-reject rather than partial-parse, because a
  regex-based Markdown scanner cannot safely rewrite arbitrary HTML/link
  forms
- every remaining ``[text](url)`` link must point at this repo's own
  ``github.com/<owner>/<repo>`` host (from ``repo_identity``) or be a
  relative in-page anchor — anything else fails validation
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

_SCRIPTS_ROOT = Path(__file__).resolve().parents[1]
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from repo_identity import resolve_repo_identity  # noqa: E402

# Comfortably below GitHub's ~125,000-char release-body limit — leaves
# headroom for the mechanically-appended footer and any neutralization
# that lengthens text (e.g. wrapping a mention in backticks).
MAX_RELEASE_BODY_BYTES = 60_000

ALLOWED_HEADINGS = {
    "Highlights",
    "Features",
    "Breaking Changes",
    "Changed",
    "Fixed",
    "Security",
}

_HEADING_RE = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)
# ANY ATX heading — level 1-6, 0-3 leading spaces (CommonMark/GFM both allow
# this, and GitHub's release-page renderer still renders it as a real
# heading). _check_headings scans with THIS, not _HEADING_RE, so a `#`,
# `###`+, or indented `## ` line cannot smuggle unauthorized text past the
# vocabulary/empty-section gate by simply not being an exact "##" line
# (doubt-reviewer finding — confirmed as a live bypass by hand-tracing).
_ANY_ATX_HEADING_RE = re.compile(r"^ {0,3}(#{1,6})(?:\s+(.*?))?\s*$", re.MULTILINE)
_MENTION_RE = re.compile(r"(?<![`\w])@([A-Za-z0-9][A-Za-z0-9-]{0,38})\b")
_ISSUE_REF_RE = re.compile(r"(?<![`\w#])#(\d+)\b")
_IMAGE_RE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
_AUTOLINK_RE = re.compile(r"<https?://[^>\s]+>")
_BARE_URL_RE = re.compile(r"(?<!\]\()(?<!<)\bhttps?://[^\s)>\]]+")
_HTML_TAG_RE = re.compile(r"<\s*(a|img)\b[^>]*>", re.IGNORECASE)
_LINK_RE = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
_INLINE_CODE_SPAN_RE = re.compile(r"`[^`\n]*`")
# Common emoji-bearing ranges — "no emoji" is an explicit AC (operator
# request from turn one of this feature), so it is enforced mechanically
# rather than left to the prompt alone.
_EMOJI_RE = re.compile(
    "["
    "\U0001F300-\U0001FAFF"
    "\U00002600-\U000027BF"
    "\U0001F1E6-\U0001F1FF"
    "\U0000FE0F"
    "]"
)


@dataclass
class ValidationResult:
    ok: bool
    sanitized_body: str | None
    reason: str | None


def _neutralize_mentions_and_refs(body: str) -> str:
    # Applying the substitution to the WHOLE body — including inside an
    # existing inline code span — wraps the match in fresh backticks that
    # close the surrounding span early, leaving the tail as live text (e.g.
    # "`reported by @user`" -> "`reported by `@user`" un-neutralizes @user
    # rather than neutralizing it). Skip text already inside a `code span`.
    def _substitute_outside_code_spans(text: str, pattern: re.Pattern, repl) -> str:
        pieces = []
        pos = 0
        for span in _INLINE_CODE_SPAN_RE.finditer(text):
            pieces.append(pattern.sub(repl, text[pos:span.start()]))
            pieces.append(span.group(0))
            pos = span.end()
        pieces.append(pattern.sub(repl, text[pos:]))
        return "".join(pieces)

    body = _substitute_outside_code_spans(body, _MENTION_RE, lambda m: f"`@{m.group(1)}`")
    body = _substitute_outside_code_spans(body, _ISSUE_REF_RE, lambda m: f"`#{m.group(1)}`")
    return body


def _reject_unsafe_url_forms(body: str) -> str | None:
    """Return a failure reason if the body contains a rejected URL form."""
    if _IMAGE_RE.search(body):
        return "body contains Markdown image syntax, which is rejected"
    if _AUTOLINK_RE.search(body):
        return "body contains a Markdown autolink (<https://...>), which is rejected"
    if _HTML_TAG_RE.search(body):
        return "body contains a raw HTML <a>/<img> tag, which is rejected"
    if _BARE_URL_RE.search(body):
        return "body contains a bare http(s):// URL outside [text](url) form, which is rejected"
    return None


def _check_link_hosts(body: str, repo_identity: str | None) -> str | None:
    for match in _LINK_RE.finditer(body):
        url = match.group(1).strip()
        if url.startswith("#"):
            continue  # relative in-page anchor — always allowed
        if repo_identity:
            own_repo = f"https://github.com/{repo_identity}"
            # A plain prefix check (`url.startswith(own_repo)`) also accepts
            # e.g. "acme/widgets-archive" for repo_identity "acme/widgets" —
            # require the match to end exactly there or continue at a real
            # path/query/fragment boundary (external code review finding).
            if url == own_repo or url.startswith(own_repo + "/") or url.startswith(own_repo + "?"):
                continue
        return f"link to disallowed host: {url!r}"
    return None


def _check_headings(body: str) -> str | None:
    for match in _ANY_ATX_HEADING_RE.finditer(body):
        hashes, name = match.group(1), (match.group(2) or "").strip()
        if len(hashes) != 2:
            return f"heading {match.group(0).strip()!r} is not an H2 ('## ...') — only H2 headings are allowed"
        if name not in ALLOWED_HEADINGS:
            return f"heading '## {name}' is not in the allowed vocabulary {sorted(ALLOWED_HEADINGS)}"
    return None


def _check_no_empty_sections(body: str) -> str | None:
    matches = list(_HEADING_RE.finditer(body))
    for i, match in enumerate(matches):
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        if not body[start:end].strip():
            return f"heading '## {match.group(1).strip()}' has no content — an empty section must be omitted entirely"
    return None


def _check_no_emoji(body: str) -> str | None:
    if _EMOJI_RE.search(body):
        return "body contains an emoji, which is rejected"
    return None


def expected_footer(
    version: str, changelog_anchor_url: str, compare_url: str | None
) -> str:
    # Real markdown links, never a bare URL — the bare-URL rejection below
    # applies uniformly to the whole body, footer included, so the footer
    # must obey its own rule rather than being a silent exemption.
    # The version string is embedded in the link TEXT (not just relied on
    # via a compare-link substring) so the "version present" check holds
    # even for a first-ever release, which has no compare link at all.
    lines = [f"[Full changelog for v{version}]({changelog_anchor_url})"]
    if compare_url:
        lines.append(f"[Compare with the previous release]({compare_url})")
    return "\n".join(lines)


def validate(
    body: str,
    version: str,
    *,
    footer: str,
    repo_identity: str | None,
) -> ValidationResult:
    """Validate ``body`` (WITHOUT the footer — callers append it separately
    before calling this) and return the sanitized, publish-ready text
    (body + footer)."""
    if not body or not body.strip():
        return ValidationResult(False, None, "body is empty")

    full_body = f"{body.rstrip()}\n\n{footer}\n"

    if len(full_body.encode("utf-8")) > MAX_RELEASE_BODY_BYTES:
        return ValidationResult(
            False, None, f"body exceeds {MAX_RELEASE_BODY_BYTES} bytes"
        )

    heading_reason = _check_headings(full_body)
    if heading_reason:
        return ValidationResult(False, None, heading_reason)

    # Scoped to `body`, NOT `full_body`: the footer has no `##` heading of
    # its own, so appending it first would let its non-empty link text mask
    # a genuinely empty LAST section (code-reviewer finding).
    empty_section_reason = _check_no_empty_sections(body)
    if empty_section_reason:
        return ValidationResult(False, None, empty_section_reason)

    emoji_reason = _check_no_emoji(full_body)
    if emoji_reason:
        return ValidationResult(False, None, emoji_reason)

    if version not in full_body:
        return ValidationResult(False, None, f"version string {version!r} not found in body")

    url_reason = _reject_unsafe_url_forms(full_body)
    if url_reason:
        return ValidationResult(False, None, url_reason)

    link_reason = _check_link_hosts(full_body, repo_identity)
    if link_reason:
        return ValidationResult(False, None, link_reason)

    sanitized = _neutralize_mentions_and_refs(full_body)
    return ValidationResult(True, sanitized, None)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    parser.add_argument("--body-file", required=True, help="condensed body WITHOUT the footer")
    parser.add_argument("--version", required=True)
    parser.add_argument("--changelog-anchor-url", required=True)
    parser.add_argument("--compare-url", default=None)
    parser.add_argument("--project-root", default=".")
    parser.add_argument("--out-file", required=True, help="where to write the sanitized body on success")
    args = parser.parse_args(argv)

    body_path = Path(args.body_file)
    if not body_path.is_file():
        print(json.dumps({"ok": False, "reason": f"body file not found: {body_path}"}))
        return 1
    body = body_path.read_text(encoding="utf-8")

    footer = expected_footer(args.version, args.changelog_anchor_url, args.compare_url)
    repo_identity = resolve_repo_identity(Path(args.project_root).resolve())

    result = validate(body, args.version, footer=footer, repo_identity=repo_identity)
    if result.ok:
        out_path = Path(args.out_file)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with out_path.open("w", encoding="utf-8", newline="\n") as fh:
            fh.write(result.sanitized_body)

    print(json.dumps({"ok": result.ok, "reason": result.reason}, indent=2))
    return 0 if result.ok else 1


if __name__ == "__main__":
    sys.exit(main())
