"""Which runnable surfaces a path touches (``_surface_detect``), and the F0.5 producer's ``--reason-code``."""

from __future__ import annotations

import pytest

from surface_verification import EXIT_NONE_WITHOUT_JUSTIFICATION, EXIT_OK, verify_surface
from tools.verifiers._surface_detect import detect_surfaces, split_patch
from tools.verifiers._surface_evidence import runner_test_paths


@pytest.mark.covers("FR-01.11/AC07")
@pytest.mark.parametrize(("path", "kind"), [
    ("webui/client/src/App.tsx", "ui"),
    ("client/src/styles/board.css", "ui"),
    ("server/src/routes/tasks.ts", "api_route"),
    ("app/api/users/handler.py", "api_route"),
    ("backend/urls.py", "api_route"),
    ("server/tasks.controller.ts", "api_route"),
    ("server/src/sse.ts", "realtime"),
    ("server/ws/hub.go", "realtime"),
    ("proto/events.proto", "message_contract"),
    ("api/openapi.yaml", "message_contract"),
    ("shared/contracts/iterate.py", "message_contract"),
    ("app/router.py", "api_route"),  # ambiguous names count: a false positive costs one cli run
    ("shared/scripts/lib/triage_route.py", "api_route"),
])
def test_each_surface_kind_is_detected(path, kind):
    assert path in detect_surfaces([path]).get(kind, [])


@pytest.mark.covers("FR-01.11/AC07")
@pytest.mark.parametrize("path", [
    "shared/tests/test_routes.py",            # a test, whatever its name says
    "client/src/__tests__/Board.test.tsx",
    "e2e/board.spec.ts",
    "plugins/x/tests/fixtures/routes/api.py",
    "docs/api/routes.md",                     # prose
    "server/routes/README.md",
    ".github/workflows/ci.yml",
    ".shipwright/agent_docs/architecture.md",  # a finalization record
    "shipwright_test_results.json",
    "shared/scripts/tools/verifiers/iterate_checks.py",
])
def test_tests_prose_records_and_tooling_are_never_a_surface(path):
    assert detect_surfaces([path]) == {}


@pytest.mark.covers("FR-01.11/AC07")
def test_paths_are_normalised_and_grouped_per_kind():
    found = detect_surfaces([".\\server\\routes\\a.ts", "server/routes/a.ts", "client/src/B.tsx"])
    assert found == {"ui": ["client/src/B.tsx"], "api_route": ["server/routes/a.ts"]}


@pytest.mark.covers("FR-01.11/AC07")
@pytest.mark.parametrize(("line", "kind"), [
    ('@app.get("/tasks")', "api_route"),
    ("router = APIRouter(prefix='/v1')", "api_route"),
    ("const r = express.Router();", "api_route"),
    ("app.post('/login', handler)", "api_route"),
    ("const ws = new WebSocket(url);", "realtime"),
    ("res.setHeader('Content-Type', 'text/event-stream')", "realtime"),
])
def test_changed_lines_reveal_a_surface_the_path_does_not(line, kind):
    patch = "\n".join(["diff --git a/server/main.ts b/server/main.ts", "--- a/server/main.ts",
                       "+++ b/server/main.ts", "@@ -1,0 +2 @@", f"+{line}"])
    changed = split_patch(patch)
    assert detect_surfaces(["server/main.ts"]) == {}
    assert "server/main.ts" in detect_surfaces(["server/main.ts"], changed).get(kind, [])


@pytest.mark.covers("FR-01.11/AC07")
def test_split_patch_keeps_both_sides_and_ignores_header_lookalikes():
    patch = "\n".join([
        "diff --git a/old.py b/old.py", "deleted file mode 100644", "--- a/old.py", "+++ /dev/null",
        "@@ -1 +0,0 @@", "-gone = 1", "--- not a header",
        "diff --git a/new.py b/new.py", "--- /dev/null", "+++ b/new.py", "@@ -0,0 +1 @@", "+added = 2",
    ])
    assert split_patch(patch) == {"old.py": "gone = 1\n-- not a header", "new.py": "added = 2"}


@pytest.mark.covers("FR-01.11/AC07")
def test_runner_test_paths_keep_only_existing_test_paths(tmp_path):
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_a.py").write_text("", encoding="utf-8")
    (tmp_path / "tools").mkdir()
    (tmp_path / "tools" / "probe.py").write_text("", encoding="utf-8")
    runner = ("uv run pytest tests/test_a.py::test_x tests/test_gone.py tools/probe.py "
              "--project-root /abs -q")
    assert runner_test_paths(tmp_path, runner) == ["tests/test_a.py"]


@pytest.mark.covers("FR-01.11/AC07")
def test_producer_records_a_closed_reason_code_for_none(tmp_path):
    code, block = verify_surface(project_root=tmp_path, run_id="r", surface="none", runner=None,
                                 justification="docs only", tests_run_override=None,
                                 reason_code="docs-only")
    assert code == EXIT_OK and block["reason_code"] == "docs-only"


@pytest.mark.covers("FR-01.11/AC07")
def test_producer_refuses_a_reason_code_outside_the_vocabulary(tmp_path):
    code, block = verify_surface(project_root=tmp_path, run_id="r", surface="none", runner=None,
                                 justification="docs only", tests_run_override=None,
                                 reason_code="because")
    assert code == EXIT_NONE_WITHOUT_JUSTIFICATION
    assert "surface_none" in block["error"] and "reason_code" not in block
