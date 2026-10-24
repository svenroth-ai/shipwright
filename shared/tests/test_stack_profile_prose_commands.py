"""Prose is runtime code (campaign stack-profile-resolver S4): every
``resolve_profile.py`` command shape in the edited skill prose is extracted,
placeholders are filled from a tmp fixture project, and the command is run.

Tagged to FR-01.06; see test_profile_resolver.py for the FR note.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

from shared.tests.profile_test_fixtures import proj_dir, write_profile
from shared.tests.profile_test_fixtures import profile_project, profile_user_dir  # noqa: F401  (fixtures "project", "user_dir")

pytestmark = pytest.mark.covers("FR-01.06")

REPO = Path(__file__).resolve().parents[2]
SHARED = REPO / "shared"
PROSE = [
    "plugins/shipwright-test/skills/test/references/first-actions.md",
    "plugins/shipwright-preview/skills/preview/SKILL.md",
    "plugins/shipwright-project/skills/project/references/project-scaffolding.md",
    "plugins/shipwright-project/skills/project/references/step-7-scaffolding.md",
    "plugins/shipwright-security/skills/security/SKILL.md",
    "plugins/shipwright-build/agents/section-builder.md",
    "plugins/shipwright-build/skills/build/references/migrations-apply.md",
    "plugins/shipwright-test/agents/test-runner.md",
]

def _snippets() -> list[tuple[str, str]]:
    found = []
    for rel in PROSE:
        text = (REPO / rel).read_text(encoding="utf-8")
        for m in re.finditer(r'uv run --no-project\s+"[^"]*resolve_profile\.py"[^`]*', text):
            raw = m.group(0)
            # keep the command (up to the closing paren / backtick / end of a continuation block)
            lines, cmd = raw.splitlines(), []
            for ln in lines:
                cmd.append(ln.rstrip("\\").strip())
                if not ln.rstrip().endswith("\\"):
                    break
            found.append((rel, " ".join(cmd)))
    return found


def _fill(cmd: str, project: Path, name: str) -> list[str]:
    tokens = re.findall(r'"[^"]*"|\S+', cmd)  # quoted arguments stay whole (paths with spaces)
    subs = {"${SHIPWRIGHT_PLUGIN_ROOT}/../..": str(REPO), "{shared_root}": str(SHARED),
            "${SHIPWRIGHT_PROJECT_ROOT}": str(project), "{project_root}": str(project),
            "{profile_name}": name, "{profile}": name}
    out = []
    for tok in tokens:
        tok = tok.strip('"')
        for old, new in subs.items():
            tok = tok.replace(old, new)
        out.append(tok)
    return out


def test_prose_snippets_are_found():
    assert {rel for rel, _ in _snippets()} == set(PROSE)  # one per edited file; a vanished snippet fails


@pytest.mark.parametrize("rel,cmd", _snippets(), ids=lambda v: v if isinstance(v, str) and "/" in v and " " not in v else None)
def test_snippet_runs_against_fixture(rel, cmd, project, user_dir):
    write_profile(proj_dir(project), "my-stack")
    args = _fill(cmd, project, "my-stack")
    assert args[:3] == ["uv", "run", "--no-project"], (rel, cmd)
    done = subprocess.run(args, capture_output=True, text=True, encoding="utf-8", timeout=120)
    assert done.returncode == 0, (rel, cmd, done.stderr)
    if "--path-only" in args:
        assert done.stdout.strip().endswith("my-stack.json")
        assert re.search(r'--name "\{profile(?:_name)?\}"', cmd), (rel, cmd)  # the name is quoted
        blank = [*args[:args.index("--name") + 1], "", *args[args.index("--name") + 2:]]
        empty = subprocess.run(blank, capture_output=True, text=True, encoding="utf-8", timeout=120)
        assert empty.returncode == 4 and empty.stdout == "", (rel, empty.returncode)  # an empty name never reads as defaults
    # an unknown name is the documented "profile problem" exit 2; a sentinel is built-in defaults
    if "--name" in args:
        bad = [*args[:args.index("--name") + 1], "no-such-stack", *args[args.index("--name") + 2:]]
        assert subprocess.run(bad, capture_output=True, text=True, encoding="utf-8", timeout=120).returncode == 2
        sent = [*args[:args.index("--name") + 1], "generic", *args[args.index("--name") + 2:]]
        gen = subprocess.run(sent, capture_output=True, text=True, encoding="utf-8", timeout=120)
        assert gen.returncode == 0 and gen.stdout.strip() == ""


def test_test_layer_prose_passes_the_name_never_a_bundled_path():
    layer = REPO / "plugins/shipwright-test/skills/test"
    for rel in ("references/step-1-unit-tests.md", "references/step-1.5-integration-tests.md",
                "references/step-1.6-pgtap-tests.md", "SKILL.md"):
        text = (layer / rel).read_text(encoding="utf-8")
        assert "--profile-path" not in text, rel
        assert '--profile "{profile}"' in text, rel
    perf = (layer / "references/step-3.8-performance-budget.md").read_text(encoding="utf-8")
    assert '--profile "{profile}" --project-root "{project_root}"' in perf
    assert "--profile-path" not in perf


def test_dev_server_sites_carry_the_stop_on_profile_error_sentence():
    sites = [
        "plugins/shipwright-iterate/skills/iterate/references/design-and-testing.md",
        "plugins/shipwright-build/skills/build/references/browser-verify.md",
        "plugins/shipwright-build/agents/section-builder.md",
        "plugins/shipwright-test/skills/test/references/step-3-playwright-e2e.md",
        "plugins/shipwright-test/agents/test-runner.md",
        "plugins/shipwright-adopt/skills/adopt/references/step-b5-route-discovery.md",
        "plugins/shipwright-preview/skills/preview/SKILL.md",
    ]
    for rel in sites:
        lines = (REPO / rel).read_text(encoding="utf-8").splitlines()
        starts = [i for i, ln in enumerate(lines) if "dev_server.py" in ln and " start" in " ".join(lines[i:i + 2])]
        profile_starts = [i for i in starts if any("--profile" in ln for ln in lines[i:i + 3])]
        assert profile_starts, rel
        for i in profile_starts:  # the rule follows EACH --profile start block
            assert any("stop and show the message" in ln for ln in lines[i:i + 8]), (rel, i + 1)


def _path_only_gaps(lines: list[str]) -> list[int]:
    """Line numbers of ``--path-only`` snippets lacking the empty-output, stop and name-pattern clauses nearby."""
    gaps = []
    for i, ln in enumerate(lines):
        if "resolve_profile.py" in ln and "--path-only" in " ".join(lines[i:i + 3]):
            near = " ".join(lines[max(0, i - 4):i + 5]).lower()
            ok_empty = "built-in defaults" in near and "empty" in near and "exit 0" in near
            ok_stop = "non-zero" in near and "stop and show the message" in near  # exit 4/1 also have empty stdout
            ok_name = "a-z0-9" in near  # the name pattern is the real guard against shell metacharacters
            if not (ok_empty and ok_stop and ok_name):
                gaps.append(i + 1)
    return gaps


def test_every_path_only_snippet_states_the_empty_and_error_branches():
    for rel in PROSE:
        lines = (REPO / rel).read_text(encoding="utf-8").splitlines()
        assert not _path_only_gaps(lines), rel


def test_path_only_branch_check_is_red_on_a_planted_omission_and_green_when_fixed():
    bare = ['Load: `uv run --no-project "x/resolve_profile.py" resolve --name a --path-only`.']
    assert _path_only_gaps(bare) == [1]
    old_wording = [bare[0][:-1] + " (empty = built-in defaults; exit 2/3: stop, show message)."]
    assert _path_only_gaps(old_wording) == [1]  # exit 4/1 would read as "defaults"
    fixed = [bare[0][:-1] + " (exit 0 with empty output = built-in defaults; any other non-zero exit = stop and show the message, do not retry; name must match `^[a-z0-9][a-z0-9-]*$`, otherwise stop)."]
    assert _path_only_gaps(fixed) == []
    no_name = [bare[0][:-1] + " (exit 0 with empty output = built-in defaults; any other non-zero exit = stop and show the message, do not retry)."]
    assert _path_only_gaps(no_name) == [1]  # a site may not drop the name-pattern clause
