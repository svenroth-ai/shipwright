"""A campaign-runner shell's loop identity must not reach the integration tests.

Run with ``SHIPWRIGHT_LOOP_ID`` / ``SHIPWRIGHT_LOOP_UNIT_ID`` exported, the Stop
hooks that subprocess tests fire resolved a unit worktree that does not exist and
skipped the handoff (``test_removal_survivors_offpath``)."""
import os

import pytest


@pytest.mark.covers("FR-01.11")
def test_the_loop_identity_is_not_inherited():
    assert "SHIPWRIGHT_LOOP_ID" not in os.environ
    assert "SHIPWRIGHT_LOOP_UNIT_ID" not in os.environ
