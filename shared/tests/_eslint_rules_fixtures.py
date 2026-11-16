"""Shared fixtures for the eslint architecture-rule tests: create-next-app configs and a project builder."""

from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(ROOT / "shared" / "scripts"))
import eslint_architecture_rules as ear  # noqa: E402

TOOL = ROOT / "shared" / "scripts" / "tools" / "check_eslint_architecture_rules.py"
TEMPLATE = ROOT / "shared" / "templates" / "eslint" / "eslint.config.mjs.template"
IDS = ["supabase-client-through-helpers", "no-fetch-in-components"]

NEXT16 = """import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";

const eslintConfig = defineConfig([
  ...nextVitals,
  ...nextTs,
  // Override default ignores of eslint-config-next.
  globalIgnores([
    // Default ignores of eslint-config-next:
    ".next/**",
    "out/**",
    "build/**",
    "next-env.d.ts",
  ]),
]);

export default eslintConfig;
"""

NEXT15 = """import { dirname } from "path";
import { fileURLToPath } from "url";
import { FlatCompat } from "@eslint/eslintrc";

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

const compat = new FlatCompat({
  baseDirectory: __dirname,
});

const eslintConfig = [
  ...compat.extends("next/core-web-vitals", "next/typescript"),
];

export default eslintConfig;
"""


def _project(tmp_path: Path, config: str | None = None, name: str = "eslint.config.mjs", profile: str = "supabase-nextjs",
             package: bool = True) -> Path:
    (tmp_path / "shipwright_run_config.json").write_text(json.dumps({"profile": profile}), encoding="utf-8")
    if package:
        (tmp_path / "package.json").write_text(json.dumps({"devDependencies": {"eslint": "^10", "typescript-eslint": "^8",
                                                                                "typescript": "^5"}}), encoding="utf-8")
    if config is not None:
        (tmp_path / name).write_bytes(config.encode("utf-8"))
    return tmp_path


def _rules(tmp_path: Path):
    return ear.rules_for_project(tmp_path)[1]


def _statuses(tmp_path: Path) -> dict:
    return {f.rule_id: f.status for f in ear.check(tmp_path, _rules(tmp_path)).findings}


