"""Unit tests for dry_run_reporter."""

from pathlib import Path

from lib.dry_run_reporter import plan_standard_writes, ProposedWrite, DryRunReport


def test_standard_writes_lists_all_expected(tmp_path: Path) -> None:
    report = plan_standard_writes(
        tmp_path,
        split_name="01-adopted",
        write_sync=True,
        crawl_succeeded=True,
        nested_excluded=["webui"],
    )
    paths = [w.path for w in report.writes]
    assert "CLAUDE.md" in paths
    assert ".shipwright/agent_docs/architecture.md" in paths
    assert ".shipwright/planning/01-adopted/spec.md" in paths
    assert "shipwright_run_config.json" in paths
    assert "shipwright_sync_config.json" in paths
    assert "e2e/flows/adopted-baseline.spec.ts" in paths
    # .claude/settings.json is NOT written — hook is plugin-owned now.
    assert ".claude/settings.json" not in paths


def test_no_sync_no_crawl(tmp_path: Path) -> None:
    report = plan_standard_writes(
        tmp_path, split_name="01-adopted", write_sync=False,
        crawl_succeeded=False, nested_excluded=[],
    )
    paths = [w.path for w in report.writes]
    assert "shipwright_sync_config.json" not in paths
    assert "e2e/flows/adopted-baseline.spec.ts" not in paths


def test_render_includes_sections() -> None:
    report = DryRunReport(
        writes=[ProposedWrite("foo.md", "create", "why")],
        excluded_paths=["webui"],
        commit_message="chore(shipwright): adopt",
        crawl_enabled=True,
    )
    rendered = report.render()
    assert "DRY RUN" in rendered
    assert "foo.md" in rendered
    assert "webui" in rendered
    assert "chore(shipwright): adopt" in rendered
    assert "Playwright crawl: enabled" in rendered
