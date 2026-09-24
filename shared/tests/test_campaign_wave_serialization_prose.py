"""Guards for the campaign-dag-scheduler R5a wave-serialization invariant:
wave N+1's ready set must not be computed, and wave N+1 must not be spawned,
until wave N's merge lane (today's still-serial 3f-bis..3i pipeline — R5b
has not been built yet at this sub-iterate's build time) has fully cleared
every unit in wave N.

A content guard, same shape as `test_campaign_step_3f_bis.py` and
`test_r2_worktree_capability_prose.py` (no code runs these docs) — each
assertion here has a clear "delete the subject and it fails" mutation.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _campaign_prose_harness import CAMPAIGN_DOC, norm  # noqa: E402


def _wave_loop_section() -> str:
    """The whole `3. **Loop ...` section, from its own header up to the
    `4. **Finalize:**` step that follows it."""
    text = CAMPAIGN_DOC.read_text(encoding="utf-8")
    start = re.search(r"(?m)^3\. \*\*Loop", text)
    assert start, "campaign-mode.md must define the numbered Loop step (3.)"
    body = text[start.start():]
    end = re.search(r"(?m)^4\. \*\*Finalize:\*\*", body)
    assert end, "campaign-mode.md must define step 4 (Finalize) after the Loop"
    return body[:end.start()]


def test_waves_serialize_on_the_merge_lane_is_stated_explicitly():
    section = norm(_wave_loop_section())
    assert "waves serialize on the merge lane" in section, (
        "the wave-serialization rule must be stated in the loop's own "
        "section, not only in the sub-iterate spec / plan document"
    )


def test_next_wave_ready_set_is_computed_only_after_the_drain_not_before():
    """The loop's OWN text must place 3a's next-wave computation textually
    AFTER the 3f-bis..3h drain description, not interleaved with or ahead
    of it — a reader following the doc top-to-bottom must reach "drain the
    wave" before "compute the next wave"."""
    section = _wave_loop_section()
    drain_at = section.find("3f-bis through 3h drain the wave")
    continue_at = section.find("3i.")
    assert drain_at >= 0, "the loop must describe the per-unit 3f-bis..3h drain"
    assert continue_at >= 0, "the loop must define step 3i"
    assert drain_at < continue_at, (
        "the drain description must precede 3i's continuation logic -- a "
        "reader must learn the wave drains before learning the loop "
        "advances to the next wave"
    )


def test_step_3i_names_both_the_intra_wave_and_cross_wave_continuation():
    """3i must distinguish "more units in this wave" (continue draining)
    from "wave fully drained" (compute the next wave) -- collapsing the two
    would let a reader believe the next wave's ready set could be computed
    while a sibling in the current wave is still mid-drain."""
    section = norm(_wave_loop_section())
    i_at = section.find("3i.")
    assert i_at >= 0
    body_3i = section[i_at:i_at + 700]
    assert "remain in this wave" in body_3i or "remain in the wave" in body_3i, (
        "3i must name the intra-wave continuation (more units still draining)"
    )
    assert "next-batch" in body_3i or "outer loop" in body_3i, (
        "3i must name the cross-wave continuation (advancing to the next wave)"
    )


def test_cross_wave_pipelining_is_named_as_an_explicit_non_goal():
    section = norm(_wave_loop_section())
    assert "non-goal" in section, (
        "the loop must state that overlapping a wave's merge lane with the "
        "next wave's build is an explicit non-goal, not merely unimplemented"
    )


def test_next_batch_replaces_the_single_unit_next_call_in_the_live_loop():
    """The live loop's own step 3a must call the BATCH primitive
    (`loop_claim.py next-batch`), not the single-unit `autonomous_loop.py
    next` this doc used before R5a's flip -- the batch call is what actually
    enforces the bounded, atomic multi-unit claim the wave model depends on."""
    section = norm(_wave_loop_section())
    step_3a = section[section.find("3a."):section.find("3b.")]
    assert "next-batch" in step_3a, (
        "step 3a must call loop_claim.py's next-batch, the wave-claiming primitive"
    )


def test_step_3c_spawns_every_claimed_unit_in_one_message():
    section = norm(_wave_loop_section())
    step_3c = section[section.find("3c."):section.find("3d.")]
    assert "one message" in step_3c, (
        "3c must spawn every claimed unit's Task in ONE message, not one at a time"
    )
    assert "every" in step_3c and "task" in step_3c, (
        "3c must describe spawning for EVERY unit in the claimed wave"
    )
