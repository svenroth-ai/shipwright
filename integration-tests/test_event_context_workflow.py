from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CATALOG_CLI = REPO_ROOT / "shared/scripts/tools/area_catalog.py"
CONTEXT_CLI = REPO_ROOT / "shared/scripts/tools/event_context.py"


def _run(*args: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, *args], cwd=cwd, text=True, capture_output=True, check=False)


def test_public_cli_catalog_index_query_metrics_round_trip(tmp_path: Path) -> None:
    split = tmp_path / ".shipwright/planning/01-orders/sections"
    split.mkdir(parents=True)
    (split.parent / "spec.md").write_text("FR-01.01\n", encoding="utf-8")
    (split / "01-api.md").write_text("Create `src/orders/api.py`\n", encoding="utf-8")
    events = [
        {"event_id": "orders-old", "type": "work_completed", "changed_files": ["src/orders/api.py"],
         "affected_frs": ["FR-01.01"], "description": "Prior orders change"},
        {"event_id": "global", "type": "grade_snapshot", "description": "Safety baseline"},
    ]
    (tmp_path / "shipwright_events.jsonl").write_text(
        "".join(json.dumps(event) + "\n" for event in events), encoding="utf-8"
    )
    seed = _run(str(CATALOG_CLI), "seed-greenfield", "--project-root", str(tmp_path),
                "--source", "project", cwd=tmp_path)
    assert seed.returncode == 0, seed.stderr
    output = tmp_path / ".shipwright/runtime/bundle.json"
    query = _run(str(CONTEXT_CLI), "query", "--project-root", str(tmp_path),
                 "--run-id", "iterate-integration", "--changed-file", "src/orders/api.py",
                 "--max-events", "1", "--output", str(output), cwd=tmp_path)
    assert query.returncode == 0, query.stderr
    bundle = json.loads(output.read_text(encoding="utf-8"))
    assert bundle["selected_event_ids"] == ["orders-old"]
    assert bundle["provenance"]["raw_source_of_truth"] is True
    assert (tmp_path / ".shipwright/runtime/events-context-index.json").exists()
    assert (tmp_path / ".shipwright/compliance/context-cost/events-context-metrics.jsonl").exists()
    assert "Reduction" in (tmp_path / ".shipwright/compliance/context-cost/events-context-report.md").read_text()


def test_all_phase_surfaces_invoke_one_catalog_producer() -> None:
    files = {
        "project": REPO_ROOT / "plugins/shipwright-project/skills/project/SKILL.md",
        "plan": REPO_ROOT / "plugins/shipwright-plan/skills/plan/SKILL.md",
        "adopt": REPO_ROOT / "plugins/shipwright-adopt/skills/adopt/SKILL.md",
        "build": REPO_ROOT / "plugins/shipwright-build/skills/build/references/section-state.md",
        "build-agent": REPO_ROOT / "plugins/shipwright-build/agents/section-builder.md",
        "iterate": REPO_ROOT / "plugins/shipwright-iterate/skills/iterate/references/context-loading.md",
    }
    for phase, path in files.items():
        text = path.read_text(encoding="utf-8")
        assert "scripts/tools/area_catalog.py" in text, f"{phase} does not invoke canonical producer"
