"""Unit tests for the GitHub check-name derivation in automerge_readiness.

Pins ``expand_check_names`` / ``_is_dormant`` against handcrafted parsed-workflow
dicts with known-good outputs (matrix interpolation, no-`name:` job, no-matrix
job, multi-dim matrix, name-without-matrix-ref, include/exclude, `if:`-gating),
independent of any template. The integration / render / drift-pin tests live in
``test_automerge_readiness.py`` (split to keep each file under the 300-LOC
guideline).
"""

from __future__ import annotations

import pytest

pytest.importorskip("yaml")  # automerge_readiness imports PyYAML at module load

from lib import automerge_readiness as ar  # noqa: E402


class TestExpandCheckNames:
    def test_no_name_no_matrix_uses_job_id(self) -> None:
        parsed = {"jobs": {"claude-review": {"runs-on": "ubuntu-latest"}}}
        assert ar.expand_check_names(parsed) == ["claude-review"]

    def test_name_no_matrix_uses_name(self) -> None:
        parsed = {"jobs": {"scan": {"name": "Shipwright Security Scan"}}}
        assert ar.expand_check_names(parsed) == ["Shipwright Security Scan"]

    def test_matrix_name_interpolation(self) -> None:
        parsed = {
            "jobs": {
                "analyze": {
                    "name": "Analyze (${{ matrix.language }})",
                    "strategy": {"matrix": {"language": ["python", "javascript-typescript"]}},
                }
            }
        }
        assert ar.expand_check_names(parsed) == [
            "Analyze (python)",
            "Analyze (javascript-typescript)",
        ]

    def test_matrix_os_em_dash_name(self) -> None:
        parsed = {
            "jobs": {
                "test": {
                    "name": "Python (lint + test) — ${{ matrix.os }}",
                    "strategy": {"matrix": {"os": ["ubuntu-latest", "windows-latest"]}},
                }
            }
        }
        assert ar.expand_check_names(parsed) == [
            "Python (lint + test) — ubuntu-latest",
            "Python (lint + test) — windows-latest",
        ]

    def test_matrix_no_ref_in_name_appends_combo(self) -> None:
        # GitHub appends "(combo)" when name doesn't reference the matrix var.
        parsed = {
            "jobs": {
                "build": {
                    "name": "Build",
                    "strategy": {"matrix": {"os": ["ubuntu-latest", "windows-latest"]}},
                }
            }
        }
        assert ar.expand_check_names(parsed) == [
            "Build (ubuntu-latest)",
            "Build (windows-latest)",
        ]

    def test_matrix_no_name_appends_combo_to_job_id(self) -> None:
        parsed = {"jobs": {"build": {"strategy": {"matrix": {"os": ["ubuntu-latest"]}}}}}
        assert ar.expand_check_names(parsed) == ["build (ubuntu-latest)"]

    def test_include_exclude_keys_are_not_dims(self) -> None:
        parsed = {
            "jobs": {
                "t": {
                    "name": "T — ${{ matrix.os }}",
                    "strategy": {
                        "matrix": {
                            "os": ["ubuntu-latest"],
                            "include": [{"os": "macos-latest", "extra": 1}],
                        }
                    },
                }
            }
        }
        # `include` is not an expansion dim; only `os` expands.
        assert ar.expand_check_names(parsed) == ["T — ubuntu-latest"]

    def test_include_excluded_with_constant_name(self) -> None:
        # M1 guard with a NON-referencing name: `include` must not create a
        # spurious extra combo (the previous bug was masked by name interpolation).
        parsed = {
            "jobs": {
                "build": {
                    "name": "Build",
                    "strategy": {
                        "matrix": {
                            "os": ["ubuntu-latest"],
                            "include": [{"os": "macos-latest"}],
                            "exclude": [{"os": "windows-latest"}],
                        }
                    },
                }
            }
        }
        names = ar.expand_check_names(parsed)
        assert names == ["Build (ubuntu-latest)"]
        assert not any("macos" in n for n in names)

    def test_partial_multidim_appends_full_combo(self) -> None:
        # M2: name references `os` but the matrix is os×node — GitHub appends the
        # full combo, and emitting only the rendered name would collide.
        parsed = {
            "jobs": {
                "build": {
                    "name": "Build ${{ matrix.os }}",
                    "strategy": {"matrix": {"os": ["ubuntu-latest"], "node": [18, 20]}},
                }
            }
        }
        names = ar.expand_check_names(parsed)
        assert names == [
            "Build ubuntu-latest (ubuntu-latest, 18)",
            "Build ubuntu-latest (ubuntu-latest, 20)",
        ]
        assert len(names) == len(set(names)), "multi-dim names must be unique"

    def test_if_gated_job_still_in_expand_but_split_in_report(self) -> None:
        # expand_check_names returns ALL names; the requireable/conditional split
        # is workflow_report's job.
        parsed = {
            "jobs": {
                "test": {"name": "Tests"},
                "deploy": {"if": "github.ref == 'refs/heads/main'"},
            }
        }
        assert ar.expand_check_names(parsed) == ["Tests", "deploy"]


class TestIsDormant:
    def test_workflow_dispatch_only_is_dormant(self) -> None:
        assert ar._is_dormant({"on": {"workflow_dispatch": None}}) is True

    def test_pull_request_is_active(self) -> None:
        assert ar._is_dormant({"on": {"pull_request": {"branches": ["main"]}}}) is False

    def test_bare_on_truthy_key(self) -> None:
        # PyYAML parses bare `on:` -> Python True.
        assert ar._is_dormant({True: {"pull_request": None}}) is False
