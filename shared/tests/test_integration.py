"""Integration tests: templates + handoff + decision log together."""


from lib.config import read_config, write_config
from lib.state import get_checkpoint
from tools.generate_session_handoff import generate_handoff
from tools.write_decision_log import append_decision


def test_full_workflow(tmp_project):
    """Test the full workflow: config → decision → handoff."""
    # 1. Write run config
    write_config("run", tmp_project, {
        "scope": "full_app",
        "profile": "supabase-nextjs",
        "autonomy_level": 2,
        "current_step": "build",
        "completed_steps": ["project", "design", "plan"],
        "completed_splits": ["01-auth"],
        "pipeline": ["project", "design", "plan", "build", "test", "changelog", "deploy"],
    })

    # 2. Write project config with splits
    write_config("project", tmp_project, {
        "status": "complete",
        "splits": [
            {"name": "01-auth", "status": "complete"},
            {"name": "02-dashboard", "status": "in_progress"},
        ],
    })

    # 3. Write build config
    write_config("build", tmp_project, {
        "sections": [
            {"name": "01-layout", "status": "complete", "commit": "abc1234"},
        ],
    })

    # 4. Append a decision
    number = append_decision(
        tmp_project,
        section_ref="Section 01: Layout",
        commit_hash="abc1234",
        context="Needed sidebar vs top nav",
        decision="Sidebar nav for dashboard",
        consequences="More vertical space, standard SaaS pattern",
        rejected="Top nav (less room for nav items)",
    )
    assert number == 1

    # 5. Generate handoff
    content = generate_handoff(tmp_project, session_id="integration-test")

    # Verify handoff contains state info
    assert "integration-test" in content
    assert "build" in content  # current phase
    assert "exists" in content  # config files exist

    # Verify handoff includes decision
    assert "ADR-001" in content

    # 6. Verify checkpoint
    checkpoint = get_checkpoint(tmp_project)
    assert checkpoint["phase"] == "build"
    assert checkpoint["completed_splits"] == 1
    assert checkpoint["current_split"] == "02-dashboard"


def test_cost_tracking_integration(tmp_project):
    """Test cost tracker integrates with config system."""
    from lib.cost_tracker import get_project_cost_summary, record_section_cost

    write_config("build", tmp_project, {"sections": []})

    record_section_cost(tmp_project, "01-auth", estimated_tokens=50000, estimated_api_calls=12)
    record_section_cost(tmp_project, "02-dashboard", estimated_tokens=75000, estimated_api_calls=18)

    summary = get_project_cost_summary(tmp_project)
    assert summary["total_tokens"] == 125000
    assert summary["total_api_calls"] == 30
    assert summary["section_count"] == 2

    # Verify it's in the build config
    config = read_config("build", tmp_project)
    assert config["sections"][0]["estimated_tokens_used"] == 50000
