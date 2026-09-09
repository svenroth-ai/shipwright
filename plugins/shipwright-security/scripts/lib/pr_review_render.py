"""Comment assembly for the Tier-3 PR reviewer.

Turns a parsed review result into the Markdown a maintainer reads. The
sanitiser and model-facing metadata block moved to `pr_review_sanitize` when
this file crossed the source-size guideline
(iterate-2026-09-09-pr-review-dict-finding-render) -- this module re-exports
them so existing call sites (`pr_review_lib`, `pr_review_dismiss`, tests) are
unchanged. Originally split out of `pr_review_lib` itself
(iterate-2026-07-27-pr-review-forged-boundary).

Path names rendered here come from the PR's own diff, so on an untrusted PR they
are attacker-chosen. `safe_path` is the one chokepoint.
"""

from __future__ import annotations

from pr_review_diff_filter import MAX_DIFF_CHARS
from pr_review_sanitize import (  # noqa: F401 -- re-exported for existing callers
    _CONTROL_AND_INVISIBLE,
    _CONTROL_ONLY,
    _left_out_count,
    _MARKDOWN_UNSAFE,
    _MAX_RENDERED_PATH,
    _path_list,
    _TRUNCATION_MARKER,
    _UNSAFE_IN_DISPLAY,
    build_pr_meta,
    nothing_reviewed_summary,
    safe_path,
    strip_display_unsafe,
)

__all__ = ["build_pr_meta", "nothing_reviewed_summary", "render_comment",
           "safe_path", "strip_display_unsafe", "_finding_text"]


def _finding_text(item) -> str:
    """A blocking/comment finding as the model returns it — usually a string,
    but observed (PR #690, 2026-09-08T14:04:35Z) as a structured object
    instead, with every other round on the same PR rendering the same finding
    as `path:lines - text` prose. Rendering whatever shape arrived via `str()`
    turns an object into its Python repr, truncating mid-value and feeding the
    next remediation round a mangled instruction — so both shapes are
    normalized to prose here, never stringified as-is.

    A finding's own text is model output, but the model can be steered by the
    PR's own untrusted content (paths, diff lines) — reviewed and blocked on
    PR #694, whose CI Tier-3 round caught this very module inserting such a
    value straight into the Markdown it renders. Every value that reaches the
    return is therefore sanitised: `location` through `safe_path` (the same
    chokepoint every other PR-controlled path in this module goes through, so
    it also gets a length bound), everything else through `_UNSAFE_IN_DISPLAY`
    (control/invisible + backtick/brace, uncapped — finding prose is free text
    that must not be truncated the way a path is).
    """
    if isinstance(item, dict):
        location = safe_path(str(
            item.get("file") or item.get("path") or item.get("location") or ""
        ).strip())
        text = _UNSAFE_IN_DISPLAY.sub("?", str(
            item.get("issue") or item.get("description") or item.get("message")
            or item.get("detail") or item.get("text") or ""
        ).strip())
        if location and text:
            return f"{location} - {text}"
        if location or text:
            return location or text
        # Unknown object shape: still never a raw dict repr. The key is just as
        # attacker-influenced as the value here (PR #694 CI review, round 2) --
        # a dict shaped {"a.py`x`\ninjected": "..."} must not smuggle either
        # half of the pair past this fallback unsanitised.
        return "; ".join(
            f"{_UNSAFE_IN_DISPLAY.sub('?', str(k))}: {_UNSAFE_IN_DISPLAY.sub('?', str(v))}"
            for k, v in item.items()
        )
    return _UNSAFE_IN_DISPLAY.sub("?", str(item))


def render_comment(
    review: dict, *, model: str, truncated: bool,
    excluded_generated: list[str] | None = None,
    omitted: tuple[str, ...] = (), partial: tuple[str, ...] = (),
    unidentified: int = 0,
) -> str:
    """Render the PR comment Markdown from a parsed review object."""
    decision = str(review.get("decision") or "unknown").strip().lower()
    badge = {"approve": "✅ APPROVE", "comment": "💬 COMMENT", "block": "🔴 BLOCK"}.get(
        decision, f"⚠️ {decision.upper()}"
    )
    lines = [
        "## 🤖 Shipwright PR Review",
        "",
        f"**Decision: {badge}**",
        "",
        str(review.get("summary") or "_No summary provided._"),
        "",
    ]
    if excluded_generated:
        # Human-facing transparency: say what the reviewer did NOT look at.
        n = len(excluded_generated)
        shown = ", ".join(f"`{safe_path(p)}`" for p in excluded_generated[:10])
        more = f" _(+{n - 10} more)_" if n > 10 else ""
        lines += [
            # Do NOT name lockfiles here. They left the filter in
            # iterate-2026-07-27-pr-review-forged-boundary, and a notice that
            # still lists them tells a maintainer the dependency change went
            # unreviewed when it was in fact sent to the model — the exact
            # inversion of the transparency this line exists for.
            f"> ℹ️ {n} generated file(s) were excluded from review (regenerated "
            f"artifacts — compliance docs, agent-docs, changelog drops, state "
            f"logs, prior review records — with no reviewable logic): "
            f"{shown}{more}.",
            "",
        ]
    if truncated:
        # Say WHAT went unreviewed, not just how many characters were dropped —
        # a byte count tells a reader nothing about what to go and look at.
        detail = []
        if omitted or unidentified:
            detail.append(
                # Paths, not files: a rename contributes both of its ends, so
                # counting "files" here would over-report a single moved file.
                # And paths are counted apart from unnameable sections — see
                # _left_out_count.
                f"**Not reviewed** ({_left_out_count(omitted, unidentified)}): "
                f"{_path_list(list(omitted), 10, unidentified)}."
            )
        if partial:
            detail.append(
                f"**Seen only in part**, as context: {_path_list(list(partial), 10)} — "
                "too large to include whole, so it counts as unreviewed."
            )
        if not detail:
            detail.append(
                "The affected files could not be identified — the diff had no "
                "parseable file headers."
            )
        lines += [
            f"> ⚠️ **This PR exceeded the {MAX_DIFF_CHARS:,}-character review limit**, so the "
            "review is **partial** and the check **fails closed**: a human must review "
            "this PR before merge. A waiver needs a trusted exact-head GitHub approval, "
            "a schema-valid review record with completed internal passes, **and** the `skip-pr-review` label; the label "
            "alone does **not** waive this check or retract the change request, which has "
            "to be dismissed by hand.",
            ">",
            *(f"> {d}" for d in detail),
            "",
        ]
    blocking = [t for b in (review.get("blocking") or []) if (t := _finding_text(b)).strip()]
    if blocking:
        lines.append("### 🚫 Blocking issues")
        lines += [f"- {b}" for b in blocking]
        lines.append("")
    comments = [t for c in (review.get("comments") or []) if (t := _finding_text(c)).strip()]
    if comments:
        lines.append("### Comments")
        lines += [f"- {c}" for c in comments]
        lines.append("")
    lines += [
        "---",
        f"_Automated Tier-3 review by `{model}` via OpenRouter "
        "(external / sensitive-path PR). Tier 1/2 PRs are reviewed locally at "
        "`/shipwright-iterate` Step 8 — see B4.5._",
    ]
    return "\n".join(lines)
