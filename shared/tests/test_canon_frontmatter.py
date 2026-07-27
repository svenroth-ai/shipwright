"""`lib.canon_frontmatter` — the ONE parser for the handoff's canon frontmatter.

The block is written by ``generate_session_handoff.py --canon-marker``, read by the
Stop hook (to decide whether regenerating would clobber a canon handoff) and, since
iterate-2026-07-27-name-the-blocker, by the F11 freshness verifier (to decide whether
the handoff names the run currently finishing). Three consumers, one format — so the
parser lives in one place and this suite pins its semantics.

The semantics are carried over verbatim from the Stop hook's former private copy:
only a top-of-file block that declares ``canon_generated: true`` counts; anything
else (absent, malformed, or ordinary YAML written for another purpose) means "no
canon marker".
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))

from lib.canon_frontmatter import parse_canon_frontmatter  # noqa: E402


def _block(**fields) -> str:
    body = "\n".join(f'{k}: "{v}"' for k, v in fields.items())
    return f"---\ncanon_generated: true\n{body}\n---\n\n# Session Handoff\n"


def test_parses_a_well_formed_canon_block():
    out = parse_canon_frontmatter(_block(run_id="iterate-x", phase="iterate"))
    assert out is not None
    assert out["run_id"] == "iterate-x"
    assert out["phase"] == "iterate"


def test_no_frontmatter_at_all_is_none():
    assert parse_canon_frontmatter("# Session Handoff\n\nplain body\n") is None


def test_frontmatter_without_canon_generated_is_none():
    # Ordinary YAML written for some other purpose must NOT be mistaken for a
    # canon marker — that would let any front-matter'd file claim canon status.
    content = '---\ntitle: "notes"\nrun_id: "iterate-x"\n---\n\nbody\n'
    assert parse_canon_frontmatter(content) is None


def test_canon_generated_false_is_none():
    content = '---\ncanon_generated: false\nrun_id: "iterate-x"\n---\n\nbody\n'
    assert parse_canon_frontmatter(content) is None


def test_canon_generated_is_case_insensitive():
    content = '---\ncanon_generated: TRUE\nrun_id: "iterate-x"\n---\n\nbody\n'
    out = parse_canon_frontmatter(content)
    assert out is not None and out["run_id"] == "iterate-x"


def test_block_must_be_at_the_very_top():
    # A block after a leading line is not frontmatter. Guards the `\A` anchor:
    # without it, a fenced YAML sample inside the doc would be read as the marker.
    content = 'intro\n---\ncanon_generated: true\nrun_id: "iterate-x"\n---\n'
    assert parse_canon_frontmatter(content) is None


def test_unquoted_values_parse():
    content = "---\ncanon_generated: true\nrun_id: iterate-x\n---\n\nbody\n"
    out = parse_canon_frontmatter(content)
    assert out is not None and out["run_id"] == "iterate-x"


def test_unparsable_lines_are_skipped_not_fatal():
    content = (
        "---\ncanon_generated: true\n"
        "not a field line at all\n"
        'run_id: "iterate-x"\n---\n\nbody\n'
    )
    out = parse_canon_frontmatter(content)
    assert out is not None and out["run_id"] == "iterate-x"


def test_empty_string_is_none():
    assert parse_canon_frontmatter("") is None


def test_hook_and_lib_agree_on_the_same_input():
    """Drift guard: the Stop hook MUST delegate, not keep a second copy.

    The hook's decision (skip regeneration) and the verifier's decision (the
    handoff names this run) have to read the identical block the identical way,
    or one of them silently disagrees about what "this run wrote it" means.
    """
    sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts" / "hooks"))
    import generate_handoff_on_stop as hook

    assert hook._parse_canon_frontmatter is parse_canon_frontmatter
