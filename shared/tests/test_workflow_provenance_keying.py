"""CI / CodeQL name-keyed defaults apply by PROVENANCE, not by name (D9, campaign S3).

A project / user / explicit profile that merely carries a bundled name never receives a
bundled CI template or CodeQL language list; ``None`` (no provenance) keeps the legacy
name-only lookup. Tagged to FR-01.06 (see shared/tests/test_profile_resolver.py).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from lib.ci_workflow import TEMPLATE_BY_PROFILE, template_path_for_profile  # noqa: E402
from lib.codeql_workflow import CODEQL_LANGUAGES_BY_PROFILE, languages_for_profile  # noqa: E402

pytestmark = pytest.mark.covers("FR-01.06")


@pytest.mark.parametrize("source", [None, "bundled", "builtin"])
@pytest.mark.parametrize("name", sorted(TEMPLATE_BY_PROFILE))
def test_bundled_provenance_keeps_the_name_keyed_template(name, source):
    assert template_path_for_profile(name, source) == TEMPLATE_BY_PROFILE[name]
    assert languages_for_profile(name, source) == CODEQL_LANGUAGES_BY_PROFILE[name]


@pytest.mark.parametrize("source", ["project", "user", "explicit"])
@pytest.mark.parametrize("name", sorted(TEMPLATE_BY_PROFILE))
def test_custom_provenance_never_gets_a_bundled_default(name, source):
    assert template_path_for_profile(name, source) is None
    assert languages_for_profile(name, source) is None


def test_unmapped_names_and_none_stay_none():
    assert template_path_for_profile("generic", "builtin") is None
    assert languages_for_profile(None, "bundled") is None
