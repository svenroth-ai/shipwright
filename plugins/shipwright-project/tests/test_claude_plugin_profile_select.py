"""/shipwright-project can select the bundled ``claude-plugin`` profile by name (FR-01.01 AC30)."""

from __future__ import annotations

import pytest

from lib.profile_check import check_profile

pytestmark = pytest.mark.covers("FR-01.01/AC30")


def test_bundled_claude_plugin_profile_can_be_selected_by_name(tmp_path):
    """The skill lists profiles from the resolver and the writers check the name with it: nothing is special-cased."""
    check_profile("claude-plugin", tmp_path)  # raises ValueError for a name that cannot be used


def test_a_misspelt_plugin_profile_name_is_still_refused(tmp_path):
    with pytest.raises(ValueError):
        check_profile("claude-plugins", tmp_path)
