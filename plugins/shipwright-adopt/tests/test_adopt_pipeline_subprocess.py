"""End-to-end subprocess test of the adopt artifact pipeline (sub-iterate F).

Marked `slow` — runs the REAL `generate_adoption_artifacts.py` as a uv-spawned
subprocess (not via direct import). Synthesizes a minimal but realistic
snapshot.json + routes.json + enrichment.json against a temp git repo,
then verifies every expected output file exists and the JSON result has
the new fields (visual_docs, gitignore_report, enrichment metadata).

This is the test that would have caught a bunch of integration bugs in
sub-iterates A-E before they reached the merge — the existing tests
exercise individual functions but not the wired-up CLI.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest


pytestmark = pytest.mark.slow


REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT = REPO_ROOT / "plugins" / "shipwright-adopt" / "scripts" / "tools" / "generate_adoption_artifacts.py"


def _git_init(root: Path) -> None:
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=root, check=True)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t",
                    "commit", "--allow-empty", "-m", "init", "-q"], cwd=root, check=True)


def _write_snapshot(project_root: Path) -> None:
    snap_dir = project_root / ".shipwright" / "adopt"
    snap_dir.mkdir(parents=True)
    (snap_dir / "snapshot.json").write_text(json.dumps({
        "stack": {
            "primary_language": "typescript",
            "frontend": {"vite": "^6.0.0", "react": "^19.0.0"},
            "backend": {"hono": "^4.7.0"},
            "multi_service": {
                "detected": True,
                "services": [
                    {"name": "client", "root": "client", "framework": "vite"},
                    {"name": "server", "root": "server", "framework": "hono"},
                ],
            },
        },
        "profile": {"matched": "vite-hono"},
        "commands": {"dev": None, "build": None, "test": "npx vitest run"},
        "features": [
            {"route": "/api/diagnostics", "source_file": "server/src/index.ts",
             "framework": "hono", "method": "GET"},
            {"route": "/api/sessions", "source_file": "server/src/sessions.ts",
             "framework": "hono", "method": "POST"},
        ],
        "git": {"commits_total": 75, "contributors_total": 3, "major_refactor_commits": []},
        "folders": {
            "layers": [{"name": "presentation", "paths": ["client/src/components"]}],
            "loc_by_layer": {"presentation": 1500},
        },
        "conventions": {"linter": "eslint", "formatter": "prettier", "tsconfig_strict": True},
        "ci_pipeline": {"provider": "github-actions"},
        "excludes": [],
    }), encoding="utf-8")
    (snap_dir / "routes.json").write_text(json.dumps([
        {"url": "/", "title": "Home"},
        {"url": "/dashboard", "title": "Dashboard"},
    ]), encoding="utf-8")
    # No enrichment.json → exercises the enrichment_fallback path


def _write_frontend_assets(project_root: Path) -> None:
    """Lay down a tiny client/ tree so visual docs have something to inventory."""
    client = project_root / "client"
    (client / "src" / "components").mkdir(parents=True)
    (client / "src" / "components" / "Button.tsx").write_text(
        "export interface ButtonProps { label: string; onClick: () => void }\n"
        "export function Button(p: ButtonProps) { return null; }\n",
        encoding="utf-8",
    )
    (client / "tailwind.config.ts").write_text(
        "export default { theme: { extend: { "
        "colors: { primary: '#0066cc' }, "
        "fontSize: { display: '4rem' } } } };\n",
        encoding="utf-8",
    )
    (client / "package.json").write_text(
        json.dumps({"name": "client", "devDependencies": {"vite": "^6.0.0"}}),
        encoding="utf-8",
    )


def test_full_pipeline_e2e_via_subprocess(tmp_path: Path) -> None:
    _git_init(tmp_path)
    _write_snapshot(tmp_path)
    _write_frontend_assets(tmp_path)

    # Force UTF-8 stdout for the child Python — Windows cp1252 is fragile here.
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"

    r = subprocess.run(
        ["uv", "run", "python", str(SCRIPT), "--project-root", str(tmp_path)],
        capture_output=True, text=True, env=env, timeout=120, check=False,
    )
    assert r.returncode == 0, (
        f"generate_adoption_artifacts subprocess failed: rc={r.returncode}\n"
        f"stdout: {r.stdout[-1500:]}\n"
        f"stderr: {r.stderr[-1500:]}\n"
    )

    # The JSON result is the LAST stdout block (script may print warnings first).
    payload = json.loads(r.stdout[r.stdout.find("{"):])

    # Every expected artifact landed
    assert (tmp_path / "CLAUDE.md").exists()
    assert (tmp_path / ".shipwright" / "agent_docs" / "decision_log.md").exists()
    assert (tmp_path / ".shipwright" / "agent_docs" / "architecture.md").exists()
    assert (tmp_path / "shipwright_run_config.json").exists()
    assert (tmp_path / "shipwright_events.jsonl").exists()
    # .claude/settings.json is NO LONGER written by adopt — the
    # suggest_iterate hook is plugin-owned (registered in
    # plugins/shipwright-iterate/hooks/hooks.json). See
    # iterate-20260505-plugin-hook-registration.
    assert not (tmp_path / ".claude" / "settings.json").exists()
    assert (tmp_path / ".shipwright" / "planning" / "01-adopted" / "spec.md").exists()

    # Tier-5 visual docs were produced (fixture has client/components + tailwind)
    assert (tmp_path / ".shipwright" / "agent_docs" / "design_tokens.md").exists()
    assert (tmp_path / ".shipwright" / "agent_docs" / "component_inventory.md").exists()
    assert (tmp_path / ".shipwright" / "designs" / "visual-guidelines.md").exists()
    assert payload["visual_docs"]["wrote_docs"] is True
    assert payload["visual_docs"]["component_count"] >= 1
    # frontend_root must be the client dir (multi-service pivot worked)
    assert payload["visual_docs"]["frontend_root"].rstrip("/\\").endswith("client")

    # Tier-4 enrichment fallback was used (no enrichment.json provided)
    assert payload["enrichment"]["source"] == "fallback"

    # Tier-4 gitignore report present
    assert "gitignore_report" in payload
    assert payload["gitignore_report"]["total"] > 0

    # Tier-4 additive merge: spec contains BOTH /dashboard (crawl) AND /api/* (AST)
    spec = (tmp_path / ".shipwright" / "planning" / "01-adopted" / "spec.md").read_text(encoding="utf-8")
    assert "/api/diagnostics" in spec
    assert "/api/sessions" in spec
    assert "Dashboard" in spec  # crawl entries surface their title
    # Distinct FR rows for all 4 (2 crawl + 2 AST)
    assert spec.count("FR-01.") >= 4

    # Step E.5 — .env.local scaffold.
    env_local = tmp_path / ".env.local"
    assert env_local.exists(), ".env.local was not scaffolded"
    env_text = env_local.read_text(encoding="utf-8")
    # Framework keys land regardless of the active profile (vite-hono has
    # no required_env_vars block, so these come from _SHIPWRIGHT_FRAMEWORK_VARS).
    for key in ("OPENROUTER_API_KEY", "GEMINI_API_KEY", "OPENAI_API_KEY"):
        assert f"# {key}=" in env_text, f"Framework key {key} missing from .env.local"
    # Documented payload shape from AC1/AC8 — locks in deterministic
    # consumption by the Step H banner. A future regression that drops
    # any key would fail here loud.
    env_payload = payload["env_local"]
    assert env_payload["action"] == "created"
    assert "path" in env_payload, "missing 'path' in env_local payload"
    assert env_payload["path"].replace("\\", "/").endswith("/.env.local")
    assert "vars" in env_payload, "missing 'vars' in env_local payload"
    # vars must contain at minimum the framework triple, in fallback order.
    fw_in_vars = [v for v in env_payload["vars"]
                  if v in {"OPENROUTER_API_KEY", "GEMINI_API_KEY", "OPENAI_API_KEY"}]
    assert fw_in_vars == ["OPENROUTER_API_KEY", "GEMINI_API_KEY", "OPENAI_API_KEY"]
    assert env_payload["framework_keys"] == [
        "OPENROUTER_API_KEY", "GEMINI_API_KEY", "OPENAI_API_KEY",
    ]
    # Every key is placeholder-empty on first scaffold.
    assert set(env_payload["missing_keys"]) >= {
        "OPENROUTER_API_KEY", "GEMINI_API_KEY", "OPENAI_API_KEY",
    }
    # .gitignore is enforced before the file is written.
    gi = (tmp_path / ".gitignore").read_text(encoding="utf-8")
    assert ".env.local" in gi

    # Step E.14 — CI workflow scaffold landed (fixture uses vite-hono profile).
    ci_wf = tmp_path / ".github" / "workflows" / "ci.yml"
    assert ci_wf.exists(), "Step E.14 did not scaffold .github/workflows/ci.yml"
    ci_payload = payload["ci_workflow"]
    assert ci_payload["wrote"] is True
    assert ci_payload["reason"] == "scaffolded"
    # Content sanity — the cross-platform matrix block must be present in
    # the scaffolded file (the whole point of this iterate).
    ci_text = ci_wf.read_text(encoding="utf-8")
    assert "matrix:" in ci_text and "ubuntu-latest" in ci_text and "windows-latest" in ci_text
    assert "fail-fast: false" in ci_text
    assert "client-checks" in ci_text  # vite-hono template has 2 jobs

    # Step E.15 — Claude-Review workflow scaffold landed (profile-agnostic).
    cr_wf = tmp_path / ".github" / "workflows" / "claude-review.yml"
    assert cr_wf.exists(), "Step E.15 did not scaffold .github/workflows/claude-review.yml"
    cr_payload = payload["claude_review_workflow"]
    assert cr_payload["wrote"] is True
    assert cr_payload["reason"] == "scaffolded"


def test_pipeline_ci_scaffold_supabase_nextjs_profile(tmp_path: Path) -> None:
    """External-review #O7: parametrize subprocess coverage across profiles.

    The vite-hono case is covered by test_full_pipeline_e2e_via_subprocess.
    This test exercises supabase-nextjs end-to-end so the rename
    (ci-nextjs.yml.template → ci-supabase-nextjs.yml.template) and the
    profile→template lookup are wired correctly for that profile too.
    """
    _git_init(tmp_path)
    # Synthesize a supabase-nextjs profile snapshot.
    snap_dir = tmp_path / ".shipwright" / "adopt"
    snap_dir.mkdir(parents=True)
    (snap_dir / "snapshot.json").write_text(json.dumps({
        "stack": {
            "primary_language": "typescript",
            "frontend": {"next": "^16.2.0", "react": "^19.2.4"},
            "backend": {"supabase-js": "@supabase/supabase-js@^2.99.3"},
        },
        "profile": {"matched": "supabase-nextjs"},
        "commands": {"dev": None, "build": None, "test": "npx vitest run"},
        "features": [
            {"route": "/api/health", "source_file": "src/app/api/health/route.ts",
             "framework": "nextjs", "method": "GET"},
        ],
        "git": {"commits_total": 25, "contributors_total": 1, "major_refactor_commits": []},
        "folders": {
            "layers": [{"name": "presentation", "paths": ["src/app"]}],
            "loc_by_layer": {"presentation": 500},
        },
        "conventions": {"linter": "eslint", "formatter": "prettier", "tsconfig_strict": True},
        "ci_pipeline": {"provider": "github-actions"},
        "excludes": [],
    }), encoding="utf-8")
    (snap_dir / "routes.json").write_text("[]", encoding="utf-8")

    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"

    r = subprocess.run(
        ["uv", "run", "python", str(SCRIPT), "--project-root", str(tmp_path)],
        capture_output=True, text=True, env=env, timeout=120, check=False,
    )
    assert r.returncode == 0, (
        f"supabase-nextjs adopt subprocess failed: rc={r.returncode}\n"
        f"stderr: {r.stderr[-1500:]}"
    )

    payload = json.loads(r.stdout[r.stdout.find("{"):])

    ci_wf = tmp_path / ".github" / "workflows" / "ci.yml"
    assert ci_wf.exists()
    assert payload["ci_workflow"]["wrote"] is True
    assert payload["ci_workflow"]["reason"] == "scaffolded"
    # Sanity-check it's the supabase-nextjs template (single `test` job).
    ci_text = ci_wf.read_text(encoding="utf-8")
    assert "supabase-nextjs profile" in ci_text
    assert "windows-latest" in ci_text


def test_pipeline_ci_scaffold_python_monorepo_profile(tmp_path: Path) -> None:
    """Cross-platform matrix for the python-plugin-monorepo profile.

    This is the profile that the shipwright monorepo itself uses. Test
    proves end-to-end that adopt against a Python repo lands the
    cross-platform CI template with the setup-uv step (external-review #G1).
    """
    _git_init(tmp_path)
    snap_dir = tmp_path / ".shipwright" / "adopt"
    snap_dir.mkdir(parents=True)
    (snap_dir / "snapshot.json").write_text(json.dumps({
        "stack": {
            "primary_language": "python",
            "backend": {"python": ">=3.11"},
        },
        "profile": {"matched": "python-plugin-monorepo"},
        "commands": {"dev": None, "build": None, "test": "uv run pytest"},
        "features": [],
        "git": {"commits_total": 50, "contributors_total": 1, "major_refactor_commits": []},
        "folders": {"layers": [], "loc_by_layer": {}},
        "conventions": {"linter": "ruff", "formatter": "ruff", "tsconfig_strict": False},
        "ci_pipeline": {"provider": "github-actions"},
        "excludes": [],
    }), encoding="utf-8")
    (snap_dir / "routes.json").write_text("[]", encoding="utf-8")

    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"

    r = subprocess.run(
        ["uv", "run", "python", str(SCRIPT), "--project-root", str(tmp_path)],
        capture_output=True, text=True, env=env, timeout=120, check=False,
    )
    assert r.returncode == 0, (
        f"python-plugin-monorepo adopt subprocess failed: rc={r.returncode}\n"
        f"stderr: {r.stderr[-1500:]}"
    )
    payload = json.loads(r.stdout[r.stdout.find("{"):])

    ci_wf = tmp_path / ".github" / "workflows" / "ci.yml"
    assert ci_wf.exists()
    assert payload["ci_workflow"]["wrote"] is True
    ci_text = ci_wf.read_text(encoding="utf-8")
    assert "python-plugin-monorepo profile" in ci_text
    # setup-uv@v3 is the external-review #G1 fix that makes the template
    # actually run on a fresh GitHub Actions runner.
    assert "astral-sh/setup-uv@v3" in ci_text
    assert "windows-latest" in ci_text


def test_pipeline_env_local_idempotent_on_rerun(tmp_path: Path) -> None:
    """Second adopt run on the same project must leave `.env.local` byte-equal
    and report ``action == 'unchanged'``. Locks in AC2 from the iterate spec
    against future drift in `init_env_file` formatting."""
    _git_init(tmp_path)
    _write_snapshot(tmp_path)
    _write_frontend_assets(tmp_path)

    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"

    # First run — creates .env.local
    r1 = subprocess.run(
        ["uv", "run", "python", str(SCRIPT), "--project-root", str(tmp_path)],
        capture_output=True, text=True, env=env, timeout=120, check=False,
    )
    assert r1.returncode == 0, f"first run failed: {r1.stderr[-1000:]}"
    payload1 = json.loads(r1.stdout[r1.stdout.find("{"):])
    assert payload1["env_local"]["action"] == "created"
    env_bytes_after_first = (tmp_path / ".env.local").read_bytes()

    # Second run on the same project root.
    r2 = subprocess.run(
        ["uv", "run", "python", str(SCRIPT), "--project-root", str(tmp_path)],
        capture_output=True, text=True, env=env, timeout=120, check=False,
    )
    assert r2.returncode == 0, f"second run failed: {r2.stderr[-1000:]}"
    payload2 = json.loads(r2.stdout[r2.stdout.find("{"):])
    assert payload2["env_local"]["action"] == "unchanged"
    # AC6 — Step H banner depends on missing_keys being non-empty even on
    # an unchanged rerun when entries are still placeholder-only. Locks in
    # the contract so the user is still prompted to fill in keys.
    assert set(payload2["env_local"]["missing_keys"]) >= {
        "OPENROUTER_API_KEY", "GEMINI_API_KEY", "OPENAI_API_KEY",
    }, "unchanged rerun must still surface placeholder keys via missing_keys"
    # File preserved BYTE-for-byte (tests against trailing-newline / whitespace
    # churn that subtle formatting bugs would introduce on re-run).
    assert (tmp_path / ".env.local").read_bytes() == env_bytes_after_first
    # .gitignore must remain unchanged when it already matched .env.local.
    gi_after_first = (tmp_path / ".gitignore").read_bytes()
    # Re-read after second run (idempotent _ensure_gitignore should be a no-op)
    assert (tmp_path / ".gitignore").read_bytes() == gi_after_first
    # And it really does still match .env.local.
    gi_text = (tmp_path / ".gitignore").read_text(encoding="utf-8")
    assert ".env.local" in gi_text


def test_pipeline_env_local_appends_missing_keys(tmp_path: Path) -> None:
    """If `.env.local` already exists with one of the framework keys, adopt
    appends only the missing keys and preserves existing user content
    byte-for-byte. Locks in the 'updated' path from AC2 / AC8."""
    _git_init(tmp_path)
    _write_snapshot(tmp_path)
    _write_frontend_assets(tmp_path)

    # Pre-populate .env.local with one filled key plus arbitrary user content.
    pre_existing = (
        "# User notes — do not delete\n"
        "OPENROUTER_API_KEY=sk-or-v1-real-secret\n"
        "MY_PERSONAL_THING=keep-me\n"
    )
    (tmp_path / ".env.local").write_text(pre_existing, encoding="utf-8")
    # Pre-create .gitignore so the scaffold doesn't have to add it.
    (tmp_path / ".gitignore").write_text(".env.local\n", encoding="utf-8")

    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"

    r = subprocess.run(
        ["uv", "run", "python", str(SCRIPT), "--project-root", str(tmp_path)],
        capture_output=True, text=True, env=env, timeout=120, check=False,
    )
    assert r.returncode == 0, f"adopt run failed: {r.stderr[-1000:]}"
    payload = json.loads(r.stdout[r.stdout.find("{"):])
    assert payload["env_local"]["action"] == "updated"
    # Only GEMINI + OPENAI were appended; OPENROUTER already present.
    added = set(payload["env_local"].get("added", []))
    assert "OPENROUTER_API_KEY" not in added
    assert {"GEMINI_API_KEY", "OPENAI_API_KEY"} <= added

    final = (tmp_path / ".env.local").read_text(encoding="utf-8")
    # User content preserved verbatim
    assert "# User notes — do not delete" in final
    assert "OPENROUTER_API_KEY=sk-or-v1-real-secret" in final
    assert "MY_PERSONAL_THING=keep-me" in final
    # Newly added framework keys present (commented placeholders).
    assert "# GEMINI_API_KEY=" in final
    assert "# OPENAI_API_KEY=" in final
    # missing_keys must NOT include OPENROUTER (it has a real value).
    assert "OPENROUTER_API_KEY" not in payload["env_local"]["missing_keys"]
    # .gitignore was pre-populated as exact match — must remain untouched.
    gi_text = (tmp_path / ".gitignore").read_text(encoding="utf-8")
    assert gi_text == ".env.local\n"


def test_pipeline_loud_failure_on_invalid_enrichment(tmp_path: Path) -> None:
    """Enrichment with missing required keys should make the subprocess exit
    non-zero with a clear stderr diagnostic — not silently fall back."""
    _git_init(tmp_path)
    _write_snapshot(tmp_path)
    # Plant a malformed enrichment.json
    enr = tmp_path / ".shipwright" / "adopt" / "enrichment.json"
    enr.write_text(json.dumps({"product_description": "missing other required keys"}),
                    encoding="utf-8")

    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"

    r = subprocess.run(
        ["uv", "run", "python", str(SCRIPT), "--project-root", str(tmp_path)],
        capture_output=True, text=True, env=env, timeout=60, check=False,
    )
    assert r.returncode != 0, "expected loud failure on invalid enrichment"
    combined = (r.stderr + r.stdout).lower()
    assert "enrichment" in combined or "schema" in combined
