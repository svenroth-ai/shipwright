"""The freshness check compares what it RENDERS
(iterate-2026-07-31-f11-delivery-truth).

Split out of ``test_handoff_freshness.py`` to keep both files under the 300-line
source limit (constitution; the Group H audit fails an oversize file that carries no
baseline entry). The observed defect was a warning naming the SAME run id on both sides of its own
"not": the comparison saw raw values while the message rendered `clip()`-normalized
ones. The fix canonicalizes both sides through a SEPARATE, non-truncating normalizer,
because `clip` also cuts at 120 chars and comparing through it would trade a false WARN
for a false PASS.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))
# APPENDED, not inserted at 0 — `shared/tests/tools/` exists, so putting this directory
# first makes `import tools.…` resolve to the TEST tools package instead of
# `shared/scripts/tools` (ADR-045, the lib/tools collision).
sys.path.append(str(Path(__file__).resolve().parent))

from verifiers.handoff_freshness import check_session_handoff_fresh  # noqa: E402
from verifiers.handoff_marker import canonical_run_id  # noqa: E402

RUN = "iterate-2026-07-27-name-the-blocker"
OTHER = "iterate-2026-07-01-something-else"


def _write(root: Path, body: str) -> Path:
    docs = root / ".shipwright" / "agent_docs"
    docs.mkdir(parents=True, exist_ok=True)
    path = docs / "session_handoff.md"
    path.write_text(body, encoding="utf-8")
    return path


def _canon(run_id: str, body: str = "") -> str:
    return (
        f'---\ncanon_generated: true\nrun_id: "{run_id}"\nphase: "iterate"\n'
        f'reason: "finalize"\ntimestamp: "2026-07-27T09:00:00+00:00"\n---\n\n'
        f"# Session Handoff\n{body}"
    )


def _progress_block(run_id: str) -> str:
    return (
        "\n## Current Iterate Progress\n\n"
        "- **Branch**: iterate/x\n"
        f"- **Run ID**: {run_id}\n"
    )

# --- the check compares what it renders (iterate-2026-07-31-f11-delivery-truth) ---
#
# The observed defect was a warning naming the SAME run id on both sides of its
# own "not". The card blamed a backticked producer; no producer ever wrote one
# (`git log -S` over both, and the runtime cache copy, all bare). The real cause
# is narrower: the comparison saw the raw values while the message rendered
# `clip()`-normalized ones, so every difference `clip` erases produced a
# self-refuting sentence. Comparison now runs through the same canonicalization —
# but a SEPARATE, non-truncating one, because `clip` also cuts at 120 chars and
# comparing clipped values would trade a false WARN for a false PASS.

def test_a_run_id_padded_with_whitespace_still_names_this_run(tmp_path):
    """The actual mechanism: `clip` strips surrounding whitespace, the old
    comparison did not. Both sides rendered identically while `==` said no."""
    _write(tmp_path, _canon(RUN))
    result = check_session_handoff_fresh(tmp_path, f"  {RUN}\n")
    assert result.ok is True, result.detail


def test_a_backticked_run_id_still_names_this_run(tmp_path):
    """The shape the card reported. No producer writes it today; accepting it
    costs nothing and closes the door the card thought was already open."""
    _write(tmp_path, _canon(RUN, _progress_block(f"`{RUN}`")))
    result = check_session_handoff_fresh(tmp_path, RUN)
    assert result.ok is True, result.detail


def test_a_backticked_body_marker_still_names_this_run(tmp_path):
    """Same, on the no-frontmatter fallback path — the branch that actually
    emitted the observed warning."""
    _write(tmp_path, "# Session Handoff\n" + _progress_block(f"`{RUN}`"))
    result = check_session_handoff_fresh(tmp_path, RUN)
    assert result.ok is True, result.detail


def test_two_long_ids_sharing_the_display_prefix_are_not_equal():
    """The negative control on the fix itself. `clip` truncates at 120 chars, so
    canonicalizing THROUGH it would call these two the same run — a false PASS
    is worse than the false WARN being fixed."""
    long_a = "iterate-2026-07-31-" + ("a" * 120) + "-alpha"
    long_b = "iterate-2026-07-31-" + ("a" * 120) + "-beta"
    assert canonical_run_id(long_a) != canonical_run_id(long_b)


def test_a_long_id_survives_canonicalization_untruncated():
    """States the property the test above relies on, so a future `clip`-based
    'simplification' fails here with a readable reason."""
    long_id = "iterate-2026-07-31-" + ("z" * 200)
    assert canonical_run_id(long_id) == long_id


def test_an_invisible_character_inside_a_different_id_still_warns(tmp_path):
    """Stripping invisibles must not erase a REAL difference: a zero-width space
    inside an otherwise-different id leaves it different."""
    _write(tmp_path, _canon("iterate-2026-07-01-some\u200bthing-else"))
    result = check_session_handoff_fresh(tmp_path, RUN)
    assert result.ok is False
    assert result.severity == "warning"


def test_the_warning_never_names_the_same_run_on_both_sides(tmp_path):
    """The invariant, stated directly. This is the sentence the operator read:
    'names X, not X'. It must be unreachable, not merely unobserved."""
    for handoff_body, other in (
        (_canon(OTHER), RUN),
        ("# Session Handoff\n" + _progress_block(OTHER), RUN),
    ):
        _write(tmp_path, handoff_body)
        result = check_session_handoff_fresh(tmp_path, other)
        assert result.ok is False
        # Both operands appear in the detail, and they are DIFFERENT strings.
        assert canonical_run_id(OTHER) in result.detail
        assert canonical_run_id(other) in result.detail
        assert canonical_run_id(OTHER) != canonical_run_id(other)


def test_canonicalization_accepts_only_the_stated_equivalences():
    """Surrounding whitespace, paired backticks, invisibles. NOT case, NOT
    interior punctuation — an over-eager normalizer would launder real drift."""
    assert canonical_run_id(" `iterate-x` ") == "iterate-x"
    assert canonical_run_id("iterate-x\u200b") == "iterate-x"
    assert canonical_run_id("ITERATE-X") != canonical_run_id("iterate-x")
    assert canonical_run_id("iterate_x") != canonical_run_id("iterate-x")
    # A lone backtick is not a pair — leave it, so a malformed value stays visibly
    # malformed instead of being silently repaired into a match.
    assert canonical_run_id("`iterate-x") == "`iterate-x"


def test_a_mismatch_beyond_the_display_limit_still_reads_as_a_mismatch(tmp_path):
    """The residual case, closed explicitly. Two ids that differ only past the
    120-char display cap would CLIP to the same text — reproducing the
    self-refuting sentence one step further out. The message has to say where the
    difference sits instead of showing the same words twice."""
    from verifiers.handoff_marker import render_pair

    left = "iterate-2026-07-31-" + ("a" * 130) + "-alpha"
    right = "iterate-2026-07-31-" + ("a" * 130) + "-beta"
    shown_left, shown_right = render_pair(left, right)
    assert shown_left != shown_right
    assert "beyond" in shown_left

    _write(tmp_path, _canon(left))
    result = check_session_handoff_fresh(tmp_path, right)
    assert result.ok is False
    before, _, after = result.detail.partition(", not ")
    assert before.strip() != after.strip()


def test_render_pair_leaves_ordinary_values_alone():
    """No disambiguating noise on the overwhelmingly common case."""
    from verifiers.handoff_marker import render_pair

    assert render_pair(OTHER, RUN) == (OTHER, RUN)


def test_an_invisible_difference_is_not_reported_as_truncation(tmp_path):
    """`clip` truncates AND collapses whitespace, so a collision has two possible
    causes. Attributing every one to truncation told the operator the difference lay
    past character 120 for two short ids differing by a non-breaking space (Stage 2)."""
    from verifiers.handoff_marker import render_pair

    # U+00A0 is whitespace to `str.split()` (so `clip` collapses it) but NOT stripped by
    # `canonical_run_id` — a real difference that renders identically.
    left, right = "iterate-2026-07-31-a\u00a0b", "iterate-2026-07-31-a b"
    shown_left, shown_right = render_pair(left, right)
    assert shown_left != shown_right
    assert "cannot be seen" in shown_left
    assert "beyond" not in shown_left


def test_the_invisible_class_covers_the_characters_split_does_not_collapse():
    """SOFT HYPHEN, WORD JOINER, BOM and the grapheme joiner are invisible and are NOT
    whitespace, so `clip` leaves them in place — two ids differing only by one of them
    would have rendered as two identical strings, reproducing the original defect for
    that character class (Stage 2)."""
    from verifiers.handoff_marker import canonical_run_id

    for codepoint in ("\u00ad", "\u034f", "\u2060", "\ufeff"):
        assert canonical_run_id(f"iterate-x{codepoint}") == "iterate-x", repr(codepoint)
