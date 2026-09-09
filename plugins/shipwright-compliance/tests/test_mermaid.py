"""Tests for mermaid.py diagram builders."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.lib.data_collector import CommitEntry, DependencyInfo, SectionInfo
from scripts.lib.mermaid import (
    commit_type_pie,
    license_pie,
    pipeline_status_diagram,
    testing_pyramid_diagram,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _task(phase: str, status: str, split: str | None = None) -> dict:
    """A minimal phase_tasks[] entry — mirrors the pattern used by
    shared/tests/test_handoff_pipeline_phases.py. This reader only looks at
    ``phase`` and ``status``, so the other schema-required fields are omitted."""
    return {"phase": phase, "splitId": split, "status": status}


class TestPipelineStatusDiagram:
    def test_complete_pipeline(self):
        configs = {
            "run": {"status": "complete", "current_step": "changelog"},
            "project": {"status": "complete"},
            "plan": {"status": "complete"},
            "build": {"status": "complete"},
        }
        result = pipeline_status_diagram(configs)
        assert "```mermaid" in result
        assert "flowchart LR" in result
        assert "COMPLETE" in result
        assert "#4CAF50" in result  # green

    def test_in_progress_pipeline(self):
        """A driven run: project/design done, build mid-flight, nothing past it
        planned yet. Status comes from ``phase_tasks[]``, not ``current_step``."""
        configs = {
            "run": {
                "status": "in_progress",
                "phase_tasks": [
                    _task("project", "done"),
                    _task("design", "done"),
                    _task("build", "in_progress"),
                ],
            },
        }
        result = pipeline_status_diagram(configs)
        assert "IN PROGRESS" in result
        assert "#FFC107" in result  # yellow
        assert "#9E9E9E" in result  # gray for pending phases (test/changelog/deploy)

    def test_empty_configs(self):
        configs = {}
        result = pipeline_status_diagram(configs)
        assert "```mermaid" in result
        assert "PENDING" in result

    def test_the_write_once_fields_are_present_but_ignored(self):
        """``current_step`` / ``completed_steps`` are write-once and never
        advance on a driven run (campaign p4-04-retire-write-once-steps). Here
        they claim ``build`` is current and nothing is complete, while
        ``phase_tasks[]`` says build already finished and test is running —
        the rendered strip must follow phase_tasks[], not the stale fields."""
        configs = {
            "run": {
                "status": "in_progress",
                "current_step": "build",
                "completed_steps": [],
                "phase_tasks": [
                    _task("project", "done"),
                    _task("design", "done"),
                    _task("plan", "done"),
                    _task("build", "done"),
                    _task("test", "in_progress"),
                ],
            },
        }
        result = pipeline_status_diagram(configs)
        # BUILD would read PENDING (never IN PROGRESS/COMPLETE) if current_step
        # / completed_steps were still consulted — they are not.
        assert 'BUILD["Build<br/>COMPLETE"]' in result
        assert 'TEST["Test<br/>IN PROGRESS"]' in result

    def test_a_split_phase_is_complete_only_once_every_split_is(self):
        """plan/build can hold multiple phase_tasks entries (one per frozen
        split) — the node must not read complete while one split lags."""
        configs = {
            "run": {
                "status": "in_progress",
                "phase_tasks": [
                    _task("build", "done", split="01-core"),
                    _task("build", "in_progress", split="02-billing"),
                ],
            },
        }
        result = pipeline_status_diagram(configs)
        assert 'BUILD["Build<br/>IN PROGRESS"]' in result

    def test_falls_through_to_the_phase_config_when_phase_tasks_gives_no_confident_signal(self):
        """A phase whose only phase_tasks[] entry is neither finished nor
        active (e.g. still queued after a re-plan) must not assert PENDING
        outright — it falls through to that phase's own config, exactly as a
        phase with no phase_tasks[] entry at all does."""
        configs = {
            "run": {
                "status": "in_progress",
                "phase_tasks": [_task("plan", "backlog")],
            },
            "plan": {"status": "complete"},
        }
        result = pipeline_status_diagram(configs)
        assert 'PLAN["Plan<br/>COMPLETE"]' in result

    def test_a_malformed_task_status_does_not_crash_the_render(self):
        """A producer that writes a non-string ``status`` (list/dict) must not
        raise — ``x in frozenset`` on an unhashable value is exactly the
        hazard shared/scripts/lib/handoff_phase_status.status_of() guards
        against, and this reader mirrors that guard."""
        configs = {
            "run": {
                "status": "in_progress",
                "phase_tasks": [{"phase": "build", "splitId": None, "status": ["done"]}],
            },
        }
        result = pipeline_status_diagram(configs)
        assert 'BUILD["Build<br/>PENDING"]' in result

    def test_pins_the_rendered_strip_against_a_fixture_config(self):
        """A fixture config recorded on disk, rendered byte-for-byte, so a
        future change to the phase_tasks[] reading path is caught here."""
        run_config = json.loads(
            (FIXTURES_DIR / "sample_run_config_phase_tasks.json").read_text(
                encoding="utf-8",
            ),
        )
        configs = {"run": run_config}
        result = pipeline_status_diagram(configs)
        expected = (
            "```mermaid\n"
            "flowchart LR\n"
            '    PROJECT["Project<br/>COMPLETE"]\n'
            '    DESIGN["Design<br/>COMPLETE"]\n'
            '    PLAN["Plan<br/>COMPLETE"]\n'
            '    BUILD["Build<br/>IN PROGRESS"]\n'
            '    TEST["Test<br/>PENDING"]\n'
            '    CHANGELO["Changelog<br/>PENDING"]\n'
            '    DEPLOY["Deploy<br/>PENDING"]\n'
            "    PROJECT --> DESIGN --> PLAN --> BUILD --> TEST --> CHANGELO --> DEPLOY\n"
            "\n"
            "    style PROJECT fill:#4CAF50,color:#fff\n"
            "    style DESIGN fill:#4CAF50,color:#fff\n"
            "    style PLAN fill:#4CAF50,color:#fff\n"
            "    style BUILD fill:#FFC107,color:#000\n"
            "    style TEST fill:#9E9E9E,color:#fff\n"
            "    style CHANGELO fill:#9E9E9E,color:#fff\n"
            "    style DEPLOY fill:#9E9E9E,color:#fff\n"
            "```"
        )
        assert result == expected


class TestCommitTypePie:
    def test_with_commits(self):
        commits = [
            CommitEntry("abc", "feat", "auth", "add login", "2026-03-20", "Claude"),
            CommitEntry("def", "feat", "api", "add endpoint", "2026-03-20", "Claude"),
            CommitEntry("ghi", "fix", "auth", "fix timeout", "2026-03-21", "Claude"),
            CommitEntry("jkl", "test", "auth", "add tests", "2026-03-21", "Claude"),
        ]
        result = commit_type_pie(commits)
        assert "```mermaid" in result
        assert "pie title" in result
        assert '"feat" : 2' in result
        assert '"fix" : 1' in result
        assert '"test" : 1' in result

    def test_empty_commits(self):
        result = commit_type_pie([])
        assert "no commits" in result


class TestLicensePie:
    def test_with_dependencies(self):
        deps = [
            DependencyInfo("react", "19.2.0", "runtime", "MIT"),
            DependencyInfo("next", "16.2.0", "runtime", "MIT"),
            DependencyInfo("playwright", "1.50.0", "dev", "Apache-2.0"),
        ]
        result = license_pie(deps)
        assert "```mermaid" in result
        assert '"MIT" : 2' in result
        assert '"Apache-2.0" : 1' in result

    def test_empty_dependencies(self):
        result = license_pie([])
        assert "no packages" in result


class TestTestPyramidDiagram:
    def test_with_sections(self):
        sections = [
            SectionInfo("01-login", "01-auth", "complete", "abc", 5, 5, 1, 1, 0, 0),
            SectionInfo("02-rbac", "01-auth", "complete", "def", 8, 8, 0, 0, 0, 0),
        ]
        result = testing_pyramid_diagram(sections)
        assert "```mermaid" in result
        assert "13/13 passed" in result
        assert "2 sections reviewed" in result
