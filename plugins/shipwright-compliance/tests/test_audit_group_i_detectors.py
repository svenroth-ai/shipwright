"""Group I — pure detector tests (name/description fences, fold candidates).

Split out of ``test_audit_group_i.py`` to mirror the group_i /
group_i_detectors source split and keep both files under the 300-LOC cap.
These exercise pure string predicates only — no filesystem, no findings.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path


PLUGIN_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PLUGIN_ROOT))

from scripts.audit import group_i  # noqa: E402


# ---------------------------------------------------------------------------
# Detectors — name fence
# ---------------------------------------------------------------------------


def test_name_flags_http_verb():
    assert "http-verb" in group_i.name_violations("Pending tool_use list (GET)")


def test_name_flags_adr_number():
    assert "adr-number" in group_i.name_violations("Embedded terminal (ADR-067)")


def test_name_flags_snake_case_symbol():
    assert "code-symbol" in group_i.name_violations("Manage actions_config upload")


def test_name_flags_iterate_slug():
    assert "iterate-slug" in group_i.name_violations("Mission view iterate-2026-07-09-w3")


def test_name_flags_file_path():
    assert "file-path" in group_i.name_violations("Upload actions.json")


def test_clean_capability_name_is_silent():
    assert group_i.name_violations("Start or resume a task") == []
    assert group_i.name_violations("Embedded terminal") == []


# ---------------------------------------------------------------------------
# Detectors — description fence
# ---------------------------------------------------------------------------


def test_description_flags_file_path():
    got = group_i.description_violations("Persisted at client/src/lib/taskSort.ts on save.")
    assert "file-path" in got


def test_description_flags_camel_case_symbol():
    got = group_i.description_violations("Ordered by lastJsonlSeenMtimeMs descending.")
    assert "code-symbol" in got


def test_description_allows_plain_prose_with_gloss():
    text = (
        "Settings are saved safely, so two open tabs can't corrupt each "
        "other's changes. The save is idempotent (safe to run twice)."
    )
    assert group_i.description_violations(text) == []


def test_platform_names_are_not_code_symbols():
    """`iOS` / `macOS` are camelCase-shaped but are ordinary product words."""
    assert group_i.description_violations("Prevents unwanted zoom on iOS and iPadOS.") == []


def test_description_flags_pascal_case_symbol():
    """PascalCase class/type names are implementation detail too."""
    assert "code-symbol" in group_i.description_violations(
        "Delegates to TaskService before rendering."
    )


def test_capitalised_prose_is_not_a_pascal_symbol():
    """Ordinary Title Case must not be mistaken for a class name."""
    assert group_i.description_violations(
        "The Command Center shows every Task on one Board."
    ) == []


# ---------------------------------------------------------------------------
# Detectors — fold candidates
# ---------------------------------------------------------------------------


def test_fold_candidate_completes_another_fr():
    assert group_i.is_fold_candidate("Bugfix that completes FR-01.37.")


def test_fold_candidate_phase_n_of():
    assert group_i.is_fold_candidate("Campaigns lane, Phase 2 of FR-01.33.")


def test_fold_candidate_replaces_another_fr():
    assert group_i.is_fold_candidate("Replaces FR-01.33's affordance.")


def test_fold_candidate_covers_every_verb_the_rulebook_lists():
    """§3 names completes/fixes/polishes/extends — all must be detected."""
    for verb in ("completes", "fixes", "polishes", "extends", "supersedes", "modifies"):
        assert group_i.is_fold_candidate(f"This {verb} FR-01.37."), verb


def test_ordinary_description_is_not_a_fold_candidate():
    assert not group_i.is_fold_candidate("Shows every task grouped by state.")


def test_domain_phase_prose_is_not_a_fold_candidate():
    """'Phase N of' is ordinary domain vocabulary unless it cites an FR."""
    assert not group_i.is_fold_candidate(
        "The system SHALL show phase 2 of the application form."
    )


# ---------------------------------------------------------------------------
# ReDoS regression (CodeQL py/redos, HIGH — caught on PR #395)
# ---------------------------------------------------------------------------


def test_detectors_are_linear_on_pathological_input():
    r"""These regexes run over arbitrary requirement prose — they must not blow up.

    The original `_FILE_PATH_RE` was `[\w./-]*\w\.(ext)`: `\w` is a subset of
    `[\w./-]`, so a long word-char run that never reaches a real extension has
    exponentially many ways to split, and the match backtracks forever. The same
    class of overlap existed in `_PASCAL_RE`'s inner `[a-zA-Z]*`.

    A spec description is untrusted-ish input (adopt reverse-engineers it from a
    foreign repo), and a hung detector would wedge the whole compliance audit.
    The old pattern does not finish this in any practical time; the fixed one is
    linear, so a generous ceiling still separates them decisively.
    """
    hostile = [
        "A" * 4000,                       # one long word-char run, no dot
        ("a" * 2000) + "!",               # long run then a non-matching tail
        "Aa" * 2000,                      # alternating case, PascalCase-ish
        ("x" * 2000) + ".zzz",            # long run then a NON-matching extension
        ("path/" * 500) + "file",         # many separators, no extension
    ]
    start = time.perf_counter()
    for text in hostile:
        group_i.name_violations(text)
        group_i.description_violations(text)
        group_i.is_fold_candidate(text)
    elapsed = time.perf_counter() - start
    assert elapsed < 2.0, f"detectors took {elapsed:.2f}s on pathological input — ReDoS regression"


def test_file_path_detection_survived_the_redos_fix():
    """The linear pattern must still catch the real cases the fence exists for."""
    for text in ("Persisted at client/src/lib/taskSort.ts on save.",
                 "Upload actions.json via the modal.",
                 "See spec.md for detail.",
                 "Reads config.yaml at boot.",
                 "Styled in main.css."):
        assert "file-path" in group_i.description_violations(text), text


def test_tsx_is_not_read_as_ts_plus_x():
    assert "file-path" in group_i.description_violations("Renders in Board.tsx today.")
