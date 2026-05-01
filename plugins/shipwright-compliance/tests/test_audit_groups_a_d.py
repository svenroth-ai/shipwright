"""Groups A + D detective-only tests (plan v7 Option Z, Step 4).

Group A — Artifact / path integrity:
- A2: dev-block command refs (npm/uv/make) resolve in the project tree
- A3: ``pyproject.toml [project.scripts]`` entry-points are importable
- A4: every path-valued field listed in ``audit_config.json.a4_path_fields``
  points to an existing file on disk

Group D — Event-log FR coverage:
- D1: every FR in spec.md has at least one covering ``work_completed``
  event with that FR-ID in ``affected_frs``. Severity is priority-driven
  (Must=HIGH, Should=MEDIUM, May=LOW).
- D2: events referencing FR-IDs not present in the current spec.md
- D3: FRs introduced via an event's ``new_frs`` but never observed in any
  subsequent event's ``affected_frs``
- D4: most recent covering event has ``tests.passed < tests.total``

Epoch floor (D1/D2): the latest event carrying a ``spec_updated`` field
acts as a watermark — older events are excluded so a renamed FR doesn't
generate a stale-coverage finding against its old id.

These tests are hermetic: every fixture is built under ``tmp_path``, no
network, no real plugin/shared imports beyond the audit modules
themselves.
"""

from __future__ import annotations

import json
import sys
import textwrap
from pathlib import Path

import pytest

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
if str(PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(PLUGIN_ROOT))

from scripts.audit import group_a, group_d  # noqa: E402
from scripts.audit.audit_adapters import SOURCE_DETECTIVE_ONLY  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(content).lstrip("\n"), encoding="utf-8")


def _events(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row) + "\n" for row in rows),
        encoding="utf-8",
    )


def _default_config() -> dict:
    """Mirrors ``audit_detector._DEFAULT_CONFIG`` for the fields we exercise."""
    return {
        "a4_path_fields": [
            "project_config.splits[].spec_path",
            "plan_config.sections[].section_file",
        ],
    }


# ---------------------------------------------------------------------------
# Group A — A2: dev-block command refs
# ---------------------------------------------------------------------------


def test_a2_passes_when_all_commands_resolve(tmp_path):
    _write(tmp_path / "package.json", """
        {"scripts": {"dev": "vite", "build": "vite build"}}
    """)
    # Makefile rules MUST sit at column 0 — write directly, no dedent.
    (tmp_path / "Makefile").write_text("check:\n\techo ok\n", encoding="utf-8")
    _write(tmp_path / "pyproject.toml", """
        [project]
        name = "demo"
    """)
    _write(tmp_path / "CLAUDE.md", """
        ## Development

        ```bash
        npm run dev
        npm run build
        uv run pytest
        make check
        ```
    """)

    findings = group_a.run(tmp_path, _default_config(), None)
    a2 = next(f for f in findings if f.check_id == "A2")
    assert a2.status == "pass", a2.detail
    assert a2.source == SOURCE_DETECTIVE_ONLY


def test_a2_flags_missing_npm_script(tmp_path):
    _write(tmp_path / "package.json", """
        {"scripts": {"dev": "vite"}}
    """)
    _write(tmp_path / "CLAUDE.md", """
        ## Development

        ```bash
        npm run lint
        ```
    """)

    findings = group_a.run(tmp_path, _default_config(), None)
    a2 = next(f for f in findings if f.check_id == "A2")
    assert a2.status == "fail"
    assert a2.severity == "HIGH"
    assert "npm run lint" in a2.detail


def test_a2_flags_missing_make_target(tmp_path):
    (tmp_path / "Makefile").write_text("check:\n\techo ok\n", encoding="utf-8")
    _write(tmp_path / "CLAUDE.md", """
        ## Development

        ```bash
        make ship
        ```
    """)

    findings = group_a.run(tmp_path, _default_config(), None)
    a2 = next(f for f in findings if f.check_id == "A2")
    assert a2.status == "fail"
    assert "make ship" in a2.detail


def test_a2_skips_when_no_claude_md(tmp_path):
    findings = group_a.run(tmp_path, _default_config(), None)
    a2 = next(f for f in findings if f.check_id == "A2")
    assert a2.status == "skip"


def test_a2_skips_when_no_dev_block(tmp_path):
    _write(tmp_path / "CLAUDE.md", """
        # No development section here
    """)
    findings = group_a.run(tmp_path, _default_config(), None)
    a2 = next(f for f in findings if f.check_id == "A2")
    assert a2.status == "skip"


def test_a2_passes_bare_uv_tools_silently(tmp_path):
    """``uv run pytest`` references a transitive dev-dep, not a project
    file or console script. By design A2 does NOT fail on bare tool
    names — see _verify_uv_ref docstring for the rationale."""
    _write(tmp_path / "pyproject.toml", """
        [project]
        name = "demo"
    """)
    _write(tmp_path / "CLAUDE.md", """
        ## Development

        ```bash
        uv run pytest
        ```
    """)
    findings = group_a.run(tmp_path, _default_config(), None)
    a2 = next(f for f in findings if f.check_id == "A2")
    assert a2.status == "pass", a2.detail


def test_a2_flags_uv_path_refs_that_dont_exist(tmp_path):
    """Path-shaped uv targets (containing ``/`` or ``.py``) DO get checked."""
    _write(tmp_path / "CLAUDE.md", """
        ## Development

        ```bash
        uv run scripts/missing.py
        ```
    """)
    findings = group_a.run(tmp_path, _default_config(), None)
    a2 = next(f for f in findings if f.check_id == "A2")
    assert a2.status == "fail"
    assert "scripts/missing.py" in a2.detail


# ---------------------------------------------------------------------------
# Group A — A3: pyproject [project.scripts] entry-points
# ---------------------------------------------------------------------------


def test_a3_passes_when_entry_modules_exist(tmp_path):
    _write(tmp_path / "pyproject.toml", """
        [project]
        name = "demo"
        [project.scripts]
        demo-cli = "demo.cli:main"
    """)
    _write(tmp_path / "demo" / "__init__.py", "")
    _write(tmp_path / "demo" / "cli.py", "def main():\n    pass\n")

    findings = group_a.run(tmp_path, _default_config(), None)
    a3 = next(f for f in findings if f.check_id == "A3")
    assert a3.status == "pass", a3.detail


def test_a3_flags_missing_module(tmp_path):
    _write(tmp_path / "pyproject.toml", """
        [project]
        name = "demo"
        [project.scripts]
        demo-cli = "demo.cli:main"
    """)
    # No demo/cli.py created.

    findings = group_a.run(tmp_path, _default_config(), None)
    a3 = next(f for f in findings if f.check_id == "A3")
    assert a3.status == "fail"
    assert a3.severity == "MEDIUM"
    assert "demo.cli" in a3.detail


def test_a3_skips_when_no_pyproject(tmp_path):
    findings = group_a.run(tmp_path, _default_config(), None)
    a3 = next(f for f in findings if f.check_id == "A3")
    assert a3.status == "skip"


def test_a3_skips_when_no_project_scripts_table(tmp_path):
    _write(tmp_path / "pyproject.toml", """
        [project]
        name = "demo"
    """)
    findings = group_a.run(tmp_path, _default_config(), None)
    a3 = next(f for f in findings if f.check_id == "A3")
    assert a3.status == "skip"


# ---------------------------------------------------------------------------
# Group A — A4: config path-field integrity
# ---------------------------------------------------------------------------


def test_a4_passes_when_every_path_field_resolves(tmp_path):
    spec_path = tmp_path / ".shipwright" / "planning" / "01-foo" / "spec.md"
    section_path = tmp_path / ".shipwright" / "planning" / "01-foo" / "sections" / "01-init.md"
    _write(spec_path, "FRs go here\n")
    _write(section_path, "section body\n")

    _write(tmp_path / "shipwright_project_config.json", json.dumps({
        "splits": [{"spec_path": ".shipwright/planning/01-foo/spec.md"}],
    }))
    _write(tmp_path / "shipwright_plan_config.json", json.dumps({
        "sections": [{"section_file": ".shipwright/planning/01-foo/sections/01-init.md"}],
    }))

    findings = group_a.run(tmp_path, _default_config(), None)
    a4 = next(f for f in findings if f.check_id == "A4")
    assert a4.status == "pass", a4.detail


def test_a4_flags_missing_path(tmp_path):
    _write(tmp_path / "shipwright_project_config.json", json.dumps({
        "splits": [{"spec_path": ".shipwright/planning/missing/spec.md"}],
    }))
    findings = group_a.run(tmp_path, _default_config(), None)
    a4 = next(f for f in findings if f.check_id == "A4")
    assert a4.status == "fail"
    assert a4.severity == "HIGH"
    assert ".shipwright/planning/missing/spec.md" in a4.detail


def test_a4_skips_when_no_configs_present(tmp_path):
    findings = group_a.run(tmp_path, _default_config(), None)
    a4 = next(f for f in findings if f.check_id == "A4")
    assert a4.status == "skip"


# ---------------------------------------------------------------------------
# A4 regression — Sub-Iterate C: real-shape config schema + {} walker
# ---------------------------------------------------------------------------


def _default_config_real_shape() -> dict:
    """Mirrors the post-Sub-Iterate-C ``audit_detector._DEFAULT_CONFIG``."""
    return {
        "a4_path_fields": [
            "plan_config.splits.{}.plan_file",
            "plan_config.spec_file",
        ],
    }


def test_a4_passes_against_aiportal_shape_plan_config(tmp_path):
    """Real plan_config shape: ``splits.<name>.plan_file`` (multi-split).

    The Sub-Iterate C default uses ``splits.{}.plan_file`` to walk the
    dynamic split-name keys. This test pins the contract so future schema
    changes can't silently drop coverage.
    """
    plan_a = tmp_path / ".shipwright" / "planning" / "01-foundation" / "plan.md"
    plan_b = tmp_path / ".shipwright" / "planning" / "02-course-platform" / "plan.md"
    _write(plan_a, "Foundation plan\n")
    _write(plan_b, "Course platform plan\n")

    _write(tmp_path / "shipwright_plan_config.json", json.dumps({
        "splits": {
            "01-foundation": {
                "status": "complete",
                "plan_file": ".shipwright/planning/01-foundation/plan.md",
            },
            "02-course-platform": {
                "status": "complete",
                "plan_file": ".shipwright/planning/02-course-platform/plan.md",
            },
        },
    }))

    findings = group_a.run(tmp_path, _default_config_real_shape(), None)
    a4 = next(f for f in findings if f.check_id == "A4")
    assert a4.status == "pass", a4.detail


def test_a4_flags_missing_plan_file_in_multi_split_shape(tmp_path):
    _write(tmp_path / "shipwright_plan_config.json", json.dumps({
        "splits": {
            "01-foundation": {
                "plan_file": ".shipwright/planning/01-foundation/plan.md",
            },
        },
    }))
    # plan.md intentionally not created.
    findings = group_a.run(tmp_path, _default_config_real_shape(), None)
    a4 = next(f for f in findings if f.check_id == "A4")
    assert a4.status == "fail"
    assert "01-foundation/plan.md" in a4.detail


def test_a4_passes_against_single_split_shape_plan_config(tmp_path):
    """Real plan_config from setup-planning-session.py: top-level ``spec_file``."""
    spec = tmp_path / ".shipwright" / "planning" / "splits" / "01-auth" / "spec.md"
    _write(spec, "FRs\n")
    _write(tmp_path / "shipwright_plan_config.json", json.dumps({
        "spec_file": ".shipwright/planning/splits/01-auth/spec.md",
        "status": "complete",
    }))

    findings = group_a.run(tmp_path, _default_config_real_shape(), None)
    a4 = next(f for f in findings if f.check_id == "A4")
    assert a4.status == "pass", a4.detail


def test_a4_walker_supports_brace_dict_iteration(tmp_path):
    """The ``{}`` dotted-path segment iterates a dict's values.

    Direct test of the engine: configurable enough that future projects
    with their own dotted-path layouts can use it.
    """
    cfg = {"a4_path_fields": ["plan_config.entries.{}.path"]}
    _write(tmp_path / "real-a.txt", "x\n")
    _write(tmp_path / "real-b.txt", "y\n")
    _write(tmp_path / "shipwright_plan_config.json", json.dumps({
        "entries": {
            "alpha": {"path": "real-a.txt"},
            "beta": {"path": "real-b.txt"},
        },
    }))
    findings = group_a.run(tmp_path, cfg, None)
    a4 = next(f for f in findings if f.check_id == "A4")
    assert a4.status == "pass", a4.detail


def test_a4_walker_brace_iteration_flags_missing_value(tmp_path):
    cfg = {"a4_path_fields": ["plan_config.entries.{}.path"]}
    _write(tmp_path / "shipwright_plan_config.json", json.dumps({
        "entries": {"alpha": {"path": "missing.txt"}},
    }))
    findings = group_a.run(tmp_path, cfg, None)
    a4 = next(f for f in findings if f.check_id == "A4")
    assert a4.status == "fail"
    assert "missing.txt" in a4.detail


def test_a4_walker_brace_iteration_skips_when_node_is_list(tmp_path):
    """``{}`` requires a dict — wrong-type yields nothing rather than crashing."""
    cfg = {"a4_path_fields": ["plan_config.splits.{}.plan_file"]}
    # splits is a list (project_config-style), not a dict — {} won't iterate.
    _write(tmp_path / "shipwright_plan_config.json", json.dumps({
        "splits": [{"name": "01-foo"}],
    }))
    findings = group_a.run(tmp_path, cfg, None)
    a4 = next(f for f in findings if f.check_id == "A4")
    # No values yielded → no path-fields → A4 skips.
    assert a4.status == "skip"


# ---------------------------------------------------------------------------
# Group D — D1: spec FR uncovered in events
# ---------------------------------------------------------------------------


def _spec_with_frs(frs: list[tuple[str, str, str]]) -> str:
    """Build a spec.md body with the given (id, text, priority) FR rows."""
    rows = "\n".join(f"| {fr_id} | {text} | {prio} |" for fr_id, text, prio in frs)
    return f"# Spec\n\n| FR | Description | Priority |\n| --- | --- | --- |\n{rows}\n"


def test_d1_passes_when_every_must_fr_has_an_event(tmp_path):
    _write(
        tmp_path / ".shipwright" / "planning" / "01-foo" / "spec.md",
        _spec_with_frs([
            ("FR-01.01", "Login flow", "Must"),
            ("FR-01.02", "Reset", "Should"),
        ]),
    )
    _events(tmp_path / "shipwright_events.jsonl", [
        {"type": "work_completed", "ts": "2026-04-01T00:00:00+00:00",
         "affected_frs": ["FR-01.01", "FR-01.02"]},
    ])

    findings = group_d.run(tmp_path, _default_config(), None)
    d1 = next(f for f in findings if f.check_id == "D1")
    assert d1.status == "pass", d1.detail


def test_d1_flags_uncovered_must_fr_as_high(tmp_path):
    _write(
        tmp_path / ".shipwright" / "planning" / "01-foo" / "spec.md",
        _spec_with_frs([("FR-02.01", "Critical path", "Must")]),
    )
    _events(tmp_path / "shipwright_events.jsonl", [
        {"type": "work_completed", "ts": "2026-04-01T00:00:00+00:00",
         "affected_frs": ["FR-99.99"]},
    ])

    findings = group_d.run(tmp_path, _default_config(), None)
    d1 = next(f for f in findings if f.check_id == "D1")
    assert d1.status == "fail"
    assert d1.severity == "HIGH"
    assert "FR-02.01" in d1.detail


def test_d1_uses_priority_for_severity(tmp_path):
    _write(
        tmp_path / ".shipwright" / "planning" / "01-foo" / "spec.md",
        _spec_with_frs([
            ("FR-01.01", "Could-have", "May"),
        ]),
    )
    _events(tmp_path / "shipwright_events.jsonl", [
        {"type": "work_completed", "ts": "2026-04-01T00:00:00+00:00",
         "affected_frs": ["FR-99.99"]},
    ])

    findings = group_d.run(tmp_path, _default_config(), None)
    d1 = next(f for f in findings if f.check_id == "D1")
    assert d1.status == "fail"
    assert d1.severity == "LOW"


def test_d1_skips_when_events_jsonl_absent(tmp_path):
    _write(
        tmp_path / ".shipwright" / "planning" / "01-foo" / "spec.md",
        _spec_with_frs([("FR-01.01", "x", "Must")]),
    )
    findings = group_d.run(tmp_path, _default_config(), None)
    d1 = next(f for f in findings if f.check_id == "D1")
    assert d1.status == "skip"


def test_d1_skips_when_no_work_completed_events(tmp_path):
    _write(
        tmp_path / ".shipwright" / "planning" / "01-foo" / "spec.md",
        _spec_with_frs([("FR-01.01", "x", "Must")]),
    )
    _events(tmp_path / "shipwright_events.jsonl", [
        {"type": "phase_started", "ts": "2026-04-01T00:00:00+00:00",
         "phase": "build"},
    ])
    findings = group_d.run(tmp_path, _default_config(), None)
    d1 = next(f for f in findings if f.check_id == "D1")
    assert d1.status == "skip"


def test_d1_epoch_floor_excludes_pre_watermark_events(tmp_path):
    """An event for FR-01.01 BEFORE the spec_updated watermark should be ignored —
    the FR may have been redefined, so old coverage is not authoritative."""
    _write(
        tmp_path / ".shipwright" / "planning" / "01-foo" / "spec.md",
        _spec_with_frs([("FR-01.01", "Renamed FR", "Must")]),
    )
    _events(tmp_path / "shipwright_events.jsonl", [
        {"type": "work_completed", "ts": "2026-01-01T00:00:00+00:00",
         "affected_frs": ["FR-01.01"]},
        {"type": "work_completed", "ts": "2026-03-01T00:00:00+00:00",
         "spec_updated": ".shipwright/planning/01-foo/spec.md"},
    ])

    findings = group_d.run(tmp_path, _default_config(), None)
    d1 = next(f for f in findings if f.check_id == "D1")
    assert d1.status == "fail"
    assert "FR-01.01" in d1.detail


# ---------------------------------------------------------------------------
# Group D — D2: stale FR references in events
# ---------------------------------------------------------------------------


def test_d2_passes_when_every_event_fr_exists_in_spec(tmp_path):
    _write(
        tmp_path / ".shipwright" / "planning" / "01-foo" / "spec.md",
        _spec_with_frs([("FR-01.01", "x", "Must")]),
    )
    _events(tmp_path / "shipwright_events.jsonl", [
        {"type": "work_completed", "ts": "2026-04-01T00:00:00+00:00",
         "affected_frs": ["FR-01.01"]},
    ])

    findings = group_d.run(tmp_path, _default_config(), None)
    d2 = next(f for f in findings if f.check_id == "D2")
    assert d2.status == "pass"


def test_d2_flags_stale_fr_reference(tmp_path):
    _write(
        tmp_path / ".shipwright" / "planning" / "01-foo" / "spec.md",
        _spec_with_frs([("FR-01.01", "x", "Must")]),
    )
    _events(tmp_path / "shipwright_events.jsonl", [
        {"type": "work_completed", "ts": "2026-04-01T00:00:00+00:00",
         "affected_frs": ["FR-99.99"]},
    ])

    findings = group_d.run(tmp_path, _default_config(), None)
    d2 = next(f for f in findings if f.check_id == "D2")
    assert d2.status == "fail"
    assert d2.severity == "MEDIUM"
    assert "FR-99.99" in d2.detail


def test_d2_flags_stale_fr_on_non_work_completed_event(tmp_path):
    """D2 scans every event with affected_frs, regardless of type —
    a stale FR on a task_created or event_amended is still drift."""
    _write(
        tmp_path / ".shipwright" / "planning" / "01-foo" / "spec.md",
        _spec_with_frs([("FR-01.01", "x", "Must")]),
    )
    _events(tmp_path / "shipwright_events.jsonl", [
        {"type": "task_created", "ts": "2026-04-01T00:00:00+00:00",
         "affected_frs": ["FR-99.99"]},
    ])
    findings = group_d.run(tmp_path, _default_config(), None)
    d2 = next(f for f in findings if f.check_id == "D2")
    assert d2.status == "fail"
    assert "FR-99.99" in d2.detail


def test_d2_skips_when_no_spec(tmp_path):
    _events(tmp_path / "shipwright_events.jsonl", [
        {"type": "work_completed", "ts": "2026-04-01T00:00:00+00:00",
         "affected_frs": ["FR-99.99"]},
    ])
    findings = group_d.run(tmp_path, _default_config(), None)
    d2 = next(f for f in findings if f.check_id == "D2")
    assert d2.status == "skip"


# ---------------------------------------------------------------------------
# Group D — D3: promised FRs (new_frs) never delivered
# ---------------------------------------------------------------------------


def test_d3_passes_when_promised_frs_were_delivered(tmp_path):
    _write(
        tmp_path / ".shipwright" / "planning" / "01-foo" / "spec.md",
        _spec_with_frs([("FR-01.01", "x", "Must")]),
    )
    _events(tmp_path / "shipwright_events.jsonl", [
        {"type": "work_completed", "ts": "2026-04-01T00:00:00+00:00",
         "new_frs": ["FR-01.01"]},
        {"type": "work_completed", "ts": "2026-04-02T00:00:00+00:00",
         "affected_frs": ["FR-01.01"]},
    ])

    findings = group_d.run(tmp_path, _default_config(), None)
    d3 = next(f for f in findings if f.check_id == "D3")
    assert d3.status == "pass"


def test_d3_flags_promised_but_never_touched_fr(tmp_path):
    _write(
        tmp_path / ".shipwright" / "planning" / "01-foo" / "spec.md",
        _spec_with_frs([("FR-01.01", "x", "Must")]),
    )
    _events(tmp_path / "shipwright_events.jsonl", [
        {"type": "work_completed", "ts": "2026-04-01T00:00:00+00:00",
         "new_frs": ["FR-01.01"]},
    ])

    findings = group_d.run(tmp_path, _default_config(), None)
    d3 = next(f for f in findings if f.check_id == "D3")
    assert d3.status == "fail"
    assert d3.severity == "MEDIUM"
    assert "FR-01.01" in d3.detail


# ---------------------------------------------------------------------------
# Group D — D4: latest covering event has failing tests
# ---------------------------------------------------------------------------


def test_d4_passes_when_latest_covering_events_were_green(tmp_path):
    _write(
        tmp_path / ".shipwright" / "planning" / "01-foo" / "spec.md",
        _spec_with_frs([("FR-01.01", "x", "Must")]),
    )
    _events(tmp_path / "shipwright_events.jsonl", [
        {"type": "work_completed", "ts": "2026-04-01T00:00:00+00:00",
         "affected_frs": ["FR-01.01"],
         "tests": {"passed": 10, "total": 10}},
    ])
    findings = group_d.run(tmp_path, _default_config(), None)
    d4 = next(f for f in findings if f.check_id == "D4")
    assert d4.status == "pass"


def test_d4_flags_fr_last_touched_in_failing_build(tmp_path):
    _write(
        tmp_path / ".shipwright" / "planning" / "01-foo" / "spec.md",
        _spec_with_frs([("FR-01.01", "x", "Must")]),
    )
    _events(tmp_path / "shipwright_events.jsonl", [
        {"type": "work_completed", "ts": "2026-04-01T00:00:00+00:00",
         "affected_frs": ["FR-01.01"],
         "tests": {"passed": 8, "total": 10}},
    ])
    findings = group_d.run(tmp_path, _default_config(), None)
    d4 = next(f for f in findings if f.check_id == "D4")
    assert d4.status == "fail"
    assert d4.severity == "LOW"
    assert "FR-01.01" in d4.detail


# ---------------------------------------------------------------------------
# End-to-end through the detector + registry
# ---------------------------------------------------------------------------


def test_registry_wires_a_and_d_via_run_all(tmp_path):
    """After register_all() runs, every Plan-v7 group is present."""
    from scripts.audit import audit_detector
    from scripts.audit._registry import register_all

    register_all()
    registered = set(audit_detector.registered_groups().keys())
    # Sub-Iterate C wired E + G; the registry now covers all of A..G.
    assert registered == {"A", "B", "C", "D", "E", "F", "G"}


def test_a_d_findings_are_detective_only(tmp_path):
    """Every A/D finding must carry source=detective-only — they're novel,
    not preventive re-runs."""
    _write(tmp_path / "CLAUDE.md", """
        # No dev block, A2 will skip
    """)
    findings = group_a.run(tmp_path, _default_config(), None) + \
        group_d.run(tmp_path, _default_config(), None)
    assert findings  # at least one finding came out of each
    for f in findings:
        assert f.source == SOURCE_DETECTIVE_ONLY
